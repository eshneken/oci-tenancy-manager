"""Atomically freeze and queue lifecycle notices for the responsible administrator."""

import json
from uuid import uuid4

from sqlalchemy import select, update

from otm.email_policy import EmailPolicyBlocked
from otm.notifications.contracts import (
    CostFailureNotice,
    NotificationEvidence,
    NotificationIntent,
    NotificationSummary,
)
from otm.operations.contracts import canonical_hash
from otm.operations.responsibility import execution_authority, latest_claim
from otm.storage.tables import administrator, audit_event, notification_outbox
from otm.storage.transaction import require_transaction
from otm.tenancies.onboarding import load_intent


# Reject altered persisted content before deriving any recipient, transport message or status row.
def decode_intent(row):
    if canonical_hash(row["intent"]) != row["intent_hash"]:
        raise ValueError("NOTIFICATION_INTENT_INVALID")
    model = (
        CostFailureNotice
        if row["intent"].get("contract_version") == "cost-failure-email-1"
        else NotificationIntent
    )
    frozen = model.model_validate_json(json.dumps(row["intent"]))
    if (
        frozen.operation_id != row["operation_id"]
        or frozen.original_recipient != frozen.route.original_email
        or frozen.delivery_recipient != frozen.route.effective_email
    ):
        raise ValueError("NOTIFICATION_SCOPE_INVALID")
    return frozen


# Append fixed delivery-state evidence inside the same transaction as its mutable head transition.
def record_evidence(connection, row, *, state, attempts, safe_code, at):
    proof = NotificationEvidence(
        notification_id=row["id"],
        intent_hash=row["intent_hash"],
        state=state,
        attempts=attempts,
        safe_code=safe_code,
    )
    data = proof.model_dump(mode="json")
    connection.execute(
        audit_event.insert().values(
            id=uuid4(),
            workspace_id=row["workspace_id"],
            operation_id=row["operation_id"],
            actor="otm-worker:email",
            actor_subject="otm-worker:email",
            actor_snapshot={"kind": "worker", "subject": "email"},
            kind="email_delivery",
            at=at,
            contract_version=proof.contract_version,
            data=data,
            data_hash=canonical_hash(data),
        )
    )


