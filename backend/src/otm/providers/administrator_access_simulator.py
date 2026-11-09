"""Independent retained simulation fixtures for exact administrator assignment readback."""

from otm.providers.administrator_access import (
    AdministratorAccessInspection,
    AdministratorBinding,
    AdministratorCapture,
    AdministratorFacts,
    AdministratorObservation,
)


# Fixture reads return the original captured facts, not expected values copied from a command.
class SimulatedAdministratorAccessProvider:
    # A test or setup producer supplies explicit independent scoped facts.
    def __init__(self, facts, clock):
        self.facts, self.clock = facts, clock

    # Validate actual fixture scope against the requested subject and resources.
    def inspect_administrator_access(self, command):
        return AdministratorObservation(
            context=command.context,
            target=command.target,
            captured_at=self.clock(),
            facts=self.facts,
        )


# Setup fixtures represent the built-in group and domain role separately from account existence.
def configured_administrator_capture(domain, user, suffix):
    binding = AdministratorBinding(
        domain_ocid=domain,
        scim_resource_id=user,
        group_id="administrators-" + suffix,
        application_id="domain-admin-app-" + suffix,
        role_id="domain-admin-role-" + suffix,
    )
    return AdministratorCapture(
        binding=binding,
        facts=AdministratorFacts(
            binding=binding,
            authorized=True,
            complete=True,
            supported=True,
            builtin_group=True,
            group_enabled=True,
            role_enabled=True,
            user_enabled=True,
            group_members=(user,),
            role_users=(),
            role_groups=(binding.group_id,),
        ),
    )


# Composition rehydrates immutable producer facts; legacy evidence remains unavailable.
def simulated_administrator_inspection(command, source, clock):
    capture = source.automation_administrator
    if capture is None:
        raise ValueError("ADMINISTRATOR_CAPTURE_UNAVAILABLE")
    return AdministratorAccessInspection(
        SimulatedAdministratorAccessProvider(capture.facts, clock), clock
    )
