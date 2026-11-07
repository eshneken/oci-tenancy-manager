"""Per-subject incidents reuse sealed presence evidence and the existing durable email outbox."""

from uuid import uuid4

from sqlalchemy import and_, select

from otm.email_policy import EmailPolicyBlocked
from otm.notifications.contracts import RequiredUserMissingNotice
from otm.notifications.recipients import recipient_still_authorized, required_user_recipients
from otm.notifications.service import record_evidence
from otm.operations.contracts import canonical_hash
from otm.storage.tables import administrator, audit_event, notification_outbox, tenancy
from otm.storage.tables import user_presence_check as checks
from otm.storage.transaction import require_transaction
from otm.tenancies.directory import registry_state
from otm.tenancies.presence_context import capture_snapshot, subject_scope
from otm.tenancies.presence_contracts import PresenceNoticeEpisode
from otm.tenancies.presence_records import decode_result


# The admission sequence, not callback time, owns the latest terminal evidence and incident state.
def latest_check(connection, workspace, tenancy_id):
    return (
        connection.execute(
            select(
                checks, audit_event.c.data.label("data"), audit_event.c.data_hash.label("data_hash")
            )
            .outerjoin(
                audit_event,
                and_(
                    audit_event.c.workspace_id == checks.c.workspace_id,
                    audit_event.c.operation_id == checks.c.operation_id,
                    audit_event.c.id == checks.c.evidence_event_id,
                    audit_event.c.kind == "required_user_check_outcome",
                ),
            )
            .where(
                checks.c.workspace_id == workspace,
                checks.c.tenancy_id == tenancy_id,
                checks.c.state.in_(("complete", "unavailable", "superseded")),
            )
            .order_by(checks.c.acquisition_sequence.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )


# The caller holds the child/workspace locks used by admission and seals this state atomically.
def advance_episodes(connection, row, check, snapshot, results):
    require_transaction(connection)
    latest = latest_check(connection, row["workspace_id"], snapshot.tenancy_id)
    if latest is not None and latest["acquisition_sequence"] >= check["acquisition_sequence"]:
        return None, ()
    previous = {}
    if latest is not None:
        evidence = decode_result(latest, latest["data"], latest["data_hash"])
        previous = {e.purpose: e for e in evidence.notice_episodes or ()}
    episodes, opened = [], []
    for result in results:
        purpose = result.target.purpose
        scope = subject_scope(snapshot, purpose)
        prior = previous.get(purpose)
        identifier = prior.episode_id if prior and prior.scope_hash == scope else None
        if result.state == "present":
            identifier = None
        elif result.state == "missing" and identifier is None:
            identifier = uuid4()
            opened.append(purpose)
        # Unknown carries only a matching incident. It cannot resolve or restart it.
        episodes.append(
            PresenceNoticeEpisode(purpose=purpose, scope_hash=scope, episode_id=identifier)
        )
    return tuple(episodes), tuple(opened)


# Freeze original contacts and every routing reason from one current organization snapshot.
def stage_missing(notifier, connection, row, check, snapshot, episodes, opened, at):
    require_transaction(connection)
    if not opened:
        return
    state = registry_state(connection, row["workspace_id"])
    grants = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == row["workspace_id"],
                administrator.c.status == "active",
            )
        )
        .mappings()
        .all()
    )
    recipients, issues = required_user_recipients(state, grants, snapshot.tenancy_id)
    for episode in episodes:
        if episode.purpose not in opened:
            continue
        for original, reasons in recipients.items():
            route = notifier.policy.route(original)
            status, code = "pending", None
            try:
                notifier.policy.guard(route)
                if not any(
                    r.person_id is not None or r.administrator_id is not None for r in reasons
                ):
                    status, code = "blocked", "EMAIL_RECIPIENT_UNAVAILABLE"
            except EmailPolicyBlocked:
                status, code = "blocked", "EMAIL_ROUTE_BLOCKED"
            notice = RequiredUserMissingNotice(
                operation_id=row["id"],
                tenancy_id=snapshot.tenancy_id,
                purpose=episode.purpose,
                scope_hash=episode.scope_hash,
                episode_id=episode.episode_id,
                check_context_hash=check["context_hash"],
                organization_version_id=state.context.applied_version_id,
                configuration_id=state.context.configuration_id,
                reasons=reasons,
                routing_issues=issues,
                original_recipient=original,
                delivery_recipient=route.effective_email,
                route=route,
                application_origin=notifier.application_origin,
                delivery_profile_hash=notifier.profile_hash,
                created_at=at,
            )
            transition = canonical_hash(
                {
                    "scope": episode.scope_hash,
                    "episode": str(episode.episode_id),
                    "recipient": original,
                }
            )
            prior = connection.scalar(
                select(notification_outbox.c.id).where(
                    notification_outbox.c.workspace_id == row["workspace_id"],
                    notification_outbox.c.transition_key == transition,
                )
            )
            if prior:
                continue
            data = notice.model_dump(mode="json")
            values = dict(
                id=uuid4(),
                workspace_id=row["workspace_id"],
                operation_id=row["id"],
                transition_key=transition,
                intent=data,
                intent_hash=canonical_hash(data),
                state=status,
                attempts=0,
                created_at=at,
                updated_at=at,
                safe_code=code,
            )
            connection.execute(notification_outbox.insert().values(**values))
            record_evidence(connection, values, state=status, attempts=0, safe_code=code, at=at)
            if status == "pending":
                notifier.enqueuer.enqueue(connection, values["id"])


