"""Actual native worker, exact-intent migration, and read publication integration regressions."""

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import procrastinate
import pytest
from psycopg.conninfo import make_conninfo
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from test_admission_postgres import accepted, admission, pg_case, records
from test_admission_service import NOW

from otm.operations.execution import SimulatedInspectionWorker
from otm.operations.execution_contracts import DispatchGrant, InspectionOutcome
from otm.operations.runner import register_inspection_task
from otm.providers.inspection import TenancyInspection
from otm.providers.inspection_contracts import InspectTenancy, TenancyFacts
from otm.providers.inspection_simulator import (
    ManualClock,
    SimulatedAccess,
    SimulatedInspectionProvider,
    SimulatedTenancy,
)
from otm.storage.execution import SqlExecutionStore
from otm.storage.tables import audit_event, operation, operation_step

pytestmark = pytest.mark.postgres
__all__ = ["admission", "pg_case"]


# Use real acceptance/storage and independent server/provider state in a fresh workspace.
@pytest.fixture
def worker_case(pg_case):
    receipt = accepted(pg_case)
    store = SqlExecutionStore(pg_case.engine)
    committed = store.load(receipt.operation_id)
    grant = DispatchGrant(
        workspace_id=committed.intent.workspace_id,
        actor_key=committed.actor.key,
        policy_revision=committed.intent.policy_revision,
        runtime_policy_revision=uuid4(),
        access_binding_id=committed.intent.access_binding_id,
        credential_generation=1,
    )
    authority = Mock(require_inspection=Mock(return_value=grant))
    clock = ManualClock(NOW)
    provider = SimulatedInspectionProvider(clock.now)
    provider.set_access(
        SimulatedAccess(
            workspace_id=committed.intent.workspace_id,
            access_binding_id=grant.access_binding_id,
            credential_generation=1,
            permitted=True,
            tenancy_ocids=frozenset({committed.intent.target.tenancy_ocid}),
        )
    )
    tenancy = SimulatedTenancy(
        workspace_id=committed.intent.workspace_id,
        visible_at=NOW,
        facts=TenancyFacts(
            **committed.intent.target.model_dump(),
            actual_name="Example sandbox",
            home_region_key="EXAMPLE-HOME",
            home_region_identifier=None,
            role="CHILD",
            observed_at=NOW,
        ),
    )
    provider.set_tenancy(tenancy)
    inspection = TenancyInspection(provider, clock.now)
    worker = SimulatedInspectionWorker(store, authority, inspection, clock.now)
    return SimpleNamespace(
        case=pg_case,
        receipt=receipt,
        store=store,
        committed=committed,
        grant=grant,
        authority=authority,
        clock=clock,
        provider=provider,
        tenancy=tenancy,
        inspection=inspection,
        worker=worker,
    )


# Inspect one workspace's single logical read step via an independent connection.
def step_row(case):
    with case.case.engine.connect() as connection:
        return (
            connection.execute(
                select(operation_step).where(
                    operation_step.c.workspace_id == case.committed.intent.workspace_id
                )
            )
            .mappings()
            .one_or_none()
        )


# Deserialize durable normalized result evidence, not the simulator's in-memory registry.
def read_outcome(case):
    events = records(case.case)[1]
    event = next(row for row in events if row["kind"] == "inspection_outcome")
    return InspectionOutcome.model_validate_json(json.dumps(event["data"]))


# Execute actual runner fetching/completion while isolating this test's queued job.
def test_real_native_worker_consumes_reference_and_persists_verified_read(worker_case):
    case = worker_case
    url = case.case.engine.url
    conninfo = make_conninfo(
        hostaddr="127.0.0.1",
        host="127.0.0.1",
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.database,
        options="-c timezone=UTC -c statement_timeout=10000",
    )
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=conninfo, min_size=1, max_size=2)
    )
    register_inspection_task(app, case.worker)
    # Other admission tests deliberately retain queued jobs. Move only our own job to an
    # isolated test queue, keeping its real native task, reference, lock and payload unchanged.
    queue = "otm.test." + uuid4().hex
    with case.case.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.procrastinate_jobs SET queue_name=:queue "
                "WHERE args->>'operation_id'=:id"
            ),
            {"queue": queue, "id": str(case.receipt.operation_id)},
        )
    app.run_worker(queues=[queue], wait=False, concurrency=1, listen_notify=False)
    ops, events, _ = records(case.case)
    assert ops[0]["state"] == "succeeded" and ops[0]["effect_knowledge"] == "none"
    assert [
        event["kind"] for event in sorted(events, key=lambda row: row["intent_revision"] is None)
    ].count("operation_intent") == 1
    assert len(events) == 3 and step_row(case)["state"] == "verified"
    result = read_outcome(case)
    assert (
        result.provider_mode == "simulated"
        and result.result.tenancy.actual_name == "Example sandbox"
    )
    assert result.result.tenancy.home_region_identifier is None
    with case.case.engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT status::text FROM public.procrastinate_jobs "
                    "WHERE args->>'operation_id'=:id"
                ),
                {"id": str(case.receipt.operation_id)},
            ).scalar_one()
            == "succeeded"
        )
    before = records(case.case)[1]
    case.worker.run(case.receipt.operation_id)
    assert records(case.case)[1] == before


