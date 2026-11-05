"""Whole-tenancy deletion guards and multi-person publication independent of OCI or PostgreSQL."""

from contextlib import nullcontext
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import attach, intent, person, principal, registry, service

from otm.providers.lifecycle import LifecycleBlocked, LifecycleCompletion
from otm.storage.organization import OrganizationConflict
from otm.tenancies.deletion import (
    TenancyDeletionCommand,
    deletion_plan,
    publish_deletion,
    validate_deletion,
)

__all__ = ["registry"]


# Model two distinct people with exact current associations, independent of their source presence.
def shared_case(state):
    app, owner = service(state), person(state)
    row, link = attach(state, owner, kind="shared")
    member = person(state, "delegate@example.test")
    second = {**link, "id": uuid4(), "person_id": member.id, "role": "member"}
    state.links = (*state.links, second)
    return app, owner, member, row


# Complete plans freeze every user/role and refuse unregistered parents, pending work and wrong
# scope.
def test_complete_plan_and_target_guards(registry):
    s = registry
    app, owner, member, row = shared_case(s)
    plan = deletion_plan(s, row["id"], app.policy)
    assert {a.person_id for a in plan} == {owner.id, member.id} and all(
        a.action == "delete" for a in plan
    )
    with pytest.raises(OrganizationConflict, match="NOT_FOUND"):
        deletion_plan(s, uuid4(), app.policy)
    for field, value in [("status", "pending"), ("operation_id", uuid4())]:
        old = row[field]
        row[field] = value
        with pytest.raises(OrganizationConflict, match="UNAVAILABLE"):
            deletion_plan(s, row["id"], app.policy)
        row[field] = old
    row["tenancy_ocid"] = app.policy.parent_tenancy_ocid
    with pytest.raises(OrganizationConflict, match="REGISTERED_CHILD"):
        deletion_plan(s, row["id"], app.policy)


# Dispatch checks the full frozen set and each person's reservation, not only the initiating owner.
def test_dispatch_fences_changed_membership_and_roles(registry):
    s = registry
    app, owner, member, row = shared_case(s)
    plan = deletion_plan(s, row["id"], app.policy)
    op = uuid4()
    frozen = intent(
        s, app, owner, action="delete_tenancy", whole_tenancy_deletion=True, associations=plan
    )
    frozen = frozen.model_copy(
        update={"target": frozen.target.model_copy(update={"tenancy_ocid": row["tenancy_ocid"]})}
    )
    row.update(status="terminating", operation_id=op)
    for link in s.links:
        link.update(status="removing", operation_id=op)
        s.controls[link["person_id"]]["pending_operation_id"] = op
    validate_deletion(s, frozen, op)
    with pytest.raises(LifecycleBlocked):
        validate_deletion(s, frozen.model_copy(update={"associations": ()}), op)
    s.links = (*s.links, {**s.links[0], "id": uuid4()})
    with pytest.raises(LifecycleBlocked):
        validate_deletion(s, frozen, op)
    s.links = s.links[:-1]
    s.controls[member.id]["pending_operation_id"] = uuid4()
    with pytest.raises(LifecycleBlocked):
        validate_deletion(s, frozen, op)
    s.controls[member.id]["pending_operation_id"] = op
    s.links[1]["user_ocid"] = "changed"
    with pytest.raises(LifecycleBlocked):
        validate_deletion(s, frozen, op)


# Publication computes other associations independently and retains immutable identity/history
# anchors.
def test_publication_preserves_other_tenancies_and_records_each_person(registry):
    s = registry
    app, owner, member, row = shared_case(s)
    plan = deletion_plan(s, row["id"], app.policy)
    op = uuid4()
    frozen = intent(
        s, app, owner, action="delete_tenancy", whole_tenancy_deletion=True, associations=plan
    )
    connection = MagicMock()

    # Only the member has another tenancy; SQL still scopes that check to the exact person.
    def results(statement):
        values = statement.compile().params
        return Mock(first=Mock(return_value=(uuid4(),) if member.id in values.values() else None))

    connection.execute.side_effect = results
    with patch("otm.tenancies.deletion.add_change") as history:
        publish_deletion(connection, s, frozen, LifecycleCompletion(), op, NOW)
        assert history.call_count == 2
    updates = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_update", False)
    ]
    assert any(v.get("directory_status") == "offboarded" for v in updates)
    assert any(v.get("directory_status") == "included" for v in updates)
    assert any(v.get("status") == "terminated" for v in updates)
    with pytest.raises(LifecycleBlocked):
        publish_deletion(connection, s, frozen, Mock(bindings=("unexpected",)), op, NOW)


