"""Real immutable override revisions, staged all-target reviews."""

import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from test_baseline_pinning_postgres import publish
from test_configuration_updates_postgres import children, updates
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
from otm.configuration.override_contracts import (
    CreateConfigurationPlan,
    OverrideContext,
    OverridePreviewRequest,
    OverrideValues,
    SaveConfigurationReview,
)
from otm.configuration.plans import ConfigurationPlans
from otm.configuration.rollout_contracts import ConfigurationUpdate
from otm.configuration.service import BaselineAuthoring
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import (
    audit_event,
    configuration_plan,
    tenancy,
    tenancy_configuration,
)

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Build exact editor context and preview without guessing current baseline or configuration
# pointers.
def override_command(c, service, identifier, values):
    editor = service.override_editor(c.principal, identifier)
    context = OverrideContext(
        baseline_version_id=editor.baseline.id,
        tenancy_revision=editor.tenancy_revision,
        configuration_id=editor.configuration.id if editor.configuration else None,
    )
    preview = service.preview_override(
        c.principal, OverridePreviewRequest(tenancy_id=identifier, values=values, context=context)
    )
    return ConfigurationUpdate(
        client_request_key=uuid4(),
        tenancy_id=identifier,
        override_mode=True,
        overrides=values,
        override_context=context,
        preview_hash=preview.preview_hash,
    )


# A reviewed publication can change one authored category without accidentally changing the other.
def changed_baseline(c, policy=True, quota=False):
    app = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    old = app.read(c.principal).latest
    values = old.content.model_dump()
    if policy:
        values["policy_statements"] = ("Allow group NewPolicy to inspect instances in tenancy",)
    if quota:
        values["quota_statements"] = ("Set compute quota NewQuota to 8 in tenancy",)
    draft = app.save(
        c.principal,
        SaveBaselineDraft(based_on_id=old.id, content=old.content.model_validate(values)),
    )
    return app.publish(
        c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=draft.edit_revision)
    )


