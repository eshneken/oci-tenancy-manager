"""Bounded administrator notices share the existing durable outbox and frozen routing guards."""

from uuid import uuid4

from sqlalchemy import select

from otm.email_policy import EmailPolicyBlocked
from otm.notifications.contracts import SigningKeyFailureNotice
from otm.notifications.service import record_evidence
from otm.operations.contracts import canonical_hash
from otm.storage.tables import administrator, notification_outbox, signing_credential, tenancy


# Repeated holds of one original operation never flood administrators or silently retarget email.
def stage_failure(notifier, connection, op, head, at):
    grants = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == op["workspace_id"],
                administrator.c.status == "active",
            )
        )
        .mappings()
        .all()
    )
    for grant in grants:
        transition = canonical_hash(
            {
                "operation": str(op["id"]),
                "administrator": str(grant["id"]),
                "event": "signing_key_attention",
            }
        )
        if connection.scalar(
            select(notification_outbox.c.id)
            .where(
                notification_outbox.c.workspace_id == op["workspace_id"],
                notification_outbox.c.operation_id == op["id"],
                notification_outbox.c.transition_key == transition,
            )
            .limit(1)
        ):
            continue
        route = notifier.policy.route(grant["email"])
        state, code = "pending", None
        try:
            notifier.policy.guard(route)
        except EmailPolicyBlocked:
            state, code = "blocked", "EMAIL_ROUTE_BLOCKED"
        notice = SigningKeyFailureNotice(
            operation_id=op["id"],
            tenancy_id=head["tenancy_id"],
            credential_id=head["id"],
            generation=head["generation"],
            administrator_id=grant["id"],
            authorization_revision=grant["authorization_revision"],
            original_recipient=grant["email"],
            delivery_recipient=route.effective_email,
            route=route,
            application_origin=notifier.application_origin,
            delivery_profile_hash=notifier.profile_hash,
            retire_at=head["retire_at"],
            created_at=at,
        )
        data = notice.model_dump(mode="json")
        values = dict(
            id=uuid4(),
            workspace_id=op["workspace_id"],
            operation_id=op["id"],
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
            notifier.enqueuer.enqueue(connection, values["id"])


# Recheck recipient grant, unresolved original operation and exact route before each SMTP boundary.
def delivery_issue(worker, connection, row, op, intent):
    head = (
        connection.execute(
            select(signing_credential).where(
                signing_credential.c.workspace_id == worker.workspace,
                signing_credential.c.id == intent.credential_id,
                signing_credential.c.tenancy_id == intent.tenancy_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    child = (
        connection.execute(
            select(tenancy).where(
                tenancy.c.workspace_id == worker.workspace,
                tenancy.c.id == intent.tenancy_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    grant = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == worker.workspace,
                administrator.c.id == intent.administrator_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        not grant
        or grant["status"] != "active"
        or grant["authorization_revision"] != intent.authorization_revision
        or grant["email"] != intent.original_recipient
    ):
        return "blocked", "EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE"
    unresolved = head is not None and (
        head["state"] == "attention"
        and op["state"] == "needs_attention"
        or head["state"] == "rotating"
        and op["state"] in {"waiting", "running", "queued"}
    )
    if (
        not unresolved
        or head["rotation_operation_id"] != op["id"]
        or head["generation"] not in {intent.generation, intent.generation + 1}
        or head["retire_at"] != intent.retire_at
        or not child
        or child["status"] not in {"active", "pending"}
    ):
        return "superseded", "EMAIL_CONTEXT_CHANGED"
    try:
        recipient = worker.policy_loader().guard(intent.route)
    except EmailPolicyBlocked:
        return "blocked", "EMAIL_ROUTE_BLOCKED"
    if recipient != intent.delivery_recipient:
        raise ValueError("NOTIFICATION_ROUTE_INVALID")
    if intent.application_origin != worker.application_origin:
        return "blocked", "EMAIL_APPLICATION_ORIGIN_CHANGED"
    if intent.delivery_profile_hash != getattr(worker.transport, "profile_hash", None):
        return "blocked", "EMAIL_TRANSPORT_CHANGED"
    return None
