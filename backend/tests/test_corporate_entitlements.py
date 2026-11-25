"""Only the active Atlas grant authorizes requests in an already authenticated session."""

from unittest.mock import Mock

import pytest

from otm.auth.corporate_enrollment import EnrollmentTarget
from otm.auth.corporate_entitlements import CorporateEntitlements

GUID = "b" * 32
LOCAL_ISSUER = "urn:otm:recovery"


# Dispatch explicit namespaces to the same current local grant store.
@pytest.fixture
def authority():
    target = EnrollmentTarget(
        environment="development",
        workspace="development",
        domain="domain",
        issuer="urn:otm:domain",
        app="a" * 32,
        group="c" * 32,
    )
    return CorporateEntitlements(Mock(), LOCAL_ISSUER, target)


# Corporate and local sessions both recheck their existing Atlas grant.
def test_entitlements_check_current_grants_for_both_issuers(authority):
    require = authority.grants.require_admin
    for issuer, subject in ((LOCAL_ISSUER, "local"), (authority.target.issuer, GUID)):
        assert (
            authority.require_admin(issuer, subject, authority.target.workspace)
            is require.return_value
        )
        require.assert_called_with(issuer, subject, authority.target.workspace)
    require.side_effect = PermissionError()
    with pytest.raises(PermissionError):
        authority.require_admin(authority.target.issuer, GUID, authority.target.workspace)


# Reject cross-environment calls, untrusted issuers and mutable corporate identifiers.
def test_entitlements_reject_mismatched_corporate_scope(authority):
    with pytest.raises(PermissionError):
        authority.require_admin(authority.target.issuer, GUID, "staging")
    with pytest.raises(PermissionError):
        authority.require_admin("other-issuer", GUID, authority.target.workspace)
    with pytest.raises(ValueError):
        authority.require_admin(
            authority.target.issuer, "synthetic@example.test", authority.target.workspace
        )
    authority.grants.require_admin.assert_not_called()
    with pytest.raises(ValueError, match="CORPORATE_ISSUER_COLLISION"):
        CorporateEntitlements(authority.grants, authority.target.issuer, authority.target)