# Preview and command admission require current context/confirmations and share existing atomic
# admission.
def test_service_preview_admission_replay_and_confirmation_guards(registry):
    s = registry
    app, owner, _, row = shared_case(s)
    s.people[owner.id] = owner.model_copy(update={"known_manager": True})
    connection = MagicMock()
    app.store._principal.return_value = s.workspace
    app.store._write.return_value = nullcontext((connection, s.workspace, NOW))
    with (
        patch("otm.tenancies.workflows.read_snapshot", return_value=nullcontext(connection)),
        patch("otm.tenancies.workflows.registry_state", return_value=s),
    ):
        preview = app.deletion_preview(principal(), row["id"])
        assert len(preview.people) == 2 and preview.shared_warning and preview.manager_warning
        command = TenancyDeletionCommand(
            client_request_key=uuid4(), tenancy_id=row["id"], context=s.context
        )
        with (
            patch.object(app, "_replay", return_value=None),
            patch.object(app, "_admit", return_value="accepted") as accept,
        ):
            for fields, code in [
                ({}, "DELETION_CONFIRMATION"),
                ({"confirm_deletion": True}, "MANAGER_CONFIRMATION"),
                ({"confirm_deletion": True, "confirm_manager": True}, "SHARED_CONFIRMATION"),
            ]:
                with pytest.raises(OrganizationConflict, match=code):
                    app.delete_tenancy(principal(), command.model_copy(update=fields))
            confirmed = command.model_copy(
                update={"confirm_deletion": True, "confirm_manager": True, "confirm_shared": True}
            )
            assert app.delete_tenancy(principal(), confirmed) == "accepted"
            assert len(accept.call_args.kwargs["deletion_plan"]) == 2
        with patch.object(app, "_replay", return_value="same operation"):
            assert app.delete_tenancy(principal(), command) == "same operation"
    with pytest.raises(ValueError):
        TenancyDeletionCommand.model_validate({**command.model_dump(), "member_ids": [uuid4()]})


# New HTTP inputs are bounded and closed; a client cannot supply its own whole-delete member set.
def test_deletion_http_validation_and_receipts(registry):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from otm.tenancies.contracts import ActionReceipt
    from otm.tenancies.http import workflow_router

    s = registry
    app, _, _, row = shared_case(s)
    connection = MagicMock()
    app.store._principal.return_value = s.workspace
    with (
        patch("otm.tenancies.workflows.read_snapshot", return_value=nullcontext(connection)),
        patch("otm.tenancies.workflows.registry_state", return_value=s),
    ):
        preview = app.deletion_preview(principal(), row["id"])
    boundary, http = Mock(), FastAPI()
    boundary.deletion_preview.return_value = preview
    boundary.delete_tenancy.return_value = ActionReceipt(
        operation_id=uuid4(), state="queued", provider_mode="simulated", accepted_at=NOW
    )

    # This adapter test separates authentication (covered by real HTTPS browser cases) from parsing.
    @http.middleware("http")
    async def test_user(request, call_next):
        request.scope["user"] = object()
        return await call_next(request)

    http.include_router(workflow_router(boundary))
    body = TenancyDeletionCommand(
        client_request_key=uuid4(), tenancy_id=row["id"], context=s.context, confirm_deletion=True
    ).model_dump(mode="json")
    with TestClient(http) as client:
        assert (
            client.get("/api/tenancies/" + str(row["id"]) + "/deletion-preview").status_code == 200
        )
        assert client.post("/api/tenancy-deletions", json=body).status_code == 202
        for content, headers in [(b"{}", {}), (b"x" * 4097, {"content-type": "application/json"})]:
            assert (
                client.post("/api/tenancy-deletions", content=content, headers=headers).status_code
                == 400
            )
        assert (
            client.post(
                "/api/tenancy-deletions", json={**body, "member_ids": [str(uuid4())]}
            ).status_code
            == 400
        )
        assert boundary.delete_tenancy.call_count == 1
        boundary.delete_tenancy.return_value = ActionReceipt(
            operation_id=uuid4(), state="succeeded", provider_mode="simulated", accepted_at=NOW
        )
        assert client.post("/api/tenancy-deletions", json=body).status_code == 200
