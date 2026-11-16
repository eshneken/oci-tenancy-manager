"""Explicit hosted composition seams and migration CLI; no local or simulated provider fallback."""

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import procrastinate
import uvicorn
from psycopg.conninfo import make_conninfo
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from otm.admin_cli import PrivateParser
from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.auth.local import LocalLogin
from otm.auth.service import SessionService
from otm.hosted_database import (
    database_ready,
    hosted_connection_options,
    hosted_engine,
    hosted_settings,
    migrate_database,
)
from otm.notifications.worker import NOTIFICATION_TASK
from otm.organization.web import OrganizationWeb
from otm.settings import load_settings
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import SqlAuditExport
from otm.storage.enqueue import (
    CONFIGURATION_CHECK_TASK,
    CONFIGURATION_TASK,
    COST_TASK,
    INSPECTION_TASK,
    ORGANIZATION_TASK,
    PRESENCE_TASK,
    RECOVERY_NETWORK_TASK,
    RECOVERY_PASSWORD_TASK,
    SIGNING_KEY_TASK,
    workspace_queue,
)
from otm.storage.local_auth import SqlLocalAuth
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.organization import SqlOrganizationStore
from otm.storage.sessions import SqlSessionRepository
from otm.tenancies.workflows import OrganizationWorkflows

REQUIRED_OPERATION_TASKS = frozenset(
    {
        CONFIGURATION_CHECK_TASK,
        CONFIGURATION_TASK,
        COST_TASK,
        INSPECTION_TASK,
        ORGANIZATION_TASK,
        PRESENCE_TASK,
        RECOVERY_NETWORK_TASK,
        RECOVERY_PASSWORD_TASK,
        SIGNING_KEY_TASK,
        NOTIFICATION_TASK,
    }
)


# UTC is server-owned; client clocks never determine session or job authority.
def utc_now():
    return datetime.now(UTC)


# Compose real auth/directory/audit services using an explicit secret reader and verified API pool.
# Provider mutations stay unavailable until the OCI composition is supplied in a subsequent slice.
def create_hosted_application(
    settings, environment, engine, mfa_secrets, *, frontend, notifier=None, clock=utc_now
):
    try:
        settings = hosted_settings(settings, environment)
        if settings.local_auth is None or not callable(getattr(mfa_secrets, "get", None)):
            raise ValueError("HOSTED_IDENTITY_AND_SECRET_PROVIDER_REQUIRED")
        if engine.get_execution_options().get("otm_hosted_role") != "api" or not database_ready(
            engine
        ):
            raise ValueError("HOSTED_RUNTIME_DATABASE_NOT_READY")
        if not frontend.is_dir():
            raise ValueError("HOSTED_FRONTEND_REQUIRED")
        if settings.notifications.enabled and notifier is None:
            raise ValueError("HOSTED_NOTIFICATION_COMPOSITION_REQUIRED")
        policy = settings.local_auth
        grants = SqlAdministratorStore(
            engine, clock, local_issuer=policy.issuer, trusted_issuers=frozenset({policy.issuer})
        )
        sessions = SessionService(SqlSessionRepository(engine), grants, policy.issuer, clock)
        login = LocalLogin(settings, SqlLocalAuth(engine, settings, clock), mfa_secrets)
        store = SqlOrganizationStore(engine, sessions, clock)
        workflow = OrganizationWorkflows(
            store, notifications=notifier, mail_policy=settings.mail_policy()
        )
        draining = Event()

        # Return503 during drain; DB/schema/role failures never disclose their cause.
        def readiness():
            return not draining.is_set() and database_ready(engine)

        app = create_app(
            sessions,
            BrowserSettings(public_origin=settings.hosted.public_origin),
            login,
            grants,
            frontend,
            operations=SqlOperationDirectory(engine),
            audit_history=SqlAuditDirectory(engine),
            audit_export=SqlAuditExport(engine, clock),
            branding=settings.branding,
            email_policy=settings.mail_policy(),
            readiness=readiness,
            organization=OrganizationWeb(
                store, clock, None, test_reset_enabled=False, workflows=workflow
            ),
        )
        app.add_middleware(
            ProxyHeadersMiddleware, trusted_hosts=list(settings.hosted.trusted_proxy_cidrs)
        )

        # Uvicorn stops admission/drains requests first; then the factory releases its own pool.
        @asynccontextmanager
        async def lifespan(application):
            try:
                yield
            finally:
                draining.set()
                engine.dispose()

        app.router.lifespan_context = lifespan
        return app
    except Exception:
        engine.dispose()
        raise RuntimeError("HOSTED_API_STARTUP_FAILED") from None


# Run one API process per pod; only the application's explicit proxy boundary may trust headers.
def serve_hosted_api(app):
    uvicorn.run(
        app,
        # Container port only; ingress/ClusterIP, network policy and OCI NSGs bound reachability.
        host="0.0.0.0",  # nosec B104
        port=8080,
        workers=1,
        proxy_headers=False,
        access_log=False,
        timeout_graceful_shutdown=90,
    )


# The real OCI host supplies a trusted registration function; no dynamic imports/plugin registry.
# Check all existing capabilities before fetching jobs so absent adapters cannot fail queued work.
def run_hosted_worker(settings, environment, engine, ca_file, register_tasks, *, once=False):
    try:
        settings = hosted_settings(settings, environment)
        if settings.local_auth is None or not callable(register_tasks):
            raise ValueError("HOSTED_WORKER_COMPOSITION_REQUIRED")
        if engine.get_execution_options().get("otm_hosted_role") != "worker" or not database_ready(
            engine
        ):
            raise ValueError("HOSTED_RUNTIME_DATABASE_NOT_READY")
        url, options = hosted_connection_options(
            engine.url.render_as_string(hide_password=False), ca_file, role="worker"
        )
        # SQLAlchemy translates credential fields in memory; no password enters argv or a log.
        conninfo = make_conninfo(
            **url.translate_connect_args(username="user", database="dbname"), **options
        )
        native = procrastinate.App(
            connector=procrastinate.PsycopgConnector(conninfo=conninfo, min_size=1, max_size=2)
        )
        queue = workspace_queue(settings.local_auth.workspace_id)
        register_tasks(native, engine, queue)
        required = REQUIRED_OPERATION_TASKS
        if any(
            name not in native.tasks
            or native.tasks[name].queue != queue
            or native.tasks[name].retry_strategy is not None
            for name in required
        ):
            raise ValueError("HOSTED_WORKER_HANDLERS_REQUIRED")
        native.run_worker(
            queues=[queue],
            concurrency=1,
            wait=not once,
            listen_notify=False,
            fetch_job_polling_interval=1,
            shutdown_graceful_timeout=settings.hosted.worker_shutdown_seconds,
            install_signal_handlers=True,
            delete_jobs="never",
        )
    except Exception:
        raise RuntimeError("HOSTED_WORKER_FAILED") from None
    finally:
        engine.dispose()


# Only migration is CLI-enabled; API/worker require explicit Vault/OCI composition.
def main(argv=None):
    engine = None
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument("command", choices=["migrate"])
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument(
            "--expected-environment", choices=["staging", "production"], required=True
        )
        args = parser.parse_args(argv)
        hosted_settings(load_settings(args.config), args.expected_environment)
        engine = hosted_engine(
            os.environ["OTM_DATABASE_URL"], os.environ["OTM_DATABASE_CA_FILE"], role="migration"
        )
        revision = migrate_database(engine)
        print("HOSTED_MIGRATION_COMPLETE:" + revision)
        return 0
    except Exception:
        print("HOSTED_MIGRATION_FAILED")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
