"""Native simulated lifecycle execution with fresh authority and exact frozen registry targets."""

import json
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.operations.responsibility import execution_authority
from otm.organization.reviews import add_change
from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    operation_step,
    org_person,
    org_workspace,
    tenancy,
    tenancy_membership,
)
from otm.storage.transaction import require_transaction
from otm.tenancies.contracts import OrganizationActionOutcome, OrganizationIntent
from otm.tenancies.directory import registry_state


# Apply local provider effects only after locking the same administrator anchor as command
# admission.
class OrganizationLifecycleWorker:
    # The qualified worker engine, current sandbox loader and facade are explicit dependencies.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        facade,
        *,
        mail_policy_loader=None,
        notifications=None,
    ):
        self.engine, self.workspace, self.clock = engine, workspace, clock
        self.mail_policy_loader, self.notifications = mail_policy_loader, notifications
        self.policy_loader, self.facade = policy_loader, facade

    # A completed/replayed native delivery never repeats verified registry effects.
    def run(self, identifier):
        try:
            self._run(identifier)
        except Exception:
            # Roll back the simulated unit of work before publishing a separate safe failure.
            # If PostgreSQL is unavailable, this second transaction also fails; native failure
            # remains visible for the documented operator recovery instead of false success.
            self._record_failure(identifier)

    # Each delivery commits one local phase; human waits release the worker and database locks.
    def _run(self, identifier):
        with self.engine.begin() as connection:
            require_transaction(connection)
            anchor = connection.execute(
                select(administrator.c.id)
                .where(
                    administrator.c.workspace_id == self.workspace,
                    administrator.c.identity_kind == "local_recovery",
                    administrator.c.status == "active",
                )
                .with_for_update()
            ).scalar_one_or_none()
            if anchor is None:
                return
            state_row = (
                connection.execute(
                    select(org_workspace)
                    .where(org_workspace.c.id == self.workspace)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            row = (
                connection.execute(
                    select(operation)
                    .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["kind"] != "organization_action" or row["state"] != "queued":
                return
            event = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.workspace_id == self.workspace,
                        audit_event.c.id == row["current_intent_event_id"],
                        audit_event.c.operation_id == identifier,
                        audit_event.c.intent_revision == row["current_intent_revision"],
                    )
                )
                .mappings()
                .one()
            )
            if canonical_hash(event["data"]) != event["data_hash"]:
                raise ValueError("INVALID_ORGANIZATION_INTENT_EVIDENCE")
            frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
            intent = frozen.intent
            if (
                not isinstance(intent, OrganizationIntent)
                or frozen.actor.key != row["initiating_actor_subject"]
                or intent.workspace_id != self.workspace
            ):
                raise ValueError("INVALID_ORGANIZATION_INTENT_SCOPE")
            at = self.clock()
            completion = None
            try:
                if state_row is None:
                    raise LifecycleBlocked("TARGET_CHANGED")
                authority_id, authority_revision, authority_actor = execution_authority(
                    connection, row, frozen
                )
                grant = (
                    connection.execute(
                        select(administrator).where(
                            administrator.c.workspace_id == self.workspace,
                            administrator.c.id == authority_id,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    grant is None
                    or grant["status"] != "active"
                    or grant["authorization_revision"] != authority_revision
                    or (grant["issuer"], grant["subject"])
                    != (authority_actor.issuer, authority_actor.subject)
                ):
                    raise LifecycleBlocked("AUTHORIZATION_CHANGED")
                policy = self.policy_loader()
                if policy.execution_paused:
                    raise LifecycleBlocked("LIFECYCLE_UNAVAILABLE")
                if policy.policy.model_dump() != self.facade.policy.model_dump():
                    raise LifecycleBlocked("TARGET_CHANGED")
                if self.mail_policy_loader and (
                    intent.action
                    in {"create_tenancy", "import_tenancy", "join_shared", "transfer_owner"}
                    or any(item.action == "transfer" for item in intent.associations)
                ):
                    from otm.email_policy import EmailPolicyBlocked
                    from otm.providers.email_contacts import validate_contacts

                    try:
                        mail_policy = self.mail_policy_loader()
                        if intent.email_contacts is not None or mail_policy.environment != "local":
                            validate_contacts(mail_policy, intent)
                    except EmailPolicyBlocked:
                        raise LifecycleBlocked("EMAIL_ROUTING_CHANGED") from None
                state = registry_state(connection, self.workspace)
                self._validate(state, intent, identifier)
                if intent.baseline is not None:
                    from otm.configuration.service import published_baseline

                    # Compare the exact frozen snapshot, never the possibly newer default pointer.
                    try:
                        pinned = published_baseline(connection, self.workspace, intent.baseline.id)
                        if pinned != intent.baseline:
                            raise ValueError("BASELINE_PIN_CHANGED")
                    except (ValueError, RuntimeError, OrganizationConflict):
                        raise LifecycleBlocked("TARGET_CHANGED") from None
                if intent.onboarding_version in {1, 2, 3}:
                    from otm.tenancies.onboarding import advance

                    if not advance(connection, row, intent, self.facade, at):
                        self._stage_email(connection, identifier, at)
                        return
                completion = self.facade.apply(intent)
                self._publish(connection, state, intent, completion, identifier, at)
                code, status = "SIMULATED_LIFECYCLE_VERIFIED", "succeeded"
            except LifecycleBlocked as failure:
                code, status = failure.code, "needs_attention"
            self._finish(
                connection,
                row,
                intent,
                identifier,
                at,
                code,
                status,
                state_row is not None,
                completion,
            )

    # Notification acceptance shares the transition transaction; email itself runs in another job.
    def _stage_email(self, connection, identifier, at):
        if self.notifications is None:
            return
        row = (
            connection.execute(
                select(operation).where(
                    operation.c.workspace_id == self.workspace,
                    operation.c.id == identifier,
                )
            )
            .mappings()
            .one()
        )
        self.notifications.stage(connection, row, at)

    # Append only a closed outcome and finish the matching business operation under its row lock.
    def _finish(
        self, connection, row, intent, identifier, at, code, status, has_workspace, completion=None
    ):
        outcome = OrganizationActionOutcome(
            action=intent.action,
            safe_code=code,
            removals=completion.removals if completion and status == "succeeded" else (),
            verified_at=at if status == "succeeded" else None,
        )
        evidence_id = uuid4()
        data = outcome.model_dump(mode="json")
        connection.execute(
            audit_event.insert().values(
                id=evidence_id,
                workspace_id=self.workspace,
                operation_id=identifier,
                administrator_id=None,
                intent_revision=None,
                actor="otm-worker:organization",
                actor_subject="otm-worker:organization",
                actor_snapshot={"kind": "worker", "subject": "organization"},
                kind="organization_action_outcome",
                at=at,
                contract_version="organization-action-1",
                data=data,
                data_hash=canonical_hash(data),
            )
        )
        connection.execute(
            insert(operation_step)
            .values(
                workspace_id=self.workspace,
                operation_id=identifier,
                intent_revision=1,
                step_key="apply_lifecycle",
                intent_event_id=row["current_intent_event_id"],
                command_kind="organization_action",
                contract_version="organization-action-1",
                inputs=intent.model_dump(mode="json"),
                state="verified" if status == "succeeded" else "needs_attention",
                execution_generation=1,
                attempt_number=1,
                current_attempt_id=uuid4(),
                effect_knowledge="known" if status == "succeeded" else "none",
                last_outcome=data,
                verified_at=at if status == "succeeded" else None,
                evidence_event_id=evidence_id,
            )
            .on_conflict_do_update(
                index_elements=[
                    operation_step.c.workspace_id,
                    operation_step.c.operation_id,
                    operation_step.c.intent_revision,
                    operation_step.c.step_key,
                ],
                set_={
                    "state": "verified" if status == "succeeded" else "needs_attention",
                    "last_outcome": data,
                    "verified_at": at if status == "succeeded" else None,
                    "evidence_event_id": evidence_id,
                    "effect_knowledge": "known" if status == "succeeded" else "none",
                    "attempt_number": operation_step.c.attempt_number + 1,
                },
            )
        )
        if outcome.removals:
            from otm.tenancies.membership_access import save_removal_steps

            save_removal_steps(connection, row, outcome.removals, data, evidence_id, at)
        connection.execute(
            update(operation)
            .where(
                operation.c.workspace_id == self.workspace,
                operation.c.id == identifier,
                operation.c.state == "queued",
            )
            .values(
                state=status,
                stage="Simulated lifecycle verified"
                if status == "succeeded"
                else "Review required in tenancy context",
                # A failed later phase cannot erase already-committed setup effects.
                effect_knowledge="known" if status == "succeeded" else operation.c.effect_knowledge,
                updated_at=at,
                completed_at=at,
                revision=row["revision"] + 1,
            )
        )
        if has_workspace:
            connection.execute(
                update(org_workspace)
                .where(org_workspace.c.id == self.workspace)
                .values(registry_revision=org_workspace.c.registry_revision + 1)
            )
        self._stage_email(connection, identifier, at)

    # Preserve pending obligations on failure; never acknowledge completed OCI work or leak
    # exceptions.
    def _record_failure(self, identifier):
        with self.engine.begin() as connection:
            require_transaction(connection)
            connection.execute(
                select(administrator.c.id)
                .where(
                    administrator.c.workspace_id == self.workspace,
                    administrator.c.identity_kind == "local_recovery",
                    administrator.c.status == "active",
                )
                .with_for_update()
            ).scalar_one_or_none()
            header = connection.execute(
                select(org_workspace.c.id)
                .where(org_workspace.c.id == self.workspace)
                .with_for_update()
            ).scalar_one_or_none()
            row = (
                connection.execute(
                    select(operation)
                    .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["kind"] != "organization_action" or row["state"] != "queued":
                return
            event = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.workspace_id == self.workspace,
                        audit_event.c.id == row["current_intent_event_id"],
                        audit_event.c.operation_id == identifier,
                        audit_event.c.intent_revision == row["current_intent_revision"],
                    )
                )
                .mappings()
                .one()
            )
            if canonical_hash(event["data"]) != event["data_hash"]:
                raise ValueError("INVALID_ORGANIZATION_INTENT_EVIDENCE")
            frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
            if (
                not isinstance(frozen.intent, OrganizationIntent)
                or frozen.intent.workspace_id != self.workspace
                or frozen.actor.key != row["initiating_actor_subject"]
            ):
                raise ValueError("INVALID_ORGANIZATION_INTENT_SCOPE")
            self._finish(
                connection,
                row,
                frozen.intent,
                identifier,
                self.clock(),
                "LIFECYCLE_UNAVAILABLE",
                "needs_attention",
                header is not None,
            )

    # Scope, presence, registration, identities and all transfer recipients remain
    # dispatch-time guards.
    def _validate(self, state, intent, identifier):
        if intent.whole_tenancy_deletion:
            from otm.tenancies.deletion import validate_deletion

            return validate_deletion(state, intent, identifier)
        person = state.people.get(intent.target.person_id)
        control = state.controls.get(intent.target.person_id)
        if (
            person is None
            or control is None
            or control["pending_operation_id"] != identifier
            or control["directory_status"] == "merged"
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        if intent.action in {"create_tenancy", "import_tenancy", "join_shared"} and (
            person.profile != "employee"
            or person.email not in state.supplied
            or control["directory_status"] != "included"
        ):
            raise LifecycleBlocked(
                "PERSON_RETURNED" if intent.person_was_absent else "TARGET_CHANGED"
            )
        if intent.person_was_absent and person.email in state.supplied:
            raise LifecycleBlocked("PERSON_RETURNED")
        if (
            any(a.action == "delete" for a in intent.associations)
            and person.known_manager
            and not intent.person_was_manager
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        for item in intent.associations:
            link = next(
                (a for a in state.associations(person=person.id) if a["id"] == item.id), None
            )
            row = state.tenancies.get(item.tenancy_id)
            expected_op = None if item.action == "keep" else identifier
            if (
                link is None
                or row is None
                or row["status"] != "active"
                or link["status"] != "active"
                or (
                    row["tenancy_ocid"],
                    row["parent_tenancy_ocid"],
                    row["revision"],
                    row["operation_id"],
                    link["role"],
                    link["user_ocid"],
                    link["compartment_ocid"],
                )
                != (
                    item.tenancy_ocid,
                    item.parent_tenancy_ocid,
                    item.tenancy_revision,
                    expected_op,
                    item.role,
                    item.user_ocid,
                    item.compartment_ocid,
                )
            ):
                raise LifecycleBlocked("TARGET_CHANGED")
            if (
                row["provider_mode"] != "simulated"
                or row["parent_tenancy_ocid"] != intent.parent_tenancy_ocid
                or row["organization_id"] != intent.organization_id
                or row["tenancy_ocid"] == intent.parent_tenancy_ocid
            ):
                raise LifecycleBlocked("TARGET_CHANGED")
            if item.action == "delete" and (
                row["kind"] != "individual"
                or item.role != "owner"
                or len(state.associations(tenant=row["id"])) != 1
            ):
                raise LifecycleBlocked("TARGET_CHANGED")
            if item.action == "remove" and (
                item.role != "member"
                or not item.user_ocid
                or any(
                    other["id"] != item.id and other["user_ocid"] == item.user_ocid
                    for other in state.associations(tenant=row["id"])
                )
            ):
                # An inconsistent reused identity must not remove another member's access.
                raise LifecycleBlocked("TARGET_CHANGED")
            if item.action == "transfer":
                recipient = state.people.get(item.recipient_person_id)
                recipient_control = state.controls.get(item.recipient_person_id)
                if (
                    item.role != "owner"
                    or recipient is None
                    or recipient_control is None
                    or recipient.profile != "employee"
                    or recipient.email not in state.supplied
                    or recipient.absence_review
                    or recipient_control["directory_status"] != "included"
                    or recipient_control["pending_operation_id"] != identifier
                ):
                    raise LifecycleBlocked("TARGET_CHANGED")
        if intent.pending_tenancy_id:
            row = state.tenancies.get(intent.pending_tenancy_id)
            link = next((a for a in state.links if a["id"] == intent.pending_association_id), None)
            if (
                row is None
                or link is None
                or row["operation_id"] != identifier
                or link["operation_id"] != identifier
                or link["status"] != "pending"
                or link["person_id"] != person.id
                or link["tenancy_id"] != row["id"]
                or row["tenancy_ocid"] != intent.target.tenancy_ocid
                or row["parent_tenancy_ocid"] != intent.parent_tenancy_ocid
                or row["provider_mode"] != "simulated"
                or row["organization_id"] != intent.organization_id
            ):
                raise LifecycleBlocked("TARGET_CHANGED")
            if intent.action in {"create_tenancy", "import_tenancy"} and (
                row["status"] != "pending"
                or row.get("baseline_version_id")
                != (intent.baseline.id if intent.baseline else None)
            ):
                raise LifecycleBlocked("TARGET_CHANGED")
            if intent.action == "join_shared" and (
                row["status"] != "active" or row["kind"] != "shared"
            ):
                raise LifecycleBlocked("TARGET_CHANGED")

    # Publish exact read-back bindings before retiring access; manual resources remain owned
    # obligations.
    def _publish(self, connection, state, intent, completion, identifier, at):
        from otm.tenancies.membership_access import validate_removals

        validate_removals(intent, completion)
        if intent.whole_tenancy_deletion:
            from otm.tenancies.deletion import publish_deletion

            return publish_deletion(connection, state, intent, completion, identifier, at)
        expected = {
            item.new_association_id: (item.tenancy_ocid, item.recipient_person_id)
            for item in intent.associations
            if item.action == "transfer"
        }
        if intent.pending_association_id:
            expected[intent.pending_association_id] = (
                intent.target.tenancy_ocid,
                intent.target.person_id,
            )
        bindings = {b.association_id: b for b in completion.bindings}
        if (
            len(bindings) != len(completion.bindings)
            or set(bindings) != set(expected)
            or any((b.tenancy_ocid, b.person_id) != expected[key] for key, b in bindings.items())
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        if intent.pending_association_id:
            binding = bindings[intent.pending_association_id]
            if intent.action == "join_shared" and (
                binding.compartment_ocid is None
                or binding.parent_compartment_ocid != intent.parent_compartment_ocid
                or (
                    intent.existing_compartment_ocid is not None
                    and binding.compartment_ocid != intent.existing_compartment_ocid
                )
            ):
                raise LifecycleBlocked("TARGET_CHANGED")
            connection.execute(
                update(tenancy_membership)
                .where(
                    tenancy_membership.c.workspace_id == self.workspace,
                    tenancy_membership.c.id == intent.pending_association_id,
                )
                .values(
                    status="active",
                    user_ocid=binding.user_ocid,
                    compartment_ocid=binding.compartment_ocid,
                    operation_id=None,
                    updated_at=at,
                    revision=tenancy_membership.c.revision + 1,
                )
            )
            connection.execute(
                update(tenancy)
                .where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == intent.pending_tenancy_id,
                )
                .values(
                    status="active",
                    verified_at=at,
                    operation_id=None,
                    updated_at=at,
                    revision=tenancy.c.revision + 1,
                )
            )
        for item in intent.associations:
            if item.action == "keep":
                continue
            link = next(a for a in state.links if a["id"] == item.id)
            if item.action == "transfer":
                binding = bindings[item.new_association_id]
                for recipient_link in state.associations(
                    person=item.recipient_person_id, tenant=item.tenancy_id
                ):
                    connection.execute(
                        update(tenancy_membership)
                        .where(
                            tenancy_membership.c.workspace_id == self.workspace,
                            tenancy_membership.c.id == recipient_link["id"],
                        )
                        .values(
                            status="removed",
                            operation_id=None,
                            updated_at=at,
                            revision=recipient_link["revision"] + 1,
                        )
                    )
                connection.execute(
                    update(tenancy_membership)
                    .where(
                        tenancy_membership.c.workspace_id == self.workspace,
                        tenancy_membership.c.id == item.id,
                    )
                    .values(
                        status="removed",
                        operation_id=None,
                        cleanup_required=bool(item.compartment_ocid),
                        updated_at=at,
                        revision=link["revision"] + 1,
                    )
                )
                connection.execute(
                    tenancy_membership.insert().values(
                        id=item.new_association_id,
                        workspace_id=self.workspace,
                        tenancy_id=item.tenancy_id,
                        person_id=item.recipient_person_id,
                        role="owner",
                        status="active",
                        user_ocid=binding.user_ocid,
                        compartment_ocid=binding.compartment_ocid,
                        compartment_name=item.recipient_compartment_name,
                        parent_compartment_ocid=binding.parent_compartment_ocid,
                        created_at=at,
                        updated_at=at,
                    )
                )
            else:
                connection.execute(
                    update(tenancy_membership)
                    .where(
                        tenancy_membership.c.workspace_id == self.workspace,
                        tenancy_membership.c.id == item.id,
                    )
                    .values(
                        status="removed",
                        operation_id=None,
                        cleanup_required=item.action == "remove" and bool(item.compartment_ocid),
                        updated_at=at,
                        revision=link["revision"] + 1,
                    )
                )
            if item.action == "delete":
                from otm.storage.managed_bindings import retire_bindings

                retire_bindings(connection, self.workspace, item.tenancy_id, identifier, at)
            connection.execute(
                update(tenancy)
                .where(tenancy.c.workspace_id == self.workspace, tenancy.c.id == item.tenancy_id)
                .values(
                    status="terminated" if item.action == "delete" else "active",
                    operation_id=None,
                    updated_at=at,
                    verified_at=at,
                    revision=tenancy.c.revision + 1,
                )
            )
        remaining = connection.execute(
            select(tenancy_membership.c.id).where(
                tenancy_membership.c.workspace_id == self.workspace,
                tenancy_membership.c.person_id == intent.target.person_id,
                tenancy_membership.c.status.in_(("active", "pending", "removing")),
            )
        ).first()
        status = "included"
        person = state.people[intent.target.person_id]
        if intent.action in {
            "offboard_person",
            "remove_member",
            "delete_tenancy",
            "transfer_owner",
        }:
            status = (
                "offboarded"
                if remaining is None
                else "outside"
                if intent.action == "offboard_person" or intent.person_was_absent
                else "included"
            )
        connection.execute(
            update(org_person)
            .where(
                org_person.c.workspace_id == self.workspace,
                org_person.c.id == intent.target.person_id,
            )
            .values(
                directory_status=status,
                pending_operation_id=None,
                removed_capture_at=state.head.source_captured_at
                if status == "offboarded" and intent.person_was_absent
                else None,
            )
        )
        for recipient_id in {
            item.recipient_person_id for item in intent.associations if item.action == "transfer"
        }:
            connection.execute(
                update(org_person)
                .where(
                    org_person.c.workspace_id == self.workspace,
                    org_person.c.id == recipient_id,
                    org_person.c.pending_operation_id == identifier,
                )
                .values(pending_operation_id=None)
            )
        add_change(
            connection,
            self.workspace,
            state.head,
            person,
            "LIFECYCLE_COMPLETED",
            at,
            {
                "action": intent.action,
                "operation_id": str(identifier),
                "provider_mode": "simulated",
            },
        )