# Original sealed Missing, the same current incident and a surviving role authorize mail.
def delivery_issue(worker, connection, row, op, notice):
    source = (
        connection.execute(
            select(
                checks, audit_event.c.data.label("data"), audit_event.c.data_hash.label("data_hash")
            )
            .outerjoin(
                audit_event,
                and_(
                    audit_event.c.workspace_id == checks.c.workspace_id,
                    audit_event.c.operation_id == checks.c.operation_id,
                    audit_event.c.id == checks.c.evidence_event_id,
                    audit_event.c.kind == "required_user_check_outcome",
                ),
            )
            .where(
                checks.c.workspace_id == worker.workspace,
                checks.c.operation_id == op["id"],
                checks.c.tenancy_id == notice.tenancy_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None or source["context_hash"] != notice.check_context_hash:
        return "superseded", "EMAIL_CONTEXT_CHANGED"
    original = decode_result(source, source["data"], source["data_hash"])
    if not any(
        r.target.purpose == notice.purpose and r.state == "missing" for r in original.results
    ) or not any(
        e.purpose == notice.purpose
        and e.scope_hash == notice.scope_hash
        and e.episode_id == notice.episode_id
        for e in original.notice_episodes or ()
    ):
        return "superseded", "EMAIL_CONTEXT_CHANGED"
    latest = latest_check(connection, worker.workspace, notice.tenancy_id)
    if latest is None:
        return "superseded", "EMAIL_CONTEXT_CHANGED"
    current_evidence = decode_result(latest, latest["data"], latest["data_hash"])
    if not any(
        e.purpose == notice.purpose
        and e.scope_hash == notice.scope_hash
        and e.episode_id == notice.episode_id
        for e in current_evidence.notice_episodes or ()
    ):
        return "superseded", "EMAIL_CONTEXT_CHANGED"
    if worker.presence_context_loader is None:
        return "blocked", "EMAIL_CONTEXT_CHANGED"
    policy = worker.presence_context_loader()
    if policy.execution_paused:
        return "blocked", "EMAIL_CONTEXT_CHANGED"
    child = (
        connection.execute(
            select(tenancy).where(
                tenancy.c.workspace_id == worker.workspace, tenancy.c.id == notice.tenancy_id
            )
        )
        .mappings()
        .one_or_none()
    )
    snapshot = (
        capture_snapshot(connection, worker.workspace, child, policy.policy) if child else None
    )
    if snapshot is None or subject_scope(snapshot, notice.purpose) != notice.scope_hash:
        return "superseded", "EMAIL_CONTEXT_CHANGED"
    state = registry_state(connection, worker.workspace)
    grants = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == worker.workspace, administrator.c.status == "active"
            )
        )
        .mappings()
        .all()
    )
    if not recipient_still_authorized(notice, state, grants):
        return "superseded", "EMAIL_RECIPIENT_CHANGED"
    try:
        recipient = worker.policy_loader().guard(notice.route)
    except EmailPolicyBlocked:
        return "blocked", "EMAIL_ROUTE_BLOCKED"
    if recipient != notice.delivery_recipient:
        raise ValueError("NOTIFICATION_ROUTE_INVALID")
    if notice.application_origin != worker.application_origin:
        return "blocked", "EMAIL_APPLICATION_ORIGIN_CHANGED"
    if notice.delivery_profile_hash != getattr(worker.transport, "profile_hash", None):
        return "blocked", "EMAIL_TRANSPORT_CHANGED"
    return None
