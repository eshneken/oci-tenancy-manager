"""Native HTTPS/worker perimeter repair with a real desired-settings change in an owned fixture."""

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
from otm.recovery_console import parse_release_cidrs
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import SqlOrganizationStore
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Setup uses real domain workflows; only desired fixture settings change before the browser starts.
def test_recovery_network_native_browser(runtime):
    c = runtime

    # Keep authentication and all data evidence on the same aware wall-clock source.
    def clock():
        return datetime.now(UTC)

    store = SqlOrganizationStore(c.owner, c.sessions, clock)
    store.configure_initial(c.principal, example_config())
    store.ingest(
        c.principal, Intake(envelope=envelope("network-ui", clock()), records=example_records())
    )
    author = BaselineAuthoring(store, SimulatedBaselineQualifier())
    draft = author.save(c.principal, SaveBaselineDraft(content=content()))
    author.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    sandbox = load_sandbox(c.root / "simulation.json", c.settings.local_auth.workspace_id)
    loader = Mock(return_value=sandbox)
    initial = parse_release_cidrs("198.51.100.0/24,2001:db8::/32")
    facade = SimulatedLifecycleFacade(sandbox.policy, recovery_console=initial)
    workflow = OrganizationWorkflows(
        store,
        policy=sandbox.policy,
        policy_loader=loader,
        facade=facade,
        recovery_console=initial,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(sandbox.policy.workspace_id), task=ORGANIZATION_TASK
        ),
    )
    worker = OrganizationLifecycleWorker(
        c.owner, sandbox.policy.workspace_id, clock, loader, facade
    )
    prepared = SimpleNamespace(store=store, principal=c.principal, workflow=workflow, worker=worker)
    identifier = children(prepared, 1)[0]
    config = c.root / "application.toml"
    text = config.read_text()
    old = 'allowed_cidrs = ["198.51.100.0/24", "2001:db8::/32"]'
    assert old in text
    config.write_text(text.replace(old, 'allowed_cidrs = ["203.0.113.0/24"]'))
    run_browser_runtime(c, "e2e/recovery-network.spec.ts", {"OTM_E2E_TENANCY_ID": str(identifier)})