# Same-baseline edits change configuration identity; verification advances only after worker
# readback.
def test_override_apply_clear_and_persisted_revision_chain(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, facade = updates(c)
    original = service.override_editor(c.principal, identifier)
    command = override_command(
        c,
        service,
        identifier,
        OverrideValues(
            policy_override_statements=("Allow group Example to inspect instances in tenancy",),
            monthly_budget_override_amount=Decimal("500"),
        ),
    )
    receipt = service.start(c.principal, command)
    with c.engine.connect() as connection:
        pending = (
            connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        )
        assert pending["baseline_version_id"] == original.baseline.id
        assert (
            pending["desired_configuration_id"]
            and pending["last_verified_configuration_id"] is None
        )
        assert (
            connection.scalar(
                select(tenancy_configuration.c.monthly_budget_override_amount).where(
                    tenancy_configuration.c.id == pending["desired_configuration_id"]
                )
            )
            == 500
        )
    worker.run(receipt.operation_id)
    editor = service.override_editor(c.principal, identifier)
    assert (
        editor.values.monthly_budget_override_amount == 500
        and editor.configuration.revision_number == 1
    )
    assert service.start(c.principal, command).operation_id == receipt.operation_id
    # A later published default cannot be implicitly adopted while clearing an assigned override.
    publish(c)
    clear = service.start(c.principal, override_command(c, service, identifier, OverrideValues()))
    worker.run(clear.operation_id)
    current = service.override_editor(c.principal, identifier)
    assert current.baseline == original.baseline and current.configuration.revision_number == 2
    assert (
        current.configuration.previous_id == editor.configuration.id
        and current.values == OverrideValues()
    )
    with c.engine.connect() as connection:
        row = connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        assert (
            row["desired_configuration_id"]
            == row["last_verified_configuration_id"]
            == current.configuration.id
        )
        assert (
            row["configuration_observation"]["budget"]["payload"]
            != pending["configuration_observation"]
        )
    # Immutable rows cannot be rewritten even by a maintenance connection without trigger removal.
    with pytest.raises(Exception, match="immutable|permitted|not allowed|append"):
        with c.engine.begin() as connection:
            connection.execute(
                update(tenancy_configuration)
                .where(tenancy_configuration.c.id == current.configuration.id)
                .values(monthly_budget_override_amount=999)
            )


# Budget-only overrides carry across amount/tag/policy changes without statement review.
def test_budget_override_survives_baseline_update(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = updates(c)
    receipt = service.start(
        c.principal,
        override_command(
            c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("750"))
        ),
    )
    worker.run(receipt.operation_id)
    latest = changed_baseline(c)
    preview = service.preview(c.principal)
    assert not preview.conflicts and not preview.blockers
    plans = ConfigurationPlans(service)
    plan = plans.create(c.principal, CreateConfigurationPlan(client_request_key=uuid4()))
    receipt = service.start(
        c.principal,
        ConfigurationUpdate(
            client_request_key=uuid4(), plan_id=plan.id, preview_hash=plan.preview.preview_hash
        ),
    )
    worker.run(receipt.operation_id)
    editor = service.override_editor(c.principal, identifier)
    assert editor.baseline.id == latest.id and editor.values.monthly_budget_override_amount == 750
    with c.engine.connect() as connection:
        payload = connection.scalar(
            select(tenancy.c.configuration_observation).where(tenancy.c.id == identifier)
        )
        assert "750.0000" in payload["budget"]["payload"]
        assert "NewPolicy" in payload["policy"]["payload"]


# Reviewing all conflicts is staging only; one missing category prevents the complete fleet
# admission.
@pytest.mark.parametrize("policy_choice", ["keep_override", "use_new_baseline"])
def test_whole_batch_conflicts_staged_then_atomically_applied(workflow_case, policy_choice):
    c = workflow_case
    identifiers = children(c)
    service, worker, _ = updates(c)
    values = OverrideValues(
        policy_override_statements=("Allow group OverridePolicy to read buckets in tenancy",),
        quota_override_statements=("Set compute quota OverrideQuota to 2 in tenancy",),
        monthly_budget_override_amount=Decimal("600"),
    )
    receipt = service.start(c.principal, override_command(c, service, identifiers[0], values))
    worker.run(receipt.operation_id)
    latest = changed_baseline(c, policy=True, quota=True)
    plans = ConfigurationPlans(service)
    request = CreateConfigurationPlan(client_request_key=uuid4())
    plan = plans.create(c.principal, request)
    assert plans.create(c.principal, request).id == plan.id
    assert (
        plan.preview.ready_count == 1
        and len(plan.preview.blockers) == 1
        and len(plan.preview.conflicts) == 1
    )
    with c.engine.connect() as connection:
        before = (
            connection.execute(
                select(tenancy).where(tenancy.c.id.in_(identifiers)).order_by(tenancy.c.id)
            )
            .mappings()
            .all()
        )
        jobs = connection.scalar(text("SELECT count(*) FROM public.procrastinate_jobs"))
    with pytest.raises(OrganizationConflict):
        service.start(
            c.principal,
            ConfigurationUpdate(
                client_request_key=uuid4(), plan_id=plan.id, preview_hash=plan.preview.preview_hash
            ),
        )
    with pytest.raises(OrganizationConflict):
        plans.review(
            c.principal,
            plan.id,
            SaveConfigurationReview(
                expected_revision=plan.revision,
                tenancy_id=identifiers[0],
                policy_choice=policy_choice,
            ),
        )
    reviewed = plans.review(
        c.principal,
        plan.id,
        SaveConfigurationReview(
            expected_revision=plan.revision,
            tenancy_id=identifiers[0],
            policy_choice=policy_choice,
            quota_choice="keep_override",
        ),
    )
    assert reviewed.preview.ready_count == 2 and not reviewed.preview.blockers
    assert plans.read(c.principal, plan.id) == reviewed
    with c.engine.connect() as connection:
        assert (
            connection.execute(
                select(tenancy).where(tenancy.c.id.in_(identifiers)).order_by(tenancy.c.id)
            )
            .mappings()
            .all()
            == before
        )
        assert connection.scalar(text("SELECT count(*) FROM public.procrastinate_jobs")) == jobs
        assert connection.scalar(
            select(audit_event.c.id).where(
                audit_event.c.kind == "configuration_review_staged",
                audit_event.c.workspace_id == c.policy.workspace_id,
            )
        )
    command = ConfigurationUpdate(
        client_request_key=uuid4(), plan_id=plan.id, preview_hash=reviewed.preview.preview_hash
    )
    receipt = service.start(c.principal, command)
    worker.run(receipt.operation_id)
    assert plans.read(c.principal, plan.id).state == "accepted"
    assert service.start(c.principal, command).operation_id == receipt.operation_id
    editor = service.override_editor(c.principal, identifiers[0])
    assert editor.baseline.id == latest.id
    assert editor.values.quota_override_statements == values.quota_override_statements
    assert editor.values.policy_override_statements == (
        values.policy_override_statements if policy_choice == "keep_override" else None
    )
    assert editor.values.monthly_budget_override_amount == 600
    with c.engine.connect() as connection:
        data = connection.scalar(
            select(tenancy.c.configuration_observation).where(tenancy.c.id == identifiers[0])
        )
        assert ("OverridePolicy" in data["policy"]["payload"]) == (policy_choice == "keep_override")
        assert "OverrideQuota" in data["quota"]["payload"]


# Later publication or a separate override edit invalidates staged evidence rather than rebasing it.
@pytest.mark.parametrize("change", ["publication", "override", "membership_revision"])
def test_plan_and_editor_staleness_preserve_original_context(workflow_case, change):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = updates(c)
    receipt = service.start(
        c.principal,
        override_command(
            c,
            service,
            identifier,
            OverrideValues(
                policy_override_statements=(
                    "Allow group OldOverride to inspect instances in tenancy",
                )
            ),
        ),
    )
    worker.run(receipt.operation_id)
    target = changed_baseline(c)
    plans = ConfigurationPlans(service)
    plan = plans.create(c.principal, CreateConfigurationPlan(client_request_key=uuid4()))
    draft = override_command(
        c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("900"))
    )
    if change == "publication":
        changed_baseline(c, quota=True)
    elif change == "override":
        receipt = service.start(
            c.principal, draft.model_copy(update={"client_request_key": uuid4()})
        )
        worker.run(receipt.operation_id)
    else:
        with c.engine.begin() as connection:
            connection.execute(
                update(tenancy)
                .where(tenancy.c.id == identifier)
                .values(revision=tenancy.c.revision + 1)
            )
    stale = plans.read(c.principal, plan.id)
    assert stale.state == "stale" and stale.preview.baseline.id == target.id
    with pytest.raises(OrganizationConflict):
        plans.review(
            c.principal,
            plan.id,
            SaveConfigurationReview(
                expected_revision=plan.revision,
                tenancy_id=identifier,
                policy_choice="keep_override",
            ),
        )
    with pytest.raises(OrganizationConflict):
        service.start(
            c.principal,
            ConfigurationUpdate(
                client_request_key=uuid4(), plan_id=plan.id, preview_hash=plan.preview.preview_hash
            ),
        )
    if change != "publication":
        with pytest.raises(OrganizationConflict):
            service.start(c.principal, draft.model_copy(update={"client_request_key": uuid4()}))


