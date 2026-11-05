"""Real enrollment, factor issuance, replay/race exclusion and HTTP commit boundaries."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_admission_service import NOW
from test_local_auth import factors

from otm.admin_cli import main
from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.local import LocalAuthFailure, LocalLogin, LocalSignIn, password_verifier, totp_step
from otm.auth.service import SessionFailure, SessionService
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.local_auth import SqlLocalAuth
from otm.storage.sessions import SqlSessionRepository
from otm.storage.tables import admin_session, administrator, audit_event, local_credential

pytestmark = pytest.mark.postgres
__all__ = ["factors"]
ORIGIN = "https://otm.example.test"
HEADERS = {"origin": ORIGIN, "x-otm-request": "1"}


# Enroll real factors through the actual operator transaction in a unique synthetic workspace.
@pytest.fixture
def login_case(pg_engine, tmp_path, factors):
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    policy = settings.local_auth.model_copy(
        update={"workspace_id": "local-" + uuid4().hex, "issuer": "urn:otm:local:" + str(uuid4())}
    )
    settings = settings.model_copy(update={"local_auth": policy})
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    custody = DirectorySecrets(root)
    clock = Mock(return_value=NOW)
    repository = SqlLocalAuth(pg_engine, settings, clock)
    existing, operator = repository.operator_status()
    assert existing is None
    seed = pyotp.random_base32()
    reference = custody.put(seed)
    step = totp_step(seed, pyotp.TOTP(seed).at(NOW), NOW, -1)
    identifier = repository.enroll(factors.verifier, reference, step, operator)
    clock.return_value = NOW + timedelta(seconds=30 * (step - int(NOW.timestamp()) // 30 + 1))
    service = LocalLogin(settings, repository, custody)
    grants = SqlAdministratorStore(
        pg_engine, clock, local_issuer=policy.issuer, trusted_issuers=frozenset({policy.issuer})
    )
    sessions = SessionService(SqlSessionRepository(pg_engine), grants, policy.issuer, clock)
    return SimpleNamespace(
        engine=pg_engine,
        settings=settings,
        policy=policy,
        clock=clock,
        repository=repository,
        service=service,
        custody=custody,
        root=root,
        seed=seed,
        reference=reference,
        identifier=identifier,
        factors=factors,
        sessions=sessions,
    )


# Construct a live proof without exporting raw factor values into logs or diagnostic assertions.
def command(c, **changes):
    values = dict(
        username="recovery-admin",
        password=c.factors.password,
        totp_code=pyotp.TOTP(c.seed).at(c.clock()),
    )
    values.update(changes)
    return LocalSignIn(**values)


# Count committed records directly under this scope, not from a service response or mocked SQL.
def records(c):
    with c.engine.connect() as connection:
        cred = (
            connection.execute(
                select(local_credential).where(local_credential.c.administrator_id == c.identifier)
            )
            .mappings()
            .one()
        )
        sessions = (
            connection.execute(
                select(admin_session).where(admin_session.c.workspace_id == c.policy.workspace_id)
            )
            .mappings()
            .all()
        )
        events = (
            connection.execute(
                select(audit_event).where(audit_event.c.workspace_id == c.policy.workspace_id)
            )
            .mappings()
            .all()
        )
    return cred, sessions, events


# True factors issue a safe cookie; repeating a consumed proof cannot create another session.
def test_real_http_login_replay_and_logout(login_case):
    c = login_case
    app = create_app(c.sessions, BrowserSettings(public_origin=ORIGIN), c.service)
    body = {
        "username": "recovery-admin",
        "password": c.factors.password,
        "totp_code": pyotp.TOTP(c.seed).at(c.clock()),
    }
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post("/api/auth/local/sign-in", json=body, headers=HEADERS)
        assert response.status_code == 200 and "set-cookie" in response.headers
        assert client.get("/api/session").status_code == 200
        again = client.post("/api/auth/local/sign-in", json=body, headers=HEADERS)
        assert again.status_code == 401 and "set-cookie" not in again.headers
        assert len(records(c)[1]) == 1
        assert client.post("/api/logout", headers=HEADERS).status_code == 204
        assert client.get("/api/session").status_code == 401
    assert records(c)[1][0]["revoked_at"] is not None
    assert sum(e["kind"] == "session_logged_out" for e in records(c)[2]) == 1


# First enrollment is permanent; status lookup and a second transaction cannot replace that account.
def test_bootstrap_cannot_repeat_and_enrollment_step_is_consumed(login_case):
    c = login_case
    with pytest.raises(LocalAuthFailure) as error:
        c.repository.operator_status()
    assert error.value.code == "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED"
    _, operator = c.repository.operator_status(reset=True)
    with pytest.raises(LocalAuthFailure):
        c.repository.enroll(c.factors.verifier, c.reference, 100, operator)
    original = records(c)
    c.clock.return_value = NOW
    with pytest.raises(LocalAuthFailure):
        c.service.sign_in(command(c))
    assert not records(c)[1] and original[0]["last_totp_step"] == records(c)[0]["last_totp_step"]


# A second successful sign-in rotates the handle and revokes the previous same-identity session.
def test_fresh_login_replaces_old_handle_without_reusing_it(login_case):
    c = login_case
    first = c.service.sign_in(command(c))
    c.clock.return_value += timedelta(seconds=30)
    second = c.service.sign_in(command(c), first.handle.get_secret_value())
    assert first.handle.get_secret_value() != second.handle.get_secret_value()
    with pytest.raises(SessionFailure):
        c.sessions.authenticate(first.handle.get_secret_value())
    assert c.sessions.authenticate(second.handle.get_secret_value()).session.id == second.session.id


# Cooldown is persisted across processes and has a fixed deadline, then allows legitimate recovery.
def test_shared_throttle_does_not_extend_cooldown(login_case):
    c = login_case
    for _ in range(c.policy.max_failures):
        with pytest.raises(LocalAuthFailure):
            c.service.sign_in(command(c, password="wrong synthetic password"))
    credential, sessions, events = records(c)
    due = credential["retry_after"]
    assert due == c.clock() + timedelta(seconds=c.policy.cooldown_seconds) and not sessions
    assert sum(e["kind"] == "local_sign_in_failed" for e in events) == 2
    another = LocalLogin(c.settings, c.repository, c.custody)
    with pytest.raises(LocalAuthFailure):
        another.sign_in(command(c))
    assert records(c)[0]["retry_after"] == due and len(records(c)[2]) == len(events)
    c.clock.return_value = due + timedelta(seconds=1)
    assert another.sign_in(command(c)).session.workspace_id == c.policy.workspace_id
    assert records(c)[0]["failed_attempts"] == 0 and records(c)[0]["retry_after"] is None


# Independent worker instances cannot consume one valid TOTP proof twice.
def test_concurrent_login_has_one_issued_session(login_case):
    c = login_case
    gate = Barrier(2)
    original = c.custody.get

    # Synchronize only after each material read has released its database connection.
    def retrieve(reference):
        seed = original(reference)
        gate.wait(timeout=10)
        return seed

    services = [LocalLogin(c.settings, c.repository, Mock(get=retrieve)) for _ in range(2)]

    # Each service runs its real password verification, final row locks and factor transaction.
    def sign_in(service):
        try:
            return service.sign_in(command(c)).session.id
        except LocalAuthFailure as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(sign_in, services))
    assert sum(value == 401 for value in results) == 1 and len(records(c)[1]) == 1


# An unavailable exact secret never falls back to password-only authentication.
def test_missing_custody_is_unavailable_and_creates_no_session(login_case):
    c = login_case
    (c.root / c.reference.split(":")[1]).unlink()
    with pytest.raises(LocalAuthFailure) as error:
        c.service.sign_in(command(c))
    assert error.value.status == 503 and not records(c)[1]


# Reset consumes the new enrollment code, changes the grant revision and invalidates old sessions.
def test_reset_replaces_credential_and_revokes_old_sessions(login_case):
    c = login_case
    first = c.service.sign_in(command(c))
    existing, operator = c.repository.operator_status(reset=True)
    new_seed = pyotp.random_base32()
    reference = c.custody.put(new_seed)
    code = pyotp.TOTP(new_seed).at(c.clock())
    step = totp_step(new_seed, code, c.clock(), -1)
    new_password = c.factors.password + "-reset"
    c.repository.enroll(
        password_verifier(new_password), reference, step, operator, expected=existing
    )
    with pytest.raises(SessionFailure):
        c.sessions.authenticate(first.handle.get_secret_value())
    with pytest.raises(LocalAuthFailure):
        c.service.sign_in(command(c, password=new_password, totp_code=code))
    assert records(c)[0]["last_totp_step"] == step
    c.clock.return_value += timedelta(seconds=30)
    result = c.service.sign_in(
        command(c, password=new_password, totp_code=pyotp.TOTP(new_seed).at(c.clock()))
    )
    assert result.session.entitlement_revision != existing.authorization_revision
    assert any(e["kind"] == "local_credentials_reset" for e in records(c)[2])
    assert (c.root / c.reference.split(":")[1]).exists()


# Audit or deferred COMMIT rejection rolls back factor consumption and emits no success cookie.
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_failed_login_transaction_never_emits_cookie(login_case, failure):
    c = login_case
    before = records(c)[0]["last_totp_step"]
    with c.engine.begin() as connection:
        connection.exec_driver_sql("""CREATE FUNCTION public.otm_test_reject_login() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled login failure'; END $$""")
        if failure == "audit":
            connection.exec_driver_sql("""
                CREATE TRIGGER otm_test_login_failure BEFORE INSERT ON public.audit_event
                FOR EACH ROW WHEN (NEW.kind='local_sign_in_succeeded')
                EXECUTE FUNCTION public.otm_test_reject_login()""")
        else:
            connection.exec_driver_sql("""
                CREATE CONSTRAINT TRIGGER otm_test_login_failure AFTER INSERT
                ON public.otm_admin_session DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
                EXECUTE FUNCTION public.otm_test_reject_login()""")
    try:
        with TestClient(
            create_app(c.sessions, BrowserSettings(public_origin=ORIGIN), c.service),
            base_url=ORIGIN,
        ) as client:
            response = client.post(
                "/api/auth/local/sign-in",
                json={
                    "username": "recovery-admin",
                    "password": c.factors.password,
                    "totp_code": pyotp.TOTP(c.seed).at(c.clock()),
                },
                headers=HEADERS,
            )
            assert response.status_code == 503 and "set-cookie" not in response.headers
        credential, sessions, events = records(c)
        assert credential["last_totp_step"] == before and not sessions and len(events) == 1
    finally:
        with c.engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER otm_test_login_failure ON public."
                + ("audit_event" if failure == "audit" else "otm_admin_session")
            )
            connection.exec_driver_sql("DROP FUNCTION public.otm_test_reject_login()")


