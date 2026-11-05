"""Required typed egress builders for OCI contacts that may generate provider-owned email."""

from otm.contracts import Contract, Text
from otm.email_policy import EmailPolicyBlocked


# OCI login identity stays distinct from its notification mailbox, avoiding override collisions.
class IdentityContactRequest(Contract):
    username: Text
    primary_email: str
    recovery_email: str
    use_email_as_username: bool = False


# Call immediately before child creation, never substituting a current mailbox for an old route.
def activation_address(policy, intent):
    if intent.email_contacts is None:
        raise EmailPolicyBlocked("FROZEN_EMAIL_CONTACTS_REQUIRED")
    return policy.guard(intent.email_contacts.activation)


# SDK adapters consume only these qualified contact values; employee matching still uses real
# identity.
def identity_contacts(policy, username, route):
    address = policy.guard(route)
    return IdentityContactRequest(username=username, primary_email=address, recovery_email=address)


# Check all frozen recipients before any email-capable provider phase; unknown legacy live work
# blocks.
def validate_contacts(policy, intent):
    if intent.email_contacts is None:
        raise EmailPolicyBlocked("FROZEN_EMAIL_CONTACTS_REQUIRED")
    if intent.action == "create_tenancy":
        policy.guard(intent.email_contacts.activation)
    policy.guard(intent.email_contacts.owner)
    for route in intent.email_contacts.people.values():
        policy.guard(route)
