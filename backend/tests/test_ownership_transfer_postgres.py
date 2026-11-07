"""Real queued transfers preserve identities or verify removal before publishing ownership."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_organization_fixtures import example_records
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, feed, workflow_case

from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import managed_object_binding, operation, operation_step, tenancy_membership
from otm.tenancies.contracts import AssociationChoice
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Build a shared child with two independently bound people through the real application services.
def shared_pair(c):
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    old, new = people["engineer@example.test"], people["delegate@example.test"]
    _, created = action(c, old, "create_tenancy", name="transfercase", tenancy_kind="shared")
    complete_setup(c, created.operation_id)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, joined = action(
        c,
        new,
        "join_shared",
        tenancy_id=child.id,
        parent_compartment_ocid=child.tenancy_ocid,
        compartment_name="replacement",
    )
    c.worker.run(joined.operation_id)
    return old, new, child


# Keep preserves both users' OCI IDs and former association; remove verifies exact retirement steps.
@pytest.mark.parametrize("disposition", ["keep_member", "remove"])
def test_ownership_transfer_choice_preserves_or_removes(workflow_case, disposition):
    c = workflow_case
    old, new, child = shared_pair(c)
    before = c.workflow.tenancy_detail(c.principal, child.id)
    previous = next(a for a in before.memberships if a.person_id == old and a.status == "active")
    replacement = next(a for a in before.memberships if a.person_id == new and a.status == "active")
    command, accepted = action(
        c,
        old,
        "transfer_owner",
        tenancy_id=child.id,
        recipient_person_id=new,
        former_owner_disposition=disposition,
        confirm_shared=True,
        confirm_destructive=disposition == "remove",
    )
    assert c.workflow.act(c.principal, command) == accepted
    with patch.object(
        c.provider, "remove_member_access", wraps=c.provider.remove_member_access
    ) as remove:
        c.worker.run(accepted.operation_id)
        c.worker.run(accepted.operation_id)
        assert remove.call_count == (1 if disposition == "remove" else 0)
    after = c.workflow.tenancy_detail(c.principal, child.id)
    assert after.tenancy.owner_person_id == new
    assert after.tenancy.member_count == (2 if disposition == "keep_member" else 1)
    current = [a for a in after.memberships if a.status == "active"]
    assert sum(a.role == "owner" for a in current) == 1
    next_owner = next(a for a in current if a.person_id == new)
    assert next_owner.user_ocid == replacement.user_ocid
    assert next_owner.compartment_ocid == replacement.compartment_ocid
    former = next(a for a in after.memberships if a.id == previous.id)
    assert (
        former.user_ocid == previous.user_ocid
        and former.compartment_ocid == previous.compartment_ocid
    )
    assert former.status == ("active" if disposition == "keep_member" else "removed")
    assert former.role == ("member" if disposition == "keep_member" else "owner")
    assert former.cleanup_required is (disposition == "remove")
    assert c.workflow.preview(c.principal, old).directory_status == "included"
    with c.engine.connect() as connection:
        steps = (
            connection.execute(
                select(operation_step.c.step_key).where(
                    operation_step.c.operation_id == accepted.operation_id
                )
            )
            .scalars()
            .all()
        )
        result = (
            connection.execute(select(operation).where(operation.c.id == accepted.operation_id))
            .mappings()
            .one()
        )
    assert result["state"] == "succeeded"
    with pytest.raises(RequestConflict):
        c.workflow.act(
            c.principal,
            command.model_copy(
                update={
                    "former_owner_disposition": "remove"
                    if disposition == "keep_member"
                    else "keep_member"
                }
            ),
        )
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        c.workflow.act(c.principal, command.model_copy(update={"client_request_key": uuid4()}))
    for prefix in ("remove_member_groups:", "delete_member_user:"):
        assert any(key.startswith(prefix) for key in steps) is (disposition == "remove")


# Direct API/service callers cannot omit disposition or bypass removal consent; no work is admitted.
def test_ownership_transfer_new_admission_guards(workflow_case):
    c = workflow_case
    old, new, child = shared_pair(c)
    with pytest.raises(OrganizationConflict, match="DISPOSITION_REQUIRED"):
        action(
            c,
            old,
            "transfer_owner",
            tenancy_id=child.id,
            recipient_person_id=new,
            former_owner_disposition=None,
            confirm_shared=True,
        )
    with pytest.raises(OrganizationConflict, match="DESTRUCTIVE_CONFIRMATION_REQUIRED"):
        action(
            c,
            old,
            "transfer_owner",
            tenancy_id=child.id,
            recipient_person_id=new,
            former_owner_disposition="remove",
            confirm_destructive=False,
            confirm_shared=True,
        )
    assert c.workflow.tenancy_detail(c.principal, child.id).tenancy.owner_person_id == old


# A failed provider write retains the ownership/identity obligations and reports uncertain effects.
def test_ownership_transfer_partial_removal_retains_obligations(workflow_case):
    c = workflow_case
    old, new, child = shared_pair(c)
    previous = next(
        a
        for a in c.workflow.tenancy_detail(c.principal, child.id).memberships
        if a.person_id == old and a.status == "active"
    )
    _, accepted = action(
        c,
        old,
        "transfer_owner",
        tenancy_id=child.id,
        recipient_person_id=new,
        former_owner_disposition="remove",
        confirm_shared=True,
    )
    with patch.object(c.provider, "delete_member_user", side_effect=RuntimeError("private")):
        c.worker.run(accepted.operation_id)
    after = c.workflow.tenancy_detail(c.principal, child.id)
    assert after.tenancy.owner_person_id == old
    assert next(a for a in after.memberships if a.id == previous.id).status == "active"
    with c.engine.connect() as connection:
        result = (
            connection.execute(select(operation).where(operation.c.id == accepted.operation_id))
            .mappings()
            .one()
        )
    assert result["state"] == "needs_attention" and result["effect_knowledge"] == "unknown"
    assert c.workflow.preview(c.principal, old).pending_operation_id == accepted.operation_id
    assert c.provider._member_access[(child.tenancy_ocid, previous.user_ocid)] == {
        "groups": False,
        "user": True,
    }


# Corrupted personal-user mappings cannot delete the canonical automation or recovery identity.
def test_ownership_transfer_protected_identity_stops_before_provider(workflow_case):
    c = workflow_case
    old, new, child = shared_pair(c)
    with c.engine.begin() as connection:
        protected = connection.execute(
            select(managed_object_binding.c.provider_ocid).where(
                managed_object_binding.c.tenancy_id == child.id,
                managed_object_binding.c.logical_key == "identity/user/automation",
            )
        ).scalar_one()
        connection.execute(
            update(tenancy_membership)
            .where(
                tenancy_membership.c.tenancy_id == child.id,
                tenancy_membership.c.person_id == old,
                tenancy_membership.c.status == "active",
            )
            .values(user_ocid=protected)
        )
    _, accepted = action(
        c,
        old,
        "transfer_owner",
        tenancy_id=child.id,
        recipient_person_id=new,
        former_owner_disposition="remove",
        confirm_shared=True,
    )
    with patch.object(c.provider, "apply", wraps=c.provider.apply) as apply:
        c.worker.run(accepted.operation_id)
        apply.assert_not_called()
    assert c.workflow.tenancy_detail(c.principal, child.id).tenancy.owner_person_id == old
    with c.engine.connect() as connection:
        assert (
            connection.execute(
                select(operation.c.state).where(operation.c.id == accepted.operation_id)
            ).scalar_one()
            == "needs_attention"
        )


# Explicit offboarding retains an obligation for keep; its omitted transfer choice freezes remove.
@pytest.mark.parametrize("keep", [False, True])
def test_ownership_transfer_offboard_disposition(workflow_case, keep):
    c = workflow_case
    old, new, child = shared_pair(c)
    feed(c, tuple(row for row in example_records() if row.email != "engineer@example.test"))
    before = c.workflow.preview(c.principal, old)
    association = next(a for a in before.associations if a.tenancy_id == child.id)
    plan = AssociationChoice(
        association_id=association.id,
        action="transfer",
        recipient_person_id=new,
        former_owner_disposition="keep_member" if keep else None,
    )
    _, accepted = action(c, old, "offboard_person", plan=(plan,), confirm_shared=True)
    c.worker.run(accepted.operation_id)
    after = c.workflow.preview(c.principal, old)
    assert after.directory_status == ("outside" if keep else "offboarded")
    assert len(after.associations) == (1 if keep else 0)
    assert c.workflow.tenancy_detail(c.principal, child.id).tenancy.owner_person_id == new
