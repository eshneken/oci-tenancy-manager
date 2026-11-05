"""Disposable PostgreSQL checks qualify immutable evidence and no desired-state writes."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from test_baseline_pinning_postgres import publish
from test_configuration_updates_postgres import children
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.configuration.drift import ConfigurationChecks
from otm.configuration.drift_contracts import ConfigurationCheckRequest, ConfigurationDriftQuery
from otm.configuration.drift_worker import ConfigurationCheckWorker
from otm.configuration.observation_contracts import ManagedObservation
from otm.configuration.observations import decode_observation
from otm.providers.configuration import SimulatedConfigurationFacade
from otm.storage.enqueue import CONFIGURATION_CHECK_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, configuration_check, operation, tenancy
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Reuse the actual actor, native transactional queue and scoped provider instead of bypassing
# admission.
def checks(c):
    service = ConfigurationChecks(
        c.store,
        policy=c.loader().policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(c.policy.workspace_id), task=CONFIGURATION_CHECK_TASK
        ),
    )
    worker = ConfigurationCheckWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        SimulatedConfigurationFacade(c.loader().policy),
    )
    c.workflow.configuration_checks = service
    return service, worker


# Every test snapshot is disposable; owner changes mimic external cloud drift without touching
# saved apps.
def scenario(c, identifier, state, category="policy"):
    with c.engine.begin() as connection:
        row = connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        objects = dict(row["configuration_observation"])
        original = decode_observation(objects[category]).binding
        objects[category] = ManagedObservation(
            binding=original,
            state=state,
            observed=original if state == "present" else None,
            complete=state != "unavailable",
        ).model_dump(mode="json")
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == identifier)
            .values(configuration_observation=objects)
        )


# A matching child check seals evidence while leaving every tenancy column and assigned version
# unchanged.
def test_matching_readonly_replay_and_projection(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    with c.engine.connect() as connection:
        before = dict(
            connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        )
    command = ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    receipt = service.start(c.principal, command)
    assert service.detail(c.principal, identifier).state == "checking"
    assert service.start(c.principal, command).operation_id == receipt.operation_id
    worker.run(receipt.operation_id)
    worker.run(receipt.operation_id)
    view = service.detail(c.principal, identifier)
    assert view.state == "matching" and view.confirmed_issue_count == 0
    assert service.directory(c.principal, ConfigurationDriftQuery()).total == 0
    assert (
        c.workflow.tenancy_detail(c.principal, identifier).tenancy.configuration_check_state
        == "matching"
    )
    assert (
        c.workflow.tenancies(c.principal, TenancyQuery()).items[0].configuration_check_state
        == "matching"
    )
    with c.engine.connect() as connection:
        assert (
            dict(
                connection.execute(select(tenancy).where(tenancy.c.id == identifier))
                .mappings()
                .one()
            )
            == before
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(configuration_check)
                .where(configuration_check.c.operation_id == receipt.operation_id)
            )
            == 1
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.operation_id == receipt.operation_id,
                    audit_event.c.kind == "configuration_check_outcome",
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == receipt.operation_id)
            )
            == "succeeded"
        )
    assert service.start(c.principal, command).state == "succeeded"


# An authorized absence persists across failed reads and clears only after a complete matching
# bundle.
def test_missing_unknown_and_recovery(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    scenario(c, identifier, "missing")
    first = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(first.operation_id)
    missing = service.detail(c.principal, identifier)
    assert (
        missing.state == "drifted"
        and missing.confirmed_issue_count == 1
        and missing.categories[0].state == "missing"
    )
    assert service.directory(c.principal, ConfigurationDriftQuery()).total == 1
    c.loader.return_value.execution_paused = True
    paused = service.detail(c.principal, identifier)
    assert paused.state == "unavailable" and paused.confirmed_issue_count == 1
    assert paused.categories[0].retained and not paused.can_check
    c.loader.return_value.execution_paused = False
    scenario(c, identifier, "unavailable")
    c.clock.return_value += timedelta(seconds=1)
    next_check = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(next_check.operation_id)
    unknown = service.detail(c.principal, identifier)
    assert (
        unknown.state == "unavailable"
        and unknown.confirmed_issue_count == 1
        and unknown.categories[0].retained
    )
    scenario(c, identifier, "present")
    last = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(last.operation_id)
    assert service.detail(c.principal, identifier).state == "matching"
    assert service.directory(c.principal, ConfigurationDriftQuery()).total == 0


# Later publication cannot change expected data; an assignment change before dispatch
# invalidates the read.
def test_assigned_not_latest_and_stale_dispatch(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    old = c.workflow.tenancy_detail(c.principal, identifier).tenancy.baseline_version_id
    publish(c, "750")
    receipt = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(receipt.operation_id)
    assert service.detail(c.principal, identifier).baseline_id == old
    assert service.detail(c.principal, identifier).state == "matching"
    pending = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == identifier)
            .values(revision=tenancy.c.revision + 1)
        )
    worker.run(pending.operation_id)
    assert service.detail(c.principal, identifier).state == "not_checked"
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(configuration_check.c.state).where(
                    configuration_check.c.operation_id == pending.operation_id
                )
            )
            == "superseded"
        )


# Unknown child IDs, duplicate active requests and unavailable policy never broaden accepted scope.
def test_scope_and_pending_guards(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    with pytest.raises(OrganizationConflict):
        service.detail(c.principal, uuid4())
    with pytest.raises(OrganizationConflict):
        service.start(
            c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=uuid4())
        )
    receipt = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    with pytest.raises(OrganizationConflict):
        service.start(
            c.principal,
            ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier),
        )
    c.loader.return_value.execution_paused = True
    worker.run(receipt.operation_id)
    assert service.detail(c.principal, identifier).state == "unavailable"


# Partial reads cannot confirm drift; wrong identities and unbound legacy rows remain unknown.
@pytest.mark.parametrize("scenario_name", ["different", "conflict", "partial", "unbound"])
def test_difference_binding_and_partial_proofs(workflow_case, scenario_name):
    import json

    from otm.operations.contracts import canonical_hash

    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    with c.engine.begin() as connection:
        row = connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        objects = dict(row["configuration_observation"])
        binding = decode_observation(objects["policy"]).binding
        payload = {"statements": ["Local disposable changed statement"]}
        changed = binding.model_copy(
            update={"payload": json.dumps(payload), "payload_hash": canonical_hash(payload)}
        )
        if scenario_name == "conflict":
            changed = binding.model_copy(update={"object_ocid": binding.object_ocid + "wrong"})
        objects["policy"] = ManagedObservation(
            binding=binding, observed=changed, state="present", complete=True
        ).model_dump(mode="json")
        if scenario_name == "partial":
            quota = decode_observation(objects["quota"]).binding
            objects["quota"] = ManagedObservation(
                binding=quota, observed=None, state="unavailable", complete=False
            ).model_dump(mode="json")
        if scenario_name == "unbound":
            objects.pop("tags")
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == identifier)
            .values(configuration_observation=objects)
        )
    receipt = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(receipt.operation_id)
    view = service.detail(c.principal, identifier)
    assert view.state == ("drifted" if scenario_name == "different" else "unavailable")
    assert view.confirmed_issue_count == (1 if scenario_name == "different" else 0)
    if scenario_name in {"partial", "unbound"}:
        assert all(item.state != "matching" for item in view.categories)


# Generated acquisition ordering wins when a later read has an earlier wall clock timestamp.
def test_acquisition_order_does_not_use_wall_clock(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    scenario(c, identifier, "missing")
    initial = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(initial.operation_id)
    first = service.detail(c.principal, identifier)
    scenario(c, identifier, "present")
    later = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    # The trusted worker clock is independently injected; the actual grant remains currently valid.
    worker.clock = lambda: c.clock.return_value - timedelta(seconds=5)
    worker.run(later.operation_id)
    latest = service.detail(c.principal, identifier)
    assert latest.checked_at < first.checked_at and latest.state == "matching"
    assert latest.confirmed_issue_count == 0


# The real inventory and both tabs agree across expiration, pending checks and complete refresh.
def test_expired_checks_are_not_four_configuration_differences(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker = checks(c)
    first = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    worker.run(first.operation_id)
    with c.engine.connect() as connection:
        original = (
            connection.execute(
                select(configuration_check).where(
                    configuration_check.c.operation_id == first.operation_id
                )
            )
            .mappings()
            .one()
        )
    c.clock.return_value += timedelta(hours=35)
    from test_local_auth_postgres import command

    # Observation age advances independently of a newly authenticated administrator session.
    issued = c.service.sign_in(command(c))
    c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    summary = service.detail(c.principal, identifier)
    inventory = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    confirmed = service.directory(c.principal, ConfigurationDriftQuery())
    checks_tab = service.directory(c.principal, ConfigurationDriftQuery(tab="checks"))
    assert summary.stale and inventory.configuration_check_stale
    assert summary.issue_count == inventory.configuration_issue_count == 0
    assert summary.confirmed_issue_count == inventory.configuration_confirmed_issue_count == 0
    assert confirmed.total == 0 and confirmed.stale_count == 1
    assert checks_tab.total == 1 and checks_tab.stale_count == 1 and checks_tab.unchecked_count == 0
    again = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=identifier)
    )
    during = c.workflow.tenancy_detail(c.principal, identifier).tenancy
    assert during.configuration_check_state == "checking" and during.configuration_issue_count == 0
    worker.run(again.operation_id)
    after = c.workflow.tenancy_detail(c.principal, identifier).tenancy
    assert after.configuration_check_state == "matching" and not after.configuration_check_stale
    assert after.configuration_issue_count == 0
    assert service.directory(c.principal, ConfigurationDriftQuery()).stale_count == 0
    with c.engine.connect() as connection:
        preserved = (
            connection.execute(
                select(configuration_check).where(configuration_check.c.id == original["id"])
            )
            .mappings()
            .one()
        )
    assert dict(preserved) == dict(original)
