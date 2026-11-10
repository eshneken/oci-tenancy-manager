"""Small nonsecret record helpers shared by disclosure and the existing durable worker."""

import json
from uuid import uuid4

from sqlalchemy import select

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.recovery_password import PasswordLocation, PasswordVersion
from otm.storage.tables import audit_event, operation, recovery_version


# Authenticate immutable subject/secret metadata before constructing any custody request.
def location_of(head):
    location = PasswordLocation.model_validate_json(json.dumps(head["location"]))
    if (
        canonical_hash(head["location"]) != head["location_hash"]
        or location.credential_id != head["id"]
        or location.target.workspace_id != head["workspace_id"]
        or location.target.tenancy_id != head["tenancy_id"]
        or location.target.subject_binding_id != head["principal_binding_id"]
    ):
        raise ValueError("RECOVERY_PASSWORD_BINDING_INVALID")
    return location


# Exact version evidence must belong to this head and remain unchanged after insertion.
def version_of(connection, head, identifier):
    row = (
        connection.execute(
            select(recovery_version).where(
                recovery_version.c.workspace_id == head["workspace_id"],
                recovery_version.c.credential_id == head["id"],
                recovery_version.c.id == identifier,
            )
        )
        .mappings()
        .one()
    )
    reference = PasswordVersion.model_validate_json(json.dumps(row["reference"]))
    if (
        canonical_hash(row["reference"]) != row["reference_hash"]
        or reference.location != location_of(head)
        or reference.operation_id != row["created_operation_id"]
    ):
        raise ValueError("RECOVERY_PASSWORD_VERSION_INVALID")
    return reference


# Accepted operations, immutable intent and native reference-only scheduling share one transaction.
def admit_operation(connection, intent, actor, at, enqueuer, *, identifier=None):
    identifier, event = identifier or uuid4(), uuid4()
    data = IntentEventData(intent=intent, actor=actor).model_dump(mode="json")
    future = intent.due_at is not None and intent.due_at > at
    connection.execute(
        operation.insert().values(
            id=identifier,
            workspace_id=intent.workspace_id,
            kind=intent.kind,
            initiating_actor_subject=actor.key,
            initiating_actor_snapshot=actor.model_dump(mode="json"),
            responsible_actor_subject=actor.key,
            client_request_key=uuid4(),
            request_digest=canonical_hash(data),
            current_intent_revision=1,
            current_intent_event_id=event,
            state="waiting" if future else "queued",
            wait_reason="recovery_rotation_due" if future else None,
            stage="Rotate recovery password at original deadline"
            if intent.phase == "rotation"
            else "Prepare recovery password custody",
            effect_knowledge="none",
            revision=1,
            accepted_at=at,
            created_at=at,
            updated_at=at,
        )
    )
    connection.execute(
        audit_event.insert().values(
            id=event,
            workspace_id=intent.workspace_id,
            operation_id=identifier,
            actor=actor.key,
            actor_subject=actor.key,
            actor_snapshot=actor.model_dump(mode="json"),
            kind="operation_intent",
            intent_revision=1,
            at=at,
            contract_version=intent.contract_version,
            data=data,
            data_hash=canonical_hash(data),
        )
    )
    delay = max(0, int((intent.due_at - at).total_seconds()) + 1) if future else 0
    enqueuer.enqueue(connection, identifier, delay_seconds=delay)
    return identifier


# Public projections later select explicit safe fields rather than serializing private references.
def record_event(connection, workspace, operation_id, kind, proof, at, actor=None):
    data = proof.model_dump(mode="json")
    key = uuid4()
    connection.execute(
        audit_event.insert().values(
            id=key,
            workspace_id=workspace,
            operation_id=operation_id,
            actor=actor.key if actor else "otm-worker:recovery-password",
            actor_subject=actor.key if actor else "otm-worker:recovery-password",
            actor_snapshot=actor.model_dump(mode="json")
            if actor
            else {
                "kind": "worker",
                "subject": "recovery-password",
            },
            kind=kind,
            at=at,
            contract_version=proof.contract_version,
            data=data,
            data_hash=canonical_hash(data),
        )
    )
    return key
