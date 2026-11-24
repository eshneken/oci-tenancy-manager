"""Hosted TLS, schema ownership, real authentication and native queue execution on disposable PG."""

import os
import secrets
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import procrastinate
import pyotp
import pytest
from docker_test_resources import remove_owned
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL
from test_local_auth import factors

from otm import hosted_runtime as runtime
from otm.auth.local import totp_step
from otm.hosted_database import database_ready, hosted_engine, migrate_database
from otm.settings import load_settings
from otm.storage.local_auth import SqlLocalAuth

pytestmark = pytest.mark.postgres
__all__ = ["factors"]
IMAGE = "postgres:18.7@sha256:eb63372c1e05c755f55fa30cbd07aecc443676fc6c0fa90b9002d01537841e1a"
HOST = "otm-db.example.test"


# Keep generated test credentials out of fixture representations and failed assertion diagnostics.
class TlsDatabase(SimpleNamespace):
    # Diagnostics identify the disposable fixture without serializing its credential-bearing fields.
    def __repr__(self):
        return "DisposableTlsDatabase()"


# Test-only MFA custody is in memory; production must supply an explicit Vault capability.
class FakeMfa:
    # Opaque references hold generated transient seeds in this disposable test process only.
    def __init__(self):
        self.values = {}

    # Enrollment uses immutable random references without storing factors in public fixtures.
    def put(self, seed):
        reference = "synthetic-mfa:" + uuid4().hex
        self.values[reference] = seed
        return reference

    # Missing references fail, never falling back to local files or another secret version.
    def get(self, reference):
        return self.values[reference]


# Run fixed local tooling with captured diagnostics; passwords/private keys never enter argv/output.
def tool(arguments, *, input=None, env=None):
    return subprocess.run(
        arguments, input=input, env=env, check=True, capture_output=True, timeout=60
    )


# Create a dedicated CA and signed DNS-only server leaf, with all private material outside source.
def tls_files(directory):
    tool(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "ca.key"),
            "-out",
            str(directory / "ca.crt"),
            "-days",
            "2",
            "-subj",
            "/CN=OTM disposable test CA",
        ]
    )
    tool(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / "server.key"),
            "-out",
            str(directory / "server.csr"),
            "-subj",
            "/CN=" + HOST,
        ]
    )
    extension = directory / "server.ext"
    extension.write_text(
        "subjectAltName=DNS:" + HOST + "\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n"
    )
    tool(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(directory / "server.csr"),
            "-CA",
            str(directory / "ca.crt"),
            "-CAkey",
            str(directory / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(directory / "server.crt"),
            "-days",
            "2",
            "-extfile",
            str(extension),
        ]
    )
    for name in ("ca.key", "server.key"):
        (directory / name).chmod(0o600)


# Wait only on this uniquely named owned container; no saved application database is inspected.
def await_database(client, name):
    for _ in range(100):
        result = subprocess.run(
            [client, "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "otm_test"],
            check=False,
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return
        time.sleep(0.1)
    raise RuntimeError("DISPOSABLE_TLS_POSTGRES_NOT_READY")


# The test-only DNS override routes a synthetic certified hostname to the owned loopback server.
# Libpq still verifies that exact hostname and the supplied CA; no TLS check is disabled.
def loopback_dns(engine):
    # SQLAlchemy's documented connection event supplies only the transport address in tests.
    @event.listens_for(engine, "do_connect")
    def resolve(dialect, record, args, options):
        options["hostaddr"] = "127.0.0.1"

    return engine


# One disposable TLS server per module retains migration/auth history across isolated test cases.
@pytest.fixture(scope="module")
def tls_database(tmp_path_factory):
    client = shutil.which("docker")
    assert client is not None
    directory = tmp_path_factory.mktemp("hosted-tls")
    tls_files(directory)
    owner = uuid4().hex
    name = "otm-hosted-tls-" + owner[:16]
    password = secrets.token_urlsafe(32)
    environment = {**os.environ, "POSTGRES_PASSWORD": password}
    engines = []
    try:
        tool(
            [
                client,
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                "otm.hosted.tls=" + owner,
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                "POSTGRES_USER=otm_test",
                "-e",
                "POSTGRES_DB=otm_backend_test",
                "-p",
                "127.0.0.1::5432",
                IMAGE,
            ],
            env=environment,
        )
        await_database(client, name)
        port = int(
            tool([client, "port", name, "5432/tcp"]).stdout.decode().strip().rsplit(":", 1)[1]
        )
        owner_engine = create_engine(
            URL.create(
                "postgresql+psycopg",
                username="otm_test",
                password=password,
                host="127.0.0.1",
                port=port,
                database="otm_backend_test",
            ),
            hide_parameters=True,
        )
        engines.append(owner_engine)
        for filename in ("server.key", "server.crt"):
            target = "/var/lib/postgresql/" + filename
            tool(
                [
                    client,
                    "exec",
                    "-i",
                    name,
                    "sh",
                    "-c",
                    "umask 077; cat > " + target + "; chown postgres:postgres " + target,
                ],
                input=(directory / filename).read_bytes(),
            )
        with owner_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql("ALTER SYSTEM SET ssl='on'")
            connection.exec_driver_sql(
                "ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/server.crt'"
            )
            connection.exec_driver_sql(
                "ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/server.key'"
            )
        owner_engine.dispose()
        tool([client, "restart", name])
        await_database(client, name)
        # Docker may allocate a new ephemeral host port on restart; never reuse a stale endpoint.
        port = int(
            tool([client, "port", name, "5432/tcp"]).stdout.decode().strip().rsplit(":", 1)[1]
        )
        owner_engine = create_engine(owner_engine.url.set(port=port), hide_parameters=True)
        engines.append(owner_engine)
        passwords = {
            role: secrets.token_urlsafe(32) for role in ("otm_migration", "otm_api", "otm_worker")
        }
        with owner_engine.begin() as connection:
            raw = connection.connection.driver_connection
            for role, value in passwords.items():
                raw.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(value)
                    )
                )
            connection.exec_driver_sql("ALTER SCHEMA public OWNER TO otm_migration")
            connection.exec_driver_sql("GRANT CREATE ON DATABASE otm_backend_test TO otm_migration")
        state = TlsDatabase(
            client=client,
            name=name,
            owner=owner,
            directory=directory,
            port=port,
            owner_engine=owner_engine,
            passwords=passwords,
            engines=engines,
        )
        yield state
    finally:
        for engine in engines:
            engine.dispose()
        # Verify exact ownership before removing a container, even after partial fixture failure.
        remove_owned(client, name, "otm.hosted.tls", owner)


