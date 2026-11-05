"""Owned disposable local-runtime qualification using actual installer roles and native worker."""

import json
import os
import secrets
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pyotp
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from otm.audit.contracts import AuditQuery
from otm.auth.local import LocalLogin, LocalSignIn, password_verifier
from otm.auth.service import SessionService
from otm.local_development import database_url, docker, environment, read_state, setup
from otm.local_worker import run_worker
from otm.maintenance import maintenance_engine
from otm.operations.contracts import InspectImportRequest, InspectionIntent
from otm.operations.sandbox import InspectionSubmission, SandboxAdmission, load_sandbox
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.admission import SqlAdmissionStore
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.local_auth import SqlLocalAuth
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.sessions import SqlSessionRepository

pytestmark = pytest.mark.postgres
PROJECT = Path(__file__).resolve().parents[2]


# Never include fixture credentials/DSNs in pytest's parameter or assertion representations.
@dataclass(repr=False)
class RuntimeFixture:
    root: Path
    state: object
    settings: object
    owner: object
    api: object
    sessions: object
    principal: object
    password: SecretStr
    seed: SecretStr


# Create only this run's private, labeled Docker installation and remove only that owned container.
@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    root = tmp_path_factory.mktemp("owned-simulator") / "application"
    try:
        setup(PROJECT, root)
        state = read_state(root)
        config = root / "application.toml"
        config.write_text(config.read_text() + '\n[testing]\nemail_override = "capture@otm.test"\n')
        settings = load_settings(config)
        owner = maintenance_engine(database_url(state, owner=True), None)
        api = maintenance_engine(database_url(state), None)
        policy = settings.local_auth
        password, seed = SecretStr(secrets.token_urlsafe(24)), SecretStr(pyotp.random_base32())
        custody = DirectorySecrets(root / "mfa")
        reference = custody.put(seed.get_secret_value())
        # Synthetic operator enrollment uses an older step so real API/browser factors remain fresh.
        repository = SqlLocalAuth(owner, settings, lambda: datetime.now(UTC))
        _, operator = repository.operator_status()
        repository.enroll(
            password_verifier(password.get_secret_value()),
            reference,
            int(time.time()) // 30 - 2,
            operator,
        )
        # Pin this synthetic enrollment login's proof/check instant across password hashing.
        # Later HTTPS logins still use wall time; reserve their current factor to avoid replay.
        login_at = datetime.now(UTC)
        login = LocalLogin(settings, SqlLocalAuth(api, settings, lambda: login_at), custody)
        issued = login.sign_in(
            LocalSignIn(
                username="recovery-admin",
                password=password.get_secret_value(),
                totp_code=pyotp.TOTP(seed.get_secret_value()).at(login_at.timestamp() - 30),
            )
        )
        grants = SqlAdministratorStore(
            api,
            lambda: datetime.now(UTC),
            local_issuer=policy.issuer,
            trusted_issuers=frozenset({policy.issuer}),
        )
        sessions = SessionService(
            SqlSessionRepository(api), grants, policy.issuer, lambda: datetime.now(UTC)
        )
        yield RuntimeFixture(
            root,
            state,
            settings,
            owner,
            api,
            sessions,
            sessions.authenticate(issued.handle.get_secret_value()),
            password,
            seed,
        )
    finally:
        if "api" in locals():
            api.dispose()
        if "owner" in locals():
            owner.dispose()
        if (root / "state.json").exists():
            state = read_state(root)
            name = "otm-local-" + state.instance_id.hex[:12]
            client = docker()
            inspected = subprocess.run([client, "inspect", name], capture_output=True, text=True)
            if inspected.returncode == 0:
                labels = json.loads(inspected.stdout)[0]["Config"]["Labels"]
                assert labels.get("otm.local.instance") == str(state.instance_id)
                subprocess.run([client, "rm", "--force", name], check=True, capture_output=True)


# Run the actual foreground factory against only this fixture's private worker credential/policy.
def drain(c, monkeypatch):
    for key, value in environment(c.root, c.state, worker=True).items():
        if key.startswith("OTM_"):
            monkeypatch.setenv(key, value)
    run_worker(once=True)


# Query committed native status independently of both the HTTP acceptance and worker return value.
def native_status(c, identifier):
    with c.owner.connect() as connection:
        return connection.scalar(
            text(
                "SELECT status::text FROM public.procrastinate_jobs WHERE args->>'operation_id'=:id"
            ),
            {"id": str(identifier)},
        )


