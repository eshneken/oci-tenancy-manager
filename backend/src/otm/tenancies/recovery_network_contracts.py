"""Safe repair commands and private frozen evidence for one existing recovery network boundary."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.rollout_contracts import ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Text, UtcInstant
from otm.providers.recovery_console import RecoveryConsoleCapture
from otm.tenancies.presence_contracts import PresenceSnapshot


# Browser commands carry consent and immutable hashes, never operational CIDRs or provider IDs.
class RecoveryNetworkRequest(Contract):
    client_request_key: UUID
    preview_hash: Digest
    acknowledged: bool


# A compact public preview describes the security change without exposing configured networks.
class RecoveryNetworkPreview(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    preview_hash: Digest
    desired_fingerprint: Digest
    observed_fingerprint: Digest
    current_network_count: int = Field(ge=1, le=64)
    desired_network_count: int = Field(ge=1, le=64)
    expires_at: UtcInstant
    provider_mode: Literal["simulated"] = "simulated"


# Scope, source and desired revision are immutable; secrets and CIDRs remain outside this intent.
class RecoveryNetworkIntent(Contract):
    contract_version: Literal["recovery-network-repair-1"] = "recovery-network-repair-1"
    kind: Literal["recovery_network_repair"] = "recovery_network_repair"
    workspace_id: Text
    administrator_id: UUID
    authorization_revision: UUID
    snapshot: PresenceSnapshot
    source_check_id: UUID
    source_hash: Digest
    desired_fingerprint: Digest
    observed_fingerprint: Digest
    preview_hash: Digest
    target: ConfigurationOperationTarget
    expires_at: UtcInstant

    # Persisted internal metadata cannot redirect a repair to another workspace or tenancy.
    @model_validator(mode="after")
    def coherent_scope(self):
        if (
            self.workspace_id != self.snapshot.subjects[1].workspace_id
            or self.target.tenancy_ocid != self.snapshot.subjects[1].tenancy_ocid
            or self.desired_fingerprint != self.snapshot.recovery_console_fingerprint
        ):
            raise ValueError("RECOVERY_NETWORK_INTENT_INVALID")
        return self


# Only a verified exact readback may retain private provider capture for future simulated reads.
class RecoveryNetworkEvidence(Contract):
    contract_version: Literal["recovery-network-repair-1"] = "recovery-network-repair-1"
    operation_id: UUID
    tenancy_id: UUID
    snapshot: PresenceSnapshot
    effect: Literal["none", "known", "unknown"]
    state: Literal["verified", "blocked", "unknown", "superseded"]
    safe_code: Literal[
        "RECOVERY_NETWORK_VERIFIED",
        "RECOVERY_NETWORK_BLOCKED",
        "RECOVERY_NETWORK_UNKNOWN",
        "RECOVERY_NETWORK_SUPERSEDED",
    ]
    checked_at: UtcInstant
    # Provider capture is private database evidence; public operation projections select safe code.
    capture: RecoveryConsoleCapture | None = Field(default=None, repr=False)

    # Private captures remain exact and may describe an applied older revision without readiness.
    @model_validator(mode="after")
    def coherent_result(self):
        expected = {
            "verified": ("known", "RECOVERY_NETWORK_VERIFIED"),
            "superseded": ("known", "RECOVERY_NETWORK_SUPERSEDED"),
            "blocked": ("none", "RECOVERY_NETWORK_BLOCKED"),
            "unknown": ("unknown", "RECOVERY_NETWORK_UNKNOWN"),
        }[self.state]
        if (self.effect, self.safe_code) != expected or self.tenancy_id != self.snapshot.tenancy_id:
            raise ValueError("RECOVERY_NETWORK_EVIDENCE_INVALID")
        if (self.capture is not None) != (self.effect == "known"):
            raise ValueError("RECOVERY_NETWORK_EVIDENCE_INVALID")
        if self.capture is not None and (
            self.capture.scim_resource_id != self.snapshot.subjects[1].scim_resource_id
            or self.capture.facts.domain_ocid != self.snapshot.subjects[1].domain_ocid
            or self.capture.facts.perimeter.fingerprint
            != self.snapshot.recovery_console_fingerprint
        ):
            raise ValueError("RECOVERY_NETWORK_EVIDENCE_INVALID")
        return self