# The real CLI uses privileged credentials and live factor verification, and refuses every reseed.
def test_real_interactive_cli_bootstrap_is_one_time(pg_engine, tmp_path, factors, monkeypatch):
    base = Path(__file__).resolve().parents[1] / "config/application.toml"
    workspace = "cli-" + uuid4().hex
    config = tmp_path / "application.toml"
    config.write_text(
        base.read_text().replace('workspace_id = "example-org"', f'workspace_id = "{workspace}"')
    )
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OTM_DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))

    # Read the just-staged synthetic seed only inside the private test to produce a real
    # current OTP.
    def prompt(message):
        if message.strip() == "Current authenticator code:":
            return pyotp.TOTP(next(root.iterdir()).read_text()).now()
        return factors.password

    argv = ["bootstrap", "--config", str(config), "--secret-directory", str(root)]
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("otm.admin_cli.getpass.getpass", side_effect=prompt),
        patch("otm.admin_cli.print"),
    ):
        assert main(argv) == 0
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("otm.admin_cli.getpass.getpass") as prompts,
        patch("otm.admin_cli.print") as output,
    ):
        assert main(argv) == 1
        prompts.assert_not_called()
        assert json_code(output) == "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED"
    assert len(list(root.iterdir())) == 1
    with pg_engine.connect() as connection:
        assert (
            len(
                connection.execute(
                    select(administrator.c.id).where(administrator.c.workspace_id == workspace)
                ).all()
            )
            == 1
        )


