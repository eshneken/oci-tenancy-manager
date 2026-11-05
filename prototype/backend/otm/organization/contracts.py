"""Immutable source, policy and revision contracts shared by reconciliation and storage."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


# Normalize an email identity without removing aliases; reject malformed addresses.
def email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 320 or value.count("@") != 1 or any(c.isspace() for c in value):
        raise ValueError("invalid email identity")
    local, domain = value.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("invalid email identity")
    return value


# Immutable, extra-field-rejecting base for canonical inputs and persisted state.
class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Distinguish a declared census from partial or unconfirmed source coverage.
class Completeness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNCONFIRMED = "unconfirmed"


# One normalized source employee row; manager references need not have profiles.
class Record(Contract):
    source_record_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    email: str
    manager_email: str | None
    manager_name: str | None = None
    reported_top_manager_email: str | None = None
    territory: str | None = None

    _emails = field_validator("email", "manager_email", "reported_top_manager_email")(
        lambda value: email(value) if value is not None else None
    )

    # Trim required identity/name fields and reject whitespace-only values.
    @field_validator("source_record_id", "full_name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank identity/name field")
        return value.strip()


# Source-supplied snapshot identity, capture time and completeness declaration.
class Envelope(Contract):
    source_id: str = Field(min_length=1)
    population_id: str = Field(min_length=1)
    external_snapshot_id: str = Field(min_length=1)
    captured_at: AwareDatetime | None
    declared_completeness: Completeness

    # Convert a validated aware capture timestamp to UTC, preserving unknown time.
    @field_validator("captured_at")
    @classmethod
    def normalize_capture(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value else None


# Canonical source data. Trusted policy/configuration is never supplied here.
class Intake(Contract):
    envelope: Envelope
    records: tuple[Record, ...]


# Trusted population policy that controls metadata and absence eligibility.
class SourcePolicy(Contract):
    # Exact source namespace expected in each intake envelope; mismatch blocks publication.
    source_id: str
    # Exact population scope expected in each envelope; prevents reconciling another census.
    population_id: str
    # Normalized email boundary (at most 320 characters); reporting paths stop at this root.
    root_email: str
    # Permit this source to update effective employee metadata; false blocks publication.
    allow_metadata: bool
    # Permit absence inference only with confirmed, complete, fresh and fully covered census.
    authoritative: bool
    # Administrator-confirmed census contract; required alongside authority for absence checks.
    census_contract_confirmed: bool
    # Positive source-age limit in seconds; stale trusted reapply may review, never infer absence.
    max_age_seconds: int = Field(gt=0)
    # Development-only undated metadata; never qualifies a census.
    allow_undated_development_metadata: bool = False
    # Require a root employee row by default; false exempts only that boundary from coverage.
    required_root_profile: bool = True
    # Nonempty alert-recipient email tuple, normalized/deduplicated; confers no app access.
    administrator_recipients: tuple[str, ...] = Field(min_length=1)

    _root = field_validator("root_email")(email)

    # Normalize and deduplicate configured administrator alert recipients.
    @field_validator("administrator_recipients")
    @classmethod
    def normalize_recipients(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({email(value) for value in values}))

    # Prevent undated development inputs from claiming authoritative census status.
    @model_validator(mode="after")
    def development_not_authoritative(self) -> SourcePolicy:
        if self.allow_undated_development_metadata and self.authoritative:
            raise ValueError("undated development mode cannot be authoritative")
        return self


# Explicitly configured reporting relationship with auditable provenance.
class SupplementalEdge(Contract):
    employee_email: str
    manager_email: str
    provenance: str = Field(min_length=1)

    _emails = field_validator("employee_email", "manager_email")(email)


# Administrator-defined business branch, accountable leader and nominated designees.
class Lob(Contract):
    id: str
    label: str
    leader_email: str
    designee_emails: tuple[str, ...] = ()

    _leader = field_validator("leader_email")(email)

    # Normalize and deduplicate designee identities without deriving them from the feed.
    @field_validator("designee_emails")
    @classmethod
    def normalize_designees(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({email(value) for value in values}))


# Explicit admin correction preserved across feeds, with provenance and supported fields.
class PersonOverride(Contract):
    email: str
    values: dict[Literal["full_name", "manager_email"], str]
    reason: str = Field(min_length=1)
    actor: str = Field(min_length=1)

    _email = field_validator("email")(email)

    # Require a real correction and normalize names/manager identities.
    @field_validator("values")
    @classmethod
    def normalize_values(cls, values: dict[str, str]) -> dict[str, str]:
        if not values or any(not value.strip() for value in values.values()):
            raise ValueError("override values cannot be empty")
        return {
            key: email(value) if key == "manager_email" else value.strip()
            for key, value in values.items()
        }


# Audited, frozen closure/ignore rule; its basis scopes conditional episode resolution.
class ReviewDecision(Contract):
    kind: str
    target: str
    disposition: Literal["resolved", "ignored"]
    # Simulation outcomes live in the same frozen decision/audit transaction as review closure.
    operation: str | None = None
    simulation: Literal["succeeded"] | None = None
    person_id: UUID | None = None
    basis: str | None = None
    recorded_at: AwareDatetime
    actor: str
    reason: str


# Explicit old-to-new email alias retaining the absent person's stable UUID.
class IdentityMerge(Contract):
    old_email: str
    new_email: str
    person_id: UUID
    retired_person_id: UUID
    actor: str
    reason: str

    _emails = field_validator("old_email", "new_email")(email)


# Immutable trusted source policy and accountability configuration revision.
class Configuration(Contract):
    # Immutable configuration-revision UUID; changes publish a new trusted configuration identity.
    id: UUID
    # Trusted source/population, coverage, freshness and alert policy for this revision.
    policy: SourcePolicy
    # Optional business branches with unique IDs/leaders and explicit accountability designees.
    lobs: tuple[Lob, ...] = ()
    # Explicit manager relationships with provenance; at most one edge per employee key.
    supplemental_edges: tuple[SupplementalEdge, ...] = ()
    # Persistent name/manager corrections with actor/reason; at most one override per email.
    overrides: tuple[PersonOverride, ...] = ()
    # Frozen review closures/ignores and local simulation acknowledgments; no OCI execution.
    review_decisions: tuple[ReviewDecision, ...] = ()
    # Normalized emails excluded from the effective org, preserving source and historic identity.
    excluded_emails: tuple[str, ...] = ()
    # One-way email aliases retaining the absent person UUID; duplicate origins/cycles fail.
    identity_merges: tuple[IdentityMerge, ...] = ()
    # Directory eligibility is separate from the source/reporting graph and immutable history.
    managed_exclusions: tuple[UUID, ...] = ()
    # Stable person UUIDs still requiring onboarding review; empty does not imply OCI readiness.
    pending_onboarding_person_ids: tuple[UUID, ...] = ()
    # Use persisted registry rows after initialization; false reconstructs legacy simulations.
    registry_initialized: bool = False
    # People retained outside the org with associations; require explicit return before onboarding.
    outside_person_ids: tuple[UUID, ...] = ()

    # Keep durable organization removals normalized without deleting historical identity.
    @field_validator("excluded_emails")
    @classmethod
    def normalize_exclusions(cls, values):
        return tuple(sorted({email(value) for value in values}))

    # Reject ambiguous LOB/edge keys and edges above the configured organization root.
    @model_validator(mode="after")
    def unique_keys(self) -> Configuration:
        for values in (
            [lob.id for lob in self.lobs],
            [lob.leader_email for lob in self.lobs],
            [edge.employee_email for edge in self.supplemental_edges],
            [override.email for override in self.overrides],
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate configuration key")
        if any(
            override.email == self.policy.root_email and "manager_email" in override.values
            for override in self.overrides
        ):
            raise ValueError("root cannot have a manager override")
        if any(edge.employee_email == self.policy.root_email for edge in self.supplemental_edges):
            raise ValueError("supplemental edges cannot extend the configured root boundary")
        if self.policy.root_email in self.excluded_emails:
            raise ValueError("root cannot be excluded")
        aliases = {m.old_email: m.new_email for m in self.identity_merges}
        if len(aliases) != len(self.identity_merges):
            raise ValueError("duplicate identity alias")
        for origin in aliases:
            seen = set()
            cursor = origin
            while cursor in aliases:
                if cursor in seen:
                    raise ValueError("identity alias cycle")
                seen.add(cursor)
                cursor = aliases[cursor]
        return self


# Safe reconciliation finding; fatal findings prevent candidate publication.
class Diagnostic(Contract):
    code: str
    affected_email: str | None = None
    fatal: bool = False


# Effective person attributes and evidence within one immutable organization revision.
class PersonState(Contract):
    id: UUID
    email: str
    full_name: str | None
    source_record_id: str | None = None
    source_values: dict[str, str | None] = Field(default_factory=dict)
    profile: Literal["employee", "reference", "configured"]
    manager_email: str | None = None
    manager_provenance: str | None = None
    known_manager: bool = False
    last_row_observed_at: AwareDatetime | None = None
    last_reference_observed_at: AwareDatetime | None = None
    last_source_capture_at: AwareDatetime | None = None
    last_qualified_census_at: AwareDatetime | None = None
    reported_top_manager_email: str | None = None
    territory: str | None = None
    ancestry: Literal["root", "resolved", "incomplete"] = "incomplete"
    # Ordered from this person's direct manager upwards; excludes the person.
    manager_path: tuple[str, ...] = ()
    lob_id: str | None = None
    accountable_leader_email: str | None = None
    designee_emails: tuple[str, ...] = ()
    absence_review: bool = False
    # Retain a settled absence's episode key until positive evidence returns, preventing
    # repeated missing feeds from opening a new review for the same continuous absence.
    absence_review_since: AwareDatetime | None = None


# Published organization snapshot with source/configuration provenance and stable
# identities.
class Revision(Contract):
    id: UUID
    predecessor_id: UUID | None
    configuration_id: UUID
    snapshot_id: UUID
    population_id: str
    published_at: AwareDatetime
    source_captured_at: AwareDatetime | None
    declared_completeness: Completeness
    assessed_coverage: Completeness
    absence_eligible: bool
    people: tuple[PersonState, ...]


# Staged effective graph and diagnostics bound to the head/configuration read during
# preparation.
class Candidate(Contract):
    envelope: Envelope
    expected_head_id: UUID | None
    expected_configuration_id: UUID
    observed_at: AwareDatetime
    people: tuple[PersonState, ...]
    diagnostics: tuple[Diagnostic, ...]
    assessed_coverage: Completeness
    absence_eligible: bool
    issues: tuple[tuple[str, str], ...]
    employee_row_emails: tuple[str, ...]

    # Return whether any diagnostic makes this candidate unsafe to publish.
    @property
    def rejected(self) -> bool:
        return any(d.fatal for d in self.diagnostics)


# Reject naive clocks so freshness checks and evidence times have an explicit timezone.
def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("UTC-aware clock required")
