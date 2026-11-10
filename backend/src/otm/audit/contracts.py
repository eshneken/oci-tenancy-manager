"""Closed, nonsecret audit directory fields; history is separate from operational action queues."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract, Text, UtcInstant

AuditKind = Literal[
    "email_delivery",
    "signing_key_outcome",
    "signing_key_requested",
    "operation_responsibility_changed",
    "configuration_check_outcome",
    "cost_collection_outcome",
    "required_user_check_outcome",
    "recovery_network_outcome",
    "recovery_password_outcome",
    "recovery_password_disclosed",
    "cost_refresh_requested",
    "configuration_review_staged",
    "baseline_draft_saved",
    "baseline_published",
    "baseline_default_changed",
    "operation_intent",
    "inspection_dispatch",
    "inspection_outcome",
    "organization_action_outcome",
    "onboarding_action",
    "onboarding_outcome",
    "configuration_outcome",
    "configuration_retry",
    "administrator_revoked",
    "administrator_bootstrapped",
    "local_credentials_reset",
    "local_sign_in_succeeded",
    "local_sign_in_failed",
    "session_logged_out",
    "audit_export",
    "organization_configured",
    "organization_feed_received",
    "organization_feed_rejected",
    "organization_published",
    "organization_review_decided",
]
AuditCategory = Literal[
    "authentication", "administration", "operations", "organization", "email_delivery"
]


# Export all matching rows independently of directory pagination; authority is never a filter.
class AuditExportQuery(Contract):
    sort: Literal["at", "kind", "actor_name"] = "at"
    direction: Literal["asc", "desc"] = "desc"
    category: Literal[
        "", "authentication", "administration", "operations", "organization", "email_delivery"
    ] = ""
    query: Annotated[str, Field(max_length=128)] = ""
    from_at: UtcInstant | None = None
    to_at: UtcInstant | None = None

    # A half-open UTC interval has one meaning for directory views and complete filtered exports.
    @model_validator(mode="after")
    def ordered_dates(self):
        if self.from_at is not None and self.to_at is not None and self.from_at >= self.to_at:
            raise ValueError("INVALID_AUDIT_DATE_RANGE")
        return self


# Scope is derived from the live session, while all browser-provided controls are bounded.
class AuditQuery(AuditExportQuery):
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50, 100] = 10


# A scoped resource label supplements the operation link without changing immutable audit facts.
class AuditResource(Contract):
    kind: Literal["tenancy", "person"]
    id: UUID
    name: Annotated[str, Field(min_length=1, max_length=320)]


# Expose display context, closed outcomes and selected recorded changes without raw payloads.
class AuditEntry(Contract):
    resources: Annotated[tuple[AuditResource, ...], Field(max_length=501)] = ()
    baseline_id: UUID | None = None
    id: UUID
    at: UtcInstant
    kind: AuditKind
    category: AuditCategory
    actor_name: Text | None
    operation_id: UUID | None
    administrator_id: UUID | None
    administrator_name: Text | None
    safe_code: Text | None
    # Readable allowlisted action summary, derived from immutable recorded evidence.
    summary: Annotated[str, Field(max_length=512)] | None = None
    # Selected historical before/after values; never raw feed, credentials or full configuration.
    changes: Annotated[
        tuple[Annotated[str, Field(max_length=18000)], ...], Field(max_length=512)
    ] = ()
    organization_subject_name: Annotated[str, Field(max_length=320)] | None = None


# Count/page rows come from one read-only snapshot; retention is independent of pagination.
class AuditDirectory(Contract):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int
    pages: int


# Record server preparation, never successful receipt of a download or its sensitive search text.
class AuditExportEvidence(Contract):
    contract_version: Literal["audit-export-1"]
    row_count: Annotated[int, Field(ge=0, le=10000)]
    query_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
