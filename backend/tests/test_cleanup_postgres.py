"""Real session cleanup, bounded concurrency and activity/revocation database regressions."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from database_helpers import seed_session_grant
from sqlalchemy import func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from test_admission_service import NOW
from test_sessions import session_case

from otm.auth.cleanup import cleanup_sessions
from otm.auth.service import SessionFailure, SessionService
from otm.settings import load_settings
from otm.storage.sessions import SqlSessionRepository
from otm.storage.tables import admin_session, audit_event, operation

pytestmark = pytest.mark.postgres
__all__ = ["session_case"]


# Insert only synthetic sessions directly; production still has no unqualified sign-in shortcut.
@pytest.fixture
def cleanup_case(pg_engine, session_case):
    # Retain issued/hosted thirty-minute policy independently of new laptop defaults.
    session_case.session = session_case.session.model_copy(update={"idle_timeout_seconds": 1800})
    with pg_engine.begin() as connection:
        seed_session_grant(connection, session_case.session.model_dump())
        connection.execute(admin_session.insert().values(**session_case.session.model_dump()))
    repository = SqlSessionRepository(pg_engine)
    session_case.authority.require_admin.return_value = session_case.grant.model_copy(
        update={"valid_until": NOW + timedelta(days=1)}
    )
    service = SessionService(
        repository, session_case.authority, session_case.session.issuer, session_case.clock
    )
    return SimpleNamespace(
        engine=pg_engine, repository=repository, service=service, case=session_case
    )


# Reuse exact insertion fields while giving each test row its own unguessable identity/digest.
def add_session(c, **changes):
    values = c.case.session.model_dump()
    values.update(id=uuid4(), session_token_hash=uuid4().hex + uuid4().hex)
    values.update(changes)
    with c.engine.begin() as connection:
        seed_session_grant(connection, values)
        connection.execute(admin_session.insert().values(**values))
    return values["id"]


# Query IDs/counts independently; no test concludes SQL scope from a mocked query string.
def ids(engine):
    with engine.connect() as connection:
        return set(connection.execute(select(admin_session.c.id)).scalars())


# Purge invalid sessions across workspaces while preserving live sessions and immutable history.
def test_cleanup_removes_only_idle_absolute_and_revoked_rows(cleanup_case):
    c = cleanup_case
    dead = [
        add_session(c, revoked_at=NOW),
        add_session(
            c,
            created_at=NOW - timedelta(hours=9),
            auth_time=NOW - timedelta(hours=9),
            entitlement_checked_at=NOW - timedelta(hours=9),
            last_seen_at=NOW - timedelta(seconds=1),
            expires_at=NOW,
        ),
        add_session(
            c,
            created_at=NOW - timedelta(hours=1),
            auth_time=NOW - timedelta(hours=1),
            entitlement_checked_at=NOW - timedelta(hours=1),
            last_seen_at=NOW - timedelta(seconds=1800),
            workspace_id="other-example-org",
        ),
    ]
    with c.engine.connect() as connection:
        counts = [
            connection.scalar(select(func.count()).select_from(table))
            for table in (operation, audit_event)
        ]
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    result = cleanup_sessions(c.repository, settings.sessions.cleanup, lambda: NOW)
    assert result.deleted >= 3 and not result.batch_limit_reached
    assert not set(dead) & ids(c.engine) and c.case.session.id in ids(c.engine)
    with c.engine.connect() as connection:
        assert counts == [
            connection.scalar(select(func.count()).select_from(table))
            for table in (operation, audit_event)
        ]
    assert c.repository.purge_expired(NOW, 500) == 0


# Activity respects database liveness and preserves issued policy and hard expiry.
def test_activity_extends_idle_but_not_absolute_and_polling_does_not(cleanup_case):
    c = cleanup_case
    c.case.clock.return_value = NOW + timedelta(minutes=20)
    principal = c.service.authenticate(c.case.handle)
    assert c.repository.find(c.case.session.session_token_hash).last_seen_at == NOW
    refreshed = c.service.activity(principal)
    assert refreshed.session.last_seen_at == NOW + timedelta(minutes=20)
    assert refreshed.session.expires_at == c.case.session.expires_at
    assert refreshed.session.idle_timeout_seconds == 1800
    c.case.clock.return_value = NOW + timedelta(minutes=50)
    with pytest.raises(SessionFailure) as error:
        c.service.authenticate(c.case.handle)
    assert error.value.status == 401
    assert c.repository.touch(refreshed.session, c.case.clock()) is None


# A stale principal cannot overwrite revocation or borrow a different target's live session.
@pytest.mark.parametrize("damage", ["revoked", "expired", "idle", "scope"])
def test_atomic_touch_rejects_invalid_or_mismatched_row(cleanup_case, damage):
    c = cleanup_case
    s = c.case.session
    with c.engine.begin() as connection:
        if damage == "revoked":
            connection.execute(
                update(admin_session).where(admin_session.c.id == s.id).values(revoked_at=NOW)
            )
    at = (
        s.expires_at
        if damage == "expired"
        else NOW + timedelta(seconds=1800)
        if damage == "idle"
        else NOW
    )
    if damage == "scope":
        s = s.model_copy(update={"workspace_id": "other"})
    assert c.repository.touch(s, at) is None


# A delayed earlier activity timestamp cannot move the shared idle timer backwards.
def test_out_of_order_activity_keeps_monotonic_last_seen(cleanup_case):
    c = cleanup_case
    updated = c.repository.touch(c.case.session, NOW + timedelta(seconds=20))
    earlier = c.repository.touch(c.case.session, NOW + timedelta(seconds=10))
    assert updated.last_seen_at == earlier.last_seen_at == NOW + timedelta(seconds=20)


# Batches limit deletes even when concurrent cleanup processes share the same table.
def test_cleanup_batches_are_bounded_and_concurrent_runs_are_safe(cleanup_case):
    c = cleanup_case
    for _ in range(8):
        add_session(c, revoked_at=NOW)
    before = ids(c.engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = list(pool.map(lambda _: c.repository.purge_expired(NOW, 2), range(2)))
    assert deleted == [2, 2]
    assert len(before - ids(c.engine)) == 4 and c.case.session.id in ids(c.engine)


# Locked invalid rows do not block cleanup and remain eligible after their owning transaction exits.
def test_cleanup_skips_locked_rows_without_deleting_live_sessions(cleanup_case):
    c = cleanup_case
    locked = add_session(c, revoked_at=NOW)
    with c.engine.begin() as connection:
        connection.execute(
            select(admin_session.c.id).where(admin_session.c.id == locked).with_for_update()
        ).one()
        settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
        result = cleanup_sessions(c.repository, settings.sessions.cleanup, lambda: NOW)
        assert result.batch_limit_reached is False
        assert locked in ids(c.engine) and c.case.session.id in ids(c.engine)
    c.repository.purge_expired(NOW, 10000)
    assert locked not in ids(c.engine) and c.case.session.id in ids(c.engine)


# New session inserts must explicitly pin policy; a migration backfill is not a runtime default.
def test_idle_policy_has_no_database_default_and_invalid_values_are_rejected(cleanup_case):
    c = cleanup_case
    column = next(
        col
        for col in inspect(c.engine).get_columns("otm_admin_session")
        if col["name"] == "idle_timeout_seconds"
    )
    assert column["default"] is None and column["nullable"] is False
    values = c.case.session.model_dump()
    values.update(id=uuid4(), session_token_hash=uuid4().hex + uuid4().hex, idle_timeout_seconds=0)
    with pytest.raises(IntegrityError):
        with c.engine.begin() as connection:
            connection.execute(admin_session.insert().values(**values))


# Exercise the real operator command against only this run's disposable database and credentials.
def test_real_maintenance_command_purges_invalid_sessions(cleanup_case, monkeypatch, capsys):
    from otm.maintenance import main

    c = cleanup_case
    dead = add_session(c, revoked_at=NOW)
    monkeypatch.setenv("OTM_DATABASE_URL", c.engine.url.render_as_string(hide_password=False))
    config = Path(__file__).resolve().parents[1] / "config/application.toml"
    assert main(["cleanup-sessions", "--config", str(config)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["deleted"] >= 1 and set(result) == {"deleted", "batches", "batch_limit_reached"}
    assert dead not in ids(c.engine)


# Prove cleanup works with column-scoped privileges rather than the test owner's power.
def test_cleanup_with_restricted_database_role(cleanup_case):
    from contextlib import contextmanager

    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    c = cleanup_case
    dead = add_session(c, revoked_at=NOW)
    with c.engine.begin() as connection:
        connection.exec_driver_sql("CREATE ROLE otm_session_sweeper_test NOLOGIN")
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_session_sweeper_test")
        connection.exec_driver_sql(
            "GRANT SELECT(id,expires_at,last_seen_at,idle_timeout_seconds,revoked_at), "
            "UPDATE(id), DELETE "
            "ON public.otm_admin_session TO otm_session_sweeper_test"
        )

    # Restrict the real connection before the unmodified repository executes its actual SQL.
    class RoleEngine:
        # Keep role scope transaction-local; the owner's pooled connection is restored on exit.
        @contextmanager
        def begin(self):
            with c.engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL ROLE otm_session_sweeper_test")
                yield connection

    restricted = RoleEngine()
    assert SqlSessionRepository(restricted).purge_expired(NOW, 10000) >= 1
    assert dead not in ids(c.engine) and c.case.session.id in ids(c.engine)
    for statement in (
        "SELECT * FROM public.audit_event",
        "SELECT subject FROM public.otm_admin_session",
        "UPDATE public.otm_admin_session SET subject='forbidden'",
        "UPDATE public.otm_admin_session SET revoked_at=NULL",
    ):
        with pytest.raises(ProgrammingError):
            with restricted.begin() as connection:
                connection.execute(text(statement))