# One lifecycle hook can be called repeatedly without routine progress or duplicate-email events.
class LifecycleNotifier:
    # Deployment routing and reference-only native deferral are explicit composition dependencies.
    def __init__(self, policy, enqueuer, *, profile_hash=None, application_origin=None):
        self.policy, self.enqueuer, self.profile_hash = policy, enqueuer, profile_hash
        self.application_origin = application_origin

    # The caller already owns lifecycle row/authority locks; email acceptance shares its
    # transaction.
    def stage(self, connection, row, at):
        require_transaction(connection)
        if row["kind"] != "organization_action":
            return None
        frozen = load_intent(connection, row)
        intent = frozen.intent
        if intent.action not in {
            "create_tenancy",
            "import_tenancy",
        } or intent.onboarding_version not in {1, 2, 3}:
            return None
        if row["state"] not in {"waiting", "needs_attention", "failed"}:
            self._supersede(connection, row, at)
            return None
        uncertain = (
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.workspace_id == row["workspace_id"],
                    notification_outbox.c.operation_id == row["id"],
                    notification_outbox.c.state.in_(("sending", "unknown")),
                )
            )
            .mappings()
            .all()
        )
        for prior in uncertain:
            prior_intent = decode_intent(prior)
            if (
                prior_intent.operation_state == row["state"]
                and prior_intent.stage == row["stage"]
                and prior_intent.wait_reason == row["wait_reason"]
            ):
                # Changing the responsible person must not turn uncertain acceptance into a resend.
                return prior["id"]
        self._supersede(connection, row, at)
        authority_id, authority_revision, _ = execution_authority(connection, row, frozen)
        grant = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == row["workspace_id"],
                    administrator.c.id == authority_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        original = grant["email"] if grant else None
        route = self.policy.route(original)
        state, code = "pending", None
        try:
            self.policy.guard(route)
        except EmailPolicyBlocked:
            state, code = "blocked", "EMAIL_ROUTE_BLOCKED"
        if (
            not grant
            or grant["status"] != "active"
            or grant["authorization_revision"] != authority_revision
        ):
            state, code = "blocked", "EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE"
        event = "terminal_failure" if row["state"] == "failed" else "action_required"
        notice = NotificationIntent(
            operation_id=row["id"],
            operation_revision=row["revision"],
            intent_event_id=row["current_intent_event_id"],
            intent_hash=canonical_hash(frozen.model_dump(mode="json")),
            responsible_subject=row["responsible_actor_subject"],
            administrator_id=authority_id,
            authorization_revision=authority_revision,
            original_recipient=original,
            delivery_recipient=route.effective_email,
            route=route,
            delivery_profile_hash=self.profile_hash,
            application_origin=self.application_origin,
            event=event,
            operation_state=row["state"],
            stage=row["stage"],
            wait_reason=row["wait_reason"],
            created_at=at,
        )
        # Progress/retries in the same human state do not manufacture repeated notices.
        claim = latest_claim(connection, row)
        transition = canonical_hash(
            {
                "operation_id": str(row["id"]),
                "responsibility_revision": claim["data"]["operation_revision"] if claim else None,
                "event": event,
                "state": row["state"],
                "stage": row["stage"],
                "wait_reason": row["wait_reason"],
                "subject": row["responsible_actor_subject"],
                "route": route.model_dump(mode="json"),
                "delivery_profile_hash": self.profile_hash,
                "application_origin": self.application_origin,
            }
        )
        previous = connection.scalar(
            select(notification_outbox.c.id).where(
                notification_outbox.c.workspace_id == row["workspace_id"],
                notification_outbox.c.operation_id == row["id"],
                notification_outbox.c.transition_key == transition,
            )
        )
        if previous:
            return previous
        identifier = uuid4()
        data = notice.model_dump(mode="json")
        values = dict(
            id=identifier,
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            transition_key=transition,
            intent=data,
            intent_hash=canonical_hash(data),
            state=state,
            attempts=0,
            created_at=at,
            updated_at=at,
            safe_code=code,
        )
        connection.execute(notification_outbox.insert().values(**values))
        record_evidence(connection, values, state=state, attempts=0, safe_code=code, at=at)
        if state == "pending":
            self.enqueuer.enqueue(connection, identifier)
        return identifier

    # Known-unsent notices can be replaced, but uncertain/accepted submissions remain immutable
    # history.
    def _supersede(self, connection, row, at):
        pending = (
            connection.execute(
                select(notification_outbox)
                .where(
                    notification_outbox.c.workspace_id == row["workspace_id"],
                    notification_outbox.c.operation_id == row["id"],
                    notification_outbox.c.state.in_(("pending", "blocked")),
                )
                .with_for_update()
            )
            .mappings()
            .all()
        )
        for previous in pending:
            intent = decode_intent(previous)
            if (
                intent.responsible_subject == row["responsible_actor_subject"]
                and intent.operation_state == row["state"]
                and intent.stage == row["stage"]
                and intent.wait_reason == row["wait_reason"]
                and intent.route.policy_hash == self.policy.fingerprint
            ):
                continue
            connection.execute(
                update(notification_outbox)
                .where(
                    notification_outbox.c.id == previous["id"],
                    notification_outbox.c.workspace_id == row["workspace_id"],
                )
                .values(state="superseded", safe_code="EMAIL_CONTEXT_CHANGED", updated_at=at)
            )
            record_evidence(
                connection,
                previous,
                state="superseded",
                attempts=previous["attempts"],
                safe_code="EMAIL_CONTEXT_CHANGED",
                at=at,
            )


# Exact operation scope and closed projection prevent the UI from exposing raw message/provider
# content.
def list_for_operation(connection, workspace, operation_id):
    rows = connection.execute(
        select(notification_outbox)
        .where(
            notification_outbox.c.workspace_id == workspace,
            notification_outbox.c.operation_id == operation_id,
        )
        .order_by(notification_outbox.c.created_at.desc(), notification_outbox.c.id)
        .limit(100)
    ).mappings()
    result = []
    for row in rows:
        intent = decode_intent(row)
        result.append(
            NotificationSummary(
                id=row["id"],
                state=row["state"],
                event=intent.event,
                recipient=intent.delivery_recipient,
                original_recipient=intent.original_recipient,
                redirected=intent.route.redirected,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                last_attempt_at=row["last_attempt_at"],
                attempts=row["attempts"],
                safe_code=row["safe_code"],
            )
        )
    return tuple(result)
