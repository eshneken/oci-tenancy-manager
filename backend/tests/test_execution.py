"""Current-authority and read-only worker behavior, independent of database IO."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import procrastinate
import pytest
from test_admission_service import admission

from otm.operations.execution import SimulatedInspectionWorker, current_grant
from otm.operations.execution_contracts import ClaimedInspection, CommittedInspection, DispatchGrant
from otm.operations.runner import register_inspection_task
from otm.providers.inspection import ProviderContractError
from otm.providers.inspection_contracts import ExecutionContext, TenancyFacts
from otm.providers.inspection_simulator import SimulatedAccess, SimulatedTenancy

__all__ = ["admission"]


# Pair frozen admission, independent provider facts and explicit current authority.
@pytest.fixture
def execution_case(admission, inspection):
    committed = CommittedInspection(
        operation_id=admission.accepted.operation_id,
        operation_revision=1,
        intent_event_id=uuid4(),
        intent_revision=1,
        actor=admission.actor,
        intent=admission.intent,
    )
    grant = DispatchGrant(
        workspace_id=admission.intent.workspace_id,
        actor_key=admission.actor.key,
        policy_revision=admission.intent.policy_revision,
        runtime_policy_revision=uuid4(),
        access_binding_id=admission.intent.access_binding_id,
        credential_generation=1,
    )
    context = ExecutionContext(
        workspace_id=admission.intent.workspace_id,
        operation_id=committed.operation_id,
        step_key="inspect_target",
        attempt_id=uuid4(),
        intent_revision=1,
        execution_generation=1,
        access_binding_id=grant.access_binding_id,
        credential_generation=1,
    )
    attempt = ClaimedInspection(
        committed=committed, operation_revision=2, context=context, grant=grant
    )
    provider = inspection.provider
    access = SimulatedAccess(
        workspace_id=context.workspace_id,
        access_binding_id=context.access_binding_id,
        credential_generation=1,
        permitted=True,
        tenancy_ocids=frozenset({admission.request.tenancy_ocid}),
    )
    tenancy = SimulatedTenancy(
        workspace_id=context.workspace_id,
        visible_at=inspection.clock.now(),
        facts=TenancyFacts(
            **admission.intent.target.model_dump(),
            actual_name="Example child",
            home_region_key="EXAMPLE-HOME",
            home_region_identifier=None,
            role="CHILD",
            observed_at=inspection.clock.now(),
        ),
    )
    provider.set_access(access)
    provider.set_tenancy(tenancy)
    store = Mock(load=Mock(return_value=committed), claim=Mock(return_value=attempt))
    authority = Mock(require_inspection=Mock(return_value=grant))
    worker = SimulatedInspectionWorker(store, authority, inspection.service, inspection.clock.now)
    return SimpleNamespace(
        committed=committed,
        grant=grant,
        attempt=attempt,
        store=store,
        authority=authority,
        worker=worker,
        inspection=inspection,
        provider=provider,
        access=access,
        tenancy=tenancy,
    )


# Return the typed publication argument to inspect durable evidence.
def outcome(case):
    return case.store.finish.call_args.args[2]


# Three current checks precede a confirmed simulated result; no import or setup is claimed.
def test_confirmed_inspection_records_only_read_milestone(execution_case):
    case = execution_case
    case.worker.run(case.committed.operation_id)
    assert case.authority.require_inspection.call_count == 3
    result = outcome(case)
    assert result.provider_mode == "simulated" and result.safe_code == "TENANCY_INSPECTED"
    assert result.result.milestone == "tenancy_inspected"
    assert result.context == case.attempt.context
    case.store.claim.assert_called_once_with(
        case.committed, case.grant, case.inspection.clock.now()
    )


# An authorizer's malformed scope cannot silently change an accepted target or actor.
@pytest.mark.parametrize(
    "field", ["workspace_id", "actor_key", "policy_revision", "access_binding_id"]
)
def test_current_grant_cannot_retarget_frozen_scope(execution_case, field):
    case = execution_case
    value = "other" if field in {"workspace_id", "actor_key"} else uuid4()
    case.authority.require_inspection.return_value = case.grant.model_copy(update={field: value})
    with pytest.raises(PermissionError):
        current_grant(case.authority, case.committed)
    case.worker.run(case.committed.operation_id)
    case.store.claim.assert_not_called()
    assert outcome(case).safe_code == "DISPATCH_NOT_AUTHORIZED"
    assert outcome(case).context is None and outcome(case).result is None


# No provider call or raw authorization diagnostics enter durable evidence.
def test_authorization_failure_does_not_retain_raw_private_error(execution_case):
    case = execution_case
    case.authority.require_inspection.side_effect = RuntimeError("private-example-never-record")
    case.worker.inspection = Mock()
    case.worker.run(case.committed.operation_id)
    case.worker.inspection.inspect.assert_not_called()
    assert "private-example" not in outcome(case).model_dump_json()


# Entitlement or credential-generation change blocks a completed or pending read.
@pytest.mark.parametrize("when", ["before_read", "after_read"])
def test_mid_attempt_revocation_never_publishes_confirmed_facts(execution_case, when):
    case = execution_case
    changed = case.grant.model_copy(update={"credential_generation": 2})
    case.authority.require_inspection.side_effect = (
        [case.grant, changed] if when == "before_read" else [case.grant, case.grant, changed]
    )
    case.worker.run(case.committed.operation_id)
    assert outcome(case).safe_code == "DISPATCH_CONTEXT_CHANGED"
    assert outcome(case).result is None


# Unavailable data never becomes absence, adopted tenancy or configured access.
@pytest.mark.parametrize("fault", ["denied", "timeout", "unsupported"])
def test_provider_unknown_or_unsupported_remains_unresolved(execution_case, fault):
    case = execution_case
    case.provider.set_tenancy(case.tenancy.model_copy(update={"fault": fault}))
    case.worker.run(case.committed.operation_id)
    assert outcome(case).result.kind in {"unobservable", "unsupported"}
    assert outcome(case).safe_code != "TENANCY_INSPECTED"


# An invalid adapter never leaks arbitrary output into the outcome record.
def test_provider_contract_error_is_fixed_and_contains_no_raw_output(execution_case):
    case = execution_case
    case.worker.inspection = Mock(
        inspect=Mock(side_effect=ProviderContractError("private-example"))
    )
    case.worker.run(case.committed.operation_id)
    assert outcome(case).safe_code == "INSPECTION_PROVIDER_REJECTED"
    assert outcome(case).result is None


# Duplicate delivery or a lost claim does not call the provider or append an outcome.
@pytest.mark.parametrize("boundary", ["load", "claim"])
def test_missing_terminal_or_raced_work_is_a_noop(execution_case, boundary):
    case = execution_case
    getattr(case.store, boundary).return_value = None
    case.worker.inspection = Mock()
    case.worker.run(case.committed.operation_id)
    case.worker.inspection.inspect.assert_not_called()
    case.store.finish.assert_not_called()


# Internal task data is validated rather than interpreted as a query or command.
def test_untyped_operation_reference_fails_before_store(execution_case):
    with pytest.raises(ValueError, match="INVALID_OPERATION_REFERENCE"):
        execution_case.worker.run("bad-reference")
    execution_case.store.load.assert_not_called()


# The fixed task registers without live IO or generic payload/action dispatch.
@pytest.mark.parametrize("reference", ["valid", "bad", None, 123])
def test_native_task_accepts_only_uuid_reference_without_opening_connector(
    execution_case, reference
):
    connector = procrastinate.PsycopgConnector()
    app = procrastinate.App(connector=connector)
    worker = Mock()
    task = register_inspection_task(app, worker)
    value = str(execution_case.committed.operation_id) if reference == "valid" else reference
    if reference == "valid":
        task.func(value)
        worker.run.assert_called_once_with(execution_case.committed.operation_id)
    else:
        with pytest.raises(ValueError, match="INVALID_OPERATION_REFERENCE"):
            task.func(value)
        worker.run.assert_not_called()