# Prove installed-role admission and native worker publication for each read scenario.
def test_actual_installer_roles_and_native_scenarios(runtime, monkeypatch):
    c = runtime
    config = load_sandbox(c.root / "simulation.json", c.settings.local_auth.workspace_id)
    admission = SandboxAdmission(
        c.api,
        c.sessions,
        c.root / "simulation.json",
        config.policy.workspace_id,
        lambda: datetime.now(UTC),
    )
    reads = SqlOperationDirectory(c.api)
    accepted = []
    for target in config.targets:
        command = InspectionSubmission(client_request_key=uuid4(), tenancy_ocid=target.tenancy_ocid)
        receipt = admission.submit(c.principal, command)
        assert admission.submit(c.principal, command).operation_id == receipt.operation_id
        assert native_status(c, receipt.operation_id) == "todo"
        accepted.append((receipt, target.scenario))
    drain(c, monkeypatch)
    for receipt, scenario in accepted:
        detail = reads.detail(config.policy.workspace_id, receipt.operation_id)
        assert detail.operation.state == (
            "succeeded" if scenario == "healthy" else "needs_attention"
        )
        assert native_status(c, receipt.operation_id) == "succeeded"
        assert len(detail.events) == 3
        assert detail.steps[0].safe_code is not None
    history = SqlAuditDirectory(c.api).directory(
        config.policy.workspace_id, AuditQuery(page_size=100, category="operations")
    )
    assert history.total == 15
    assert sum(row.actor_name == "Inspection worker" for row in history.items) == 10
    # Runtime roles have no administrative bootstrap/auth-secret or operation-audit rewrite power.
    worker = maintenance_engine(database_url(c.state, worker=True), None)
    try:
        with worker.begin() as connection:
            with pytest.raises(DBAPIError):
                connection.exec_driver_sql("SELECT * FROM public.otm_local_credential")
        with c.api.begin() as connection:
            with pytest.raises(DBAPIError):
                connection.exec_driver_sql(
                    "UPDATE public.otm_operation SET effect_knowledge='known'"
                )
        with worker.begin() as connection:
            with pytest.raises(DBAPIError):
                connection.exec_driver_sql("DELETE FROM public.audit_event")
    finally:
        worker.dispose()


# A foreign job remains queued in both native and business state after draining this workspace.
def test_worker_never_consumes_foreign_queue(runtime, monkeypatch):
    c = runtime
    workspace = "foreign-" + uuid4().hex
    config = load_sandbox(c.root / "simulation.json", c.settings.local_auth.workspace_id)
    request = InspectImportRequest(
        workspace_id=workspace,
        client_request_key=uuid4(),
        tenancy_ocid=config.targets[0].tenancy_ocid,
    )
    intent = InspectionIntent(
        contract_version="inspect-import-1",
        kind="inspect_import",
        workspace_id=workspace,
        policy_revision=config.policy.policy_revision,
        access_binding_id=config.policy.access_binding_id,
        target={
            "organization_id": config.policy.organization_id,
            "parent_tenancy_ocid": config.policy.parent_tenancy_ocid,
            "tenancy_ocid": request.tenancy_ocid,
        },
    )
    receipt = SqlAdmissionStore(
        c.owner, InspectionEnqueuer(queue=workspace_queue(workspace))
    ).insert(request, c.principal.actor, intent, datetime.now(UTC))
    drain(c, monkeypatch)
    assert native_status(c, receipt.operation_id) == "todo"
    assert (
        SqlOperationDirectory(c.owner).detail(workspace, receipt.operation_id).operation.state
        == "queued"
    )


# The broad lifecycle regression retains its existing real-process browser coverage.
def test_browser_submission_and_live_worker(runtime):
    run_browser_runtime(runtime, "e2e/simulation.spec.ts")


