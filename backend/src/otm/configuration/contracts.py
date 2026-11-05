"""Bounded draft authoring values; structural validity does not qualify OCI grammar or currency."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from otm.contracts import Contract, UtcInstant

Statement = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


# One static tag definition/default value, never an expression or provider object identifier.
class TagDefault(Contract):
    # Defined key, 1–100 characters; unique without case within the OTM namespace.
    key: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    # Literal root-default text, 1–1000 characters; never evaluated as code.
    value: Annotated[str, StringConstraints(min_length=1, max_length=1000)]

    # Reject blank or NUL-bearing values before any storage/provider boundary.
    @field_validator("key", "value")
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or "\x00" in value or "-----BEGIN " in value:
            raise ValueError("INVALID_STATIC_TAG")
        return value


# Explicit authored columns mirror the approved baseline recipe without splitting statement rows.
class BaselineContent(Contract):
    # One complete authored statement per entry, including embedded line breaks; 1–50 entries.
    policy_statements: Annotated[tuple[Statement, ...], Field(min_length=1, max_length=50)]
    # Complete quota statements, 1–50 entries; no substitution or numeric-rule parsing.
    quota_statements: Annotated[tuple[Statement, ...], Field(min_length=1, max_length=50)]
    # Exact content/history amount, 20 digits/4 places; commands additionally require whole units.
    monthly_budget_amount: Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=4)]
    # Proposed currency code; local USD checks do not qualify actual OCI billing.
    budget_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    # V1 budgets are monthly and cannot target another period through authoring.
    budget_period: Literal["MONTHLY"] = "MONTHLY"
    # One fixed root OTM namespace; authoring cannot redirect the owning scope.
    tag_namespace: Literal["OTM"] = "OTM"
    # Up to 100 static key/value defaults; tags have no per-tenancy V1 override.
    tag_defaults: Annotated[tuple[TagDefault, ...], Field(max_length=100)] = ()

    # Preserve complete multi-line statement boundaries and reject obvious credential material.
    @field_validator("policy_statements", "quota_statements")
    @classmethod
    def complete_statements(cls, statements):
        if any(not s.strip() or "\x00" in s or "-----BEGIN " in s for s in statements):
            raise ValueError("INVALID_STATEMENT")
        return statements

    # Canonical fixed-scale encoding makes equivalent decimal inputs identical on retries.
    @field_validator("monthly_budget_amount")
    @classmethod
    def fixed_scale(cls, value):
        return value.quantize(Decimal("0.0001"))

    # Namespace keys are unambiguous under the approved case-insensitive authoring uniqueness rule.
    @model_validator(mode="after")
    def unique_tags(self):
        keys = [tag.key.casefold() for tag in self.tag_defaults]
        if len(set(keys)) != len(keys):
            raise ValueError("DUPLICATE_TAG_KEY")
        return self


# An explicit expected draft identity/revision fences concurrent edits; new drafts use both null.
class SaveBaselineDraft(Contract):
    baseline_id: UUID | None = None
    expected_revision: Annotated[int, Field(ge=1)] | None = None
    # Exact latest-published parent when creating a derived draft; null for the initial baseline.
    based_on_id: UUID | None = None
    # New budgets use whole units while archival content retains decimal precision.
    content: BaselineContent = Field(
        description="Monthly budget must be a positive whole currency amount."
    )

    # Reject cents without rounding stored values or changing historical canonical hashes.
    @field_validator("content")
    @classmethod
    def whole_budget(cls, value):
        if value.monthly_budget_amount != value.monthly_budget_amount.to_integral_value():
            raise ValueError("WHOLE_BUDGET_REQUIRED")
        return value

    # Never allow an identifier without its matching optimistic concurrency token.
    @model_validator(mode="after")
    def paired_revision(self):
        if (self.baseline_id is None) != (self.expected_revision is None):
            raise ValueError("BASELINE_REVISION_REQUIRED")
        return self


# A closed authoring read exposes draft provenance and values, not arbitrary database/audit rows.
class BaselineDraft(Contract):
    id: UUID
    version_number: Annotated[int, Field(ge=1)]
    edit_revision: Annotated[int, Field(ge=1)]
    created_by: str
    created_at: UtcInstant
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    content: BaselineContent


# Version metadata extends the retained draft payload without mixing recipe fields with provenance.
class BaselineVersion(BaselineDraft):
    based_on_id: UUID | None = None
    published_by: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    published_by_name: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    published_at: UtcInstant | None = None
    publication_mode: Literal["simulated"] | None = None

    # Never imply qualification from a partially populated publication record.
    @model_validator(mode="after")
    def publication_pair(self):
        values = (
            self.published_by,
            self.published_by_name,
            self.published_at,
            self.publication_mode,
        )
        if any(v is None for v in values) != all(v is None for v in values):
            raise ValueError("INVALID_PUBLICATION_METADATA")
        return self


# Page controls and optional exact-version selection never choose workspace or publishing mode.
class BaselineQuery(Contract):
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50] = 10
    baseline_id: UUID | None = None


# History is paged separately from the sole active draft; latest is independent of the chosen page.
class BaselineDirectory(Contract):
    configured: bool
    draft: BaselineVersion | None = None
    publication_available: bool = False
    latest: BaselineVersion | None = None
    selected: BaselineVersion | None = None
    items: Annotated[tuple[BaselineVersion, ...], Field(max_length=50)] = ()
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 1


# Publication targets only an exact saved draft revision, never a browser-supplied recipe or mode.
class PublishBaseline(Contract):
    baseline_id: UUID
    expected_revision: Annotated[int, Field(ge=1)]


# Immutable publication evidence records what local validation established, including its limits.
class BaselinePublicationEvidence(Contract):
    # Earlier publications did not select a default; retain their original historical meaning.
    default_for_new: bool = False
    qualification_version: Literal["baseline-structure-simulated-1"]
    baseline: BaselineVersion

    # Require an immutable simulated publication and a hash matching its exact authored recipe.
    @model_validator(mode="after")
    def published_snapshot(self):
        from otm.operations.contracts import canonical_hash

        if (
            self.baseline.publication_mode != "simulated"
            or self.baseline.content_hash
            != canonical_hash(self.baseline.content.model_dump(mode="json"))
        ):
            raise ValueError("PUBLISHED_BASELINE_REQUIRED")
        return self


# Immutable before/after evidence makes editable draft changes reconstructible without extra tables.
class BaselineDraftEvidence(Contract):
    based_on_id: UUID | None = None
    baseline_id: UUID
    version_number: Annotated[int, Field(ge=1)]
    edit_revision: Annotated[int, Field(ge=1)]
    before: BaselineContent | None
    after: BaselineContent


# Human-readable per-field changes stay bounded even when statement arrays contain long text.
def describe_draft(evidence):
    from itertools import zip_longest

    changes = []
    for field, label in (("policy_statements", "Policy"), ("quota_statements", "Quota")):
        old = getattr(evidence.before, field) if evidence.before else ()
        for index, (before, after) in enumerate(
            zip_longest(old, getattr(evidence.after, field)), 1
        ):
            if before != after:
                changes.append(
                    f"{label} statement {index}: {before or 'Not set'} → {after or 'Not set'}"
                )
    for field in ("monthly_budget_amount", "budget_currency"):
        before = getattr(evidence.before, field) if evidence.before else None
        after = getattr(evidence.after, field)
        if before != after:
            changes.append(
                f"{field.replace('_', ' ').capitalize()}: {before or 'Not set'} → {after}"
            )
    old_tags = (
        {tag.key: tag.value for tag in evidence.before.tag_defaults} if evidence.before else {}
    )
    new_tags = {tag.key: tag.value for tag in evidence.after.tag_defaults}
    for key in sorted(old_tags.keys() | new_tags.keys()):
        if old_tags.get(key) != new_tags.get(key):
            changes.append(
                f"Tag {key}: {old_tags.get(key, 'Not set')} → {new_tags.get(key, 'Not set')}"
            )
    return tuple(changes)


# Historical read-only evidence from the withdrawn manual-default feature; no new events emitted.
class BaselineSelectionEvidence(Contract):
    previous_baseline_id: UUID | None
    baseline: BaselineVersion

    # Only complete published simulated snapshots can become the local onboarding default.
    @model_validator(mode="after")
    def published_snapshot(self):
        BaselinePublicationEvidence(
            qualification_version="baseline-structure-simulated-1", baseline=self.baseline
        )
        return self
