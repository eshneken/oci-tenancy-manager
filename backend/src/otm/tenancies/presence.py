"""Authenticated per-child check admission and read-only current-result projection."""

import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import administrator, audit_event, operation, tenancy
from otm.storage.tables import user_presence_check as checks
from otm.tenancies.contracts import ActionReceipt
from otm.tenancies.presence_context import capture_snapshot
from otm.tenancies.presence_contracts import PresenceCheckIntent, PresenceSnapshot, UserPresenceView
from otm.tenancies.presence_records import decode_intent, decode_result, operation_rows

FRESH_FOR = timedelta(hours=24)


# One service uses the existing session/store locks and explicit deployment policy/queue.
class PresenceChecks:
    # No default adapter or authority is invented when the service is not composed.
    def __init__(self, store, *, policy, policy_loader, enqueuer):
        self.store, self.policy, self.policy_loader, self.enqueuer = (
            store,
            policy,
            policy_loader,
            enqueuer,
        )

    # Current server-side selection gates manual work and invalidates replaced provider context.
    def available_policy(self):
        if self.policy is None or self.enqueuer is None:
            return None
        current = self.policy_loader()
        return (
            self.policy if not current.execution_paused and current.policy == self.policy else None
        )

    # Freeze only a server-resolved registered child; callers cannot supply authority references.
    def snapshot(self, connection, workspace, child):
        return capture_snapshot(connection, workspace, child, self.available_policy())

    # Page refresh performs bounded local reads, never provider acquisition or historical backfill.
    def project(self, connection, workspace, child, directory):
        current = self.policy_loader() if self.policy is not None else None
        selected = self.policy if current is not None and current.policy == self.policy else None
        snapshot = capture_snapshot(connection, workspace, child, selected)
        reason = (
            "tenancy_inactive"
            if child["status"] != "active"
            else "tenancy_busy"
            if child["operation_id"]
            else "provider_unavailable"
            if selected is None or current.execution_paused or self.enqueuer is None
            else "not_configured"
            if snapshot is None
            else None
        )
        digest = canonical_hash(snapshot.model_dump(mode="json")) if snapshot else None
        pending = next(
            (
                r["id"]
                for r in operation_rows(connection, workspace, tenancy_id=child["id"], pending=True)
                if decode_intent(r).intent.context_hash == digest
            ),
            None,
        )
        latest = (
            connection.execute(
                select(checks)
                .where(
                    checks.c.workspace_id == workspace,
                    checks.c.tenancy_id == child["id"],
                    checks.c.state.in_(("complete", "unavailable", "superseded")),
                )
                .order_by(checks.c.acquisition_sequence.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if latest is not None:
            event = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.workspace_id == workspace,
                        audit_event.c.operation_id == latest["operation_id"],
                        audit_event.c.id == latest["evidence_event_id"],
                        audit_event.c.kind == "required_user_check_outcome",
                    )
                )
                .mappings()
                .one()
            )
        views = presence_views(
            snapshot, latest, event if latest is not None else None, self.store.clock()
        )
        return directory.model_copy(
            update={
                "check_available": reason is None,
                "check_unavailable_reason": reason,
                "pending_operation_id": pending,
                "users": tuple(
                    user.model_copy(
                        update={"presence": views.get(user.purpose, UserPresenceView())}
                    )
                    for user in directory.users
                ),
            }
        )

    # An identical request UUID replays its durable receipt; distinct requests remain independent.
    def start(self, principal, identifier, command):
        try:
            return self._start(principal, identifier, command)
        except (OrganizationConflict, RequestConflict):
            raise
        except (ValueError, KeyError):
            raise RuntimeError("REQUIRED_USERS_CHECK_UNAVAILABLE") from None

    # The admitted operation, snapshot, audit and native deferral share one active transaction.
    def _start(self, principal, identifier, command):
        digest = canonical_hash(
            {
                "kind": "required_user_check",
                "tenancy_id": str(identifier),
                **command.model_dump(mode="json"),
            }
        )
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            prior = (
                connection.execute(
                    select(operation).where(
                        operation.c.workspace_id == workspace,
                        operation.c.initiating_actor_subject == principal.actor.key,
                        operation.c.client_request_key == command.client_request_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if prior:
                if prior["kind"] != "required_user_check" or prior["request_digest"] != digest:
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                return receipt(prior)
            child = (
                connection.execute(
                    select(tenancy)
                    .where(tenancy.c.workspace_id == workspace, tenancy.c.id == identifier)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if child is None:
                raise OrganizationConflict("TENANCY_NOT_FOUND")
            snapshot = self.snapshot(connection, workspace, child)
            if snapshot is None:
                raise OrganizationConflict("REQUIRED_USERS_CHECK_UNAVAILABLE")
            context = snapshot.model_dump(mode="json")
            context_hash = canonical_hash(context)
            grant = (
                connection.execute(
                    select(administrator).where(
                        administrator.c.workspace_id == workspace,
                        administrator.c.issuer == principal.session.issuer,
                        administrator.c.subject == principal.session.subject,
                    )
                )
                .mappings()
                .one()
            )
            key, event = uuid4(), uuid4()
            frozen = PresenceCheckIntent(
                workspace_id=workspace,
                administrator_id=grant["id"],
                authorization_revision=grant["authorization_revision"],
                snapshot=snapshot,
                context_hash=context_hash,
                target=ConfigurationOperationTarget(
                    tenancy_ocid=snapshot.subjects[0].tenancy_ocid,
                    display_name=snapshot.tenancy_name,
                ),
            )
            data = IntentEventData(intent=frozen, actor=principal.actor).model_dump(mode="json")
            row = dict(
                id=key,
                workspace_id=workspace,
                kind="required_user_check",
                initiating_actor_subject=principal.actor.key,
                initiating_actor_snapshot=principal.actor.model_dump(mode="json"),
                responsible_actor_subject=principal.actor.key,
                client_request_key=command.client_request_key,
                request_digest=digest,
                current_intent_revision=1,
                current_intent_event_id=event,
                state="queued",
                stage="Check required-user presence",
                effect_knowledge="none",
                revision=1,
                accepted_at=at,
                created_at=at,
                updated_at=at,
            )
            connection.execute(operation.insert().values(**row))
            connection.execute(
                audit_event.insert().values(
                    id=event,
                    workspace_id=workspace,
                    operation_id=key,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="operation_intent",
                    intent_revision=1,
                    at=at,
                    contract_version=frozen.contract_version,
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            connection.execute(
                checks.insert().values(
                    operation_id=key,
                    workspace_id=workspace,
                    tenancy_id=identifier,
                    context=context,
                    context_hash=context_hash,
                    state="queued",
                    attempt_number=0,
                    created_at=at,
                )
            )
            self.enqueuer.enqueue(connection, key)
            return receipt(row)


# Joining existing work is progress, not permission or a new claim of verified access.
def receipt(row):
    return ActionReceipt(
        operation_id=row["id"],
        state=row["state"],
        provider_mode="simulated",
        accepted_at=row["accepted_at"],
    )


# Summary and detail share evidence validation, current-context matching and per-subject age rules.
def presence_views(snapshot, latest, event, now):
    if latest is None:
        return {}
    evidence = decode_result(latest, event["data"], event["data_hash"])
    # Validate the original sealed context first; only harmless registry metadata is ignored here.
    # Dispatch/publication still compare the complete snapshot, including its revision.
    stored = PresenceSnapshot.model_validate_json(json.dumps(latest["context"]))
    excluded = {"tenancy_revision", "tenancy_name"}
    if snapshot is None or snapshot.model_dump(exclude=excluded) != stored.model_dump(
        exclude=excluded
    ):
        return {}
    return {
        result.target.purpose: UserPresenceView(
            state=result.state,
            checked_at=result.captured_at,
            operation_id=latest["operation_id"],
            stale=not result.captured_at <= now < result.captured_at + FRESH_FOR,
        )
        for result in evidence.results
    }
