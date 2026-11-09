"""Closed baseline/override update previews, immutable targets and simulated readback evidence."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.contracts import BaselineVersion
from otm.configuration.override_contracts import (
    OverrideConflict,
    OverrideContext,
    OverrideReviewEvidence,
    OverrideValues,
    TenancyConfiguration,
)
from otm.contracts import Contract, Text, UtcInstant
from otm.providers.inspection_contracts import TenancyOcid

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Category = Literal["policy", "quota", "budget", "tags"]


# Display-only labels cannot select a provider target or change its scope.
class ConfigurationOperationTarget(Contract):
    tenancy_ocid: TenancyOcid | None
    display_name: Text


# Freeze every registered target and its prior desired/verified state at acceptance.
class ConfigurationTarget(Contract):
    source_configuration_id: UUID | None = None
    source_verified_configuration_id: UUID | None = None
    configuration: TenancyConfiguration | None = None
    overrides: OverrideValues = Field(default_factory=OverrideValues)
    review: OverrideReviewEvidence | None = None
    # Server-frozen repair scope, exact bindings, separate context/value fences and source check.
    repair_categories: tuple[Category, ...] = ()
    repair_bindings: dict[Category, str] | None = None
    repair_context_hash: Digest | None = None
    repair_observation_hash: Digest | None = None
    repair_check_id: UUID | None = None
    tenancy_id: UUID
    name: Text
    tenancy_ocid: TenancyOcid
    parent_tenancy_ocid: TenancyOcid
    organization_id: Text
    revision: Annotated[int, Field(ge=1)]
    source_baseline_id: UUID | None
    source_verified_id: UUID | None


# One accepted operation owns the complete batch; later publication never retargets it.
class ConfigurationIntent(Contract):
    change_kind: Literal["baseline_update", "override_change", "repair"] = "baseline_update"
    contract_version: Literal["configuration-update-1"] = "configuration-update-1"
    kind: Literal["configuration_update"] = "configuration_update"
    workspace_id: Text
    policy_revision: UUID
    organization_id: Text
    parent_tenancy_ocid: TenancyOcid
    administrator_id: UUID
    authorization_revision: UUID
    baseline: BaselineVersion
    targets: Annotated[tuple[ConfigurationTarget, ...], Field(min_length=1, max_length=500)]
    target: ConfigurationOperationTarget

    # Duplicate or foreign target scopes cannot be hidden within an otherwise valid batch.
    @model_validator(mode="after")
    def scoped_targets(self):
        if self.baseline.publication_mode != "simulated" or len(
            {t.tenancy_id for t in self.targets}
        ) != len(self.targets):
            raise ValueError("INVALID_CONFIGURATION_TARGETS")
        if any(
            t.configuration
            and (
                t.configuration.tenancy_id != t.tenancy_id
                or t.configuration.baseline_version_id != self.baseline.id
            )
            for t in self.targets
        ):
            raise ValueError("INVALID_CONFIGURATION_REVISION_SCOPE")
        if any(
            t.parent_tenancy_ocid != self.parent_tenancy_ocid
            or t.organization_id != self.organization_id
            for t in self.targets
        ):
            raise ValueError("INVALID_CONFIGURATION_SCOPE")
        repair = self.change_kind == "repair"
        if repair and len(self.targets) != 1:
            raise ValueError("SINGLE_REPAIR_TARGET_REQUIRED")
        for target in self.targets:
            if bool(target.repair_categories) != repair or bool(target.repair_bindings) != repair:
                raise ValueError("INVALID_REPAIR_SCOPE")
            if not repair and any(
                (target.repair_context_hash, target.repair_observation_hash, target.repair_check_id)
            ):
                raise ValueError("INVALID_REPAIR_SCOPE")
            if repair and (
                not target.repair_context_hash
                or not target.repair_observation_hash
                or not target.repair_check_id
                or len(set(target.repair_categories)) != len(target.repair_categories)
                or set(target.repair_bindings) != {"policy", "quota", "budget", "tags"}
                or target.source_baseline_id != self.baseline.id
                or target.source_configuration_id
                != (target.configuration.id if target.configuration else None)
            ):
                raise ValueError("INVALID_REPAIR_SCOPE")
        return self


# Preview errors identify exact blockers without leaking provider error messages.
class ConfigurationBlocker(Contract):
    tenancy_id: UUID
    name: Text
    code: Literal[
        "TENANCY_BUSY",
        "REGISTERED_CHILD_REQUIRED",
        "PROVIDER_UNAVAILABLE",
        "OVERRIDE_REVIEW_REQUIRED",
        "OVERRIDE_CONTEXT_UNAVAILABLE",
    ]
    operation_id: UUID | None = None


# The UI needs one ready count and complete blocker list, not a second tenancy inventory.
class ConfigurationPreview(Contract):
    # Repair confirmation renders these fresh server observations, never stale page values.
    repair_expected: dict[Category, Annotated[str, Field(max_length=700000)]] = Field(
        default_factory=dict
    )
    repair_observed: dict[Category, Annotated[str, Field(max_length=700000)] | None] = Field(
        default_factory=dict
    )
    conflicts: tuple[OverrideConflict, ...] = ()
    baseline: BaselineVersion | None
    tenancy_id: UUID | None
    ready_count: int
    pending_count: int
    blockers: tuple[ConfigurationBlocker, ...]
    preview_hash: Digest


# Only the reviewed hash/scope and request identity cross the browser admission boundary.
class ConfigurationUpdate(Contract):
    repair_categories: tuple[Category, ...] = ()
    plan_id: UUID | None = None
    override_context: OverrideContext | None = None
    override_mode: bool = False
    overrides: OverrideValues | None = None
    client_request_key: UUID
    tenancy_id: UUID | None = None
    preview_hash: Digest

    # Only a one-child override may carry authored values; plan reviews never bypass this boundary.
    @model_validator(mode="after")
    def mode_scope(self):
        if self.repair_categories and (
            self.tenancy_id is None
            or self.plan_id is not None
            or self.override_mode
            or len(self.repair_categories) > 4
            or len(set(self.repair_categories)) != len(self.repair_categories)
        ):
            raise ValueError("INVALID_REPAIR_SCOPE")
        if (
            self.override_mode != (self.overrides is not None)
            or self.override_mode != (self.override_context is not None)
            or (self.override_mode and (self.tenancy_id is None or self.plan_id is not None))
        ):
            raise ValueError("INVALID_OVERRIDE_SCOPE")
        return self


# Reloadable staging is separate from accepted configuration and immutable execution history.
class ConfigurationPlanView(Contract):
    id: UUID
    revision: int
    state: Literal["draft", "accepted", "stale"]
    preview: ConfigurationPreview
    operation_id: UUID | None = None


# Stable safe evidence records each target result and the failing category, not raw exceptions.
class ConfigurationOutcome(Contract):
    contract_version: Literal["configuration-update-1"] = "configuration-update-1"
    tenancy_id: UUID
    baseline_id: UUID
    configuration_id: UUID | None = None
    safe_code: Literal[
        "CONFIGURATION_VERIFIED",
        "CONFIGURATION_UNVERIFIED",
        "AUTHORIZATION_CHANGED",
        "TARGET_CHANGED",
        "LIFECYCLE_UNAVAILABLE",
    ]
    category: Category | None = None
    verified_at: UtcInstant | None = None


# Simulator state is explicit and persisted; readback reads stored objects rather than desired
# input.
class ManagedConfigurationObject(Contract):
    category: Category
    object_ocid: Annotated[str, Field(pattern=r"^ocid1\.[a-z]+\.oc1\.\.otmsim[a-z0-9]+$")]
    payload: Annotated[str, Field(min_length=2, max_length=700000)]
    payload_hash: Digest

    # Corrupt fake-provider state must never count as successful independent readback.
    @model_validator(mode="after")
    def valid_payload(self):
        import json

        from otm.operations.contracts import canonical_hash

        value = json.loads(self.payload)
        if not isinstance(value, dict) or canonical_hash(value) != self.payload_hash:
            raise ValueError("INVALID_MANAGED_OBJECT")
        return self


# Per-target progress belongs to configuration/tenancy screens, while Operations keeps history.
class ConfigurationTargetProgress(Contract):
    tenancy_id: UUID
    name: Text
    state: Literal["pending", "verified", "needs_attention"]
    safe_code: str | None = None
    verified_at: UtcInstant | None = None


# Read-only progress and an explicit failed-target retry reuse one durable operation identity.
class ConfigurationProgress(Contract):
    change_kind: Literal["baseline_update", "override_change", "repair"] = "baseline_update"
    operation_id: UUID
    state: str
    baseline: BaselineVersion
    targets: tuple[ConfigurationTargetProgress, ...]
    can_retry: bool


# Retrying an unchanged accepted batch is itself an auditable administrator action.
class ConfigurationRetryEvidence(Contract):
    contract_version: Literal["configuration-update-1"] = "configuration-update-1"
    baseline_id: UUID
    configuration_id: UUID | None = None
    safe_code: Literal["CONFIGURATION_RETRY_ACCEPTED"] = "CONFIGURATION_RETRY_ACCEPTED"
