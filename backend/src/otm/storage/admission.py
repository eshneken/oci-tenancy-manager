"""Persist idempotent inspection acceptance and immutable intent with one native queue insert."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, Engine, RowMapping

from otm.operations.contracts import (
    Acceptance,
    ActorIdentity,
    InspectImportRequest,
    InspectionIntent,
    IntentEventData,
    canonical_hash,
)
from otm.storage.tables import audit_event, operation
from otm.storage.transaction import require_transaction


# A caller cannot reuse its accepted request key for different bounded input.
class RequestConflict(ValueError):
    pass


# The job adapter participates in this exact transaction rather than opening its own.
class Enqueuer(Protocol):
    # Insert only the operation reference using the provided active connection.
    def enqueue(self, connection: Connection, operation_id: UUID) -> None: ...


# Check request compatibility before returning any accepted identity or current state.
def receipt(row: RowMapping, digest: str) -> Acceptance:
    if row["request_digest"] != digest:
        raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
    return Acceptance(
        operation_id=row["id"], state=row["state"], accepted_at=row["accepted_at"].astimezone(UTC)
    )


# Own short database transactions; authorization and policy resolution happen outside them.
class SqlAdmissionStore:
    # Inject deployment adapters without reading environment URLs or default databases.
    def __init__(self, engine: Engine, enqueuer: Enqueuer):
        self.engine, self.enqueuer = engine, enqueuer

    # Scope lookup by workspace, qualified actor and request key before digest checks.
    def _find(
        self, connection: Connection, request: InspectImportRequest, actor: ActorIdentity
    ) -> Acceptance | None:
        row = (
            connection.execute(
                select(operation).where(
                    operation.c.workspace_id == request.workspace_id,
                    operation.c.initiating_actor_subject == actor.key,
                    operation.c.client_request_key == request.client_request_key,
                )
            )
            .mappings()
            .one_or_none()
        )
        return receipt(row, request.digest) if row is not None else None

    # Read a committed replay before current policy checks, without writing a receipt.
    def find(self, request: InspectImportRequest, actor: ActorIdentity) -> Acceptance | None:
        with self.engine.connect() as connection:
            return self._find(connection, request, actor)

    # Return acceptance only after operation, intent and job have actually committed.
    def insert(
        self,
        request: InspectImportRequest,
        actor: ActorIdentity,
        intent: InspectionIntent,
        at: datetime,
    ) -> Acceptance:
        # Validate snapshots/time and their mutual scope before opening a write transaction.
        event = IntentEventData(intent=intent, actor=actor)
        if (
            intent.workspace_id != request.workspace_id
            or intent.target.tenancy_ocid != request.tenancy_ocid
            or intent.target.parent_tenancy_ocid == request.tenancy_ocid
        ):
            raise ValueError("INTENT_SCOPE_MISMATCH")
        identifier, event_id = uuid4(), uuid4()
        accepted = Acceptance(operation_id=identifier, state="queued", accepted_at=at)
        data, snapshot = event.model_dump(mode="json"), actor.model_dump(mode="json")
        with self.engine.begin() as connection:
            require_transaction(connection)
            inserted = connection.execute(
                insert(operation)
                .values(
                    id=identifier,
                    workspace_id=request.workspace_id,
                    kind="inspect_import",
                    initiating_actor_subject=actor.key,
                    initiating_actor_snapshot=snapshot,
                    responsible_actor_subject=actor.key,
                    client_request_key=request.client_request_key,
                    request_digest=request.digest,
                    current_intent_revision=1,
                    current_intent_event_id=event_id,
                    state="queued",
                    stage="inspect_target",
                    wait_reason=None,
                    effect_knowledge="none",
                    revision=1,
                    accepted_at=at,
                    created_at=at,
                    updated_at=at,
                    completed_at=None,
                )
                .on_conflict_do_nothing(constraint="uq_operation_request")
                .returning(operation.c.id)
            ).scalar_one_or_none()
            if inserted is None:
                winner = self._find(connection, request, actor)
                if winner is None:
                    raise RuntimeError("COMMITTED_ACCEPTANCE_WINNER_NOT_FOUND")
                return winner
            # Both directions are scoped deferred FKs: the audit pointer can be assigned before
            # its insert, while COMMIT still requires the exact operation/revision/intent event.
            connection.execute(
                audit_event.insert().values(
                    id=event_id,
                    workspace_id=request.workspace_id,
                    operation_id=identifier,
                    intent_revision=1,
                    actor=actor.key,
                    actor_subject=actor.key,
                    actor_snapshot=snapshot,
                    kind="operation_intent",
                    at=at,
                    contract_version="inspect-import-1",
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            self.enqueuer.enqueue(connection, identifier)
        return accepted
