"""Scoped read-check commands, immutable evidence and current configuration issue projections."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.override_contracts import OverrideValues
from otm.configuration.rollout_contracts import Category, ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Text, UtcInstant
from otm.providers.inspection_contracts import TenancyOcid

CheckState = Literal["matching", "drifted", "unavailable", "superseded"]
ObjectState = Literal["matching", "missing", "different", "unavailable", "conflict"]
ReadCode = Literal[
    "MATCHING",
    "MISSING",
    "DIFFERENT",
    "READ_UNAVAILABLE",
    "BINDING_CONFLICT",
    "UNBOUND_CONFIGURATION",
    "ASSIGNMENT_CHANGED",
    "AUTHORIZATION_CHANGED",
    "TENANCY_BUSY",
    "PROVIDER_UNAVAILABLE",
    "CHECK_STALE",
]


# Read checks accept only bounded scope and replay identity, never desired statements or fake state.
class ConfigurationCheckRequest(Contract):
    client_request_key: UUID
    tenancy_id: UUID | None = None


# Exact registered provenance is frozen separately from mutable simulated observations.
class CheckTarget(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    tenancy_ocid: TenancyOcid
    parent_tenancy_ocid: TenancyOcid
    organization_id: Text
    revision: Annotated[int, Field(ge=1)]
    policy_revision: UUID
    baseline_id: UUID | None
    baseline_hash: Digest | None
    configuration_id: UUID | None
    effective_hash: Digest | None
    overrides: OverrideValues
    bindings: dict[Category, str]
    bindings_hash: Digest
    qualified: bool

    # A positive inventory qualification must include all four exact registered identities.
    @model_validator(mode="after")
    def inventory_coverage(self):
        if self.qualified and (
            set(self.bindings) != {"policy", "quota", "budget", "tags"}
            or self.baseline_id is None
            or self.baseline_hash is None
            or self.effective_hash is None
        ):
            raise ValueError("QUALIFIED_INVENTORY_REQUIRED")
        return self


# Reference-only jobs carry one immutable set of assigned contexts instead of selecting latest
# later.
class ConfigurationCheckIntent(Contract):
    contract_version: Literal["configuration-check-1"] = "configuration-check-1"
    kind: Literal["configuration_check"] = "configuration_check"
    workspace_id: Text
    policy_revision: UUID
    organization_id: Text
    parent_tenancy_ocid: TenancyOcid
    administrator_id: UUID
    authorization_revision: UUID
    targets: Annotated[tuple[CheckTarget, ...], Field(min_length=1, max_length=500)]
    target: ConfigurationOperationTarget

    # Duplicate or cross-organization targets cannot hide inside a queued read request.
    @model_validator(mode="after")
    def scoped_targets(self):
        if len({t.tenancy_id for t in self.targets}) != len(self.targets) or any(
            t.parent_tenancy_ocid != self.parent_tenancy_ocid
            or t.organization_id != self.organization_id
            for t in self.targets
        ):
            raise ValueError("INVALID_CHECK_SCOPE")
        return self


# Observed payloads are canonical managed data only; fixed codes replace raw provider exceptions.
class ConfigurationObjectCheck(Contract):
    category: Category
    state: ObjectState
    safe_code: ReadCode
    complete: bool
    binding_ocid: str | None
    expected: Annotated[str, Field(max_length=700000)] | None
    observed: Annotated[str, Field(max_length=700000)] | None

    # Covered absence and values must be explicit; failed/conflicting reads never prove absence.
    @model_validator(mode="after")
    def evidence_coverage(self):
        if self.state in {"matching", "missing", "different"} and (
            not self.complete
            or not self.binding_ocid
            or self.expected is None
            or (self.state == "missing") != (self.observed is None)
        ):
            raise ValueError("OBSERVATION_EVIDENCE_REQUIRED")
        if self.state in {"unavailable", "conflict"} and (
            self.complete or self.observed is not None
        ):
            raise ValueError("UNVERIFIED_HAS_NO_OBSERVATION")
        return self


# A sealed child attempt is ordered by database acquisition ordinal, never completion wall time.
class ConfigurationCheckEvidence(Contract):
    contract_version: Literal["configuration-check-1"] = "configuration-check-1"
    check_id: UUID
    tenancy_id: UUID
    state: CheckState
    safe_code: Literal[
        "CONFIGURATION_CHECK_COMPLETE",
        "CONFIGURATION_CHECK_UNAVAILABLE",
        "CONFIGURATION_CHECK_SUPERSEDED",
    ]
    checked_at: UtcInstant
    context_hash: Digest
    results: Annotated[tuple[ConfigurationObjectCheck, ...], Field(min_length=4, max_length=4)]

    # Every category is explicit and a complete result cannot contain unavailable/conflicting reads.
    @model_validator(mode="after")
    def complete_categories(self):
        if {r.category for r in self.results} != {"policy", "quota", "budget", "tags"}:
            raise ValueError("FOUR_CATEGORIES_REQUIRED")
        if self.state in {"matching", "drifted"} and any(not r.complete for r in self.results):
            raise ValueError("COMPLETE_COVERAGE_REQUIRED")
        if self.state == "matching" and any(r.state != "matching" for r in self.results):
            raise ValueError("MATCHING_CANNOT_CONTAIN_DRIFT")
        if self.state == "drifted" and not any(
            r.state in {"missing", "different"} for r in self.results
        ):
            raise ValueError("DRIFT_EVIDENCE_REQUIRED")
        return self


# A visible issue may retain earlier same-context evidence while the latest check is incomplete.
class ConfigurationIssue(Contract):
    category: Category
    state: ObjectState | Literal["not_checked"]
    safe_code: ReadCode | None
    binding_ocid: str | None
    expected: Annotated[str, Field(max_length=700000)] | None
    observed: Annotated[str, Field(max_length=700000)] | None
    evidence_at: UtcInstant | None
    retained: bool = False


# One current tenancy projection powers both directory tabs and the compact inventory indicator.
class ConfigurationCheckSummary(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    baseline_id: UUID | None
    baseline_version_number: int | None
    override_categories: tuple[Category, ...]
    state: CheckState | Literal["not_checked", "checking"]
    checked_at: UtcInstant | None
    # Count confirmed missing/different categories only; unavailable and age are separate.
    issue_count: int
    confirmed_issue_count: int
    stale: bool = False
    can_check: bool = True
    pending_operation_id: UUID | None
    last_operation_id: UUID | None
    categories: tuple[ConfigurationIssue, ...]


# Explicit tab/search/sort/pagination follows the existing management directories.
class ConfigurationDriftQuery(Contract):
    tab: Literal["confirmed", "checks"] = "confirmed"
    query: Annotated[str, Field(max_length=128)] = ""
    state: Literal[
        "all", "matching", "drifted", "unavailable", "not_checked", "checking", "stale"
    ] = "all"
    tenancy_id: UUID | None = None
    sort: Literal["name", "checked_at", "issue_count"] = "name"
    direction: Literal["asc", "desc"] = "asc"
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50] = 10


# Counts refer to tenancies; only authorized complete observations enter the confirmed queue.
class ConfigurationDriftDirectory(Contract):
    items: tuple[ConfigurationCheckSummary, ...]
    total: int
    page: int
    pages: int
    page_size: int
    confirmed_count: int
    unavailable_count: int
    unchecked_count: int
    checking_count: int
    # Age is independent of retained confirmed findings or an in-progress verification.
    stale_count: int = 0
    provider_mode: Literal["simulated"] = "simulated"
