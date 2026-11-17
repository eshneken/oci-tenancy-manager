"""Existing-user import through restricted HTTPS roles and an independent native worker."""

from datetime import UTC, datetime

import pytest
from test_baseline_authoring import content
from test_organization_fixtures import envelope, example_config, example_records
from test_sandbox_runtime_postgres import run_browser_runtime, runtime

from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.organization.contracts import Intake
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.storage.organization import SqlOrganizationStore

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Seed prerequisites through domain services; adoption actions use the actual browser and worker.
def test_shared_import_existing_users_native_browser(runtime):
    c = runtime

    # Actual UTC keeps authenticated browser/native-worker freshness independent of fixture clocks.
    def clock():
        return datetime.now(UTC)

    store = SqlOrganizationStore(c.owner, c.sessions, clock)
    store.configure_initial(c.principal, example_config())
    store.ingest(
        c.principal, Intake(envelope=envelope("adoption", clock()), records=example_records())
    )
    author = BaselineAuthoring(store, SimulatedBaselineQualifier())
    draft = author.save(c.principal, SaveBaselineDraft(content=content()))
    author.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    run_browser_runtime(c, "e2e/import-adoption.spec.ts")
