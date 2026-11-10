"""Explicit conditional perimeter fixture, independent of desired configuration and live OCI."""

from otm.providers.inspection import ProviderContractError
from otm.providers.recovery_console import RecoveryConsoleCapture, observed_fingerprint
from otm.providers.recovery_network import (
    RecoveryNetworkAuthority,
    RecoveryNetworkOutcome,
    RecoveryNetworkRepair,
    require_network_repair,
)


# Retained producer facts model current state; no failed real adapter falls back to this fixture.
class SimulatedRecoveryNetworkProvider:
    # An authenticated capture, exact context and server clock are explicit composition inputs.
    def __init__(self, command, capture, clock):
        self.command, self.clock = command, clock
        self.capture = RecoveryConsoleCapture.model_validate(capture)
        if (
            self.capture.binding != command.binding
            or self.capture.scim_resource_id != command.target.scim_resource_id
            or self.capture.facts.domain_ocid != command.target.domain_ocid
            or not command.target.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
        ):
            raise ProviderContractError("SIMULATED_RECOVERY_NETWORK_SCOPE_INVALID")

    # This explicit simulated capability does not qualify any live provider permission profile.
    def inspect_network_authority(self, command):
        if command != self.command:
            raise ProviderContractError("SIMULATED_RECOVERY_NETWORK_SCOPE_INVALID")
        return RecoveryNetworkAuthority(
            command=command,
            captured_at=self.clock(),
            facts=self.capture.facts,
            can_replace_perimeter=True,
            conditional_update=True,
            owns_perimeter=True,
            compare_token=observed_fingerprint(self.capture.facts),
        )

    # Compare actual retained state before replacing only its network union; preserve every rule.
    def replace_network(self, command):
        authority = require_network_repair(command.authority, self.command)
        if observed_fingerprint(authority.facts) != observed_fingerprint(
            self.capture.facts
        ) or authority.compare_token != observed_fingerprint(self.capture.facts):
            return RecoveryNetworkOutcome(effect="none")
        self.capture = self.capture.model_copy(
            update={
                "facts": self.capture.facts.model_copy(update={"perimeter": self.command.desired})
            }
        )
        return RecoveryNetworkOutcome(effect="known", capture=self.capture)


# Local composition explicitly supplies retained source state and never seeds it from desired data.
def simulated_network_repair(command, capture, clock):
    return RecoveryNetworkRepair(SimulatedRecoveryNetworkProvider(command, capture, clock), clock)
