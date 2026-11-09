"""Managed-configuration contracts and pure recipe/scope helpers; no concrete provider imports."""

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


# Check common configured scope without assuming an SDK, credential source or synthetic identity.
def require_configuration_target(target, policy):
    if (
        target.parent_tenancy_ocid != policy.parent_tenancy_ocid
        or target.organization_id != policy.organization_id
        or target.tenancy_ocid == policy.parent_tenancy_ocid
    ):
        raise ValueError("REGISTERED_CHILD_REQUIRED")


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


# Apply/readback through the injected capability, retaining partial state and verified prefixes.
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