# Every runtime test obtains a fresh pool through the actual hosted verifier and TLS configuration.
def pool(c, role, *, host=HOST, ca=None):
    user = "otm_" + role
    url = URL.create(
        "postgresql+psycopg",
        username=user,
        password=c.passwords[user],
        host=host,
        port=c.port,
        database="otm_backend_test",
    )
    engine = loopback_dns(
        hosted_engine(
            url.render_as_string(hide_password=False),
            str(c.directory / "ca.crt") if ca is None else str(ca),
            role=role,
        )
    )
    c.engines.append(engine)
    return engine


# Real forward migrations run under a dedicated non-superuser, and replay remains a no-op.
@pytest.fixture(scope="module")
def migrated(tls_database):
    c = tls_database
    c.migration = pool(c, "migration")
    c.head = migrate_database(c.migration)
    assert migrate_database(c.migration) == c.head
    with c.owner_engine.begin() as connection:
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_api,otm_worker")
        connection.exec_driver_sql(
            "GRANT SELECT ON public.alembic_version,public.otm_administrator TO otm_api,otm_worker"
        )
        # Row locking the exact administrator during sign-in requires UPDATE on one column.
        connection.exec_driver_sql("GRANT UPDATE(id) ON public.otm_administrator TO otm_api")
        connection.exec_driver_sql(
            "GRANT SELECT ON public.otm_local_credential,public.otm_admin_session,"
            "public.audit_event TO otm_api"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(last_totp_step,failed_attempts,failure_window_started_at,retry_after) "
            "ON public.otm_local_credential TO otm_api"
        )
        connection.exec_driver_sql(
            "GRANT INSERT ON public.otm_admin_session,public.audit_event TO otm_api"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(last_seen_at,revoked_at) ON public.otm_admin_session TO otm_api"
        )
        connection.exec_driver_sql(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON public.procrastinate_jobs,"
            "public.procrastinate_events,public.procrastinate_workers,"
            "public.procrastinate_periodic_defers TO otm_worker"
        )
        connection.exec_driver_sql("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO otm_worker")
    return c


# TLS must encrypt runtime traffic and reject both a wrong hostname and a different trust root.
def test_real_tls_and_runtime_role(migrated, tmp_path):
    c = migrated
    api = pool(c, "api")
    assert database_ready(api)
    with api.connect() as connection:
        assert (
            connection.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"))
            is True
        )
    assert not database_ready(pool(c, "api", host="wrong.example.test"))
    other = tmp_path / "untrusted"
    other.mkdir()
    tls_files(other)
    assert not database_ready(pool(c, "api", ca=other / "ca.crt"))
    assert not database_ready(c.migration)
    with pytest.raises(ValueError, match="DEDICATED_MIGRATION_OWNER_REQUIRED"):
        migrate_database(api)


