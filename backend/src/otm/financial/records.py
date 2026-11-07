"""Validate stored context/snapshot hashes and bound current reads to one record per source."""

import json
from decimal import Decimal

from sqlalchemy import and_, or_, select

from otm.financial.context import failure_source, target_source
from otm.financial.contracts import CostSnapshot, CostTarget
from otm.operations.contracts import canonical_hash
from otm.storage.tables import financial_collection, financial_observation


# Persisted identity/hash mismatches fail closed rather than reporting money for another child.
def decode_collection(row):
    target = CostTarget.model_validate_json(json.dumps(row["context"]))
    if (
        canonical_hash(row["context"]) != row["context_hash"]
        or target_source(target) != row["source_hash"]
        or failure_source(target) != row["failure_scope_hash"]
        or target.configuration.tenancy_id != row["tenancy_id"]
    ):
        raise ValueError("INVALID_COST_CONTEXT")
    return target


# Queryable money columns must exactly match the immutable same-response JSON evidence.
def decode_snapshot(row):
    snapshot = CostSnapshot.model_validate_json(json.dumps(row["snapshot"]))
    target = CostTarget.model_validate_json(json.dumps(row["collection_context"]))
    if (
        canonical_hash(row["collection_context"]) != row["context_hash"]
        or target_source(target) != row["source_hash"]
        or target.configuration.tenancy_id != row["tenancy_id"]
        or snapshot.budget_ocid != target.budget_ocid
        or snapshot.profile_hash != canonical_hash(target.profile.model_dump(mode="json"))
    ):
        raise ValueError("INVALID_COST_SOURCE")
    if (
        canonical_hash(row["snapshot"]) != row["snapshot_hash"]
        or snapshot.budget_ocid != row["budget_ocid"]
        or snapshot.retrieved_at != row["captured_at"]
        or snapshot.computed_at != row["time_spend_computed"]
        or snapshot.period_start != row["period_start"]
        or snapshot.period_end != row["period_end"]
        or snapshot.currency != row["currency"]
        or any(
            (Decimal(value) if value is not None else None) != row[column]
            for value, column in [
                (snapshot.budget, "observed_budget_amount"),
                (snapshot.actual, "actual_spend"),
                (snapshot.forecast, "forecasted_spend"),
            ]
        )
    ):
        raise ValueError("INVALID_COST_SNAPSHOT")
    return snapshot


# Match the billing subject; registry revision fences execution rather than data identity.
# Original hashes still validate. Baseline/configuration, authority and full profile stay exact.
def compatible_sources(table, sources):
    return or_(
        *(
            and_(
                table.c.tenancy_id == identifier,
                table.c.context["profile"] == context["profile"],
                table.c.context.contains(
                    {
                        "configuration": {
                            "tenancy_id": context["tenancy_id"],
                            "tenancy_ocid": context["tenancy_ocid"],
                            "parent_tenancy_ocid": context["parent"],
                            "organization_id": context["organization"],
                            "baseline_id": context["baseline_id"],
                            "configuration_id": context["configuration_id"],
                            "policy_revision": context["policy_revision"],
                        },
                        "source_access_binding_id": context["access_binding_id"],
                        "budget_ocid": context["budget_ocid"],
                    }
                ),
            )
            for identifier, context in sources.items()
        )
    )


# Select in SQL before pagination, using current source keys and at most one coherent fact per
# child.
def current_records(connection, workspace, sources):
    if not sources:
        return {}, {}
    history = financial_collection.alias("cost_history")
    # A new queued request is not recovery. Select the latest meaningful acquisition outcome,
    # ignoring malformed/no-observation success and preserving failure through pending requests.
    normalized = (
        select(financial_observation.c.id)
        .where(
            financial_observation.c.workspace_id == history.c.workspace_id,
            financial_observation.c.collection_id == history.c.id,
        )
        .exists()
    )
    outcome = (
        select(history.c.safe_code)
        .where(
            history.c.workspace_id == financial_collection.c.workspace_id,
            history.c.tenancy_id == financial_collection.c.tenancy_id,
            compatible_sources(history, sources),
            (
                history.c.safe_code.in_(
                    ("COST_READ_UNAVAILABLE", "COST_RETRIES_EXHAUSTED", "COST_SOURCE_UNQUALIFIED")
                )
                | normalized
            ),
        )
        .order_by(history.c.updated_at.desc(), history.c.id.desc())
        .limit(1)
        .correlate(financial_collection)
        .scalar_subquery()
    )
    heads = (
        connection.execute(
            select(financial_collection, outcome.label("continuing_outcome"))
            .where(
                financial_collection.c.workspace_id == workspace,
                compatible_sources(financial_collection, sources),
            )
            .distinct(financial_collection.c.tenancy_id)
            .order_by(
                financial_collection.c.tenancy_id,
                financial_collection.c.created_at.desc(),
                financial_collection.c.id.desc(),
            )
        )
        .mappings()
        .all()
    )
    query = (
        select(financial_observation, financial_collection.c.context.label("collection_context"))
        .join(
            financial_collection,
            and_(
                financial_collection.c.workspace_id == financial_observation.c.workspace_id,
                financial_collection.c.id == financial_observation.c.collection_id,
                financial_collection.c.source_hash == financial_observation.c.source_hash,
                financial_collection.c.context_hash == financial_observation.c.context_hash,
                financial_collection.c.tenancy_id == financial_observation.c.tenancy_id,
            ),
        )
        .where(
            financial_observation.c.workspace_id == workspace,
            compatible_sources(financial_collection, sources),
        )
    )
    observations = (
        connection.execute(
            query.distinct(financial_observation.c.tenancy_id).order_by(
                financial_observation.c.tenancy_id,
                (financial_observation.c.snapshot["source_state"].astext == "qualified").desc(),
                financial_observation.c.time_spend_computed.desc().nulls_last(),
                financial_observation.c.captured_at.desc(),
                financial_observation.c.id.desc(),
            )
        )
        .mappings()
        .all()
    )
    for row in heads:
        decode_collection(row)
    return (
        {row["tenancy_id"]: (row, decode_snapshot(row)) for row in observations},
        {row["tenancy_id"]: row for row in heads},
    )