# Provider uncertainty persists without deletion, onboarding or hidden automatic retry.
@pytest.mark.parametrize("fault", ["denied", "timeout", "unsupported"])
def test_unavailable_inspection_never_marks_business_success(worker_case, fault):
    case = worker_case
    case.provider.set_tenancy(case.tenancy.model_copy(update={"fault": fault}))
    case.worker.run(case.receipt.operation_id)
    assert records(case.case)[0][0]["state"] == "needs_attention"
    assert step_row(case)["verified_at"] is None
    assert read_outcome(case).result.kind in {"unobservable", "unsupported"}


# Current authority failure creates one safe outcome without a dispatch or step.
def test_revoked_actor_blocks_before_claim_and_provider_read(worker_case):
    case = worker_case
    case.authority.require_inspection.side_effect = PermissionError("private-example")
    case.worker.inspection = Mock()
    case.worker.run(case.receipt.operation_id)
    assert step_row(case) is None
    assert records(case.case)[0][0]["state"] == "needs_attention"
    assert len(records(case.case)[1]) == 2
    assert read_outcome(case).safe_code == "DISPATCH_NOT_AUTHORIZED"
    case.worker.inspection.inspect.assert_not_called()


# Revoke authority during the read and retain no confirmed tenancy observation.
def test_read_permission_change_discards_previously_confirmed_result(worker_case):
    case = worker_case
    case.authority.require_inspection.side_effect = [
        case.grant,
        case.grant,
        PermissionError("revoked"),
    ]
    case.worker.run(case.receipt.operation_id)
    assert read_outcome(case).result is None
    assert records(case.case)[0][0]["state"] == "needs_attention"
    assert step_row(case)["verified_at"] is None


# Actual row locks and revision predicates arbitrate two checked-out transactions.
def test_only_one_concurrent_claim_wins_the_same_operation_revision(worker_case):
    case = worker_case
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: case.store.claim(case.committed, case.grant, NOW), range(2))
        )
    assert sum(result is not None for result in results) == 1
    assert len(records(case.case)[1]) == 2 and step_row(case)["attempt_number"] == 1


# Read redelivery advances generation; an earlier late result cannot publish.
def test_interrupted_read_can_be_superseded_but_old_attempt_cannot_publish(worker_case):
    case = worker_case
    old = case.store.claim(case.committed, case.grant, NOW)
    fresh = case.store.load(case.receipt.operation_id)
    current = case.store.claim(fresh, case.grant, NOW)
    assert current.context.execution_generation == old.context.execution_generation + 1
    result = case.inspection.inspect(
        InspectTenancy(
            contract_version="execution-1-draft",
            kind="inspect_tenancy",
            context=old.context,
            payload=case.committed.intent.target,
        )
    )
    outcome = InspectionOutcome(
        context=old.context,
        intent_event_id=case.committed.intent_event_id,
        safe_code=result.safe_code,
        result=result,
    )
    assert case.store.finish(case.committed, old, outcome, NOW) is False
    assert len(records(case.case)[1]) == 3 and records(case.case)[0][0]["state"] == "running"
    result = case.inspection.inspect(
        InspectTenancy(
            contract_version="execution-1-draft",
            kind="inspect_tenancy",
            context=current.context,
            payload=fresh.intent.target,
        )
    )
    outcome = InspectionOutcome(
        context=current.context,
        intent_event_id=fresh.intent_event_id,
        safe_code=result.safe_code,
        result=result,
    )
    assert case.store.finish(fresh, current, outcome, NOW) is True
    assert len(records(case.case)[1]) == 4 and records(case.case)[0][0]["state"] == "succeeded"
    assert step_row(case)["last_outcome"]["context"]["attempt_id"] == str(
        current.context.attempt_id
    )


