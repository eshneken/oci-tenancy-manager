"""Exact Decimal and calendar qualification without guessing currency or monthly source periods."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from otm.financial.contracts import CostSnapshot, CostView
from otm.operations.contracts import canonical_hash


# Calendar boundaries are UTC only for the explicitly qualified local simulator profile.
def month_bounds(at):
    start = datetime(at.year, at.month, 1, tzinfo=UTC)
    end = datetime(at.year + (at.month == 12), 1 if at.month == 12 else at.month + 1, 1, tzinfo=UTC)
    return start, end


# Preserve one response's facts; mismatched scope is a failed acquisition, not observed
# zero/missing.
def normalize(target, result, now):
    child = target.configuration.tenancy_ocid
    if (
        result.budget_ocid != target.budget_ocid
        or result.compartment_ocid != child
        or result.target_type != "COMPARTMENT"
        or result.targets != (child,)
        or result.captured_at > now
        or result.captured_at < target.period_start
    ):
        raise ValueError("COST_TARGET_CHANGED")
    if result.amount is not None and Decimal(result.amount) < 0:
        raise ValueError("COST_SOURCE_UNQUALIFIED")
    facts = result.cycle_facts
    qualified = (
        facts.reset_period == "MONTHLY"
        and facts.processing_period_type == "MONTH"
        and facts.budget_processing_period_start_offset == 1
        and facts.start_date is None
        and facts.end_date is None
        and result.time_spend_computed is not None
        and result.time_spend_computed <= result.captured_at
    )
    start, end = month_bounds(result.time_spend_computed) if qualified else (None, None)
    return CostSnapshot(
        budget_ocid=result.budget_ocid,
        budget=result.amount,
        actual=result.actual_spend,
        forecast=result.forecasted_spend,
        computed_at=result.time_spend_computed,
        retrieved_at=result.captured_at,
        period_start=start,
        period_end=end,
        currency="USD" if qualified else None,
        minor_units=2 if qualified else None,
        profile_hash=canonical_hash(target.profile.model_dump(mode="json")),
        source_state="qualified" if qualified else "unqualified",
        cycle_facts=facts,
    )


# Unknown computation time cannot displace qualified facts; equal times prefer later retrieval.
def snapshot_order(snapshot):
    return (snapshot.computed_at or datetime.min.replace(tzinfo=UTC), snapshot.retrieved_at)


# Data qualification stays visible and over-budget colors never certify old or incompatible money.
def project(
    snapshot,
    policy,
    now,
    *,
    pending=False,
    failure=None,
    operation_id=None,
    can_refresh=False,
    desired_budget=None,
):
    common = dict(
        pending=pending,
        latest_failure=failure,
        operation_id=operation_id,
        can_refresh=can_refresh,
        desired_budget=desired_budget,
    )
    if snapshot is None:
        return CostView(
            state="unqualified"
            if failure == "COST_SOURCE_UNQUALIFIED"
            else "unavailable"
            if failure
            else "not_collected",
            **common,
        )
    state = "current"
    if snapshot.source_state != "qualified":
        state = "unqualified"
    elif (snapshot.period_start, snapshot.period_end) != month_bounds(now):
        state = "prior_cycle"
    elif now - snapshot.retrieved_at > timedelta(
        seconds=policy.retrieval_max_age_seconds
    ) or now - snapshot.computed_at > timedelta(seconds=policy.source_max_age_seconds):
        state = "stale"
    elif failure:
        state = "unqualified" if failure == "COST_SOURCE_UNQUALIFIED" else "unavailable"
    elif any(value is None for value in (snapshot.budget, snapshot.actual, snapshot.forecast)):
        state = "partial"
    usable = state in {"current", "partial"}
    return CostView(
        state=state,
        budget=snapshot.budget,
        actual=snapshot.actual,
        forecast=snapshot.forecast,
        currency=snapshot.currency,
        minor_units=snapshot.minor_units,
        retrieved_at=snapshot.retrieved_at,
        computed_at=snapshot.computed_at,
        cycle_facts=snapshot.cycle_facts,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        actual_over_budget=bool(
            usable
            and snapshot.budget is not None
            and snapshot.actual is not None
            and Decimal(snapshot.actual) > Decimal(snapshot.budget)
        ),
        forecast_over_budget=bool(
            usable
            and snapshot.budget is not None
            and snapshot.forecast is not None
            and Decimal(snapshot.forecast) > Decimal(snapshot.budget)
        ),
        **common,
    )