# Extract only the fixed CLI error code; do not retain enrollment output in the test evidence.
def json_code(output):
    import json

    return json.loads(output.call_args.args[0])["code"]


# Minimal API privileges permit real sign-in while denying the operator status boundary.
def test_restricted_api_role_can_login_but_cannot_bootstrap(login_case):
    c = login_case
    with c.engine.begin() as connection:
        connection.exec_driver_sql("CREATE ROLE otm_local_login_api_test NOLOGIN")
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_local_login_api_test")
        connection.exec_driver_sql(
            "GRANT SELECT ON public.otm_administrator,public.otm_local_credential "
            "TO otm_local_login_api_test"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(id) ON public.otm_administrator TO otm_local_login_api_test"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(last_totp_step,failed_attempts,failure_window_started_at,retry_after) "
            "ON public.otm_local_credential TO otm_local_login_api_test"
        )
        connection.exec_driver_sql(
            "GRANT INSERT,SELECT ON public.otm_admin_session TO otm_local_login_api_test"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(revoked_at) ON public.otm_admin_session TO otm_local_login_api_test"
        )
        connection.exec_driver_sql("GRANT INSERT ON public.audit_event TO otm_local_login_api_test")

    # Keep every role change local to this disposable transaction.
    class RoleEngine:
        # Expose only scoped transaction connections, never owner credentials or role fallbacks.
        @contextmanager
        def begin(self):
            with c.engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL ROLE otm_local_login_api_test")
                yield connection

        # Read snapshots under the same actual restricted role used for issuance.
        def connect(self):
            return self.begin()

    repository = SqlLocalAuth(RoleEngine(), c.settings, c.clock)
    with pytest.raises(LocalAuthFailure) as error:
        repository.operator_status()
    assert error.value.status == 403
    service = LocalLogin(c.settings, repository, c.custody)
    issued = service.sign_in(command(c))
    assert issued.session.subject == str(c.identifier)
    SessionService(SqlSessionRepository(RoleEngine()), Mock(), c.policy.issuer, c.clock).logout(
        issued.handle.get_secret_value()
    )
    assert records(c)[1][0]["revoked_at"] is not None
    assert any(e["kind"] == "session_logged_out" for e in records(c)[2])


