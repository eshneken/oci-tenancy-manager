"""Append-only child check evidence and deterministic acquisition-ordered history reads."""

import json
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from otm.configuration.drift_contracts import CheckTarget, ConfigurationCheckEvidence
from otm.operations.contracts import canonical_hash
from otm.storage.tables import audit_event, configuration_check, operation_step


# Validate immutable audit identity/hash against each persisted check before using it as health
# data.
def decode_check(row):
    context = CheckTarget.model_validate_json(json.dumps(row["context"]))
    evidence = ConfigurationCheckEvidence.model_validate_json(json.dumps(row["audit_data"]))
    if (
        canonical_hash(row["context"]) != row["context_hash"]
        or canonical_hash(row["audit_data"]) != row["audit_hash"]
        or evidence.check_id != row["id"]
        or evidence.tenancy_id != row["tenancy_id"]
        or context.tenancy_id != row["tenancy_id"]
        or evidence.context_hash != row["context_hash"]
        or evidence.state != row["state"]
        or evidence.checked_at != row["checked_at"]
        or [item.model_dump(mode="json") for item in evidence.results] != row["results"]
    ):
        raise ValueError("INVALID_CHECK_EVIDENCE")
    return context, evidence


# Ordinals, not wall clocks, select the latest attempted and latest complete observation per child.
def check_history(connection, workspace):
    query = select(
        configuration_check,
        audit_event.c.data.label("audit_data"),
        audit_event.c.data_hash.label("audit_hash"),
    ).join(
        audit_event,
        and_(
            audit_event.c.workspace_id == configuration_check.c.workspace_id,
            audit_event.c.operation_id == configuration_check.c.operation_id,
            audit_event.c.id == configuration_check.c.evidence_event_id,
        ),
    )
    latest = (
        select(configuration_check.c.id)
        .where(configuration_check.c.workspace_id == workspace)
        .distinct(configuration_check.c.tenancy_id)
        .order_by(
            configuration_check.c.tenancy_id, configuration_check.c.acquisition_sequence.desc()
        )
    )
    complete = latest.where(configuration_check.c.state.in_(("matching", "drifted")))
    # Bound the projection to at most two records per child, independently of retained history size.
    rows = (
        connection.execute(
            query.where(
                configuration_check.c.workspace_id == workspace,
                or_(configuration_check.c.id.in_(latest), configuration_check.c.id.in_(complete)),
            ).order_by(configuration_check.c.acquisition_sequence.desc())
        )
        .mappings()
        .all()
    )
    return tuple((row, *decode_check(row)) for row in rows)


# Reads and sealed insertion run under the same workspace/child lock, giving monotonic acquisition.
def save_check(connection, row, target, results, state, started_at, checked_at):
    identifier, event = uuid4(), uuid4()
    context = target.model_dump(mode="json")
    code = (
        "CONFIGURATION_CHECK_SUPERSEDED"
        if state == "superseded"
        else (
            "CONFIGURATION_CHECK_UNAVAILABLE"
            if state == "unavailable"
            else "CONFIGURATION_CHECK_COMPLETE"
        )
    )
    evidence = ConfigurationCheckEvidence(
        check_id=identifier,
        tenancy_id=target.tenancy_id,
        state=state,
        safe_code=code,
        checked_at=checked_at,
        context_hash=canonical_hash(context),
        results=results,
    )
    data = evidence.model_dump(mode="json")
    connection.execute(
        audit_event.insert().values(
            id=event,
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            actor="otm-worker:configuration-check",
            actor_subject="otm-worker:configuration-check",
            actor_snapshot={"kind": "worker", "subject": "configuration-check"},
            kind="configuration_check_outcome",
            at=checked_at,
            contract_version="configuration-check-1",
            data=data,
            data_hash=canonical_hash(data),
        )
    )
    connection.execute(
        configuration_check.insert().values(
            id=identifier,
            workspace_id=row["workspace_id"],
            tenancy_id=target.tenancy_id,
            operation_id=row["id"],
            contract_version="configuration-check-1",
            started_at=started_at,
            checked_at=checked_at,
            context=context,
            context_hash=evidence.context_hash,
            state=state,
            results=[item.model_dump(mode="json") for item in results],
            evidence_event_id=event,
        )
    )
    connection.execute(
        insert(operation_step)
        .values(
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            intent_revision=1,
            step_key="configuration_check:" + str(target.tenancy_id),
            intent_event_id=row["current_intent_event_id"],
            command_kind="configuration_check",
            contract_version="configuration-check-1",
            inputs={},
            state="verified" if state in {"matching", "drifted"} else "needs_attention",
            execution_generation=1,
            attempt_number=1,
            current_attempt_id=uuid4(),
            effect_knowledge="none",
            last_outcome=data,
            verified_at=checked_at if state in {"matching", "drifted"} else None,
            evidence_event_id=event,
        )
        .on_conflict_do_nothing()
    )
    return evidence
