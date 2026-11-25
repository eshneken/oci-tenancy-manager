"""Hosted startup rejects unsafe dependencies and keeps health, auth and job lifecycle separate."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from otm import hosted_database as database
from otm import hosted_runtime as runtime
from otm.app import create_app
from otm.email_policy import EmailPolicyBlocked, MailPolicy
from otm.notifications.runtime import compose_notifications
from otm.providers.email_contacts import activation_address, identity_contacts
from otm.settings import ApplicationSettings, load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config"


# These synthetic release inputs reuse strict hosted policies and explicit local-recovery identity.
@pytest.fixture
def hosted(tmp_path):
    path = tmp_path / "application.toml"
    path.write_text(
        (CONFIG / "staging.application.toml").read_text()
        + '\n[recovery_console]\nallowed_cidrs=["198.51.100.0/24"]\n'
    )
    settings = load_settings(path).model_copy(
        update={"local_auth": load_settings(CONFIG / "application.toml").local_auth}
    )
    frontend = tmp_path / "public"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("<html>synthetic hosted shell</html>")
    engine = MagicMock()
    engine.get_execution_options.return_value = {"otm_hosted_role": "api"}
    engine.url = make_url("postgresql+psycopg://runtime:synthetic@db.example.test:5432/otm")
    return SimpleNamespace(settings=settings, path=path, engine=engine, frontend=frontend)


# Hosted settings never enable loopback public serving, a local profile or mismatched email origin.
@pytest.mark.parametrize(
    "fault",
    [
        "environment",
        "absent",
        "localhost",
        "loopback",
        "unspecified",
        "proxy",
        "pool",
        "grace",
        "local",
    ],
)
def test_hosted_settings_reject_bad_profiles(hosted, fault):
    settings = hosted.settings
    if fault == "environment":
        environment = "production"
    else:
        environment = "staging"
        raw = settings.model_dump()
        if fault == "absent":
            raw["hosted"] = None
        elif fault in {"localhost", "loopback", "unspecified"}:
            raw["hosted"]["public_origin"] = {
                "localhost": "https://localhost:8443",
                "loopback": "https://127.0.0.2:8443",
                "unspecified": "https://0.0.0.0:8443",
            }[fault]
            raw["notifications"]["application_origin"] = raw["hosted"]["public_origin"]
        elif fault == "proxy":
            raw["hosted"]["trusted_proxy_cidrs"] = ["0.0.0.0/0"]
        elif fault == "pool":
            raw["hosted"]["database_pool_size"] = 17
        elif fault == "grace":
            raw["hosted"]["worker_shutdown_seconds"] = 300
        else:
            raw["environment"] = "local"
        settings = raw
    with pytest.raises(ValueError):
        database.hosted_settings(settings, environment)


# Pool construction always preserves explicit verified TLS, role markers and bounded connection use.
@pytest.mark.parametrize("role", ["api", "worker", "migration"])
def test_hosted_pool_contract(tmp_path, role):
    ca = tmp_path / "ca.crt"
    ca.write_text("synthetic certificate fixture")
    with (
        patch.object(database.ssl, "create_default_context") as context,
        patch.object(database, "create_engine") as factory,
    ):
        database.hosted_engine(
            "postgresql+psycopg://runtime:synthetic@db.example.test:5432/otm", str(ca), role=role
        )
    context.assert_called_once_with(cafile=str(ca))
    options = factory.call_args.kwargs
    assert options["connect_args"]["sslmode"] == "verify-full"
    assert options["connect_args"]["sslrootcert"] == str(ca)
    assert (
        options["pool_timeout"] == 1 and options["max_overflow"] == 0 and options["hide_parameters"]
    )
    assert options["pool_size"] == (1 if role == "migration" else 2)
    factory.return_value.execution_options.assert_called_once_with(otm_hosted_role=role)


# Remote startup never inherits local TLS exceptions, environment redirects or libpq URL overrides.
@pytest.mark.parametrize(
    "fault",
    [
        "ip",
        "localhost",
        "suffix",
        "bare",
        "invalid",
        "ca",
        "relative",
        "empty",
        "large",
        "role",
        "pool",
        "bool",
        "query",
        "env",
    ],
)
def test_hosted_pool_denials(tmp_path, monkeypatch, fault):
    ca = tmp_path / "ca.crt"
    ca.write_text("synthetic certificate fixture")
    host, role, pool = "db.example.test", "api", 2
    suffix = ""
    if fault in {"ip", "localhost", "suffix", "bare", "invalid"}:
        host = {
            "ip": "127.0.0.2",
            "localhost": "localhost",
            "suffix": "db.localhost",
            "bare": "database",
            "invalid": "db_bad.example.test",
        }[fault]
    elif fault == "ca":
        ca = None
    elif fault == "relative":
        ca = Path("relative-ca.crt")
    elif fault == "empty":
        ca.write_text("")
    elif fault == "large":
        ca.write_bytes(b"x" * 1048577)
    elif fault == "role":
        role = "operator"
    elif fault in {"pool", "bool"}:
        pool = 0 if fault == "pool" else True
    elif fault == "query":
        suffix = "?sslmode=disable"
    elif fault == "env":
        monkeypatch.setenv("PGHOSTADDR", "another.example.test")
    with patch.object(database, "create_engine") as factory, pytest.raises((ValueError, OSError)):
        database.hosted_engine(
            f"postgresql+psycopg://runtime:synthetic@{host}:5432/otm{suffix}",
            str(ca) if ca else None,
            role=role,
            pool_size=pool,
        )
    factory.assert_not_called()


# Schema/current-role/TLS observations all matter; raw driver exceptions cannot leak through health.
@pytest.mark.parametrize("fault", [None, "schema", "role", "tls", "missing", "error"])
def test_bounded_database_readiness(fault):
    engine, connection = MagicMock(), MagicMock()
    engine.begin.return_value = nullcontext(connection)
    row = {"schema_current": True, "safe_role": True, "transport_secure": True}
    if fault in {"schema", "role", "tls"}:
        row[{"schema": "schema_current", "role": "safe_role", "tls": "transport_secure"}[fault]] = (
            False
        )
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        None if fault == "missing" else row
    )
    if fault == "error":
        connection.execute.side_effect = RuntimeError("private DB details")
    assert database.database_ready(engine) is (fault is None)
    assert (
        connection.exec_driver_sql.call_args_list[0].args[0]
        == "SET LOCAL statement_timeout='1000ms'"
    )
    assert connection.exec_driver_sql.call_args_list[1].args[0] == "SET LOCAL lock_timeout='1000ms'"


# Runtime role denial and a concurrent migrator stop before Alembic can issue any schema changes.
@pytest.mark.parametrize("fault", [None, "role", "lock"])
def test_migration_admission_and_connection(fault):
    engine, connection = MagicMock(), MagicMock()
    engine.begin.return_value = nullcontext(connection)
    connection.scalar.side_effect = [fault != "role", fault != "lock"]
    with patch.object(database.command, "upgrade") as upgrade:
        if fault:
            with pytest.raises(ValueError):
                database.migrate_database(engine)
            upgrade.assert_not_called()
        else:
            revision = database.migrate_database(engine)
            config, target = upgrade.call_args.args
            assert config.attributes["connection"] is connection and target == "head" and revision


# Missing installed/source migration assets fail rather than reading a CWD or operator override.
def test_migration_assets_required():
    with (
        patch.object(Path, "is_file", return_value=False),
        pytest.raises(ValueError, match="HOSTED_MIGRATION_ASSETS_UNAVAILABLE"),
    ):
        database.migration_configuration()


# An unset/failing readiness dependency is503; it never changes process liveness.
@pytest.mark.parametrize("fault", ["absent", "false", "exception"])
def test_process_health_is_independent(fault):
    callback = None if fault == "absent" else Mock(return_value=False)
    if fault == "exception":
        callback.side_effect = RuntimeError("private DB details")
    with TestClient(create_app(readiness=callback)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503 and response.json() == {"status": "unavailable"}
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/health/live").status_code == 200


# Trust only explicitly configured proxy peers; preserve browser guards and close the owned pool.
def test_hosted_api_health_proxy_and_shutdown(hosted):
    with patch.object(runtime, "database_ready", return_value=True) as ready:
        app = runtime.create_hosted_application(
            hosted.settings, "staging", hosted.engine, Mock(), frontend=hosted.frontend
        )
        with TestClient(
            app, base_url="http://otm.example.test", client=("192.0.2.10", 40000)
        ) as client:
            assert client.get("/", headers={"x-forwarded-proto": "https"}).status_code == 200
            assert (
                client.get("/api/session", headers={"x-forwarded-proto": "https"}).status_code
                == 401
            )
            assert client.get("/health/ready").status_code == 200
            ready.return_value = False
            assert client.get("/health/ready").status_code == 503
            assert client.get("/health/live").status_code == 200
        hosted.engine.dispose.assert_called_once()
        assert TestClient(app).get("/health/ready").status_code == 503
    with patch.object(runtime, "database_ready", return_value=True):
        other = runtime.create_hosted_application(
            hosted.settings, "staging", hosted.engine, Mock(), frontend=hosted.frontend
        )
        with TestClient(
            other, base_url="http://otm.example.test", client=("198.51.100.9", 40000)
        ) as client:
            assert client.get("/", headers={"x-forwarded-proto": "https"}).status_code == 400


# No missing identity, unverified database or local secret fallback can produce a hosted API.
@pytest.mark.parametrize("fault", ["mfa", "identity", "role", "readiness", "frontend"])
def test_hosted_api_startup_denied(hosted, fault):
    settings, secrets = hosted.settings, Mock()
    if fault == "mfa":
        secrets = None
    elif fault == "identity":
        settings = settings.model_copy(update={"local_auth": None})
    elif fault == "role":
        hosted.engine.get_execution_options.return_value = {"otm_hosted_role": "migration"}
    elif fault == "frontend":
        hosted.frontend = hosted.frontend / "absent"
    with (
        patch.object(runtime, "database_ready", return_value=fault != "readiness"),
        pytest.raises(RuntimeError, match="^HOSTED_API_STARTUP_FAILED$"),
    ):
        runtime.create_hosted_application(
            settings, "staging", hosted.engine, secrets, frontend=hosted.frontend
        )
    hosted.engine.dispose.assert_called_once()


# Qualified composition registers every fixed capability before polling, with one slot per pod.
@pytest.mark.parametrize(
    "fault", [None, "missing", "queue", "retry", "no_composition", "db", "role", "error"]
)
def test_hosted_worker_guard_and_drain(hosted, fault):
    hosted.engine.get_execution_options.return_value = {
        "otm_hosted_role": "worker" if fault != "role" else "migration"
    }
    native = MagicMock()
    expected_queue = runtime.workspace_queue(hosted.settings.local_auth.workspace_id)
    native.tasks = {
        name: SimpleNamespace(queue=expected_queue, retry_strategy=None)
        for name in runtime.REQUIRED_OPERATION_TASKS
    }
    if fault == "missing":
        native.tasks.pop(next(iter(native.tasks)))
    elif fault in {"queue", "retry"}:
        task = next(iter(native.tasks.values()))
        if fault == "queue":
            task.queue = "another-queue"
        else:
            task.retry_strategy = object()
    elif fault == "error":
        native.run_worker.side_effect = RuntimeError("private worker details")
    register = None if fault == "no_composition" else Mock()
    options = dict(connect_timeout=2, sslmode="verify-full", sslrootcert="/synthetic/ca.crt")
    with (
        patch.object(runtime, "database_ready", return_value=fault != "db"),
        patch.object(
            runtime, "hosted_connection_options", return_value=(hosted.engine.url, options)
        ),
        patch.object(runtime.procrastinate, "App", return_value=native),
    ):
        if fault:
            with pytest.raises(RuntimeError, match="^HOSTED_WORKER_FAILED$"):
                runtime.run_hosted_worker(
                    hosted.settings, "staging", hosted.engine, "/synthetic/ca.crt", register
                )
            if fault != "error":
                native.run_worker.assert_not_called()
        else:
            runtime.run_hosted_worker(
                hosted.settings, "staging", hosted.engine, "/synthetic/ca.crt", register, once=True
            )
            options = native.run_worker.call_args.kwargs
            assert options["concurrency"] == 1 and options["install_signal_handlers"]
            assert options["shutdown_graceful_timeout"] == 120 and not options["wait"]
            assert options["delete_jobs"] == "never"
            register.assert_called_once_with(native, hosted.engine, expected_queue)
    hosted.engine.dispose.assert_called_once()


# The CLI never accepts target URLs/passwords in argv or leaks failure details to shared logs.
@pytest.mark.parametrize("fault", [None, "config", "database", "migration", "arguments"])
def test_migration_cli(hosted, monkeypatch, capsys, fault):
    monkeypatch.setenv("OTM_DATABASE_URL", "synthetic-private-database-url")
    monkeypatch.setenv("OTM_DATABASE_CA_FILE", "/synthetic/ca.crt")
    args = ["migrate", "--config", str(hosted.path), "--expected-environment", "staging"]
    if fault == "arguments":
        args += ["--password", "never-echo-this"]
    with (
        patch.object(runtime, "hosted_engine", return_value=hosted.engine) as factory,
        patch.object(
            runtime, "migrate_database", return_value="0028_signing_credentials"
        ) as migrate,
    ):
        if fault == "config":
            args[2] = str(hosted.path / "absent")
        elif fault == "database":
            factory.side_effect = RuntimeError("never-echo-this")
        elif fault == "migration":
            migrate.side_effect = RuntimeError("never-echo-this")
        assert runtime.main(args) == (0 if fault is None else 1)
    output = capsys.readouterr().out
    assert "never-echo-this" not in output and "synthetic-private-database-url" not in output
    assert output == (
        "HOSTED_MIGRATION_COMPLETE:0028_signing_credentials\n"
        if fault is None
        else "HOSTED_MIGRATION_FAILED\n"
    )


# Uvicorn cannot add an independent trust-all proxy layer or outlive the120-second pod grace.
def test_api_server_shutdown_and_proxy_contract():
    application = Mock()
    with patch.object(runtime.uvicorn, "run") as serve:
        runtime.serve_hosted_api(application)
    assert serve.call_args.args == (application,)
    options = serve.call_args.kwargs
    assert options["proxy_headers"] is False and options["workers"] == 1
    assert options["access_log"] is False and options["timeout_graceful_shutdown"] == 90
    assert options["host"] == "0.0.0.0" and options["port"] == 8080


# Composition must keep a delivery handler for previously queued notices when new mail is disabled.
def test_disabled_email_still_requires_existing_delivery_handler(hosted):
    assert not hosted.settings.notifications.enabled
    assert runtime.NOTIFICATION_TASK in runtime.REQUIRED_OPERATION_TASKS


# An enabled delivery profile must never silently discard lifecycle notices during API composition.
@pytest.mark.parametrize("notifier_policy", [None, "wrong", "configured"])
def test_hosted_api_requires_notification_composition(hosted, notifier_policy):
    settings = hosted.settings.model_copy(
        update={"notifications": hosted.settings.notifications.model_copy(update={"enabled": True})}
    )
    notifier, _, _ = compose_notifications(settings, "synthetic-queue")
    if notifier_policy is None:
        notifier = None
    elif notifier_policy == "wrong":
        notifier.policy = MailPolicy(environment="production")
    with patch.object(runtime, "database_ready", return_value=True):
        if notifier_policy == "configured":
            app = runtime.create_hosted_application(
                settings,
                "staging",
                hosted.engine,
                Mock(),
                frontend=hosted.frontend,
                notifier=notifier,
            )
            with TestClient(app) as client:
                assert client.get("/health/ready").status_code == 200
        else:
            with pytest.raises(RuntimeError, match="HOSTED_API_STARTUP_FAILED"):
                runtime.create_hosted_application(
                    settings,
                    "staging",
                    hosted.engine,
                    Mock(),
                    frontend=hosted.frontend,
                    notifier=notifier,
                )
    hosted.engine.dispose.assert_called_once()


# A missing source preserves legacy startup; an operator-owned census opt-in binds both trust flags.
def test_hosted_organization_source_is_optional_and_explicit():
    settings = load_settings(CONFIG / "staging.application.toml").model_dump()
    source = settings["hosted"].pop("organization_source")
    assert runtime.organization_template(ApplicationSettings.model_validate(settings)) is None

    settings["hosted"]["organization_source"] = {**source, "census_contract_confirmed": True}
    policy = runtime.organization_template(ApplicationSettings.model_validate(settings)).policy
    assert policy.authoritative and policy.census_contract_confirmed
    assert not policy.allow_undated_development_metadata


# Hosted source config accepts only deployment settings and uses the correct environment mailbox.
@pytest.mark.parametrize(
    ("environment", "fields"),
    [
        ("staging", {"administrator_alert_email": "unexpected@example.test"}),
        ("staging", {"root_email": "employee@example.test"}),
        ("staging", {"source_id": " "}),
        ("staging", {"max_age_seconds": 0}),
        ("production", {"administrator_alert_email": None}),
        ("production", {"administrator_alert_email": "one@example.test,two@example.test"}),
    ],
)
def test_hosted_organization_source_rejects_invalid_scope_and_alert_mailbox(environment, fields):
    raw = load_settings(CONFIG / f"{environment}.application.toml").model_dump()
    raw["hosted"]["organization_source"].update(fields)
    with pytest.raises(ValueError):
        ApplicationSettings.model_validate(raw)


# Real directory addresses remain identity values while staging SMTP and OCI route to one mailbox.
def test_hosted_staging_mail_uses_one_destination_for_organization_contacts():
    settings = load_settings(CONFIG / "staging.application.toml")
    raw = settings.model_dump()
    raw["notifications"]["enabled"] = True
    settings = ApplicationSettings.model_validate(raw)
    override = settings.testing.email_override
    policy = settings.mail_policy()
    notifier, _, _ = compose_notifications(settings, "synthetic-queue")
    identity = "employee@directory.example.test"
    route = policy.route(identity)
    assert route.original_email == identity
    assert notifier.policy.guard(route) == override
    assert (
        activation_address(
            policy, SimpleNamespace(email_contacts=SimpleNamespace(activation=route))
        )
        == override
    )
    contact = identity_contacts(policy, identity, route)
    assert contact.username == identity
    assert contact.primary_email == contact.recovery_email == override
    with pytest.raises(EmailPolicyBlocked):
        policy.guard_address(identity)
