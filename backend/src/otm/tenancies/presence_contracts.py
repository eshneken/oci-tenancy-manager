"""Independent presence/policy check scope, immutable evidence and safe browser projections."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.rollout_contracts import ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.providers.administrator_access import AdministratorCheck
from otm.providers.automation_keys import AutomationKeyCheck
from otm.providers.recovery_console import RecoveryConsoleCheck
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
    # Absent legacy snapshots stay byte-compatible and never gain inferred policy proof.
    recovery_console_fingerprint: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

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
    # New admissions opt into required-user notices; omission preserves historical intent bytes.
    notice_policy_version: Literal[1] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

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


# Current incident state travels with existing sealed evidence rather than a second incident table.
class PresenceNoticeEpisode(Contract):
    purpose: Literal["automation", "recovery"]
    scope_hash: Digest
    episode_id: UUID | None


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

    # Administrator assignments are independent of presence and absent in historical payloads.
    administrator_access: AdministratorCheck | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    # Recovery assignments remain a separately scoped result, without changing legacy bytes.
    recovery_administrator_access: AdministratorCheck | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    # Observed signing-key metadata is absent from legacy evidence, not an inferred empty list.
    automation_keys: AutomationKeyCheck | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    # Policy verification is independent of the two user-existence results.
    recovery_console: RecoveryConsoleCheck | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    # Ordered state is present only on new alert-enabled head publications; historical
    # bytes stay stable.
    notice_episodes: (
        Annotated[tuple[PresenceNoticeEpisode, ...], Field(min_length=2, max_length=2)] | None
    ) = Field(default=None, exclude_if=lambda value: value is None)

    # Qualified per-user Missing remains valid alongside an Unknown peer. Incomplete or
    # denied per-user evidence and superseded reads cannot certify presence or absence.
    @model_validator(mode="after")
    def coverage(self):
        for access, subject in zip(
            (self.administrator_access, self.recovery_administrator_access),
            self.results,
            strict=True,
        ):
            if access is not None and (
                access.context != subject.context
                or access.target != subject.target
                or not self.started_at <= access.checked_at <= self.checked_at
                or self.state == "superseded"
                and (access.result.group != "unknown" or access.result.domain_role != "unknown")
            ):
                raise ValueError("ADMINISTRATOR_CHECK_SCOPE_INVALID")
        if self.automation_keys is not None:
            keys = self.automation_keys
            if (
                keys.context != self.results[0].context
                or keys.target != self.results[0].target
                or not self.started_at <= keys.checked_at <= self.checked_at
                or self.state == "superseded"
                and keys.state != "unavailable"
            ):
                raise ValueError("AUTOMATION_KEY_CHECK_SCOPE_INVALID")
        if self.recovery_console is not None:
            policy = self.recovery_console
            if (
                policy.context != self.results[1].context
                or policy.target != self.results[1].target
                or not self.started_at <= policy.checked_at <= self.checked_at
                or self.state == "superseded"
                and policy.result.state != "unknown"
            ):
                raise ValueError("RECOVERY_CONSOLE_CHECK_SCOPE_INVALID")
        expected = {
            "complete": "USER_PRESENCE_CHECK_COMPLETE",
            "unavailable": "USER_PRESENCE_UNAVAILABLE",
            "superseded": "USER_PRESENCE_SUPERSEDED",
        }[self.state]
        a, b = self.results
        if self.notice_episodes is not None and tuple(e.purpose for e in self.notice_episodes) != (
            "automation",
            "recovery",
        ):
            raise ValueError("PRESENCE_EPISODES_INVALID")
        if self.notice_episodes is not None and any(
            (result.state == "present" and episode.episode_id is not None)
            or (result.state == "missing" and episode.episode_id is None)
            for result, episode in zip(self.results, self.notice_episodes, strict=True)
        ):
            raise ValueError("PRESENCE_EPISODES_INVALID")
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


# Stored policy facts never imply password health, admin grants or live OCI qualification.
class RecoveryConsoleView(Contract):
    state: Literal["not_checked", "verified", "drift", "unknown", "stale"] = "not_checked"
    mfa_exemption: Literal["not_checked", "verified", "drift", "unknown"] = "not_checked"
    network_boundary: Literal["not_checked", "verified", "drift", "unknown"] = "not_checked"
    checked_at: UtcInstant | None = None
    operation_id: UUID | None = None
    desired_fingerprint: Digest | None = None
    observed_fingerprint: Digest | None = None

    # A positive label needs complete dated evidence; stale retains past results without readiness.
    @model_validator(mode="after")
    def verified_evidence(self):
        if self.state in {"verified", "drift", "stale"} and (
            self.checked_at is None or self.operation_id is None or self.desired_fingerprint is None
        ):
            raise ValueError("RECOVERY_CONSOLE_VIEW_UNQUALIFIED")
        if self.state == "verified" and (
            self.mfa_exemption != "verified"
            or self.network_boundary != "verified"
            or self.observed_fingerprint is None
        ):
            raise ValueError("RECOVERY_CONSOLE_VIEW_UNQUALIFIED")
        return self


# Dated assignment reads never certify signing, passwords or all effective privileges.
class AdministratorAccessView(Contract):
    group: Literal["not_checked", "verified", "missing", "unknown"] = "not_checked"
    domain_role: Literal["not_checked", "verified", "missing", "unknown"] = "not_checked"
    stale: bool = False
    checked_at: UtcInstant | None = None
    operation_id: UUID | None = None

    # Positive and negative assignment claims require dated exact-operation provenance.
    @model_validator(mode="after")
    def qualified(self):
        if any(s in {"verified", "missing"} for s in (self.group, self.domain_role)) and (
            self.checked_at is None or self.operation_id is None
        ):
            raise ValueError("ADMINISTRATOR_VIEW_UNQUALIFIED")
        return self


# Inventory keeps existence and recovery policy separate from privileges/password readiness.
class RequiredUsersSummary(Contract):
    state: Literal["not_checked", "present", "missing", "unavailable", "stale"] = "not_checked"
    automation: UserPresenceView = Field(default_factory=UserPresenceView)
    recovery: UserPresenceView = Field(default_factory=UserPresenceView)
    checking: bool = False
    recovery_console: RecoveryConsoleView = Field(default_factory=RecoveryConsoleView)
    administrator_access: AdministratorAccessView = Field(default_factory=AdministratorAccessView)
    recovery_administrator_access: AdministratorAccessView = Field(
        default_factory=AdministratorAccessView
    )

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
