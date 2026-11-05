"""Closed organization storage outcomes and redacted administrative/service evidence."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from otm.contracts import Contract, Text
from otm.operations.contracts import ActorIdentity
from otm.organization.contracts import Diagnostic
from otm.organization.mapping_contracts import MappingChange
from otm.tenancies.contracts import ActionReceipt


# Processing results identify persisted snapshots, never caller-supplied publishable candidates.
class OrganizationOutcome(Contract):
    snapshot_id: UUID
    state: Literal["received", "staged", "published", "rejected", "superseded", "duplicate"]
    proposed_version_id: UUID | None = None
    revision_id: UUID | None = None
    original_state: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


# Public audit projection validates this shape but does not disclose configuration or employee rows.
class OrganizationEvidence(Contract):
    contract_version: Literal["organization-1"] = "organization-1"
    request_key: UUID | None = None
    request_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    receipt: ActionReceipt | None = None
    review_id: UUID | None = None
    person_id: UUID | None = None
    action: Annotated[str, Field(max_length=64)] | None = None
    subject_name: Annotated[str, Field(max_length=320)] | None = None
    source_id: Text
    population_id: Text
    configuration_id: UUID
    feed_id: UUID | None = None
    proposed_version_id: UUID | None = None
    applied_version_id: UUID | None = None
    person_count: Annotated[int, Field(ge=0, le=10000)] = 0
    mapping_root_before: Annotated[str, Field(max_length=320)] | None = None
    mapping_root_after: Annotated[str, Field(max_length=320)] | None = None
    # Display-only before/after names; null preserves absent evidence in historical records.
    mapping_root_name_before: Annotated[str, Field(max_length=256)] | None = None
    mapping_root_name_after: Annotated[str, Field(max_length=256)] | None = None
    mapping_changes: tuple[MappingChange, ...] = ()
    diagnostic_count: Annotated[int, Field(ge=0, le=30000)] = 0


# Computation attribution grants no ingestion authority and cannot replace a live principal.
ORGANIZATION_SERVICE_ACTOR = ActorIdentity(
    issuer="urn:otm:service",
    subject="organization",
    display_name="Organization synchronization",
)
