"""Run local inspection and lifecycle simulations with native jobs and restricted roles."""

import os
from datetime import UTC, datetime
from pathlib import Path

import procrastinate
from psycopg.conninfo import make_conninfo

from otm.admin_cli import PrivateParser
from otm.configuration.drift_worker import ConfigurationCheckWorker
from otm.configuration.rollout_worker import ConfigurationUpdateWorker
from otm.maintenance import maintenance_engine, require_runtime_role
from otm.notifications.runtime import compose_notifications
from otm.notifications.worker import NotificationDeliveryWorker, register_notification_task
from otm.operations.execution import SimulatedInspectionWorker
from otm.operations.runner import (
    register_configuration_check_task,
    register_configuration_task,
    register_cost_task,
    register_inspection_task,
    register_organization_task,
)
from otm.operations.sandbox import SandboxAuthority, SandboxProvider, load_sandbox
from otm.providers.configuration_simulator import SimulatedConfigurationFacade
from otm.providers.inspection import TenancyInspection
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.settings import load_settings
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.enqueue import workspace_queue
from otm.storage.execution import SqlExecutionStore
from otm.tenancies.worker import OrganizationLifecycleWorker


# Consume the scoped native queue; once drains currently available work, not just one job.
def run_worker(*, once=False):
    settings = load_settings(Path(os.environ["OTM_APPLICATION_CONFIG"]))
    if settings.local_auth is None or settings.local_server is None:
        raise ValueError("EXPLICIT_LOCAL_CONFIGURATION_REQUIRED")
    path = Path(os.environ["OTM_SANDBOX_CONFIG"])
    policy = settings.local_auth
    load_sandbox(path, policy.workspace_id)
    engine = maintenance_engine(os.environ["OTM_DATABASE_URL"], None)
    try:
        if engine.url.host not in {"127.0.0.1", "localhost"}:
            raise ValueError("LOOPBACK_DATABASE_REQUIRED")
        require_runtime_role(engine)

        # Server UTC governs grants and observation freshness, independently of browser clocks.
        def clock():
            return datetime.now(UTC)

        grants = SqlAdministratorStore(
            engine, clock, local_issuer=policy.issuer, trusted_issuers=frozenset({policy.issuer})
        )
        worker = SimulatedInspectionWorker(
            SqlExecutionStore(engine, workspace=policy.workspace_id),
            SandboxAuthority(grants, path, policy.workspace_id),
            TenancyInspection(SandboxProvider(path, policy.workspace_id, clock), clock),
            clock,
        )
        url = engine.url
        conninfo = make_conninfo(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=url.port,
            user=url.username,
            password=url.password,
            dbname=url.database,
            connect_timeout=5,
            sslmode="disable",
            gssencmode="disable",
            options="-c timezone=UTC -c statement_timeout=10000 -c lock_timeout=5000",
        )
        native = procrastinate.App(
            connector=procrastinate.PsycopgConnector(conninfo=conninfo, min_size=1, max_size=2)
        )
        queue = workspace_queue(policy.workspace_id)
        register_inspection_task(native, worker, queue=queue)
        notifier, transport, email_enqueuer = compose_notifications(settings, queue)

        # Reload only trusted settings at dispatch; queued contacts cannot silently change mailbox.
        def mail_policy():
            from otm.email_policy import EmailPolicyBlocked

            current = load_settings(Path(os.environ["OTM_APPLICATION_CONFIG"]))
            if (
                current.notifications != settings.notifications
                or current.local_server != settings.local_server
            ):
                raise EmailPolicyBlocked("EMAIL_TRANSPORT_CHANGED")
            return current.mail_policy()

        if notifier is not None:
            register_notification_task(
                native,
                NotificationDeliveryWorker(
                    engine,
                    policy.workspace_id,
                    clock,
                    mail_policy,
                    transport,
                    email_enqueuer,
                    application_origin=settings.local_server.public_origin,
                    presence_context_loader=lambda: load_sandbox(path, policy.workspace_id),
                    cost_context_loader=lambda: (
                        load_sandbox(path, policy.workspace_id),
                        load_settings(Path(os.environ["OTM_APPLICATION_CONFIG"])).costs,
                    ),
                ),
                queue,
            )

        # The same explicit local policy gates lifecycle simulation; no real OCI adapter
        # is composed.
        def organization_policy():
            return load_sandbox(path, policy.workspace_id)

        register_organization_task(
            native,
            OrganizationLifecycleWorker(
                engine,
                policy.workspace_id,
                clock,
                organization_policy,
                SimulatedLifecycleFacade(organization_policy().policy),
                mail_policy_loader=mail_policy,
                notifications=notifier,
            ),
            queue,
        )
        register_configuration_task(
            native,
            ConfigurationUpdateWorker(
                engine,
                policy.workspace_id,
                clock,
                organization_policy,
                SimulatedConfigurationFacade(organization_policy().policy),
            ),
            queue,
        )
        register_configuration_check_task(
            native,
            ConfigurationCheckWorker(
                engine,
                policy.workspace_id,
                clock,
                organization_policy,
                SimulatedConfigurationFacade(organization_policy().policy),
            ),
            queue,
        )
        from otm.operations.runner import register_presence_task
        from otm.providers.presence_simulator import simulated_presence_inspection
        from otm.tenancies.presence_worker import UserPresenceWorker

        register_presence_task(
            native,
            UserPresenceWorker(
                engine,
                policy.workspace_id,
                clock,
                organization_policy,
                organization_policy().policy,
                simulated_presence_inspection,
                notifications=notifier,
            ),
            queue,
        )
        from otm.financial.worker import CostCollectionWorker
        from otm.providers.budget_simulator import SimulatedBudgetFacade
        from otm.storage.enqueue import COST_TASK, InspectionEnqueuer

        # Reload only operator settings; old work cannot silently adopt changed cost policy.
        def cost_policy():
            return load_settings(Path(os.environ["OTM_APPLICATION_CONFIG"])).costs

        register_cost_task(
            native,
            CostCollectionWorker(
                engine,
                policy.workspace_id,
                clock,
                organization_policy,
                SimulatedBudgetFacade(organization_policy().policy),
                InspectionEnqueuer(queue=queue, task=COST_TASK),
                profile=settings.costs,
                profile_loader=cost_policy,
                notifications=notifier,
            ),
            queue,
        )
        native.run_worker(
            queues=[queue],
            concurrency=1,
            wait=not once,
            listen_notify=False,
            fetch_job_polling_interval=1,
            shutdown_graceful_timeout=10,
            delete_jobs="never",
        )
    finally:
        engine.dispose()


# Operator process control accepts no passwords/DSNs/actor claims as arguments or printed errors.
def main(argv=None):
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument("--once", action="store_true")
        options = parser.parse_args(argv)
        print("Starting local simulated inspection worker.", flush=True)
        run_worker(once=options.once)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("LOCAL_WORKER_UNAVAILABLE: verify setup, private settings and Docker.")
        return 1
