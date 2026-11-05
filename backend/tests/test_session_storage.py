"""Session adapter unit boundaries; PostgreSQL separately proves constraints and scope."""

from contextlib import nullcontext
from datetime import timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from test_admission_service import NOW
from test_sessions import session_case

from otm.storage.sessions import SqlSessionRepository

__all__ = ["session_case"]


# Stub IO without pretending mocks prove database constraints or transaction behavior.
@pytest.fixture
def session_db():
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    engine = Mock(
        connect=Mock(return_value=nullcontext(connection)),
        begin=Mock(return_value=nullcontext(connection)),
    )
    return SimpleNamespace(connection=connection, engine=engine, store=SqlSessionRepository(engine))


# Reconstruct UTC metadata without relabeling timestamps or returning raw claims.
@pytest.mark.parametrize("found", [False, True])
def test_lookup_normalizes_database_timezone_and_closed_snapshot(session_db, session_case, found):
    values = session_case.session.model_dump()
    for field in (
        "entitlement_checked_at",
        "auth_time",
        "created_at",
        "expires_at",
        "last_seen_at",
    ):
        values[field] = values[field].astimezone(timezone(timedelta(hours=2)))
    session_db.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        values if found else None
    )
    assert session_db.store.find(session_case.session.session_token_hash) == (
        session_case.session if found else None
    )


# Unexpected provider data is rejected rather than copied into an application principal.
def test_invalid_stored_snapshot_cannot_become_trusted_session(session_db, session_case):
    values = session_case.session.model_dump()
    values["display_snapshot"] = {"access_token": "private-example"}
    session_db.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        values
    )
    with pytest.raises(ValidationError):
        session_db.store.find(session_case.session.session_token_hash)


# Revoke by id/workspace/digest with no identifier interpolation or overwrite of first time.
def test_revocation_uses_bound_exact_scope_and_caller_transaction(session_db, session_case):
    value = "example-' OR '1'='1"
    with patch("otm.storage.sessions.require_transaction") as guard:
        session_db.store.revoke(
            session_case.session.id, session_case.session.session_token_hash, value, NOW
        )
    guard.assert_called_once_with(session_db.connection)
    query = session_db.connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert value not in str(query) and value in query.params.values()
    assert "revoked_at IS NULL" in str(query) and session_case.session.id in query.params.values()
    assert session_case.session.session_token_hash in query.params.values()


# A database timezone cannot silently interpret an unqualified revocation timestamp.
def test_revocation_rejects_naive_time_before_transaction(session_db, session_case):
    with pytest.raises(ValidationError):
        session_db.store.revoke(
            session_case.session.id,
            session_case.session.session_token_hash,
            session_case.session.workspace_id,
            NOW.replace(tzinfo=None),
        )
    session_db.engine.begin.assert_not_called()


# Persist activity only through an exact scoped conditional update, never an unconditional write.
@pytest.mark.parametrize("found", [True, False])
def test_activity_adapter_uses_live_predicate_and_server_time(session_db, session_case, found):
    row = session_case.session.model_dump() if found else None
    session_db.connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    with patch("otm.storage.sessions.require_transaction"):
        result = session_db.store.touch(session_case.session, NOW)
    assert result == (session_case.session if found else None)
    query = session_db.connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "greatest" in str(query) and "revoked_at IS NOT NULL" in str(query)
    assert "idle_timeout_seconds" in str(query) and session_case.session.id in query.params.values()


# Cleanup has a bounded locking select and only deletes operational session rows.
def test_cleanup_adapter_builds_skip_locked_bounded_delete(session_db):
    session_db.connection.execute.return_value.all.return_value = [(object(),), (object(),)]
    with patch("otm.storage.sessions.require_transaction"):
        assert session_db.store.purge_expired(NOW, 2) == 2
    query = session_db.connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "SKIP LOCKED" in str(query) and "LIMIT" in str(query)
    assert "DELETE FROM public.otm_admin_session" in str(query)


# Invalid cleanup bounds never open a write transaction.
@pytest.mark.parametrize("limit", [0, -1, 10001, True, "1"])
def test_cleanup_adapter_rejects_bad_limit(session_db, limit):
    with pytest.raises(ValueError, match="INVALID_SESSION_CLEANUP_LIMIT"):
        session_db.store.purge_expired(NOW, limit)
    session_db.engine.begin.assert_not_called()


# Logout records the first exact revocation in the same transaction without active-role lookup.
def test_revoke_records_closed_security_evidence(session_db, session_case):
    from uuid import uuid4

    results = [MagicMock(), MagicMock(), MagicMock()]
    results[0].mappings.return_value.one_or_none.return_value = session_case.session.model_dump()
    results[1].scalar_one.return_value = uuid4()
    session_db.connection.execute.side_effect = results
    with patch("otm.storage.sessions.require_transaction"):
        session_db.store.revoke(
            session_case.session.id,
            session_case.session.session_token_hash,
            session_case.session.workspace_id,
            NOW,
        )
    query = session_db.connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert query.params["kind"] == "session_logged_out"
    assert query.params["data"]["session_id"] == str(session_case.session.id)
    assert session_case.handle not in repr(query.params["data"])