# Failed application keeps prior verified revision even when the baseline itself has not changed.
def test_partial_override_failure_keeps_prior_verified_configuration(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, facade = updates(c)
    first = service.start(
        c.principal,
        override_command(
            c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("400"))
        ),
    )
    worker.run(first.operation_id)
    previous = service.override_editor(c.principal, identifier).configuration
    next_receipt = service.start(
        c.principal,
        override_command(
            c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("800"))
        ),
    )
    with patch.object(facade, "apply", side_effect=ValueError("SYNTHETIC_FAILURE")):
        worker.run(next_receipt.operation_id)
    with c.engine.connect() as connection:
        row = connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        assert (
            row["last_verified_configuration_id"] == previous.id
            and row["desired_configuration_id"] != previous.id
        )
    service.retry(c.principal, next_receipt.operation_id)
    worker.run(next_receipt.operation_id)
    assert service.progress(c.principal, next_receipt.operation_id).state == "succeeded"


# An accepted plan cannot acquire a new target or have historical staged choices rewritten.
def test_accepted_plan_targets_and_revision_sql_guards(workflow_case):
    from otm.storage.tables import configuration_plan_target

    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = updates(c)
    publish(c)
    plans = ConfigurationPlans(service)
    plan = plans.create(c.principal, CreateConfigurationPlan(client_request_key=uuid4()))
    receipt = service.start(
        c.principal,
        ConfigurationUpdate(
            client_request_key=uuid4(), plan_id=plan.id, preview_hash=plan.preview.preview_hash
        ),
    )
    worker.run(receipt.operation_id)
    with c.engine.connect() as connection:
        row = (
            connection.execute(
                select(configuration_plan_target).where(
                    configuration_plan_target.c.plan_id == plan.id
                )
            )
            .mappings()
            .one()
        )
    with pytest.raises(Exception, match="accepted plan target is immutable"):
        with c.engine.begin() as connection:
            connection.execute(
                configuration_plan_target.insert().values(**{**dict(row), "tenancy_id": uuid4()})
            )
    with pytest.raises(Exception, match="accepted plan is immutable"):
        with c.engine.begin() as connection:
            connection.execute(
                update(configuration_plan)
                .where(configuration_plan.c.id == plan.id)
                .values(revision=2)
            )
    current = service.override_editor(c.principal, identifier).configuration
    for overrides in (
        {"monthly_budget_override_amount": Decimal("500.5")},
        {"policy_override_statements": []},
        {"quota_override_statements": {"invalid": "object"}},
    ):
        with pytest.raises(Exception, match="ck_configuration"):
            with c.engine.begin() as connection:
                connection.execute(
                    tenancy_configuration.insert().values(
                        workspace_id=c.policy.workspace_id,
                        **{
                            **current.model_dump(),
                            "id": uuid4(),
                            "revision_number": current.revision_number + 1,
                            "previous_id": current.id,
                            **overrides,
                        },
                    )
                )


