"""Read-only budget facade and explicitly synthetic USD/monthly simulator; no live OCI fallback."""

import json
from decimal import Decimal
from typing import Protocol

from otm.configuration.observations import decode_observation
from otm.financial.contracts import BudgetCycleFacts, BudgetReadResult
from otm.providers.configuration import SimulatedConfigurationFacade


# A qualified adapter owns SDK timeout/credential resolution and returns one bounded response.
class BudgetFacade(Protocol):
    # Read only the exact retained budget through the captured child/source context.
    def read_managed_budget(self, target, stored, at) -> BudgetReadResult: ...


# Failure codes are closed at the worker boundary; raw provider strings never become audit/UI text.
class BudgetReadUnavailable(ValueError):
    pass


# Normal local usage has zero synthetic spend; tests inject typed responses without a simulator UI.
class SimulatedBudgetFacade:
    # The same trusted parent authority used for other simulation operations limits child targets.
    def __init__(self, policy):
        self.policy = policy

    # Read retained observed budget content rather than copying the desired baseline or override.
    def read_managed_budget(self, target, stored, at):
        SimulatedConfigurationFacade(self.policy).require_target(target.configuration)
        if target.source_access_binding_id != self.policy.access_binding_id or not stored:
            raise BudgetReadUnavailable("COST_READ_UNAVAILABLE")
        observation = decode_observation(stored)
        if (
            observation.state != "present"
            or not observation.complete
            or observation.binding.object_ocid != target.budget_ocid
            or observation.observed is None
            or observation.observed.object_ocid != target.budget_ocid
        ):
            raise BudgetReadUnavailable("COST_READ_UNAVAILABLE")
        value = json.loads(observation.observed.payload)
        if value.get("currency") != "USD" or value.get("period") != "MONTHLY":
            raise ValueError("COST_SOURCE_UNQUALIFIED")
        amount = Decimal(value["monthly_amount"])
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -4:
            raise ValueError("COST_SOURCE_UNQUALIFIED")
        child = target.configuration.tenancy_ocid
        return BudgetReadResult(
            budget_ocid=target.budget_ocid,
            compartment_ocid=child,
            target_type="COMPARTMENT",
            targets=(child,),
            cycle_facts=BudgetCycleFacts(
                reset_period="MONTHLY",
                processing_period_type="MONTH",
                budget_processing_period_start_offset=1,
            ),
            amount=f"{amount:.4f}",
            actual_spend="0.0000",
            forecasted_spend="0.0000",
            time_spend_computed=at,
            captured_at=at,
        )
