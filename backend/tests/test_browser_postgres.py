"""Real HTTPS/Chromium integration with an isolated Docker database and synthetic local factors."""

import os
import secrets
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pyotp
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from test_administrators import grant
from test_organization_fixtures import example_config

from otm.auth.local import password_verifier
from otm.local_development import setup_certificate
from otm.operations.contracts import ActorIdentity, InspectImportRequest, InspectionIntent
from otm.operations.execution import SimulatedInspectionWorker
from otm.operations.execution_contracts import DispatchGrant
from otm.providers.inspection import TenancyInspection
from otm.providers.inspection_contracts import InspectionTarget, TenancyFacts
from otm.providers.inspection_simulator import (
    SimulatedAccess,
    SimulatedInspectionProvider,
    SimulatedTenancy,
)
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings
from otm.storage.admission import SqlAdmissionStore
from otm.storage.enqueue import InspectionEnqueuer
from otm.storage.execution import SqlExecutionStore
from otm.storage.local_auth import SqlLocalAuth
from otm.storage.tables import administrator

pytestmark = pytest.mark.postgres
PROJECT = Path(__file__).resolve().parents[2]


# Launch the actual factory with a restricted SQL role and synthetic seed held only in private temp.
def test_real_https_browser_login_directory_and_logout(pg_engine, tmp_path):
    root = tmp_path / "browser"
    root.mkdir(mode=0o700)
    custody = root / "mfa"
    custody.mkdir(mode=0o700)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"https://localhost:{port}"
    workspace, issuer = "browser-" + uuid4().hex, "urn:otm:local:" + str(uuid4())
    config = root / "application.toml"
    config.write_text(
        (PROJECT / "backend/config/application.toml")
        .read_text()
        .replace('workspace_id = "example-org"', f'workspace_id = "{workspace}"')
        .replace("urn:otm:local:00000000-0000-4000-8000-000000000001", issuer)
        .replace("https://localhost:8443", origin)
        .replace("organization_reset_enabled = false", "organization_reset_enabled = true")
    )
    settings = load_settings(config)
    organization_profile = root / "organization.json"
    organization_profile.write_text(example_config().model_dump_json())
    organization_profile.chmod(0o600)
    seed, password = pyotp.random_base32(), secrets.token_urlsafe(24)
    reference = DirectorySecrets(custody).put(seed)
    repository = SqlLocalAuth(pg_engine, settings, lambda: datetime.now(UTC))
    _, operator = repository.operator_status()
    root_identifier = repository.enroll(
        password_verifier(password), reference, int(time.time()) // 30 - 1, operator
    )
    # Seed one accepted read through the real admission/audit/native-enqueue transaction.
    request = InspectImportRequest(
        workspace_id=workspace,
        client_request_key=uuid4(),
        tenancy_ocid="ocid1.tenancy.oc1..browsersandbox",
    )
    intent = InspectionIntent(
        contract_version="inspect-import-1",
        kind="inspect_import",
        workspace_id=workspace,
        policy_revision=uuid4(),
        access_binding_id=uuid4(),
        target=InspectionTarget(
            organization_id="synthetic-browser-org",
            parent_tenancy_ocid="ocid1.tenancy.oc1..browserparent",
            tenancy_ocid=request.tenancy_ocid,
        ),
    )
    admission_store = SqlAdmissionStore(pg_engine, InspectionEnqueuer())
    admission_store.insert(
        request,
        ActorIdentity(
            issuer=issuer, subject=str(root_identifier), display_name="Recovery administrator"
        ),
        intent,
        datetime.now(UTC),
    )
    # A second real accepted operation runs the simulator and commits verified step/audit evidence.
    verified_request = request.model_copy(
        update={"client_request_key": uuid4(), "tenancy_ocid": "ocid1.tenancy.oc1..browserverified"}
    )
    verified_intent = intent.model_copy(
        update={
            "target": intent.target.model_copy(
                update={"tenancy_ocid": verified_request.tenancy_ocid}
            )
        }
    )
    actor = ActorIdentity(
        issuer=issuer, subject=str(root_identifier), display_name="Recovery administrator"
    )
    at = datetime.now(UTC)
    accepted = admission_store.insert(verified_request, actor, verified_intent, at)
    clock = SimpleNamespace(now=lambda: datetime.now(UTC))
    provider = SimulatedInspectionProvider(clock.now)
    provider.set_access(
        SimulatedAccess(
            workspace_id=workspace,
            access_binding_id=intent.access_binding_id,
            credential_generation=1,
            permitted=True,
            tenancy_ocids=frozenset({verified_request.tenancy_ocid}),
        )
    )
    provider.set_tenancy(
        SimulatedTenancy(
            workspace_id=workspace,
            visible_at=at,
            facts=TenancyFacts(
                **verified_intent.target.model_dump(),
                actual_name="Synthetic browser sandbox",
                home_region_key="TEST",
                home_region_identifier=None,
                role="CHILD",
                observed_at=at,
            ),
        )
    )
    grant_context = DispatchGrant(
        workspace_id=workspace,
        actor_key=actor.key,
        policy_revision=intent.policy_revision,
        runtime_policy_revision=uuid4(),
        access_binding_id=intent.access_binding_id,
        credential_generation=1,
    )
    SimulatedInspectionWorker(
        SqlExecutionStore(pg_engine),
        Mock(require_inspection=Mock(return_value=grant_context)),
        TenancyInspection(provider, clock.now),
        clock.now,
    ).run(accepted.operation_id)
    synthetic = grant(
        workspace_id=workspace,
        display_name="Synthetic corporate",
        subject="browser-corporate",
        email="synthetic@example.test",
    )
    role, db_password = "browser_" + uuid4().hex, secrets.token_urlsafe(24)
    with pg_engine.begin() as connection:
        connection.execute(administrator.insert().values(**synthetic.model_dump()))
        driver = connection.connection.driver_connection
        driver.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(db_password)
            )
        )
        driver.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        for statement in [
            "GRANT UPDATE(published_by,published_at,published_by_name,publication_mode) "
            "ON public.otm_baseline_version TO {}",
            "GRANT SELECT ON public.otm_baseline_version TO {}",
            "GRANT INSERT(id,workspace_id,version_number,based_on_id,schema_ver"
            "sion,policy_statements,quota_statements,monthly_budget_amount,budg"
            "et_currency,budget_period,tag_namespace,tag_defaults,content_hash,"
            "edit_revision,created_by,created_at) ON public.otm_baseline_versio"
            "n TO {}",
            "GRANT UPDATE(policy_statements,quota_statements,monthly_budget_amo"
            "unt,budget_currency,budget_period,tag_namespace,tag_defaults,conte"
            "nt_hash,edit_revision) ON public.otm_baseline_version TO {}",
            "GRANT SELECT,INSERT ON public.org_workspace,public.org_person,public.org_feed,"
            "public.org_version,public.org_member TO {}",
            "GRANT UPDATE(proposed_version_id,applied_version_id,configuration_id,configuration,"
            "registry_revision) ON public.org_workspace TO {}",
            "GRANT UPDATE(state,diagnostics,proposed_version_id,applied_version_id) "
            "ON public.org_feed TO {}",
            "GRANT UPDATE(sealed) ON public.org_version TO {}",
            "GRANT SELECT,INSERT ON public.org_recommendation,public.otm_tenancy,"
            "public.otm_tenancy_membership TO {}",
            "GRANT UPDATE(directory_status,setup_required,setup_episode_id,"
            "removed_capture_at,pending_operation_id) ON public.org_person TO {}",
            "GRANT UPDATE(status,resolved_at,resolution,last_seen_at,version_id,operation_id) "
            "ON public.org_recommendation TO {}",
            "GRANT SELECT ON "
            "public.otm_configuration_check,public.otm_tenancy_configuration,public.otm_configuration_plan,public.otm_c"
            "onfiguration_plan_target,public.otm_administrator,public.otm_local_credenti"
            "al,"
            "public.otm_notification_outbox,public.otm_admin_session,public.otm_operation,public.otm_operation_step,"
            "public.audit_event TO {}",
            "GRANT UPDATE(status,authorization_revision,updated_at,revoked_at) "
            "ON public.otm_administrator TO {}",
            "GRANT UPDATE(last_totp_step,failed_attempts,failure_window_started_at,retry_after) "
            "ON public.otm_local_credential TO {}",
            "GRANT INSERT ON public.otm_admin_session,public.audit_event TO {}",
            "GRANT UPDATE(last_seen_at,revoked_at) ON public.otm_admin_session TO {}",
        ]:
            driver.execute(sql.SQL(statement).format(sql.Identifier(role)))
    setup_certificate(root)
    url = make_url(os.environ["OTM_BACKEND_TEST_DATABASE_URL"]).set(
        username=role, password=db_password
    )
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment.update(
        OTM_APPLICATION_CONFIG=str(config),
        OTM_ORGANIZATION_CONFIG=str(organization_profile),
        OTM_MFA_SECRET_DIRECTORY=str(custody),
        OTM_FRONTEND_DIST=str(PROJECT / "frontend/dist"),
        OTM_DATABASE_URL=url.render_as_string(hide_password=False),
        OTM_E2E_ORIGIN=origin,
        OTM_E2E_PASSWORD=password,
        OTM_E2E_SEED=seed,
    )
    process = subprocess.Popen(
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
            str(root / "tls.crt"),
            "--ssl-keyfile",
            str(root / "tls.key"),
            "--no-access-log",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(verify=False, trust_env=False) as client:
            for _ in range(60):
                try:
                    if client.get(origin + "/health/live").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.1)
            else:
                pytest.fail("Synthetic HTTPS server failed to start")
        result = subprocess.run(
            ["npm", "run", "test:ui", "--", "e2e/auth.spec.ts"],
            cwd=PROJECT / "frontend",
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Scrub factors before any retained assertion diagnostic, even though tracing is disabled.
        output = result.stdout + result.stderr
        for private in (password, seed, db_password):
            output = output.replace(private, "[REDACTED]")
        assert result.returncode == 0, output
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


# Real catalog role checks refuse table-owner membership even when NOINHERIT hides direct usage.
def test_local_factory_rejects_noinherit_owner_membership(pg_engine, tmp_path, monkeypatch):
    from otm.local_server import create_local_application

    role, password = "unsafe_" + uuid4().hex, secrets.token_urlsafe(24)
    with pg_engine.begin() as connection:
        driver = connection.connection.driver_connection
        driver.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        owner = connection.exec_driver_sql(
            "SELECT pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid='public.otm_administrator'::regclass"
        ).scalar_one()
        driver.execute(
            sql.SQL("GRANT {} TO {}").format(sql.Identifier(owner), sql.Identifier(role))
        )
    custody = tmp_path / "private"
    custody.mkdir(mode=0o700)
    monkeypatch.setenv("OTM_APPLICATION_CONFIG", str(PROJECT / "backend/config/application.toml"))
    monkeypatch.setenv("OTM_MFA_SECRET_DIRECTORY", str(custody))
    monkeypatch.setenv("OTM_FRONTEND_DIST", str(PROJECT / "frontend/dist"))
    url = make_url(os.environ["OTM_BACKEND_TEST_DATABASE_URL"]).set(
        username=role, password=password
    )
    monkeypatch.setenv("OTM_DATABASE_URL", url.render_as_string(hide_password=False))
    with pytest.raises(ValueError, match="RESTRICTED_RUNTIME_ROLE_REQUIRED"):
        create_local_application()
