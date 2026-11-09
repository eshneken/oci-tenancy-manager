"""Real PostgreSQL repair admission, queue references, retained evidence and uncertainty fences."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case
from test_recovery_console_checks_postgres import OTHER, POLICY, console_case, refresh
from test_user_presence_checks_postgres import view

from otm.audit.contracts import AuditQuery
from otm.providers.recovery_console import RecoveryConsoleInspection, observed_fingerprint
from otm.providers.recovery_console_simulator import SimulatedRecoveryConsoleProvider
from otm.providers.recovery_network import RecoveryNetworkOutcome, RecoveryNetworkRepair
from otm.providers.recovery_network_simulator import (
    SimulatedRecoveryNetworkProvider,
    simulated_network_repair,
)
from otm.recovery_console import parse_release_cidrs
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.enqueue import RECOVERY_NETWORK_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import administrator, audit_event, operation, operation_step, tenancy
from otm.tenancies.recovery_network import RecoveryNetworkRepairs
from otm.tenancies.recovery_network_contracts import RecoveryNetworkRequest
from otm.tenancies.recovery_network_worker import RecoveryNetworkWorker

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case", "console_case"]


# The actual producer has its original networks; changing desired settings never edits that source.
@pytest.fixture
def repair_case(console_case):
    c = console_case
    c.service.recovery_console_loader.return_value = OTHER
    refresh(c)
    c.repair = RecoveryNetworkRepairs(
        c.service,
        simulated_network_repair,
        InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=RECOVERY_NETWORK_TASK),
    )
    c.workflow.recovery_network_repairs = c.repair
    c.repair_worker = RecoveryNetworkWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.service.recovery_console_loader,
        simulated_network_repair,
    )
    return c


# Use the public preview/accept contract and its unchanged replay key in each database scenario.
def admit(c):
    preview = c.repair.preview(c.principal, c.child.id)
    command = RecoveryNetworkRequest(
        client_request_key=uuid4(), preview_hash=preview.preview_hash, acknowledged=True
    )
    return preview, command, c.repair.start(c.principal, c.child.id, command)


# Repair persists actual state across independent refreshes without rewriting onboarding history.
def test_repair_readback_replay_and_safe_public_history(repair_case):
    c = repair_case
    assert view(c).recovery_console.state == "drift"
    with c.engine.connect() as connection:
        source = (
            connection.execute(
                select(audit_event).where(audit_event.c.kind == "onboarding_outcome")
            )
            .mappings()
            .all()
        )
    before = [(r["id"], r["data_hash"]) for r in source]
    preview, command, accepted = admit(c)
    assert preview.desired_fingerprint == OTHER.fingerprint
    assert c.repair.start(c.principal, c.child.id, command).operation_id == accepted.operation_id
    c.repair_worker.run(accepted.operation_id)
    c.repair_worker.run(accepted.operation_id)
    assert c.repair.start(c.principal, c.child.id, command).operation_id == accepted.operation_id
    detail = SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, accepted.operation_id)
    assert detail.operation.state == "succeeded"
    assert detail.operation.result_tenancy_id == c.child.id
    assert detail.steps[0].safe_code == "RECOVERY_NETWORK_VERIFIED"
    refresh(c)
    result = view(c)
    assert result.recovery_console.state == "verified"
    refresh(c)
    assert view(c).recovery_console.state == "verified"
    audit = SqlAuditDirectory(c.engine).directory(c.policy.workspace_id, AuditQuery())
    public = detail.model_dump_json() + audit.model_dump_json() + result.model_dump_json()
    assert (
        "198.51.100" not in public and "203.0.113" not in public and "compare_token" not in public
    )
    with c.engine.connect() as connection:
        assert before == [
            (r["id"], r["data_hash"])
            for r in connection.execute(
                select(audit_event).where(audit_event.c.kind == "onboarding_outcome")
            ).mappings()
        ]
        assert (
            connection.scalar(select(tenancy.c.operation_id).where(tenancy.c.id == c.child.id))
            is None
        )
    # Equal application clocks cannot reorder actual applied captures: source check ordinals decide.
    for desired in (POLICY, OTHER):
        c.service.recovery_console_loader.return_value = desired
        refresh(c)
        assert view(c).recovery_console.state == "drift"
        _, _, next_repair = admit(c)
        c.repair_worker.run(next_repair.operation_id)
        refresh(c)
        assert view(c).recovery_console.state == "verified"


# Unchecked consent, stale previews, conflicting work and revoked authority never perform a write.
@pytest.mark.parametrize("fault", ["unchecked", "preview", "busy", "desired", "revoked"])
def test_guarded_admission_and_dispatch(repair_case, fault):
    c = repair_case
    preview = c.repair.preview(c.principal, c.child.id)
    command = RecoveryNetworkRequest(
        client_request_key=uuid4(),
        preview_hash=preview.preview_hash,
        acknowledged=fault != "unchecked",
    )
    if fault == "preview":
        command = command.model_copy(update={"preview_hash": "0" * 64})
    if fault in {"unchecked", "preview"}:
        with pytest.raises(OrganizationConflict):
            c.repair.start(c.principal, c.child.id, command)
        return
    first = c.repair.start(c.principal, c.child.id, command)
    if fault == "busy":
        with pytest.raises(OrganizationConflict):
            c.repair.start(
                c.principal, c.child.id, command.model_copy(update={"client_request_key": uuid4()})
            )
        c.repair_worker.run(first.operation_id)
        return
    if fault == "desired":
        c.service.recovery_console_loader.return_value = None
    else:
        with c.engine.begin() as connection:
            connection.execute(
                update(administrator)
                .where(
                    administrator.c.issuer == c.principal.session.issuer,
                    administrator.c.subject == c.principal.session.subject,
                )
                .values(authorization_revision=uuid4())
            )
    c.repair_worker.run(first.operation_id)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(select(operation.c.state).where(operation.c.id == first.operation_id))
            == "failed"
        )
        assert (
            connection.scalar(select(tenancy.c.operation_id).where(tenancy.c.id == c.child.id))
            is None
        )


# A lost/unknown write effect retains its exact durable attempt and blocks any replacement repair.
def test_unknown_effect_and_interrupted_attempt_are_not_replayed(repair_case):
    c = repair_case
    _, _, accepted = admit(c)
    facade = Mock()
    facade.apply.return_value = RecoveryNetworkOutcome(effect="unknown")
    c.repair_worker.factory = Mock(return_value=facade)
    # Preserve a real qualified authority while injecting only the independent write outcome.
    original = simulated_network_repair

    # Delegate reads to the real simulator; an unknown mutation cannot invent capture evidence.
    def factory(command, capture, clock):
        real = original(command, capture, clock)
        facade.preview.side_effect = real.preview
        return facade

    c.repair_worker.factory = factory
    c.repair_worker.run(accepted.operation_id)
    c.repair_worker.run(accepted.operation_id)
    facade.apply.assert_called_once()
    with c.engine.connect() as connection:
        row = (
            connection.execute(select(operation).where(operation.c.id == accepted.operation_id))
            .mappings()
            .one()
        )
        step = (
            connection.execute(
                select(operation_step).where(operation_step.c.operation_id == accepted.operation_id)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "needs_attention" and row["effect_knowledge"] == "unknown"
        assert step["inputs"]["compare_token"]
        assert (
            connection.scalar(select(tenancy.c.operation_id).where(tenancy.c.id == c.child.id))
            == accepted.operation_id
        )
    with pytest.raises(OrganizationConflict):
        c.repair.preview(c.principal, c.child.id)


# A restarted running worker never resends an unconfirmed security change.
def test_interrupted_worker_holds_without_second_send(repair_case):
    c = repair_case
    _, _, accepted = admit(c)
    assert c.repair_worker.begin(accepted.operation_id)
    c.repair_worker.factory = Mock()
    c.repair_worker.run(accepted.operation_id)
    c.repair_worker.factory.assert_not_called()
    detail = SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, accepted.operation_id)
    assert detail.operation.state == "needs_attention"
    assert detail.steps[0].safe_code == "RECOVERY_NETWORK_UNKNOWN"


# Independently observed external changes can be repaired only after a matching fresh check.
@pytest.mark.parametrize("phase", ["unrefreshed", "refreshed", "after_admission"])
def test_external_actual_state_is_not_confused_with_setup_capture(repair_case, phase):
    c = repair_case
    accepted = admit(c)[2] if phase == "after_admission" else None
    with c.engine.connect() as connection:
        child = (
            connection.execute(select(tenancy).where(tenancy.c.id == c.child.id)).mappings().one()
        )
        snapshot = c.service.snapshot(
            connection, c.policy.workspace_id, dict(child, operation_id=None)
        )
        setup = c.reader.source(connection, snapshot).recovery_console
    actual = {
        "capture": setup.model_copy(
            update={
                "facts": setup.facts.model_copy(
                    update={"perimeter": parse_release_cidrs("192.0.2.0/24")}
                )
            }
        ),
        "writes": 0,
    }

    # This independent provider models external actual state without rewriting original setup rows.
    class ExternalNetworkProvider(SimulatedRecoveryNetworkProvider):
        # Persist only the independent simulated provider effect, then let the caller read it again.
        def replace_network(self, command):
            outcome = super().replace_network(command)
            if outcome.effect == "known":
                actual["capture"] = outcome.capture
                actual["writes"] += 1
            return outcome

    # The repair connection reads actual provider state instead of seeding it from desired values.
    def repair_factory(command, capture, clock):
        return RecoveryNetworkRepair(
            ExternalNetworkProvider(command, actual["capture"], clock), clock
        )

    # Read-only inspection reports the same independent actual state and its complete policy facts.
    def read_factory(command, source, clock):
        return RecoveryConsoleInspection(
            SimulatedRecoveryConsoleProvider(
                command.target, command.context, actual["capture"].facts, clock
            ),
            clock,
        )

    c.repair.factory = c.repair_worker.factory = repair_factory
    c.reader.recovery_inspection_factory = read_factory
    if phase == "unrefreshed":
        with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
            c.repair.preview(c.principal, c.child.id)
        assert actual["writes"] == 0
        return
    if phase == "refreshed":
        refresh(c)
        preview, _, accepted = admit(c)
        assert preview.observed_fingerprint == observed_fingerprint(actual["capture"].facts)
        assert preview.observed_fingerprint != observed_fingerprint(setup.facts)
    c.repair_worker.run(accepted.operation_id)
    result = SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, accepted.operation_id)
    assert result.operation.state == ("succeeded" if phase == "refreshed" else "failed")
    assert actual["writes"] == (1 if phase == "refreshed" else 0)
    if phase == "refreshed":
        refresh(c)
        assert view(c).recovery_console.state == "verified"
    assert setup.facts.perimeter.fingerprint == POLICY.fingerprint
