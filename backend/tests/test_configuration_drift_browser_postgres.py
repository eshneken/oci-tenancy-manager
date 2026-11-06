"""Focused native read checks on independently seeded disposable managed tenancies."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_baseline_authoring import content
from test_configuration_updates_postgres import children
from test_organization_fixtures import envelope, example_config, example_records
from test_sandbox_runtime_postgres import run_browser_runtime, runtime

from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.operations.sandbox import load_sandbox
from otm.organization.contracts import Intake
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import SqlOrganizationStore
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Build prerequisites through domain workflows so the browser isolates the new read path.
def configuration_browser(runtime, *, repair=False):
    c = runtime

    # Match the real local server's aware UTC clock without mocking authentication freshness.
    def clock():
        return datetime.now(UTC)

    store = SqlOrganizationStore(c.owner, c.sessions, clock)
    store.configure_initial(c.principal, example_config())
    store.ingest(
        c.principal, Intake(envelope=envelope("focused", clock()), records=example_records())
    )
    author = BaselineAuthoring(store, SimulatedBaselineQualifier())
    draft = author.save(c.principal, SaveBaselineDraft(content=content()))
    author.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    sandbox = load_sandbox(c.root / "simulation.json", c.settings.local_auth.workspace_id)
    loader = Mock(return_value=sandbox)
    facade = SimulatedLifecycleFacade(sandbox.policy)
    workflow = OrganizationWorkflows(
        store,
        policy=sandbox.policy,
        policy_loader=loader,
        facade=facade,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(sandbox.policy.workspace_id), task=ORGANIZATION_TASK
        ),
    )
    worker = OrganizationLifecycleWorker(
        c.owner, sandbox.policy.workspace_id, clock, loader, facade
    )
    prepared = SimpleNamespace(store=store, principal=c.principal, workflow=workflow, worker=worker)
    identifier = children(prepared, 1)[0]
    name = workflow.tenancy_detail(c.principal, identifier).tenancy.name
    extra = {"OTM_E2E_TENANCY_NAME": name}
    if repair:
        import json
        from uuid import uuid4

        from repair_examples import OVERRIDE_PAYLOADS, OVERRIDES
        from test_configuration_drift_postgres import checks
        from test_configuration_repairs_postgres import alter_managed_observation
        from test_configuration_updates_postgres import updates
        from test_tenancy_overrides_postgres import override_command

        from otm.configuration.drift_contracts import ConfigurationCheckRequest

        prepared = SimpleNamespace(
            **vars(prepared), engine=c.owner, policy=sandbox.policy, loader=loader, clock=clock
        )
        rollouts, apply_worker, _ = updates(prepared)
        overridden = rollouts.start(
            c.principal, override_command(prepared, rollouts, identifier, OVERRIDES)
        )
        apply_worker.run(overridden.operation_id)
        assert rollouts.progress(c.principal, overridden.operation_id).state == "succeeded"
        for category in ("policy", "quota", "budget", "tags"):
            alter_managed_observation(
                prepared, identifier, category, "missing" if category == "quota" else "different"
            )
        service, checker = checks(prepared)
        accepted = service.start(
            c.principal,
            ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier),
        )
        checker.run(accepted.operation_id)
        assert service.detail(c.principal, identifier).confirmed_issue_count == 4
        # Expected values are authored synthetic fixtures, never copied from provider readback.
        extra["OTM_E2E_REPAIR_EXPECTED"] = json.dumps(OVERRIDE_PAYLOADS)
    run_browser_runtime(
        c,
        "e2e/configuration-repair.spec.ts" if repair else "e2e/configuration-drift.spec.ts",
        extra,
    )


# Keep the original matching-check journey on its own owned module-scoped installation.
def test_configuration_check_native_browser(runtime):
    configuration_browser(runtime)
