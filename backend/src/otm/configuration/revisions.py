"""Immutable accepted configuration revisions and effective-content verification."""

import json
from uuid import uuid4

from sqlalchemy import select

from otm.configuration.override_contracts import (
    OverrideConflict,
    TenancyConfiguration,
    configuration_hash,
)
from otm.configuration.service import published_baseline
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import tenancy_configuration


# SQL values are explicit typed columns; labels and provider observations never supply intent.
def configuration_view(row, baseline):
    values = {key: row[key] for key in TenancyConfiguration.model_fields}
    if values["monthly_budget_override_amount"] is not None:
        values["monthly_budget_override_amount"] = str(values["monthly_budget_override_amount"])
    values["created_at"] = values["created_at"].isoformat()
    model = TenancyConfiguration.model_validate_json(json.dumps(values, default=str))
    if model.baseline_version_id != baseline.id or model.effective_hash != configuration_hash(
        baseline, model
    ):
        raise ValueError("INVALID_CONFIGURATION_EVIDENCE")
    return model


# A missing pointer is explicitly legacy inheritance; a foreign/missing nonnull pointer fails
# closed.
def load_configuration(connection, workspace, tenant, identifier):
    if identifier is None:
        return None
    row = (
        connection.execute(
            select(tenancy_configuration).where(
                tenancy_configuration.c.workspace_id == workspace,
                tenancy_configuration.c.tenancy_id == tenant,
                tenancy_configuration.c.id == identifier,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise OrganizationConflict("CONFIGURATION_CONTEXT_UNAVAILABLE")
    baseline = published_baseline(connection, workspace, row["baseline_version_id"])
    return configuration_view(row, baseline)


# Full-list review applies only to overridden categories whose assigned baseline content changed.
def override_conflict(connection, workspace, row, latest, values):
    if not row.get("baseline_version_id"):
        return None
    old = published_baseline(connection, workspace, row["baseline_version_id"])
    policy = (
        values.policy_override_statements is not None
        and old.content.policy_statements != latest.content.policy_statements
    )
    quota = (
        values.quota_override_statements is not None
        and old.content.quota_statements != latest.content.quota_statements
    )
    if values.monthly_budget_override_amount is not None and (
        old.content.budget_currency,
        old.content.budget_period,
    ) != (latest.content.budget_currency, latest.content.budget_period):
        raise OrganizationConflict("CONFIGURATION_CONTEXT_UNAVAILABLE")
    return (
        OverrideConflict(
            tenancy_id=row["id"],
            tenancy_name=row["name"],
            old_baseline=old,
            overrides=values,
            policy_review=policy,
            quota_review=quota,
        )
        if policy or quota
        else None
    )


# Create the next same-tenancy revision only inside atomic operation admission.
def accept_configuration(connection, workspace, row, baseline, values, operation_id, actor, at):
    previous = load_configuration(
        connection, workspace, row["id"], row.get("desired_configuration_id")
    )
    model = TenancyConfiguration(
        **values.model_dump(),
        id=uuid4(),
        tenancy_id=row["id"],
        baseline_version_id=baseline.id,
        revision_number=previous.revision_number + 1 if previous else 1,
        previous_id=previous.id if previous else None,
        operation_id=operation_id,
        created_by=actor,
        created_at=at,
        effective_hash=configuration_hash(baseline, values),
    )
    payload = model.model_dump()
    connection.execute(tenancy_configuration.insert().values(workspace_id=workspace, **payload))
    return model


# Match accepted overrides independently of matching baseline IDs; same-baseline edits still
# need work.
def configuration_is_verified(row, baseline):
    return (
        row.get("verified_baseline_version_id") == baseline.id
        and row["baseline_version_id"] == baseline.id
        and row.get("desired_configuration_id") == row.get("last_verified_configuration_id")
    )
