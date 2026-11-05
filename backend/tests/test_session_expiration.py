"""Session idle/absolute expiry and explicit activity/logout behavior without database IO."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from test_admission_service import NOW
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.service import SessionFailure

__all__ = ["session_case"]
ORIGIN = "https://otm.example.test"


# Expiration must be enforced on each request, even before housekeeping ever runs.
@pytest.mark.parametrize("boundary", ["idle", "absolute"])
def test_expiry_is_immediate_and_no_entitlement_is_queried(session_case, boundary):
    c = session_case
    c.clock.return_value = (
        NOW + timedelta(seconds=c.session.idle_timeout_seconds)
        if boundary == "idle"
        else c.session.expires_at
    )
    with pytest.raises(SessionFailure) as error:
        c.service.authenticate(c.handle)
    assert error.value.status == 401
    c.authority.require_admin.assert_not_called()


# A long authority call cannot grant access past the pinned idle deadline.
def test_idle_can_expire_during_authority_check(session_case):
    c = session_case
    c.clock.side_effect = [NOW, NOW + timedelta(seconds=c.session.idle_timeout_seconds)]
    with pytest.raises(SessionFailure) as error:
        c.service.authenticate(c.handle)
    assert error.value.status == 401


# Successful activity refresh uses only server time and the current validated identity.
def test_activity_updates_only_after_current_authority(session_case):
    c = session_case
    principal = c.service.authenticate(c.handle)
    at = NOW + timedelta(seconds=10)
    updated = c.session.model_copy(update={"last_seen_at": at})
    c.clock.return_value = at
    c.repository.touch.return_value = updated
    assert c.service.activity(principal).session == updated
    c.repository.touch.assert_called_once_with(c.session, at)


# Losing a concurrent expiration/revocation race must never revive the session.
def test_failed_touch_is_unauthorized(session_case):
    c = session_case
    principal = c.service.authenticate(c.handle)
    c.repository.touch.return_value = None
    with pytest.raises(SessionFailure) as error:
        c.service.activity(principal)
    assert error.value.status == 401


# Adapter failures are fixed unavailable diagnostics rather than private details.
def test_touch_failure_is_sanitized(session_case):
    c = session_case
    principal = c.service.authenticate(c.handle)
    c.repository.touch.side_effect = RuntimeError("private-example")
    with pytest.raises(SessionFailure) as error:
        c.service.activity(principal)
    assert error.value.status == 503 and "private-example" not in str(error.value)


# Wrong types and absent/invalid handles cannot trigger revocation of arbitrary rows.
@pytest.mark.parametrize("handle", [None, "bad", 123])
def test_logout_missing_or_malformed_is_idempotent(session_case, handle):
    session_case.service.logout(handle)
    session_case.repository.find.assert_not_called()


# Ending an owned session does not require a functioning corporate IdP or current role.
def test_logout_skips_entitlement_and_revokes_exact_session(session_case):
    c = session_case
    c.authority.require_admin.side_effect = RuntimeError("SSO unavailable")
    c.service.logout(c.handle)
    c.repository.revoke.assert_called_once_with(
        c.session.id, c.session.session_token_hash, c.session.workspace_id, NOW
    )
    c.authority.require_admin.assert_not_called()


# A deleted handle remains safely logged out; conflicting metadata is not trusted.
@pytest.mark.parametrize("kind", ["missing", "mismatch", "failure"])
def test_logout_missing_or_unavailable_metadata(session_case, kind):
    c = session_case
    if kind == "missing":
        c.repository.find.return_value = None
    elif kind == "mismatch":
        c.repository.find.return_value = c.session.model_copy(
            update={"session_token_hash": "0" * 64}
        )
    else:
        c.repository.find.side_effect = RuntimeError("private-example")
    if kind == "missing":
        c.service.logout(c.handle)
    else:
        with pytest.raises(SessionFailure) as error:
            c.service.logout(c.handle)
        assert error.value.status == 503
    c.repository.revoke.assert_not_called()


# Polling authenticates but never refreshes the idle timer; intentional activity is separate.
def test_http_polling_does_not_extend_session_and_activity_does(session_case):
    c = session_case
    headers = {"cookie": COOKIE_NAME + "=" + c.handle, "origin": ORIGIN, "x-otm-request": "1"}
    c.repository.touch.return_value = c.session
    with TestClient(
        create_app(c.service, BrowserSettings(public_origin=ORIGIN)), base_url=ORIGIN
    ) as client:
        assert client.get("/api/session", headers=headers).status_code == 200
        c.repository.touch.assert_not_called()
        assert client.post("/api/session/activity", headers=headers).status_code == 200
    c.repository.touch.assert_called_once()


# CSRF protection remains in force on the narrow unauthenticated logout exception.
def test_http_logout_safe_scope_and_secure_cookie_deletion(session_case):
    c = session_case
    c.authority.require_admin.side_effect = RuntimeError("SSO unavailable")
    with TestClient(
        create_app(c.service, BrowserSettings(public_origin=ORIGIN)), base_url=ORIGIN
    ) as client:
        cookie = {"cookie": COOKIE_NAME + "=" + c.handle}
        assert client.post("/api/logout", headers=cookie).status_code == 403
        result = client.post(
            "/api/logout", headers={**cookie, "origin": ORIGIN, "x-otm-request": "1"}
        )
    assert result.status_code == 204
    header = result.headers["set-cookie"]
    assert (
        "Secure" in header
        and "HttpOnly" in header
        and "Path=/" in header
        and "Domain=" not in header
    )
    c.authority.require_admin.assert_not_called()
    c.repository.revoke.assert_called_once()


# Session-store failures clear the browser cookie but report server revocation as unconfirmed.
def test_http_logout_failure_and_missing_cookie(session_case):
    c = session_case
    with TestClient(
        create_app(c.service, BrowserSettings(public_origin=ORIGIN)), base_url=ORIGIN
    ) as client:
        headers = {"origin": ORIGIN, "x-otm-request": "1"}
        assert client.post("/api/logout", headers=headers).status_code == 204
        c.repository.find.side_effect = RuntimeError("private-example")
        response = client.post(
            "/api/logout", headers={**headers, "cookie": COOKIE_NAME + "=" + c.handle}
        )
    assert response.status_code == 503 and "set-cookie" in response.headers
    assert "private-example" not in response.text


# A race that expires/revokes the session after middleware must clear the secure cookie as well.
def test_http_activity_lost_liveness_clears_cookie(session_case):
    c = session_case
    c.repository.touch.return_value = None
    with TestClient(
        create_app(c.service, BrowserSettings(public_origin=ORIGIN)), base_url=ORIGIN
    ) as client:
        result = client.post(
            "/api/session/activity",
            headers={
                "cookie": COOKIE_NAME + "=" + c.handle,
                "origin": ORIGIN,
                "x-otm-request": "1",
            },
        )
    assert result.status_code == 401
    assert (
        "Secure" in result.headers["set-cookie"] and "Domain=" not in result.headers["set-cookie"]
    )
