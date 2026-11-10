"""Nonsecret setup, disclosure, original-window and password-rotation contracts."""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.rollout_contracts import ConfigurationOperationTarget, Digest
from otm.contracts import Contract, Text, UtcInstant
from otm.providers.recovery_password import PasswordLocation, PasswordVersion


# One durable system operation either prepares custody or closes an original disclosure window.
class RecoveryPasswordIntent(Contract):
    contract_version: Literal["recovery-password-1"] = "recovery-password-1"
    kind: Literal["recovery_password"] = "recovery_password"
    workspace_id: Text
    phase: Literal["setup", "rotation"]
    credential_id: UUID
    generation: int = Field(ge=1)
    location: PasswordLocation
    target: ConfigurationOperationTarget
    onboarding_operation_id: UUID
    expected_current: Text | None = None
    exposure_generation: int = Field(ge=0)
    due_at: UtcInstant | None = None

    # Exact child ownership and original deadline are not replaceable browser/provider arguments.
    @model_validator(mode="after")
    def coherent_scope(self):
        if (
            self.credential_id != self.location.credential_id
            or self.workspace_id != self.location.target.workspace_id
            or self.target.tenancy_ocid != self.location.target.tenancy_ocid
            or (
                self.phase == "setup"
                and (
                    self.location.secret_reference is not None
                    or self.expected_current is not None
                    or self.due_at is not None
                    or self.exposure_generation != 0
                )
            )
            or (
                self.phase == "rotation"
                and (
                    self.location.secret_reference is None
                    or self.expected_current is None
                    or self.due_at is None
                    or self.exposure_generation < 1
                )
            )
        ):
            raise ValueError("RECOVERY_PASSWORD_INTENT_INVALID")
        return self


# Public state describes readiness/deadlines and operation links without secret-location metadata.
class RecoveryPasswordView(Contract):
    tenancy_id: UUID
    tenancy_name: Text
    user_name: Text | None = None
    state: Literal[
        "not_prepared",
        "preparing",
        "ready",
        "exposed",
        "overdue",
        "rotating",
        "attention",
        "unavailable",
        "inactive",
    ]
    available: bool
    preview_hash: Digest | None = None
    first_disclosure_at: UtcInstant | None = None
    rotation_due_at: UtcInstant | None = None
    operation_id: UUID | None = None
    provider_mode: Literal["simulated"] = "simulated"


# Every intentional request has consent and a retry key; clients never select a secret or version.
class RecoveryPasswordRequest(Contract):
    client_request_key: UUID
    preview_hash: Digest
    acknowledged: bool


# Safe evidence is sufficient for audit/result projection; candidate material stays in custody.
class RecoveryPasswordEvidence(Contract):
    contract_version: Literal["recovery-password-1"] = "recovery-password-1"
    credential_id: UUID
    tenancy_id: UUID
    operation_id: UUID
    phase: Literal["setup", "rotation"]
    state: Literal["verified", "blocked", "unknown", "superseded"]
    effect: Literal["none", "known", "unknown"]
    safe_code: Literal[
        "RECOVERY_PASSWORD_VERIFIED",
        "RECOVERY_PASSWORD_BLOCKED",
        "RECOVERY_PASSWORD_UNKNOWN",
        "RECOVERY_PASSWORD_SUPERSEDED",
    ]
    checked_at: UtcInstant
    version: PasswordVersion | None = None

    # Unknown/blocked outcomes cannot carry a candidate as if it were confirmed usable.
    @model_validator(mode="after")
    def coherent_outcome(self):
        if (
            (self.state, self.effect, self.safe_code)
            not in {
                ("verified", "known", "RECOVERY_PASSWORD_VERIFIED"),
                ("blocked", "none", "RECOVERY_PASSWORD_BLOCKED"),
                ("unknown", "unknown", "RECOVERY_PASSWORD_UNKNOWN"),
                ("superseded", "known", "RECOVERY_PASSWORD_SUPERSEDED"),
            }
            or (self.version is not None) != (self.state in {"verified", "superseded"})
            or (
                self.version is not None
                and (
                    self.version.location.credential_id != self.credential_id
                    or self.version.operation_id != self.operation_id
                    or self.version.location.target.tenancy_id != self.tenancy_id
                )
            )
        ):
            raise ValueError("RECOVERY_PASSWORD_OUTCOME_INVALID")
        return self


# Disclosure history identifies one request and the unchanged root window, never the password.
class RecoveryDisclosureEvidence(Contract):
    contract_version: Literal["recovery-disclosure-1"] = "recovery-disclosure-1"
    grant_id: UUID
    credential_id: UUID
    tenancy_id: UUID
    disclosed_version_id: UUID
    window_root_grant_id: UUID
    exposure_generation: int = Field(ge=1)
    first_disclosure_at: UtcInstant
    rotation_due_at: UtcInstant
    duration_seconds: Literal[14400] = 14400
    deadline_anchor: Literal["first_authorized_disclosure"] = "first_authorized_disclosure"

    # The disclosure record cannot relabel a later or shorter deadline as the approved window.
    @model_validator(mode="after")
    def original_window(self):
        if self.rotation_due_at - self.first_disclosure_at != timedelta(hours=4):
            raise ValueError("RECOVERY_DISCLOSURE_DEADLINE_INVALID")
        return self


# This exceptional no-store response is last-mile only, never an intent, audit or cache value.
class RecoveryPasswordDisclosure(Contract):
    request_id: UUID
    user_name: Text
    password: str = Field(min_length=32, max_length=256, repr=False)
    first_disclosure_at: UtcInstant
    rotation_due_at: UtcInstant
    operation_id: UUID
    provider_mode: Literal["simulated"] = "simulated"
