"""Short transactional claim/publication of the first simulated inspection operation."""

import json
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from otm.contracts import UtcInstant
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.operations.execution_contracts import (
    ClaimedInspection,
    CommittedInspection,
    DispatchEvent,
    DispatchGrant,
    InspectionOutcome,
)
from otm.providers.inspection_contracts import ExecutionContext, InspectionConfirmed
from otm.storage.tables import audit_event, operation, operation_step
from otm.storage.transaction import require_transaction


# Persist read progress with exact intent/operation/attempt generation guards.
class SqlExecutionStore:
    # Use the injected application engine; never open a provider or queue connection here.
    def __init__(self, engine: Engine, workspace: str | None = None):
        self.engine, self.workspace = engine, workspace

    # Resolve only current runnable inspection intent and verify its closed snapshot/hash.
    def load(self, operation_id: UUID) -> CommittedInspection | None:
        with self.engine.connect() as connection:
            op = (
                connection.execute(
                    select(operation).where(
                        operation.c.id == operation_id,
                        *(
                            [operation.c.workspace_id == self.workspace]
                            if self.workspace is not None
                            else []
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if op is None or op["state"] not in {"queued", "running"}:
                return None
            event = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.workspace_id == op["workspace_id"],
                        audit_event.c.operation_id == op["id"],
                        audit_event.c.intent_revision == op["current_intent_revision"],
                        audit_event.c.id == op["current_intent_event_id"],
                        audit_event.c.kind == "operation_intent",
                    )
                )
                .mappings()
                .one()
            )
        try:
            frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
            if (
                canonical_hash(event["data"]) != event["data_hash"]
                or frozen.intent.workspace_id != op["workspace_id"]
                or frozen.actor.key != op["initiating_actor_subject"]
                or frozen.actor.model_dump(mode="json") != op["initiating_actor_snapshot"]
                or event["actor_subject"] != frozen.actor.key
                or op["kind"] != "inspect_import"
            ):
                raise ValueError("Invalid frozen inspection")
            return CommittedInspection(
                operation_id=op["id"],
                operation_revision=op["revision"],
                intent_event_id=event["id"],
                intent_revision=event["intent_revision"],
                actor=frozen.actor,
                intent=frozen.intent,
            )
        except (ValueError, TypeError):
            raise ValueError("INVALID_COMMITTED_INSPECTION") from None

    # Lock only the exact runnable operation revision; a late claim/publication loses.
    def _current(self, connection, committed: CommittedInspection, revision: int):
        return (
            connection.execute(
                select(operation)
                .where(
                    operation.c.id == committed.operation_id,
                    operation.c.workspace_id == committed.intent.workspace_id,
                    operation.c.current_intent_event_id == committed.intent_event_id,
                    operation.c.current_intent_revision == committed.intent_revision,
                    operation.c.initiating_actor_subject == committed.actor.key,
                    operation.c.revision == revision,
                    operation.c.state.in_(["queued", "running"]),
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    # Bind one immutable logical read step to this exact workspace and intent revision.
    def _step_scope(self, committed: CommittedInspection):
        return (
            operation_step.c.workspace_id == committed.intent.workspace_id,
            operation_step.c.operation_id == committed.operation_id,
            operation_step.c.intent_revision == committed.intent_revision,
            operation_step.c.step_key == "inspect_target",
        )

    # Append worker evidence with no raw exception or mutable actor claims.
    def _audit(self, connection, committed, kind, data, at):
        identifier = uuid4()
        connection.execute(
            audit_event.insert().values(
                id=identifier,
                workspace_id=committed.intent.workspace_id,
                operation_id=committed.operation_id,
                intent_revision=None,
                actor="otm-worker:inspection",
                actor_subject="otm-worker:inspection",
                actor_snapshot={"kind": "worker", "subject": "inspection"},
                kind=kind,
                at=at,
                contract_version="inspection-worker-1",
                data=data,
                data_hash=canonical_hash(data),
            )
        )
        return identifier

    # Create/supersede one read attempt; no DB transaction crosses provider execution.
    def claim(
        self, committed: CommittedInspection, grant: DispatchGrant, at: datetime
    ) -> ClaimedInspection | None:
        at = TypeAdapter(UtcInstant).validate_python(at)
        if (
            grant.workspace_id != committed.intent.workspace_id
            or grant.actor_key != committed.actor.key
            or grant.policy_revision != committed.intent.policy_revision
            or grant.access_binding_id != committed.intent.access_binding_id
        ):
            raise ValueError("DISPATCH_SCOPE_MISMATCH")
        with self.engine.begin() as connection:
            require_transaction(connection)
            if self._current(connection, committed, committed.operation_revision) is None:
                return None
            step = (
                connection.execute(select(operation_step).where(*self._step_scope(committed)))
                .mappings()
                .one_or_none()
            )
            inputs = committed.intent.model_dump(mode="json")
            if step and (
                step["inputs"] != inputs or step["intent_event_id"] != committed.intent_event_id
            ):
                raise ValueError("IMMUTABLE_STEP_INPUT_MISMATCH")
            generation = step["execution_generation"] + 1 if step else 1
            context = ExecutionContext(
                workspace_id=committed.intent.workspace_id,
                operation_id=committed.operation_id,
                step_key="inspect_target",
                attempt_id=uuid4(),
                intent_revision=committed.intent_revision,
                execution_generation=generation,
                access_binding_id=grant.access_binding_id,
                credential_generation=grant.credential_generation,
            )
            attempt = ClaimedInspection(
                committed=committed,
                operation_revision=committed.operation_revision + 1,
                context=context,
                grant=grant,
            )
            event = DispatchEvent(
                context=context, grant=grant, intent_event_id=committed.intent_event_id
            )
            values = dict(
                state="running",
                execution_generation=generation,
                attempt_number=step["attempt_number"] + 1 if step else 1,
                current_attempt_id=context.attempt_id,
                effect_knowledge="none",
                last_outcome=None,
                verified_at=None,
                evidence_event_id=None,
            )
            if step:
                connection.execute(
                    update(operation_step).where(*self._step_scope(committed)).values(**values)
                )
            else:
                connection.execute(
                    operation_step.insert().values(
                        workspace_id=committed.intent.workspace_id,
                        operation_id=committed.operation_id,
                        intent_revision=committed.intent_revision,
                        step_key="inspect_target",
                        intent_event_id=committed.intent_event_id,
                        command_kind="inspect_tenancy",
                        contract_version="execution-1-draft",
                        inputs=inputs,
                        **values,
                    )
                )
            self._audit(
                connection, committed, "inspection_dispatch", event.model_dump(mode="json"), at
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == committed.operation_id)
                .values(state="running", revision=attempt.operation_revision, updated_at=at)
            )
        return attempt

    # Publish winning evidence and progress together; ignore superseded results.
    def finish(
        self,
        committed: CommittedInspection,
        attempt: ClaimedInspection | None,
        outcome: InspectionOutcome,
        at: datetime,
    ) -> bool:
        at = TypeAdapter(UtcInstant).validate_python(at)
        outcome = InspectionOutcome.model_validate(outcome)
        if (
            outcome.intent_event_id != committed.intent_event_id
            or (outcome.context != (attempt.context if attempt else None))
            or (attempt and attempt.committed != committed)
            or (not attempt and outcome.result is not None)
        ):
            raise ValueError("OUTCOME_SCOPE_MISMATCH")
        if outcome.result is not None and (
            outcome.context is None
            or outcome.result.attempt_id != outcome.context.attempt_id
            or outcome.safe_code != outcome.result.safe_code
        ):
            raise ValueError("OUTCOME_RESULT_MISMATCH")
        verified = isinstance(outcome.result, InspectionConfirmed)
        if verified and (
            outcome.result.tenancy.tenancy_ocid == outcome.result.tenancy.parent_tenancy_ocid
            or outcome.result.tenancy.tenancy_ocid != committed.intent.target.tenancy_ocid
            or outcome.result.tenancy.parent_tenancy_ocid
            != committed.intent.target.parent_tenancy_ocid
            or outcome.result.tenancy.organization_id != committed.intent.target.organization_id
        ):
            raise ValueError("OUTCOME_TARGET_MISMATCH")
        revision = attempt.operation_revision if attempt else committed.operation_revision
        with self.engine.begin() as connection:
            require_transaction(connection)
            if self._current(connection, committed, revision) is None:
                return False
            if attempt:
                step = (
                    connection.execute(select(operation_step).where(*self._step_scope(committed)))
                    .mappings()
                    .one()
                )
                if (
                    step["state"] != "running"
                    or step["current_attempt_id"] != attempt.context.attempt_id
                    or step["execution_generation"] != attempt.context.execution_generation
                ):
                    return False
            event_id = self._audit(
                connection, committed, "inspection_outcome", outcome.model_dump(mode="json"), at
            )
            if attempt:
                connection.execute(
                    update(operation_step)
                    .where(*self._step_scope(committed))
                    .values(
                        state="verified" if verified else "needs_attention",
                        last_outcome=outcome.model_dump(mode="json"),
                        evidence_event_id=event_id,
                        verified_at=at if verified else None,
                    )
                )
            connection.execute(
                update(operation)
                .where(operation.c.id == committed.operation_id)
                .values(
                    state="succeeded" if verified else "needs_attention",
                    stage="inspect_target",
                    wait_reason=None if verified else "manual",
                    effect_knowledge="none",
                    revision=revision + 1,
                    completed_at=at if verified else None,
                    updated_at=at,
                )
            )
        return True
