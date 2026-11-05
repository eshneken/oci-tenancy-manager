"""Typed authored overrides, immutable local revisions and staged whole-batch conflict reviews."""

import json
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from otm.configuration.contracts import BaselineContent, BaselineVersion, Statement
from otm.contracts import Contract, Text, UtcInstant

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Choice = Literal["use_new_baseline", "keep_override"]


# Null inherits; a present complete list or positive whole amount replaces only that authored
# category.
class OverrideValues(Contract):
    # Null inherits; otherwise replace the entire authored policy list (1–50, up to 2,000
    # chars each).
    policy_override_statements: (
        Annotated[tuple[Statement, ...], Field(min_length=1, max_length=50)] | None
    ) = None
    # Null inherits; otherwise replace the entire quota list without appending baseline statements.
    quota_override_statements: (
        Annotated[tuple[Statement, ...], Field(min_length=1, max_length=50)] | None
    ) = None
    # Null inherits; positive whole units only, NUMERIC(20,4), at most 16 whole digits; no
    # scope change.
    monthly_budget_override_amount: (
        Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=4)] | None
    ) = None

    # Preserve statement boundaries without allowing blank lists, credential material or NULs.
    @field_validator("policy_override_statements", "quota_override_statements")
    @classmethod
    def statements(cls, value):
        if value is not None:
            BaselineContent.complete_statements(value)
        return value

    # Money is exact, positive and whole at this command boundary, never binary floating-point cost.
    @field_validator("monthly_budget_override_amount")
    @classmethod
    def whole_amount(cls, value):
        if value is not None:
            if value != value.to_integral_value():
                raise ValueError("WHOLE_BUDGET_REQUIRED")
            return value.quantize(Decimal("0.0001"))
        return value


# One immutable accepted revision keeps baseline and override heads from moving independently.
class TenancyConfiguration(OverrideValues):
    id: UUID
    tenancy_id: UUID
    baseline_version_id: UUID
    revision_number: Annotated[int, Field(ge=1)]
    previous_id: UUID | None
    operation_id: UUID
    created_by: Text
    created_at: UtcInstant
    resolution_contract_version: Literal["simulated-config-1"] = "simulated-config-1"
    effective_hash: Digest


# An editor reads the assigned publication; it never silently upgrades to latest while editing.
class OverrideEditor(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    tenancy_revision: int
    baseline: BaselineVersion
    configuration: TenancyConfiguration | None
    values: OverrideValues
    can_edit: bool


# Freeze the editor's assigned publication and registry/configuration generation before previewing.
class OverrideContext(Contract):
    baseline_version_id: UUID
    tenancy_revision: Annotated[int, Field(ge=1)]
    configuration_id: UUID | None


# Previewing authored values is read-only and binds the current child/configuration and exact input.
class OverridePreviewRequest(Contract):
    context: OverrideContext
    tenancy_id: UUID
    values: OverrideValues


# A review is anchored to old/new full lists rather than a reusable acknowledgement boolean.
class OverrideConflict(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    old_baseline: BaselineVersion | None
    overrides: OverrideValues
    policy_review: bool
    quota_review: bool
    policy_choice: Choice | None = None
    quota_choice: Choice | None = None


# Explicit plan creation is a local draft command with a replay-safe request identity.
class CreateConfigurationPlan(Contract):
    client_request_key: UUID
    tenancy_id: UUID | None = None


# Optimistic plan revisions prevent another tab from overwriting a different staged decision.
class SaveConfigurationReview(Contract):
    expected_revision: Annotated[int, Field(ge=1)]
    tenancy_id: UUID
    policy_choice: Choice | None = None
    quota_choice: Choice | None = None


# Accepted evidence identifies who reviewed each exact full-list conflict and when.
class OverrideReviewEvidence(Contract):
    policy_choice: Choice | None = None
    quota_choice: Choice | None = None
    reviewed_by: Text
    reviewed_at: UtcInstant
    plan_id: UUID


# One immutable snapshot and its explicit values resolve only authored local managed-object content.
def effective_content(baseline: BaselineVersion, values: OverrideValues) -> BaselineContent:
    data = baseline.content.model_dump(mode="json")
    for field, destination in (
        ("policy_override_statements", "policy_statements"),
        ("quota_override_statements", "quota_statements"),
        ("monthly_budget_override_amount", "monthly_budget_amount"),
    ):
        value = values.model_dump(mode="json")[field]
        if value is not None:
            data[destination] = value
    return BaselineContent.model_validate_json(json.dumps(data))


# The digest binds exact baseline identity/content, authored override values and resolution version.
def configuration_hash(baseline, values):
    from otm.operations.contracts import canonical_hash

    return canonical_hash(
        {
            "baseline_id": str(baseline.id),
            "baseline_hash": baseline.content_hash,
            "values": values.model_dump(mode="json", include=set(OverrideValues.model_fields)),
            "resolution": "simulated-config-1",
            "effective": effective_content(baseline, values).model_dump(mode="json"),
        }
    )


# One local staged choice is auditable without pretending it changes a live configuration.
class ConfigurationReviewEvidence(Contract):
    contract_version: Literal["configuration-review-1"] = "configuration-review-1"
    plan_id: UUID
    tenancy_id: UUID
    baseline_id: UUID
    proposal_hash: Digest
    policy_choice: Choice | None = None
    quota_choice: Choice | None = None
