"""Frozen secret-free recovery notices reuse the durable email outbox."""

from uuid import uuid4

from sqlalchemy import select

from otm.email_policy import EmailPolicyBlocked
from otm.notifications.contracts import RecoveryPasswordNotice
from otm.notifications.recipients import required_user_recipients
from otm.notifications.service import record_evidence
from otm.operations.contracts import ActorIdentity, IntentEventData, canonical_hash
from otm.storage.tables import (
    administrator,
    audit_event,
    notification_outbox,
    recovery_credential,
    recovery_grant,
)
from otm.storage.transaction import require_transaction
from otm.tenancies.directory import registry_state
from otm.tenancies.recovery_password_records import location_of


# Distinct disclosure roles exclude designees and the requester from other-administrator delivery.
def recipients(state, administrators, tenancy_id, requester, *, failure=False):
    eligible = [
        grant
        for grant in administrators
        if failure
        or ActorIdentity(issuer=grant["issuer"], subject=grant["subject"]).key != requester
    ]
    contacts, issues = required_user_recipients(state, eligible, tenancy_id)
    result = {}
    for address, reasons in contacts.items():
        kept = tuple(
            reason
            for reason in reasons
            if reason.role != "designee"
            and (not failure or reason.role == "administrator")
            and (reason.role != "administrator" or eligible)
        )
        if kept:
            result[address] = kept
    issues = tuple(
        item
        for item in issues
        if item != "designee_unavailable"
        and (not failure or item == "administrator_unavailable")
        and (item != "administrator_unavailable" or eligible)
    )
    if not result and issues:
        result[None] = ()
    return result, issues


# Freeze accountable contacts, staging routes and immutable original timing in the same transaction.
def stage(notifier, connection, workspace, operation_id, head, at, *, request=None, actor=None):
    require_transaction(connection)
    state = registry_state(connection, workspace)
    administrators = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == workspace,
                administrator.c.status == "active",
            )
        )
        .mappings()
        .all()
    )
    requester = actor.key if actor is not None else head["requester_subject"]
    contacts, issues = recipients(
        state,
        administrators,
        head["tenancy_id"],
        requester,
        failure=request is None,
    )
    event = (
        "recovery_password_requested"
        if request is not None
        else "recovery_password_rotation_failed"
    )
    first = request["first_disclosure_attempt_at"] if request else head["first_disclosure_at"]
    due = request["due_at"] if request else head["rotation_due_at"]
    for original, reasons in contacts.items():
        route = notifier.policy.route(original)
        status, code = "pending", None
        try:
            notifier.policy.guard(route)
            if not reasons or not any(
                reason.person_id is not None or reason.administrator_id is not None
                for reason in reasons
            ):
                status, code = "blocked", "EMAIL_RECIPIENT_UNAVAILABLE"
        except EmailPolicyBlocked:
            status, code = "blocked", "EMAIL_ROUTE_BLOCKED"
        notice = RecoveryPasswordNotice(
            operation_id=operation_id,
            tenancy_id=head["tenancy_id"],
            credential_id=head["id"],
            grant_id=request["id"] if request else None,
            requester_subject=requester,
            organization_version_id=state.context.applied_version_id,
            configuration_id=state.context.configuration_id,
            reasons=reasons,
            routing_issues=issues,
            original_recipient=original,
            delivery_recipient=route.effective_email,
            route=route,
            application_origin=notifier.application_origin,
            delivery_profile_hash=notifier.profile_hash,
            event=event,
            first_disclosure_at=first,
            rotation_due_at=due,
            created_at=at,
        )
        transition = canonical_hash(
            {
                "event": event,
                "operation_id": str(operation_id),
                "grant_id": str(request["id"]) if request else None,
                "recipient": original,
            }
        )
        if (
            connection.scalar(
                select(notification_outbox.c.id).where(
                    notification_outbox.c.workspace_id == workspace,
                    notification_outbox.c.transition_key == transition,
                )
            )
            is not None
        ):
            continue
        data = notice.model_dump(mode="json")
        row = dict(
            id=uuid4(),
            workspace_id=workspace,
            operation_id=operation_id,
            transition_key=transition,
            intent=data,
            intent_hash=canonical_hash(data),
            state=status,
            attempts=0,
            created_at=at,
            updated_at=at,
            safe_code=code,
        )
        connection.execute(notification_outbox.insert().values(**row))
        record_evidence(connection, row, state=status, attempts=0, safe_code=code, at=at)
        if status == "pending":
            notifier.enqueuer.enqueue(connection, row["id"])


# Retain original recipients; role/contact changes can suppress, never retarget, delivery.
def delivery_issue(worker, connection, row, op, notice):
    origin = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == worker.workspace,
                audit_event.c.operation_id == op["id"],
                audit_event.c.id == op["current_intent_event_id"],
                audit_event.c.kind == "operation_intent",
            )
        )
        .mappings()
        .one()
    )
    import json

    frozen = IntentEventData.model_validate_json(json.dumps(origin["data"]))
    if canonical_hash(origin["data"]) != origin["data_hash"]:
        raise ValueError("RECOVERY_NOTICE_SOURCE_INVALID")
    head = (
        connection.execute(
            select(recovery_credential).where(
                recovery_credential.c.workspace_id == worker.workspace,
                recovery_credential.c.id == notice.credential_id,
                recovery_credential.c.tenancy_id == notice.tenancy_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if head is None or (
        frozen.intent.kind != "recovery_password"
        or frozen.intent.credential_id != notice.credential_id
        or (
            frozen.intent.location.model_dump(exclude={"secret_reference"})
            != location_of(head).model_dump(exclude={"secret_reference"})
            if frozen.intent.phase == "setup"
            else frozen.intent.location != location_of(head)
        )
    ):
        return "blocked", "EMAIL_CONTEXT_CHANGED"
    if notice.grant_id is not None:
        request = (
            connection.execute(
                select(recovery_grant).where(
                    recovery_grant.c.workspace_id == worker.workspace,
                    recovery_grant.c.id == notice.grant_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if request is None or (
            request["accepted_operation_id"] != op["id"]
            or request["credential_id"] != notice.credential_id
            or request["first_disclosure_attempt_at"] != notice.first_disclosure_at
            or request["due_at"] != notice.rotation_due_at
            or request["requesting_subject"] != notice.requester_subject
        ):
            return "blocked", "EMAIL_CONTEXT_CHANGED"
    state = registry_state(connection, worker.workspace)
    administrators = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == worker.workspace,
                administrator.c.status == "active",
            )
        )
        .mappings()
        .all()
    )
    current, _ = recipients(
        state,
        administrators,
        notice.tenancy_id,
        notice.requester_subject,
        failure=notice.event == "recovery_password_rotation_failed",
    )
    if not any(reason in current.get(notice.original_recipient, ()) for reason in notice.reasons):
        return "blocked", "EMAIL_RECIPIENT_UNAVAILABLE"
    try:
        destination = worker.policy_loader().guard(notice.route)
    except EmailPolicyBlocked:
        return "blocked", "EMAIL_ROUTE_BLOCKED"
    if destination != notice.delivery_recipient:
        raise ValueError("NOTIFICATION_ROUTE_INVALID")
    if notice.application_origin != worker.application_origin:
        return "blocked", "EMAIL_APPLICATION_ORIGIN_CHANGED"
    if notice.delivery_profile_hash != getattr(worker.transport, "profile_hash", None):
        return "blocked", "EMAIL_TRANSPORT_CHANGED"
    return None
