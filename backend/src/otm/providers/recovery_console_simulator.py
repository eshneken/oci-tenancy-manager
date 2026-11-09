"""Explicit in-memory console-policy fixtures; never fabricate applied state from desired CIDRs."""

from otm.providers.recovery_console import (
    ConsolePolicyFacts,
    ConsolePolicyObservation,
    InspectRecoveryConsole,
)


# Tests configure producer facts independently; this adapter has no live OCI or fallback path.
class SimulatedRecoveryConsoleProvider:
    # Exact source target/context and UTC clock are host-selected, not supplied by a browser.
    def __init__(self, target, context, facts: ConsolePolicyFacts, clock):
        self.target, self.context, self.clock = target, context, clock
        self.facts = ConsolePolicyFacts.model_validate(facts)

    # A changed desired policy is compared with these retained actual fixtures, never copied over.
    def inspect_recovery_console(self, command: InspectRecoveryConsole):
        if command.target != self.target or command.context != self.context:
            raise ValueError("SIMULATED_RECOVERY_CONSOLE_SCOPE_MISMATCH")
        return ConsolePolicyObservation(
            context=self.context, target=self.target, captured_at=self.clock(), facts=self.facts
        )


# Simulated creation configures an isolated exact-user rule pair; existing rules remain untouched.
def configured_console_capture(domain, scim_id, suffix, policy):
    from otm.providers.recovery_console import RecoveryConsoleBinding, RecoveryConsoleCapture

    binding = RecoveryConsoleBinding(
        application_id="console-" + suffix,
        policy_id="policy-" + suffix,
        perimeter_id="perimeter-" + suffix,
        group_id="recovery-only-" + suffix,
        allow_rule_id="recovery-inside-" + suffix,
        deny_rule_id="recovery-outside-" + suffix,
    )
    common = dict(enabled=True, subjects=(scim_id,), group_id=binding.group_id, supported=True)
    facts = ConsolePolicyFacts(
        domain_ocid=domain,
        application_id=binding.application_id,
        policy_id=binding.policy_id,
        assigned=True,
        enabled=True,
        authorized=True,
        complete=True,
        perimeter_id=binding.perimeter_id,
        perimeter=policy,
        rules=(
            dict(
                **common,
                id=binding.allow_rule_id,
                effect="allow",
                mfa="exempt",
                perimeter_id=binding.perimeter_id,
            ),
            dict(
                **common,
                id=binding.deny_rule_id,
                effect="deny",
                mfa="not_applicable",
                perimeter_id=None,
            ),
            dict(
                id="ordinary-users-" + suffix,
                enabled=True,
                subjects=None,
                effect="allow",
                mfa="required",
                perimeter_id=None,
                group_id=None,
                supported=True,
            ),
        ),
    )
    return RecoveryConsoleCapture(binding=binding, scim_resource_id=scim_id, facts=facts)


# Rehydrate only original producer fixtures; a new desired list cannot overwrite observed facts.
def simulated_console_inspection(command, source, clock):
    from otm.providers.recovery_console import RecoveryConsoleInspection

    capture = source.recovery_console
    if capture is None or (
        source.workspace_id,
        source.tenancy_ocid,
        source.domain_ocid,
        source.recovery.scim_resource_id,
    ) != (
        command.target.workspace_id,
        command.target.tenancy_ocid,
        command.target.domain_ocid,
        command.target.scim_resource_id,
    ):
        raise ValueError("SIMULATED_RECOVERY_CONSOLE_SOURCE_UNAVAILABLE")
    if capture.binding != command.binding:
        raise ValueError("SIMULATED_RECOVERY_CONSOLE_SOURCE_UNAVAILABLE")
    return RecoveryConsoleInspection(
        SimulatedRecoveryConsoleProvider(command.target, command.context, capture.facts, clock),
        clock,
    )
