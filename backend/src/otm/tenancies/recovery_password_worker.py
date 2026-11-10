"""System-owned staged password changes and CURRENT promotion outside database transactions."""

import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import NoResultFound

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.recovery_password import (
    PasswordChange,
    PasswordVersion,
    require_password_material,
)
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    operation_step,
    org_workspace,
    tenancy,
)
from otm.storage.tables import (
    managed_object_binding as bindings,
)
from otm.storage.tables import (
    recovery_credential as heads,
)
from otm.storage.tables import (
    recovery_version as versions,
)
from otm.storage.tables import (
    user_presence_connection as connections,
)
from otm.tenancies.recovery_password_contracts import (
    RecoveryPasswordEvidence,
    RecoveryPasswordIntent,
)
from otm.tenancies.recovery_password_records import location_of, record_event


# Rotation is a system obligation even if the requesting human no longer has access.
class RecoveryPasswordWorker:
    # No cloud adapter or credential fallback is inferred from missing explicit dependencies.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        vault,
        target,
        enqueuer,
        organization_enqueuer,
        *,
        notifier=None,
    ):
        self.engine, self.workspace, self.clock = engine, workspace, clock
        self.policy_loader, self.vault, self.target = policy_loader, vault, target
        self.enqueuer, self.organization_enqueuer = enqueuer, organization_enqueuer
        self.notifier = notifier

    # Lock the administrator anchor, workspace, operation, child and credential in existing order.
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
            select(org_workspace.c.id)
            .where(
                org_workspace.c.id == self.workspace,
            )
            .with_for_update()
        ).scalar_one()
        row = (
            connection.execute(
                select(operation)
                .where(
                    operation.c.workspace_id == self.workspace,
                    operation.c.id == identifier,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["kind"] != "recovery_password":
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
            or not isinstance(frozen.intent, RecoveryPasswordIntent)
            or frozen.actor.key != row["initiating_actor_subject"]
            or frozen.intent.workspace_id != self.workspace
        ):
            raise ValueError("RECOVERY_PASSWORD_INTENT_INVALID")
        intent = frozen.intent
        child = (
            connection.execute(
                select(tenancy)
                .where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == intent.location.target.tenancy_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        head = (
            connection.execute(
                select(heads)
                .where(
                    heads.c.workspace_id == self.workspace,
                    heads.c.id == intent.credential_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        return row, frozen, child, head

    # Machine binding/lifecycle guards do not depend on human readiness dates for due rotation.
    def current(self, connection, row, intent, child, head):
        policy, location = self.policy_loader(), location_of(head)
        subject = location.target
        child_operation = intent.onboarding_operation_id if intent.phase == "setup" else row["id"]
        if (
            policy.execution_paused
            or policy.policy.workspace_id != self.workspace
            or policy.policy.parent_tenancy_ocid != subject.parent_tenancy_ocid
            or policy.policy.organization_id != subject.organization_id
            or (
                location != intent.location
                and not (
                    intent.phase == "setup"
                    and intent.location.secret_reference is None
                    and head["current_version_id"] is None
                    and location.model_dump(exclude={"secret_reference"})
                    == intent.location.model_dump(exclude={"secret_reference"})
                )
            )
            or head["generation"] != intent.generation
            or head["rotation_operation_id"] != row["id"]
            or head["source_operation_id"] != intent.onboarding_operation_id
            or child["tenancy_ocid"] != subject.tenancy_ocid
            or child["parent_tenancy_ocid"] != subject.parent_tenancy_ocid
            or child["provider_mode"] != "simulated"
            or child["operation_id"] not in {None, child_operation}
            or child["status"] != ("pending" if intent.phase == "setup" else "active")
            or head["state"] not in {"staging", "usable", "rotating"}
        ):
            return False
        binding = connection.execute(
            select(bindings.c.id).where(
                bindings.c.workspace_id == self.workspace,
                bindings.c.id == subject.subject_binding_id,
                bindings.c.tenancy_id == child["id"],
                bindings.c.state == "active",
                bindings.c.generation == subject.binding_generation,
                bindings.c.identity_domain_binding_id == subject.identity_domain_binding_id,
                bindings.c.scim_resource_id == subject.scim_resource_id,
                bindings.c.provider_ocid == subject.provider_ocid,
                bindings.c.created_operation_id == intent.onboarding_operation_id,
            )
        ).scalar_one_or_none()
        machine = connection.execute(
            select(connections.c.id).where(
                connections.c.workspace_id == self.workspace,
                connections.c.tenancy_id == child["id"],
                connections.c.state == "active",
                connections.c.provider_mode == "simulated",
                connections.c.created_operation_id == intent.onboarding_operation_id,
            )
        ).scalar_one_or_none()
        if binding is None or machine is None:
            return False
        if intent.phase == "rotation":
            return (
                head["exposure_generation"] == intent.exposure_generation
                and head["rotation_due_at"] == intent.due_at
            )
        parent = (
            connection.execute(
                select(operation).where(
                    operation.c.workspace_id == self.workspace,
                    operation.c.id == intent.onboarding_operation_id,
                    operation.c.state == "waiting",
                    operation.c.wait_reason == "onboarding_password",
                )
            )
            .mappings()
            .one_or_none()
        )
        if parent is None:
            return False
        from otm.operations.responsibility import execution_authority

        parent_event = connection.scalar(
            select(audit_event.c.data).where(
                audit_event.c.workspace_id == self.workspace,
                audit_event.c.id == parent["current_intent_event_id"],
            )
        )
        parent_frozen = IntentEventData.model_validate_json(json.dumps(parent_event))
        owner, revision, actor = execution_authority(connection, parent, parent_frozen)
        return (
            connection.scalar(
                select(administrator.c.id).where(
                    administrator.c.workspace_id == self.workspace,
                    administrator.c.id == owner,
                    administrator.c.status == "active",
                    administrator.c.authorization_revision == revision,
                    administrator.c.issuer == actor.issuer,
                    administrator.c.subject == actor.subject,
                )
            )
            is not None
        )

    # Qualify the canonical automation/domain connection at dispatch, not four hours ago.
    def context(self, connection, intent, operation_id, attempt):
        from otm.providers.required_user_contracts import RequiredUserReadContext

        target = intent.location.target
        machine = (
            connection.execute(
                select(connections).where(
                    connections.c.workspace_id == self.workspace,
                    connections.c.tenancy_id == target.tenancy_id,
                    connections.c.state == "active",
                    connections.c.provider_mode == "simulated",
                    connections.c.created_operation_id == intent.onboarding_operation_id,
                )
            )
            .mappings()
            .one()
        )
        rows = (
            connection.execute(
                select(bindings).where(
                    bindings.c.workspace_id == self.workspace,
                    bindings.c.tenancy_id == target.tenancy_id,
                    bindings.c.state == "active",
                    bindings.c.id.in_(
                        (
                            machine["domain_binding_id"],
                            machine["automation_binding_id"],
                            target.subject_binding_id,
                        )
                    ),
                )
            )
            .mappings()
            .all()
        )
        keyed = {item["logical_key"]: item for item in rows}
        domain, automation, recovery = (
            keyed.get("identity/domain"),
            keyed.get("identity/user/automation"),
            keyed.get("identity/user/recovery"),
        )
        if (
            len(rows) != 3
            or len(keyed) != 3
            or domain is None
            or automation is None
            or recovery is None
            or domain["id"] != target.identity_domain_binding_id
            or domain["provider_ocid"] != target.domain_ocid
            or automation["identity_domain_binding_id"] != domain["id"]
            or automation["id"] != machine["automation_binding_id"]
            or recovery["id"] != target.subject_binding_id
            or recovery["generation"] != target.binding_generation
            or recovery["scim_resource_id"] != target.scim_resource_id
            or any(
                item["created_operation_id"] != intent.onboarding_operation_id
                or item["source_evidence_event_id"] != machine["source_evidence_event_id"]
                for item in rows
            )
        ):
            raise ValueError("RECOVERY_PASSWORD_MACHINE_CONTEXT_INVALID")
        return RequiredUserReadContext(
            workspace_id=self.workspace,
            operation_id=operation_id,
            step_key="recovery_password:" + str(intent.credential_id),
            attempt_id=attempt,
            intent_revision=1,
            execution_generation=1,
            connection_id=machine["id"],
            connection_revision=machine["revision"],
        )

    # Persisted attempt context must still match current authority before every subsequent effect.
    def same_context(self, connection, row, intent, attempt):
        from otm.providers.required_user_contracts import RequiredUserReadContext

        step = (
            connection.execute(
                select(operation_step).where(
                    operation_step.c.workspace_id == self.workspace,
                    operation_step.c.operation_id == row["id"],
                    operation_step.c.current_attempt_id == attempt,
                )
            )
            .mappings()
            .one()
        )
        recorded = RequiredUserReadContext.model_validate_json(
            json.dumps(step["inputs"]["machine_context"]),
        )
        return recorded == self.context(connection, intent, row["id"], attempt)

    # Recheck between external calls without holding any database transaction around those calls.
    def still_current(self, identifier, attempt):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            return (
                values is not None
                and values[0]["state"] == "running"
                and self.current(connection, values[0], values[1].intent, values[2], values[3])
                and self.same_context(connection, values[0], values[1].intent, attempt)
            )

    # Future jobs never reserve a child; due writes recheck context and briefly acquire exclusion.
    def begin(self, identifier):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is None:
                return None
            row, frozen, child, head = values
            intent, at = frozen.intent, self.clock()
            if row["state"] == "running":
                self.finish(connection, values, "unknown", None, at)
                return None
            if row["state"] not in {"queued", "waiting"}:
                return None
            if intent.due_at and at < intent.due_at:
                self.enqueuer.enqueue(
                    connection,
                    identifier,
                    delay_seconds=max(1, int((intent.due_at - at).total_seconds()) + 1),
                )
                return None
            if intent.phase == "rotation" and (
                child["operation_id"] not in {None, identifier}
                or self.policy_loader().execution_paused
            ):
                # Known-unsent work remains due; one frozen notice covers repeated deferrals.
                connection.execute(
                    update(operation)
                    .where(operation.c.id == identifier)
                    .values(
                        state="waiting",
                        wait_reason="recovery_rotation_blocked",
                        stage="Recovery rotation overdue; waiting for execution availability",
                        updated_at=at,
                        revision=row["revision"] + 1,
                    )
                )
                if self.notifier is not None:
                    self.notifier.stage_recovery_failure(connection, row, head, at)
                self.enqueuer.enqueue(connection, identifier, delay_seconds=30)
                return None
            if not self.current(connection, row, intent, child, head):
                self.finish(connection, values, "blocked", None, at)
                return None
            if intent.phase == "rotation":
                connection.execute(
                    update(tenancy)
                    .where(
                        tenancy.c.workspace_id == self.workspace,
                        tenancy.c.id == child["id"],
                    )
                    .values(operation_id=identifier)
                )
            attempt = uuid4()
            context = self.context(connection, intent, identifier, attempt)
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    state="running",
                    wait_reason=None,
                    stage="Stage and verify recovery password",
                    effect_knowledge="none",
                    updated_at=at,
                    revision=row["revision"] + 1,
                )
            )
            connection.execute(
                update(heads)
                .where(heads.c.id == head["id"])
                .values(
                    state="rotating",
                    updated_at=at,
                )
            )
            connection.execute(
                operation_step.insert().values(
                    workspace_id=self.workspace,
                    operation_id=identifier,
                    intent_revision=1,
                    step_key="recovery_password:" + str(head["id"]),
                    intent_event_id=row["current_intent_event_id"],
                    command_kind="recovery_password",
                    contract_version=intent.contract_version,
                    inputs={"machine_context": context.model_dump(mode="json")},
                    state="running",
                    execution_generation=1,
                    attempt_number=1,
                    current_attempt_id=attempt,
                    effect_knowledge="none",
                )
            )
            return intent, attempt, context

    # Persist the exact recoverable candidate before any request to change the child's password.
    def stage(self, identifier, intent, attempt, candidate):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is None:
                return False
            row, frozen, child, head = values
            if (
                row["state"] != "running"
                or frozen.intent != intent
                or not self.current(connection, row, intent, child, head)
                or candidate.location.model_dump(exclude={"secret_reference"})
                != intent.location.model_dump(exclude={"secret_reference"})
                or (intent.phase == "rotation" and candidate.location != intent.location)
                or (intent.phase == "setup" and location_of(head).secret_reference is not None)
                or candidate.operation_id != identifier
            ):
                return False
            if not self.same_context(connection, row, intent, attempt):
                return False
            authority = self.context(connection, intent, identifier, attempt)
            version_id = uuid4()
            number = 1 + (
                connection.scalar(
                    select(func.max(versions.c.version_number)).where(
                        versions.c.workspace_id == self.workspace,
                        versions.c.credential_id == head["id"],
                    )
                )
                or 0
            )
            data = candidate.model_dump(mode="json")
            connection.execute(
                versions.insert().values(
                    id=version_id,
                    workspace_id=self.workspace,
                    credential_id=head["id"],
                    version_number=number,
                    reference=data,
                    reference_hash=canonical_hash(data),
                    created_operation_id=identifier,
                    created_at=self.clock(),
                )
            )
            connection.execute(
                update(heads)
                .where(heads.c.id == head["id"])
                .values(
                    staged_version_id=version_id,
                    location=candidate.location.model_dump(mode="json"),
                    location_hash=canonical_hash(candidate.location.model_dump(mode="json")),
                    updated_at=self.clock(),
                )
            )
            result = connection.execute(
                update(operation_step)
                .where(
                    operation_step.c.operation_id == identifier,
                    operation_step.c.current_attempt_id == attempt,
                    operation_step.c.state == "running",
                )
                .values(
                    inputs={
                        "candidate": data,
                        "machine_context": authority.model_dump(mode="json"),
                    },
                    effect_knowledge="none",
                )
            )
            return result.rowcount == 1

    # Mark possible dispatch durably after the final exact machine-context check.
    def before_write(self, identifier, attempt):
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if (
                values is None
                or values[0]["state"] != "running"
                or not self.current(
                    connection,
                    values[0],
                    values[1].intent,
                    values[2],
                    values[3],
                )
            ):
                return False
            if not self.same_context(connection, values[0], values[1].intent, attempt):
                return False
            changed = connection.execute(
                update(operation_step)
                .where(
                    operation_step.c.operation_id == identifier,
                    operation_step.c.current_attempt_id == attempt,
                    operation_step.c.state == "running",
                )
                .values(effect_knowledge="unknown")
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier)
                .values(
                    effect_knowledge="unknown",
                    updated_at=self.clock(),
                )
            )
            return changed.rowcount == 1

    # All external calls are outside transactions; exceptions never cause automatic password resend.
    def run(self, identifier):
        ticket = self.begin(identifier)
        if ticket is None:
            return
        intent, attempt, context = ticket
        state, candidate = "blocked", None
        try:
            if intent.phase == "rotation":
                original = require_password_material(self.vault.current(intent.location))
                if (
                    original.reference.location != intent.location
                    or original.reference.version != intent.expected_current
                ):
                    raise ValueError("RECOVERY_PASSWORD_CURRENT_CHANGED")
            candidate = PasswordVersion.model_validate(
                self.vault.stage(intent.location, identifier)
            )
            if not self.stage(identifier, intent, attempt, candidate):
                raise ValueError("RECOVERY_PASSWORD_CONTEXT_CHANGED")
            material = require_password_material(self.vault.candidate(candidate))
            if material.reference != candidate:
                raise ValueError("RECOVERY_PASSWORD_CANDIDATE_INVALID")
            if not self.before_write(identifier, attempt):
                raise ValueError("RECOVERY_PASSWORD_CONTEXT_CHANGED")
            state = "unknown"
            result = PasswordChange.model_validate(self.target.change(material, context))
            if result.effect == "none":
                state = "blocked"
            elif (
                result.effect == "known"
                and self.still_current(identifier, attempt)
                and self.target.verify(material, context) is True
            ):
                if not self.still_current(identifier, attempt):
                    raise ValueError("RECOVERY_PASSWORD_MACHINE_CONTEXT_CHANGED")
                self.vault.promote(candidate, intent.expected_current)
                current = require_password_material(self.vault.current(candidate.location))
                if (
                    current.reference == candidate
                    and self.still_current(identifier, attempt)
                    and self.target.verify(current, context) is True
                ):
                    state = "verified"
        except Exception:
            # No retry: errors after possible dispatch retain unknown effect knowledge.
            state = "blocked" if state == "blocked" else "unknown"
        with self.engine.begin() as connection:
            values = self.locked(connection, identifier)
            if values is not None and values[0]["state"] == "running":
                if state == "verified":
                    try:
                        if not self.same_context(connection, values[0], values[1].intent, attempt):
                            state = "superseded"
                    except (ValueError, NoResultFound):
                        state = "superseded"
                self.finish(
                    connection,
                    values,
                    state,
                    candidate if state in {"verified", "superseded"} else None,
                    self.clock(),
                )

    # Resolve only exact verified outcomes; failed/unknown rotations retain the original deadline.
    def finish(self, connection, values, state, candidate, at):
        row, frozen, child, head = values
        intent = frozen.intent
        if state == "verified" and not self.current(connection, row, intent, child, head):
            state = "superseded"
        code = {
            "verified": "RECOVERY_PASSWORD_VERIFIED",
            "blocked": "RECOVERY_PASSWORD_BLOCKED",
            "unknown": "RECOVERY_PASSWORD_UNKNOWN",
            "superseded": "RECOVERY_PASSWORD_SUPERSEDED",
        }[state]
        proof = RecoveryPasswordEvidence(
            credential_id=head["id"],
            tenancy_id=child["id"],
            operation_id=row["id"],
            phase=intent.phase,
            state=state,
            effect="known" if candidate else "none" if state == "blocked" else "unknown",
            safe_code=code,
            checked_at=at,
            version=candidate,
        )
        event = record_event(
            connection, self.workspace, row["id"], "recovery_password_outcome", proof, at
        )
        good = state == "verified"
        if good:
            connection.execute(
                update(heads)
                .where(heads.c.id == head["id"])
                .values(
                    state="usable",
                    generation=head["generation"] + (intent.phase == "rotation"),
                    current_version_id=head["staged_version_id"],
                    staged_version_id=None,
                    first_disclosure_at=None,
                    rotation_due_at=None,
                    active_window_grant_id=None,
                    updated_at=at,
                )
            )
        else:
            connection.execute(
                update(heads)
                .where(heads.c.id == head["id"])
                .values(
                    state="unknown",
                    updated_at=at,
                )
            )
        connection.execute(
            update(operation)
            .where(operation.c.id == row["id"])
            .values(
                state="succeeded" if good else "needs_attention",
                effect_knowledge=proof.effect,
                stage="Recovery password verified in simulation"
                if good
                else "Reconcile recovery password using independent recovery",
                completed_at=at,
                updated_at=at,
                revision=row["revision"] + 1,
                wait_reason=None,
            )
        )
        connection.execute(
            update(operation_step)
            .where(
                operation_step.c.operation_id == row["id"],
            )
            .values(
                state="verified" if good else "needs_attention",
                effect_knowledge=proof.effect,
                last_outcome=proof.model_dump(mode="json"),
                evidence_event_id=event,
                verified_at=at if good else None,
            )
        )
        if intent.phase == "rotation":
            connection.execute(
                update(tenancy)
                .where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == child["id"],
                    tenancy.c.operation_id == row["id"],
                )
                .values(operation_id=None)
            )
        elif good:
            self.resume_onboarding(connection, intent, at)
        else:
            from otm.tenancies.onboarding import save_step, transition
            from otm.tenancies.onboarding_contracts import OnboardingEvidence

            parent = (
                connection.execute(
                    select(operation)
                    .where(
                        operation.c.workspace_id == self.workspace,
                        operation.c.id == intent.onboarding_operation_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            save_step(
                connection,
                parent,
                "prepare_recovery_password",
                at,
                inputs={},
                payload=OnboardingEvidence(
                    step="prepare_recovery_password",
                    outcome="blocked",
                    safe_code="REQUIRED_ACCESS_UNVERIFIED",
                ),
                state="needs_attention",
            )
            transition(
                connection,
                parent,
                at,
                "needs_attention",
                "Reconcile recovery password; temporary accounts retained",
                "onboarding_password",
            )
        if not good and self.notifier is not None:
            self.notifier.stage_recovery_failure(connection, row, head, at)

    # Only coupled custody/child verification permits the parent to retire temporary administrators.
    def resume_onboarding(self, connection, intent, at):
        from otm.tenancies.onboarding import save_step, transition
        from otm.tenancies.onboarding_contracts import OnboardingEvidence

        parent = (
            connection.execute(
                select(operation)
                .where(
                    operation.c.workspace_id == self.workspace,
                    operation.c.id == intent.onboarding_operation_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        save_step(
            connection,
            parent,
            "prepare_recovery_password",
            at,
            inputs={},
            payload=OnboardingEvidence(
                step="prepare_recovery_password",
                outcome="verified",
                safe_code="ONBOARDING_VERIFIED",
            ),
        )
        transition(connection, parent, at, "queued", "Complete temporary administrator cleanup")
        self.organization_enqueuer.enqueue(connection, parent["id"])
