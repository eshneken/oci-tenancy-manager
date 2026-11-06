"""Owned laptop database/HTTPS setup and foreground startup, separate from the organization lab."""

import json
import os
import secrets
import shutil
import stat

# reviewed operator-only argv calls; no shell or HTTP input.
import subprocess  # nosec B404
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from psycopg import sql
from pydantic import Field, SecretStr
from sqlalchemy import text
from sqlalchemy.engine import URL

from otm.admin_cli import PrivateParser
from otm.contracts import Contract
from otm.maintenance import maintenance_engine
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings

IMAGE = "postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"


# Keep generated operator/API credentials private and masked in object representations.
class LocalState(Contract):
    # Random ownership label; every Docker operation verifies this exact instance first.
    instance_id: UUID
    # Random local database-owner credential, used only for explicit setup/bootstrap operations.
    owner_password: SecretStr
    # Separate runtime DB credential; API processes never receive the owner credential in their env.
    api_password: SecretStr
    # Separate worker credential; legacy installations acquire it only during explicit setup.
    worker_password: SecretStr | None = None
    # Actual loopback PostgreSQL host port assigned by Docker; no saved external URL is accepted.
    database_port: int | None = Field(default=None, ge=1, le=65535)


# Never print subprocess output or environment contents: they can contain credentials/provider
# errors.
def run(args, *, env=None):
    # internal argv lists; trusted operator executables.
    return subprocess.run(  # nosec B603
        args, env=env, check=True, capture_output=True, text=True
    )


# Locate the user's Docker client without changing the system PATH or connecting to OCI.
def docker():
    candidate = shutil.which("docker") or str(Path.home() / ".rd/bin/docker")
    if not Path(candidate).is_file():
        raise ValueError("DOCKER_REQUIRED")
    return candidate


