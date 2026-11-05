"""Apply the frozen onboarding baseline with independent simulated object readback."""

from sqlalchemy import select, update

from otm.configuration.rollout_contracts import ConfigurationTarget
from otm.providers.configuration import configure_target
from otm.storage.tables import operation, tenancy


# Persist partial object observations for retries; verified heads advance only after all categories.
def configure_baseline(connection, row, intent, facade, at):
    registered = (
        connection.execute(
            select(tenancy).where(
                tenancy.c.workspace_id == row["workspace_id"],
                tenancy.c.id == intent.pending_tenancy_id,
            )
        )
        .mappings()
        .one()
    )
    if registered["baseline_version_id"] != intent.baseline.id:
        raise ValueError("BASELINE_PIN_CHANGED")
    target = ConfigurationTarget(
        tenancy_id=registered["id"],
        name=registered["name"],
        tenancy_ocid=registered["tenancy_ocid"],
        parent_tenancy_ocid=registered["parent_tenancy_ocid"],
        organization_id=registered["organization_id"],
        revision=registered["revision"],
        source_baseline_id=registered["baseline_version_id"],
        source_verified_id=registered["verified_baseline_version_id"],
    )
    objects, failed = configure_target(
        target,
        intent.baseline,
        facade.configuration_facade,
        registered["configuration_observation"],
    )
    connection.execute(
        update(tenancy)
        .where(tenancy.c.workspace_id == row["workspace_id"], tenancy.c.id == target.tenancy_id)
        .values(
            configuration_observation=objects,
            updated_at=at,
            **(
                {
                    "verified_baseline_version_id": intent.baseline.id,
                    "configuration_verified_at": at,
                }
                if failed is None
                else {}
            ),
        )
    )
    if objects:
        connection.execute(
            update(operation)
            .where(operation.c.workspace_id == row["workspace_id"], operation.c.id == row["id"])
            .values(effect_knowledge="known")
        )
    if failed is not None:
        raise ValueError("BASELINE_UNVERIFIED")
