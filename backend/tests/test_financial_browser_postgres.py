"""Focused native cost reads on independently seeded disposable managed tenancies."""

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
from otm.providers.baseline import SimulatedBaselineQualifier
from otm.providers.lifecycle import SimulatedLifecycleFacade
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import SqlOrganizationStore
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Build prerequisites through domain workflows so the browser isolates the new read path.
def test_cost_collection_native_browser(runtime):
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
    run_browser_runtime(c, "e2e/financial-costs.spec.ts", {"OTM_E2E_TENANCY_NAME": name})
