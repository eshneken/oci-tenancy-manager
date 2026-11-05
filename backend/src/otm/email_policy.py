"""One trusted environment policy for external delivery and OCI-triggered contact emails."""

import hashlib
import json
import re
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract

Environment = Literal["local", "staging", "production"]


# Fixed diagnostics keep addresses and external failures out of unauthenticated error messages.
class EmailPolicyBlocked(ValueError):
    pass


# Use a deliberately narrow mailbox profile, rejecting display names, lists and header injection.
def mailbox(value):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 254
        or not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value
        )
        or value.startswith(".")
        or ".@" in value
        or any(
            not label or label.startswith("-") or label.endswith("-")
            for label in value.split("@")[-1].split(".")
        )
        or ".." in value
        or "." not in value.split("@")[-1]
    ):
        raise EmailPolicyBlocked("INVALID_EMAIL_ADDRESS")
    return value


# Freeze both intended identity contact and effective delivery without mutating employee records.
class EmailRoute(Contract):
    original_email: str | None
    effective_email: str | None
    environment: Environment
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    redirected: bool

    # Every frozen address obeys the same single-mailbox/header restrictions as configuration.
    @model_validator(mode="after")
    def valid_addresses(self):
        mailbox(self.original_email)
        mailbox(self.effective_email)
        return self


# OCI child activation and owner invitations retain separate immutable routing proofs.
class EmailContacts(Contract):
    activation: EmailRoute
    owner: EmailRoute
    people: dict[UUID, EmailRoute] = Field(default_factory=dict)


# Only operator settings choose the environment and destination; no request can disable redirection.
class MailPolicy(Contract):
    # Trusted deployment profile; local is compatible with existing offline simulator installations.
    environment: Environment = "local"
    # One optional single testing mailbox; required in staging and forbidden in production.
    email_override: str | None = None

    # Reject unsafe production overrides and incomplete staging profiles before any worker starts.
    @model_validator(mode="after")
    def compatible_environment(self):
        mailbox(self.email_override)
        if self.environment == "production" and self.email_override is not None:
            raise EmailPolicyBlocked("PRODUCTION_EMAIL_OVERRIDE_FORBIDDEN")
        if self.environment == "staging" and self.email_override is None:
            raise EmailPolicyBlocked("STAGING_EMAIL_OVERRIDE_REQUIRED")
        return self

    # A route binds only environment/redirection identity, not unrelated connection credentials.
    @property
    def fingerprint(self):
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    # Explicit testing routing can serve an email-less recovery administrator without
    # inventing a profile.
    def route(self, original):
        original = mailbox(original)
        return EmailRoute(
            original_email=original,
            effective_email=self.email_override or original,
            environment=self.environment,
            policy_hash=self.fingerprint,
            redirected=self.email_override is not None,
        )

    # Revalidate at actual egress; changed policy blocks old work instead of silently
    # retargeting it.
    def guard(self, route):
        route = EmailRoute.model_validate(route)
        if (
            (self.environment != "production" and self.email_override is None)
            or route != self.route(route.original_email)
            or route.effective_email is None
        ):
            raise EmailPolicyBlocked("EMAIL_ROUTE_BLOCKED")
        return route.effective_email

    # Registered OCI SDK builders and SMTP envelopes may use only an already qualified destination.
    def guard_address(self, address):
        address = mailbox(address)
        if (
            (self.environment != "production" and self.email_override is None)
            or address is None
            or (self.email_override and address != self.email_override)
        ):
            raise EmailPolicyBlocked("EMAIL_DESTINATION_BLOCKED")
        return address


# Public to authenticated administrators only; connection settings and secret references stay
# private.
class EmailPolicyView(Contract):
    environment: Environment
    redirected: bool
    effective_test_email: str | None
