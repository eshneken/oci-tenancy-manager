"""Restore explicit fixture facts from producer capture, not expected identity rows."""

from otm.providers.required_user import RequiredUserInspection
from otm.providers.required_user_simulator import (
    SimulatedDomainUser,
    SimulatedIdentityDomain,
    SimulatedRequiredUserProvider,
    SimulatedUserReadAccess,
)


# This composition is simulation only: it reconfirms retained fixture facts, never live OCI state.
def simulated_presence_inspection(snapshot, source, clock):
    subject = snapshot.subjects[0]
    if (
        source.workspace_id,
        source.tenancy_ocid,
        source.parent_tenancy_ocid,
        source.organization_id,
    ) != (
        subject.workspace_id,
        subject.tenancy_ocid,
        subject.parent_tenancy_ocid,
        subject.organization_id,
    ):
        raise ValueError("SIMULATED_CAPTURE_SCOPE_INVALID")
    provider = SimulatedRequiredUserProvider(clock)
    provider.set_access(
        SimulatedUserReadAccess(
            workspace_id=source.workspace_id,
            connection_id=snapshot.connection_id,
            connection_revision=snapshot.connection_revision,
            permitted=True,
            tenancy_ocids=frozenset({source.tenancy_ocid}),
        )
    )
    at = clock()
    provider.set_domain(
        SimulatedIdentityDomain(
            workspace_id=source.workspace_id,
            tenancy_ocid=source.tenancy_ocid,
            parent_tenancy_ocid=source.parent_tenancy_ocid,
            organization_id=source.organization_id,
            domain_ocid=source.domain_ocid,
            visible_at=at,
            complete=True,
        )
    )
    for user in (source.automation, source.recovery):
        provider.set_user(
            SimulatedDomainUser(
                workspace_id=source.workspace_id,
                tenancy_ocid=source.tenancy_ocid,
                visible_at=at,
                **user.model_dump(),
            )
        )
    return RequiredUserInspection(provider, clock)