# CHECK must reject SQL UNKNOWN as well as invalid event/revision combinations.
@pytest.mark.parametrize(
    "kind,revision",
    [
        ("operation_intent", None),
        ("operation_intent", 0),
        ("inspection_outcome", 1),
        ("unknown", None),
    ],
)
def test_audit_revision_check_rejects_null_intents_and_nonnull_outcomes(
    worker_case, kind, revision
):
    case = worker_case
    original = dict(records(case.case)[1][0])
    original.update(id=uuid4(), kind=kind, intent_revision=revision)
    with pytest.raises(IntegrityError):
        with case.case.engine.begin() as connection:
            connection.execute(audit_event.insert().values(**original))
    assert len(records(case.case)[1]) == 1


# A nullable outcome revision cannot satisfy the operation's positive exact-intent FK.
def test_outcome_cannot_be_substituted_for_exact_current_intent(worker_case):
    case = worker_case
    case.worker.run(case.receipt.operation_id)
    event = next(e for e in records(case.case)[1] if e["kind"] == "inspection_outcome")
    with pytest.raises(IntegrityError):
        with case.case.engine.begin() as connection:
            connection.execute(
                update(operation)
                .where(operation.c.id == case.receipt.operation_id)
                .values(current_intent_event_id=event["id"])
            )
    assert case.store.load(case.receipt.operation_id) is None


# A failure after audit insertion cannot leave a false terminal operation or evidence head.
def test_failed_publication_rolls_back_outcome_and_step_then_read_redelivery_recovers(worker_case):
    from unittest.mock import patch

    case = worker_case
    original = case.store._audit

    # Fail only after the real outcome INSERT; leave committed dispatch history intact.
    def reject_outcome(connection, committed, kind, data, at):
        identifier = original(connection, committed, kind, data, at)
        if kind == "inspection_outcome":
            raise RuntimeError("controlled publication failure")
        return identifier

    with patch.object(case.store, "_audit", side_effect=reject_outcome):
        with pytest.raises(RuntimeError, match="controlled publication failure"):
            case.worker.run(case.receipt.operation_id)
    assert records(case.case)[0][0]["state"] == "running"
    assert len(records(case.case)[1]) == 2
    assert step_row(case)["evidence_event_id"] is None
    case.worker.run(case.receipt.operation_id)
    assert records(case.case)[0][0]["state"] == "succeeded"
    assert len(records(case.case)[1]) == 4 and step_row(case)["attempt_number"] == 2


# Session setup writes under0001; head upgrade must preserve pointer, actor and native job.
def test_forward_upgrade_preserves_existing_acceptance_and_immutable_intent(pg_engine):
    with pg_engine.connect() as connection:
        row = (
            connection.execute(
                select(operation).where(operation.c.workspace_id == "migration-compatibility")
            )
            .mappings()
            .one()
        )
        event = (
            connection.execute(
                select(audit_event).where(audit_event.c.id == row["current_intent_event_id"])
            )
            .mappings()
            .one()
        )
        assert row["state"] == "queued" and event["kind"] == "operation_intent"
        assert event["intent_revision"] == row["current_intent_revision"] == 1
        assert event["data"]["intent"]["target"]["tenancy_ocid"] == "ocid1.tenancy.oc1..legacychild"
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM public.procrastinate_jobs WHERE args->>'operation_id'=:id"
                ),
                {"id": str(row["id"])},
            ).scalar_one()
            == 1
        )


# Host/VM clock skew must not postpone jobs that were explicitly admitted for immediate execution.
def test_immediate_admission_ignores_host_eta_clock(pg_case):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import patch

    future = datetime.now(UTC) + timedelta(seconds=5)
    with patch("procrastinate.utils.datetime_from_timedelta_params", return_value=future):
        receipt = accepted(pg_case)
    with pg_case.engine.connect() as connection:
        due = connection.scalar(
            text(
                "SELECT scheduled_at FROM public.procrastinate_jobs WHERE args->>'operation_id'=:id"
            ),
            {"id": str(receipt.operation_id)},
        )
    assert due is None
