"""Bounded read-only financial jobs perform provider I/O outside database transactions."""

import json
from datetime import timedelta
from math import ceil
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from otm.financial.context import source_context, target_source
from otm.financial.contracts import BudgetReadResult, CostEvidence, CostIntent
from otm.financial.normalization import month_bounds, normalize
from otm.financial.records import decode_collection
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.tables import (
    administrator,
    audit_event,
    financial_collection,
    financial_observation,
    operation,
    operation_step,
    org_workspace,
    tenancy,
)


# Verify immutable operation scope before selecting any credentials, target or administrator.
def cost_intent(row):
    if canonical_hash(row["intent_data"]) != row["intent_hash"]:
        raise ValueError("INVALID_COST_INTENT")
    frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
    if (
        not isinstance(frozen.intent, CostIntent)
        or frozen.intent.workspace_id != row["workspace_id"]
        or frozen.actor.key != row["initiating_actor_subject"]
    ):
        raise ValueError("INVALID_COST_INTENT")
    return frozen


# Replays re-read harmless GETs, while attempt IDs fence late publication and retries remain
# bounded.
class CostCollectionWorker:
    # No provider call occurs during construction; deployment policy and clock are explicit inputs.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        facade,
        enqueuer,
        *,
        profile,
        profile_loader=None,
        notifications=None,
    ):
        self.engine, self.workspace, self.clock = engine, workspace, clock
        self.policy_loader, self.facade, self.enqueuer = policy_loader, facade, enqueuer
        self.profile, self.profile_loader, self.notifications = (
            profile,
            profile_loader,
            notifications,
        )

    # Each child publishes independently; native ETA retries do not sleep or hold fleet locks.
    def run(self, identifier):
        with self.engine.connect() as connection:
            ids = list(
                connection.scalars(
                    select(financial_collection.c.id)
                    .where(
                        financial_collection.c.workspace_id == self.workspace,
                        financial_collection.c.operation_id == identifier,
                    )
                    .order_by(financial_collection.c.tenancy_id)
                )
            )
        for collection_id in ids:
            prepared = self._prepare(identifier, collection_id)
            if prepared is None:
                continue
            row, target, stored, problem = prepared
            snapshot, code = None, problem
            if code is None:
                try:
                    result = self.facade.read_managed_budget(target, stored, self.clock())
                    if not isinstance(result, BudgetReadResult):
                        raise ValueError("COST_SOURCE_UNQUALIFIED")
                    result = BudgetReadResult.model_validate(result)
                    candidate = normalize(target, result, self.clock())
                    if candidate.retrieved_at < row["updated_at"]:
                        raise ValueError("COST_SOURCE_UNQUALIFIED")
                    # Publish only after every response fence passes; rejected candidates cannot
                    # replace retained facts or become evidence that a failure episode recovered.
                    snapshot = candidate
                    code = (
                        "COST_READ_COMPLETE"
                        if snapshot.source_state == "qualified"
                        else "COST_SOURCE_UNQUALIFIED"
                    )
                except ValueError as error:
                    from otm.providers.budget import BudgetReadUnavailable

                    code = (
                        "COST_READ_UNAVAILABLE"
                        if isinstance(error, BudgetReadUnavailable)
                        else "COST_TARGET_CHANGED"
                        if str(error) == "COST_TARGET_CHANGED"
                        else "COST_SOURCE_UNQUALIFIED"
                    )
                except Exception:
                    code = "COST_READ_UNAVAILABLE"
            self._finish(identifier, row, target, snapshot, code)
        self._progress(identifier)

    # Match existing lock ordering and exact intent references; no lock survives provider I/O.
    def _locked(self, connection, identifier):
        anchor = connection.scalar(
            select(administrator.c.id)
            .where(
                administrator.c.workspace_id == self.workspace,
                administrator.c.identity_kind == "local_recovery",
                administrator.c.status == "active",
            )
            .with_for_update()
        )
        if anchor is None:
            return None
        connection.execute(
            select(org_workspace.c.id).where(org_workspace.c.id == self.workspace).with_for_update()
        ).scalar_one_or_none()
        row = (
            connection.execute(
                select(
                    operation,
                    audit_event.c.data.label("intent_data"),
                    audit_event.c.data_hash.label("intent_hash"),
                )
                .join(
                    audit_event,
                    (audit_event.c.workspace_id == operation.c.workspace_id)
                    & (audit_event.c.operation_id == operation.c.id)
                    & (audit_event.c.id == operation.c.current_intent_event_id)
                    & (audit_event.c.intent_revision == operation.c.current_intent_revision)
                    & (audit_event.c.kind == "operation_intent"),
                )
                .where(
                    operation.c.workspace_id == self.workspace,
                    operation.c.id == identifier,
                    operation.c.kind == "cost_collection",
                )
                .with_for_update(of=operation)
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["state"] not in {"queued", "running"}:
            return None
        cost_intent(row)
        return row

    # Live grant, parent, profile, exact budget and cycle fences apply both before and after the
    # GET.
    def _problem(self, connection, op, target, row, at):
        frozen = cost_intent(op)
        grant = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == self.workspace,
                    administrator.c.id == frozen.intent.administrator_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            grant is None
            or grant["status"] != "active"
            or grant["authorization_revision"] != frozen.intent.authorization_revision
            or (grant["issuer"], grant["subject"]) != (frozen.actor.issuer, frozen.actor.subject)
        ):
            return "COST_AUTHORIZATION_CHANGED"
        current = self.policy_loader()
        if (
            current.execution_paused
            or current.policy != self.facade.policy
            or (self.profile_loader and self.profile_loader() != self.profile)
            or target.profile != self.profile
        ):
            return "COST_CONTEXT_UNAVAILABLE"
        source = source_context(row, current.policy, self.profile) if row else None
        if (
            source is None
            or canonical_hash(source) != target_source(target)
            or (target.period_start, target.period_end) != month_bounds(at)
            or row["operation_id"]
        ):
            return "COST_TARGET_CHANGED"
        return None

    # Claim a new bounded read attempt and commit it before invoking the facade.
    def _prepare(self, identifier, collection_id):
        with self.engine.begin() as connection:
            op = self._locked(connection, identifier)
            if op is None:
                return None
            row = (
                connection.execute(
                    select(financial_collection)
                    .where(
                        financial_collection.c.workspace_id == self.workspace,
                        financial_collection.c.operation_id == identifier,
                        financial_collection.c.id == collection_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] in {"succeeded", "failed", "superseded"}:
                return None
            at = max(self.clock(), row["updated_at"])
            if row["next_attempt_at"] and row["next_attempt_at"] > at:
                return None
            target = decode_collection(row)
            if not any(t == target for t in cost_intent(op).intent.targets):
                raise ValueError("COST_COLLECTION_NOT_IN_INTENT")
            registered = (
                connection.execute(
                    select(tenancy).where(
                        tenancy.c.workspace_id == self.workspace,
                        tenancy.c.id == row["tenancy_id"],
                    )
                )
                .mappings()
                .one_or_none()
            )
            problem = self._problem(connection, op, target, registered, at)
            if row["attempts"] >= 3:
                # An abandoned third read cannot create an unbounded fourth provider invocation.
                self._record(
                    connection,
                    op,
                    row,
                    "superseded" if problem else "failed",
                    problem or "COST_RETRIES_EXHAUSTED",
                    at,
                )
                if not problem and self.notifications:
                    from otm.financial.notifications import stage_failure

                    stage_failure(self.notifications, connection, op, row, target, at)
                return None
            values = dict(
                state="reading",
                attempts=row["attempts"] + 1,
                attempt_id=uuid4(),
                next_attempt_at=None,
                updated_at=at,
                safe_code=row["safe_code"],
            )
            connection.execute(
                update(financial_collection)
                .where(financial_collection.c.id == collection_id)
                .values(**values)
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state="running",
                    stage="Reading current month costs",
                    updated_at=at,
                )
            )
            return (
                dict(row, **values),
                target,
                (registered["configuration_observation"].get("budget") if registered else None),
                problem,
            )

    # Only the current attempt may publish; source changes and rollback never advance current facts.
    def _finish(self, identifier, prepared, target, snapshot, code):
        with self.engine.begin() as connection:
            op = self._locked(connection, identifier)
            if op is None:
                return
            row = (
                connection.execute(
                    select(financial_collection)
                    .where(
                        financial_collection.c.workspace_id == self.workspace,
                        financial_collection.c.id == prepared["id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] != "reading" or row["attempt_id"] != prepared["attempt_id"]:
                return
            at = max(self.clock(), row["updated_at"])
            registered = (
                connection.execute(
                    select(tenancy).where(
                        tenancy.c.workspace_id == self.workspace,
                        tenancy.c.id == row["tenancy_id"],
                    )
                )
                .mappings()
                .one_or_none()
            )
            problem = self._problem(connection, op, target, registered, at)
            if problem or code in {
                "COST_TARGET_CHANGED",
                "COST_AUTHORIZATION_CHANGED",
                "COST_CONTEXT_UNAVAILABLE",
            }:
                self._record(connection, op, row, "superseded", problem or code, at)
                return
            if code == "COST_READ_UNAVAILABLE":
                retry = row["attempts"] <= len(target.profile.retry_delays_seconds)
                due = (
                    at + timedelta(seconds=target.profile.retry_delays_seconds[row["attempts"] - 1])
                    if retry
                    else None
                )
                self._record(
                    connection,
                    op,
                    row,
                    "retry" if retry else "failed",
                    code if retry else "COST_RETRIES_EXHAUSTED",
                    at,
                    due=due,
                )
                if not retry and self.notifications:
                    from otm.financial.notifications import stage_failure

                    stage_failure(self.notifications, connection, op, row, target, at)
                return
            if snapshot is not None:
                data = snapshot.model_dump(mode="json")
                connection.execute(
                    financial_observation.insert().values(
                        id=uuid4(),
                        workspace_id=self.workspace,
                        tenancy_id=row["tenancy_id"],
                        collection_id=row["id"],
                        context_hash=row["context_hash"],
                        source_hash=row["source_hash"],
                        budget_ocid=snapshot.budget_ocid,
                        observed_budget_amount=snapshot.budget,
                        actual_spend=snapshot.actual,
                        forecasted_spend=snapshot.forecast,
                        currency=snapshot.currency,
                        time_spend_computed=snapshot.computed_at,
                        captured_at=snapshot.retrieved_at,
                        period_start=snapshot.period_start,
                        period_end=snapshot.period_end,
                        snapshot=data,
                        snapshot_hash=canonical_hash(data),
                    )
                )
            self._record(connection, op, row, "succeeded", code, at)

    # Outcome, read step and collection head commit together; no money or credentials enter history.
    def _record(self, connection, op, row, state, code, at, *, due=None):
        proof = CostEvidence(
            collection_id=row["id"],
            tenancy_id=row["tenancy_id"],
            state=state,
            attempts=row["attempts"],
            safe_code=code,
        )
        data, event = proof.model_dump(mode="json"), uuid4()
        connection.execute(
            audit_event.insert().values(
                id=event,
                workspace_id=self.workspace,
                operation_id=op["id"],
                actor="otm-worker:costs",
                actor_subject="otm-worker:costs",
                actor_snapshot={"kind": "worker", "subject": "costs"},
                kind="cost_collection_outcome",
                at=at,
                contract_version=proof.contract_version,
                data=data,
                data_hash=canonical_hash(data),
            )
        )
        connection.execute(
            update(financial_collection)
            .where(financial_collection.c.id == row["id"])
            .values(state=state, safe_code=code, next_attempt_at=due, updated_at=at)
        )
        values = dict(
            workspace_id=self.workspace,
            operation_id=op["id"],
            intent_revision=1,
            step_key="cost:" + str(row["tenancy_id"]),
            intent_event_id=op["current_intent_event_id"],
            command_kind="cost_collection",
            contract_version=proof.contract_version,
            inputs={},
            state="verified"
            if state == "succeeded"
            else "running"
            if state == "retry"
            else "needs_attention",
            execution_generation=1,
            attempt_number=row["attempts"],
            current_attempt_id=row["attempt_id"],
            effect_knowledge="none",
            last_outcome=data,
            verified_at=at if state == "succeeded" else None,
            evidence_event_id=event,
        )
        statement = insert(operation_step).values(**values)
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    operation_step.c.workspace_id,
                    operation_step.c.operation_id,
                    operation_step.c.intent_revision,
                    operation_step.c.step_key,
                ],
                set_={
                    key: value
                    for key, value in values.items()
                    if key not in {"workspace_id", "operation_id", "intent_revision", "step_key"}
                },
            )
        )

    # A failed child does not roll back peers; due retries use native scheduling on the same queue.
    def _progress(self, identifier):
        with self.engine.begin() as connection:
            op = self._locked(connection, identifier)
            if op is None:
                return
            rows = (
                connection.execute(
                    select(financial_collection).where(
                        financial_collection.c.workspace_id == self.workspace,
                        financial_collection.c.operation_id == identifier,
                    )
                )
                .mappings()
                .all()
            )
            pending = [r for r in rows if r["state"] in {"queued", "reading", "retry"}]
            at = self.clock()
            if pending:
                due = min(r["next_attempt_at"] or at for r in pending)
                self.enqueuer.enqueue(
                    connection, identifier, delay_seconds=max(0, ceil((due - at).total_seconds()))
                )
                state, stage, completed = "queued", "Cost refresh retry scheduled", None
            else:
                failed = sum(r["state"] in {"failed", "superseded"} for r in rows)
                state = "failed" if failed else "succeeded"
                stage = f"Cost refresh complete: {len(rows) - failed} of {len(rows)} collected"
                completed = at
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state=state,
                    stage=stage,
                    completed_at=completed,
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
