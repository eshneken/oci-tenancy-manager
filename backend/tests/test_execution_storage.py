"""Adapter boundary unit tests; disposable PostgreSQL separately proves real SQL behavior."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_admission_service import NOW, admission
from test_execution import execution_case

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.operations.execution_contracts import InspectionOutcome
from otm.providers.inspection_contracts import InspectTenancy
from otm.storage.execution import SqlExecutionStore

__all__ = ["admission", "execution_case"]


# Stub IO only; transaction/constraint/concurrency claims require real PG evidence.
@pytest.fixture
def execution_db():
    connection = MagicMock()
    engine = Mock(
        connect=Mock(return_value=nullcontext(connection)),
        begin=Mock(return_value=nullcontext(connection)),
    )
    return SimpleNamespace(connection=connection, engine=engine, store=SqlExecutionStore(engine))


# Arrange the validated intent and its exact selected operation head.
def committed_rows(case):
    c = case.committed
    data = IntentEventData(intent=c.intent, actor=c.actor).model_dump(mode="json")
    op = dict(
        id=c.operation_id,
        workspace_id=c.intent.workspace_id,
        kind="inspect_import",
        state="queued",
        revision=c.operation_revision,
        current_intent_revision=c.intent_revision,
        current_intent_event_id=c.intent_event_id,
        initiating_actor_subject=c.actor.key,
        initiating_actor_snapshot=c.actor.model_dump(mode="json"),
    )
    event = dict(
        id=c.intent_event_id,
        data=data,
        data_hash=canonical_hash(data),
        intent_revision=c.intent_revision,
        actor_subject=c.actor.key,
    )
    return op, event


# Represent one selected step; SQL filtering is verified in actual database regressions.
def row_step(case, **changes):
    return dict(
        inputs=case.committed.intent.model_dump(mode="json"),
        intent_event_id=case.committed.intent_event_id,
        execution_generation=1,
        attempt_number=1,
        state="running",
        current_attempt_id=case.attempt.context.attempt_id,
        **changes,
    )


# Obtain a real paired simulator result, not a hand-built success dictionary.
def checked_outcome(case):
    result = case.inspection.service.inspect(
        InspectTenancy(
            contract_version="execution-1-draft",
            kind="inspect_tenancy",
            context=case.attempt.context,
            payload=case.committed.intent.target,
        )
    )
    return InspectionOutcome(
        context=case.attempt.context,
        intent_event_id=case.committed.intent_event_id,
        safe_code=result.safe_code,
        result=result,
    )


# Terminal/unowned delivery does not inspect another event or create progress.
@pytest.mark.parametrize("state", [None, "succeeded", "needs_attention"])
def test_load_missing_or_nonrunnable_work_without_followup_query(execution_db, state):
    io = execution_db
    io.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        None if state is None else {"state": state}
    )
    assert io.store.load(uuid4()) is None
    assert io.connection.execute.call_count == 1


# A closed snapshot and canonical hash reconstruct the expected current intent.
def test_load_validates_immutable_snapshot(execution_db, execution_case):
    op, event = committed_rows(execution_case)
    result = execution_db.connection.execute.return_value.mappings.return_value
    result.one_or_none.return_value = op
    result.one.return_value = event
    assert execution_db.store.load(op["id"]) == execution_case.committed


# Reject mismatched persisted identity/evidence with a fixed error, not raw stored data.
@pytest.mark.parametrize(
    "damage", ["hash", "workspace", "actor", "snapshot", "event_actor", "kind", "shape"]
)
def test_corrupt_committed_intent_never_reaches_provider(execution_db, execution_case, damage):
    op, event = committed_rows(execution_case)
    if damage == "hash":
        event["data_hash"] = "0" * 64
    elif damage == "workspace":
        op["workspace_id"] = "other"
    elif damage == "actor":
        op["initiating_actor_subject"] = "other"
    elif damage == "snapshot":
        op["initiating_actor_snapshot"] = {}
    elif damage == "event_actor":
        event["actor_subject"] = "other"
    elif damage == "kind":
        op["kind"] = "other"
    else:
        event["data"] = {"raw": "private-example"}
    result = execution_db.connection.execute.return_value.mappings.return_value
    result.one_or_none.return_value = op
    result.one.return_value = event
    with pytest.raises(ValueError, match="^INVALID_COMMITTED_INSPECTION$") as error:
        execution_db.store.load(op["id"])
    assert error.value.__suppress_context__


# New and interrupted reads retain the same intent and commit dispatch evidence.
@pytest.mark.parametrize("existing", [False, True])
def test_claim_retains_inputs_and_advances_only_read_attempt_state(
    execution_db, execution_case, existing
):
    io, case = execution_db, execution_case
    io.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        {"state": "running"},
        row_step(case) if existing else None,
    ]
    with patch("otm.storage.execution.require_transaction") as guard:
        attempt = io.store.claim(case.committed, case.grant, NOW)
    guard.assert_called_once_with(io.connection)
    assert attempt.context.execution_generation == (2 if existing else 1)
    assert attempt.operation_revision == case.committed.operation_revision + 1
    assert attempt.context.access_binding_id == case.grant.access_binding_id
    assert io.connection.execute.call_count == 5


# The losing claimant cannot insert a step or append dispatch evidence.
def test_claim_losing_revision_race_is_read_only(execution_db, execution_case):
    execution_db.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        None
    )
    with patch("otm.storage.execution.require_transaction"):
        assert execution_db.store.claim(execution_case.committed, execution_case.grant, NOW) is None
    assert execution_db.connection.execute.call_count == 1


# Persistence cannot accidentally consume a differently scoped dispatch grant.
@pytest.mark.parametrize(
    "field", ["workspace_id", "actor_key", "policy_revision", "access_binding_id"]
)
def test_claim_scope_rejection_precedes_transaction(execution_db, execution_case, field):
    value = "other" if field in {"workspace_id", "actor_key"} else uuid4()
    grant = execution_case.grant.model_copy(update={field: value})
    with pytest.raises(ValueError, match="DISPATCH_SCOPE_MISMATCH"):
        execution_db.store.claim(execution_case.committed, grant, NOW)
    execution_db.engine.begin.assert_not_called()


# A corrupted or retargeted logical step blocks the read rather than being rewritten.
def test_claim_cannot_rewrite_existing_step_inputs(execution_db, execution_case):
    step = row_step(execution_case)
    step["inputs"] = {}
    execution_db.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        {},
        step,
    ]
    with patch("otm.storage.execution.require_transaction"):
        with pytest.raises(ValueError, match="IMMUTABLE_STEP_INPUT_MISMATCH"):
            execution_db.store.claim(execution_case.committed, execution_case.grant, NOW)
    assert execution_db.connection.execute.call_count == 2


# Only a paired confirmed read verifies; pre-dispatch denial never invents a step.
@pytest.mark.parametrize("mode", ["confirmed", "unresolved", "denied_before_claim"])
def test_publication_updates_audit_and_step_in_one_supplied_transaction(
    execution_db, execution_case, mode
):
    io, case = execution_db, execution_case
    result = (
        checked_outcome(case)
        if mode == "confirmed"
        else InspectionOutcome(
            context=None if mode == "denied_before_claim" else case.attempt.context,
            intent_event_id=case.committed.intent_event_id,
            safe_code="DISPATCH_NOT_AUTHORIZED",
            result=None,
        )
    )
    attempt = None if mode == "denied_before_claim" else case.attempt
    io.connection.execute.return_value.mappings.return_value.one_or_none.return_value = {}
    io.connection.execute.return_value.mappings.return_value.one.return_value = row_step(case)
    with patch("otm.storage.execution.require_transaction"):
        assert io.store.finish(case.committed, attempt, result, NOW) is True
    assert io.connection.execute.call_count == (3 if attempt is None else 5)


# Superseded or closed work loses before audit/state mutation.
@pytest.mark.parametrize("guard", ["revision", "state", "attempt", "generation"])
def test_late_publication_never_appends_outcome(execution_db, execution_case, guard):
    io, case = execution_db, execution_case
    io.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        None if guard == "revision" else {}
    )
    step = row_step(case)
    if guard == "state":
        step["state"] = "verified"
    elif guard == "attempt":
        step["current_attempt_id"] = uuid4()
    elif guard == "generation":
        step["execution_generation"] = 2
    io.connection.execute.return_value.mappings.return_value.one.return_value = step
    with patch("otm.storage.execution.require_transaction"):
        assert io.store.finish(case.committed, case.attempt, checked_outcome(case), NOW) is False
    assert io.connection.execute.call_count == (1 if guard == "revision" else 2)


# A result cannot be attached to an unrelated intent or invented pre-claim confirmation.
@pytest.mark.parametrize("field", ["intent_event_id", "context", "committed", "unclaimed_result"])
def test_outcome_pairing_rejects_mismatched_publication_before_transaction(
    execution_db, execution_case, field
):
    case = execution_case
    result = checked_outcome(case)
    attempt = case.attempt
    if field == "intent_event_id":
        result = result.model_copy(update={"intent_event_id": uuid4()})
    elif field == "context":
        result = result.model_copy(update={"context": None})
    elif field == "committed":
        attempt = attempt.model_copy(
            update={"committed": case.committed.model_copy(update={"operation_revision": 9})}
        )
    else:
        attempt = None
        result = result.model_copy(update={"context": None})
    with pytest.raises(ValueError, match="OUTCOME_SCOPE_MISMATCH"):
        execution_db.store.finish(case.committed, attempt, result, NOW)
    execution_db.engine.begin.assert_not_called()


# Persistence cannot let a database timezone reinterpret an unqualified timestamp.
@pytest.mark.parametrize("boundary", ["claim", "finish"])
def test_naive_clock_is_rejected_before_opening_write_transaction(
    execution_db, execution_case, boundary
):
    from pydantic import ValidationError

    case = execution_case
    with pytest.raises(ValidationError):
        if boundary == "claim":
            execution_db.store.claim(case.committed, case.grant, NOW.replace(tzinfo=None))
        else:
            execution_db.store.finish(
                case.committed, case.attempt, checked_outcome(case), NOW.replace(tzinfo=None)
            )
    execution_db.engine.begin.assert_not_called()


# A caller cannot attach another read's result even if its outer attempt context is correct.
@pytest.mark.parametrize(
    "damage", ["attempt", "code", "child", "parent", "organization", "self_parent"]
)
def test_publication_rechecks_result_pairing_before_writes(execution_db, execution_case, damage):
    case = execution_case
    outcome = checked_outcome(case)
    result = outcome.result
    if damage == "attempt":
        result = result.model_copy(update={"attempt_id": uuid4()})
    elif damage == "code":
        outcome = outcome.model_copy(update={"safe_code": "READ_TIMEOUT"})
    elif damage == "self_parent":
        result = result.model_copy(
            update={
                "tenancy": result.tenancy.model_copy(
                    update={"parent_tenancy_ocid": result.tenancy.tenancy_ocid}
                )
            }
        )
    else:
        field = {
            "child": "tenancy_ocid",
            "parent": "parent_tenancy_ocid",
            "organization": "organization_id",
        }[damage]
        value = "other-organization" if damage == "organization" else "ocid1.tenancy.oc1..other"
        result = result.model_copy(
            update={"tenancy": result.tenancy.model_copy(update={field: value})}
        )
    outcome = outcome.model_copy(update={"result": result})
    with pytest.raises(ValueError, match="OUTCOME_(RESULT|TARGET)_MISMATCH"):
        execution_db.store.finish(case.committed, case.attempt, outcome, NOW)
    execution_db.engine.begin.assert_not_called()
