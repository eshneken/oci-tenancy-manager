"""Key jobs serialize one child, release SQL locks before I/O and resume exact state."""

import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.required_user_contracts import RequiredUserReadContext
from otm.providers.signing_key_rotation import ManagedSigningKey
from otm.storage.tables import (
    administrator,
    audit_event,
    financial_collection,
    managed_object_binding,
    operation,
    operation_step,
    org_workspace,
    recovery_credential,
    signing_credential,
    tenancy,
    user_presence_check,
)
from otm.tenancies.onboarding_contracts import OnboardingEvidence
from otm.tenancies.signing_key_contracts import SigningKeyEvidence, SigningKeyIntent
from otm.tenancies.signing_key_engine import (
    SigningKeyRotationEngine,
    SigningRotationBlocked,
    SigningRotationState,
)
from otm.tenancies.signing_key_records import admit, current_key


# One original-generation intent and its owning head govern every retry/duplicate.
class SigningKeyWorker:
    # Queue, provider/custody and trusted deployment policy are explicitly selected by the host.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        provider,
        enqueuer,
        organization_enqueuer,
        *,
        notifier=None,
    ):
        self.engine, self.workspace, self.clock, self.policy_loader = (
            engine,
            workspace,
            clock,
            policy_loader,
        )
        self.notifier = notifier
        self.provider, self.enqueuer, self.organization_enqueuer = (
            provider,
            enqueuer,
            organization_enqueuer,
        )
        self.machine = SigningKeyRotationEngine(provider, provider, clock)

    # Use the existing administrator/workspace/operation/child lock order.
    def locked(self, connection, identifier):
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
        if (
            row is None
            or row["kind"] != "signing_key"
            or row["state"] in {"succeeded", "cancelled", "failed"}
        ):
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
            or not isinstance(frozen.intent, SigningKeyIntent)
            or frozen.intent.workspace_id != self.workspace
            or frozen.actor.key != row["initiating_actor_subject"]
        ):
            raise ValueError("SIGNING_KEY_CONTEXT_CHANGED")
        intent = frozen.intent
        child = (
            connection.execute(
                select(tenancy)
                .where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == intent.subject.tenancy_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        head = (
            connection.execute(
                select(signing_credential)
                .where(
                    signing_credential.c.workspace_id == self.workspace,
                    signing_credential.c.id == intent.credential_id,
                    signing_credential.c.tenancy_id == child["id"],
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        return row, frozen, child, head

    # Verify immutable binding, source and policy on every dispatch/checkpoint, never infer by name.
    def current(self, connection, values):
        row, frozen, child, head = values
        intent = frozen.intent
        policy = self.policy_loader()
        if (
            policy.execution_paused
            or canonical_hash(policy.policy.model_dump(mode="json")) != intent.policy_hash
            or head["source_operation_id"] != intent.source_operation_id
            or head["source_evidence_event_id"] != intent.source_evidence_event_id
            or head["state"] == "retired"
            or head["rotation_operation_id"] != row["id"]
            or canonical_hash(head["target"]) != head["target_hash"]
            or head["target"] != intent.subject.model_dump(mode="json")
        ):
            return False
        if (child["tenancy_ocid"], child["organization_id"], child["parent_tenancy_ocid"]) != (
            intent.subject.tenancy_ocid,
            policy.policy.organization_id,
            policy.policy.parent_tenancy_ocid,
        ):
            return False
        if intent.phase == "rotation" and head["retire_at"] != intent.old.retire_at:
            return False
        source = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.workspace_id == self.workspace,
                    audit_event.c.operation_id == intent.source_operation_id,
                    audit_event.c.id == intent.source_evidence_event_id,
                    audit_event.c.kind == "onboarding_outcome",
                )
            )
            .mappings()
            .one_or_none()
        )
        if source is None or canonical_hash(source["data"]) != source["data_hash"]:
            return False
        capture = OnboardingEvidence.model_validate_json(json.dumps(source["data"])).required_users
        if capture is None or (
            capture.automation.domain_ocid,
            capture.automation.scim_resource_id,
            capture.automation.provider_ocid,
            capture.automation.user_name,
        ) != (
            intent.subject.domain_ocid,
            intent.subject.scim_resource_id,
            intent.subject.provider_ocid,
            intent.subject.user_name,
        ):
            return False
        owned = intent.source_operation_id if intent.phase == "setup" else row["id"]
        if child["status"] != ("pending" if intent.phase == "setup" else "active") or child[
            "operation_id"
        ] not in {None, owned}:
            return False
        user = (
            connection.execute(
                select(managed_object_binding).where(
                    managed_object_binding.c.workspace_id == self.workspace,
                    managed_object_binding.c.id == intent.subject.subject_binding_id,
                    managed_object_binding.c.tenancy_id == child["id"],
                    managed_object_binding.c.state == "active",
                )
            )
            .mappings()
            .one_or_none()
        )
        domain = (
            connection.execute(
                select(managed_object_binding).where(
                    managed_object_binding.c.workspace_id == self.workspace,
                    managed_object_binding.c.id == intent.subject.identity_domain_binding_id,
                    managed_object_binding.c.tenancy_id == child["id"],
                    managed_object_binding.c.state == "active",
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            user is None
            or domain is None
            or (
                user["generation"],
                user["provider_ocid"],
                user["scim_resource_id"],
                user["user_name"],
                user["identity_domain_binding_id"],
                domain["provider_ocid"],
            )
            != (
                intent.subject.binding_generation,
                intent.subject.provider_ocid,
                intent.subject.scim_resource_id,
                intent.subject.user_name,
                intent.subject.identity_domain_binding_id,
                intent.subject.domain_ocid,
            )
        ):
            return False
        from otm.storage.tables import user_presence_connection as connections

        binding = (
            connection.execute(
                select(connections).where(
                    connections.c.workspace_id == self.workspace,
                    connections.c.id == intent.connection_id,
                    connections.c.tenancy_id == child["id"],
                    connections.c.state == "active",
                )
            )
            .mappings()
            .one_or_none()
        )
        return (
            binding is not None
            and binding["revision"] == intent.connection_revision
            and binding["automation_binding_id"] == head["principal_binding_id"]
        )

    # Already dispatched reads drain first; queued reads cannot pass the later child reservation.
    def draining(self, connection, child):
        if child["operation_id"] is not None:
            return True
        if (
            connection.scalar(
                select(recovery_credential.c.id)
                .where(
                    recovery_credential.c.workspace_id == self.workspace,
                    recovery_credential.c.tenancy_id == child["id"],
                    recovery_credential.c.active_window_grant_id.is_not(None),
                    recovery_credential.c.state != "retired",
                )
                .limit(1)
            )
            is not None
        ):
            return True
        for table in (financial_collection, user_presence_check):
            if (
                connection.scalar(
                    select(table.c.operation_id)
                    .where(
                        table.c.workspace_id == self.workspace,
                        table.c.tenancy_id == child["id"],
                        table.c.state == "reading",
                    )
                    .limit(1)
                )
                is not None
            ):
                return True
        return (
            connection.scalar(
                select(operation_step.c.operation_id)
                .join(
                    operation,
                    (operation.c.workspace_id == operation_step.c.workspace_id)
                    & (operation.c.id == operation_step.c.operation_id),
                )
                .where(
                    operation_step.c.workspace_id == self.workspace,
                    operation_step.c.step_key == "configuration_check:" + str(child["id"]),
                    operation_step.c.state == "running",
                    operation.c.state == "running",
                )
                .limit(1)
            )
            is not None
        )

    # Seal closed metadata and update the existing single logical step, never any private material.
    def record(self, connection, values, state, code, checkpoint=None, current=None):
        row, frozen, child, head = values
        intent = frozen.intent
        at = self.clock()
        event = uuid4()
        proof = SigningKeyEvidence(
            operation_id=row["id"],
            credential_id=head["id"],
            tenancy_id=child["id"],
            phase=intent.phase,
            state=state,
            safe_code=code,
            checkpoint=checkpoint,
            current=current,
            checked_at=at,
        )
        data = proof.model_dump(mode="json")
        connection.execute(
            audit_event.insert().values(
                id=event,
                workspace_id=self.workspace,
                operation_id=row["id"],
                actor="otm-worker:signing-key",
                actor_subject="otm-worker:signing-key",
                actor_snapshot={"kind": "worker", "subject": "signing-key"},
                kind="signing_key_outcome",
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
                last_outcome=data,
                evidence_event_id=event,
                state="verified"
                if state in {"verified", "cancelled"}
                else "needs_attention"
                if state == "attention"
                else "running",
                verified_at=at if state == "verified" else None,
                effect_knowledge="known" if state == "verified" else "unknown",
            )
        )
        return proof

    # Persist a new attempt before external calls; the child pause is acquired only after draining.
    def begin(self, identifier):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is None:
                return None
            row, frozen, child, head = values
            intent = frozen.intent
            at = self.clock()
            # Only queued work or a known due/drain wait can acquire a fresh attempt.
            # Native redelivery must neither resume human-held work nor steal in-flight I/O.
            if row["state"] not in {"queued", "waiting"} or (
                row["state"] == "waiting"
                and row["wait_reason"] not in {"signing_rotation_due", "signing_drain"}
            ):
                return None
            if (
                intent.phase == "rotation"
                and row["state"] == "waiting"
                and row["wait_reason"] == "signing_rotation_due"
                and intent.due_at > at
            ):
                return None
            if head["state"] == "retired" or head["rotation_operation_id"] != identifier:
                return None
            if child["status"] == "terminating":
                connection.execute(
                    update(operation)
                    .where(operation.c.id == identifier)
                    .values(
                        state="waiting",
                        wait_reason="signing_drain",
                        stage="Waiting for termination outcome",
                        updated_at=at,
                    )
                )
                self.enqueuer.enqueue(connection, identifier, delay_seconds=15)
                return None
            if child["status"] not in {"active", "pending"}:
                connection.execute(
                    update(signing_credential)
                    .where(signing_credential.c.id == head["id"])
                    .values(state="retired", updated_at=at)
                )
                connection.execute(
                    update(operation)
                    .where(operation.c.id == identifier)
                    .values(
                        state="cancelled",
                        stage="Tenancy no longer active",
                        completed_at=at,
                        updated_at=at,
                    )
                )
                return None
            if intent.phase == "rotation" and child["operation_id"] != identifier:
                # Stop new admissions while already accepted work and recovery access drain.
                connection.execute(
                    update(signing_credential)
                    .where(signing_credential.c.id == head["id"])
                    .values(state="rotating", updated_at=at)
                )
                if self.draining(connection, child):
                    connection.execute(
                        update(operation)
                        .where(operation.c.id == identifier)
                        .values(
                            state="waiting",
                            wait_reason="signing_drain",
                            stage="Waiting for provider work and recovery access to finish",
                            updated_at=at,
                        )
                    )
                    if self.notifier is not None and head["retire_at"] <= at:
                        from otm.tenancies.signing_key_notices import stage_failure

                        stage_failure(self.notifier, connection, row, head, at)
                    self.enqueuer.enqueue(connection, identifier, delay_seconds=15)
                    return None
                connection.execute(
                    update(tenancy)
                    .where(
                        tenancy.c.workspace_id == self.workspace,
                        tenancy.c.id == child["id"],
                        tenancy.c.operation_id.is_(None),
                    )
                    .values(operation_id=identifier, updated_at=at)
                )
                child = dict(child) | {"operation_id": identifier}
                values = (row, frozen, child, head)
            if not self.current(connection, values):
                raise SigningRotationBlocked("SIGNING_KEY_CONTEXT_CHANGED")
            step = (
                connection.execute(
                    select(operation_step)
                    .where(
                        operation_step.c.workspace_id == self.workspace,
                        operation_step.c.operation_id == identifier,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            checkpoint = None
            if step is not None and step["last_outcome"] is not None:
                evidence = (
                    connection.execute(
                        select(audit_event).where(
                            audit_event.c.workspace_id == self.workspace,
                            audit_event.c.operation_id == identifier,
                            audit_event.c.id == step["evidence_event_id"],
                        )
                    )
                    .mappings()
                    .one()
                )
                if (
                    canonical_hash(evidence["data"]) != evidence["data_hash"]
                    or evidence["data"] != step["last_outcome"]
                ):
                    raise ValueError("SIGNING_KEY_CONTEXT_CHANGED")
                proof = SigningKeyEvidence.model_validate_json(json.dumps(evidence["data"]))
                checkpoint = proof.checkpoint
            attempt = uuid4()
            number = step["attempt_number"] + 1 if step else 1
            if step is None:
                connection.execute(
                    operation_step.insert().values(
                        workspace_id=self.workspace,
                        operation_id=identifier,
                        intent_revision=1,
                        step_key="signing_key:" + str(head["id"]),
                        intent_event_id=row["current_intent_event_id"],
                        command_kind="signing_key",
                        contract_version=intent.contract_version,
                        inputs={},
                        state="running",
                        execution_generation=number,
                        attempt_number=number,
                        current_attempt_id=attempt,
                        effect_knowledge="none",
                    )
                )
            else:
                connection.execute(
                    update(operation_step)
                    .where(
                        operation_step.c.workspace_id == self.workspace,
                        operation_step.c.operation_id == identifier,
                    )
                    .values(
                        state="running",
                        attempt_number=number,
                        execution_generation=number,
                        current_attempt_id=attempt,
                    )
                )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state="running",
                    wait_reason=None,
                    stage="Prepare automation signing credential"
                    if intent.phase == "setup"
                    else "Rotate automation signing key",
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
            context = RequiredUserReadContext(
                workspace_id=self.workspace,
                operation_id=identifier,
                step_key="signing_key:" + str(head["id"]),
                attempt_id=attempt,
                intent_revision=1,
                execution_generation=number,
                connection_id=intent.connection_id,
                connection_revision=intent.connection_revision,
            )
            return frozen, head, context, checkpoint

    # Every callback rechecks the original attempt and source after I/O, under short transactions.
    def callback(self, identifier, context, checkpoint, *, activate=False):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is None or not self.current(connection, values):
                return False
            row, frozen, child, head = values
            attempt = connection.scalar(
                select(operation_step.c.current_attempt_id).where(
                    operation_step.c.workspace_id == self.workspace,
                    operation_step.c.operation_id == identifier,
                )
            )
            if row["state"] != "running" or attempt != context.attempt_id:
                return False
            if activate:
                if (
                    current_key(head) != checkpoint.old
                    or head["generation"] != checkpoint.old.version.generation
                ):
                    return False
                key = checkpoint.uploaded
                payload = key.model_dump(mode="json")
                connection.execute(
                    update(signing_credential)
                    .where(
                        signing_credential.c.id == head["id"],
                        signing_credential.c.generation == head["generation"],
                    )
                    .values(
                        current_key=payload,
                        current_hash=canonical_hash(payload),
                        generation=key.version.generation,
                        updated_at=self.clock(),
                    )
                )
                # Retain the original retirement date until old-key absence is proved.
            elif frozen.intent.phase == "rotation":
                expected = (
                    checkpoint.uploaded
                    if checkpoint.phase in {"retire", "complete"}
                    else checkpoint.old
                )
                if current_key(head) != expected:
                    return False
            self.record(connection, values, "progress", "SIGNING_KEY_PROGRESS", checkpoint)
            return True

    # Native duplicate deliveries reuse persisted state and exact material; no in-memory scheduler.
    def run(self, identifier):
        context = None
        try:
            ticket = self.begin(identifier)
            if ticket is None:
                return
            frozen, head, context, checkpoint = ticket
            intent = frozen.intent
            if intent.phase == "setup":
                with self.engine.connect() as connection:
                    source = (
                        connection.execute(
                            select(audit_event).where(
                                audit_event.c.workspace_id == self.workspace,
                                audit_event.c.operation_id == intent.source_operation_id,
                                audit_event.c.id == intent.source_evidence_event_id,
                            )
                        )
                        .mappings()
                        .one()
                    )
                if canonical_hash(source["data"]) != source["data_hash"]:
                    raise ValueError("SIGNING_KEY_CONTEXT_CHANGED")
                capture = OnboardingEvidence.model_validate_json(
                    json.dumps(source["data"])
                ).required_users
                key = self.provider.enroll(
                    intent.subject,
                    head["id"],
                    identifier,
                    capture.automation_administrator,
                    context,
                )
                self.finish(identifier, context, key, None)
                return
            checkpoint = checkpoint or SigningRotationState(old=intent.old)
            # Yield between durable phases so higher-priority password closure jobs can run.
            checkpoint = self.machine.step(
                checkpoint,
                context,
                lambda state: self.callback(identifier, context, state),
                lambda state: self.callback(identifier, context, state, activate=True),
            )
            if checkpoint.phase == "complete":
                self.finish(identifier, context, checkpoint.uploaded, checkpoint)
            else:
                with self.engine.begin() as connection:
                    values = self.locked(connection, identifier)
                    if values is not None and self.current(connection, values):
                        attempt = connection.scalar(
                            select(operation_step.c.current_attempt_id).where(
                                operation_step.c.workspace_id == self.workspace,
                                operation_step.c.operation_id == identifier,
                            )
                        )
                        if values[0]["state"] != "running" or attempt != context.attempt_id:
                            return
                        # Commit the next phase admission and its native job together.
                        # A duplicate delivery cannot replace a still-running attempt.
                        connection.execute(
                            update(operation)
                            .where(operation.c.id == identifier)
                            .values(state="queued", updated_at=self.clock())
                        )
                        self.enqueuer.enqueue(connection, identifier)
        except Exception as error:
            code = (
                error.code
                if isinstance(error, SigningRotationBlocked)
                else "SIGNING_KEY_UNAVAILABLE"
            )
            try:
                self.fail(identifier, context, code)
            except Exception:
                raise RuntimeError("SIGNING_KEY_OUTCOME_UNAVAILABLE") from None

    # A verified successor gets its own original day29 ETA; old cleanup must already be complete.
    def finish(self, identifier, context, key, checkpoint):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is None or not self.current(connection, values):
                return
            row, frozen, child, head = values
            intent = frozen.intent
            at = self.clock()
            key = ManagedSigningKey.model_validate(key)
            if (
                key.version.credential_id != head["id"]
                or key.version.created_operation_id != identifier
                or key.version.target != intent.subject
                or key.version.generation != intent.expected_generation + 1
                or not key.version.material_created_at <= key.uploaded_at <= at < key.retire_at
            ):
                raise ValueError("SIGNING_KEY_CONTEXT_CHANGED")
            if (
                connection.scalar(
                    select(operation_step.c.current_attempt_id).where(
                        operation_step.c.operation_id == identifier
                    )
                )
                != context.attempt_id
            ):
                return
            if intent.phase == "rotation" and (
                checkpoint is None or checkpoint.phase != "complete" or current_key(head) != key
            ):
                raise ValueError("SIGNING_KEY_RETIREMENT_UNVERIFIED")
            self.record(
                connection,
                values,
                "verified",
                "SIGNING_KEY_PREPARED" if intent.phase == "setup" else "SIGNING_KEY_ROTATED",
                checkpoint,
                key,
            )
            successor = intent.model_copy(
                update={
                    "phase": "rotation",
                    "expected_generation": key.version.generation,
                    "old": key,
                    "due_at": key.retire_at - timedelta(days=1),
                }
            )
            next_id = admit(connection, successor, frozen.actor, at, self.enqueuer)
            payload = key.model_dump(mode="json")
            connection.execute(
                update(signing_credential)
                .where(signing_credential.c.id == head["id"])
                .values(
                    current_key=payload,
                    current_hash=canonical_hash(payload),
                    generation=key.version.generation,
                    state="usable",
                    retire_at=key.retire_at,
                    rotation_operation_id=next_id,
                    updated_at=at,
                )
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state="succeeded",
                    stage="Automation signer prepared"
                    if intent.phase == "setup"
                    else "Replacement verified and old key retired",
                    effect_knowledge="known",
                    completed_at=at,
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
            if intent.phase == "rotation":
                connection.execute(
                    update(tenancy)
                    .where(
                        tenancy.c.workspace_id == self.workspace,
                        tenancy.c.id == child["id"],
                        tenancy.c.operation_id == identifier,
                    )
                    .values(operation_id=None, updated_at=at)
                )
            else:
                from otm.tenancies.onboarding import save_step, transition

                parent = (
                    connection.execute(
                        select(operation)
                        .where(
                            operation.c.workspace_id == self.workspace,
                            operation.c.id == intent.source_operation_id,
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                save_step(
                    connection,
                    parent,
                    "prepare_automation_signer",
                    at,
                    inputs={},
                    payload=OnboardingEvidence(
                        step="prepare_automation_signer",
                        outcome="verified",
                        safe_code="ONBOARDING_VERIFIED",
                    ),
                )
                transition(connection, parent, at, "queued", "Continue verified tenancy setup")
                self.organization_enqueuer.enqueue(connection, parent["id"])

    # Stale callbacks cannot lose the old-key obligation or release the child pause.
    def fail(self, identifier, context, code):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is None:
                return
            row, frozen, child, head = values
            step = (
                connection.execute(
                    select(operation_step).where(
                        operation_step.c.workspace_id == self.workspace,
                        operation_step.c.operation_id == identifier,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if context is None:
                # Admission failed before an attempt could be committed. Hold the original
                # operation without inventing external effects or replacing sealed checkpoints.
                if row["state"] not in {"queued", "waiting"}:
                    return
            elif step is None or step["current_attempt_id"] != context.attempt_id:
                return
            previous = (
                SigningKeyEvidence.model_validate_json(json.dumps(step["last_outcome"])).checkpoint
                if step is not None and step["last_outcome"]
                else None
            )
            self.record(connection, values, "attention", code, previous)
            if frozen.intent.phase == "setup":
                from otm.tenancies.onboarding import save_step, transition

                parent = (
                    connection.execute(
                        select(operation)
                        .where(
                            operation.c.workspace_id == self.workspace,
                            operation.c.id == frozen.intent.source_operation_id,
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                save_step(
                    connection,
                    parent,
                    "prepare_automation_signer",
                    self.clock(),
                    inputs={},
                    payload=OnboardingEvidence(
                        step="prepare_automation_signer",
                        outcome="blocked",
                        safe_code="REQUIRED_ACCESS_UNVERIFIED",
                    ),
                    state="needs_attention",
                )
                transition(
                    connection,
                    parent,
                    self.clock(),
                    "needs_attention",
                    "Automation signer setup requires attention",
                    "onboarding_signer",
                )
            connection.execute(
                update(signing_credential)
                .where(signing_credential.c.id == head["id"])
                .values(state="attention", updated_at=self.clock())
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state="needs_attention",
                    stage="Signing-key maintenance requires attention",
                    updated_at=self.clock(),
                    effect_knowledge="unknown",
                )
            )

            if self.notifier is not None:
                from otm.tenancies.signing_key_notices import stage_failure

                stage_failure(self.notifier, connection, row, head, self.clock())
