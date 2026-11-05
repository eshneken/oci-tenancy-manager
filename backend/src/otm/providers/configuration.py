"""Pure local managed-object simulator; no OCI client, key, credential or network fallback."""

import json
from hashlib import sha256
from typing import Protocol

from otm.configuration.rollout_contracts import ManagedConfigurationObject

CATEGORIES = ("policy", "quota", "budget", "tags")


# The actual adapter boundary separates writes and reads; confirmation alone is never evidence.
class ConfigurationFacade(Protocol):
    # Return applied object state for one exact managed logical object in a verified child.
    def apply(self, target, desired, previous): ...

    # Read a retained exact identity with explicit authorized absence/completeness evidence.
    def observe(self, target, category, stored): ...

    # Observe stored provider state independently of the desired recipe.
    def read(self, target, category, stored): ...


# Resolve one deterministic OTM object per category without touching unrelated owner resources.
def desired_objects(target, baseline):
    from otm.operations.contracts import canonical_hash

    content = baseline.content.model_dump(mode="json")
    values = {
        "policy": {"statements": content["policy_statements"]},
        "quota": {"statements": content["quota_statements"]},
        "budget": {
            "monthly_amount": content["monthly_budget_amount"],
            "currency": content["budget_currency"],
            "period": "MONTHLY",
        },
        "tags": {"namespace": "OTM", "defaults": content["tag_defaults"]},
    }
    return {
        category: ManagedConfigurationObject(
            category=category,
            object_ocid=f"ocid1.{category}.oc1..otmsim"
            + sha256((target.tenancy_ocid + ":" + category).encode()).hexdigest()[:32],
            payload=json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            payload_hash=canonical_hash(value),
        )
        for category, value in values.items()
    }


# Identities and object ownership remain fixed across simulator writes, retries and process
# restarts.
class SimulatedConfigurationFacade:
    # Trusted policy is the same parent/workspace authority used at admission and dispatch.
    def __init__(self, policy):
        self.policy = policy

    # Reject non-child or mismatched scope before any local simulated mutation.
    def require_target(self, target):
        if (
            target.parent_tenancy_ocid != self.policy.parent_tenancy_ocid
            or target.organization_id != self.policy.organization_id
            or target.tenancy_ocid == self.policy.parent_tenancy_ocid
            or not target.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
        ):
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


# Apply/readback one child while retaining partial simulator state and verified category prefixes.
def configure_target(target, baseline, facade, stored):
    objects = dict(stored or {})
    desired = desired_objects(target, baseline)
    category = None
    try:
        for category in CATEGORIES:
            from otm.configuration.observations import decode_observation

            previous = (
                decode_observation(objects[category]).binding if category in objects else None
            )
            if previous and facade.read(target, category, objects[category]) == desired[category]:
                continue
            written = facade.apply(target, desired[category], previous)
            objects[category] = written.model_dump(mode="json")
            observed = facade.read(target, category, objects[category])
            if observed != desired[category]:
                raise ValueError("CONFIGURATION_READBACK_MISMATCH")
        return objects, None
    except ValueError:
        return objects, category
