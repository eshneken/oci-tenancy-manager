"""Current-cycle monetary invariants with independent typed provider facts, no OCI or database."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from otm.configuration.drift_contracts import CheckTarget
from otm.configuration.override_contracts import OverrideValues
from otm.financial.context import source_context, target_source
from otm.financial.contracts import (
    BudgetCycleFacts,
    BudgetReadResult,
    CostPolicy,
    CostTarget,
    Money,
)
from otm.financial.normalization import month_bounds, normalize, project, snapshot_order
from otm.operations.contracts import canonical_hash
from otm.providers.budget import BudgetReadUnavailable
from otm.providers.budget_simulator import SimulatedBudgetFacade
from otm.providers.configuration import desired_objects

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


# Build explicit source/target/response fixtures with no dependency on private runtime data.
def example():
    from test_baseline_authoring import content

    from otm.configuration.contracts import BaselineVersion

    parent = "ocid1.tenancy.oc1..otmsimparent"
    child = "ocid1.tenancy.oc1..otmsimchild"
    policy = SimpleNamespace(
        workspace_id="synthetic-costs",
        organization_id="synthetic-org",
        parent_tenancy_ocid=parent,
        policy_revision=uuid4(),
        access_binding_id=uuid4(),
    )
    baseline = BaselineVersion(
        id=uuid4(),
        version_number=1,
        content=content(),
        content_hash=canonical_hash(content().model_dump(mode="json")),
        publication_mode="simulated",
        published_at=NOW,
        published_by="synthetic-admin",
        published_by_name="Administrator",
        edit_revision=1,
        created_by="synthetic-admin",
        created_at=NOW,
    )
    configuration = CheckTarget(
        tenancy_id=uuid4(),
        tenancy_name="Example sandbox",
        tenancy_ocid=child,
        parent_tenancy_ocid=parent,
        organization_id=policy.organization_id,
        revision=1,
        policy_revision=policy.policy_revision,
        baseline_id=baseline.id,
        baseline_hash=baseline.content_hash,
        configuration_id=None,
        effective_hash=baseline.content_hash,
        overrides=OverrideValues(),
        bindings={},
        bindings_hash=canonical_hash({}),
        qualified=False,
    )
    objects = desired_objects(configuration, baseline)
    bindings = {k: v.object_ocid for k, v in objects.items()}
    configuration = configuration.model_copy(
        update={"bindings": bindings, "bindings_hash": canonical_hash(bindings), "qualified": True}
    )
    target = CostTarget(
        configuration=configuration,
        budget_ocid=bindings["budget"],
        source_access_binding_id=policy.access_binding_id,
        profile=CostPolicy(),
        period_start=month_bounds(NOW)[0],
        period_end=month_bounds(NOW)[1],
    )
    row = dict(
        id=configuration.tenancy_id,
        tenancy_ocid=child,
        parent_tenancy_ocid=parent,
        organization_id=policy.organization_id,
        revision=1,
        baseline_version_id=baseline.id,
        desired_configuration_id=None,
        configuration_observation={k: v.model_dump(mode="json") for k, v in objects.items()},
        status="active",
        provider_mode="simulated",
        operation_id=None,
    )
    response = BudgetReadResult(
        budget_ocid=target.budget_ocid,
        compartment_ocid=child,
        target_type="COMPARTMENT",
        targets=(child,),
        cycle_facts=BudgetCycleFacts(
            reset_period="MONTHLY",
            processing_period_type="MONTH",
            budget_processing_period_start_offset=1,
        ),
        amount="250.0000",
        actual_spend="120.0000",
        forecasted_spend="320.0000",
        time_spend_computed=NOW,
        captured_at=NOW,
    )
    return SimpleNamespace(
        policy=policy, baseline=baseline, target=target, row=row, response=response, objects=objects
    )


# Keep legitimate signed adjustments and zero while rejecting coerced/excess/nonfinite money.
@pytest.mark.parametrize("value", ["0.0000", "-12.0001", "9999999999999999.9999"])
def test_canonical_money_valid(value):
    assert TypeAdapter(Money).validate_python(value) == value


# Wire values cannot silently round, overflow or become IEEE-754 NaN/Infinity.
@pytest.mark.parametrize(
    "value",
    [
        0,
        True,
        1.5,
        "NaN",
        "Infinity",
        "1e3",
        "1.00001",
        "01.0000",
        "10000000000000000.0000",
        "1.00",
        " 1.0000",
    ],
)
def test_canonical_money_invalid(value):
    with pytest.raises(ValidationError):
        TypeAdapter(Money).validate_python(value)


# UTC monthly boundaries include leap years and December/January rollover.
@pytest.mark.parametrize(
    "at,end",
    [
        (datetime(2026, 12, 31, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
        (datetime(2024, 2, 29, tzinfo=UTC), datetime(2024, 3, 1, tzinfo=UTC)),
    ],
)
def test_month_boundaries(at, end):
    assert month_bounds(at)[1] == end


# Forecast is the full estimate, independent of actual, and both overrun indicators are independent.
def test_same_response_and_independent_indicators():
    c = example()
    snapshot = normalize(c.target, c.response, NOW)
    view = project(snapshot, CostPolicy(), NOW)
    assert view.actual == "120.0000" and view.forecast == "320.0000" and view.budget == "250.0000"
    assert not view.actual_over_budget and view.forecast_over_budget
    both = normalize(c.target, c.response.model_copy(update={"actual_spend": "250.0001"}), NOW)
    assert project(both, CostPolicy(), NOW).actual_over_budget
    assert Decimal(project(both, CostPolicy(), NOW).actual) - Decimal(view.budget) == Decimal(
        "0.0001"
    )


# Optional null forecast never borrows an older value; signed/zero values stay real amounts.
def test_partial_and_signed_values():
    c = example()
    snapshot = normalize(
        c.target,
        c.response.model_copy(update={"actual_spend": "-3.0000", "forecasted_spend": None}),
        NOW,
    )
    view = project(snapshot, CostPolicy(), NOW)
    assert view.state == "partial" and view.forecast is None and view.actual == "-3.0000"
    empty = project(None, CostPolicy(), NOW)
    assert empty.actual is None and empty.state == "not_collected"
    assert project(None, CostPolicy(), NOW, failure="COST_READ_UNAVAILABLE").state == "unavailable"
    assert (
        project(None, CostPolicy(), NOW, failure="COST_SOURCE_UNQUALIFIED").state == "unqualified"
    )


# Wrong identities and malformed source timing are rejected rather than adopted by display name.
@pytest.mark.parametrize(
    "damage",
    [
        {"budget_ocid": "ocid1.budget.oc1..other"},
        {"compartment_ocid": "ocid1.tenancy.oc1..other"},
        {"target_type": "TAG"},
        {"targets": ()},
        {"captured_at": NOW + timedelta(seconds=1)},
        {"captured_at": datetime(2026, 10, 1, tzinfo=UTC)},
        {"amount": "-1.0000"},
    ],
)
def test_wrong_scope_and_budget_rejected(damage):
    c = example()
    with pytest.raises(ValueError):
        normalize(c.target, c.response.model_copy(update=damage), NOW)


# Monthly inference requires actual computation time and qualified reset/processing facts.
@pytest.mark.parametrize(
    "damage",
    [
        {"time_spend_computed": None},
        {"time_spend_computed": NOW + timedelta(seconds=1)},
        {
            "cycle_facts": BudgetCycleFacts(
                reset_period="SINGLE_USE",
                processing_period_type="MONTH",
                budget_processing_period_start_offset=1,
            )
        },
        {
            "cycle_facts": BudgetCycleFacts(
                reset_period="MONTHLY",
                processing_period_type="INVOICE",
                budget_processing_period_start_offset=1,
            )
        },
    ],
)
def test_source_qualification_is_explicit(damage):
    c = example()
    s = normalize(c.target, c.response.model_copy(update=damage), NOW)
    assert s.currency is None and s.period_start is None
    assert project(s, CostPolicy(), NOW).state == "unqualified"


# Retention keeps retrieval age and prior cycles, suppressing misleading green/over-budget states.
def test_freshness_rollover_retained_failure_and_order():
    c = example()
    s = normalize(c.target, c.response, NOW)
    assert project(s, CostPolicy(), NOW + timedelta(days=2)).state == "stale"
    assert project(s, CostPolicy(), datetime(2026, 12, 1, tzinfo=UTC)).state == "prior_cycle"
    failed = project(s, CostPolicy(), NOW, failure="COST_RETRIES_EXHAUSTED", pending=True)
    assert (
        failed.state == "unavailable" and failed.actual == s.actual and failed.retrieved_at == NOW
    )
    assert failed.pending and not failed.forecast_over_budget
    unknown = s.model_copy(update={"computed_at": None})
    assert snapshot_order(s) > snapshot_order(unknown)
    assert snapshot_order(
        s.model_copy(update={"retrieved_at": NOW + timedelta(seconds=1)})
    ) > snapshot_order(s)


# Source keys are exact registry/binding/profile identity, independent of owner labels and cycle.
def test_current_source_context_and_target_agree():
    c = example()
    assert canonical_hash(source_context(c.row, c.policy, CostPolicy())) == target_source(c.target)
    assert source_context(dict(c.row, status="terminated"), c.policy, CostPolicy()) is None
    assert source_context(dict(c.row, configuration_observation={}), c.policy, CostPolicy()) is None
    assert source_context(c.row, None, CostPolicy()) is None
    with pytest.raises(ValidationError):
        c.target.model_validate({**c.target.model_dump(), "period_end": c.target.period_start})
    with pytest.raises(ValidationError):
        CostPolicy(retry_delays_seconds=(True,))
    assert CostPolicy(retry_delays_seconds=[1, 2]).retry_delays_seconds == (1, 2)


# The simulator reads retained observed budget data and cannot select a parent or another budget.
def test_budget_facade_reads_observed_budget_and_rejects_gaps():
    c = example()
    facade = SimulatedBudgetFacade(c.policy)
    result = facade.read_managed_budget(c.target, c.row["configuration_observation"]["budget"], NOW)
    assert result.amount == "200.0000" and result.actual_spend == "0.0000"
    with pytest.raises(BudgetReadUnavailable):
        facade.read_managed_budget(c.target, None, NOW)
    with pytest.raises(BudgetReadUnavailable):
        facade.read_managed_budget(
            c.target.model_copy(update={"source_access_binding_id": uuid4()}),
            c.row["configuration_observation"]["budget"],
            NOW,
        )
