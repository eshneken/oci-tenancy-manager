"""One-shot conditional network writes with durable attempt fences and no blind retries."""

import json
from uuid import uuid4

from sqlalchemy import select, update

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.recovery_console import observed_fingerprint
from otm.providers.recovery_network import RecoveryNetworkOutcome
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    operation_step,
    org_workspace,
    tenancy,
)
from otm.tenancies.presence_context import capture_snapshot
from otm.tenancies.presence_source import load_presence_source
from otm.tenancies.recovery_network import network_command
from otm.tenancies.recovery_network_contracts import RecoveryNetworkEvidence, RecoveryNetworkIntent


# Only this explicitly composed capability may execute the fixed reference-only queue task.
class RecoveryNetworkWorker:
    # Authority, desired settings, time and provider factory are operator-owned dependencies.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        console_loader,
        factory,
        *,
        signing_dispatch=None,
    ):
        self.signing_dispatch = signing_dispatch
        self.engine, self.workspace, self.clock = engine, workspace, clock
        self.policy_loader, self.console_loader, self.factory = (
            policy_loader,
            console_loader,
            factory,
        )

    # Lock in the existing anchor/workspace/operation/child order; unrelated work cannot interleave.
    def locked(self, connection, identifier):
        connection.execute(
            select(administrator.c.id)
            .where(
                administrator.c.workspace_id == self.workspace,
                administrator.c.identity_kind == "local_recovery",
                administrator.c.status == "active",
            )
            .with_for_update()
        ).scalar_one()
        connection.execute(
            select(org_workspace.c.id).where(org_workspace.c.id == self.workspace).with_for_update()
        ).scalar_one()
        row = (
            connection.execute(
                select(operation)
                .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["kind"] != "recovery_network_repair":
            return None
        event = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.workspace_id == self.workspace,
                    audit_event.c.operation_id == identifier,
                    audit_event.c.id == row["current_intent_event_id"],
                    audit_event.c.kind == "operation_intent",
                    audit_event.c.intent_revision == row["current_intent_revision"],
                )
            )
            .mappings()
            .one()
        )
        frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
        if (
            canonical_hash(event["data"]) != event["data_hash"]
            or not isinstance(frozen.intent, RecoveryNetworkIntent)
            or frozen.intent.workspace_id != self.workspace
            or frozen.actor.key != row["initiating_actor_subject"]
        ):
            raise ValueError("RECOVERY_NETWORK_INTENT_INVALID")
        child = (
            connection.execute(
                select(tenancy)
                .where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == frozen.intent.snapshot.tenancy_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        return row, frozen, child

    # Busy ownership is excluded only for this exact admitted operation; all other context is exact.
    def current(self, connection, row, frozen, child):
        intent = frozen.intent
        grant = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == self.workspace,
                    administrator.c.id == intent.administrator_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if self.signing_dispatch is not None and not self.signing_dispatch(
            connection, self.workspace, child["id"], self.clock()
        ):
            return None
        policy, desired = self.policy_loader(), self.console_loader()
        if (
            grant is None
            or grant["status"] != "active"
            or grant["authorization_revision"] != intent.authorization_revision
            or (grant["issuer"], grant["subject"]) != (frozen.actor.issuer, frozen.actor.subject)
            or child["operation_id"] != row["id"]
            or child["status"] != "active"
            or policy.execution_paused
            or desired is None
            or desired.fingerprint != intent.desired_fingerprint
            or not row["accepted_at"] <= self.clock() < intent.expires_at
        ):
            return None
        target = dict(child, operation_id=None)
        snapshot = capture_snapshot(connection, self.workspace, target, policy.policy, desired)
        if snapshot != intent.snapshot:
            return None
        source = load_presence_source(connection, snapshot)
        if canonical_hash(source.model_dump(mode="json")) != intent.source_hash:
            return None
        return source, desired

    # Prepare one durable attempt; a replay never repeats a possibly-sent provider write.
    def begin(self, identifier):
        with self.engine.begin() as connection:
            locked = self.locked(connection, identifier)
            if locked is None:
                return None
            row, frozen, child = locked
            if row["state"] not in {"queued", "running"}:
                return None
            if row["state"] == "running":
                self.complete(
                    connection, row, frozen, child, RecoveryNetworkOutcome(effect="unknown")
                )
                return None
            prepared = self.current(connection, row, frozen, child)
            if prepared is None:
                self.complete(connection, row, frozen, child, RecoveryNetworkOutcome(effect="none"))
                return None
            source, desired = prepared
            attempt = uuid4()
            command = network_command(
                frozen.intent.snapshot, source.recovery_console, desired, identifier, attempt
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state="running",
                    stage="Verifying conditional perimeter authority",
                    revision=operation.c.revision + 1,
                    updated_at=self.clock(),
                )
            )
            connection.execute(
                operation_step.insert().values(
                    workspace_id=self.workspace,
                    operation_id=identifier,
                    intent_revision=1,
                    step_key=command.context.step_key,
                    intent_event_id=row["current_intent_event_id"],
                    command_kind="recovery_network_repair",
                    contract_version=frozen.intent.contract_version,
                    inputs={"attempt_id": str(attempt)},
                    state="running",
                    execution_generation=1,
                    attempt_number=1,
                    current_attempt_id=attempt,
                    effect_knowledge="none",
                )
            )
            return command, source.recovery_console, frozen.intent.observed_fingerprint

    # Persist the exact conditional compare token before dispatch and release every database lock.
    def dispatch(self, identifier, authority):
        with self.engine.begin() as connection:
            locked = self.locked(connection, identifier)
            if locked is None:
                return False
            row, frozen, child = locked
            if row["state"] != "running":
                return False
            if self.current(connection, row, frozen, child) is None:
                self.complete(connection, row, frozen, child, RecoveryNetworkOutcome(effect="none"))
                return False
            changed = connection.execute(
                update(operation_step)
                .where(
                    operation_step.c.workspace_id == self.workspace,
                    operation_step.c.operation_id == identifier,
                    operation_step.c.current_attempt_id == authority.command.context.attempt_id,
                    operation_step.c.effect_knowledge == "none",
                )
                .values(inputs=authority.model_dump(mode="json"), effect_knowledge="unknown")
            ).rowcount
            if changed != 1:
                return False
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    effect_knowledge="unknown",
                    stage="Replacing approved recovery networks",
                    revision=operation.c.revision + 1,
                    updated_at=self.clock(),
                )
            )
            return True

    # Provider work is outside transactions; failures after possible dispatch remain unknown.
    def run(self, identifier):
        ticket = self.begin(identifier)
        if ticket is None:
            return
        command, capture, observed = ticket
        try:
            facade = self.factory(command, capture, self.clock)
            authority = facade.preview(command)
            if observed_fingerprint(authority.facts) != observed:
                raise ValueError("RECOVERY_NETWORK_PREVIEW_CHANGED")
        except Exception:
            self.finish(identifier, RecoveryNetworkOutcome(effect="none"))
            return
        if not self.dispatch(identifier, authority):
            return
        try:
            outcome = facade.apply(authority, before_write=lambda: self.write_allowed(identifier))
        except Exception:
            outcome = RecoveryNetworkOutcome(effect="unknown")
        self.finish(identifier, outcome)

    # Recheck loaded policy and exact ownership after provider preflight, immediately before send.
    def write_allowed(self, identifier):
        with self.engine.begin() as connection:
            locked = self.locked(connection, identifier)
            if locked is None:
                return False
            row, frozen, child = locked
            return (
                row["state"] == "running"
                and self.current(connection, row, frozen, child) is not None
            )

    # Only the current active operation publishes; a late callback cannot clear a held attempt.
    def finish(self, identifier, outcome):
        with self.engine.begin() as connection:
            locked = self.locked(connection, identifier)
            if locked is None:
                return
            row, frozen, child = locked
            if row["state"] == "running":
                self.complete(connection, row, frozen, child, outcome)

    # Retain applied older facts without claiming current readiness; unknown effects keep the fence.
    def complete(self, connection, row, frozen, child, outcome):
        effect = outcome.effect
        current = self.current(connection, row, frozen, child) is not None
        state = (
            "verified"
            if effect == "known" and current
            else "superseded"
            if effect == "known"
            else "unknown"
            if effect == "unknown"
            else "blocked"
        )
        code = "RECOVERY_NETWORK_" + state.upper()
        at, event = self.clock(), uuid4()
        proof = RecoveryNetworkEvidence(
            operation_id=row["id"],
            tenancy_id=child["id"],
            snapshot=frozen.intent.snapshot,
            effect=effect,
            state=state,
            safe_code=code,
            checked_at=at,
            capture=outcome.capture,
        )
        data = proof.model_dump(mode="json")
        connection.execute(
            audit_event.insert().values(
                id=event,
                workspace_id=self.workspace,
                operation_id=row["id"],
                actor="otm-worker:recovery-network",
                actor_subject="otm-worker:recovery-network",
                actor_snapshot={"kind": "worker", "subject": "recovery-network"},
                kind="recovery_network_outcome",
                at=at,
                contract_version=proof.contract_version,
                data=data,
                data_hash=canonical_hash(data),
            )
        )
        connection.execute(
            update(operation_step)
            .where(
                operation_step.c.workspace_id == self.workspace,
                operation_step.c.operation_id == row["id"],
            )
            .values(
                state="verified" if state == "verified" else "needs_attention",
                effect_knowledge=effect,
                last_outcome=data,
                verified_at=at if state == "verified" else None,
                evidence_event_id=event,
            )
        )
        connection.execute(
            update(operation)
            .where(operation.c.id == row["id"])
            .values(
                state="succeeded"
                if state == "verified"
                else "needs_attention"
                if effect == "unknown"
                else "failed",
                effect_knowledge=effect,
                stage=code,
                completed_at=at,
                updated_at=at,
                revision=operation.c.revision + 1,
            )
        )
        if effect != "unknown":
            connection.execute(
                update(tenancy)
                .where(
                    tenancy.c.id == child["id"],
                    tenancy.c.operation_id == row["id"],
                )
                .values(operation_id=None)
            )
