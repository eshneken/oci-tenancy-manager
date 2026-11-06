"""Financial orchestration unit tests, measured independently of PostgreSQL coverage."""

from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_configuration_drift import drift_case, update_case
from test_financial_values import NOW, example

from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.financial.context import failure_source, target_source
from otm.financial.contracts import (
    CostIntent,
    CostPolicy,
    CostRefreshRequest,
    CostTarget,
)
from otm.financial.http import guarded
from otm.financial.normalization import normalize
from otm.financial.records import current_records, decode_collection, decode_snapshot
from otm.financial.service import CostCollections, CostConflict
from otm.financial.worker import CostCollectionWorker, cost_intent
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.budget import BudgetReadUnavailable
from otm.providers.budget_simulator import SimulatedBudgetFacade
from otm.storage.admission import RequestConflict

__all__ = ["drift_case", "update_case"]


# Prepare real closed contracts and replace only persistence/I/O boundaries for unit branch
# coverage.
@pytest.fixture
def cost_case(drift_case):
    c = drift_case
    e = example()
    c.profile = CostPolicy(retry_delays_seconds=(1, 1))
    c.target = CostTarget(
        configuration=c.target,
        budget_ocid=c.target.bindings["budget"],
        source_access_binding_id=c.policy.access_binding_id,
        profile=c.profile,
        period_start=e.target.period_start,
        period_end=e.target.period_end,
    )
    c.intent = CostIntent(
        workspace_id=c.policy.workspace_id,
        administrator_id=c.grant["id"],
        authorization_revision=c.grant["authorization_revision"],
        targets=(c.target,),
        target=ConfigurationOperationTarget(
            tenancy_ocid=c.row["tenancy_ocid"], display_name=c.row["name"]
        ),
    )
    payload = IntentEventData(intent=c.intent, actor=c.actor.actor).model_dump(mode="json")
    c.operation.update(
        intent_data=payload, intent_hash=canonical_hash(payload), current_intent_revision=1
    )
    c.row["name"] = "Example child"
    c.facade = SimulatedBudgetFacade(c.policy)
    c.result = c.facade.read_managed_budget(
        c.target, c.row["configuration_observation"]["budget"], NOW
    )
    data = c.target.model_dump(mode="json")
    c.collection = dict(
        id=uuid4(),
        workspace_id=c.policy.workspace_id,
        tenancy_id=c.target.configuration.tenancy_id,
        operation_id=c.operation["id"],
        context=data,
        context_hash=canonical_hash(data),
        source_hash=target_source(c.target),
        failure_scope_hash=failure_source(c.target),
        state="reading",
        attempts=1,
        attempt_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
        next_attempt_at=None,
        safe_code=None,
    )
    c.engine = Mock()
    c.engine.begin.side_effect = lambda: nullcontext(c.connection)
    c.engine.connect.side_effect = lambda: nullcontext(c.connection)
    c.worker = CostCollectionWorker(
        c.engine,
        c.policy.workspace_id,
        Mock(return_value=NOW),
        c.loader,
        c.facade,
        c.queue,
        profile=c.profile,
    )
    c.service = CostCollections(
        c.store, policy=c.policy, policy_loader=c.loader, enqueuer=c.queue, profile=c.profile
    )
    c.store.clock.return_value = NOW
    return c


# Build retained query columns from a normalized response so each integrity fence can be broken
# alone.
def observed(c):
    snap = normalize(c.target, c.result, NOW)
    return dict(
        collection_context=c.collection["context"],
        tenancy_id=c.collection["tenancy_id"],
        context_hash=c.collection["context_hash"],
        source_hash=c.collection["source_hash"],
        snapshot=snap.model_dump(mode="json"),
        snapshot_hash=canonical_hash(snap.model_dump(mode="json")),
        budget_ocid=snap.budget_ocid,
        captured_at=snap.retrieved_at,
        time_spend_computed=snap.computed_at,
        period_start=snap.period_start,
        period_end=snap.period_end,
        currency=snap.currency,
        observed_budget_amount=Decimal(snap.budget),
        actual_spend=Decimal(snap.actual),
        forecasted_spend=Decimal(snap.forecast),
    ), snap


