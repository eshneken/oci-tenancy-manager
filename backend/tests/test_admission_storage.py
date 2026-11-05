"""Database-adapter unit contracts; real SQL constraints/rollback are tested in disposable PG."""

from contextlib import nullcontext
from datetime import timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from test_admission_service import NOW, admission

from otm.operations.contracts import Acceptance
from otm.storage.admission import RequestConflict, SqlAdmissionStore, receipt
from otm.storage.enqueue import INSPECTION_TASK, OPERATIONS_QUEUE, InspectionEnqueuer
from otm.storage.transaction import require_transaction

# Re-export the fixture for this module; data is real typed domain input, never a database mock.
__all__ = ["admission"]


# Stub IO/results only; do not claim this proves PostgreSQL filtering or transactions.
@pytest.fixture
def database_adapter():
    connection = MagicMock()
    engine = Mock(
        connect=Mock(return_value=nullcontext(connection)),
        begin=Mock(return_value=nullcontext(connection)),
    )
    enqueuer = Mock()
    return SimpleNamespace(
        connection=connection,
        engine=engine,
        enqueuer=enqueuer,
        store=SqlAdmissionStore(engine, enqueuer),
    )


# Arrange an already-selected compatible database receipt with an explicit aware timestamp.
def row_for(admission, **changes):
    return {
        "id": admission.accepted.operation_id,
        "state": "queued",
        "accepted_at": NOW,
        "request_digest": admission.request.digest,
        **changes,
    }


# Read adapter preserves missing vs accepted outcomes without enqueueing work.
@pytest.mark.parametrize("found", [True, False])
def test_scoped_lookup_returns_compatible_receipt_or_none(database_adapter, admission, found):
    result = database_adapter.connection.execute.return_value
    result.mappings.return_value.one_or_none.return_value = row_for(admission) if found else None
    result = database_adapter.store.find(admission.request, admission.actor)
    assert result == (admission.accepted if found else None)
    database_adapter.enqueuer.enqueue.assert_not_called()


# A reused key must match input; database timezone formatting cannot alter the instant.
def test_incompatible_digest_is_rejected_and_database_time_is_normalized(admission):
    with pytest.raises(RequestConflict, match="REQUEST_KEY_REUSED"):
        receipt(row_for(admission, request_digest="different"), admission.request.digest)
    local = NOW.astimezone(timezone(timedelta(hours=1)))
    assert (
        receipt(row_for(admission, accepted_at=local), admission.request.digest).accepted_at == NOW
    )


# Queue the same reference on the caller transaction and return it after exit.
def test_insert_passes_same_connection_and_identifier_to_enqueuer(database_adapter, admission):
    database_adapter.connection.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with patch("otm.storage.admission.require_transaction") as guard:
        result = database_adapter.store.insert(
            admission.request, admission.actor, admission.intent, NOW
        )
    guard.assert_called_once_with(database_adapter.connection)
    assert isinstance(result, Acceptance) and result.state == "queued"
    database_adapter.enqueuer.enqueue.assert_called_once_with(
        database_adapter.connection, result.operation_id
    )
    assert database_adapter.connection.execute.call_count == 2


# A uniqueness winner is recovered or rejected without another audit insertion/enqueue.
@pytest.mark.parametrize("winner", ["compatible", "conflict", "missing"])
def test_lost_insert_race_never_creates_a_second_intent_or_job(database_adapter, admission, winner):
    database_adapter.connection.execute.return_value.scalar_one_or_none.return_value = None
    row = (
        None
        if winner == "missing"
        else row_for(
            admission,
            request_digest="different" if winner == "conflict" else admission.request.digest,
        )
    )
    result = database_adapter.connection.execute.return_value
    result.mappings.return_value.one_or_none.return_value = row
    with patch("otm.storage.admission.require_transaction"):
        if winner == "compatible":
            assert (
                database_adapter.store.insert(
                    admission.request, admission.actor, admission.intent, NOW
                )
                == admission.accepted
            )
        else:
            with pytest.raises(RequestConflict if winner == "conflict" else RuntimeError):
                database_adapter.store.insert(
                    admission.request, admission.actor, admission.intent, NOW
                )
    database_adapter.enqueuer.enqueue.assert_not_called()


