"""Read-only comparison of exact simulator bindings and assigned authored configuration."""

import json

from otm.configuration.drift_contracts import ConfigurationObjectCheck
from otm.configuration.observation_contracts import ManagedObservation
from otm.configuration.rollout_contracts import ManagedConfigurationObject
from otm.operations.contracts import canonical_hash
from otm.providers.configuration import CATEGORIES


# Legacy app-written records remain readable without rewriting them or inventing missing objects.
def decode_observation(value):
    if isinstance(value, dict) and value.get("contract_version") == "managed-observation-1":
        return ManagedObservation.model_validate_json(json.dumps(value))
    item = ManagedConfigurationObject.model_validate_json(json.dumps(value))
    return ManagedObservation(binding=item, observed=item, state="present", complete=True)


# Capture only retained registered identities; missing/malformed inventory is never synthesized.
def binding_inventory(objects):
    inventory = {}
    for category in CATEGORIES:
        try:
            value = decode_observation((objects or {})[category])
            if value.binding.category != category:
                raise ValueError("BINDING_CATEGORY_CHANGED")
            inventory[category] = value.binding.object_ocid
        except (ValueError, KeyError, TypeError):
            continue
    return inventory


# Unavailable/context failures carry expected data only, never a fabricated observed payload.
def unavailable_results(target, desired, code="READ_UNAVAILABLE"):
    return tuple(
        ConfigurationObjectCheck(
            category=category,
            state="unavailable",
            safe_code=code,
            complete=False,
            binding_ocid=target.bindings.get(category),
            expected=desired[category].payload if desired else None,
            observed=None,
        )
        for category in CATEGORIES
    )


# Read all four exact bindings; incomplete bundles cannot confirm or clear configuration drift.
def inspect_configuration(target, desired, facade, stored):
    if not target.qualified:
        return unavailable_results(target, desired, "UNBOUND_CONFIGURATION"), "unavailable"
    results = []
    for category in CATEGORIES:
        expected = desired[category]
        values = dict(
            category=category,
            binding_ocid=target.bindings[category],
            expected=expected.payload,
            observed=None,
        )
        try:
            observed = facade.observe(target, category, (stored or {}).get(category))
            observed = ManagedObservation.model_validate_json(observed.model_dump_json())
            if (
                observed.binding.object_ocid != target.bindings[category]
                or observed.binding.category != category
            ):
                results.append(
                    ConfigurationObjectCheck(
                        **values, state="conflict", safe_code="BINDING_CONFLICT", complete=False
                    )
                )
                continue
            if observed.state == "unavailable":
                results.append(
                    ConfigurationObjectCheck(
                        **values, state="unavailable", safe_code="READ_UNAVAILABLE", complete=False
                    )
                )
            elif observed.state == "missing":
                results.append(
                    ConfigurationObjectCheck(
                        **values, state="missing", safe_code="MISSING", complete=True
                    )
                )
            elif (
                observed.observed.object_ocid != target.bindings[category]
                or observed.observed.category != category
            ):
                results.append(
                    ConfigurationObjectCheck(
                        **values, state="conflict", safe_code="BINDING_CONFLICT", complete=False
                    )
                )
            else:
                matching = canonical_hash(json.loads(observed.observed.payload)) == canonical_hash(
                    json.loads(expected.payload)
                )
                results.append(
                    ConfigurationObjectCheck(
                        **{**values, "observed": observed.observed.payload},
                        state="matching" if matching else "different",
                        safe_code="MATCHING" if matching else "DIFFERENT",
                        complete=True,
                    )
                )
        except Exception:
            results.append(
                ConfigurationObjectCheck(
                    **values, state="unavailable", safe_code="READ_UNAVAILABLE", complete=False
                )
            )
    state = (
        "unavailable"
        if any(not item.complete for item in results)
        else (
            "drifted"
            if any(item.state in {"missing", "different"} for item in results)
            else "matching"
        )
    )
    return tuple(results), state
