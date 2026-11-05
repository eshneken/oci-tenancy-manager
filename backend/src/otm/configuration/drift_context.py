"""Freeze assigned configuration and qualified local bindings without selecting newer baselines."""

from otm.configuration.drift_contracts import CheckTarget
from otm.configuration.observations import binding_inventory
from otm.configuration.override_contracts import (
    OverrideValues,
    configuration_hash,
    effective_content,
)
from otm.configuration.revisions import configuration_is_verified, load_configuration
from otm.configuration.service import published_baseline
from otm.operations.contracts import canonical_hash
from otm.providers.configuration import desired_objects


# Scope never comes from display names or a browser-supplied object identity.
def registered_child(row, policy):
    return bool(
        policy
        and row["provider_mode"] == "simulated"
        and row["organization_id"] == policy.organization_id
        and row["parent_tenancy_ocid"] == policy.parent_tenancy_ocid
        and row["tenancy_ocid"] != policy.parent_tenancy_ocid
        and row["tenancy_ocid"].startswith("ocid1.tenancy.oc1..otmsim")
    )


# An assignment fence ignores mutable observed values but includes every actual desired-
# generation fact.
def same_assignment(target, row, policy):
    return bool(
        row
        and registered_child(row, policy)
        and row["status"] == "active"
        and (
            target.tenancy_id,
            target.tenancy_ocid,
            target.parent_tenancy_ocid,
            target.organization_id,
            target.revision,
            target.baseline_id,
            target.configuration_id,
            target.policy_revision,
        )
        == (
            row["id"],
            row["tenancy_ocid"],
            row["parent_tenancy_ocid"],
            row["organization_id"],
            row["revision"],
            row["baseline_version_id"],
            row.get("desired_configuration_id"),
            policy.policy_revision,
        )
    )


# Previously written raw local bindings remain compatible; absent identities are never
# reconstructed.
def capture_target(connection, workspace, row, policy):
    baseline = (
        published_baseline(connection, workspace, row["baseline_version_id"])
        if row["baseline_version_id"]
        else None
    )
    configuration = load_configuration(
        connection, workspace, row["id"], row.get("desired_configuration_id")
    )
    values = (
        OverrideValues.model_validate(
            configuration.model_dump(include=set(OverrideValues.model_fields))
        )
        if configuration
        else OverrideValues()
    )
    if configuration and (baseline is None or configuration.baseline_version_id != baseline.id):
        raise ValueError("ASSIGNED_CONFIGURATION_CHANGED")
    bindings = binding_inventory(row["configuration_observation"])
    target = CheckTarget(
        tenancy_id=row["id"],
        tenancy_name=row["name"],
        tenancy_ocid=row["tenancy_ocid"],
        parent_tenancy_ocid=row["parent_tenancy_ocid"],
        organization_id=row["organization_id"],
        revision=row["revision"],
        policy_revision=policy.policy_revision,
        baseline_id=baseline.id if baseline else None,
        baseline_hash=baseline.content_hash if baseline else None,
        configuration_id=row.get("desired_configuration_id"),
        effective_hash=configuration_hash(baseline, values) if baseline else None,
        overrides=values,
        bindings=bindings,
        bindings_hash=canonical_hash(bindings),
        qualified=False,
    )
    desired = expected_objects(connection, workspace, target)
    # Validate the qualified local allocator against ACTUAL retained identities. Never fill gaps
    # from that allocator or infer a missing binding from a desired name/hash.
    qualified = bool(
        baseline
        and configuration_is_verified(row, baseline)
        and row.get("configuration_verified_at")
        and len(bindings) == 4
        and all(bindings.get(key) == item.object_ocid for key, item in desired.items())
    )
    return target.model_copy(update={"qualified": qualified})


# Pure expected content comes from the immutable assigned version plus accepted overrides only.
def expected_objects(connection, workspace, target):
    if target.baseline_id is None:
        return None
    baseline = published_baseline(connection, workspace, target.baseline_id)
    if (
        baseline.content_hash != target.baseline_hash
        or configuration_hash(baseline, target.overrides) != target.effective_hash
    ):
        raise ValueError("IMMUTABLE_CONFIGURATION_CHANGED")
    effective = baseline.model_copy(
        update={"content": effective_content(baseline, target.overrides)}
    )
    return desired_objects(target, effective)
