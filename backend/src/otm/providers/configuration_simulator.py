"""Local managed-object simulation with exact synthetic target and binding checks."""

from otm.providers.configuration import require_configuration_target


# Identities and object ownership remain fixed across simulator writes, retries and process
# restarts.
class SimulatedConfigurationFacade:
    # Trusted policy is the same parent/workspace authority used at admission and dispatch.
    def __init__(self, policy):
        self.policy = policy

    # Reject non-child or mismatched scope before any local simulated mutation.
    def require_target(self, target):
        require_configuration_target(target, self.policy)
        if not target.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim"):
            raise ValueError("REGISTERED_CHILD_REQUIRED")

    # Only the four exact OTM logical objects can be changed; arbitrary external IDs are rejected.
    def apply(self, target, desired, previous):
        self.require_target(target)
        if previous and previous.object_ocid != desired.object_ocid:
            raise ValueError("MANAGED_BINDING_CHANGED")
        return desired

    # Read only supplied fake-cloud state; retained bindings remain independent of observations.
    def observe(self, target, category, stored):
        from otm.configuration.observations import decode_observation

        self.require_target(target)
        if stored is None:
            # No retained binding/coverage proof means unknown, never authorized absence.
            raise ValueError("UNBOUND_OBJECT")
        observed = decode_observation(stored)
        if observed.binding.category != category:
            raise ValueError("MANAGED_CATEGORY_CHANGED")
        return observed

    # Existing apply/readback paths use the same independent observation, including strict failures.
    def read(self, target, category, stored):
        result = self.observe(target, category, stored)
        if result.state != "present" or result.observed is None:
            raise ValueError("MANAGED_OBJECT_UNAVAILABLE")
        if (
            result.observed.category != category
            or result.observed.object_ocid != result.binding.object_ocid
        ):
            raise ValueError("MANAGED_BINDING_CHANGED")
        return result.observed
