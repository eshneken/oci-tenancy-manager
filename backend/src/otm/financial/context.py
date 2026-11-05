"""Exact registered-budget source identity shared by admission, publication and dashboard reads."""

from otm.configuration.drift_context import registered_child
from otm.configuration.observations import binding_inventory
from otm.operations.contracts import canonical_hash


# Names and observed amounts are not source authority; this key remains stable across month
# rollover.
def source_context(row, policy, profile):
    if not registered_child(row, policy) or row["status"] != "active":
        return None
    budget = binding_inventory(row["configuration_observation"]).get("budget")
    if budget is None:
        return None
    return {
        "tenancy_id": str(row["id"]),
        "tenancy_ocid": row["tenancy_ocid"],
        "parent": row["parent_tenancy_ocid"],
        "organization": row["organization_id"],
        "revision": row["revision"],
        "baseline_id": str(row["baseline_version_id"]) if row["baseline_version_id"] else None,
        "configuration_id": str(row.get("desired_configuration_id"))
        if row.get("desired_configuration_id")
        else None,
        "policy_revision": str(policy.policy_revision),
        "access_binding_id": str(policy.access_binding_id),
        "budget_ocid": budget,
        "profile": profile.model_dump(mode="json"),
    }


# Reconstruct the same stable source from an immutable captured target without database queries.
def target_source(target):
    c = target.configuration
    return canonical_hash(
        {
            "tenancy_id": str(c.tenancy_id),
            "tenancy_ocid": c.tenancy_ocid,
            "parent": c.parent_tenancy_ocid,
            "organization": c.organization_id,
            "revision": c.revision,
            "baseline_id": str(c.baseline_id) if c.baseline_id else None,
            "configuration_id": str(c.configuration_id) if c.configuration_id else None,
            "policy_revision": str(c.policy_revision),
            "access_binding_id": str(target.source_access_binding_id),
            "budget_ocid": target.budget_ocid,
            "profile": target.profile.model_dump(mode="json"),
        }
    )


# Failure episodes span baseline/configuration edits, age thresholds and retry changes; only a
# changed child/budget/access/provider profile begins an independent acquisition source.
def failure_source(target):
    c = target.configuration
    return canonical_hash(
        {
            "tenancy_id": str(c.tenancy_id),
            "tenancy_ocid": c.tenancy_ocid,
            "parent": c.parent_tenancy_ocid,
            "organization": c.organization_id,
            "access_binding_id": str(target.source_access_binding_id),
            "budget_ocid": target.budget_ocid,
            "profile": target.profile.profile,
        }
    )


# Delivery checks the stable current source, not obsolete baseline/retry metadata from admission.
def current_failure_source(row, policy, profile):
    source = source_context(row, policy, profile)
    if source is None:
        return None
    return canonical_hash(
        {
            key: source[key]
            for key in (
                "tenancy_id",
                "tenancy_ocid",
                "parent",
                "organization",
                "access_binding_id",
                "budget_ocid",
            )
        }
        | {"profile": profile.profile}
    )
