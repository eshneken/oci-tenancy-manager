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
        assert "capture_required_users" in keys
        captured = connection.execute(
            select(operation_step.c.last_outcome).where(
                operation_step.c.operation_id == receipt.operation_id,
                operation_step.c.step_key == "capture_required_users",
            )
        ).scalar_one()
        facts = captured["required_users"]
        assert facts["workspace_id"] == c.policy.workspace_id
        assert facts["tenancy_ocid"] == row["tenancy_ocid"]
        assert facts["automation"]["provider_ocid"] != facts["recovery"]["provider_ocid"]
        event = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.operation_id == receipt.operation_id,
                audit_event.c.kind == "onboarding_outcome",
                audit_event.c.data["step"].astext == "capture_required_users",
            )
        ).scalar_one()
        assert event == captured
    # Redelivery of completed work must not append or replace the captured identity evidence.
    c.worker.run(receipt.operation_id)
    with c.engine.connect() as connection:
        replay = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.operation_id == receipt.operation_id,
                audit_event.c.kind == "onboarding_outcome",
                audit_event.c.data["step"].astext == "capture_required_users",
            )
        ).scalar_one()
        assert replay == captured


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


# Accepted historical graphs still finish without synthesizing permanent-user capture evidence.
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("kind", ["create_tenancy", "import_tenancy"])
def test_legacy_onboarding_completes_without_binding_backfill(workflow_case, version, kind):
    from otm.tenancies.contracts import OrganizationIntent

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")

    # Freeze an old server contract at admission to exercise real replay semantics, not JSON edits.
    def freeze_legacy(**fields):
        return OrganizationIntent(**{**fields, "onboarding_version": version})

    extra = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimlegacycapture"}
        if kind == "import_tenancy"
        else {}
    )
    with patch("otm.tenancies.workflows.OrganizationIntent", side_effect=freeze_legacy):
        _, receipt = action(c, person.id, kind, **extra)
    complete_setup(c, receipt.operation_id)
    with c.engine.connect() as connection:
        keys = set(
            connection.execute(
                select(operation_step.c.step_key).where(
                    operation_step.c.operation_id == receipt.operation_id,
                )
            ).scalars()
        )
    assert "capture_required_users" not in keys
    assert ("configure_baseline" in keys) == (version == 2)


# A failed identity capture persists a repairable stop and never retires temporary access.
def test_capture_failure_retains_temporary_access_and_retry_records_users(workflow_case):
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    with patch.object(c.provider, "capture_onboarding_users", side_effect=ValueError("private")):
        complete_setup(c, receipt.operation_id, expected_phase="blocked")
    with c.engine.connect() as connection:
        steps = {
            row["step_key"]: row
            for row in connection.execute(
                select(operation_step).where(
                    operation_step.c.operation_id == receipt.operation_id,
                )
            ).mappings()
        }
    assert "retire_temporary" not in steps
    failed = steps["capture_required_users"]["last_outcome"]
    assert failed["safe_code"] == "REQUIRED_ACCESS_UNVERIFIED"
    assert "required_users" not in failed and "private" not in str(failed)
    blocked = c.workflow.onboarding(c.principal, receipt.operation_id)
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
    assert c.workflow.onboarding(c.principal, receipt.operation_id).phase == "complete"
    with c.engine.connect() as connection:
        outcomes = (
            connection.execute(
                select(audit_event.c.data)
                .where(
                    audit_event.c.operation_id == receipt.operation_id,
                    audit_event.c.kind == "onboarding_outcome",
                    audit_event.c.data["step"].astext == "capture_required_users",
                )
                .order_by(audit_event.c.at, audit_event.c.id)
            )
            .scalars()
            .all()
        )
    assert {o["outcome"] for o in outcomes} == {"blocked", "verified"}
    assert next(o for o in outcomes if o["outcome"] == "verified")["required_users"]
