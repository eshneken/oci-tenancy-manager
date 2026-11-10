"""Nonsecret, versioned handoff and progress contracts for guided local onboarding."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.contracts import BaselineVersion
from otm.contracts import Contract, UtcInstant
from otm.email_policy import EmailContacts
from otm.providers.inspection_contracts import TenancyOcid
from otm.providers.lifecycle import OnboardingUsers

SimulatedUser = Annotated[str, Field(pattern=r"^ocid1\.user\.oc1\.\.otmsim[a-z0-9]{1,100}$")]


# A manual handoff identifies exact accounts; names and email never select cleanup targets.
class OnboardingHandoff(Contract):
    tenancy_ocid: TenancyOcid
    bootstrap_user_ocid: SimulatedUser
    activation_user_ocid: SimulatedUser | None = None


# Commands fence stale screens and keep transport retries tied to their original operation.
class OnboardingCommand(Contract):
    client_request_key: UUID
    revision: Annotated[int, Field(ge=1)]
    action: Literal["verify_handoff", "start_setup"]
    handoff: OnboardingHandoff | None = None
    confirm_cleanup: bool = False

    # Handoff verification and cleanup confirmation are separate, mutually exclusive decisions.
    @model_validator(mode="after")
    def action_fields(self):
        if (self.action == "verify_handoff") != (self.handoff is not None):
            raise ValueError("HANDOFF_REQUIRED")
        if self.action == "verify_handoff" and self.confirm_cleanup:
            raise ValueError("CLEANUP_PREVIEW_REQUIRED")
        if self.action == "start_setup" and not self.confirm_cleanup:
            raise ValueError("CLEANUP_CONFIRMATION_REQUIRED")
        return self


# Provider discovery returns read-back facts and exact domain bindings, never private credentials.
class OnboardingDiscovery(Contract):
    tenancy_ocid: TenancyOcid
    name: str
    home_region: str
    parent_tenancy_ocid: TenancyOcid
    organization_id: str
    domain_ocid: str
    bootstrap_user_ocid: SimulatedUser
    bootstrap_scim_id: str
    activation_user_ocid: SimulatedUser | None
    activation_scim_id: str | None


# One logical step retains its current result while immutable audit events retain past attempts.
class OnboardingCheck(Contract):
    key: str
    label: str
    state: Literal["pending", "verified", "needs_attention"]
    verified_at: UtcInstant | None = None


# The action panel comes from persisted progress rather than browser-local wizard state.
class OnboardingView(Contract):
    email_contacts: EmailContacts | None = None
    baseline: BaselineVersion | None = None
    operation_id: UUID
    tenancy_id: UUID
    revision: int
    state: str
    phase: Literal[
        "preparing", "handoff", "review", "configuring", "complete", "blocked", "cancelled"
    ]
    origin: Literal["create", "import"]
    requested_name: str | None = None
    requested_home_region: str | None = None
    can_act: bool = True
    expected_parent_tenancy_ocid: TenancyOcid
    owner_name: str
    administrator_name: str
    administrator_email: str | None
    suggested_handoff: OnboardingHandoff
    submitted_handoff: OnboardingHandoff | None
    discovery: OnboardingDiscovery | None
    bootstrap_username: str
    public_key: str | None = None
    checks: tuple[OnboardingCheck, ...]
    issue_code: str | None = None
    available_actions: tuple[Literal["verify_handoff", "start_setup"], ...]


# Audit evidence is closed and contains no secrets, raw SDK responses or arbitrary error text.
class OnboardingEvidence(Contract):
    contract_version: Literal["onboarding-1"] = "onboarding-1"
    step: Literal[
        "handoff",
        "inspect_bootstrap",
        "establish_automation",
        "verify_automation",
        "configure_required",
        "verify_required",
        "retire_temporary",
        "configure_baseline",
        "verify_configured_access",
        "capture_required_users",
        "prepare_recovery_password",
    ]
    outcome: Literal["accepted", "verified", "blocked"]
    safe_code: Literal[
        "ONBOARDING_ACCEPTED",
        "ONBOARDING_VERIFIED",
        "TARGET_CHANGED",
        "BOOTSTRAP_UNVERIFIED",
        "AUTOMATION_UNVERIFIED",
        "REQUIRED_ACCESS_UNVERIFIED",
        "CLEANUP_UNVERIFIED",
        "BASELINE_UNVERIFIED",
    ]
    client_request_key: UUID | None = None
    request_hash: str | None = None
    handoff: OnboardingHandoff | None = None
    discovery: OnboardingDiscovery | None = None
    # Absent on historical steps; exact readback evidence does not imply an active access binding.
    required_users: OnboardingUsers | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    # Only a successful capture carries identity evidence; historical steps remain byte-compatible.
    @model_validator(mode="after")
    def capture_evidence(self):
        captured = self.step == "capture_required_users" and self.outcome == "verified"
        if captured != (self.required_users is not None):
            raise ValueError("REQUIRED_USER_EVIDENCE_MISMATCH")
        return self
