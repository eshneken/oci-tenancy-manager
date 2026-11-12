"""Nonsecret signing-credential admission, persistent checkpoints and bounded browser views."""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.rollout_contracts import ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.providers.required_user_contracts import RequiredUserTarget
from otm.providers.signing_key_rotation import ManagedSigningKey
from otm.tenancies.signing_key_engine import SigningRotationState


# A security-maintenance operation owns one original generation; it never retargets on a retry.
class SigningKeyIntent(Contract):
    contract_version: Literal["signer-1"] = "signer-1"
    kind: Literal["signing_key"] = "signing_key"
    phase: Literal["setup", "rotation"]
    workspace_id: Text
    credential_id: UUID
    subject: RequiredUserTarget
    connection_id: UUID
    connection_revision: Generation
    policy_hash: Digest
    expected_generation: int = Field(ge=0)
    source_operation_id: UUID
    source_evidence_event_id: UUID
    target: ConfigurationOperationTarget
    old: ManagedSigningKey | None = None
    due_at: UtcInstant | None = None

    # Scheduling time and original source identity cannot drift with display names or retries.
    @model_validator(mode="after")
    def exact_scope(self):
        if (
            self.workspace_id != self.subject.workspace_id
            or self.subject.purpose != "automation"
            or self.target.tenancy_ocid != self.subject.tenancy_ocid
        ):
            raise ValueError("SIGNING_KEY_INTENT_INVALID")
        if self.phase == "setup" and (
            self.old is not None or self.expected_generation != 0 or self.due_at is not None
        ):
            raise ValueError("SIGNING_KEY_INTENT_INVALID")
        if self.phase == "rotation" and (
            self.old is None
            or self.old.version.target != self.subject
            or self.old.version.credential_id != self.credential_id
            or self.old.version.generation != self.expected_generation
            or self.due_at != self.old.retire_at - timedelta(days=1)
        ):
            raise ValueError("SIGNING_KEY_INTENT_INVALID")
        return self


# Only allowlisted metadata is sealed; material, raw provider payloads and browser choices stay out.
class SigningKeyEvidence(Contract):
    contract_version: Literal["signer-1"] = "signer-1"
    operation_id: UUID
    credential_id: UUID
    tenancy_id: UUID
    phase: Literal["setup", "rotation"]
    state: Literal["progress", "verified", "attention", "cancelled"]
    safe_code: Literal[
        "SIGNING_KEY_PREPARED",
        "SIGNING_KEY_ROTATED",
        "SIGNING_KEY_PROGRESS",
        "SIGNING_KEY_CONTEXT_CHANGED",
        "SIGNING_KEY_CANDIDATE_UNAVAILABLE",
        "SIGNING_KEY_INVENTORY_UNAVAILABLE",
        "SIGNING_KEY_CUSTODY_CHANGED",
        "SIGNING_KEY_PROBE_FAILED",
        "SIGNING_KEY_SLOT_REVIEW",
        "SIGNING_KEY_UPLOAD_UNRECONCILED",
        "SIGNING_KEY_CURRENT_UNVERIFIED",
        "SIGNING_KEY_RETIREMENT_UNVERIFIED",
        "SIGNING_KEY_UNAVAILABLE",
        "SIGNING_KEY_TENANCY_INACTIVE",
    ]
    checkpoint: SigningRotationState | None = None
    current: ManagedSigningKey | None = None
    checked_at: UtcInstant


# Explicit requests never select a Vault version, fingerprint, credential or provider target.
class SigningKeyRequest(Contract):
    client_request_key: UUID
    preview_hash: Digest
    acknowledged: bool
    action: Literal["rotate", "resume"] = "rotate"


# Request replay is independent from generation completion, so a lost response cannot rotate again.
class SigningKeyRequestEvidence(Contract):
    contract_version: Literal["signer-1"] = "signer-1"
    operation_id: UUID
    tenancy_id: UUID
    client_request_key: UUID
    request_digest: Digest
    action: Literal["rotate", "resume"]
    acknowledged: Literal[True] = True
    safe_code: Literal["SIGNING_KEY_REQUESTED"] = "SIGNING_KEY_REQUESTED"


# Public progress exposes dates/operations, never secret-version locators or credential material.
class SigningKeyView(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    provider_mode: Literal["simulated"] = "simulated"
    state: Literal[
        "not_prepared",
        "preparing",
        "scheduled",
        "waiting",
        "rotating",
        "attention",
        "overdue",
        "inactive",
        "unavailable",
    ]
    generation: int = Field(default=0, ge=0)
    available: bool = False
    preview_hash: Digest | None = None
    operation_id: UUID | None = None
    starts_at: UtcInstant | None = None
    retire_at: UtcInstant | None = None
    safe_code: Text | None = None
    last_rotation_operation_id: UUID | None = None
    last_rotated_at: UtcInstant | None = None


# Labels describe committed evidence, distinguishing a pre-dispatch fence from verified success.
def signing_event_summary(evidence):
    if evidence.state == "verified":
        return (
            "Automation signer prepared" if evidence.phase == "setup" else "Key rotation completed"
        )
    if evidence.state == "attention":
        return (
            "Signing-key setup needs attention"
            if evidence.phase == "setup"
            else "Key rotation needs attention"
        )
    if evidence.state == "cancelled":
        return "Signing-key operation cancelled"
    checkpoint = evidence.checkpoint
    if checkpoint is None:
        return "Signing-key progress recorded"
    if checkpoint.phase == "upload":
        return (
            "Public-key upload authorized; verification pending"
            if checkpoint.upload_dispatched
            else "Replacement key staged"
        )
    if checkpoint.phase == "retire":
        return (
            "Old-key removal authorized; verification pending"
            if checkpoint.retire_dispatched
            else "Replacement activated; old-key retirement pending"
        )
    return {
        "stage": "Replacement preparation recorded",
        "verify": "Replacement public key observed",
        "activate": "Replacement signer verified",
        "complete": "Old key absent; replacement access verified",
    }[checkpoint.phase]