# Changing the installation issuer cannot use reset to overwrite the existing local identity.
def test_reset_cannot_rebind_a_different_issuer(login_case):
    c = login_case
    settings = c.settings.model_copy(
        update={
            "local_auth": c.policy.model_copy(update={"issuer": "urn:otm:local:" + str(uuid4())})
        }
    )
    repository = SqlLocalAuth(c.engine, settings, c.clock)
    with pytest.raises(LocalAuthFailure) as error:
        repository.operator_status(reset=True)
    assert error.value.code == "LOCAL_CREDENTIALS_CHANGED"
    existing, operator = c.repository.operator_status(reset=True)
    with pytest.raises(LocalAuthFailure):
        repository.enroll(c.factors.verifier, c.reference, 100, operator, expected=existing)
    assert not records(c)[1]


# Concurrent fully verified bootstrap transactions leave exactly one grant, credential and audit.
def test_concurrent_full_enrollment_commits_only_one_identity(login_case):
    from sqlalchemy.exc import IntegrityError

    c = login_case
    settings = c.settings.model_copy(
        update={
            "local_auth": c.policy.model_copy(update={"workspace_id": "concurrent-" + uuid4().hex})
        }
    )
    base = SqlLocalAuth(c.engine, settings, c.clock)
    _, operator = base.operator_status()
    gate = Barrier(2)
    references = [c.custody.put(pyotp.random_base32()) for _ in range(2)]

    # Synchronize after each physical transaction opens, before either authority check proceeds.
    class ConcurrentEngine:
        # Retain real READ COMMITTED connections and commit/rollback ownership.
        @contextmanager
        def begin(self):
            with c.engine.begin() as connection:
                gate.wait(timeout=10)
                yield connection

    repository = SqlLocalAuth(ConcurrentEngine(), settings, c.clock)

    # Both contenders already possess verified synthetic enrollment material.
    def enroll(reference):
        try:
            return repository.enroll(c.factors.verifier, reference, 100, operator)
        except LocalAuthFailure as error:
            assert error.code == "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED"
            return "refused"
        except IntegrityError as error:
            assert error.orig.sqlstate == "23505"
            assert error.orig.diag.constraint_name == "uq_administrator_recovery"
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(enroll, references))
    assert results.count("refused") == 1
    with c.engine.connect() as connection:
        for table in (administrator, local_credential, audit_event):
            assert (
                len(
                    connection.execute(
                        select(table).where(
                            table.c.workspace_id == settings.local_auth.workspace_id
                        )
                    ).all()
                )
                == 1
            )


# Logout has no IdP dependency and must not claim server success if its audit/commit rolls back.
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_logout_audit_failure_rolls_back_and_clears_browser_cookie(login_case, failure):
    c = login_case
    issued = c.service.sign_in(command(c))
    before = len(records(c)[2])
    with c.engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE FUNCTION public.otm_test_reject_logout() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled logout failure'; END $$""")
        if failure == "audit":
            connection.exec_driver_sql("""CREATE TRIGGER otm_test_logout_failure BEFORE INSERT
                ON public.audit_event FOR EACH ROW WHEN (NEW.kind='session_logged_out')
                EXECUTE FUNCTION public.otm_test_reject_logout()""")
        else:
            connection.exec_driver_sql("""CREATE CONSTRAINT TRIGGER otm_test_logout_failure
                AFTER UPDATE ON public.otm_admin_session DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW WHEN (NEW.revoked_at IS NOT NULL)
                EXECUTE FUNCTION public.otm_test_reject_logout()""")
    try:
        with TestClient(
            create_app(c.sessions, BrowserSettings(public_origin=ORIGIN)), base_url=ORIGIN
        ) as client:
            response = client.post(
                "/api/logout",
                headers={**HEADERS, "cookie": COOKIE_NAME + "=" + issued.handle.get_secret_value()},
            )
            assert response.status_code == 503 and "Max-Age=0" in response.headers["set-cookie"]
        _, sessions, events = records(c)
        assert len(sessions) == 1 and sessions[0]["revoked_at"] is None and len(events) == before
    finally:
        with c.engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER otm_test_logout_failure ON public."
                + ("audit_event" if failure == "audit" else "otm_admin_session")
            )
            connection.exec_driver_sql("DROP FUNCTION public.otm_test_reject_logout()")
