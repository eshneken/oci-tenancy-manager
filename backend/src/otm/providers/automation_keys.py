"""Exact automation-user API-key inventory contracts; no signer or custody authority."""

from datetime import timedelta
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints, model_validator

from otm.contracts import Contract, Text, UtcInstant
from otm.providers.required_user_contracts import (
    ObservedRequiredUser,
    RequiredUserReadContext,
    RequiredUserTarget,
)

Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{2}(?::[0-9a-f]{2}){15}$")]
MAXIMUM_AGE = timedelta(days=30)
PREPARE_LEAD = timedelta(days=1)


# Public key identifiers and creation evidence never include either PEM half or signing material.
class ObservedAutomationKey(Contract):
    provider_key_id: Text
    fingerprint: Fingerprint
    created_at: UtcInstant | None
    state: Literal["active", "inactive", "unknown"]


# Complete inventory and key-age certainty are separate; unknown creation times remain explicit.
class AutomationKeyFacts(Contract):
    user: ObservedRequiredUser
    authorized: bool
    complete: bool
    supported: bool
    keys: Annotated[tuple[ObservedAutomationKey, ...], Field(max_length=16)]

    # Ambiguous pagination/identity results never become a known empty or de-duplicated inventory.
    @model_validator(mode="after")
    def unique_keys(self):
        if len({key.provider_key_id for key in self.keys}) != len(self.keys) or len(
            {key.fingerprint for key in self.keys}
        ) != len(self.keys):
            raise ValueError("AUTOMATION_KEY_INVENTORY_DUPLICATE")
        return self


# Capture only facts about the configured automation identity, not a selected active credential.
class AutomationKeyCapture(Contract):
    facts: AutomationKeyFacts


# Existing attempt/connection fences select one exact automation user, never an arbitrary user ID.
class InspectAutomationKeys(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget

    # The recovery identity and cross-workspace commands cannot be used to enumerate other keys.
    @model_validator(mode="after")
    def automation_only(self):
        if (
            self.target.purpose != "automation"
            or self.context.workspace_id != self.target.workspace_id
        ):
            raise ValueError("AUTOMATION_KEY_SCOPE_INVALID")
        return self


# Actual returned subject identity stays independent of expected command fields.
class AutomationKeyObservation(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    captured_at: UtcInstant
    facts: AutomationKeyFacts


# A known zero-key result requires the same complete authorized read as a populated result.
class AutomationKeyCheck(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    checked_at: UtcInstant
    state: Literal["known", "unavailable"]
    keys: Annotated[tuple[ObservedAutomationKey, ...], Field(max_length=16)] = ()

    # Unknown reads cannot expose partial rows as if they were complete; target remains exact.
    @model_validator(mode="after")
    def qualified(self):
        InspectAutomationKeys(context=self.context, target=self.target)
        if self.state == "unavailable" and self.keys:
            raise ValueError("AUTOMATION_KEY_UNQUALIFIED_ROWS")
        if len({key.provider_key_id for key in self.keys}) != len(self.keys) or len(
            {key.fingerprint for key in self.keys}
        ) != len(self.keys):
            raise ValueError("AUTOMATION_KEY_INVENTORY_DUPLICATE")
        return self


# Real adapters list every page for the exact verified user and normalize public facts.
class AutomationKeyProvider(Protocol):
    # Read only; enumeration must not create keys, select credentials or resolve private material.
    def inspect_automation_keys(
        self, command: InspectAutomationKeys
    ) -> AutomationKeyObservation: ...


# Validate independent identity, coverage and read time before publishing safe results.
class AutomationKeyInspection:
    # Explicit composition selects one provider; no real/simulated fallback exists.
    def __init__(self, provider: AutomationKeyProvider, clock):
        self.provider, self.clock = provider, clock

    # Future key dates are retained as facts with unknown age, not turned into a fresh lease.
    def inspect(self, command):
        command = InspectAutomationKeys.model_validate(command)
        started = self.clock()
        observed = AutomationKeyObservation.model_validate(
            self.provider.inspect_automation_keys(command)
        )
        finished = self.clock()
        facts, target = observed.facts, command.target
        actual = facts.user
        qualified = (
            observed.context == command.context
            and observed.target == target
            and started <= observed.captured_at <= finished <= started + timedelta(seconds=30)
            and facts.authorized
            and facts.complete
            and facts.supported
            and actual.domain_ocid == target.domain_ocid
            and actual.scim_resource_id == target.scim_resource_id
            and actual.provider_ocid == target.provider_ocid
            and actual.user_name == target.user_name
        )
        return AutomationKeyCheck(
            context=command.context,
            target=target,
            checked_at=finished,
            state="known" if qualified else "unavailable",
            keys=facts.keys if qualified else (),
        )


# Age is observational; these states do not establish signer enrollment or compliance.
def key_age(key, at):
    if key.state == "inactive":
        return "inactive", None
    if key.state != "active" or key.created_at is None or key.created_at > at:
        return "unknown", None
    due = key.created_at + MAXIMUM_AGE
    return (
        "overdue" if at >= due else "due_soon" if at >= due - PREPARE_LEAD else "within_limit"
    ), due
