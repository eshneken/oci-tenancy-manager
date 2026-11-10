"""Durable scoped key inventory through real onboarding, SQL evidence and operation projection."""

from datetime import timedelta
from functools import partial
from uuid import uuid4

import pytest
from test_local_auth_postgres import command
from test_organization_workflows_postgres import (
    action,
    complete_setup,
    factors,
    login_case,
    organization_case,
    workflow_case,
)
from test_user_presence_checks_postgres import make_presence

from otm.operations.views import OperationQuery
from otm.providers.automation_keys_simulator import (
    SimulatedAutomationKeys,
    simulated_key_inspection,
)
from otm.storage.operation_directory import SqlOperationDirectory
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Explicit opt-in creates public metadata at configure, persists SQL evidence and survives restart.
@pytest.mark.parametrize("action_name", ["create_tenancy", "import_tenancy"])
def test_configure_read_restart_and_history(workflow_case, tmp_path, action_name):
    c = workflow_case
    store = SimulatedAutomationKeys(tmp_path / "keys", c.clock)
    c.provider.automation_keys = store
    c.workflow.automation_key_inventory_enabled = True
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    fields = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimimportkeys"}
        if action_name == "import_tenancy"
        else {}
    )
    _, receipt = action(c, person.id, action_name, **fields)
    assert not list(store.directory.iterdir())
    complete_setup(c, receipt.operation_id)
    first = list(store.directory.iterdir())[0].read_bytes()
    # Reusing the permanent capture on a later read never refreshes the creation timestamp.
    c.clock.return_value += timedelta(days=29)
    store = SimulatedAutomationKeys(store.directory, c.clock)
    issued = c.service.sign_in(command(c))
    c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    from otm.providers.presence_simulator import simulated_presence_inspection
    from otm.storage.enqueue import PRESENCE_TASK, InspectionEnqueuer, workspace_queue
    from otm.tenancies.presence import PresenceChecks
    from otm.tenancies.presence_worker import UserPresenceWorker

    service = PresenceChecks(
        c.store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=PRESENCE_TASK),
    )
    c.workflow.presence_checks = service
    reader = UserPresenceWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.workflow.policy,
        simulated_presence_inspection,
        key_inspection_factory=partial(simulated_key_inspection, store),
    )
    queued = service.start(c.principal, child.id, PresenceCheckRequest(client_request_key=uuid4()))
    reader.run(queued.operation_id)
    result = c.workflow.required_users(c.principal, child.id).automation_keys
    assert result.state == "known" and result.keys[0].age_state == "due_soon"
    assert list(store.directory.iterdir())[0].read_bytes() == first
    c.clock.return_value += timedelta(days=2)
    issued = c.service.sign_in(command(c))
    c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    current = c.workflow.required_users(c.principal, child.id).automation_keys
    assert current.state == "stale" and current.keys[0].age_state == "overdue"
    detail = SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, queued.operation_id)
    historical = next(e.automation_keys for e in detail.events if e.automation_keys)
    assert historical.keys[0].age_state == "due_soon" and historical.keys[0].age_days == 29
    assert historical.age_as_of == result.checked_at
    assert (
        "private_key" not in detail.model_dump_json() and "fingerprint" in detail.model_dump_json()
    )
    reader.run(queued.operation_id)
    assert (
        SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, queued.operation_id) == detail
    )
    directory = SqlOperationDirectory(c.engine).directory(c.policy.workspace_id, OperationQuery())
    assert directory.total >= 2


# Legacy capture stays unavailable through repeated provider reads and never creates fixture files.
def test_legacy_reads_do_not_backfill(workflow_case, tmp_path):
    c = make_presence(workflow_case)
    store = SimulatedAutomationKeys(tmp_path / "keys", c.clock)
    c.reader.key_inspection_factory = partial(simulated_key_inspection, store)
    for _ in range(2):
        queued = c.service.start(
            c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
        )
        c.reader.run(queued.operation_id)
        assert (
            c.workflow.required_users(c.principal, c.child.id).automation_keys.state
            == "unavailable"
        )
    assert not list(store.directory.iterdir())
