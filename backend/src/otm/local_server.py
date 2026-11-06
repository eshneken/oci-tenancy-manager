"""Explicit laptop composition: real MFA/grants, restricted DB credentials and built public UI."""

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.auth.local import LocalLogin
from otm.auth.service import SessionService
from otm.maintenance import maintenance_engine, require_runtime_role
from otm.notifications.runtime import compose_notifications
from otm.operations.sandbox import SandboxAdmission, load_sandbox
from otm.organization.web import OrganizationWeb, load_profile
from otm.providers.configuration_simulator import SimulatedConfigurationFacade
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import SqlAuditExport
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.local_auth import SqlLocalAuth
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.organization import SqlOrganizationStore
from otm.storage.sessions import SqlSessionRepository
from otm.tenancies.workflows import OrganizationWorkflows


# Construct only explicitly configured laptop dependencies; never use a saved prototype connection.
def create_local_application():
    settings = load_settings(Path(os.environ["OTM_APPLICATION_CONFIG"]))
    if settings.local_auth is None or settings.local_server is None:
        raise ValueError("EXPLICIT_LOCAL_CONFIGURATION_REQUIRED")
    origin = settings.local_server.public_origin
    if urlsplit(origin).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("LOCAL_SERVER_MUST_USE_LOOPBACK")
    custody_path = Path(os.environ["OTM_MFA_SECRET_DIRECTORY"])
    frontend = Path(os.environ["OTM_FRONTEND_DIST"])
    if any(
        path.resolve().is_relative_to(frontend.resolve())
        for path in (
            custody_path,
            Path(os.environ["OTM_APPLICATION_CONFIG"]),
            *(
                [Path(os.environ["OTM_ORGANIZATION_CONFIG"])]
                if "OTM_ORGANIZATION_CONFIG" in os.environ
                else []
            ),
            *(
                [Path(os.environ["OTM_SANDBOX_CONFIG"])]
                if "OTM_SANDBOX_CONFIG" in os.environ
                else []
            ),
        )
    ):
        raise ValueError("SECRET_CUSTODY_CANNOT_BE_PUBLIC")
    engine = maintenance_engine(os.environ["OTM_DATABASE_URL"], None)

    # Authentication time comes from aware server UTC; browser clocks never authorize a request.
    def clock():
        return datetime.now(UTC)

    try:
        require_runtime_role(engine)
        grants = SqlAdministratorStore(
            engine,
            clock,
            local_issuer=settings.local_auth.issuer,
            trusted_issuers=frozenset({settings.local_auth.issuer}),
        )
        sessions = SessionService(
            SqlSessionRepository(engine), grants, settings.local_auth.issuer, clock
        )
        login = LocalLogin(
            settings, SqlLocalAuth(engine, settings, clock), DirectorySecrets(custody_path)
        )
        organization_store = SqlOrganizationStore(engine, sessions, clock)
        notifier, _, _ = compose_notifications(
            settings, workspace_queue(settings.local_auth.workspace_id)
        )
        workflow = OrganizationWorkflows(
            organization_store, mail_policy=settings.mail_policy(), notifications=notifier
        )
        if "OTM_SANDBOX_CONFIG" in os.environ:
            path = Path(os.environ["OTM_SANDBOX_CONFIG"])
            workspace = settings.local_auth.workspace_id

            # Reload pause/policy state at admission; a changed parent cannot retarget queued work.
            def organization_policy():
                return load_sandbox(path, workspace)

            policy = organization_policy().policy
            workflow = OrganizationWorkflows(
                organization_store,
                enqueuer=InspectionEnqueuer(
                    queue=workspace_queue(workspace), task=ORGANIZATION_TASK
                ),
                policy=policy,
                facade=SimulatedLifecycleFacade(policy),
                policy_loader=organization_policy,
                mail_policy=settings.mail_policy(),
                notifications=notifier,
            )
        from otm.configuration.drift import ConfigurationChecks
        from otm.configuration.rollout import ConfigurationRollouts
        from otm.providers.baseline_simulator import SimulatedBaselineQualifier
        from otm.storage.enqueue import CONFIGURATION_CHECK_TASK, CONFIGURATION_TASK

        checks = ConfigurationChecks(
            organization_store,
            policy=workflow.policy,
            policy_loader=workflow.policy_loader,
            enqueuer=InspectionEnqueuer(
                queue=workspace_queue(settings.local_auth.workspace_id),
                task=CONFIGURATION_CHECK_TASK,
            )
            if workflow.policy
            else None,
        )
        workflow.configuration_checks = checks
        from otm.financial.service import CostCollections
        from otm.storage.enqueue import COST_TASK

        costs = CostCollections(
            organization_store,
            policy=workflow.policy,
            policy_loader=workflow.policy_loader,
            profile=settings.costs,
            enqueuer=InspectionEnqueuer(
                queue=workspace_queue(settings.local_auth.workspace_id), task=COST_TASK
            )
            if workflow.policy
            else None,
        )
        workflow.cost_collections = costs
        app = create_app(
            sessions,
            BrowserSettings(public_origin=origin),
            login,
            grants,
            frontend,
            operations=SqlOperationDirectory(engine),
            audit_history=SqlAuditDirectory(engine),
            audit_export=SqlAuditExport(engine, clock),
            branding=settings.branding,
            email_policy=settings.mail_policy(),
            baseline_qualifier=SimulatedBaselineQualifier(),
            configuration_checks=checks,
            cost_collections=costs,
            configuration_rollouts=ConfigurationRollouts(
                organization_store,
                repair_facade=SimulatedConfigurationFacade(workflow.policy)
                if workflow.policy
                else None,
                policy=workflow.policy,
                policy_loader=workflow.policy_loader,
                enqueuer=InspectionEnqueuer(
                    queue=workspace_queue(settings.local_auth.workspace_id), task=CONFIGURATION_TASK
                )
                if workflow.policy
                else None,
            ),
            organization=OrganizationWeb(
                organization_store,
                clock,
                load_profile(
                    Path(os.environ["OTM_ORGANIZATION_CONFIG"])
                    if "OTM_ORGANIZATION_CONFIG" in os.environ
                    else None
                ),
                test_reset_enabled=settings.local_server.organization_reset_enabled,
                workflows=workflow,
            ),
            sandbox=(
                SandboxAdmission(
                    engine,
                    sessions,
                    Path(os.environ["OTM_SANDBOX_CONFIG"]),
                    settings.local_auth.workspace_id,
                    clock,
                )
                if "OTM_SANDBOX_CONFIG" in os.environ
                else None
            ),
        )
    except Exception:
        engine.dispose()
        raise

    # Dispose only this factory's pool when the server stops; no schema/credential cleanup is
    # implied.
    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            engine.dispose()

    app.router.lifespan_context = lifespan
    return app
