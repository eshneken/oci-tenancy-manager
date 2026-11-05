"""Opaque session verification and current authority; no production token issuance shortcuts."""

import hashlib
import secrets
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_admission_service import NOW

from otm.auth.contracts import AdminEntitlement, AdminSession, DisplaySnapshot
from otm.auth.service import AdminPrincipal, SessionFailure, SessionService
from otm.settings import load_settings, session_lifetime


# Use a fresh random fixture handle, synthetic identity and explicit current authority.
@pytest.fixture
def session_case():
    handle = secrets.token_urlsafe(32)
    policy = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    lifetime = session_lifetime(NOW, policy.sessions)
    session = AdminSession(
        id=uuid4(),
        workspace_id="example-org",
        session_token_hash=hashlib.sha256(handle.encode()).hexdigest(),
        issuer="https://sso.example.test",
        subject="admin-one",
        display_snapshot=DisplaySnapshot(display_name="Example Administrator"),
        entitlement_reference="example-admin-group",
        entitlement_revision=uuid4(),
        entitlement_checked_at=NOW,
        auth_time=NOW,
        created_at=NOW,
        expires_at=lifetime.expires_at,
        idle_timeout_seconds=lifetime.idle_timeout_seconds,
        last_seen_at=NOW,
        revoked_at=None,
        provider_session_reference_hash=None,
    )
    grant = AdminEntitlement(
        workspace_id=session.workspace_id,
        issuer=session.issuer,
        subject=session.subject,
        reference=session.entitlement_reference,
        revision=session.entitlement_revision,
        checked_at=NOW,
        valid_until=NOW + timedelta(minutes=1),
    )
    repository = Mock(find=Mock(return_value=session))
    authority = Mock(require_admin=Mock(return_value=grant))
    clock = Mock(return_value=NOW)
    service = SessionService(repository, authority, session.issuer, clock)
    return SimpleNamespace(
        handle=handle,
        session=session,
        grant=grant,
        repository=repository,
        authority=authority,
        clock=clock,
        service=service,
    )


# Stored old group metadata cannot replace the current authorization decision.
def test_session_handle_is_only_hashed_and_live_entitlement_is_required(session_case):
    case = session_case
    principal = case.service.authenticate(case.handle)
    assert isinstance(principal, AdminPrincipal) and principal.is_authenticated
    assert (
        principal.display_name == "Example Administrator"
        and principal.identity == principal.actor.key
    )
    case.repository.find.assert_called_once_with(case.session.session_token_hash)
    case.authority.require_admin.assert_called_once_with(
        case.session.issuer, case.session.subject, "example-org"
    )
    assert case.handle not in repr(principal) and case.handle not in repr(principal.session)


# Bound attacker input before hashing/querying and return only a fixed safe code.
@pytest.mark.parametrize(
    "handle", [None, 123, "", "abc", "x" * 44, "x" * 10000, "a' OR '1'='1", "/" * 43]
)
def test_bad_handle_rejected_before_database_or_provider(session_case, handle):
    with pytest.raises(SessionFailure) as error:
        session_case.service.authenticate(handle)
    assert error.value.status == 401 and str(error.value) == "AUTHENTICATION_REQUIRED"
    session_case.repository.find.assert_not_called()
    session_case.authority.require_admin.assert_not_called()


# A session must be live and bound to the configured issuer and exact opaque digest.
@pytest.mark.parametrize("damage", ["missing", "revoked", "expired", "future", "issuer", "hash"])
def test_invalid_session_never_resolves_entitlement(session_case, damage):
    case = session_case
    changes = {
        "revoked": {"revoked_at": NOW},
        "expired": {"expires_at": NOW},
        "future": {"created_at": NOW + timedelta(seconds=1)},
        "issuer": {"issuer": "https://other.example.test"},
        "hash": {"session_token_hash": "0" * 64},
    }
    case.repository.find.return_value = (
        None if damage == "missing" else case.session.model_copy(update=changes[damage])
    )
    with pytest.raises(SessionFailure) as error:
        case.service.authenticate(case.handle)
    assert error.value.status == 401
    case.authority.require_admin.assert_not_called()