# Read only a small regular owner-only file, refusing links and accidental permissive custody.
def read_state(root: Path) -> LocalState:
    descriptor = os.open(root / "state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("PRIVATE_LOCAL_STATE_REQUIRED")
        content = stream.read(16385)
        if len(content) > 16384:
            raise ValueError("INVALID_LOCAL_STATE")
        return LocalState.model_validate_json(content)


# Atomically save only this private local state; password serialization is deliberate and never
# logged.
def write_state(root: Path, state: LocalState):
    content = state.model_dump(mode="json")
    content.update(
        owner_password=state.owner_password.get_secret_value(),
        api_password=state.api_password.get_secret_value(),
        worker_password=state.worker_password.get_secret_value() if state.worker_password else None,
    )
    temporary = root / ("state-" + uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(content, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, root / "state.json")


# Build an explicit owned loopback connection; root/API credentials have independent lifetimes.
def database_url(state: LocalState, *, owner=False, worker=False) -> str:
    if (
        state.database_port is None
        or (worker and state.worker_password is None)
        or (owner and worker)
    ):
        raise ValueError("LOCAL_SETUP_REQUIRED")
    password = (
        state.owner_password if owner else state.worker_password if worker else state.api_password
    )
    return URL.create(
        "postgresql+psycopg",
        username="otm_owner" if owner else "otm_local_worker" if worker else "otm_local_api",
        password=password.get_secret_value(),
        host="127.0.0.1",
        port=state.database_port,
        database="otm_local",
    ).render_as_string(hide_password=False)


# Provision/migrate only a label-verified local Docker database; never inspect a saved lab DSN.
def setup_database(root: Path, state: LocalState, project: Path) -> LocalState:
    if state.worker_password is None:
        state = state.model_copy(update={"worker_password": SecretStr(secrets.token_urlsafe(32))})
    name = "otm-local-" + state.instance_id.hex[:12]
    client = docker()
    # resolved Docker + UUID-derived owned name.
    inspected = subprocess.run(  # nosec B603
        [client, "inspect", name], capture_output=True, text=True
    )
    if inspected.returncode:
        environment = os.environ.copy()
        environment["POSTGRES_PASSWORD"] = state.owner_password.get_secret_value()
        run(
            [
                client,
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                "otm.local.instance=" + str(state.instance_id),
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=otm_owner",
                "--env",
                "POSTGRES_DB=otm_local",
                "--publish",
                "127.0.0.1::5432",
                IMAGE,
            ],
            env=environment,
        )
        inspected = run([client, "inspect", name])
    info = json.loads(inspected.stdout)[0]
    if info["Config"]["Labels"].get("otm.local.instance") != str(state.instance_id):
        raise ValueError("LOCAL_CONTAINER_OWNERSHIP_MISMATCH")
    if not info["State"]["Running"]:
        run([client, "start", name])
    for _ in range(40):
        # fixed owned-container readiness command.
        result = subprocess.run(  # nosec B603
            [
                client,
                "exec",
                name,
                "pg_isready",
                "-h",
                "127.0.0.1",
                "-U",
                "otm_owner",
                "-d",
                "otm_local",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(0.25)
    else:
        raise ValueError("LOCAL_DATABASE_NOT_READY")
    ports = json.loads(run([client, "inspect", name]).stdout)[0]["NetworkSettings"]["Ports"][
        "5432/tcp"
    ]
    if len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
        raise ValueError("LOOPBACK_DATABASE_REQUIRED")
    state = state.model_copy(update={"database_port": int(ports[0]["HostPort"])})
    write_state(root, state)
    engine = maintenance_engine(database_url(state, owner=True), None)
    try:
        config = Config(str(project / "backend/alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with engine.begin() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='otm_local_api'")
            )
            if not exists:
                # psycopg composes the generated literal safely; no password appears in argv/output.
                connection.connection.driver_connection.execute(
                    sql.SQL("CREATE ROLE otm_local_api LOGIN PASSWORD {}").format(
                        sql.Literal(state.api_password.get_secret_value())
                    )
                )
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_local_api")
            connection.exec_driver_sql(
                "REVOKE UPDATE(current_baseline_id) ON public.org_workspace FROM otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(published_by,published_at,published_by_name,publication_mode) "
                "ON public.otm_baseline_version TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_baseline_version TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT INSERT(id,workspace_id,version_number,based_on_id,schema_version,policy_st"
                "atements,quota_statements,monthly_budget_amount,budget_currency,budget_period,ta"
                "g_namespace,tag_defaults,content_hash,edit_revision,created_by,created_at) ON pu"
                "blic.otm_baseline_version TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(policy_statements,quota_statements,monthly_budget_amount,budget_cur"
                "rency,budget_period,tag_namespace,tag_defaults,content_hash,edit_revision) ON pu"
                "blic.otm_baseline_version TO otm_local_api"
            )

            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_administrator,public.otm_local_credential,"
                "public.otm_admin_session,public.otm_operation,public.otm_operation_step,"
                "public.audit_event TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(id,status,authorization_revision,updated_at,revoked_at) "
                "ON public.otm_administrator TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(last_totp_step,failed_attempts,"
                "failure_window_started_at,retry_after) "
                "ON public.otm_local_credential TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT INSERT ON public.otm_admin_session,public.audit_event TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(last_seen_at,revoked_at) ON public.otm_admin_session TO otm_local_api"
            )
            # Organization may append immutable versions and advance guarded heads,
            # never delete history.
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT ON public.org_workspace,public.org_person,public.org_feed,"
                "public.org_version,public.org_member TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(proposed_version_id,applied_version_id,configuration_id,configurati"
                "on,registry_revision) "
                "ON public.org_workspace TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(state,diagnostics,proposed_version_id,applied_version_id) "
                "ON public.org_feed TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(sealed) ON public.org_version TO otm_local_api"
            )
            # Admission appends native jobs; local cancellation can finish only operation metadata.
            connection.exec_driver_sql(
                "REVOKE UPDATE ON public.otm_operation_step FROM otm_local_api"
            )
            connection.exec_driver_sql("GRANT INSERT ON public.otm_operation_step TO otm_local_api")
            connection.exec_driver_sql(
                "GRANT UPDATE(inputs,state,last_outcome,verified_at,evidence_event_id,"
                "attempt_number,current_attempt_id) ON public.otm_operation_step TO otm_local_api"
            )
            connection.exec_driver_sql("GRANT INSERT ON public.otm_operation TO otm_local_api")
            # Taking responsibility changes only the live owner, preserving original intent.
            connection.exec_driver_sql(
                "GRANT UPDATE(responsible_actor_subject) ON public.otm_operation TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(state,stage,wait_reason,completed_at,updated_at,revision) "
                "ON public.otm_operation TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT ON"
                " public.procrastinate_jobs,public.procrastinate_events TO"
                " otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT USAGE,SELECT ON SEQUENCE"
                " public.procrastinate_jobs_id_seq,"
                "public.procrastinate_events_id_seq TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT ON public.org_recommendation,public.otm_tenancy,public.otm_t"
                "enancy_membership TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(directory_status,setup_required,setup_episode_id,removed_capture_at"
                ",pending_operation_id) ON public.org_person TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(status,resolved_at,resolution,last_seen_at,version_id,operation_id)"
                " ON public.org_recommendation TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(baseline_version_id,operation_id,last_operation_id,status,updated_at,"
                "revision) ON publi"
                "c.otm_tenancy TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(status,person_id,operation_id,updated_at,revision) ON public.otm_te"
                "nancy_membership TO otm_local_api"
            )
            worker_exists = connection.scalar(
                text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='otm_local_worker'")
            )
            if not worker_exists:
                connection.connection.driver_connection.execute(
                    sql.SQL("CREATE ROLE otm_local_worker LOGIN PASSWORD {}").format(
                        sql.Literal(state.worker_password.get_secret_value())
                    )
                )
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_local_worker")
            connection.exec_driver_sql(
                "GRANT SELECT ON"
                " public.otm_administrator,public.otm_operation,"
                "public.otm_operation_step,public.audit_event TO"
                " otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT"
                " UPDATE(state,stage,wait_reason,effect_knowledge,revision,"
                "updated_at,completed_at) ON public.otm_operation TO"
                " otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT INSERT,UPDATE ON public.otm_operation_step TO otm_local_worker"
            )
            connection.exec_driver_sql("GRANT INSERT ON public.audit_event TO otm_local_worker")
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT,UPDATE,DELETE ON"
                " public.procrastinate_jobs,public.procrastinate_events,"
                "public.procrastinate_workers,"
                "public.procrastinate_periodic_defers TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT USAGE,SELECT ON SEQUENCE"
                " public.procrastinate_jobs_id_seq,"
                "public.procrastinate_events_id_seq,"
                "public.procrastinate_workers_id_seq,"
                "public.procrastinate_periodic_defers_id_seq TO"
                " otm_local_worker"
            )
            # The worker may lock the immutable administrator ID but cannot change grant identity.
            connection.exec_driver_sql(
                "GRANT UPDATE(id) ON public.otm_administrator TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_baseline_version,public.org_workspace,public.org_feed,"
                "public.org_version,public.o"
                "rg_member,public.org_person,public.org_recommendation,public.otm_tenancy,public."
                "otm_tenancy_membership TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(registry_revision) ON public.org_workspace TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(status,resolved_at,resolution,operation_id) "
                "ON public.org_recommendation TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT INSERT ON public.org_recommendation,public.otm_tenancy_membership TO otm_l"
                "ocal_worker"
            )
            connection.exec_driver_sql(
                # Verified last-association cleanup may create a new directory setup episode.
                "GRANT UPDATE(directory_status,pending_operation_id,removed_capture_at,"
                "setup_required,setup_episode_id) ON public"
                ".org_person TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(verified_baseline_version_id,configuration_verified_at,"
                "configuration_observation,"
                "status,name,home_region,verified_at,operation_id,updated_at,revision)"
                " "
                "ON public.otm_"
                "tenancy TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(status,user_ocid,compartment_ocid,operation_id,updated_at,revision,"
                "cleanup_required) ON public.otm_tenancy_membership TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT ON "
                "public.otm_tenancy_configuration,public.otm_configuration_plan,public.otm_c"
                "onfiguration_plan_target TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(desired_configuration_id) ON public.otm_tenancy TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(revision,updated_at,operation_id) ON "
                "public.otm_configuration_plan TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT "
                "UPDATE(policy_choice,quota_choice,reviewed_by,reviewed_at,accepted_configur"
                "ation_id) ON public.otm_configuration_plan_target TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_tenancy_configuration TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(last_verified_configuration_id) ON public.otm_tenancy TO "
                "otm_local_worker"
            )
            # Check history stays append-only; API reads and workers insert nonidentity fields.
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_configuration_check TO otm_local_api,otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT INSERT(id,workspace_id,tenancy_id,operation_id,contract_version,started_at,"
                "checked_at,context,context_hash,state,results,evidence_event_id) "
                "ON public.otm_configuration_check TO otm_local_worker"
            )
            # Lifecycle email freezes immutable intent; runtime writers change only delivery heads.
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT ON public.otm_notification_outbox "
                "TO otm_local_api,otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(state,safe_code,updated_at) ON public.otm_notification_outbox "
                "TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(state,attempts,attempt_id,last_attempt_at,next_attempt_at,sent_at,"
                "safe_code,updated_at) ON public.otm_notification_outbox TO otm_local_worker"
            )
            # API admits bounded financial heads; only workers publish immutable observations.
            connection.exec_driver_sql(
                "GRANT SELECT,INSERT ON public.otm_financial_collection TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_financial_collection TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE(state,attempts,attempt_id,next_attempt_at,safe_code,updated_at) "
                "ON public.otm_financial_collection TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_financial_observation TO otm_local_api,otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT INSERT ON public.otm_financial_observation TO otm_local_worker"
            )
            # Identity mappings are worker-owned; APIs can read but cannot grant/rebind access.
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_managed_object_binding "
                "TO otm_local_api,otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT INSERT,UPDATE(state,retired_operation_id,updated_at) "
                "ON public.otm_managed_object_binding TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_user_presence_connection "
                "TO otm_local_api,otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT INSERT,UPDATE(state,retired_operation_id,updated_at) "
                "ON public.otm_user_presence_connection TO otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT SELECT ON public.otm_user_presence_check TO otm_local_api,otm_local_worker"
            )
            connection.exec_driver_sql(
                "GRANT "
                "INSERT(operation_id,workspace_id,tenancy_id,context,context_hash,"
                "state,attempt_number,created_at) ON public.otm_user_presence_check "
                "TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT USAGE,SELECT ON SEQUENCE "
                "public.otm_user_presence_check_acquisition_sequence_seq TO otm_local_api"
            )
            connection.exec_driver_sql(
                "GRANT "
                "UPDATE(state,attempt_id,attempt_number,started_at,checked_at,results,"
                "evidence_event_id) ON public.otm_user_presence_check TO otm_local_worker"
            )
            from otm.organization.reviews import initialize_existing_reviews

            initialize_existing_reviews(connection)
    finally:
        engine.dispose()
    return state


