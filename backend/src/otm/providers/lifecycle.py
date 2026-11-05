"""Typed lifecycle facade with deterministic local simulation and no OCI credential access."""

from hashlib import sha256
from typing import Protocol
from uuid import UUID

from otm.contracts import Contract
from otm.operations.contracts import InspectionPolicy
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


# Record exact simulated identity/compartment bindings for safe later membership removal.
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

    # Return public synthetic setup fixtures without issuing a usable key or secret.
    def onboarding_handoff(self, intent: OrganizationIntent): ...

    # Discover exact child/domain/account identities before authorizing any configuration write.
    def inspect_onboarding(self, intent: OrganizationIntent, handoff): ...

    # Apply and read back one dependency-satisfied setup step, preserving replay target identity.
    def onboarding_step(self, intent: OrganizationIntent, key: str, discovery: dict): ...

    # Read the configured parent's subscribed regions before admitting a child creation.
    def creation_regions(self) -> tuple[CreationRegion, ...]: ...

    # Return qualified existing parents; arbitrary compartment targets are not accepted by the UI.
    def compartments(self, tenancy_ocid: str) -> tuple[CompartmentOption, ...]: ...


# Synthetic IDs are deterministic across process restarts; no external OCI effect is claimed.
class SimulatedLifecycleFacade:
    # Resolve trusted scope from the same explicit local sandbox policy used by the worker.
    def __init__(self, policy: InspectionPolicy):
        from otm.providers.configuration import SimulatedConfigurationFacade

        self.policy = policy
        self.configuration_facade = SimulatedConfigurationFacade(policy)
        self._member_access = {}

    # Local choices simulate parent subscriptions; production must discover them through the
    # parent SDK.
    def creation_regions(self):
        return (
            CreationRegion(identifier="us-ashburn-1", name="US East (Ashburn)"),
            CreationRegion(identifier="us-phoenix-1", name="US West (Phoenix)"),
            CreationRegion(identifier="eu-frankfurt-1", name="Germany Central (Frankfurt)"),
        )

    # Discover root and two stable simulated existing compartments for the selected registered
    # child.
    def compartments(self, tenancy_ocid):
        if (
            not tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
            or tenancy_ocid == self.policy.parent_tenancy_ocid
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        suffix = sha256(tenancy_ocid.encode()).hexdigest()[:24]
        return (
            CompartmentOption(ocid=tenancy_ocid, name="Root compartment"),
            CompartmentOption(
                ocid="ocid1.compartment.oc1..otmsimprojects" + suffix, name="Projects"
            ),
            CompartmentOption(
                ocid="ocid1.compartment.oc1..otmsimshared" + suffix, name="Shared environments"
            ),
        )

    # Predictable nonusable account IDs let local tests exercise the exact-account handoff.
    def onboarding_handoff(self, intent):
        from otm.tenancies.onboarding_contracts import OnboardingHandoff

        suffix = intent.pending_tenancy_id.hex
        return OnboardingHandoff(
            tenancy_ocid=intent.target.tenancy_ocid,
            bootstrap_user_ocid="ocid1.user.oc1..otmsimbootstrap" + suffix,
            activation_user_ocid="ocid1.user.oc1..otmsimactivation" + suffix
            if intent.action == "create_tenancy"
            else None,
        )

    # Discovery checks exact synthetic identity and parent scope; confirmation is never evidence.
    def inspect_onboarding(self, intent, handoff):
        from otm.tenancies.onboarding_contracts import OnboardingDiscovery

        self.apply(intent)
        if handoff != self.onboarding_handoff(intent):
            raise ValueError("BOOTSTRAP_UNVERIFIED")
        suffix = intent.pending_tenancy_id.hex
        return OnboardingDiscovery(
            tenancy_ocid=handoff.tenancy_ocid,
            name=intent.name or "sandbox-" + suffix[:12],
            home_region=(intent.home_region or "us-ashburn-1")
            if intent.action == "create_tenancy"
            else "us-ashburn-1",
            parent_tenancy_ocid=intent.parent_tenancy_ocid,
            organization_id=intent.organization_id,
            domain_ocid="ocid1.domain.oc1..otmsim" + suffix,
            bootstrap_user_ocid=handoff.bootstrap_user_ocid,
            bootstrap_scim_id="bootstrap-" + suffix,
            activation_user_ocid=handoff.activation_user_ocid,
            activation_scim_id="activation-" + suffix if handoff.activation_user_ocid else None,
        )

    # Each bounded capability verifies the same target; a real adapter requires separate
    # qualification.
    def onboarding_step(self, intent, key, discovery):
        expected = self.inspect_onboarding(intent, self.onboarding_handoff(intent))
        if discovery != expected.model_dump(mode="json") or key not in {
            "establish_automation",
            "verify_automation",
            "configure_required",
            "verify_required",
            "retire_temporary",
        }:
            raise ValueError("TARGET_CHANGED")

    # Simulated readback is exact-account scoped and never deletes a compartment or its resources.
    def remove_member_access(self, intent, association):
        if (
            association.action != "remove"
            or not association.user_ocid
            or not association.user_ocid.startswith("ocid1.user.oc1..otmsim")
            or association.tenancy_ocid == self.policy.parent_tenancy_ocid
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        key = (association.tenancy_ocid, association.user_ocid)
        self._member_access.setdefault(key, {"groups": True, "user": True})
        self.remove_member_groups(association)
        self.delete_member_user(association)
        return self.read_member_access(association)

    # Remove only this user's group memberships, leaving shared groups and other users intact.
    def remove_member_groups(self, association):
        self._member_access[(association.tenancy_ocid, association.user_ocid)]["groups"] = False

    # Delete the exact personal user only after its group memberships have been retired.
    def delete_member_user(self, association):
        state = self._member_access[(association.tenancy_ocid, association.user_ocid)]
        if state["groups"]:
            raise LifecycleBlocked("TARGET_CHANGED")
        state["user"] = False

    # Independent observation reads mutated fake provider state, rather than echoing desired flags.
    def read_member_access(self, association):
        state = self._member_access[(association.tenancy_ocid, association.user_ocid)]
        return MemberRemoval(
            association_id=association.id,
            tenancy_ocid=association.tenancy_ocid,
            user_ocid=association.user_ocid,
            group_memberships_removed=not state["groups"],
            user_deleted=not state["user"],
        )

    # Registry publication is separate from guided setup; simulation never qualifies real
    # OCI access.
    # A real adapter must implement those separately before it can be composed into production.
    def apply(self, intent):
        if (
            intent.workspace_id,
            intent.policy_revision,
            intent.organization_id,
            intent.parent_tenancy_ocid,
        ) != (
            self.policy.workspace_id,
            self.policy.policy_revision,
            self.policy.organization_id,
            self.policy.parent_tenancy_ocid,
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        targets = [a.tenancy_ocid for a in intent.associations]
        if intent.target.tenancy_ocid:
            targets.append(intent.target.tenancy_ocid)
        if any(
            not t.startswith("ocid1.tenancy.oc1..otmsim") or t == intent.parent_tenancy_ocid
            for t in targets
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        if any(a.parent_tenancy_ocid != intent.parent_tenancy_ocid for a in intent.associations):
            raise LifecycleBlocked("TARGET_CHANGED")
        bindings = []
        for item in intent.associations:
            if item.action == "transfer":
                suffix = sha256(
                    (item.tenancy_ocid + str(item.recipient_person_id)).encode()
                ).hexdigest()[:32]
                bindings.append(
                    MemberBinding(
                        association_id=item.new_association_id,
                        tenancy_ocid=item.tenancy_ocid,
                        person_id=item.recipient_person_id,
                        user_ocid=item.recipient_user_ocid or "ocid1.user.oc1..otmsim" + suffix,
                        compartment_ocid=item.recipient_compartment_ocid,
                        parent_compartment_ocid=item.recipient_parent_compartment_ocid,
                    )
                )
        if intent.pending_association_id is not None:
            tenant = intent.target.tenancy_ocid
            if tenant is None:
                raise LifecycleBlocked("TARGET_CHANGED")
            if intent.action == "join_shared" and (
                intent.existing_compartment_ocid or intent.parent_compartment_ocid
            ) not in {p.ocid for p in self.compartments(tenant)}:
                raise LifecycleBlocked("TARGET_CHANGED")
            if intent.existing_compartment_ocid == tenant:
                raise LifecycleBlocked("TARGET_CHANGED")
            suffix = sha256((tenant + str(intent.target.person_id)).encode()).hexdigest()[:32]
            bindings.append(
                MemberBinding(
                    association_id=intent.pending_association_id,
                    tenancy_ocid=tenant,
                    person_id=intent.target.person_id,
                    user_ocid="ocid1.user.oc1..otmsim" + suffix,
                    compartment_ocid=intent.existing_compartment_ocid
                    or ("ocid1.compartment.oc1..otmsim" + intent.pending_association_id.hex)
                    if intent.action == "join_shared"
                    else None,
                    parent_compartment_ocid=intent.parent_compartment_ocid,
                )
            )
        return LifecycleCompletion(
            bindings=tuple(bindings),
            removals=tuple(
                self.remove_member_access(intent, item)
                for item in intent.associations
                if item.action == "remove"
            ),
        )
