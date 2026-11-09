"""Real transactions qualify baseline batches, failure isolation, retries and authority guards."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.engine import Connection
from test_baseline_pinning_postgres import publish
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.configuration.rollout import ConfigurationRollouts
from otm.configuration.rollout_contracts import ConfigurationUpdate
from otm.configuration.rollout_worker import ConfigurationUpdateWorker
from otm.providers.configuration_simulator import SimulatedConfigurationFacade
from otm.storage.enqueue import CONFIGURATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import administrator, audit_event, operation, operation_step, tenancy

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Build registered children only through the existing real activation and setup handoff.
def children(c, count=2):
    people = {p.email: p for p in c.store.head(c.principal).people}
    identifiers = []
    for email in ["engineer@example.test", "one@example.test"][:count]:
        _, receipt = action(c, people[email].id, "create_tenancy")
        complete_setup(c, receipt.operation_id)
        identifiers.append(c.workflow.onboarding(c.principal, receipt.operation_id).tenancy_id)
    return identifiers


# Compose the exact simulator, scoped native enqueue adapter and real SQL-backed application store.
def updates(c):
    facade = SimulatedConfigurationFacade(c.loader().policy)
    service = ConfigurationRollouts(
        c.store,
        policy=c.loader().policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(c.policy.workspace_id), task=CONFIGURATION_TASK
        ),
    )
    worker = ConfigurationUpdateWorker(c.engine, c.policy.workspace_id, c.clock, c.loader, facade)
    return service, worker, facade


# Freeze the actual coherent server preview rather than fabricating an admission fingerprint.
def request(c, service, scope=None):
    view = service.preview(c.principal, scope)
    return ConfigurationUpdate(
        client_request_key=uuid4(), tenancy_id=scope, preview_hash=view.preview_hash
    )


# A newer publication cannot retarget admitted work, including replay after worker completion.
def test_individual_update_freezes_version_and_verifies_four_objects(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    _, second = publish(c)
    service, worker, _ = updates(c)
    command = request(c, service, identifier)
    receipt = service.start(c.principal, command)
    assert receipt.state == "queued"
    publish(c, "750")
    assert service.start(c.principal, command).operation_id == receipt.operation_id
    worker.run(receipt.operation_id)
    result = service.progress(c.principal, receipt.operation_id)
    assert result.state == "succeeded" and result.baseline.id == second.id
    assert result.targets[0].state == "verified" and not result.can_retry
    with c.engine.connect() as connection:
        row = connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        assert row["baseline_version_id"] == row["verified_baseline_version_id"] == second.id
        assert row["operation_id"] is None and row["configuration_verified_at"] is not None
        assert set(row["configuration_observation"]) == {"policy", "quota", "budget", "tags"}
    assert service.preview(c.principal, identifier).ready_count == 1
    worker.run(receipt.operation_id)
    assert service.retry(c.principal, receipt.operation_id).state == "succeeded"


# One blocked child gates admission; later provider failure keeps successful children and audit
# intact.
def test_bulk_partial_failure_retains_verified_prefix_and_retry(workflow_case):
    c = workflow_case
    identifiers = children(c)
    _, second = publish(c)
    service, worker, facade = updates(c)
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == identifiers[0])
            .values(operation_id=tenancy.c.last_operation_id)
        )
    blocked = service.preview(c.principal)
    assert blocked.ready_count == 1 and len(blocked.blockers) == 1
    with pytest.raises(OrganizationConflict, match="CONFIGURATION_UPDATE_BLOCKED"):
        service.start(c.principal, request(c, service))
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy).where(tenancy.c.id == identifiers[0]).values(operation_id=None)
        )
    receipt = service.start(c.principal, request(c, service))
    apply = facade.apply
    failed = identifiers[0]

    # Fail the third category of exactly one child after its first two writes have committed
    # locally.
    def fail_budget(target, desired, previous):
        if target.tenancy_id == failed and desired.category == "budget":
            raise ValueError("SYNTHETIC_BUDGET_FAILURE")
        return apply(target, desired, previous)

    with patch.object(facade, "apply", side_effect=fail_budget):
        worker.run(receipt.operation_id)
    progress = service.progress(c.principal, receipt.operation_id)
    assert progress.state == "needs_attention" and progress.can_retry
    assert service.actionable_count(c.principal) == 1
    assert {t.state for t in progress.targets} == {"verified", "needs_attention"}
    with c.engine.connect() as connection:
        rows = {
            r["id"]: r
            for r in connection.execute(
                select(tenancy).where(tenancy.c.id.in_(identifiers))
            ).mappings()
        }
        assert rows[failed]["verified_baseline_version_id"] != second.id
        assert rows[failed]["operation_id"] == receipt.operation_id
        assert set(rows[failed]["configuration_observation"]) == {
            "policy",
            "quota",
            "budget",
            "tags",
        }
        assert rows[identifiers[1]]["verified_baseline_version_id"] == second.id
    service.retry(c.principal, receipt.operation_id)
    with patch.object(facade, "apply", wraps=apply) as calls:
        worker.run(receipt.operation_id)
    assert [call.args[1].category for call in calls.call_args_list] == ["budget"]
    assert service.progress(c.principal, receipt.operation_id).state == "succeeded"
    assert service.actionable_count(c.principal) == 0
    with c.engine.connect() as connection:
        steps = (
            connection.execute(
                select(operation_step).where(operation_step.c.operation_id == receipt.operation_id)
            )
            .mappings()
            .all()
        )
        assert sorted(r["attempt_number"] for r in steps) == [1, 2]
        kinds = (
            connection.execute(
                select(audit_event.c.kind).where(audit_event.c.operation_id == receipt.operation_id)
            )
            .scalars()
            .all()
        )
        assert kinds.count("configuration_outcome") == 3 and kinds.count("configuration_retry") == 1


# Stale scope and failed queue/audit commits never leave pins or reservations partially changed.
@pytest.mark.parametrize("failure", ["queue", "audit"])
def test_stale_and_failed_admission_roll_back_entire_batch(workflow_case, failure):
    c = workflow_case
    identifiers = children(c)
    service, _, _ = updates(c)
    stale = request(c, service)
    publish(c)
    with pytest.raises(OrganizationConflict, match="CONFIGURATION_PREVIEW_CHANGED"):
        service.start(c.principal, stale)
    with c.engine.connect() as connection:
        before = (
            connection.execute(select(tenancy).where(tenancy.c.id.in_(identifiers)))
            .mappings()
            .all()
        )
    execute = Connection.execute

    # Inject failure only after admission has begun writing, so transaction rollback is meaningful.
    def fail_audit(connection, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and statement.table.name == "audit_event":
            raise RuntimeError("SYNTHETIC_FAILURE")
        return execute(connection, statement, *args, **kwargs)

    boundary = (
        patch.object(service.enqueuer, "enqueue", side_effect=RuntimeError("SYNTHETIC_FAILURE"))
        if failure == "queue"
        else patch.object(Connection, "execute", new=fail_audit)
    )
    command = request(c, service)
    with boundary, pytest.raises(RuntimeError, match="SYNTHETIC_FAILURE"):
        service.start(c.principal, command)
    with c.engine.connect() as connection:
        after = (
            connection.execute(select(tenancy).where(tenancy.c.id.in_(identifiers)))
            .mappings()
            .all()
        )
        assert before == after
        assert (
            connection.execute(
                select(operation.c.id).where(
                    operation.c.client_request_key == command.client_request_key
                )
            ).first()
            is None
        )


# Fresh authority and exact registered-child guards run before any fake provider write.
@pytest.mark.parametrize("change", ["grant", "parent", "revision", "pin"])
def test_dispatch_rechecks_authority_and_target(workflow_case, change):
    c = workflow_case
    identifier = children(c, 1)[0]
    with c.engine.connect() as connection:
        original_verified = connection.scalar(
            select(tenancy.c.verified_baseline_version_id).where(tenancy.c.id == identifier)
        )
    _, second = publish(c)
    service, worker, facade = updates(c)
    receipt = service.start(c.principal, request(c, service, identifier))
    with c.engine.begin() as connection:
        if change == "grant":
            connection.execute(
                update(administrator)
                .where(administrator.c.workspace_id == c.policy.workspace_id)
                .values(authorization_revision=uuid4())
            )
        else:
            value = {
                "parent": {"parent_tenancy_ocid": "ocid1.tenancy.oc1..otmsimother"},
                "revision": {"revision": tenancy.c.revision + 1},
                "pin": {"baseline_version_id": None},
            }[change]
            connection.execute(update(tenancy).where(tenancy.c.id == identifier).values(**value))
    with patch.object(facade, "apply", wraps=facade.apply) as calls:
        worker.run(receipt.operation_id)
    calls.assert_not_called()
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(tenancy.c.verified_baseline_version_id).where(tenancy.c.id == identifier)
            )
            == original_verified
        )
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == receipt.operation_id)
            )
            == "needs_attention"
        )
    assert second.id


# Maximum-size valid Unicode completes through persistence rather than retrying forever.
def test_unicode_recipe_round_trip(workflow_case):
    from test_baseline_authoring import content

    from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
    from otm.configuration.service import BaselineAuthoring
    from otm.providers.baseline_simulator import SimulatedBaselineQualifier

    c = workflow_case
    identifier = children(c, 1)[0]
    recipes = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    previous = recipes.read(c.principal).latest
    draft = recipes.save(
        c.principal,
        SaveBaselineDraft(
            based_on_id=previous.id,
            content=content(quota_statements=tuple(str(i) + "😀" * 1998 for i in range(50))),
        ),
    )
    recipes.publish(
        c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=draft.edit_revision)
    )
    service, worker, _ = updates(c)
    receipt = service.start(c.principal, request(c, service, identifier))
    worker.run(receipt.operation_id)
    assert service.progress(c.principal, receipt.operation_id).state == "succeeded"
    assert service.actionable_count(c.principal) == 0


# A failed later recipe cannot overwrite the last fully verified version or its retrieval time.
def test_failure_preserves_previous_complete_verification(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, facade = updates(c)
    # Onboarding already independently verified the initial baseline.
    with c.engine.connect() as connection:
        before = (
            connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        )
    c.clock.return_value += timedelta(seconds=60)
    _, latest = publish(c)
    second = service.start(c.principal, request(c, service, identifier))
    with patch.object(facade, "apply", side_effect=ValueError("SYNTHETIC_WRITE_FAILURE")):
        worker.run(second.operation_id)
    with c.engine.connect() as connection:
        after = (
            connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        )
    assert after["baseline_version_id"] == latest.id
    assert after["verified_baseline_version_id"] == before["verified_baseline_version_id"]
    assert after["configuration_verified_at"] == before["configuration_verified_at"]
    assert service.progress(c.principal, second.operation_id).can_retry
    service.retry(c.principal, second.operation_id)
    worker.run(second.operation_id)
    assert service.progress(c.principal, second.operation_id).state == "succeeded"


# Concurrent admissions serialize the same preview; only one different command may reserve children.
@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_baseline_update_admission(workflow_case, same_key):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    c = workflow_case
    identifiers = children(c)
    publish(c)
    service, worker, _ = updates(c)
    first = request(c, service)
    second = first if same_key else first.model_copy(update={"client_request_key": uuid4()})
    barrier = Barrier(2)

    # Start both independent database transactions together, retaining a closed conflict outcome.
    def start(command):
        barrier.wait(timeout=5)
        try:
            return service.start(c.principal, command)
        except OrganizationConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start, [first, second]))
    accepted = [result for result in results if result is not None]
    assert len(accepted) == (2 if same_key else 1)
    assert len({result.operation_id for result in accepted}) == 1
    identifier = accepted[0].operation_id
    with c.engine.connect() as connection:
        assert set(
            connection.execute(
                select(tenancy.c.operation_id).where(tenancy.c.id.in_(identifiers))
            ).scalars()
        ) == {identifier}
        assert (
            len(
                connection.execute(
                    select(operation.c.id).where(
                        operation.c.workspace_id == c.policy.workspace_id,
                        operation.c.kind == "configuration_update",
                    )
                ).all()
            )
            == 1
        )
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.procrastinate_jobs "
                    "WHERE args->>'operation_id'=:identifier"
                ),
                {"identifier": str(identifier)},
            )
            == 1
        )
    # Duplicate native deliveries must not produce duplicate verification or overwrite each other.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker.run, [identifier, identifier]))
    assert service.progress(c.principal, identifier).state == "succeeded"
    with c.engine.connect() as connection:
        assert len(
            connection.execute(
                select(audit_event.c.id).where(
                    audit_event.c.operation_id == identifier,
                    audit_event.c.kind == "configuration_outcome",
                )
            ).all()
        ) == len(identifiers)


# Real directory projection resolves lifecycle resources and completion dates with no new storage.
def test_inventory_and_audit_friendly_context(workflow_case):
    from otm.audit.contracts import AuditQuery
    from otm.storage.audit_directory import SqlAuditDirectory
    from otm.tenancies.views import TenancyQuery

    c = workflow_case
    identifier = children(c, 1)[0]
    directory = c.workflow.tenancies(c.principal, TenancyQuery())
    row = directory.items[0]
    assert directory.latest_baseline_id == row.baseline_version_id
    assert directory.latest_baseline_version_number == row.baseline_version_number == 1
    assert row.operation_completed_at is not None
    history = SqlAuditDirectory(c.engine).directory(
        c.policy.workspace_id, AuditQuery(category="operations", page_size=100)
    )
    lifecycle = [event for event in history.items if event.kind == "onboarding_outcome"]
    assert lifecycle and all(
        any(
            resource.kind == "tenancy" and resource.id == identifier and resource.name == row.name
            for resource in event.resources
        )
        for event in lifecycle
    )
    assert any(
        resource.kind == "person" and resource.name == "Engineer"
        for event in lifecycle
        for resource in event.resources
    )