# Stored context, source and snapshot integrity are independently checked before dashboard
# projection.
def test_stored_integrity_and_query_selection(cost_case):
    c = cost_case
    assert decode_collection(c.collection) == c.target
    row, snapshot = observed(c)
    assert decode_snapshot(row) == snapshot
    for key, value in [
        ("context_hash", "0" * 64),
        ("source_hash", "0" * 64),
        ("tenancy_id", uuid4()),
    ]:
        with pytest.raises(ValueError):
            decode_collection({**c.collection, key: value})
        with pytest.raises(ValueError):
            decode_snapshot({**row, key: value})
    for key, value in [
        ("snapshot_hash", "0" * 64),
        ("actual_spend", Decimal(2)),
        ("budget_ocid", "wrong"),
        ("captured_at", NOW + timedelta(seconds=1)),
        ("currency", None),
    ]:
        with pytest.raises(ValueError):
            decode_snapshot({**row, key: value})
    assert current_records(c.connection, c.policy.workspace_id, set()) == ({}, {})
    c.connection.execute.side_effect = [
        Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[c.collection])))),
        Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[row])))),
    ]
    facts, heads = current_records(
        c.connection, c.policy.workspace_id, {c.collection["source_hash"]}
    )
    assert facts[row["tenancy_id"]][1] == snapshot and heads[row["tenancy_id"]] == c.collection


# Unit admission branches preserve receipt identity and join compatible work; SQL tests prove
# atomicity.
def test_admission_receipts_join_and_fixed_conflicts(cost_case):
    c = cost_case
    command = CostRefreshRequest(client_request_key=uuid4(), tenancy_id=c.row["id"])
    c.connection.scalar.return_value = None
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    c.connection.execute.return_value.mappings.return_value.all.return_value = [c.row]
    c.connection.execute.return_value.mappings.return_value.one.return_value = c.grant
    with patch("otm.financial.service.capture_target", return_value=c.target.configuration):
        receipt = c.service.start(c.actor, command)
    assert receipt.accepted_count == 1 and receipt.joined_count == 0
    c.queue.enqueue.assert_called_once()
    payload = dict(
        request_hash=canonical_hash(command.model_dump(mode="json")),
        receipt=receipt.model_dump(mode="json"),
    )
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = dict(
        data=payload, data_hash=canonical_hash(payload)
    )
    assert c.service.start(c.actor, command) == receipt
    with pytest.raises(RequestConflict):
        c.service.start(c.actor, command.model_copy(update={"tenancy_id": None}))
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = dict(
        data=payload, data_hash="0" * 64
    )
    with pytest.raises(ValueError):
        c.service.start(c.actor, command)
    # First lookup is command receipt, second is an active child collection.
    c.connection.execute.side_effect = None
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        None,
        c.collection,
    ]
    with patch("otm.financial.service.capture_target", return_value=c.target.configuration):
        assert (
            c.service.start(
                c.actor, command.model_copy(update={"client_request_key": uuid4()})
            ).joined_count
            == 1
        )
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = None
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    c.connection.scalar.return_value = uuid4()
    with pytest.raises(RequestConflict):
        c.service.start(c.actor, command)
    c.connection.scalar.return_value = None
    c.loader.return_value.execution_paused = True
    with pytest.raises(CostConflict):
        c.service.start(c.actor, command)
    c.loader.return_value.execution_paused = False
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    with pytest.raises(CostConflict, match="COST_TARGET_NOT_FOUND"):
        c.service.start(c.actor, command)
    with pytest.raises(CostConflict, match="NO_COST_REFRESH_TARGETS"):
        c.service.start(c.actor, command.model_copy(update={"tenancy_id": None}))
    c.connection.execute.return_value.mappings.return_value.all.return_value = [
        {**c.row, "operation_id": uuid4()}
    ]
    with pytest.raises(CostConflict):
        c.service.start(c.actor, command)


# Summaries are two scoped stored-data reads, and live policy changes cannot claim a fresh
# current source.
def test_summaries_health_and_deployment_pause(cost_case):
    c = cost_case
    row, snapshot = observed(c)
    with patch(
        "otm.financial.service.current_records",
        return_value=({c.row["id"]: (row, snapshot)}, {c.row["id"]: c.collection}),
    ):
        view = c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[c.row["id"]]
        assert view.pending and view.can_refresh and view.state == "current"
        c.collection.update(state="failed", safe_code="COST_RETRIES_EXHAUSTED")
        assert (
            c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[c.row["id"]].state
            == "unavailable"
        )
        c.collection.update(state="succeeded", safe_code="COST_SOURCE_UNQUALIFIED")
        assert (
            c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[c.row["id"]].state
            == "unqualified"
        )
        c.row["monthly_budget_override_amount"] = "500.0000"
        assert (
            c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[
                c.row["id"]
            ].desired_budget
            == "500.0000"
        )
        c.loader.return_value.execution_paused = True
        assert not c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[
            c.row["id"]
        ].can_refresh
        c.loader.return_value.policy = None
        assert (
            c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[c.row["id"]].state
            == "not_collected"
        )
    c.service.policy = None
    assert not c.service.available()
    c.service.policy = c.policy
    c.service.policy_loader = None
    assert c.service.available()


