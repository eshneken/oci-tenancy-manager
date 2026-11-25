"""Verify the closed email-based enrollment and exact membership contracts."""

from unittest.mock import Mock

import pytest

from otm.auth.corporate_enrollment import (
    FEDERATED_USER,
    CorporateLookup,
    DomainPerson,
    EnrollmentTarget,
    NewAccountName,
    federated_user_request,
    membership_request,
    prepare_enrollment,
)


# Keep OCI test data synthetic and bind it to one development app.
@pytest.fixture
def records():
    target = EnrollmentTarget(
        environment="development",
        workspace="synthetic",
        domain="example-domain",
        issuer="urn:example:enrollment",
        app="a" * 32,
        group="b" * 32,
    )
    account = DomainPerson(
        guid="c" * 32,
        domain=target.domain,
        username="Synthetic@example.test",
        display_name="Márta Synthetic",
        active=True,
        federated=True,
        deleting=False,
    )
    return target, account, CorporateLookup(value=account.username)


# Exact OCI login reuse supplies only the display details needed to review access.
@pytest.mark.parametrize("federated_only", [True, False])
def test_existing_account_is_reused_without_exposing_provider_ids(records, federated_only):
    target, account, lookup = records
    account = account.model_copy(update={"federated": federated_only})
    domain = Mock(return_value=(account,))
    enrollment = prepare_enrollment(lookup, target, domain)
    domain.assert_called_once_with(target.domain, lookup.value)
    assert enrollment.account == account
    assert enrollment.review().model_dump() == {
        "environment": "development",
        "role": "Administrator",
        "username": lookup.value,
        "work_email": lookup.value,
        "display_name": account.display_name,
        "existing_account": True,
    }
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        federated_user_request(
            enrollment, NewAccountName(first_name="Synthetic", last_name="Pilot")
        )


# A SCIM case-insensitive match, lifecycle mismatch, wrong domain, or duplicate is unsafe.
@pytest.mark.parametrize(
    "changes",
    [
        {"username": "synthetic@example.test"},
        {"active": False},
        {"deleting": True},
        {"domain": "other"},
        None,
    ],
)
def test_invalid_or_ambiguous_domain_account_cannot_be_used(records, changes):
    target, account, lookup = records
    rows = (account, account) if changes is None else (account.model_copy(update=changes),)
    with pytest.raises(ValueError, match="DOMAIN_BINDING_UNVERIFIED"):
        prepare_enrollment(lookup, target, Mock(return_value=rows))


# Creation accepts contact and profile details and cannot request credentials or privileges.
def test_new_federated_account_payload_is_closed(records):
    target, account, lookup = records
    enrollment = prepare_enrollment(lookup, target, Mock(return_value=()))
    assert not enrollment.review().existing_account
    assert enrollment.review().display_name == lookup.value
    name = NewAccountName(first_name="  Synthetic  ", last_name="Pilot")
    assert federated_user_request(enrollment, name) == {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User", FEDERATED_USER],
        "userName": lookup.value,
        "displayName": "Synthetic Pilot",
        "name": {"givenName": "Synthetic", "familyName": "Pilot"},
        "emails": [{"value": lookup.value, "type": "work", "primary": True}],
        FEDERATED_USER: {"isFederatedUser": True, "bypassNotification": True},
    }
    existing = prepare_enrollment(lookup, target, Mock(return_value=(account,)))
    assert existing.binding() != enrollment.binding()


# Bound profile names without restricting punctuation, spaces or non-ASCII letters.
@pytest.mark.parametrize("value", ["", "  ", "A" * 101, "First\nSecond"])
def test_rejects_invalid_new_account_names(value):
    with pytest.raises(ValueError):
        NewAccountName(first_name=value, last_name="D’Ávila")
    with pytest.raises(ValueError):
        NewAccountName(first_name="Anne-Marie", last_name=value)


# Reject anything other than a single exact email and reject browser-controlled selectors.
@pytest.mark.parametrize("value", ["synthetic", "invalid@no-domain", "person@example.test\nother"])
def test_lookup_requires_email_and_rejects_target_overrides(value):
    with pytest.raises(ValueError):
        CorporateLookup(value=value)
    with pytest.raises(ValueError):
        CorporateLookup.model_validate({"value": "example@example.test", "group": "x"})


# The provider receives one exact group, domain GUID and membership direction.
def test_membership_request_changes_one_exact_member(records):
    target, account, _ = records
    assert membership_request(target, account.guid, add=True) == (target.group, account.guid, True)
    assert membership_request(target, account.guid, add=False) == (
        target.group,
        account.guid,
        False,
    )
    with pytest.raises(ValueError):
        membership_request(target, "unknown", add=True)