# Fresh exact-scope grants cannot be borrowed from another user/workspace or future time.
@pytest.mark.parametrize(
    "damage",
    ["workspace_id", "issuer", "subject", "reference", "revision", "checked_at", "valid_until"],
)
def test_current_grant_must_match_subject_scope_and_time(session_case, damage):
    case = session_case
    value = (
        uuid4()
        if damage == "revision"
        else NOW + timedelta(seconds=1)
        if damage == "checked_at"
        else NOW
        if damage == "valid_until"
        else "other"
    )
    case.authority.require_admin.return_value = case.grant.model_copy(update={damage: value})
    with pytest.raises(SessionFailure) as error:
        case.service.authenticate(case.handle)
    assert error.value.status == 403


# Outages and malformed trusted output never grant access or leak raw provider details.
@pytest.mark.parametrize("boundary", ["repository", "entitlement", "invalid_model"])
def test_unavailable_verification_fails_closed_without_private_diagnostics(session_case, boundary):
    case = session_case
    if boundary == "repository":
        case.repository.find.side_effect = RuntimeError("private-example")
    elif boundary == "entitlement":
        case.authority.require_admin.side_effect = RuntimeError("private-example")
    else:
        case.authority.require_admin.return_value = {"raw_claim": "private-example"}
    with pytest.raises(SessionFailure) as error:
        case.service.authenticate(case.handle)
    assert error.value.status == 503 and str(error.value) == "AUTHENTICATION_UNAVAILABLE"
    assert error.value.__suppress_context__


# A known non-administrator is forbidden instead of being treated as a provider error.
def test_explicit_entitlement_denial_is_distinct_from_outage(session_case):
    session_case.authority.require_admin.side_effect = PermissionError("private-example")
    with pytest.raises(SessionFailure) as error:
        session_case.service.authenticate(session_case.handle)
    assert error.value.status == 403 and str(error.value) == "ADMINISTRATOR_REQUIRED"


# Recheck expiry after the authority call rather than using an earlier cached instant.
def test_slow_entitlement_check_cannot_extend_session(session_case):
    case = session_case
    case.clock.side_effect = [NOW, case.session.expires_at]
    with pytest.raises(SessionFailure) as error:
        case.service.authenticate(case.handle)
    assert error.value.status == 401


# An earlier request principal never becomes a permanent command authorization token.
@pytest.mark.parametrize("damage", ["principal", "workspace", "identity", "session_id", "revoked"])
def test_operation_authorizer_rechecks_exact_session_and_current_workspace(session_case, damage):
    case = session_case
    principal = case.service.authenticate(case.handle)
    workspace = "other" if damage == "workspace" else case.session.workspace_id
    if damage == "identity":
        case.repository.find.return_value = case.session.model_copy(update={"subject": "other"})
    elif damage == "session_id":
        case.repository.find.return_value = case.session.model_copy(update={"id": uuid4()})
    elif damage == "revoked":
        case.repository.find.return_value = case.session.model_copy(update={"revoked_at": NOW})
    with pytest.raises(SessionFailure):
        case.service.require_admin(object() if damage == "principal" else principal, workspace)


# Authorize admission without raw claims or stale group metadata.
def test_valid_operation_authorizer_refreshes_and_returns_only_allowlisted_actor(session_case):
    case = session_case
    principal = case.service.authenticate(case.handle)
    assert case.service.require_admin(principal, case.session.workspace_id) == principal.actor
    assert case.authority.require_admin.call_count == 2
    assert set(principal.actor.model_dump()) == {"issuer", "subject", "display_name"}
    fallback = AdminPrincipal(
        case.session.model_copy(update={"display_snapshot": DisplaySnapshot()})
    )
    assert fallback.display_name == "Administrator"


# A buggy trusted adapter cannot label arbitrary private exception text as safe to return.
def test_authentication_diagnostic_is_a_closed_public_vocabulary():
    with pytest.raises(ValueError, match="^INVALID_AUTHENTICATION_DIAGNOSTIC$") as error:
        SessionFailure(401, "private-example")
    assert "private-example" not in str(error.value)