# Decode exact frozen intent before credential resolution; corruption and wrong workspace/actor
# fail closed.
def test_worker_intent_locks_and_live_authority(cost_case):
    c = cost_case
    assert cost_intent(c.operation).intent == c.intent
    for key, value in [
        ("intent_hash", "0" * 64),
        ("workspace_id", "other"),
        ("initiating_actor_subject", "other"),
    ]:
        with pytest.raises(ValueError):
            cost_intent({**c.operation, key: value})
    with pytest.raises(ValueError):
        c.intent.model_copy(update={"targets": (c.target, c.target)}).__class__.model_validate_json(
            c.intent.model_copy(update={"targets": (c.target, c.target)}).model_dump_json()
        )
    c.connection.scalar.return_value = uuid4()
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.operation
    assert c.worker._locked(c.connection, c.operation["id"]) == c.operation
    c.connection.scalar.return_value = None
    assert c.worker._locked(c.connection, c.operation["id"]) is None
    c.connection.scalar.return_value = uuid4()
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    assert c.worker._locked(c.connection, c.operation["id"]) is None
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
    assert c.worker._problem(c.connection, c.operation, c.target, c.row, NOW) is None
    c.grant["status"] = "revoked"
    assert (
        c.worker._problem(c.connection, c.operation, c.target, c.row, NOW)
        == "COST_AUTHORIZATION_CHANGED"
    )
    c.grant["status"] = "active"
    c.loader.return_value.execution_paused = True
    assert (
        c.worker._problem(c.connection, c.operation, c.target, c.row, NOW)
        == "COST_CONTEXT_UNAVAILABLE"
    )
    c.loader.return_value.execution_paused = False
    assert (
        c.worker._problem(c.connection, c.operation, c.target, None, NOW) == "COST_TARGET_CHANGED"
    )
    assert (
        c.worker._problem(c.connection, c.operation, c.target, c.row, NOW + timedelta(days=32))
        == "COST_TARGET_CHANGED"
    )
    c.worker.profile_loader = lambda: CostPolicy(source_max_age_seconds=1)
    assert (
        c.worker._problem(c.connection, c.operation, c.target, c.row, NOW)
        == "COST_CONTEXT_UNAVAILABLE"
    )


# Run dispatches the GET without persistence mocks holding an open transaction and maps every
# safe outcome.
@pytest.mark.parametrize(
    "case,expected",
    [
        ("success", "COST_READ_COMPLETE"),
        ("missing", "COST_READ_UNAVAILABLE"),
        ("changed", "COST_TARGET_CHANGED"),
        ("invalid", "COST_SOURCE_UNQUALIFIED"),
        ("unknown", "COST_READ_UNAVAILABLE"),
        ("unqualified", "COST_SOURCE_UNQUALIFIED"),
        ("old", "COST_SOURCE_UNQUALIFIED"),
        ("wrong_type", "COST_SOURCE_UNQUALIFIED"),
        ("blocked", "COST_CONTEXT_UNAVAILABLE"),
    ],
)
def test_worker_dispatch_outcomes(cost_case, case, expected):
    c = cost_case
    c.connection.scalars.return_value = [c.collection["id"]]
    result = c.result
    if case == "unqualified":
        result = result.model_copy(update={"time_spend_computed": None})
    if case == "old":
        result = result.model_copy(
            update={
                "captured_at": NOW - timedelta(seconds=1),
                "time_spend_computed": NOW - timedelta(seconds=1),
            }
        )
    if case == "wrong_type":
        result = {}
    facade = Mock(policy=c.policy)
    error = {
        "missing": BudgetReadUnavailable("safe"),
        "changed": ValueError("COST_TARGET_CHANGED"),
        "invalid": ValueError("bad"),
        "unknown": RuntimeError("private"),
    }.get(case)
    facade.read_managed_budget.side_effect = error
    facade.read_managed_budget.return_value = result
    c.worker.facade = facade
    with (
        patch.object(
            c.worker,
            "_prepare",
            return_value=(
                c.collection,
                c.target,
                {},
                "COST_CONTEXT_UNAVAILABLE" if case == "blocked" else None,
            ),
        ),
        patch.object(c.worker, "_finish") as finish,
        patch.object(c.worker, "_progress"),
    ):
        c.worker.run(c.operation["id"])
        assert finish.call_args.args[-1] == expected
        if case == "old":
            assert finish.call_args.args[-2] is None
    with (
        patch.object(c.worker, "_prepare", return_value=None),
        patch.object(c.worker, "_finish") as finish,
        patch.object(c.worker, "_progress"),
    ):
        c.worker.run(c.operation["id"])
        finish.assert_not_called()