# Share real HTTPS/worker startup between broad flows and focused independently seeded scenarios.
def run_browser_runtime(c, script, extra=None):
    import socket

    import httpx

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"https://localhost:{port}"
    config = c.root / "browser.toml"
    config.write_text(
        (c.root / "application.toml").read_text().replace("https://localhost:8443", origin)
    )
    from test_organization_fixtures import example_config

    organization_profile = c.root / "organization.json"
    organization_profile.write_text(example_config().model_dump_json())
    organization_profile.chmod(0o600)
    api_env = environment(c.root, c.state)
    api_env.update(
        OTM_APPLICATION_CONFIG=str(config), OTM_FRONTEND_DIST=str(PROJECT / "frontend/dist")
    )
    worker_env = environment(c.root, c.state, worker=True)
    server = subprocess.Popen(
        [
            str(PROJECT / "backend/.venv/bin/python"),
            "-m",
            "uvicorn",
            "otm.local_server:create_local_application",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ssl-certfile",
            str(c.root / "tls.crt"),
            "--ssl-keyfile",
            str(c.root / "tls.key"),
            "--no-access-log",
        ],
        env=api_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    worker = None
    worker_log = None
    try:
        with httpx.Client(verify=False, trust_env=False) as client:
            for _ in range(60):
                try:
                    if client.get(origin + "/health/live").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.1)
            else:
                pytest.fail("Owned simulator HTTPS server unavailable", pytrace=False)
        # Keep private synthetic diagnostics so worker failures remain visible.
        worker_log = (c.root / "browser-worker.log").open("w")
        worker = subprocess.Popen(
            [
                str(PROJECT / "backend/.venv/bin/python"),
                "-c",
                "from otm.local_worker import run_worker; run_worker()",
            ],
            env=worker_env,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
        )
        browser_env = {
            key: value for key, value in os.environ.items() if not key.startswith(("PG", "OTM_"))
        }
        browser_env.update(
            OTM_E2E_ORIGIN=origin,
            OTM_E2E_PASSWORD=c.password.get_secret_value(),
            OTM_E2E_SEED=c.seed.get_secret_value(),
        )
        browser_env.update(extra or {})
        result = subprocess.run(
            # Keep diagnostics in this owned runtime: another browser suite must not erase them.
            [
                "npm",
                "run",
                "test:ui",
                "--",
                script,
                "--output=" + str(c.root / "browser-results" / Path(script).stem),
            ],
            cwd=PROJECT / "frontend",
            env=browser_env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = result.stdout + result.stderr + (c.root / "browser-worker.log").read_text()
        for private in (
            c.password,
            c.seed,
            c.state.owner_password,
            c.state.api_password,
            c.state.worker_password,
        ):
            output = output.replace(private.get_secret_value(), "[REDACTED]")
        assert result.returncode == 0, output
    finally:
        for process in (worker, server):
            if process is None:
                continue
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if worker_log is not None:
            worker_log.close()


# Installer grants can publish organization data but cannot replace configuration or erase evidence.
def test_installed_organization_permissions_and_literal_source(runtime):
    from test_organization_fixtures import example_config

    from otm.organization.views import OrganizationQuery
    from otm.organization.web import OrganizationWeb
    from otm.storage.organization import SqlOrganizationStore

    c = runtime

    # Use server UTC for the same freshness checks as the local API.
    def clock():
        return datetime.now(UTC)

    store = SqlOrganizationStore(c.api, c.sessions, clock)
    web = OrganizationWeb(store, clock, example_config(required_root_profile=True))
    source = (
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n"
        b"Root,root@example.test,,\n"
        b"Leader One,one@example.test,root@example.test,root@example.test\n"
        b"Leader Two,two@example.test,root@example.test,root@example.test\n"
        b"Delegate,delegate@example.test,one@example.test,one@example.test\n"
        b"Robert'); DROP TABLE org_person;--,engineer@example.test,"
        b"one@example.test,one@example.test\n"
    )
    # The earlier browser lifecycle leaves a legitimate retained identity in this owned fixture.
    expected_count = sum(p.profile == "employee" for p in store.head(c.principal).people)
    result = web.upload(c.principal, source, clock(), uuid4(), True)
    assert result.state == "published"
    view = web.directory(c.principal, OrganizationQuery(query="DROP TABLE"))
    assert view.employee_count == expected_count and view.total == 1
    assert view.items[0].email == "engineer@example.test"
    assert not any(f.code == "TOP_MANAGER_MISMATCH" for f in view.findings)
    # Database grants independently reject configuration tampering and all organization DELETEs.
    for statement in (
        "UPDATE public.org_workspace SET configuration='{}'::jsonb",
        "UPDATE public.org_feed SET raw_digest=NULL",
        "UPDATE public.org_version SET configuration='{}'::jsonb",
        "DELETE FROM public.org_member",
        "DELETE FROM public.org_person",
    ):
        with pytest.raises(DBAPIError), c.api.begin() as connection:
            connection.execute(text(statement))


# Actual local operator cleanup preserves auth/history, restores guards and allows a fresh feed.
def test_local_organization_reset_cycle_and_rollback(runtime):
    import csv
    from io import StringIO
    from unittest.mock import patch

    from sqlalchemy import event
    from test_organization_fixtures import example_config, example_records

    from otm import local_development as local
    from otm.organization.local_reset import TABLES, clear_organization
    from otm.organization.web import OrganizationWeb
    from otm.storage.organization import SqlOrganizationStore

    c = runtime

    # Hash only synthetic rows locally; no credentials or private data are logged by assertions.
    def preserved():
        with c.owner.connect() as connection:
            return tuple(
                connection.scalar(
                    text(
                        "SELECT md5(coalesce(string_agg(row_to_json(t)::text,'' "
                        "ORDER BY row_to_json(t)::text),'')) FROM public." + name + " t"
                    )
                )
                for name in (
                    "otm_administrator",
                    "otm_local_credential",
                    "otm_admin_session",
                    "audit_event",
                    "otm_operation",
                    "otm_operation_step",
                )
            )

    # Source time remains real server UTC and input comes only from reusable synthetic fixtures.
    def clock():
        return datetime.now(UTC)

    source = StringIO()
    writer = csv.writer(source)
    writer.writerow(("EMPLOYEE_FULL_NAME", "EMAIL", "MGR", "TOP_MGR"))
    for row in example_records():
        writer.writerow((row.full_name, row.email, row.manager_email or "", ""))
    store = SqlOrganizationStore(c.api, c.sessions, clock)
    config = store.inspection(c.principal)[0] or example_config()
    web = OrganizationWeb(store, clock, config)
    assert (
        web.upload(c.principal, source.getvalue().encode(), clock(), uuid4(), True).state
        == "published"
    )
    from test_baseline_authoring import content

    from otm.configuration.contracts import SaveBaselineDraft
    from otm.configuration.service import BaselineAuthoring

    recipes = BaselineAuthoring(store)
    existing = recipes.read(c.principal)
    if existing.draft is None:
        recipes.save(
            c.principal,
            SaveBaselineDraft(
                content=content(), based_on_id=existing.latest.id if existing.latest else None
            ),
        )
    before = preserved()
    with c.owner.connect() as connection:
        counts_before = tuple(
            connection.scalar(text("SELECT count(*) FROM public." + name)) for name in TABLES
        )

    # Simulate failure after truncation; PostgreSQL must roll back data AND disabled guards.
    def fail_enable(connection, cursor, statement, parameters, context, executemany):
        if "ENABLE TRIGGER org_workspace_no_truncate" in statement:
            raise RuntimeError("synthetic reset interruption")

    event.listen(c.owner, "before_cursor_execute", fail_enable)
    try:
        with (
            pytest.raises(RuntimeError, match="synthetic reset interruption"),
            c.owner.begin() as connection,
        ):
            clear_organization(
                connection, c.settings.local_auth.workspace_id, c.settings.local_auth.issuer
            )
    finally:
        event.remove(c.owner, "before_cursor_execute", fail_enable)
    with c.owner.connect() as connection:
        assert (
            tuple(connection.scalar(text("SELECT count(*) FROM public." + name)) for name in TABLES)
            == counts_before
        )
        assert connection.scalar(
            text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE (tgname LIKE 'org%no_truncate' "
                "OR tgname LIKE 'otm_tenancy%no_truncate' OR tgname LIKE 'o"
                "tm_baseline%no_truncate' OR tgname LIKE 'otm_configuration%no_truncate' "
                "OR tgname LIKE 'otm_financial%no_truncate') "
                "AND tgenabled='O'"
            )
        ) == len(TABLES)
    with c.owner.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with pytest.raises(RuntimeError, match="ACTIVE_READ_COMMITTED"):
            clear_organization(
                connection, c.settings.local_auth.workspace_id, c.settings.local_auth.issuer
            )

    settings_path = c.root / "application.toml"
    original = settings_path.read_text()
    settings_path.write_text(
        original.replace("organization_reset_enabled = false", "organization_reset_enabled = true")
    )
    try:
        with patch.object(Path, "cwd", return_value=PROJECT):
            assert (
                local.main(
                    [
                        "reset-organization",
                        "--directory",
                        str(c.root),
                        "--confirm-reset-organization",
                    ]
                )
                == 0
            )
    finally:
        settings_path.write_text(original)
    assert preserved() == before
    with c.owner.connect() as connection:
        assert all(
            connection.scalar(text("SELECT count(*) FROM public." + name)) == 0 for name in TABLES
        )
        assert connection.scalar(
            text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE (tgname LIKE 'org%no_truncate' "
                "OR tgname LIKE 'otm_tenancy%no_truncate' OR tgname LIKE 'o"
                "tm_baseline%no_truncate' OR tgname LIKE 'otm_configuration%no_truncate' "
                "OR tgname LIKE 'otm_financial%no_truncate') "
                "AND tgenabled='O'"
            )
        ) == len(TABLES)
    assert store.inspection(c.principal) == (None, None, None, None, ())
    store.configure_initial(c.principal, config)
    assert (
        web.upload(c.principal, source.getvalue().encode(), clock(), uuid4(), True).state
        == "published"
    )
    with pytest.raises(DBAPIError), c.api.begin() as connection:
        connection.execute(text("TRUNCATE public.org_member"))


# Installed API credentials can cancel only pending local work, and the old native delivery cannot
# revive it.
def test_installed_api_lifecycle_cancellation_permissions(runtime):
    from unittest.mock import Mock

    from otm.operations.contracts import InspectionPolicy
    from otm.providers.lifecycle import SimulatedLifecycleFacade
    from otm.storage.organization import OrganizationConflict, SqlOrganizationStore
    from otm.tenancies.contracts import OrganizationAction
    from otm.tenancies.views import ReviewQuery, TenancyQuery
    from otm.tenancies.workflows import OrganizationWorkflows

    c = runtime
    clock = Mock(side_effect=lambda: datetime.now(UTC))
    store = SqlOrganizationStore(c.api, c.sessions, clock)
    policy = InspectionPolicy(
        workspace_id=c.settings.local_auth.workspace_id,
        policy_revision=uuid4(),
        organization_id="synthetic-org",
        parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        access_binding_id=uuid4(),
    )
    facade = SimulatedLifecycleFacade(policy)
    app = OrganizationWorkflows(
        store,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(policy.workspace_id), task=ORGANIZATION_TASK
        ),
        policy=policy,
        facade=facade,
    )
    # This fixture follows an owner-only reset: explicitly publish its new default before admission.
    from test_baseline_authoring import content

    from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
    from otm.configuration.service import BaselineAuthoring
    from otm.providers.baseline import SimulatedBaselineQualifier

    recipes = BaselineAuthoring(store, SimulatedBaselineQualifier())
    state = recipes.read(c.principal)
    if state.latest is None:
        draft = state.draft or recipes.save(
            c.principal,
            SaveBaselineDraft(
                content=content(), based_on_id=state.latest.id if state.latest else None
            ),
        )
        recipes.publish(
            c.principal,
            PublishBaseline(baseline_id=draft.id, expected_revision=draft.edit_revision),
        )
    p = next(p for p in store.head(c.principal).people if p.email == "engineer@example.test")
    preview = app.preview(c.principal, p.id)
    created = app.act(
        c.principal,
        OrganizationAction(
            client_request_key=uuid4(),
            context=preview.context,
            person_id=p.id,
            action="create_tenancy",
            name="cancellationpermissioncheck",
            home_region="us-ashburn-1",
        ),
    )
    preview = app.preview(c.principal, p.id)
    assert preview.actions == ("cancel_simulation",)
    cancellation = OrganizationAction(
        client_request_key=uuid4(),
        context=preview.context,
        person_id=p.id,
        operation_id=created.operation_id,
        action="cancel_simulation",
    )
    result = app.act(c.principal, cancellation)
    assert result.state == "cancelled" and app.act(c.principal, cancellation) == result
    assert app.tenancies(c.principal, TenancyQuery()).total == 0
    with c.api.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT state FROM public.otm_operation WHERE id=:id"),
                {"id": created.operation_id},
            )
            == "cancelled"
        )
    assert app.reviews(c.principal, ReviewQuery()).total == 0
    with pytest.raises(OrganizationConflict):
        app.act(c.principal, cancellation.model_copy(update={"client_request_key": uuid4()}))
    # API cannot claim a known provider effect or insert worker steps even after adding
    # cancellation grants.
    for statement in (
        "UPDATE public.otm_operation SET effect_knowledge='known'",
        "DELETE FROM public.otm_operation",
    ):
        with pytest.raises(DBAPIError), c.api.begin() as connection:
            connection.execute(text(statement))
