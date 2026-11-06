"""Presence-only check scope, immutable results and closed browser-facing projections."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.rollout_contracts import ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.providers.required_user_contracts import RequiredUserObservation, RequiredUserTarget


# Browser commands select no authority, credentials, provider facts or identity IDs.
class PresenceCheckRequest(Contract):
    client_request_key: UUID


# A complete registered context freezes the child and both exact independently observed subjects.
class PresenceSnapshot(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    tenancy_revision: Generation
    connection_id: UUID
    connection_revision: Generation
    policy_hash: Digest
    subjects: Annotated[tuple[RequiredUserTarget, ...], Field(min_length=2, max_length=2)]

    # A snapshot cannot mix children/domains, omit a purpose or alias the two account identities.
    @model_validator(mode="after")
    def coherent_subjects(self):
        a, b = self.subjects
        if (
            (a.purpose, b.purpose) != ("automation", "recovery")
            or a.tenancy_id != self.tenancy_id
            or b.tenancy_id != self.tenancy_id
            or (
                a.workspace_id,
                a.tenancy_ocid,
                a.parent_tenancy_ocid,
                a.organization_id,
                a.domain_ocid,
                a.identity_domain_binding_id,
            )
            != (
                b.workspace_id,
                b.tenancy_ocid,
                b.parent_tenancy_ocid,
                b.organization_id,
                b.domain_ocid,
                b.identity_domain_binding_id,
            )
            or a.subject_binding_id == b.subject_binding_id
            or a.scim_resource_id == b.scim_resource_id
        ):
            raise ValueError("PRESENCE_SCOPE_INVALID")
        return self


# The same ordinary operation/audit boundary owns durable queued manual reads.
class PresenceCheckIntent(Contract):
    contract_version: Literal["user-presence-check-1"] = "user-presence-check-1"
    kind: Literal["required_user_check"] = "required_user_check"
    workspace_id: Text
    administrator_id: UUID
    authorization_revision: UUID
    snapshot: PresenceSnapshot
    context_hash: Digest
    target: ConfigurationOperationTarget

    # Display metadata cannot redirect a frozen scoped read.
    @model_validator(mode="after")
    def scope(self):
        subject = self.snapshot.subjects[0]
        if (
            subject.workspace_id != self.workspace_id
            or self.target.tenancy_ocid != subject.tenancy_ocid
        ):
            raise ValueError("PRESENCE_INTENT_SCOPE_INVALID")
        return self


# Each sealed result retains two independent scoped provider observations, never a health claim.
class PresenceCheckEvidence(Contract):
    contract_version: Literal["user-presence-check-1"] = "user-presence-check-1"
    tenancy_id: UUID
    operation_id: UUID
    context_hash: Digest
    state: Literal["complete", "unavailable", "superseded"]
    safe_code: Literal[
        "USER_PRESENCE_CHECK_COMPLETE", "USER_PRESENCE_UNAVAILABLE", "USER_PRESENCE_SUPERSEDED"
    ]
    started_at: UtcInstant
    checked_at: UtcInstant
    results: Annotated[tuple[RequiredUserObservation, ...], Field(min_length=2, max_length=2)]

    # A successful read may establish Missing, but partial or superseded reads cannot certify facts.
    @model_validator(mode="after")
    def coverage(self):
        expected = {
            "complete": "USER_PRESENCE_CHECK_COMPLETE",
            "unavailable": "USER_PRESENCE_UNAVAILABLE",
            "superseded": "USER_PRESENCE_SUPERSEDED",
        }[self.state]
        a, b = self.results
        if (
            self.safe_code != expected
            or self.checked_at < self.started_at
            or (a.target.purpose, b.target.purpose) != ("automation", "recovery")
            or any(
                o.context.operation_id != self.operation_id
                or o.target.tenancy_id != self.tenancy_id
                or not self.started_at <= o.captured_at <= self.checked_at
                for o in self.results
            )
            or (self.state == "complete") != all(o.state != "unknown" for o in self.results)
            or self.state == "superseded"
            and any(o.state != "unknown" for o in self.results)
        ):
            raise ValueError("PRESENCE_EVIDENCE_INVALID")
        return self


# Public display deliberately separates existence from credentials, administrative grants and MFA.
class UserPresenceView(Contract):
    state: Literal["not_checked", "present", "missing", "unknown"] = "not_checked"
    checked_at: UtcInstant | None = None
    stale: bool = False
    operation_id: UUID | None = None


# A compact inventory projection describes existence only, never permissions or credential health.
class RequiredUsersSummary(Contract):
    state: Literal["not_checked", "present", "missing", "unavailable", "stale"] = "not_checked"
    automation: UserPresenceView = Field(default_factory=UserPresenceView)
    recovery: UserPresenceView = Field(default_factory=UserPresenceView)
    checking: bool = False

    # Positive summaries require dated per-subject source references, not a caller's label alone.
    @model_validator(mode="after")
    def qualified_labels(self):
        pair = (self.automation, self.recovery)
        fresh = tuple(
            v
            for v in pair
            if not v.stale and v.checked_at is not None and v.operation_id is not None
        )
        if self.state == "present" and (
            len(fresh) != 2 or any(v.state != "present" for v in fresh)
        ):
            raise ValueError("PRESENCE_SUMMARY_INVALID")
        if self.state == "missing" and not any(v.state == "missing" for v in fresh):
            raise ValueError("PRESENCE_SUMMARY_INVALID")
        return self