# Claim paths stop terminal/future deliveries, fence orphan intent targets, and bound abandoned
# attempts.
def test_worker_prepare_paths(cost_case):
    c = cost_case
    with patch.object(c.worker, "_locked", return_value=None):
        assert c.worker._prepare(c.operation["id"], c.collection["id"]) is None
    with (
        patch.object(c.worker, "_locked", return_value=c.operation),
        patch.object(c.worker, "_problem", return_value=None),
    ):
        c.connection.execute.return_value.mappings.return_value.one.side_effect = lambda: (
            c.collection
        )
        c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = lambda: (
            c.row
        )
        c.collection["state"] = "succeeded"
        assert c.worker._prepare(c.operation["id"], c.collection["id"]) is None
        c.collection.update(state="retry", next_attempt_at=NOW + timedelta(seconds=2))
        assert c.worker._prepare(c.operation["id"], c.collection["id"]) is None
        c.collection.update(state="reading", next_attempt_at=None)
        result = c.worker._prepare(c.operation["id"], c.collection["id"])
        assert result[0]["attempts"] == 2 and result[3] is None
        c.collection["attempts"] = 3
        with patch.object(c.worker, "_record") as record:
            c.worker._prepare(c.operation["id"], c.collection["id"])
            assert record.call_args.args[3:5] == ("failed", "COST_RETRIES_EXHAUSTED")
        c.collection["attempts"] = 1
        with (
            patch(
                "otm.financial.worker.decode_collection",
                return_value=c.target.model_copy(update={"budget_ocid": "wrong"}),
            ),
            pytest.raises(ValueError),
        ):
            c.worker._prepare(c.operation["id"], c.collection["id"])


# Unit finish branches check attempt and authority; SQL tests prove coherent atomic persistence.
@pytest.mark.parametrize(
    "state,code,problem",
    [
        ("succeeded", "COST_READ_COMPLETE", None),
        ("retry", "COST_READ_UNAVAILABLE", None),
        ("failed", "COST_READ_UNAVAILABLE", None),
        ("superseded", "COST_READ_COMPLETE", "COST_TARGET_CHANGED"),
        ("succeeded", "COST_SOURCE_UNQUALIFIED", None),
    ],
)
def test_worker_finish_outcome_paths(cost_case, state, code, problem):
    c = cost_case
    if state == "failed":
        c.collection["attempts"] = 3
    with (
        patch.object(c.worker, "_locked", return_value=c.operation),
        patch.object(c.worker, "_problem", return_value=problem),
        patch.object(c.worker, "_record") as record,
    ):
        c.connection.execute.return_value.mappings.return_value.one.return_value = c.collection
        c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.row
        c.worker._finish(
            c.operation["id"], c.collection, c.target, normalize(c.target, c.result, NOW), code
        )
        assert record.call_args.args[3] == state
        c.worker._finish(
            c.operation["id"], {**c.collection, "attempt_id": uuid4()}, c.target, None, code
        )
        assert record.call_count == 1
    with patch.object(c.worker, "_locked", return_value=None):
        c.worker._finish(c.operation["id"], c.collection, c.target, None, code)


# Safe outcome persistence and native ETA retry keep jobs read-only without erasing completed peers.
def test_worker_record_and_progress(cost_case):
    c = cost_case
    c.worker._record(
        c.connection, c.operation, c.collection, "succeeded", "COST_READ_COMPLETE", NOW
    )
    c.worker._record(
        c.connection,
        c.operation,
        c.collection,
        "retry",
        "COST_READ_UNAVAILABLE",
        NOW,
        due=NOW + timedelta(seconds=1),
    )
    c.worker._record(
        c.connection, c.operation, c.collection, "failed", "COST_RETRIES_EXHAUSTED", NOW
    )
    with patch.object(c.worker, "_locked", return_value=c.operation):
        for state in ["succeeded", "failed", "retry"]:
            c.connection.execute.return_value.mappings.return_value.all.return_value = [
                {**c.collection, "state": state, "next_attempt_at": NOW + timedelta(seconds=1)}
            ]
            c.worker._progress(c.operation["id"])
        c.queue.enqueue.assert_called()
    with patch.object(c.worker, "_locked", return_value=None):
        c.worker._progress(c.operation["id"])


# HTTP boundaries reflect neither malformed stored context nor provider exception text.
@pytest.mark.parametrize(
    "error,status",
    [
        (CostConflict("COST_TARGET_NOT_FOUND"), 404),
        (CostConflict("private"), 409),
        (RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT"), 409),
        (ValueError("private"), 400),
        (RuntimeError("private"), 503),
    ],
)
def test_http_error_redaction(error, status):
    assert guarded(Mock(side_effect=error)).status_code == status
    assert b"private" not in guarded(Mock(side_effect=error)).body
    assert guarded(lambda: 1) == 1
