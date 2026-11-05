"""Configured request-boundary tests over ASGI, without real SSO or a permissive login endpoint."""

from unittest.mock import Mock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.service import SessionFailure

__all__ = ["session_case"]
ORIGIN = "https://otm.example.test"


# Compose the actual boundary with explicit test-only repository and current authority.
def configured(case):
    return create_app(case.service, BrowserSettings(public_origin=ORIGIN))


# Pass fixture handles only through a cookie header, never URL/query/body parameters.
def cookie(case):
    return {"cookie": COOKIE_NAME + "=" + case.handle}


# Do not derive policy from request headers or accept malformed origin configuration.
@pytest.mark.parametrize(
    "origin",
    [
        "http://otm.example.test",
        "https://otm.example.test/",
        "https://user@otm.example.test",
        "https://OTM.example.test",
        "https://otm.example.test:443",
        "https://otm.example.test:abc",
        "https://otm.example.test:",
        "https://otm.example.test?",
        "https://otm.example.test\n",
    ],
)
def test_ambiguous_or_insecure_configured_origin_is_rejected(origin):
    with pytest.raises((ValueError, ValidationError)):
        BrowserSettings(public_origin=origin)


# Require both security dependencies; never enable partial or local authentication.
def test_partial_authority_composition_is_rejected(session_case):
    with pytest.raises(ValueError):
        create_app(session_case.service)
    with pytest.raises(ValueError):
        create_app(browser=BrowserSettings(public_origin=ORIGIN))


# Return UI context only; no handle/hash/raw claim/entitlement metadata escapes.
def test_current_session_view_is_minimal_noncacheable_and_not_an_issuance_endpoint(session_case):
    with TestClient(configured(session_case), base_url=ORIGIN) as client:
        result = client.get("/api/session", headers=cookie(session_case))
    assert result.status_code == 200
    assert set(result.json()) == {"workspace_id", "display_name", "expires_at"}
    assert (
        session_case.handle not in result.text
        and session_case.session.session_token_hash not in result.text
    )
    assert result.headers["cache-control"] == "no-store" and "Cookie" in result.headers["vary"]
    assert result.headers["x-content-type-options"] == "nosniff"
    assert (
        "set-cookie" not in result.headers and "access-control-allow-origin" not in result.headers
    )


# Missing cookies and forged identity headers cannot authenticate any protected route.
@pytest.mark.parametrize(
    "target", ["/api/session", "/api/future-command", "/auth/login", "/auth/callback"]
)
def test_configured_backend_has_no_unauthenticated_nonhealth_bypass(session_case, target):
    with TestClient(configured(session_case), base_url=ORIGIN) as client:
        result = client.get(target, headers={"x-user": "admin", "authorization": "Bearer forged"})
    assert result.status_code == 401 and result.json() == {"code": "AUTHENTICATION_REQUIRED"}
    session_case.repository.find.assert_not_called()


# Do not let proxy/cookie parsing order choose between multiple target cookies.
@pytest.mark.parametrize("value", ["duplicate", "missing_equals", "oversized", "malformed"])
def test_cookie_parser_rejects_duplicate_or_malformed_handles_before_lookup(session_case, value):
    c = COOKIE_NAME + "=" + session_case.handle
    raw = {
        "duplicate": c + "; " + c,
        "missing_equals": COOKIE_NAME,
        "oversized": "other=" + "x" * 4097,
        "malformed": COOKIE_NAME + "=bad",
    }[value]
    with TestClient(configured(session_case), base_url=ORIGIN) as client:
        result = client.get("/api/session", headers={"cookie": raw})
    assert result.status_code == 401
    session_case.repository.find.assert_not_called()


# Only deployment-configured ASGI transport/host can satisfy the public-origin boundary.
@pytest.mark.parametrize(
    "url,headers",
    [
        ("http://otm.example.test", {}),
        (ORIGIN, {"host": "other.example.test"}),
        ("http://otm.example.test", {"x-forwarded-proto": "https"}),
    ],
)
def test_transport_and_host_are_not_taken_from_untrusted_forwarded_headers(
    session_case, url, headers
):
    with TestClient(configured(session_case), base_url=url) as client:
        result = client.get("/api/session", headers={**cookie(session_case), **headers})
    assert result.status_code == 400
    session_case.repository.find.assert_not_called()


