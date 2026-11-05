"""Real PostgreSQL default selection and immutable onboarding pins across publication changes."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection
from test_baseline_authoring import content
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.providers.baseline import SimulatedBaselineQualifier
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import operation, org_workspace, tenancy

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Publish a reviewed synthetic recipe through the same service used by the actual local API.
def publish(c, amount="500"):
    recipes = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    current = recipes.read(c.principal)
    draft = recipes.save(
        c.principal,
        SaveBaselineDraft(
            content=content(monthly_budget_amount=amount),
            based_on_id=current.latest.id if current.latest else None,
        ),
    )
    return recipes, recipes.publish(
        c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=draft.edit_revision)
    )


# Publishing during activation does not retarget original work or its idempotent acceptance replay.
@pytest.mark.parametrize("first_action", ["create_tenancy", "import_tenancy"])
def test_pin_survives_wait_and_new_admission_uses_new_default(workflow_case, first_action):
    c = workflow_case
    people = {p.email: p for p in c.store.head(c.principal).people}
    employee = people["engineer@example.test"]
    fields = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimfirst"}
        if first_action == "import_tenancy"
        else {}
    )
    original, receipt = action(c, employee.id, first_action, **fields)
    c.worker.run(receipt.operation_id)
    waiting = c.workflow.onboarding(c.principal, receipt.operation_id)
    first = waiting.baseline
    assert first is not None and first.version_number == 1
    recipes, second = publish(c)
    assert second.id != first.id and recipes.read(c.principal).latest.id == second.id
    assert c.workflow.act(c.principal, original).operation_id == receipt.operation_id
    assert c.workflow.onboarding(c.principal, receipt.operation_id).baseline == first
    complete_setup(c, receipt.operation_id)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(tenancy.c.baseline_version_id).where(tenancy.c.id == waiting.tenancy_id)
            )
            == first.id
        )
    other_action = "import_tenancy" if first_action == "create_tenancy" else "create_tenancy"
    fields = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimsecond"}
        if other_action == "import_tenancy"
        else {}
    )
    _, next_receipt = action(c, people["one@example.test"].id, other_action, **fields)
    assert c.workflow.onboarding(c.principal, next_receipt.operation_id).baseline == second
    complete_setup(c, next_receipt.operation_id)
    # An old publication retry is receipt recovery, never a command to roll the default backward.
    recipes.publish(
        c.principal,
        PublishBaseline(baseline_id=first.id, expected_revision=first.edit_revision - 1),
    )
    assert recipes.read(c.principal).latest.id == second.id


# Stale previews require reload; missing defaults cause no operation or registry effects.
def test_stale_preview_and_missing_default_do_not_admit(workflow_case):
    c = workflow_case
    employee = next(
        p for p in c.store.head(c.principal).people if p.email == "engineer@example.test"
    )
    preview = c.workflow.preview(c.principal, employee.id)
    from otm.tenancies.contracts import OrganizationAction

    request = OrganizationAction(
        client_request_key=uuid4(),
        context=preview.context,
        action="create_tenancy",
        person_id=employee.id,
        name="stalechild",
        home_region="us-ashburn-1",
    )
    publish(c)
    with pytest.raises(OrganizationConflict, match="ORGANIZATION_PREVIEW_CHANGED"):
        c.workflow.act(c.principal, request)
    with c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(current_baseline_id=None)
        )
        before = connection.scalar(
            select(func.count())
            .select_from(operation)
            .where(operation.c.workspace_id == c.policy.workspace_id)
        )
    with patch("otm.tenancies.workflows.current_baseline", return_value=None):
        with pytest.raises(OrganizationConflict, match="PUBLISHED_BASELINE_REQUIRED"):
            action(c, employee.id, "create_tenancy")
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(operation)
                .where(operation.c.workspace_id == c.policy.workspace_id)
            )
            == before
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(tenancy)
                .where(tenancy.c.workspace_id == c.policy.workspace_id)
            )
            == 0
        )
    # Declining a tenancy remains an independent application decision.
    _, receipt = action(c, employee.id, "no_tenancy_required")
    assert receipt.provider_mode == "application"


# Publication and preview revision roll back together when durable evidence cannot be inserted.
def test_publication_rollback_preserves_latest(workflow_case):
    c = workflow_case
    app = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    original = app.read(c.principal).latest
    draft = app.save(
        c.principal,
        SaveBaselineDraft(content=content(monthly_budget_amount="700"), based_on_id=original.id),
    )
    execute = Connection.execute

    # Fail only the final evidence insert after both baseline and workspace rows have changed.
    def fail_audit(connection, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and statement.table.name == "audit_event":
            raise RuntimeError("SYNTHETIC_AUDIT_FAILURE")
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", new=fail_audit):
        with pytest.raises(RuntimeError, match="SYNTHETIC_AUDIT_FAILURE"):
            app.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    state = app.read(c.principal)
    assert state.latest == original and state.draft.id == draft.id
    app.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))


# Historical selection metadata cannot make new admissions use anything except latest publication.
def test_latest_is_automatic_despite_old_metadata(organization_case):
    c = organization_case
    app = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = app.save(c.principal, SaveBaselineDraft(content=content()))
    assert app.read(c.principal).latest is None
    first = app.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    _, second = publish(c)
    from otm.configuration.service import current_baseline

    with c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(current_baseline_id=first.id)
        )
        assert current_baseline(connection, c.policy.workspace_id) == second
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(current_baseline_id=None)
        )
        assert current_baseline(connection, c.policy.workspace_id) == second
    app.publish(c.principal, PublishBaseline(baseline_id=first.id, expected_revision=1))
    assert app.read(c.principal).latest == second


# The registry cannot report one selected recipe while its worker executes a different frozen pin.
def test_registry_pin_mismatch_stops_before_provider(workflow_case):
    c = workflow_case
    employee = next(
        p for p in c.store.head(c.principal).people if p.email == "engineer@example.test"
    )
    _, receipt = action(c, employee.id, "create_tenancy")
    waiting = c.workflow.onboarding(c.principal, receipt.operation_id)
    _, second = publish(c)
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == waiting.tenancy_id)
            .values(baseline_version_id=second.id)
        )
    with (
        patch.object(c.provider, "inspect_onboarding") as inspect,
        patch.object(c.provider, "apply") as apply,
    ):
        c.worker.run(receipt.operation_id)
        inspect.assert_not_called()
        apply.assert_not_called()
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == receipt.operation_id)
            )
            == "needs_attention"
        )


# Seed an old accepted payload at insertion, without rewriting or bypassing immutable audit guards.
def test_legacy_accepted_operation_stays_unpinned_after_publication(workflow_case):
    from otm.operations.contracts import canonical_hash

    c = workflow_case
    employee = next(
        p for p in c.store.head(c.principal).people if p.email == "engineer@example.test"
    )
    execute = Connection.execute

    # Represent the exact old format only in this fixture's initial audit/registry INSERTs.
    def insert_legacy(connection, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False):
            if statement.table.name == "audit_event":
                values = statement.compile().params
                if values["kind"] == "operation_intent":
                    data = dict(values["data"])
                    data["intent"] = {
                        key: value for key, value in data["intent"].items() if key != "baseline"
                    }
                    data["intent"]["onboarding_version"] = 1
                    statement = statement.values(data=data, data_hash=canonical_hash(data))
            elif statement.table.name == "otm_tenancy":
                statement = statement.values(baseline_version_id=None)
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", new=insert_legacy):
        request, receipt = action(c, employee.id, "create_tenancy")
    publish(c)
    assert c.workflow.act(c.principal, request).operation_id == receipt.operation_id
    assert c.workflow.onboarding(c.principal, receipt.operation_id).baseline is None
    complete_setup(c, receipt.operation_id)
    with c.engine.connect() as connection:
        row = (
            connection.execute(
                select(tenancy).where(
                    tenancy.c.operation_id.is_(None),
                    tenancy.c.workspace_id == c.policy.workspace_id,
                )
            )
            .mappings()
            .one()
        )
        assert row["status"] == "active" and row["baseline_version_id"] is None