# Generate an explicitly local self-signed certificate; never install a machine-wide trust root.
def setup_certificate(root: Path):
    if (root / "tls.key").is_symlink() or (root / "tls.crt").is_symlink():
        raise ValueError("PRIVATE_TLS_FILES_REQUIRED")
    if (root / "tls.key").exists() and (root / "tls.crt").exists():
        return
    previous = os.umask(0o077)
    try:
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-sha256",
                "-days",
                "30",
                "-nodes",
                "-keyout",
                str(root / "tls.key"),
                "-out",
                str(root / "tls.crt"),
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ]
        )
    finally:
        os.umask(previous)


# Set up a private installation once; preserve credentials, namespace and human edits on retries.
def setup(project: Path, root: Path, port: int = 8443):
    try:
        root.mkdir(parents=True, mode=0o700)
    except FileExistsError:
        pass
    DirectorySecrets(root)
    if (root / "state.json").exists():
        state = read_state(root)
    else:
        state = LocalState(
            instance_id=uuid4(),
            owner_password=secrets.token_urlsafe(32),
            api_password=secrets.token_urlsafe(32),
        )
        write_state(root, state)
    if not (root / "application.toml").exists():
        content = (
            (project / "backend/config/application.toml")
            .read_text()
            .replace('workspace_id = "example-org"', 'workspace_id = "local-app"')
            .replace(
                "urn:otm:local:00000000-0000-4000-8000-000000000001",
                "urn:otm:local:" + str(state.instance_id),
            )
            .replace("https://localhost:8443", "https://localhost:" + str(port))
        )
        (root / "application.toml").write_text(content)
    custody = root / "mfa"
    custody.mkdir(mode=0o700, exist_ok=True)
    DirectorySecrets(custody)
    if not (root / "simulation.json").exists():
        policy = load_settings(root / "application.toml").local_auth
        if policy is None:
            raise ValueError("LOCAL_AUTH_CONFIGURATION_REQUIRED")
        from otm.operations.sandbox import sample_sandbox

        (root / "simulation.json").write_text(
            sample_sandbox(policy.workspace_id, state.instance_id).model_dump_json(indent=2) + "\n"
        )
    setup_database(root, state, project)
    setup_certificate(root)