# An HTML form or cross-origin script cannot reach command authorization with cookies.
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": "null", "x-otm-request": "1"},
        {"origin": "https://other.example.test", "x-otm-request": "1"},
        {"origin": ORIGIN},
    ],
)
def test_unsafe_requests_require_origin_and_custom_header_before_authentication(
    session_case, headers
):
    with TestClient(configured(session_case), base_url=ORIGIN) as client:
        result = client.post(
            "/api/session", headers={**cookie(session_case), **headers}, content="x"
        )
    assert result.status_code == 403 and result.json()["code"] == "REQUEST_ORIGIN_REQUIRED"
    session_case.repository.find.assert_not_called()


# Route-specific parsing governs JSON/CSV, while the shared guard remains CSRF resistant.
@pytest.mark.parametrize(
    "content_type", ["application/json", "multipart/form-data; boundary=example"]
)
def test_valid_same_origin_guard_preserves_future_upload_content_types(session_case, content_type):
    app = configured(session_case)

    # Use a test-only handler to prove the real shared guard permits legitimate requests.
    @app.post("/api/probe")
    def probe():
        return {"ok": True}

    with TestClient(app, base_url=ORIGIN) as client:
        result = client.post(
            "/api/probe",
            headers={
                **cookie(session_case),
                "origin": ORIGIN,
                "x-otm-request": "1",
                "content-type": content_type,
            },
            content="example",
        )
    assert result.status_code == 200 and result.json() == {"ok": True}


# Liveness never depends on session storage, provider availability or HTTPS redirects.
def test_health_is_process_only_even_with_bad_cookie_and_authority_outage(session_case):
    session_case.repository.find.side_effect = RuntimeError("private-example")
    with TestClient(configured(session_case)) as client:
        result = client.get("/health/live", headers={"cookie": COOKIE_NAME + "=bad"})
    assert result.json() == {"status": "ok"}
    session_case.repository.find.assert_not_called()


# Normalize known session failures without exposing a trusted adapter's private details.
@pytest.mark.parametrize("status", [401, 403, 503])
def test_authentication_errors_are_safe_and_noncacheable(session_case, status):
    code = {
        401: "AUTHENTICATION_REQUIRED",
        403: "ADMINISTRATOR_REQUIRED",
        503: "AUTHENTICATION_UNAVAILABLE",
    }[status]
    session_case.service.authenticate = Mock(side_effect=SessionFailure(status, code))
    with TestClient(configured(session_case), base_url=ORIGIN) as client:
        response = client.get("/api/session", headers=cookie(session_case))
    assert response.status_code == status and response.json() == {"code": code}
    assert response.headers["cache-control"] == "no-store"


# Retain a route-level guard and safe fresh-authority exception mapping.
def test_session_view_defends_against_missing_principal_and_command_failure_is_normalized(
    session_case,
):
    app = configured(session_case)
    with patch("otm.auth.http.CookieSessionBackend.authenticate", return_value=None):
        with TestClient(app, base_url=ORIGIN) as client:
            assert client.get("/api/session").status_code == 401

    # Exercise the shared SessionFailure handler as a future command dependency would.
    @app.get("/api/probe")
    def probe(request: Request):
        raise SessionFailure(403, "ADMINISTRATOR_REQUIRED")

    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/probe", headers=cookie(session_case)).json() == {
            "code": "ADMINISTRATOR_REQUIRED"
        }


# Conflicting proxy/header interpretations cannot choose which origin or host is trusted.
@pytest.mark.parametrize("header", ["host", "origin", "x-otm-request"])
def test_duplicate_security_headers_are_rejected_before_session_lookup(session_case, header):
    headers = [
        ("host", "otm.example.test"),
        ("origin", ORIGIN),
        ("x-otm-request", "1"),
        ("cookie", COOKIE_NAME + "=" + session_case.handle),
    ]
    headers.append(
        (header, {"host": "otm.example.test", "origin": ORIGIN, "x-otm-request": "1"}[header])
    )
    with TestClient(configured(session_case), base_url=ORIGIN) as client:
        response = client.post("/api/probe", headers=headers)
    assert response.status_code == (400 if header == "host" else 403)
    session_case.repository.find.assert_not_called()
