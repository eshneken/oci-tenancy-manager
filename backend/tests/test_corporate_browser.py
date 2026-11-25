"""Opt-in SSO HTTP boundary and single-use browser state against synthetic dependencies."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_corporate_oidc import GROUP, GUID, binding
from test_sessions import session_case

from otm.app import create_app
from otm.auth.corporate_browser import ATTEMPT_COOKIE, CorporateSignIn, LaptopOidcAttempts
from otm.auth.corporate_enrollment import EnrollmentTarget
from otm.auth.corporate_entitlements import CorporateEntitlements
from otm.auth.corporate_exchange import OracleCodeExchange
from otm.auth.corporate_oidc import CALLBACK_PATH, START_PATH, VerifiedDomainLogin
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.local import IssuedSession
from otm.auth.service import SessionService
from otm.storage.corporate_administrators import CorporateAdministrators
from otm.storage.corporate_sessions import SqlCorporateSessions

__all__ = ["binding", "session_case"]


# Compose real browser middleware around clearly synthetic exchange and session issuance.
@pytest.fixture
def pilot(binding, session_case):
    case = session_case
    target = EnrollmentTarget(
        environment="development",
        workspace="dev",
        domain="domain",
        issuer="urn:otm:corporate:test",
        app="a" * 32,
        group=GROUP,
        oidc_client_id=binding.client_id,
    )
    authority = CorporateEntitlements(case.authority, case.session.issuer, target)
    service = SessionService(
        case.repository, case.authority, case.session.issuer, case.clock, corporate=authority
    )
    exchange = Mock(spec=OracleCodeExchange, binding=binding)
    exchange.exchange.return_value = VerifiedDomainLogin(guid=GUID, group=GROUP)
    issuer = Mock(spec=SqlCorporateSessions, authority=authority)
    issuer.issue.return_value = IssuedSession(handle=case.handle, session=case.session)
    sign_in = CorporateSignIn(LaptopOidcAttempts(), exchange, issuer)
    browser = BrowserSettings(public_origin=binding.installation_origin)
    return service, browser, sign_in


# Hide corporate sign-in until the exact app composition is available and advertise no secrets.
@pytest.mark.parametrize("enabled", [True, False])
def test_login_capability_is_public_and_matches_runtime(pilot, tmp_path, enabled):
    service, browser, sign_in = pilot
    (tmp_path / "index.html").write_text("<title>Synthetic login</title>")
    (tmp_path / "assets").mkdir()
    app = create_app(
        service, browser, ui_dist=tmp_path, corporate_sign_in=sign_in if enabled else None
    )
    with TestClient(app, base_url=browser.public_origin) as client:
        response = client.get("/api/auth/sso/status", headers={"cookie": "bad"})
        assert response.status_code == 200
        assert response.json() == {"enabled": enabled}
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/api/auth/sso/status").status_code == 403


# Require same-origin initiation and the exact browser cookie before any exchange or issuer call.
def test_callback_is_browser_bound_and_replay_safe(pilot):
    service, browser, sign_in = pilot
    app = create_app(service, browser, corporate_sign_in=sign_in)
    with TestClient(app, base_url=browser.public_origin) as client:
        assert client.post(START_PATH).status_code == 403
        response = client.post(
            START_PATH, headers={"origin": browser.public_origin, "x-otm-request": "1"}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert (
            "HttpOnly" in response.headers["set-cookie"]
            and "Secure" in response.headers["set-cookie"]
        )
        state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
        browser_cookie = client.cookies.get(ATTEMPT_COOKIE)
        client.cookies.clear()
        for cookie in ("z" * 43, None):
            if cookie:
                client.cookies.set(ATTEMPT_COOKIE, cookie)
            denied = client.get(
                CALLBACK_PATH,
                params={"code": "synthetic-code", "state": state},
                follow_redirects=False,
            )
            assert denied.headers["location"] == "/login?sso=failed"
        sign_in.exchange.exchange.assert_not_called()
        for expected in ("/", "/login?sso=failed"):
            client.cookies.clear()
            client.cookies.set(ATTEMPT_COOKIE, browser_cookie)
            completed = client.get(
                CALLBACK_PATH,
                params={"code": "synthetic-code", "state": state},
                follow_redirects=False,
            )
            assert completed.headers["location"] == expected
            if expected == "/":
                assert COOKIE_NAME in completed.headers["set-cookie"]
        sign_in.exchange.exchange.assert_called_once()
        sign_in.issuer.issue.assert_called_once_with(sign_in.exchange.exchange.return_value)


# A late issuance or exchange failure produces no Atlas session cookie.
@pytest.mark.parametrize("failure", ["exchange", "issue"])
def test_callback_failure_clears_attempt_and_never_issues_cookie(pilot, failure):
    service, browser, sign_in = pilot
    broken = sign_in.exchange.exchange if failure == "exchange" else sign_in.issuer.issue
    broken.side_effect = RuntimeError("provider secret diagnostic")
    app = create_app(service, browser, corporate_sign_in=sign_in)
    with TestClient(app, base_url=browser.public_origin) as client:
        start = client.post(
            START_PATH, headers={"origin": browser.public_origin, "x-otm-request": "1"}
        )
        state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
        response = client.get(
            CALLBACK_PATH, params={"code": "code", "state": state}, follow_redirects=False
        )
        assert response.headers["location"] == "/login?sso=failed"
        assert ATTEMPT_COOKIE in response.headers["set-cookie"]
        assert COOKIE_NAME not in response.headers["set-cookie"]
        assert "provider secret diagnostic" not in response.text


# Unconfigured and wrong-origin installations expose no corporate login capability.
def test_corporate_browser_requires_explicit_development_composition(pilot):
    service, browser, sign_in = pilot
    with TestClient(create_app(service, browser), base_url=browser.public_origin) as client:
        assert client.get(CALLBACK_PATH).status_code == 401
    with pytest.raises(ValueError, match="QUALIFIED_LAPTOP_BOUNDARY"):
        create_app(
            service,
            BrowserSettings(public_origin="https://localhost:8443"),
            corporate_sign_in=sign_in,
        )
    sign_in.exchange.binding = sign_in.exchange.binding.model_copy(
        update={"client_id": "staging-client"}
    )
    with pytest.raises(ValueError, match="QUALIFIED_LAPTOP_BOUNDARY"):
        create_app(service, browser, corporate_sign_in=sign_in)


# One callback wins an exact attempt race; expiry and saturation are bounded.
def test_attempt_store_honors_replay_race_expiry_and_capacity(monkeypatch):
    import otm.auth.corporate_browser as module

    clock = Mock(return_value=100.0)
    store = LaptopOidcAttempts(clock)
    monkeypatch.setattr(module, "ATTEMPT_LIMIT", 1)
    pending, cookie = store.begin()
    with pytest.raises(ValueError, match="ATTEMPTS_BUSY"):
        store.begin()
    with ThreadPoolExecutor(2) as workers:
        outcomes = [workers.submit(store.consume, pending.state, cookie) for _ in range(2)]
    assert sum(future.exception() is None for future in outcomes) == 1
    expired, cookie = store.begin()
    clock.return_value += timedelta(minutes=5).total_seconds()
    with pytest.raises(ValueError, match="ATTEMPT_INVALID"):
        store.consume(expired.state, cookie)
    assert store.begin()[0].state != expired.state


# Exercise opt-in administrator routes through real auth, CSRF and private failure handlers.
def test_onboarding_boundary_validates_commands_and_suppresses_provider_diagnostics(
    pilot, session_case
):
    service, browser, sign_in = pilot
    store = Mock()
    onboarding = Mock(spec=CorporateAdministrators)
    onboarding.store = store
    onboarding.target = service.corporate.target
    onboarding.preview.return_value = {"username": "synthetic"}
    onboarding.confirm.return_value = {"status": "active"}
    onboarding.cleanup.return_value = {"group_cleanup": "complete"}
    onboarding.remove.return_value = {"group_cleanup": "pending"}
    app = create_app(service, browser, administrators=store, corporate_administrators=onboarding)
    path = "/api/administrators"
    identifier, revision = uuid4(), uuid4()
    headers = {"origin": browser.public_origin, "x-otm-request": "1"}
    command = {"expected_revision": str(revision)}
    with TestClient(app, base_url=browser.public_origin) as client:
        assert client.get(f"{path}/onboarding").status_code == 401
        client.cookies.set(COOKIE_NAME, session_case.handle)
        status = client.get(f"{path}/onboarding")
        assert status.json() == {"enabled": True, "environment": "development"}
        assert status.headers["cache-control"] == "no-store"
        preview = f"{path}/onboarding/preview"
        assert client.post(preview, json={"value": "synthetic@example.test"}).status_code == 403
        assert client.post(preview, headers=headers, content="synthetic").status_code == 400
        assert client.post(preview, headers=headers, json={"value": "x" * 4100}).status_code == 400
        assert client.post(
            preview, headers=headers, json={"value": "synthetic@example.test"}
        ).json() == {"username": "synthetic"}
        assert client.post(
            f"{path}/onboarding/confirm",
            headers=headers,
            json={"value": "synthetic@example.test", "confirmation": "a" * 64},
        ).json() == {"status": "active"}
        assert client.post(
            f"{path}/{identifier}/group-cleanup", headers=headers, json=command
        ).json() == {"group_cleanup": "complete"}
        assert client.post(f"{path}/{identifier}/revoke", headers=headers, json=command).json() == {
            "group_cleanup": "pending"
        }
        assert onboarding.cleanup.call_args.args[1:] == (identifier, revision)
        for failure, status_code, code in (
            (TimeoutError("private"), 503, "ADMINISTRATOR_SERVICE_UNAVAILABLE"),
            (PermissionError("private"), 403, "ADMINISTRATOR_REQUIRED"),
        ):
            onboarding.preview.side_effect = failure
            denied = client.post(preview, headers=headers, json={"value": "synthetic@example.test"})
            assert denied.status_code == status_code
            assert denied.json() == {"code": code}
    with pytest.raises(ValueError):
        create_app(service, browser, administrators=Mock(), corporate_administrators=onboarding)
