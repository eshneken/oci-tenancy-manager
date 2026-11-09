"""Validate permanent-user readback before retaining immutable onboarding evidence."""

import json

from otm.providers.lifecycle import OnboardingUsers
from otm.tenancies.onboarding_contracts import OnboardingDiscovery


# Reject substituted scope, shared identities and temporary users before bootstrap retirement.
def capture_users(facade, intent, discovery):
    source = OnboardingDiscovery.model_validate(discovery)
    try:
        result = facade.capture_onboarding_users(intent, discovery)
        users = (
            OnboardingUsers.model_validate(result)
            if isinstance(result, OnboardingUsers)
            else OnboardingUsers.model_validate_json(json.dumps(result))
        )
    except Exception:
        raise ValueError("REQUIRED_USER_IDENTITIES_UNVERIFIED") from None
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
    from otm.providers.administrator_access import assess_assignments

    for capture in (users.automation_administrator, users.recovery_administrator):
        if capture is not None:
            result = assess_assignments(capture.binding, capture.facts)
            if result.group != "verified" or result.domain_role != "verified":
                raise ValueError("ADMINISTRATOR_ASSIGNMENTS_UNVERIFIED")
    if intent.recovery_console_fingerprint is not None:
        # Setup checks exact provider identities before permanent database bindings exist.
        from otm.providers.recovery_console import assess_policy

        capture = users.recovery_console
        if (
            capture is None
            or capture.facts.perimeter.fingerprint != intent.recovery_console_fingerprint
        ):
            raise ValueError("RECOVERY_CONSOLE_UNVERIFIED")
        if (
            assess_policy(
                capture.binding,
                users.domain_ocid,
                users.recovery.scim_resource_id,
                capture.facts.perimeter,
                capture.facts,
            ).state
            != "verified"
        ):
            raise ValueError("RECOVERY_CONSOLE_UNVERIFIED")
    return users
