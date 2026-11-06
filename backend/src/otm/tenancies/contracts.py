"""Closed organization workflow commands; authority and scope never come from the browser."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.contracts import BaselineVersion
from otm.contracts import Contract, Text, UtcInstant
from otm.email_policy import EmailContacts
from otm.providers.inspection_contracts import TenancyOcid

Action = Literal[
    "create_tenancy",
    "import_tenancy",
    "join_shared",
    "offboard_person",
    "delete_tenancy",
    "remove_member",
    "transfer_owner",
    "no_tenancy_required",
    "ignore",
    "resolve",
    "merge",
    "reonboard",
    "mark_returned",
    "cancel_simulation",
]


# These person commands remove access, ownership or stable identity; local review decisions do not.
DESTRUCTIVE_ACTIONS = frozenset(
    {
        "offboard_person",
        "delete_tenancy",
        "remove_member",
        "transfer_owner",
        "merge",
    }
)


# A preview binds decisions to both organization heads, configuration and registry changes.
class OrganizationContext(Contract):
    applied_version_id: UUID
    proposed_version_id: UUID
    configuration_id: UUID
    registry_revision: Annotated[int, Field(ge=1)]


# One offboarding choice describes every active obligation, including explicit retained access.
class AssociationChoice(Contract):
    association_id: UUID
    action: Literal["delete", "transfer", "remove", "keep"]
    recipient_person_id: UUID | None = None

    # A transfer is explicit and never inferred from the reporting chain or tenancy name.
    @model_validator(mode="after")
    def transfer_target(self):
        if (self.action == "transfer") != (self.recipient_person_id is not None):
            raise ValueError("TRANSFER_RECIPIENT_REQUIRED")
        return self


# Public bounded action inputs carry only identifiers, choices and acknowledged preview context.
class OrganizationAction(Contract):
    client_request_key: UUID
    context: OrganizationContext
    action: Action
    person_id: UUID
    review_id: UUID | None = None
    tenancy_id: UUID | None = None
    operation_id: UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    tenancy_kind: Literal["individual", "shared"] = "individual"
    home_region: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")] | None = None
    import_ocid: TenancyOcid | None = None
    parent_compartment_ocid: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    compartment_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    # A selected existing compartment replaces creation inputs.
    # Omit null to retain old request hashes.
    existing_compartment_ocid: Annotated[str, Field(min_length=1, max_length=256)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    # An existing-compartment assignment cannot also request resource creation or another action.
    @model_validator(mode="after")
    def compartment_choice(self):
        if self.existing_compartment_ocid is not None and (
            self.action != "join_shared"
            or self.parent_compartment_ocid is not None
            or self.compartment_name is not None
        ):
            raise ValueError("EXCLUSIVE_COMPARTMENT_CHOICE_REQUIRED")
        return self

    recipient_person_id: UUID | None = None
    partner_person_id: UUID | None = None
    plan: Annotated[tuple[AssociationChoice, ...], Field(max_length=100)] = ()
    # Omitted false preserves pre-consent request hashes for exact historical replay.
    # New destructive admissions require true; it never substitutes for target-specific warnings.
    confirm_destructive: bool = Field(default=False, exclude_if=lambda value: value is False)
    confirm_no_associations: bool = False
    confirm_manager: bool = False
    confirm_shared: bool = False


# A provider-bound association freezes exact targets; a later merge/feed cannot redirect a job.
class FrozenAssociation(Contract):
    person_id: UUID | None = None
    person_was_manager: bool = False
    id: UUID
    tenancy_id: UUID
    tenancy_revision: Annotated[int, Field(ge=1)]
    role: Literal["owner", "member"]
    action: Literal["delete", "transfer", "remove", "keep"]
    tenancy_ocid: TenancyOcid
    parent_tenancy_ocid: TenancyOcid
    recipient_person_id: UUID | None = None
    new_association_id: UUID | None = None
    recipient_user_ocid: str | None = None
    recipient_compartment_ocid: str | None = None
    recipient_compartment_name: str | None = None
    recipient_parent_compartment_ocid: str | None = None
    user_ocid: str | None = None
    compartment_ocid: str | None = None


# A generic display target supports person-wide operations without inventing a tenancy OCID.
class LifecycleTarget(Contract):
    tenancy_ocid: TenancyOcid | None = None
    person_id: UUID
    display_name: Text


# The committed immutable intent contains no passwords, PEM keys or raw source-feed content.
class OrganizationIntent(Contract):
    contract_version: Literal["organization-action-1"] = "organization-action-1"
    kind: Literal["organization_action"] = "organization_action"
    workspace_id: Text
    policy_revision: UUID
    organization_id: Text
    parent_tenancy_ocid: TenancyOcid
    administrator_id: UUID
    authorization_revision: UUID
    action: Action
    # Only the tenancy-level service can freeze a complete multi-person deletion plan.
    whole_tenancy_deletion: bool = False
    target: LifecycleTarget
    person_was_absent: bool
    person_was_manager: bool
    pending_tenancy_id: UUID | None = None
    pending_association_id: UUID | None = None
    # Existing accepted intents retain the original one-step simulator when this is absent.
    onboarding_version: Literal[1, 2, 3] | None = None
    # New opted-in captures may register a simulated connection; absence preserves legacy bytes.
    presence_connection_contract: Literal["simulated-user-presence-1"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # Full immutable publication snapshot; absent only for previously accepted local operations.
    baseline: BaselineVersion | None = None
    # The initiating verified mailbox is frozen separately from ownership; local testing may
    # lack one.
    activation_email: str | None = None
    # Absent legacy snapshots remain byte-compatible when reconstructed for takeover authority.
    email_contacts: EmailContacts | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    name: str | None = None
    tenancy_kind: Literal["individual", "shared"] = "individual"
    home_region: str | None = None
    parent_compartment_ocid: str | None = None
    compartment_name: str | None = None
    existing_compartment_ocid: Annotated[str, Field(min_length=1, max_length=256)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    associations: tuple[FrozenAssociation, ...] = ()

    # New setup graphs cannot silently omit configuration or reuse a legacy action boundary.
    @model_validator(mode="after")
    def baseline_setup_required(self):
        if self.onboarding_version in {2, 3} and (
            self.action not in {"create_tenancy", "import_tenancy"}
            or self.baseline is None
            or self.baseline.published_at is None
        ):
            raise ValueError("PUBLISHED_ONBOARDING_BASELINE_REQUIRED")
        if self.presence_connection_contract is not None and self.onboarding_version != 3:
            raise ValueError("PRESENCE_CONNECTION_REQUIRES_FRESH_CAPTURE")
        return self


# Public receipt distinguishes a real application decision from queued simulated provider work.
class ActionReceipt(Contract):
    operation_id: UUID | None
    state: Literal[
        "queued", "succeeded", "running", "needs_attention", "failed", "cancelled", "waiting"
    ]
    provider_mode: Literal["simulated", "application"]
    accepted_at: UtcInstant


# Exact readback receipt proves access removal without claiming compartment or resource cleanup.
class MemberRemoval(Contract):
    association_id: UUID
    tenancy_ocid: TenancyOcid
    user_ocid: str
    group_memberships_removed: Literal[True]
    user_deleted: Literal[True]


# A closed simulated completion proves the local registry milestone, never real OCI execution.
class OrganizationActionOutcome(Contract):
    contract_version: Literal["organization-action-1"] = "organization-action-1"
    provider_mode: Literal["simulated"] = "simulated"
    action: Action
    removals: tuple[MemberRemoval, ...] = ()
    safe_code: Literal[
        "SIMULATED_LIFECYCLE_VERIFIED",
        "AUTHORIZATION_CHANGED",
        "TARGET_CHANGED",
        "PERSON_RETURNED",
        "LIFECYCLE_UNAVAILABLE",
        "EMAIL_ROUTING_CHANGED",
        "SIMULATION_CANCELLED",
    ]
    verified_at: UtcInstant | None
