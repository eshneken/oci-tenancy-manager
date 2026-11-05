"""Real PostgreSQL onboarding application and exact shared-user retirement evidence."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_baseline_pinning_postgres import publish
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.storage.tables import audit_event, operation_step, tenancy, tenancy_membership
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Activation pauses do not retarget the accepted latest baseline; setup writes/readbacks all four.
@pytest.mark.parametrize("kind", ["create_tenancy", "import_tenancy"])
def test_onboarding_applies_frozen_baseline_without_second_operation(workflow_case, kind):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    extra = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimimportbaseline"}
        if kind == "import_tenancy"
        else {}
    )
    _, receipt = action(c, person.id, kind, **extra)
    original = c.workflow.tenancies(c.principal, TenancyQuery()).items[0].baseline_version_id
    publish(c, "999")
    complete_setup(c, receipt.operation_id)
    with c.engine.connect() as connection:
        row = (
            connection.execute(
                select(tenancy).where(tenancy.c.workspace_id == c.policy.workspace_id)
            )
            .mappings()
            .one()
        )
        assert row["status"] == "active"
        assert row["baseline_version_id"] == row["verified_baseline_version_id"] == original
        assert set(row["configuration_observation"]) == {"policy", "quota", "budget", "tags"}
        assert row["configuration_verified_at"] is not None
        keys = set(
            connection.execute(
                select(operation_step.c.step_key).where(
                    operation_step.c.operation_id == receipt.operation_id
                )
            ).scalars()
        )
        assert {"configure_baseline", "verify_configured_access", "retire_temporary"} <= keys


# Two people may use one existing compartment; removing one deletes only their identity binding.
def test_existing_compartment_shared_members_and_explicit_user_cleanup(workflow_case):
    c = workflow_case
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    _, created = action(c, people["one@example.test"], "create_tenancy", tenancy_kind="shared")
    complete_setup(c, created.operation_id)
    row = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    selected = c.workflow.facade.compartments(row.tenancy_ocid)[1].ocid
    for email in ["engineer@example.test", "two@example.test"]:
        _, joined = action(
            c, people[email], "join_shared", tenancy_id=row.id, existing_compartment_ocid=selected
        )
        c.worker.run(joined.operation_id)
    before = c.workflow.tenancy_detail(c.principal, row.id)
    assert before.tenancy.member_count == 3
    retiring = next(m for m in before.memberships if m.person_id == people["engineer@example.test"])
    _, removed = action(
        c, retiring.person_id, "remove_member", tenancy_id=row.id, confirm_shared=True
    )
    c.worker.run(removed.operation_id)
    after = c.workflow.tenancy_detail(c.principal, row.id)
    assert after.tenancy.member_count == 2
    with c.engine.connect() as connection:
        old = (
            connection.execute(
                select(tenancy_membership).where(tenancy_membership.c.id == retiring.id)
            )
            .mappings()
            .one()
        )
        assert old["status"] == "removed" and old["cleanup_required"]
        assert old["compartment_ocid"] == selected
        keys = set(
            connection.execute(
                select(operation_step.c.step_key).where(
                    operation_step.c.operation_id == removed.operation_id
                )
            ).scalars()
        )
        assert {
            "remove_member_groups:" + str(retiring.id),
            "delete_member_user:" + str(retiring.id),
        } <= keys
        evidence = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.operation_id == removed.operation_id,
                audit_event.c.kind == "organization_action_outcome",
            )
        ).scalar_one()
        assert evidence["removals"][0]["user_ocid"] == old["user_ocid"]
        assert evidence["removals"][0]["user_deleted"] is True
    assert selected in {p.ocid for p in c.workflow.facade.compartments(row.tenancy_ocid)}
    c.worker.run(removed.operation_id)
    assert c.workflow.tenancy_detail(c.principal, row.id).tenancy.member_count == 2


# Incomplete provider proof keeps the association visible rather than claiming the user was deleted.
@pytest.mark.parametrize("damage", ["unverified", "missing_user_deleted", "missing_groups"])
def test_unverified_user_delete_keeps_shared_association(workflow_case, damage):
    c = workflow_case
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    _, created = action(c, people["one@example.test"], "create_tenancy", tenancy_kind="shared")
    complete_setup(c, created.operation_id)
    row = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, joined = action(
        c,
        people["engineer@example.test"],
        "join_shared",
        tenancy_id=row.id,
        parent_compartment_ocid=row.tenancy_ocid,
        compartment_name="engineer",
    )
    c.worker.run(joined.operation_id)
    _, removed = action(
        c, people["engineer@example.test"], "remove_member", tenancy_id=row.id, confirm_shared=True
    )

    # A malformed provider receipt must fail validation before any local association retirement.
    def missing_proof(association):
        values = dict(
            association_id=association.id,
            tenancy_ocid=association.tenancy_ocid,
            user_ocid=association.user_ocid,
            group_memberships_removed=True,
            user_deleted=True,
        )
        values.pop(
            "user_deleted" if damage == "missing_user_deleted" else "group_memberships_removed"
        )
        return values

    method = "delete_member_user" if damage == "unverified" else "read_member_access"
    with patch.object(
        c.worker.facade, method, side_effect=None if damage == "unverified" else missing_proof
    ):
        c.worker.run(removed.operation_id)
    with c.engine.connect() as connection:
        state = connection.scalar(
            select(tenancy_membership.c.status).where(
                tenancy_membership.c.person_id == people["engineer@example.test"]
            )
        )
        assert state != "removed"
        assert (
            connection.execute(
                select(operation_step).where(
                    operation_step.c.operation_id == removed.operation_id,
                    operation_step.c.step_key.like("delete_member_user:%"),
                )
            ).first()
            is None
        )


# Partial baseline writes or post-policy access loss retain temporary access and support safe retry.
@pytest.mark.parametrize("failure", ["baseline", "access"])
def test_onboarding_failure_preserves_bootstrap_and_retries_exact_pin(workflow_case, failure):
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c = workflow_case
    engineer = next(
        p for p in c.store.head(c.principal).people if p.email == "engineer@example.test"
    )
    _, receipt = action(c, engineer.id, "create_tenancy")
    c.worker.run(receipt.operation_id)
    handoff = c.workflow.onboarding(c.principal, receipt.operation_id)
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=handoff.revision,
            action="verify_handoff",
            handoff=handoff.suggested_handoff,
        ),
    )
    c.worker.run(receipt.operation_id)
    review = c.workflow.onboarding(c.principal, receipt.operation_id)
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=review.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    calls = []
    setup = c.worker.facade.onboarding_step
    apply = c.worker.facade.configuration_facade.apply

    # The second required-access probe is after baseline writes, not the earlier setup verification.
    def probe(intent, key, discovery):
        calls.append(key)
        if failure == "access" and key == "verify_required" and calls.count(key) == 2:
            raise ValueError("synthetic post-policy access loss")
        return setup(intent, key, discovery)

    # Fail the third category; committed policy/quota observations remain retry evidence.
    def write(target, desired, previous):
        if failure == "baseline" and desired.category == "budget":
            raise ValueError("synthetic budget failure")
        return apply(target, desired, previous)

    with (
        patch.object(c.worker.facade, "onboarding_step", side_effect=probe),
        patch.object(c.worker.facade.configuration_facade, "apply", side_effect=write),
    ):
        c.worker.run(receipt.operation_id)
    blocked = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert blocked.phase == "blocked"
    assert "retire_temporary" not in calls
    with c.engine.connect() as connection:
        row = (
            connection.execute(
                select(tenancy).where(tenancy.c.workspace_id == c.policy.workspace_id)
            )
            .mappings()
            .one()
        )
        assert row["status"] == "pending"
        assert {"policy", "quota"} <= set(row["configuration_observation"])
        assert (row["verified_baseline_version_id"] is None) == (failure == "baseline")
    publish(c, "800")
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=blocked.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    c.worker.run(receipt.operation_id)
    final = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert final.phase == "complete" and final.baseline.id == review.baseline.id
    assert all(step.state == "verified" for step in final.checks)
