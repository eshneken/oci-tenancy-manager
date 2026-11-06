"""Guarded selected-object repair using existing operations, observations and assignment fences."""

from sqlalchemy import select

from otm.configuration.drift_context import capture_target, expected_objects
from otm.configuration.drift_records import check_history, save_check
from otm.configuration.drift_views import check_summary
from otm.configuration.observations import binding_inventory, inspect_configuration
from otm.configuration.rollout_contracts import ConfigurationPreview, ConfigurationTarget
from otm.configuration.service import published_baseline
from otm.operations.contracts import canonical_hash
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import tenancy


# Preview never chooses latest or treats missing/incomplete observations as repair authorization.
def preview_repair(service, connection, workspace, identifier, categories):
    row = (
        connection.execute(
            select(tenancy).where(tenancy.c.workspace_id == workspace, tenancy.c.id == identifier)
        )
        .mappings()
        .one_or_none()
    )
    policy = service.available_policy()
    if row is None:
        raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
    if (
        not policy
        or policy.workspace_id != workspace
        or not service.repair_facade
        or service.repair_facade.policy != policy
        or row["status"] != "active"
        or row["operation_id"]
        or not row["baseline_version_id"]
    ):
        raise OrganizationConflict("CONFIGURATION_REPAIR_BLOCKED")
    baseline = published_baseline(connection, workspace, row["baseline_version_id"])
    context = capture_target(connection, workspace, row, policy)
    history = check_history(connection, workspace)
    summary = check_summary(
        row,
        history,
        {},
        policy,
        baseline,
        service.store.clock(),
        include_payload=True,
    )
    if not context.qualified or summary.stale or summary.state != "drifted":
        raise OrganizationConflict("CONFIGURATION_REPAIR_BLOCKED")
    confirmed = {
        item.category for item in summary.categories if item.state in {"missing", "different"}
    }
    desired = expected_objects(connection, workspace, context)
    results, state = inspect_configuration(
        context, desired, service.repair_facade, row["configuration_observation"]
    )
    current = {item.category for item in results if item.state in {"missing", "different"}}
    if state != "drifted" or not set(categories) <= confirmed & current:
        raise OrganizationConflict("CONFIGURATION_REPAIR_BLOCKED")
    target = ConfigurationTarget(
        tenancy_id=row["id"],
        name=row["name"],
        tenancy_ocid=row["tenancy_ocid"],
        parent_tenancy_ocid=row["parent_tenancy_ocid"],
        organization_id=row["organization_id"],
        revision=row["revision"],
        source_baseline_id=baseline.id,
        source_verified_id=row["verified_baseline_version_id"],
        source_configuration_id=row.get("desired_configuration_id"),
        source_verified_configuration_id=row.get("last_verified_configuration_id"),
        overrides=context.overrides,
        repair_categories=tuple(categories),
        repair_bindings=context.bindings,
        repair_context_hash=canonical_hash(context.model_dump(mode="json")),
        repair_observation_hash=canonical_hash(row["configuration_observation"]),
        repair_check_id=next(
            stored["id"]
            for stored, ctx, evidence in history
            if ctx == context and evidence.state == "drifted"
        ),
    )
    digest = canonical_hash(
        {
            "repair": target.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "evidence": summary.model_dump(mode="json"),
            "observations": row["configuration_observation"],
        }
    )
    return ConfigurationPreview(
        repair_expected={
            item.category: item.expected for item in results if item.category in categories
        },
        repair_observed={
            item.category: item.observed for item in results if item.category in categories
        },
        baseline=baseline,
        tenancy_id=identifier,
        ready_count=1,
        pending_count=0,
        blockers=(),
        preview_hash=digest,
    ), (target,)


# Write selected retained objects only; independently observe all categories afterward.
def execute_repair(connection, workspace, row, target, baseline, facade, *, require_original=True):
    from otm.configuration.override_contracts import effective_content
    from otm.providers.configuration import desired_objects

    context = capture_target(connection, workspace, row, facade.policy)
    objects = dict(row["configuration_observation"] or {})
    if (
        not context.qualified
        or binding_inventory(objects) != target.repair_bindings
        or canonical_hash(context.model_dump(mode="json")) != target.repair_context_hash
        or (require_original and canonical_hash(objects) != target.repair_observation_hash)
    ):
        raise ValueError("REPAIR_BINDINGS_CHANGED")
    desired = desired_objects(
        target,
        baseline.model_copy(
            update={
                "content": effective_content(baseline, target.configuration or target.overrides)
            }
        ),
    )
    before, state = inspect_configuration(context, desired, facade, objects)
    if state == "unavailable":
        return objects, target.repair_categories[0], before
    failed = None
    for category in target.repair_categories:
        try:
            previous = desired[category].model_copy(
                update={"object_ocid": target.repair_bindings[category]}
            )
            written = facade.apply(target, desired[category], previous)
            objects[category] = written.model_dump(mode="json")
            if facade.read(target, category, objects[category]) != desired[category]:
                raise ValueError("REPAIR_READBACK_MISMATCH")
        except ValueError:
            failed = category
            break
    results, _ = inspect_configuration(context, desired, facade, objects)
    for item in results:
        if not item.complete or (
            item.category in target.repair_categories and item.state != "matching"
        ):
            failed = failed or item.category
    return objects, failed, results


# Seal post-write observations in the existing history so acceptance/failure cannot clear drift.
def record_repair_check(connection, operation, previous, policy, results, at):
    current = (
        connection.execute(
            select(tenancy).where(
                tenancy.c.workspace_id == previous["workspace_id"], tenancy.c.id == previous["id"]
            )
        )
        .mappings()
        .one()
    )
    context = capture_target(connection, previous["workspace_id"], current, policy)
    state = (
        "unavailable"
        if any(not item.complete for item in results)
        else (
            "drifted"
            if any(item.state in {"missing", "different"} for item in results)
            else "matching"
        )
    )
    save_check(connection, operation, context, results, state, at, at)
