"""Scoped check records, immutable intent/evidence verification and independently typed results."""

import json
from uuid import uuid4

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.required_user_contracts import RequiredUserObservation
from otm.storage.tables import audit_event, operation, operation_step
from otm.storage.tables import user_presence_check as checks
from otm.tenancies.presence_contracts import (
    PresenceCheckEvidence,
    PresenceCheckIntent,
    PresenceSnapshot,
)


# Join exact intent identity, revision and original bytes before returning any queued operation.
def operation_rows(
    connection, workspace, identifier=None, tenancy_id=None, pending=False, *, tenancy_ids=None
):
    query = (
        select(
            operation,
            checks.c.context_hash.label("check_context_hash"),
            checks.c.tenancy_id.label("presence_tenancy_id"),
            audit_event.c.data.label("intent_data"),
            audit_event.c.data_hash.label("intent_hash"),
        )
        .join(
            checks,
            and_(
                checks.c.workspace_id == operation.c.workspace_id,
                checks.c.operation_id == operation.c.id,
            ),
        )
        .join(
            audit_event,
            and_(
                audit_event.c.workspace_id == operation.c.workspace_id,
                audit_event.c.operation_id == operation.c.id,
                audit_event.c.id == operation.c.current_intent_event_id,
                audit_event.c.intent_revision == operation.c.current_intent_revision,
                audit_event.c.kind == "operation_intent",
            ),
        )
        .where(operation.c.workspace_id == workspace, operation.c.kind == "required_user_check")
    )
    if identifier is not None:
        query = query.where(operation.c.id == identifier)
    if tenancy_id is not None:
        query = query.where(checks.c.tenancy_id == tenancy_id)
    if tenancy_ids is not None:
        query = query.where(checks.c.tenancy_id.in_(tenancy_ids))
    if pending:
        query = query.where(operation.c.state.in_(("queued", "running")))
    return connection.execute(query.order_by(checks.c.acquisition_sequence.desc())).mappings().all()


# Authenticated stored JSON, not a display label, defines the subject and original read authority.
def decode_intent(row):
    frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
    if (
        canonical_hash(row["intent_data"]) != row["intent_hash"]
        or not isinstance(frozen.intent, PresenceCheckIntent)
        or frozen.intent.workspace_id != row["workspace_id"]
        or frozen.actor.key != row["initiating_actor_subject"]
        or canonical_hash(frozen.intent.snapshot.model_dump(mode="json"))
        != frozen.intent.context_hash
        or frozen.intent.context_hash != row["check_context_hash"]
    ):
        raise ValueError("PRESENCE_INTENT_INVALID")
    return frozen


# Unknown preserves the exact requested subject without carrying positive or absence facts.
def unknown(command, at, code="ACCESS_UNVERIFIED"):
    return RequiredUserObservation(
        context=command.context,
        target=command.target,
        captured_at=at,
        read_id=None,
        checked_domain_ocid=None,
        checked_scim_resource_id=None,
        state="unknown",
        safe_code=code,
        authorized=False,
        complete=False,
        observed=None,
    )


# Every sealed result still names exactly the admitted subject and selected connection revision.
def validate_result_scope(row, results):
    snapshot = PresenceSnapshot.model_validate_json(json.dumps(row["context"]))
    if any(
        result.target != target
        or result.context.connection_id != snapshot.connection_id
        or result.context.connection_revision != snapshot.connection_revision
        or result.context.workspace_id != row["workspace_id"]
        for result, target in zip(results, snapshot.subjects, strict=True)
    ):
        raise ValueError("PRESENCE_RESULT_SCOPE_INVALID")


# Verify terminal payload against immutable audit evidence before exposing stored results.
def decode_result(row, data, digest):
    evidence = PresenceCheckEvidence.model_validate_json(json.dumps(data))
    if (
        canonical_hash(data) != digest
        or evidence.operation_id != row["operation_id"]
        or evidence.tenancy_id != row["tenancy_id"]
        or evidence.context_hash != row["context_hash"]
        or canonical_hash(row["context"]) != row["context_hash"]
        or evidence.state != row["state"]
        or evidence.checked_at != row["checked_at"]
        or evidence.started_at != row["started_at"]
        or [r.model_dump(mode="json") for r in evidence.results] != row["results"]
        or any(
            r.context.attempt_id != row["attempt_id"]
            or r.context.execution_generation != row["attempt_number"]
            for r in evidence.results
        )
    ):
        raise ValueError("PRESENCE_EVIDENCE_INVALID")
    validate_result_scope(row, evidence.results)
    return evidence


# Seal results, audit and logical-step history atomically under the current attempt lock.
def seal(connection, row, check, results, state, at):
    validate_result_scope(check, results)
    key = "required_users:" + str(check["tenancy_id"])
    code = {
        "complete": "USER_PRESENCE_CHECK_COMPLETE",
        "unavailable": "USER_PRESENCE_UNAVAILABLE",
        "superseded": "USER_PRESENCE_SUPERSEDED",
    }[state]
    evidence = PresenceCheckEvidence(
        tenancy_id=check["tenancy_id"],
        operation_id=row["id"],
        context_hash=check["context_hash"],
        state=state,
        safe_code=code,
        started_at=check["started_at"],
        checked_at=at,
        results=results,
    )
    payload = evidence.model_dump(mode="json")
    event = uuid4()
    connection.execute(
        audit_event.insert().values(
            id=event,
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            actor="otm-worker:user-presence",
            actor_subject="otm-worker:user-presence",
            actor_snapshot={"kind": "worker", "subject": "user-presence"},
            kind="required_user_check_outcome",
            at=at,
            contract_version=evidence.contract_version,
            data=payload,
            data_hash=canonical_hash(payload),
        )
    )
    connection.execute(
        update(checks)
        .where(
            checks.c.workspace_id == row["workspace_id"],
            checks.c.operation_id == row["id"],
            checks.c.attempt_id == check["attempt_id"],
        )
        .values(state=state, checked_at=at, results=payload["results"], evidence_event_id=event)
    )
    connection.execute(
        insert(operation_step).values(
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            intent_revision=row["current_intent_revision"],
            step_key=key,
            intent_event_id=row["current_intent_event_id"],
            command_kind="required_user_check",
            contract_version=evidence.contract_version,
            inputs={},
            state="verified",
            execution_generation=check["attempt_number"],
            attempt_number=check["attempt_number"],
            current_attempt_id=check["attempt_id"],
            effect_knowledge="none",
            last_outcome=payload,
            verified_at=at,
            evidence_event_id=event,
        )
    )
    connection.execute(
        update(operation)
        .where(operation.c.workspace_id == row["workspace_id"], operation.c.id == row["id"])
        .values(
            state="succeeded",
            stage="Required-user presence check complete",
            completed_at=at,
            updated_at=at,
            revision=operation.c.revision + 1,
        )
    )