# Freeze the previous serialized format only at initial insertion; old hashes and request
# digests persist.
def test_legacy_baseline_only_intent_can_resume_and_replay(workflow_case):
    from unittest.mock import Mock

    from sqlalchemy.engine import Connection

    from otm.operations.contracts import canonical_hash

    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = updates(c)
    publish(c)
    preview = service.preview(c.principal, identifier)
    command = ConfigurationUpdate(
        client_request_key=uuid4(), tenancy_id=identifier, preview_hash=preview.preview_hash
    )
    execute = Connection.execute

    # Reconstruct a historical accepted row without retroactively fabricating a configuration head.
    def insert_legacy(connection, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False):
            if statement.table.name == "otm_tenancy_configuration":
                return Mock(rowcount=1)
            if statement.table.name == "audit_event":
                values = statement.compile().params
                if values.get("kind") == "operation_intent":
                    payload = json.loads(json.dumps(values["data"]))
                    payload["intent"].pop("change_kind", None)
                    for target in payload["intent"]["targets"]:
                        for key in [
                            "source_configuration_id",
                            "source_verified_configuration_id",
                            "configuration",
                            "overrides",
                            "review",
                        ]:
                            target.pop(key, None)
                    statement = statement.values(data=payload, data_hash=canonical_hash(payload))
        elif getattr(statement, "is_update", False) and statement.table.name == "otm_tenancy":
            if "desired_configuration_id" in statement.compile().params:
                statement = statement.values(desired_configuration_id=None)
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", new=insert_legacy):
        receipt = service.start(c.principal, command)
    worker.run(receipt.operation_id)
    assert service.progress(c.principal, receipt.operation_id).state == "succeeded"
    assert service.start(c.principal, command).operation_id == receipt.operation_id
    editor = service.override_editor(c.principal, identifier)
    assert editor.configuration is None
    next_receipt = service.start(
        c.principal,
        override_command(
            c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("500"))
        ),
    )
    worker.run(next_receipt.operation_id)
    assert service.override_editor(c.principal, identifier).configuration.revision_number == 1


# Same-preview edits serialize; retries share one revision/job, competing commands fail closed.
@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_override_acceptance_has_one_revision_and_job(workflow_case, same_key):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = updates(c)
    command = override_command(
        c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("900"))
    )
    other = command if same_key else command.model_copy(update={"client_request_key": uuid4()})
    barrier = Barrier(2)

    # Force independent request transactions to compete for the same child and source version.
    def accept(value):
        barrier.wait(timeout=5)
        try:
            return service.start(c.principal, value)
        except OrganizationConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = [value for value in pool.map(accept, [command, other]) if value is not None]
    assert len(accepted) == (2 if same_key else 1)
    assert len({value.operation_id for value in accepted}) == 1
    operation_id = accepted[0].operation_id
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(text("count(*)"))
                .select_from(tenancy_configuration)
                .where(tenancy_configuration.c.tenancy_id == identifier)
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.procrastinate_jobs WHERE args->>'operation_id'=:id"
                ),
                {"id": str(operation_id)},
            )
            == 1
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker.run, [operation_id, operation_id]))
    assert service.progress(c.principal, operation_id).state == "succeeded"
    with c.engine.connect() as connection:
        row = connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        assert row["desired_configuration_id"] == row["last_verified_configuration_id"]


# Failed queue admission rolls back the new immutable revision, desired pointer and audit together.
def test_override_enqueue_failure_leaves_no_partial_configuration(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, _, _ = updates(c)
    command = override_command(
        c, service, identifier, OverrideValues(monthly_budget_override_amount=Decimal("900"))
    )
    with patch.object(
        service.enqueuer, "enqueue", side_effect=RuntimeError("synthetic queue outage")
    ):
        with pytest.raises(RuntimeError, match="synthetic queue outage"):
            service.start(c.principal, command)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(text("count(*)"))
                .select_from(tenancy_configuration)
                .where(tenancy_configuration.c.tenancy_id == identifier)
            )
            == 0
        )
        assert (
            connection.scalar(
                select(tenancy.c.desired_configuration_id).where(tenancy.c.id == identifier)
            )
            is None
        )
