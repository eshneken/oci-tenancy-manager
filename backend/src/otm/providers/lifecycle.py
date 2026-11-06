"""Lifecycle capability contracts and shared binding/result types; no adapter selection or I/O."""

from typing import Protocol
from uuid import UUID

from otm.contracts import Contract
from otm.tenancies.contracts import MemberRemoval, OrganizationIntent
from otm.tenancies.views import CompartmentOption, CreationRegion


# Dispatch failures contain only a closed code, never a provider exception or secret payload.
class LifecycleBlocked(ValueError):
    # Unknown failures cannot become arbitrary UI or audit text.
    def __init__(self, code):
        if code not in {
            "AUTHORIZATION_CHANGED",
            "TARGET_CHANGED",
            "PERSON_RETURNED",
            "LIFECYCLE_UNAVAILABLE",
            "EMAIL_ROUTING_CHANGED",
        }:
            raise ValueError("INVALID_LIFECYCLE_CODE")
        self.code = code
        super().__init__(code)


# Record exact identity/compartment bindings for scoped membership removal.
class MemberBinding(Contract):
    association_id: UUID
    tenancy_ocid: str
    person_id: UUID
    user_ocid: str
    compartment_ocid: str | None
    parent_compartment_ocid: str | None


# A completion proves only the milestones declared by its qualified provider mode.
class LifecycleCompletion(Contract):
    bindings: tuple[MemberBinding, ...] = ()
    removals: tuple[MemberRemoval, ...] = ()


# The application depends on closed capabilities instead of SDK clients or credential material.
class LifecycleFacade(Protocol):
    # Execute/read-back the exact frozen target; replaying an intent must retain target identity.
    def apply(self, intent: OrganizationIntent) -> LifecycleCompletion: ...

    # Remove group memberships and delete the exact user, then independently verify absence.
    def remove_member_access(self, intent, association) -> MemberRemoval: ...

    # Return setup handoff metadata; usable credentials require the qualified implementation.
    def onboarding_handoff(self, intent: OrganizationIntent): ...

    # Discover exact child/domain/account identities before authorizing any configuration write.
    def inspect_onboarding(self, intent: OrganizationIntent, handoff): ...

    # Apply and read back one dependency-satisfied setup step, preserving replay target identity.
    def onboarding_step(self, intent: OrganizationIntent, key: str, discovery: dict): ...

    # Read the configured parent's subscribed regions before admitting a child creation.
    def creation_regions(self) -> tuple[CreationRegion, ...]: ...

    # Return qualified existing parents; arbitrary compartment targets are not accepted by the UI.
    def compartments(self, tenancy_ocid: str) -> tuple[CompartmentOption, ...]: ...
