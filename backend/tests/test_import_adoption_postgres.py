"""Persist existing shared identities, ordinary lifecycle cleanup and independent access checks."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, workflow_case

from otm.providers.presence_simulator import simulated_presence_inspection
from otm.storage.enqueue import PRESENCE_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import operation_step, org_person, tenancy_membership
from otm.tenancies.import_contracts import ImportAdoption
from otm.tenancies.onboarding_contracts import OnboardingCommand
from otm.tenancies.presence import PresenceChecks
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.presence_worker import UserPresenceWorker
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Reach the actual provider-discovered review through persisted handoff and native queue admissions.
def reviewed(c):
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    _, receipt = action(
        c,
        people["one@example.test"],
        "import_tenancy",
        tenancy_kind="shared",
        import_ocid="ocid1.tenancy.oc1..otmsimadoption",
    )
    identifier = receipt.operation_id
    c.worker.run(identifier)
    handoff = c.workflow.onboarding(c.principal, identifier)
    c.workflow.onboarding_action(
        c.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=handoff.revision,
            action="verify_handoff",
            handoff=handoff.suggested_handoff,
        ),
    )
    c.worker.run(identifier)
    view = c.workflow.onboarding(c.principal, identifier)
    assert view.phase == "review" and view.import_review is not None
    return people, identifier, view


# Explicitly adopt an existing root administrator and one multi-compartment analyst.
def accept(c, people, identifier, view):
    review = view.import_review
    command = OnboardingCommand(
        client_request_key=uuid4(),
        revision=view.revision,
        action="start_setup",
        confirm_cleanup=True,
        import_adoption=ImportAdoption(
            inventory_hash=review.inventory_hash,
            lifecycle_confirmed=True,
            members=(
                {
                    "user_ocid": review.inventory.users[0].user_ocid,
                    "person_id": people["one@example.test"],
                },
                {
                    "user_ocid": review.inventory.users[2].user_ocid,
                    "person_id": people["engineer@example.test"],
                },
            ),
        ),
    )
    c.workflow.onboarding_action(c.principal, identifier, command)
    assert c.workflow.onboarding_action(c.principal, identifier, command).operation_id == identifier
    return command


# Adopted identities bypass provisioning, retain exact grants, and use ordinary explicit removal.
def test_import_adoption_lifecycle_and_drift(workflow_case):
    c = workflow_case
    people, identifier, view = reviewed(c)
    with pytest.raises(OrganizationConflict):
        c.workflow.onboarding_action(
            c.principal,
            identifier,
            OnboardingCommand(
                client_request_key=uuid4(),
                revision=view.revision,
                action="start_setup",
                confirm_cleanup=True,
            ),
        )
    accept(c, people, identifier, view)
    with patch.object(
        c.provider, "apply", side_effect=AssertionError("human provisioning forbidden")
    ):
        c.worker.run(identifier)
    assert c.workflow.onboarding(c.principal, identifier).phase == "complete"
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    details = c.workflow.tenancy_detail(c.principal, child.id)
    assert child.member_count == 2
    member = next(m for m in details.memberships if m.person_id == people["engineer@example.test"])
    assert len(member.imported_access.identity.scopes) == 2
    owner = next(m for m in details.memberships if m.role == "owner")
    assert owner.imported_access.identity.scopes[0].kind == "root"
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy_membership)
            .where(tenancy_membership.c.id == member.id)
            .values(imported_access=member.imported_access.model_dump(mode="json"))
        )
    with pytest.raises(DBAPIError), c.engine.begin() as connection:
        connection.execute(
            update(tenancy_membership)
            .where(tenancy_membership.c.id == member.id)
            .values(imported_access=None)
        )
    checks = PresenceChecks(
        c.store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=PRESENCE_TASK),
    )
    c.workflow.presence_checks = checks
    reader = UserPresenceWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.workflow.policy,
        simulated_presence_inspection,
        import_inspector=c.provider.inspect_existing_access,
    )
    check = checks.start(c.principal, child.id, PresenceCheckRequest(client_request_key=uuid4()))
    reader.run(check.operation_id)
    assert c.workflow.required_users(c.principal, child.id).import_access.state == "matching"
    reader.import_inspector = Mock(side_effect=ValueError("unavailable"))
    check = checks.start(c.principal, child.id, PresenceCheckRequest(client_request_key=uuid4()))
    reader.run(check.operation_id)
    assert c.workflow.required_users(c.principal, child.id).import_access.state == "unavailable"
    _, removed = action(
        c, member.person_id, "remove_member", tenancy_id=child.id, confirm_shared=True
    )
    c.worker.run(removed.operation_id)
    assert c.workflow.tenancy_detail(c.principal, child.id).tenancy.member_count == 1
    inventory = c.provider.inspect_existing_access(
        child.tenancy_ocid, member.imported_access.domain_ocid
    )
    assert member.imported_access.identity.user_ocid not in {u.user_ocid for u in inventory.users}
    assert len(c.provider.compartments(child.tenancy_ocid)) == 3
    with c.engine.connect() as connection:
        keys = set(
            connection.execute(
                select(operation_step.c.step_key).where(
                    operation_step.c.operation_id == removed.operation_id
                )
            ).scalars()
        )
        assert "delete_member_user:" + str(member.id) in keys
    _, joined = action(
        c,
        people["two@example.test"],
        "join_shared",
        tenancy_id=child.id,
        existing_compartment_ocid=c.provider.compartments(child.tenancy_ocid)[1].ocid,
    )
    c.worker.run(joined.operation_id)
    current = c.workflow.tenancy_detail(c.principal, child.id)
    assert current.tenancy.member_count == 2
    newcomer = next(m for m in current.memberships if m.person_id == people["two@example.test"])
    assert newcomer.imported_access is None and newcomer.status == "active"
    retained = next(m for m in current.memberships if m.role == "owner")
    assert retained.imported_access == owner.imported_access


# Explicit cancellation releases every adopted participant reservation and pending row.
def test_cancel_import_releases_all_participants(workflow_case):
    c = workflow_case
    people, identifier, view = reviewed(c)
    accept(c, people, identifier, view)
    action(c, people["one@example.test"], "cancel_simulation", operation_id=identifier)
    with c.engine.connect() as connection:
        controls = (
            connection.execute(
                select(org_person.c.pending_operation_id).where(
                    org_person.c.workspace_id == c.policy.workspace_id
                )
            )
            .scalars()
            .all()
        )
        assert all(value is None for value in controls)
        rows = (
            connection.execute(
                select(tenancy_membership).where(
                    tenancy_membership.c.workspace_id == c.policy.workspace_id
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == 2 and all(row["status"] == "removed" for row in rows)


# Promotion retains adopted identity/scopes and the former owner account when explicitly chosen.
def test_transfer_adopted_member_preserves_provenance(workflow_case):
    c = workflow_case
    people, identifier, view = reviewed(c)
    accept(c, people, identifier, view)
    c.worker.run(identifier)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    before = c.workflow.tenancy_detail(c.principal, child.id)
    recipient = next(
        m for m in before.memberships if m.person_id == people["engineer@example.test"]
    )
    _, transfer = action(
        c,
        people["one@example.test"],
        "transfer_owner",
        tenancy_id=child.id,
        recipient_person_id=recipient.person_id,
        former_owner_disposition="keep_member",
        confirm_shared=True,
    )
    c.worker.run(transfer.operation_id)
    after = c.workflow.tenancy_detail(c.principal, child.id)
    assert after.tenancy.owner_person_id == recipient.person_id
    owner = next(m for m in after.memberships if m.role == "owner")
    assert owner.imported_access.identity == recipient.imported_access.identity
    assert owner.imported_access.expected_owner.operation_id == transfer.operation_id
    assert owner.compartment_ocid == child.tenancy_ocid
    assert len(owner.imported_access.expected_owner.identity.scopes) == 3
    from otm.providers.presence_simulator import simulated_presence_inspection
    from otm.tenancies.presence import PresenceChecks
    from otm.tenancies.presence_contracts import PresenceCheckRequest
    from otm.tenancies.presence_worker import UserPresenceWorker

    service = PresenceChecks(
        c.store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=PRESENCE_TASK),
    )
    c.workflow.presence_checks = service
    reader = UserPresenceWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.workflow.policy,
        simulated_presence_inspection,
        import_inspector=c.provider.inspect_existing_access,
    )
    checked = service.start(c.principal, child.id, PresenceCheckRequest(client_request_key=uuid4()))
    reader.run(checked.operation_id)
    assert c.workflow.required_users(c.principal, child.id).import_access.state == "matching"
    assert after.tenancy.member_count == 2
    former = next(m for m in after.memberships if m.person_id == people["one@example.test"])
    assert former.imported_access.identity.scopes[0].kind == "root"


# Inventory changes invalidate the consent fingerprint; explicit reinspection offers a new review.
def test_inventory_refresh_and_pre_effect_reverification(workflow_case):
    c = workflow_case
    people, identifier, view = reviewed(c)
    captured = view.import_review.inventory
    changed = captured.model_copy(update={"users": captured.users[:2]})
    with patch.object(c.provider, "inspect_existing_access", return_value=changed):
        with pytest.raises(OrganizationConflict, match="INVENTORY_CHANGED"):
            accept(c, people, identifier, view)
    c.workflow.onboarding_action(
        c.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(), revision=view.revision, action="refresh_import_inventory"
        ),
    )
    refreshing = c.workflow.onboarding(c.principal, identifier)
    assert refreshing.phase == "configuring"
    assert refreshing.import_review is None
    assert refreshing.checks[0].state == "pending"
    c.worker.run(identifier)
    refreshed = c.workflow.onboarding(c.principal, identifier)
    assert refreshed.revision > view.revision and refreshed.import_review is not None
    accept(c, people, identifier, refreshed)
    with (
        patch.object(c.provider, "inspect_existing_access", return_value=changed),
        patch.object(
            c.provider,
            "configure_import_access",
            side_effect=AssertionError("no setup after changed inventory"),
        ) as configure,
    ):
        c.worker.run(identifier)
        configure.assert_not_called()
    assert c.workflow.onboarding(c.principal, identifier).phase == "blocked"
    with c.engine.connect() as connection:
        reserved = (
            connection.execute(
                select(tenancy_membership).where(tenancy_membership.c.operation_id == identifier)
            )
            .mappings()
            .all()
        )
        assert len(reserved) == 2 and all(link["status"] == "pending" for link in reserved)
