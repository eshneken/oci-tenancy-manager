"""Native queued signing rotation through actual HTTPS and Chromium on an owned installation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_baseline_authoring import content
from test_organization_fixtures import envelope, example_config, example_records
from test_sandbox_runtime_postgres import run_browser_runtime, runtime
from test_signing_key_postgres import enroll

from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.operations.sandbox import load_sandbox
from otm.organization.contracts import Intake
from otm.providers.automation_keys_simulator import SimulatedAutomationKeys
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.providers.signing_key_rotation_simulator import SimulatedSigningKeys
from otm.storage.enqueue import (
    ORGANIZATION_TASK,
    SIGNING_KEY_TASK,
    InspectionEnqueuer,
    workspace_queue,
)
from otm.storage.organization import SqlOrganizationStore
from otm.tenancies.signing_key_records import SigningKeySetup
from otm.tenancies.signing_key_worker import SigningKeyWorker
from otm.tenancies.signing_keys import SigningKeys
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Setup uses normal domain handoff; the browser admits replacement work consumed by a real process.
def test_signing_rotation_native_browser(runtime):
    c = runtime

    # Use wall UTC for auth/provider freshness while keeping all fixture data synthetic.
    def clock():
        return datetime.now(UTC)

    store = SqlOrganizationStore(c.owner, c.sessions, clock)
    store.configure_initial(c.principal, example_config())
    store.ingest(
        c.principal,
        Intake(envelope=envelope("signing-browser", clock()), records=example_records()),
    )
    author = BaselineAuthoring(store, SimulatedBaselineQualifier())
    draft = author.save(c.principal, SaveBaselineDraft(content=content()))
    author.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    sandbox = load_sandbox(c.root / "simulation.json", c.settings.local_auth.workspace_id)
    loader = Mock(return_value=sandbox)
    inventory = SimulatedAutomationKeys(c.root / "automation-key-inventory", clock)
    private = c.root / "signing-key-custody"
    private.mkdir(mode=0o700)
    provider = SimulatedSigningKeys(private, inventory, clock)
    organization_queue = InspectionEnqueuer(
        workspace_queue(sandbox.policy.workspace_id), task=ORGANIZATION_TASK
    )
    key_queue = InspectionEnqueuer(
        workspace_queue(sandbox.policy.workspace_id), task=SIGNING_KEY_TASK
    )
    lifecycle = SimulatedLifecycleFacade(sandbox.policy, automation_keys=inventory)
    workflow = OrganizationWorkflows(
        store,
        policy=sandbox.policy,
        policy_loader=loader,
        facade=lifecycle,
        enqueuer=organization_queue,
        automation_key_inventory_enabled=True,
        signing_key_setup_enabled=True,
    )
    worker = OrganizationLifecycleWorker(
        c.owner,
        sandbox.policy.workspace_id,
        clock,
        loader,
        lifecycle,
        signing_setup=SigningKeySetup(key_queue, loader),
    )
    keys = SigningKeyWorker(
        c.owner, sandbox.policy.workspace_id, clock, loader, provider, key_queue, organization_queue
    )
    prepared = SimpleNamespace(
        store=store,
        principal=c.principal,
        workflow=workflow,
        worker=worker,
        engine=c.owner,
        policy=sandbox.policy,
        clock=clock,
        keys=keys,
        signing=SigningKeys(store, loader, key_queue),
    )
    enroll(prepared)
    run_browser_runtime(
        c, "e2e/signing-key-rotation.spec.ts", {"OTM_E2E_TENANCY_ID": str(prepared.child.id)}
    )
