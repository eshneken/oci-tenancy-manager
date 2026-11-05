"""Guarded local sign-in and interactive operator command boundaries without real credentials."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_sessions import session_case

from otm.admin_cli import main
from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.local import IssuedSession, LocalAuthFailure
from otm.operations.contracts import ActorIdentity
from otm.settings import load_settings

__all__ = ["session_case"]
ORIGIN = "https://otm.example.test"
HEADERS = {"origin": ORIGIN, "x-otm-request": "1"}


# Verify response behavior using only an injected committed receipt, never a password bypass route.
def test_local_login_http_cookie_and_minimal_response(session_case):
    login = Mock(
        sign_in=Mock(
            return_value=IssuedSession(handle=session_case.handle, session=session_case.session)
        )
    )
    with TestClient(
        create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), login),
        base_url=ORIGIN,
    ) as client:
        response = client.post(
            "/api/auth/local/sign-in",
            json={
                "username": "recovery-admin",
                "password": "synthetic input",
                "totp_code": "123456",
            },
            headers=HEADERS,
        )
        assert response.status_code == 200 and set(response.json()) == {
            "workspace_id",
            "display_name",
            "expires_at",
        }
        cookie = response.headers["set-cookie"]
        assert all(value in cookie for value in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"))
        assert (
            session_case.handle not in response.text
            and response.headers["cache-control"] == "no-store"
        )
        client.cookies.clear()
        assert client.get("/api/auth/local/sign-in").status_code == 401
    login.sign_in.assert_called_once()
    session_case.repository.find.assert_not_called()


# Failed proof or commit never sets a browser credential, even if an old cookie was presented.
@pytest.mark.parametrize(
    "failure", [LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED"), RuntimeError("private error")]
)
def test_local_login_failure_is_fixed_and_sets_no_cookie(session_case, failure):
    login = Mock(sign_in=Mock(side_effect=failure))
    with TestClient(
        create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), login),
        base_url=ORIGIN,
    ) as client:
        response = client.post(
            "/api/auth/local/sign-in",
            json={
                "username": "recovery-admin",
                "password": "synthetic input",
                "totp_code": "123456",
            },
            headers={**HEADERS, "cookie": COOKIE_NAME + "=" + session_case.handle},
        )
        assert response.status_code in (401, 503) and "set-cookie" not in response.headers
        assert "private error" not in response.text and "synthetic input" not in response.text
    assert login.sign_in.call_args.args[1] == session_case.handle


# Do not expose Pydantic raw input errors or allocate an unbounded factor payload.
@pytest.mark.parametrize(
    "body,content_type",
    [
        (b"{bad", "application/json"),
        (b"{}", "application/json"),
        (b"x" * 4097, "application/json"),
        (b"{}", "text/plain"),
        (b'{"username":"recovery-admin","password":123,"totp_code":"123456"}', "application/json"),
        (
            b'{"username":"recovery-admin","password":"private input","totp_code":{}}',
            "application/json",
        ),
    ],
)
def test_local_login_rejects_malformed_body_without_reflecting_input(
    session_case, body, content_type
):
    login = Mock()
    with TestClient(
        create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), login),
        base_url=ORIGIN,
    ) as client:
        response = client.post(
            "/api/auth/local/sign-in",
            content=body,
            headers={**HEADERS, "content-type": content_type},
        )
        assert response.status_code == 401 and response.json() == {
            "code": "LOCAL_AUTHENTICATION_FAILED"
        }
        assert "set-cookie" not in response.headers
    login.sign_in.assert_not_called()


# The sign-in exemption never relaxes the existing HTTPS, Host or Origin/custom-header guards.
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": "https://wrong.example.test", "x-otm-request": "1"},
        {"origin": ORIGIN},
        {**HEADERS, "host": "wrong.example.test"},
    ],
)
def test_login_keeps_browser_boundary_guards(session_case, headers):
    login = Mock()
    with TestClient(
        create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), login),
        base_url=ORIGIN,
    ) as client:
        response = client.post("/api/auth/local/sign-in", json={}, headers=headers)
        assert response.status_code in (400, 403)
    login.sign_in.assert_not_called()


# No default application or incomplete composition may expose a local authentication route.
def test_login_is_explicit_opt_in(session_case):
    with pytest.raises(ValueError):
        create_app(login=Mock())
    with TestClient(create_app()) as client:
        assert client.post("/api/auth/local/sign-in", json={}).status_code == 404
    with TestClient(
        create_app(session_case.service, BrowserSettings(public_origin=ORIGIN)), base_url=ORIGIN
    ) as client:
        assert client.post("/api/auth/local/sign-in", json={}, headers=HEADERS).status_code == 401


# Stage no real seed, hash or database call in pure CLI orchestration tests.
@pytest.fixture
def cli_case(monkeypatch):
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    engine = Mock()
    repository = Mock()
    actor = ActorIdentity(issuer="urn:otm:database-operator", subject="test_operator")
    repository.operator_status.return_value = (None, actor)
    repository.enroll.return_value = uuid4()
    monkeypatch.setenv("OTM_DATABASE_URL", "explicit-synthetic-only")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    return SimpleNamespace(settings=settings, engine=engine, repository=repository, actor=actor)


# The operator command verifies role/state before prompts and creates no preauthenticated session.
@pytest.mark.parametrize("operation", ["bootstrap", "reset-local"])
def test_cli_enrollment_and_reset_orchestration(cli_case, operation, capsys):
    c = cli_case
    if operation == "reset-local":
        c.repository.operator_status.return_value = (Mock(), c.actor)
    with (
        patch("sys.stdout.isatty", return_value=True),
        patch("otm.admin_cli.load_settings", return_value=c.settings),
        patch("otm.admin_cli.maintenance_engine", return_value=c.engine),
        patch("otm.admin_cli.SqlLocalAuth", return_value=c.repository),
        patch("otm.admin_cli.DirectorySecrets") as custody,
        patch(
            "otm.admin_cli.getpass.getpass",
            side_effect=["synthetic only long password"] * 2 + ["123456"],
        ),
        patch("otm.admin_cli.password_verifier", return_value="synthetic-verifier"),
        patch("otm.admin_cli.totp_step", return_value=100),
        patch("otm.admin_cli.print"),
    ):
        assert (
            main([operation, "--config", "synthetic.toml", "--secret-directory", "/synthetic"]) == 0
        )
    c.repository.enroll.assert_called_once()
    c.engine.dispose.assert_called_once()
    custody.assert_called_once()


# Bad parameters, unavailable state and failed enrollment never leak factors or rerun bootstrap.
@pytest.mark.parametrize(
    "damage", ["arguments", "terminal", "settings", "role", "password", "code", "commit"]
)
def test_cli_failures_are_fixed_and_cleanup_owned_engine(cli_case, damage, capsys):
    c = cli_case
    if damage == "role":
        c.repository.operator_status.side_effect = LocalAuthFailure(
            409, "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED"
        )
    if damage == "commit":
        c.repository.enroll.side_effect = RuntimeError("private db material")
    settings = (
        c.settings.model_copy(update={"local_auth": None}) if damage == "settings" else c.settings
    )
    passwords = (
        ["one synthetic passphrase", "different synthetic passphrase", "123456"]
        if damage == "password"
        else ["synthetic only long password"] * 2 + ["123456"]
    )
    argv = ["bootstrap", "--config", "synthetic.toml", "--secret-directory", "/synthetic"]
    if damage == "arguments":
        argv += ["--password=private-data"]
    with (
        patch("sys.stdout.isatty", return_value=True),
        patch("otm.admin_cli.load_settings", return_value=settings),
        patch("otm.admin_cli.maintenance_engine", return_value=c.engine),
        patch("otm.admin_cli.SqlLocalAuth", return_value=c.repository),
        patch("otm.admin_cli.DirectorySecrets"),
        patch("otm.admin_cli.getpass.getpass", side_effect=passwords),
        patch("otm.admin_cli.password_verifier", return_value="synthetic-verifier"),
        patch("otm.admin_cli.totp_step", return_value=None if damage == "code" else 100),
        patch("sys.stdin.isatty", return_value=damage != "terminal"),
        patch("otm.admin_cli.print") as output,
    ):
        assert main(argv) == 1
        messages = [str(call.args[0]) for call in output.call_args_list]
        assert "private-data" not in "".join(messages) and "private db material" not in "".join(
            messages
        )
    if damage not in {"arguments", "terminal", "settings"}:
        c.engine.dispose.assert_called_once()
    if damage in {"role", "password", "code", "arguments", "terminal", "settings"}:
        c.repository.enroll.assert_not_called()