# Reject mismatched snapshots even when an internal caller bypasses service checks.
@pytest.mark.parametrize("fault", ["workspace", "target", "parent"])
def test_invalid_intent_scope_rejects_before_transaction(database_adapter, admission, fault):
    intent = admission.intent
    if fault == "workspace":
        intent = intent.model_copy(update={"workspace_id": "other-org"})
    else:
        field = "tenancy_ocid" if fault == "target" else "parent_tenancy_ocid"
        value = "ocid1.tenancy.oc1..other" if fault == "target" else admission.request.tenancy_ocid
        intent = intent.model_copy(
            update={"target": intent.target.model_copy(update={field: value})}
        )
    with pytest.raises(ValueError, match="INTENT_SCOPE"):
        database_adapter.store.insert(admission.request, admission.actor, intent, NOW)
    database_adapter.engine.begin.assert_not_called()


# A naive timestamp cannot create accepted evidence with an ambiguous time basis.
def test_bad_clock_rejects_before_any_database_write(database_adapter, admission):
    with pytest.raises(ValidationError):
        database_adapter.store.insert(
            admission.request, admission.actor, admission.intent, NOW.replace(tzinfo=None)
        )
    database_adapter.engine.begin.assert_not_called()


# An exception at the transaction exit propagates even after an enqueue call returned.
def test_failed_commit_does_not_return_acceptance(database_adapter, admission):
    transaction = MagicMock(__enter__=Mock(return_value=database_adapter.connection))
    transaction.__exit__.side_effect = RuntimeError("controlled commit failure")
    database_adapter.engine.begin.return_value = transaction
    database_adapter.connection.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with (
        patch("otm.storage.admission.require_transaction"),
        pytest.raises(RuntimeError, match="controlled commit"),
    ):
        database_adapter.store.insert(admission.request, admission.actor, admission.intent, NOW)


# Only the qualified native, non-autocommit READ COMMITTED connection is accepted.
@pytest.mark.parametrize(
    "fault", [None, "no_transaction", "wrong_driver", "autocommit", "isolation"]
)
def test_transaction_mode_is_checked_before_writes(fault):
    raw = Mock(spec=psycopg.Connection, autocommit=False)
    connection = MagicMock()
    connection.connection.driver_connection = raw
    connection.in_transaction.return_value = True
    connection.get_isolation_level.return_value = "READ COMMITTED"
    if fault == "no_transaction":
        connection.in_transaction.return_value = False
    elif fault == "wrong_driver":
        connection.connection.driver_connection = object()
    elif fault == "autocommit":
        raw.autocommit = True
    elif fault == "isolation":
        connection.get_isolation_level.return_value = "SERIALIZABLE"
    if fault:
        with pytest.raises(RuntimeError, match="ACTIVE_READ_COMMITTED"):
            require_transaction(connection)
    else:
        assert require_transaction(connection) is raw
    connection.execute.assert_not_called()
    raw.commit.assert_not_called()


# No pool/second transaction or arbitrary actor/SDK/credential payload is introduced.
def test_native_enqueue_has_fixed_capability_and_reference_only_payload():
    app, connection, raw = Mock(), Mock(), object()
    identifier = uuid4()
    with (
        patch("otm.storage.enqueue.procrastinate.App", return_value=app),
        patch("otm.storage.enqueue.require_transaction", return_value=raw),
    ):
        adapter = InspectionEnqueuer()
        adapter.enqueue(connection, identifier)
    app.configure_task.assert_called_once_with(
        INSPECTION_TASK,
        allow_unknown=True,
        queue=OPERATIONS_QUEUE,
        connection=raw,
        lock="operation:" + str(identifier),
        schedule_in=None,
    )
    app.configure_task.return_value.defer.assert_called_once_with(operation_id=str(identifier))
    with patch("otm.storage.enqueue.require_transaction", return_value=raw):
        adapter.enqueue(connection, identifier, delay_seconds=30)
    assert app.configure_task.call_args.kwargs["schedule_in"] == {"seconds": 30}
    app.open.assert_not_called()
    connection.commit.assert_not_called()
