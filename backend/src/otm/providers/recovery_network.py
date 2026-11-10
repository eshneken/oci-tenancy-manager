"""Conditional replacement of one owned recovery perimeter; no rule or identity mutation."""

from datetime import timedelta
from typing import Literal, Protocol

from otm.contracts import Contract, Text, UtcInstant
from otm.providers.inspection import ProviderContractError
from otm.providers.recovery_console import (
    ConsolePolicyFacts,
    InspectRecoveryConsole,
    RecoveryConsoleCapture,
    evaluate_console,
    observed_fingerprint,
)


# Authority is independently scoped to one conditional write, never inferred from user presence.
class RecoveryNetworkAuthority(Contract):
    command: InspectRecoveryConsole
    captured_at: UtcInstant
    facts: ConsolePolicyFacts
    can_replace_perimeter: bool
    conditional_update: bool
    owns_perimeter: bool
    # Opaque conditional-update version from the provider, never supplied by the browser.
    compare_token: Text


# The same immutable command and observed version must reach conditional update and readback.
class RepairRecoveryNetwork(Contract):
    authority: RecoveryNetworkAuthority


# A known result includes independently read actual facts; unknown effects never imply success.
class RecoveryNetworkOutcome(Contract):
    effect: Literal["none", "known", "unknown"]
    capture: RecoveryConsoleCapture | None = None


# Real adapters must qualify the conditional perimeter operation before implementing this contract.
class RecoveryNetworkProvider(Protocol):
    # Read current effective policy and independently prove authority for this exact perimeter.
    def inspect_network_authority(
        self, command: InspectRecoveryConsole
    ) -> RecoveryNetworkAuthority: ...

    # Compare the retained observed version, replace only the perimeter, then independently read it.
    def replace_network(self, command: RepairRecoveryNetwork) -> RecoveryNetworkOutcome: ...


# Every caller shares conservative eligibility; broad or broken policies are never repaired here.
def require_network_repair(authority, command):
    authority = RecoveryNetworkAuthority.model_validate(authority)
    state = evaluate_console(command, authority.facts)
    if (
        authority.command != command
        or not authority.can_replace_perimeter
        or not authority.conditional_update
        or not authority.owns_perimeter
        or state.mfa_exemption != "verified"
        or state.network_boundary != "drift"
    ):
        raise ProviderContractError("RECOVERY_NETWORK_REPAIR_BLOCKED")
    return authority


# Adapters cannot certify writes by returning desired values or changing unrelated policy facts.
class RecoveryNetworkRepair:
    # Composition selects the provider and aware UTC clock; construction performs no I/O.
    def __init__(self, provider: RecoveryNetworkProvider, clock):
        self.provider, self.clock = provider, clock

    # Fresh exact authority is required even when a prior UI check already confirmed drift.
    def preview(self, command):
        command = InspectRecoveryConsole.model_validate(command)
        try:
            started = self.clock()
            result = require_network_repair(
                self.provider.inspect_network_authority(command), command
            )
            ended = self.clock()
            if not started <= result.captured_at <= ended or ended - started > timedelta(
                seconds=30
            ):
                raise ValueError("RECOVERY_NETWORK_AUTHORITY_EXPIRED")
            return result
        except Exception:
            raise ProviderContractError("RECOVERY_NETWORK_REPAIR_BLOCKED") from None

    # Recheck authority before a conditional write; unexpected output remains an unknown effect.
    def apply(self, authority, *, before_write=None):
        command = authority.command
        try:
            current = self.preview(command)
        except ProviderContractError:
            return RecoveryNetworkOutcome(effect="none")
        if (
            observed_fingerprint(current.facts) != observed_fingerprint(authority.facts)
            or current.compare_token != authority.compare_token
        ):
            return RecoveryNetworkOutcome(effect="none")
        if before_write is not None and not before_write():
            return RecoveryNetworkOutcome(effect="none")
        try:
            outcome = RecoveryNetworkOutcome.model_validate(
                self.provider.replace_network(RepairRecoveryNetwork(authority=current))
            )
            if outcome.effect != "known":
                return RecoveryNetworkOutcome(effect=outcome.effect)
            capture = outcome.capture
            started = self.clock()
            readback = RecoveryNetworkAuthority.model_validate(
                self.provider.inspect_network_authority(command)
            )
            ended = self.clock()
            if (
                capture is None
                or readback.command != command
                or not started <= readback.captured_at <= ended
                or ended - started > timedelta(seconds=30)
                or capture.facts != readback.facts
                or capture.binding != command.binding
                or capture.scim_resource_id != command.target.scim_resource_id
                or capture.facts.model_dump(exclude={"perimeter"})
                != current.facts.model_dump(exclude={"perimeter"})
                or evaluate_console(command, capture.facts).state != "verified"
            ):
                raise ValueError("RECOVERY_NETWORK_READBACK_INVALID")
            return outcome
        except Exception:
            # Once a write may have been sent, an exception cannot be relabeled safe to retry.
            return RecoveryNetworkOutcome(effect="unknown")