# The advisory lock excludes another owner immediately, and failed transactional DDL rolls back.
def test_migration_lock_and_rollback(migrated):
    c = migrated
    with c.migration.begin() as connection:
        assert connection.scalar(text("SELECT pg_try_advisory_xact_lock(5198925,1)")) is True
        with pytest.raises(ValueError, match="SCHEMA_MIGRATION_ALREADY_RUNNING"):
            migrate_database(pool(c, "migration"))

    # Fail after synthetic DDL within the owned transaction; frozen migrations stay unchanged.
    def fail_upgrade(config, revision):
        config.attributes["connection"].exec_driver_sql(
            "CREATE TABLE public.otm_test_rollback(id integer)"
        )
        raise RuntimeError("synthetic migration failure")

    with (
        patch("otm.hosted_database.command.upgrade", side_effect=fail_upgrade),
        pytest.raises(RuntimeError),
    ):
        migrate_database(c.migration)
    with c.migration.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.otm_test_rollback')")) is None
    assert migrate_database(c.migration) == c.head


# Actual non-owner auth/session writes use TLS; only MFA custody is an explicit in-memory boundary.
def test_hosted_authenticated_api_and_health(migrated, tmp_path, factors):
    c = migrated
    config = Path(__file__).resolve().parents[1] / "config"
    path = tmp_path / "application.toml"
    path.write_text(
        (config / "staging.application.toml").read_text()
        + '\n[recovery_console]\nallowed_cidrs=["198.51.100.0/24"]\n'
    )
    policy = load_settings(config / "application.toml").local_auth.model_copy(
        update={"workspace_id": "hosted-" + uuid4().hex, "issuer": "urn:otm:hosted:" + uuid4().hex}
    )
    settings = load_settings(path).model_copy(update={"local_auth": policy})
    now = datetime.now(UTC)
    clock = Mock(return_value=now)
    custody = FakeMfa()
    repository = SqlLocalAuth(c.migration, settings, clock)
    existing, operator = repository.operator_status()
    seed = pyotp.random_base32()
    reference = custody.put(seed)
    step = totp_step(seed, pyotp.TOTP(seed).at(now), now, -1)
    repository.enroll(factors.verifier, reference, step, operator, existing)
    clock.return_value = now + timedelta(seconds=30 * (step - int(now.timestamp()) // 30 + 1))
    frontend = tmp_path / "public"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("<html>synthetic hosted shell</html>")
    app = runtime.create_hosted_application(
        settings, "staging", pool(c, "api"), custody, frontend=frontend, clock=clock
    )
    origin = settings.hosted.public_origin
    with TestClient(app, base_url=origin) as client:
        assert client.get("/health/ready").status_code == 200
        response = client.post(
            "/api/auth/local/sign-in",
            json={
                "username": "recovery-admin",
                "password": factors.password,
                "totp_code": pyotp.TOTP(seed).at(clock()),
            },
            headers={"origin": origin, "x-otm-request": "1"},
        )
        assert response.status_code == 200
        assert client.get("/api/session").status_code == 200
        assert client.get("/api/administrators").status_code == 200
        assert (
            client.post("/api/logout", headers={"origin": origin, "x-otm-request": "1"}).status_code
            == 204
        )
    assert TestClient(app).get("/health/ready").status_code == 503


# Native Procrastinate runs the registered UUID handler over verified TLS without provider effects.
def test_hosted_native_worker_tls(migrated, tmp_path):
    c = migrated
    config = Path(__file__).resolve().parents[1] / "config"
    path = tmp_path / "application.toml"
    path.write_text(
        (config / "staging.application.toml").read_text()
        + '\n[recovery_console]\nallowed_cidrs=["198.51.100.0/24"]\n'
    )
    policy = load_settings(config / "application.toml").local_auth.model_copy(
        update={"workspace_id": "hosted-queue-" + uuid4().hex}
    )
    settings = load_settings(path).model_copy(update={"local_auth": policy})
    queue, identifier = runtime.workspace_queue(policy.workspace_id), uuid4()
    native = procrastinate.App(connector=procrastinate.SyncPsycopgConnector())
    with c.migration.begin() as connection:
        native.configure_task(
            runtime.ORGANIZATION_TASK,
            allow_unknown=True,
            queue=queue,
            connection=connection.connection.driver_connection,
        ).defer(operation_id=str(identifier))
    calls = []

    # Only the test handler records receipt; no fake OCI effect or business completion is published.
    def register(app, engine, selected_queue):
        # One explicit synthetic callback is registered for each required fixed task name.
        def handler(operation_id):
            calls.append(operation_id)

        for name in runtime.REQUIRED_OPERATION_TASKS:
            app.task(name=name, queue=selected_queue, retry=False)(handler)

    # Test-only DNS transport override retains HOST as the verified certificate identity.
    def conninfo(**kwargs):
        return make_conninfo(**kwargs, hostaddr="127.0.0.1")

    with patch.object(runtime, "make_conninfo", side_effect=conninfo):
        runtime.run_hosted_worker(
            settings, "staging", pool(c, "worker"), str(c.directory / "ca.crt"), register, once=True
        )
    assert calls == [str(identifier)]
    with c.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT status FROM public.procrastinate_jobs WHERE queue_name=:queue"),
                {"queue": queue},
            )
            == "succeeded"
        )
