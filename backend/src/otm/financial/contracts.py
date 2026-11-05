"""Closed current-month financial inputs, exact provider facts and safe stored-data projections."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from otm.configuration.drift_contracts import CheckTarget
from otm.configuration.rollout_contracts import ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Text, UtcInstant
from otm.providers.inspection_contracts import TenancyOcid

Money = Annotated[str, Field(pattern=r"^-?(0|[1-9][0-9]{0,15})\.[0-9]{4}$")]
CostCode = Literal[
    "COST_READ_COMPLETE",
    "COST_READ_UNAVAILABLE",
    "COST_SOURCE_UNQUALIFIED",
    "COST_TARGET_CHANGED",
    "COST_AUTHORIZATION_CHANGED",
    "COST_CONTEXT_UNAVAILABLE",
    "COST_READ_SUPERSEDED",
    "COST_RETRIES_EXHAUSTED",
]


# Only the explicit simulator profile qualifies currency/cycle locally; it certifies no live OCI
# SLA.
class CostPolicy(Contract):
    # Trusted profile identity; live billing profiles need their own provider qualification.
    profile: Literal["simulated-usd-utc-1"] = "simulated-usd-utc-1"
    # Maximum retrieval age in seconds, 1–604800; age never refreshes merely by viewing a page.
    retrieval_max_age_seconds: Annotated[int, Field(ge=1, le=604800)] = 86400
    # Maximum provider calculation age, 1–604800 seconds; independent from retrieval time.
    source_max_age_seconds: Annotated[int, Field(ge=1, le=604800)] = 86400
    # Read retry delays: 0–2 entries, each 1–3600 seconds; no sleeping worker or automatic writes.
    retry_delays_seconds: Annotated[
        tuple[Annotated[int, Field(ge=1, le=3600)], ...], Field(min_length=0, max_length=2)
    ] = (30, 120)

    # TOML arrays are lists; freeze them before strict bounds/type validation.
    @field_validator("retry_delays_seconds", mode="before")
    @classmethod
    def freeze_retry_delays(cls, value):
        return tuple(value) if isinstance(value, list) else value


# Request inputs contain no endpoints, credentials, object IDs, currency or provider options.
class CostRefreshRequest(Contract):
    client_request_key: UUID
    tenancy_id: UUID | None = None


# Joining compatible existing work is explicit, while replay returns the original command receipt.
class CostRefreshReceipt(Contract):
    operation_ids: tuple[UUID, ...]
    accepted_count: int
    joined_count: int
    skipped_count: int
    accepted_at: UtcInstant
    provider_mode: Literal["simulated"] = "simulated"


# Context is captured from the registered child and retained binding, never a browser OCID.
class CostTarget(Contract):
    configuration: CheckTarget
    budget_ocid: Text
    source_access_binding_id: UUID
    profile: CostPolicy
    period_start: UtcInstant
    period_end: UtcInstant

    # Exact monthly target domains must be positive, ordered and retain the budget identity.
    @model_validator(mode="after")
    def coherent_scope(self):
        if (
            self.period_start >= self.period_end
            or self.configuration.bindings.get("budget") != self.budget_ocid
        ):
            raise ValueError("INVALID_FINANCIAL_SCOPE")
        return self


# All targets share one trusted deployment scope; queue jobs carry only the operation reference.
class CostIntent(Contract):
    contract_version: Literal["cost-collection-1"] = "cost-collection-1"
    kind: Literal["cost_collection"] = "cost_collection"
    workspace_id: Text
    administrator_id: UUID
    authorization_revision: UUID
    targets: Annotated[tuple[CostTarget, ...], Field(min_length=1, max_length=500)]
    target: ConfigurationOperationTarget

    # Duplicate child targets cannot become duplicate reads or multiply shared-tenancy costs.
    @model_validator(mode="after")
    def distinct_targets(self):
        if len({t.configuration.tenancy_id for t in self.targets}) != len(self.targets):
            raise ValueError("DUPLICATE_COST_TARGET")
        return self


# These are actual public Budget response fields, not invented provider currency/month boundaries.
class BudgetCycleFacts(Contract):
    reset_period: Text
    processing_period_type: Text
    budget_processing_period_start_offset: int | None
    start_date: UtcInstant | None = None
    end_date: UtcInstant | None = None


# One facade response echoes exact scope and supplies all monetary facts together.
class BudgetReadResult(Contract):
    budget_ocid: Text
    compartment_ocid: TenancyOcid
    target_type: Text
    targets: tuple[TenancyOcid, ...]
    cycle_facts: BudgetCycleFacts
    amount: Money | None
    actual_spend: Money | None
    forecasted_spend: Money | None
    time_spend_computed: UtcInstant | None
    captured_at: UtcInstant


# Retain a coherent normalized snapshot even when optional fields or source qualification are
# absent.
class CostSnapshot(Contract):
    budget_ocid: Text
    budget: Money | None
    actual: Money | None
    forecast: Money | None
    computed_at: UtcInstant | None
    retrieved_at: UtcInstant
    period_start: UtcInstant | None
    period_end: UtcInstant | None
    currency: Literal["USD"] | None
    minor_units: Literal[2] | None
    profile_hash: Digest
    source_state: Literal["qualified", "unqualified"]
    cycle_facts: BudgetCycleFacts


# Bounded outcome evidence is safe for Operations and audit; it never contains raw SDK exceptions.
class CostEvidence(Contract):
    contract_version: Literal["cost-collection-1"] = "cost-collection-1"
    collection_id: UUID
    tenancy_id: UUID
    state: Literal["reading", "retry", "succeeded", "failed", "superseded"]
    attempts: Annotated[int, Field(ge=1, le=3)]
    safe_code: CostCode


# Dashboard fields are stored-data projections; missing values remain null, never fabricated zeroes.
class CostView(Contract):
    computed_at: UtcInstant | None = None
    cycle_facts: BudgetCycleFacts | None = None
    state: Literal[
        "not_collected", "current", "partial", "stale", "prior_cycle", "unavailable", "unqualified"
    ] = "not_collected"
    budget: Money | None = None
    actual: Money | None = None
    forecast: Money | None = None
    currency: Literal["USD"] | None = None
    minor_units: Literal[2] | None = None
    retrieved_at: UtcInstant | None = None
    period_start: UtcInstant | None = None
    period_end: UtcInstant | None = None
    pending: bool = False
    latest_failure: CostCode | None = None
    can_refresh: bool = False
    operation_id: UUID | None = None
    desired_budget: Money | None = None
    actual_over_budget: bool = False
    forecast_over_budget: bool = False
