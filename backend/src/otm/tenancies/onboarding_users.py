"""Validate permanent-user readback before retaining immutable onboarding evidence."""

from otm.providers.lifecycle import OnboardingUsers
from otm.tenancies.onboarding_contracts import OnboardingDiscovery


# Reject substituted scope, shared identities and temporary users before bootstrap retirement.
def capture_users(facade, intent, discovery):
    source = OnboardingDiscovery.model_validate(discovery)
    try:
        result = facade.capture_onboarding_users(intent, discovery)
    except Exception:
        raise ValueError("REQUIRED_USER_IDENTITIES_UNVERIFIED") from None
    users = OnboardingUsers.model_validate(
        result.model_dump(mode="json") if isinstance(result, OnboardingUsers) else result
    )
    if (
        users.workspace_id != intent.workspace_id
        or users.tenancy_ocid != intent.target.tenancy_ocid
        or users.parent_tenancy_ocid != intent.parent_tenancy_ocid
        or users.organization_id != intent.organization_id
        or users.domain_ocid != source.domain_ocid
    ):
        raise ValueError("REQUIRED_USER_IDENTITIES_UNVERIFIED")
    temporary_ocids = {source.bootstrap_user_ocid, source.activation_user_ocid}
    temporary_scim_ids = {source.bootstrap_scim_id, source.activation_scim_id}
    for subject in (users.automation, users.recovery):
        if (
            subject.provider_ocid in temporary_ocids
            or subject.scim_resource_id in temporary_scim_ids
        ):
            raise ValueError("REQUIRED_USER_IDENTITIES_UNVERIFIED")
    return users
