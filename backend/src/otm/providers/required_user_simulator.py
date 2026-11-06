"""Fake domain/user state for presence reads; no credentials, SDK or network."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.providers.inspection_contracts import InspectionTarget, TenancyOcid
from otm.providers.inspection_simulator import SimulatedAccess
from otm.providers.required_user_contracts import (
    DomainOcid,
    InspectRequiredUser,
    ObservedRequiredUser,
    RequiredUserObservation,
    UserOcid,
)


# Keep inspecting authority independent of the automation/recovery subject under observation.
class SimulatedUserReadAccess(SimulatedAccess):
    context_generation: Generation
    credential_version_id: UUID | None


# An explicit domain fixture proves scope and exact-read coverage; absent domain data is unknown.
class SimulatedIdentityDomain(InspectionTarget):
    workspace_id: Text
    domain_ocid: DomainOcid
    visible_at: UtcInstant
    complete: bool
    fault: Literal["denied", "timeout", "unsupported"] | None = None


# Provider-side user facts can change independently of a command's retained binding or display name.
class SimulatedDomainUser(Contract):
    workspace_id: Text
    tenancy_ocid: TenancyOcid
    domain_ocid: DomainOcid
    scim_resource_id: Text
    provider_ocid: UserOcid | None
    user_name: Text
    visible_at: UtcInstant
    fault: Literal["denied", "timeout", "unsupported"] | None = None


# The explicit fixture adapter is never automatically selected by API or worker composition.
class SimulatedRequiredUserProvider:
    # Retain fake provider resources independently of application target/assignment metadata.
    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock
        self._access: dict[tuple[str, UUID], SimulatedUserReadAccess] = {}
        self._domains: dict[tuple[str, str, str], SimulatedIdentityDomain] = {}
        self._users: dict[tuple[str, str, str, str], SimulatedDomainUser] = {}

    # Trusted test authority references contain permission/scope facts, never usable key material.
    def set_access(self, access: SimulatedUserReadAccess) -> None:
        access = SimulatedUserReadAccess.model_validate(access)
        self._access[(access.workspace_id, access.access_binding_id)] = access

    # Synthetic-only domain fixtures cannot point this local adapter at a real tenancy.
    def set_domain(self, domain: SimulatedIdentityDomain) -> None:
        domain = SimulatedIdentityDomain.model_validate(domain)
        if (
            not domain.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
            or not domain.domain_ocid.startswith("ocid1.domain.oc1..otmsim")
            or domain.tenancy_ocid == domain.parent_tenancy_ocid
        ):
            raise ValueError("SIMULATED_CHILD_DOMAIN_REQUIRED")
        self._domains[(domain.workspace_id, domain.tenancy_ocid, domain.domain_ocid)] = domain

    # User fixtures keep OCI and SCIM identifiers distinct and permit observation-specific faults.
    def set_user(self, user: SimulatedDomainUser) -> None:
        user = SimulatedDomainUser.model_validate(user)
        if (
            not user.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
            or not user.domain_ocid.startswith("ocid1.domain.oc1..otmsim")
            or user.provider_ocid is not None
            and not user.provider_ocid.startswith("ocid1.user.oc1..otmsim")
        ):
            raise ValueError("SIMULATED_USER_REQUIRED")
        self._users[
            (user.workspace_id, user.tenancy_ocid, user.domain_ocid, user.scim_resource_id)
        ] = user

    # An authorized complete domain read can prove exact-user absence, never a domain lookup
    # failure.
    def inspect_required_user(self, command: InspectRequiredUser) -> RequiredUserObservation:
        command = InspectRequiredUser.model_validate(command)
        target, context, at = command.target, command.context, self.clock()
        common = dict(
            context=context,
            target=target,
            captured_at=at,
            read_id=None,
            checked_domain_ocid=None,
            checked_scim_resource_id=None,
            observed=None,
        )

        # Unsuccessful reads contain no identity facts and cannot manufacture Missing or usable
        # access.
        def unknown(code):
            return RequiredUserObservation(
                state="unknown", safe_code=code, authorized=False, complete=False, **common
            )

        access = self._access.get((context.workspace_id, context.access_binding_id))
        if not access or (
            access.credential_generation,
            access.context_generation,
            access.credential_version_id,
        ) != (
            context.credential_generation,
            context.context_generation,
            context.credential_version_id,
        ):
            return unknown("ACCESS_UNVERIFIED")
        if not access.permitted or target.tenancy_ocid not in access.tenancy_ocids:
            return unknown("ACCESS_DENIED")
        domain = self._domains.get((context.workspace_id, target.tenancy_ocid, target.domain_ocid))
        if not domain or (domain.parent_tenancy_ocid, domain.organization_id) != (
            target.parent_tenancy_ocid,
            target.organization_id,
        ):
            return unknown("DOMAIN_UNVERIFIED")
        if domain.fault:
            return unknown(
                {
                    "denied": "ACCESS_DENIED",
                    "timeout": "READ_TIMEOUT",
                    "unsupported": "UNSUPPORTED_CAPABILITY",
                }[domain.fault]
            )
        if at < domain.visible_at:
            return unknown("READ_DELAYED")
        if not domain.complete:
            return unknown("INCOMPLETE_READ")
        user = self._users.get(
            (context.workspace_id, target.tenancy_ocid, target.domain_ocid, target.scim_resource_id)
        )
        if user and user.fault:
            return unknown(
                {
                    "denied": "ACCESS_DENIED",
                    "timeout": "READ_TIMEOUT",
                    "unsupported": "UNSUPPORTED_CAPABILITY",
                }[user.fault]
            )
        if user and at < user.visible_at:
            return unknown("READ_DELAYED")
        values = {
            **common,
            "read_id": uuid4(),
            "checked_domain_ocid": domain.domain_ocid,
            "checked_scim_resource_id": target.scim_resource_id,
        }
        if user is None:
            return RequiredUserObservation(
                state="missing", safe_code="USER_MISSING", authorized=True, complete=True, **values
            )
        return RequiredUserObservation(
            state="present",
            safe_code="USER_PRESENT",
            authorized=True,
            complete=True,
            **{
                **values,
                "observed": ObservedRequiredUser(
                    domain_ocid=user.domain_ocid,
                    scim_resource_id=user.scim_resource_id,
                    provider_ocid=user.provider_ocid,
                    user_name=user.user_name,
                ),
            },
        )