# Isolate subprocess credentials; libpq overrides and unrelated saved DSNs never enter the child.
def environment(root: Path, state: LocalState, *, owner=False, worker=False):
    values = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PG") and key != "OTM_DATABASE_URL"
    }
    values.update(
        OTM_DATABASE_URL=database_url(state, owner=owner, worker=worker),
        OTM_APPLICATION_CONFIG=str(root / "application.toml"),
        OTM_MFA_SECRET_DIRECTORY=str(root / "mfa"),
    )
    if (root / "simulation.json").is_file():
        values["OTM_SANDBOX_CONFIG"] = str(root / "simulation.json")
    # Trusted initial-only operator profile; uploads cannot overwrite a configured source.
    if (root / "organization.json").is_file():
        values["OTM_ORGANIZATION_CONFIG"] = str(root / "organization.json")
    if worker:
        values.pop("OTM_MFA_SECRET_DIRECTORY", None)
    return values


# Run explicit setup, interactive enrollment or foreground HTTPS serving without touching the
# prototype.
def main(argv=None) -> int:
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument(
            "operation",
            choices=["setup", "bootstrap", "reset-local", "reset-organization", "start", "worker"],
        )
        parser.add_argument("--directory", type=Path)
        parser.add_argument("--port", type=int, default=8443)
        parser.add_argument("--confirm-reset-organization", action="store_true")
        args = parser.parse_args(argv)
        project = Path.cwd()
        root = args.directory or project / ".local-dev/application"
        if not (project / "frontend/package-lock.json").is_file() or not root.is_absolute():
            raise ValueError("RUN_FROM_PROJECT_ROOT")
        if not 1024 <= args.port <= 65535:
            raise ValueError("INVALID_LOCAL_PORT")
        if args.operation == "setup":
            setup(project, root, args.port)
            print(
                "Local database and HTTPS are ready. Run otm-local bootstrap, then otm-local start."
            )
            return 0
        DirectorySecrets(root)
        state = read_state(root)
        if args.operation == "reset-organization":
            from otm.organization.local_reset import reset_test_organization

            # Inspection uses the resolved Docker binary and this installation's UUID-only name.
            def inspect_owned(name):
                return run([docker(), "inspect", name]).stdout

            removed = reset_test_organization(
                state,
                load_settings(root / "application.toml"),
                confirmed=args.confirm_reset_organization,
                inspect=inspect_owned,
                database_url=database_url,
            )
            print(
                json.dumps(
                    {
                        "organization_reset": True,
                        "removed": removed,
                        "login_and_audit_preserved": True,
                    }
                )
            )
            return 0
        values = environment(
            root,
            state,
            owner=args.operation in {"bootstrap", "reset-local"},
            worker=args.operation == "worker",
        )
        executable = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
        if args.operation == "worker":
            # Fixed local simulator command, restricted worker credential, no MFA custody in env.
            os.execve(
                executable,
                [executable, "run", "--project", str(project / "backend"), "otm-simulation-worker"],
                values,
            )  # nosec B606
            return 0
        if args.operation in {"bootstrap", "reset-local"}:
            # explicit operator enrollment; factors stay off argv.
            return subprocess.run(  # nosec B603
                [
                    executable,
                    "run",
                    "--project",
                    str(project / "backend"),
                    "otm-admin",
                    args.operation,
                    "--config",
                    str(root / "application.toml"),
                    "--secret-directory",
                    str(root / "mfa"),
                ],
                env=values,
            ).returncode
        settings = load_settings(root / "application.toml")
        if settings.local_server is None:
            raise ValueError("LOCAL_SERVER_CONFIGURATION_REQUIRED")
        origin = urlsplit(settings.local_server.public_origin)
        if origin.hostname not in {"localhost", "127.0.0.1"} or not origin.port:
            raise ValueError("LOOPBACK_ORIGIN_REQUIRED")
        run(["npm", "--prefix", str(project / "frontend"), "ci", "--ignore-scripts"])
        run(["npm", "--prefix", str(project / "frontend"), "run", "build"])
        values["OTM_FRONTEND_DIST"] = str(project / "frontend/dist")
        print(
            "Open "
            + settings.local_server.public_origin
            + " (local self-signed HTTPS). Press Ctrl-C to stop.",
            flush=True,
        )
        # trusted uv, fixed loopback factory, restricted runtime env.
        os.execve(  # nosec B606
            executable,
            [
                executable,
                "run",
                "--project",
                str(project / "backend"),
                "uvicorn",
                "otm.local_server:create_local_application",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(origin.port),
                "--ssl-certfile",
                str(root / "tls.crt"),
                "--ssl-keyfile",
                str(root / "tls.key"),
                "--no-access-log",
            ],
            values,
        )
    except Exception:
        print(
            "LOCAL_APPLICATION_COMMAND_FAILED: "
            "check Docker, private local files and setup instructions."
        )
        return 1
    return 0
