"""Bounded organization settings expose mappings only, never source-policy authority."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from otm.contracts import Contract
from otm.organization.contracts import email


# Mappings are exact normalized identities, never wildcard recipient or branch rules.
def mapping_email(value):
    normalized = email(value)
    if "*" in normalized or "?" in normalized:
        raise ValueError("EXACT_MAPPING_EMAIL_REQUIRED")
    return normalized


# Existing IDs edit active mappings; null requests a new server-assigned immutable segment ID.
class MappingSegment(Contract):
    # Null creates a server ID; a supplied1–256-character ID must be an active saved segment.
    id: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    # Trimmed1–128-character display name; case-insensitive duplicates are rejected.
    label: Annotated[str, Field(min_length=1, max_length=128)]
    # Exact normalized email, at most320characters; a replacement requires rooted eligibility.
    leader_email: str
    # Zero to50 exact normalized nominee emails; deduplicate and recheck routing eligibility.
    designee_emails: Annotated[tuple[str, ...], Field(max_length=50)] = ()

    _leader = field_validator("leader_email")(mapping_email)

    # Normalize display names so whitespace/case cannot disguise duplicate active labels.
    @field_validator("label")
    @classmethod
    def clean_label(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("SEGMENT_NAME_REQUIRED")
        return value

    # A nominee is an explicit email, deduplicated independently of current role eligibility.
    @field_validator("designee_emails")
    @classmethod
    def clean_designees(cls, values):
        return tuple(sorted({mapping_email(v) for v in values}))


# The only editable settings are the root boundary and complete active mapping set.
class MappingCandidate(Contract):
    # Exact email, at most320characters; post-import replacement requires explicit intent.
    root_email: str
    # Optional trimmed root display name (1–256 characters); null keeps legacy feed-name fallback.
    root_name: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    # Complete active set of1–50 mappings; omission removes a segment only after preview/Apply.
    segments: Annotated[tuple[MappingSegment, ...], Field(min_length=1, max_length=50)]

    _root = field_validator("root_email")(mapping_email)

    # Reject blank names while allowing older mapping documents to omit this display metadata.
    @field_validator("root_name")
    @classmethod
    def clean_root_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("ROOT_NAME_REQUIRED")
        return value.strip() if value is not None else None

    # Labels, leaders and existing IDs must identify one unambiguous segment each.
    @model_validator(mode="after")
    def unique_segments(self):
        for values in (
            [s.label.casefold() for s in self.segments],
            [s.leader_email for s in self.segments],
            [s.id for s in self.segments if s.id is not None],
        ):
            if len(values) != len(set(values)):
                raise ValueError("DUPLICATE_SEGMENT_MAPPING")
        if any(s.leader_email == self.root_email for s in self.segments):
            raise ValueError("ROOT_CANNOT_LEAD_SEGMENT")
        return self


# All four mutable authorities fence an immediate Apply, including genuinely unapplied intake.
class MappingContext(Contract):
    configuration_id: UUID | None = None
    applied_version_id: UUID | None = None
    proposed_version_id: UUID | None = None
    registry_revision: int = 0


# Accept no actor, workspace, source trust or browser-computed impact.
class MappingRequest(Contract):
    context: MappingContext
    candidate: MappingCandidate
    # Explicit intent to edit a saved root email or display name; included in the preview binding.
    change_root: bool = False


# A canonical server digest binds Apply to the candidate that was actually previewed.
class MappingApply(MappingRequest):
    preview_token: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


# Retain small before/after mapping evidence rather than raw HR input in administrative audit.
class MappingChange(Contract):
    segment_id: str
    before: MappingSegment | None
    after: MappingSegment | None


# Each configured nomination is validated even when its branch has no healthy assignments.
class MappingRole(Contract):
    segment_id: str
    segment_name: str
    role: Literal["leader", "designee"]
    email: str
    status: Literal[
        "healthy",
        "departed",
        "excluded",
        "profile_missing",
        "ancestry_incomplete",
        "branch_changed",
        "not_verified",
    ]


# A paginated assignment delta shows classification and future routing, never tenancy mutations.
class MappingImpact(Contract):
    person_id: UUID
    name: str
    email: str
    # Derived graph states; root replacement can affect ancestry without changing a segment label.
    before_ancestry: Literal["root", "resolved", "incomplete"]
    after_ancestry: Literal["root", "resolved", "incomplete"]
    before_segment: str | None
    after_segment: str | None
    before_leader: str | None
    after_leader: str | None
    before_designees: tuple[str, ...]
    after_designees: tuple[str, ...]


# Read-only state distinguishes saved configuration from evidence not yet validated by a feed.
class MappingSettings(Contract):
    configured: bool
    available: bool
    context: MappingContext
    candidate: MappingCandidate | None
    root_editable: bool
    has_feed: bool
    roles: tuple[MappingRole, ...]
    blockers: tuple[str, ...]


# Preview pages all bind the same exact normalized candidate and current revision context.
class MappingPreview(Contract):
    # Saved boundary before this proposal; null only before initial configuration.
    root_before: str | None
    # Saved display name; null for revisions created before root display names were configured.
    root_name_before: Annotated[str, Field(max_length=256)] | None = None
    # Exact employee-row presence in the latest accepted source, not proof of eligibility.
    root_present: bool
    # Whole projected employee population with incomplete paths, independent of impact pagination.
    unresolved_count: int
    context: MappingContext
    candidate: MappingCandidate
    preview_token: str
    changes: tuple[MappingChange, ...]
    roles: tuple[MappingRole, ...]
    affected_count: int
    unassigned_count: int
    items: tuple[MappingImpact, ...]
    page: int
    pages: int
    blockers: tuple[str, ...]
    has_feed: bool
