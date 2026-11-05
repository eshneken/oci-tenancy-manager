"""Real session metadata, request authorization, scope and revocation integration tests."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from database_helpers import seed_session_grant
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_admission_service import NOW, admission
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.service import SessionFailure, SessionService
from otm.operations.acceptance import AcceptInspection
from otm.storage.admission import SqlAdmissionStore
from otm.storage.enqueue import InspectionEnqueuer
from otm.storage.sessions import SqlSessionRepository
from otm.storage.tables import admin_session, operation

pytestmark = pytest.mark.postgres
__all__ = ["admission", "session_case"]
ORIGIN = "https://otm.example.test"


# Insert test-only metadata directly; production has no session-minting route or bypass.
@pytest.fixture
def stored_session(pg_engine, session_case):
    case = session_case
    with pg_engine.begin() as connection:
        seed_session_grant(connection, case.session.model_dump())
        connection.execute(admin_session.insert().values(**case.session.model_dump()))
    repository = SqlSessionRepository(pg_engine)
    authority = Mock(require_admin=Mock(return_value=case.grant))
    service = SessionService(repository, authority, case.session.issuer, case.clock)
    return SimpleNamespace(
        engine=pg_engine, repository=repository, authority=authority, service=service, case=case
    )


# No raw browser handle is persisted or held open across the external authority boundary.
def test_real_database_keeps_only_handle_hash_and_current_authority_runs_after_connection_release(
    stored_session,
):
    c = stored_session

    # Observe the actual SQLAlchemy pool while the current provider decision is made.
    def verify(issuer, subject, workspace):
        assert c.engine.pool.checkedout() == 0
        return c.case.grant

    c.authority.require_admin.side_effect = verify
    principal = c.service.authenticate(c.case.handle)
    assert principal.session == c.case.session
    with c.engine.connect() as connection:
        data = connection.execute(
            text("SELECT to_jsonb(s)::text FROM public.otm_admin_session s WHERE id=:id"),
            {"id": c.case.session.id},
        ).scalar_one()
    assert c.case.handle not in data
    assert json.loads(data)["session_token_hash"] == c.case.session.session_token_hash


# Incorrect UUID, workspace or digest cannot revoke a valid session.
@pytest.mark.parametrize("scope", ["id", "workspace", "hash"])
def test_revocation_cannot_touch_another_session_scope(stored_session, scope):
    c = stored_session
    s = c.case.session
    c.repository.revoke(
        uuid4() if scope == "id" else s.id,
        "0" * 64 if scope == "hash" else s.session_token_hash,
        "other" if scope == "workspace" else s.workspace_id,
        NOW,
    )
    assert c.repository.find(s.session_token_hash).revoked_at is None
    c.repository.revoke(s.id, s.session_token_hash, s.workspace_id, NOW)
    c.repository.revoke(s.id, s.session_token_hash, s.workspace_id, NOW + timedelta(minutes=1))
    assert c.repository.find(s.session_token_hash).revoked_at == NOW
    with pytest.raises(SessionFailure) as error:
        c.service.authenticate(c.case.handle)
    assert error.value.status == 401


# The same browser handle cannot resolve to another workspace/user through duplicate rows.
def test_real_unique_handle_hash_cannot_alias_two_sessions(stored_session):
    c = stored_session
    values = c.case.session.model_dump()
    values.update(id=uuid4(), workspace_id="other")
    with pytest.raises(IntegrityError):
        with c.engine.begin() as connection:
            connection.execute(admin_session.insert().values(**values))


# Actual DDL guards identity digests and chronology independently of Python validation.
@pytest.mark.parametrize(
    "field",
    [
        "session_token_hash",
        "provider_session_reference_hash",
        "auth_time",
        "expires_at",
        "last_seen_at",
        "entitlement_checked_at",
    ],
)
def test_database_session_constraints_reject_invalid_hashes_and_times(stored_session, field):
    c = stored_session
    values = c.case.session.model_dump()
    values.update(id=uuid4(), session_token_hash=uuid4().hex + uuid4().hex)
    if field in {"session_token_hash", "provider_session_reference_hash"}:
        values[field] = "invalid"
    elif field in {"auth_time", "entitlement_checked_at"}:
        values[field] = NOW + timedelta(seconds=1)
    elif field == "expires_at":
        values[field] = NOW
    else:
        values[field] = NOW - timedelta(seconds=1)
    with pytest.raises(IntegrityError):
        with c.engine.begin() as connection:
            connection.execute(admin_session.insert().values(**values))


# A forged digest string cannot turn the exact lookup into an unscoped directory query.
def test_sql_lookup_is_parameterized_and_does_not_borrow_another_session(stored_session):
    assert stored_session.repository.find("' OR '1'='1") is None


# Use real SQL-backed request authentication without exposing a fake SSO login.
def test_configured_http_api_sees_revocation_and_live_role_changes(stored_session):
    c = stored_session
    app = create_app(c.service, BrowserSettings(public_origin=ORIGIN))
    headers = {"cookie": COOKIE_NAME + "=" + c.case.handle}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/session", headers=headers).status_code == 200
        c.authority.require_admin.side_effect = PermissionError("role revoked")
        assert client.get("/api/session", headers=headers).status_code == 403
        c.authority.require_admin.side_effect = None
        c.repository.revoke(
            c.case.session.id, c.case.session.session_token_hash, c.case.session.workspace_id, NOW
        )
        assert client.get("/api/session", headers=headers).status_code == 401


# Use current session authority at admission; a cached principal is insufficient.
def test_admission_refreshes_real_session_before_acceptance_and_rejects_revoked_principal(
    stored_session, admission
):
    c = stored_session
    principal = c.service.authenticate(c.case.handle)
    service = AcceptInspection(
        SqlAdmissionStore(c.engine, InspectionEnqueuer()),
        c.service,
        Mock(return_value=admission.policy),
        c.case.clock,
    )
    receipt = service.accept(admission.request, principal)
    with c.engine.connect() as connection:
        op = (
            connection.execute(select(operation).where(operation.c.id == receipt.operation_id))
            .mappings()
            .one()
        )
        assert op["initiating_actor_subject"] == principal.actor.key
    c.repository.revoke(
        c.case.session.id, c.case.session.session_token_hash, c.case.session.workspace_id, NOW
    )
    with pytest.raises(SessionFailure):
        service.accept(admission.request, principal)


# Reject expired rows immediately without requiring a cleanup scheduler.
def test_database_expiry_is_enforced_without_a_cleanup_job(stored_session):
    c = stored_session
    c.case.clock.return_value = c.case.session.expires_at
    with pytest.raises(SessionFailure) as error:
        c.service.authenticate(c.case.handle)
    assert error.value.status == 401
    c.authority.require_admin.assert_not_called()
