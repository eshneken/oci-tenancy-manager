"""Explicit owner retention/removal, immutable legacy intent and exact-account safeguards."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import attach, command, database, intent, person, registry, service

from otm.providers.lifecycle import LifecycleBlocked, LifecycleCompletion
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import AssociationChoice
from otm.tenancies.membership_access import validate_removal_targets, validate_removals
from otm.tenancies.worker import OrganizationLifecycleWorker

__all__ = ["registry"]


# Freeze a shared owner transfer against a distinct eligible employee, never a browser user ID.
def transfer(state, disposition="remove", **changes):
    owner, recipient = person(state), person(state, "delegate@example.test")
    app = service(state)
    row, link = attach(state, owner, kind="shared")
    cmd = command(
        state,
        owner,
        "transfer_owner",
        tenancy_id=row["id"],
        recipient_person_id=recipient.id,
        former_owner_disposition=disposition,
        confirm_shared=True,
        **changes,
    )
    return app, owner, row, link, cmd


# Only new validated choices change behavior; absent legacy fields preserve historical digests.
def test_transfer_optional_fields_and_scope(registry):
    app, owner, row, _, cmd = transfer(registry, None)
    assert "former_owner_disposition" not in cmd.model_dump(mode="json")
    old = AssociationChoice(association_id=uuid4(), action="keep")
    assert "former_owner_disposition" not in old.model_dump(mode="json")
    with pytest.raises(ValueError, match="REQUIRES_TRANSFER"):
        type(cmd)(
            **{**cmd.model_dump(), "action": "remove_member", "former_owner_disposition": "remove"}
        )
    with pytest.raises(ValueError, match="REQUIRES_TRANSFER"):
        AssociationChoice(association_id=uuid4(), action="keep", former_owner_disposition="remove")
    with pytest.raises(OrganizationConflict, match="DISPOSITION_REQUIRED"):
        app._plan(registry, cmd, owner)
    frozen = app._plan(
        registry, cmd.model_copy(update={"former_owner_disposition": "keep_member"}), owner
    )[0]
    assert frozen.former_owner_disposition == "keep_member" and not frozen.removes_identity
    legacy = frozen.model_copy(update={"former_owner_disposition": None})
    assert "former_owner_disposition" not in legacy.model_dump(mode="json")
    assert not legacy.removes_identity
    row["kind"] = "individual"
    with pytest.raises(OrganizationConflict, match="REQUIRES_SHARED"):
        app._plan(
            registry, cmd.model_copy(update={"former_owner_disposition": "keep_member"}), owner
        )


# Shared owner removal cannot guess an absent identity or delete another participant's user.
@pytest.mark.parametrize("damage", ["missing", "reused"])
def test_transfer_rejects_unsafe_old_identity(registry, damage):
    app, owner, row, link, cmd = transfer(registry)
    if damage == "missing":
        link["user_ocid"] = None
    else:
        registry.links = (
            *registry.links,
            {
                **link,
                "id": uuid4(),
                "role": "member",
                "person_id": person(registry, "one@example.test").id,
            },
        )
    with pytest.raises(OrganizationConflict, match="EXACT_PERSONAL_IDENTITY_REQUIRED"):
        app._plan(registry, cmd, owner)


# A keep decision never calls removal capabilities; remove has independent exact-user readback.
@pytest.mark.parametrize("disposition", ["keep_member", "remove", None])
def test_transfer_simulator_and_publication(registry, disposition):
    app, owner, row, link, cmd = transfer(registry, disposition or "remove")
    planned = app._plan(registry, cmd, owner)[0].model_copy(
        update={"former_owner_disposition": disposition}
    )
    frozen = intent(registry, app, owner, action="transfer_owner", associations=(planned,))
    with patch.object(
        app.facade, "remove_member_access", wraps=app.facade.remove_member_access
    ) as remove:
        completion = app.facade.apply(frozen)
        assert remove.call_count == (1 if disposition == "remove" else 0)
    validate_removals(frozen, completion)
    assert len(completion.removals) == (1 if disposition == "remove" else 0)
    worker = OrganizationLifecycleWorker(
        Mock(), registry.workspace, Mock(return_value=NOW), Mock(), app.facade
    )
    connection = database()
    connection.execute.return_value.first.return_value = (uuid4(),)
    worker._publish(connection, registry, frozen, completion, uuid4(), NOW)
    updates = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_update", False)
        and call.args[0].table.name == "otm_tenancy_membership"
    ]
    old = next(values for values in updates if "cleanup_required" in values)
    assert old["status"] == ("active" if disposition == "keep_member" else "removed")
    assert old["role"] == ("member" if disposition == "keep_member" else "owner")
    assert "user_ocid" not in old and "compartment_ocid" not in old
    assert old["cleanup_required"] is (disposition == "remove")
    if disposition == "remove":
        with pytest.raises(LifecycleBlocked):
            validate_removals(frozen, LifecycleCompletion(bindings=completion.bindings))


# Binding snapshots cannot silently rebind an existing recipient to a different OCI identity.
def test_transfer_rejects_rebound_recipient(registry):
    app, owner, _, _, cmd = transfer(registry, "keep_member")
    planned = app._plan(registry, cmd, owner)[0].model_copy(
        update={"recipient_user_ocid": "ocid1.user.oc1..otmsimexpected"}
    )
    frozen = intent(registry, app, owner, action="transfer_owner", associations=(planned,))
    completion = app.facade.apply(frozen)
    bad = completion.model_copy(
        update={
            "bindings": (
                completion.bindings[0].model_copy(
                    update={"user_ocid": "ocid1.user.oc1..otmsimforeign"}
                ),
            )
        }
    )
    worker = OrganizationLifecycleWorker(Mock(), registry.workspace, Mock(), Mock(), app.facade)
    with pytest.raises(LifecycleBlocked):
        worker._publish(database(), registry, frozen, bad, uuid4(), NOW)


# Canonical automation/recovery bindings are protected before any provider removal can occur.
@pytest.mark.parametrize("protected", [False, True])
def test_transfer_protected_identity_guard(registry, protected):
    app, owner, _, link, cmd = transfer(registry)
    frozen = intent(
        registry, app, owner, action="transfer_owner", associations=app._plan(registry, cmd, owner)
    )
    connection = database()
    connection.execute.return_value.scalars.return_value = [link["user_ocid"]] if protected else []
    if protected:
        with pytest.raises(LifecycleBlocked):
            validate_removal_targets(connection, registry.workspace, frozen)
    else:
        validate_removal_targets(connection, registry.workspace, frozen)
    kept = frozen.model_copy(
        update={
            "associations": (
                frozen.associations[0].model_copy(
                    update={"former_owner_disposition": "keep_member"}
                ),
            )
        }
    )
    connection.reset_mock()
    validate_removal_targets(connection, registry.workspace, kept)
    connection.execute.assert_not_called()


# A replacement that aliases the outgoing account must fail before deleting that account.
def test_transfer_replacement_verified_before_removal(registry):
    app, owner, _, _, cmd = transfer(registry)
    planned = app._plan(registry, cmd, owner)[0]
    planned = planned.model_copy(update={"recipient_user_ocid": planned.user_ocid})
    frozen = intent(registry, app, owner, action="transfer_owner", associations=(planned,))
    with patch.object(app.facade, "remove_member_access") as remove:
        with pytest.raises(LifecycleBlocked):
            app.facade.apply(frozen)
        remove.assert_not_called()


# A recipient's identity or compartment rebinding after admission cannot redirect the worker.
@pytest.mark.parametrize("field", ["user_ocid", "compartment_ocid", "parent_compartment_ocid"])
def test_transfer_dispatch_rejects_changed_recipient_binding(registry, field):
    app, owner, row, link, cmd = transfer(registry, "keep_member")
    recipient = person(registry, "delegate@example.test")
    member = {
        **link,
        "id": uuid4(),
        "person_id": recipient.id,
        "role": "member",
        "user_ocid": "ocid1.user.oc1..otmsimrecipient",
    }
    registry.links = (*registry.links, member)
    planned = app._plan(registry, cmd, owner)
    frozen = intent(registry, app, owner, action="transfer_owner", associations=planned)
    operation_id = uuid4()
    row["operation_id"] = operation_id
    registry.controls[owner.id]["pending_operation_id"] = operation_id
    registry.controls[recipient.id]["pending_operation_id"] = operation_id
    member[field] = "changed-recorded-binding"
    worker = OrganizationLifecycleWorker(Mock(), registry.workspace, Mock(), Mock(), app.facade)
    with pytest.raises(LifecycleBlocked, match="TARGET_CHANGED"):
        worker._validate(registry, frozen, operation_id)
