"""Reference-only durable email jobs; SMTP runs outside transactions and uncertain sends stop."""

from datetime import timedelta
from uuid import UUID, uuid4

import procrastinate
from sqlalchemy import select, update

from otm.email_policy import EmailPolicyBlocked
from otm.notifications.contracts import (
    CostFailureNotice,
    Envelope,
    RecoveryPasswordNotice,
    RequiredUserMissingNotice,
)
from otm.notifications.service import decode_intent, record_evidence
from otm.operations.contracts import canonical_hash
from otm.operations.responsibility import execution_authority
from otm.storage.tables import administrator, notification_outbox, operation
from otm.storage.transaction import require_transaction
from otm.tenancies.onboarding import load_intent

NOTIFICATION_TASK = "otm.lifecycle_email"


# Deferral carries only a durable row reference on the exact lifecycle admission transaction.
class NotificationEnqueuer:
    # The deployment-scoped native queue already carries all operation tasks.
    def __init__(self, queue):
        self.queue = queue
        self.app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector())

    # Bounded known-rejection retries use native ETA scheduling, never a thread or sleep loop.
    def enqueue(self, connection, notification_id, *, delay_seconds=0):
        raw = require_transaction(connection)
        connection.exec_driver_sql("SET LOCAL search_path = pg_catalog, public, pg_temp")
        self.app.configure_task(
            NOTIFICATION_TASK,
            allow_unknown=True,
            queue=self.queue,
            connection=raw,
            lock="email:" + str(notification_id),
            # None means immediately eligible; host-derived zero ETAs can be ahead of DB time.
            schedule_in={"seconds": delay_seconds} if delay_seconds else None,
        ).defer(notification_id=str(notification_id))


# A delivered native job delegates to one authoritative outbox worker with no automatic native
# retry.
def register_notification_task(app, worker, queue):
    # SMTP result knowledge, rather than a generic task exception, decides whether a resend is safe.
    @app.task(name=NOTIFICATION_TASK, queue=queue, retry=False)
    def deliver(notification_id):
        worker.run(UUID(notification_id))

    return deliver


# Only the outbox head changes across delivery attempts; immutable recipient intent never retargets.
class NotificationDeliveryWorker:
    # Transport is a capability dependency, keeping tests offline and credentials outside records.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        transport,
        enqueuer,
        *,
        application_origin=None,
        cost_context_loader=None,
        presence_context_loader=None,
    ):
        self.engine, self.workspace, self.clock = engine, workspace, clock
        self.policy_loader, self.transport, self.enqueuer = policy_loader, transport, enqueuer
        self.application_origin = application_origin
        self.cost_context_loader = cost_context_loader
        self.presence_context_loader = presence_context_loader

    # A committed sending head precedes all SMTP; a crash/replayed sending head becomes unknown.
    def run(self, identifier):
        prepared = self._prepare(identifier)
        if prepared is None:
            return
        envelope, attempt_id = prepared
        if not self._preflight(identifier, attempt_id):
            return
        try:
            result = self.transport.send(envelope)
        except Exception:
            # A capability that violates its no-throw result contract may already have submitted
            # DATA.
            self._result(identifier, attempt_id, "unknown", "SMTP_OUTCOME_UNKNOWN")
            return
        state = {"accepted": "sent", "rejected": "pending", "uncertain": "unknown"}[result.state]
        self._result(identifier, attempt_id, state, result.safe_code)

    # Preserve established anchor→operation→outbox locking; staging callers already own the first
    # two.
    def _locked(self, connection, identifier):
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
        target = connection.execute(
            select(notification_outbox.c.operation_id).where(
                notification_outbox.c.workspace_id == self.workspace,
                notification_outbox.c.id == identifier,
            )
        ).scalar_one_or_none()
        if target is None:
            return None, None
        op = (
            connection.execute(
                select(operation)
                .where(
                    operation.c.workspace_id == self.workspace,
                    operation.c.id == target,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        row = (
            connection.execute(
                select(notification_outbox)
                .where(
                    notification_outbox.c.workspace_id == self.workspace,
                    notification_outbox.c.id == identifier,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        return row, op

    # Every live authority/recipient/context fence is checked before committing a new send attempt.
    def _prepare(self, identifier):
        with self.engine.begin() as connection:
            row, op = self._locked(connection, identifier)
            if row is None or row["state"] not in {"pending", "sending"}:
                return None
            at = max(self.clock(), row["updated_at"])
            if row["state"] == "sending":
                self._change(connection, row, "unknown", "SMTP_OUTCOME_UNKNOWN", at)
                return None
            if row["next_attempt_at"] and row["next_attempt_at"] > at:
                return None
            intent = decode_intent(row)
            problem = self._context_issue(connection, row, op, intent)
            if problem:
                self._change(connection, row, *problem, at)
                return None
            recipient = intent.delivery_recipient
            if row["attempts"] >= 3:
                self._change(connection, row, "failed", "EMAIL_RETRIES_EXHAUSTED", at)
                return None
            attempt = uuid4()
            connection.execute(
                update(notification_outbox)
                .where(
                    notification_outbox.c.workspace_id == self.workspace,
                    notification_outbox.c.id == identifier,
                )
                .values(
                    state="sending",
                    attempts=row["attempts"] + 1,
                    attempt_id=attempt,
                    last_attempt_at=at,
                    next_attempt_at=None,
                    updated_at=at,
                    safe_code=None,
                )
            )
            record_evidence(
                connection,
                row,
                state="sending",
                attempts=row["attempts"] + 1,
                safe_code=None,
                at=at,
            )
            if isinstance(intent, RecoveryPasswordNotice):
                requested = intent.event == "recovery_password_requested"
                return Envelope(
                    notification_id=identifier,
                    recipient=recipient,
                    subject="Recovery password requested"
                    if requested
                    else "Recovery password needs attention",
                    body=(
                        "An authorized recovery-password disclosure attempt was recorded.\n"
                        if requested
                        else "Recovery password preparation or rotation could not be verified.\n"
                    )
                    + (
                        "Original password-rotation deadline: "
                        + intent.rotation_due_at.isoformat()
                        + "\n"
                        if intent.rotation_due_at
                        else ""
                    )
                    + (
                        "Review tenancy: "
                        + intent.application_origin
                        + "/tenancies/"
                        + str(intent.tenancy_id)
                        + "\n"
                        if intent.application_origin
                        else "Sign in and open the affected tenancy.\n"
                    )
                    + "Passwords are never included in email. "
                    "Review the latest status in the application.\n",
                ), attempt
            if isinstance(intent, RequiredUserMissingNotice):
                purpose = "Automation" if intent.purpose == "automation" else "Recovery"
                return Envelope(
                    notification_id=identifier,
                    recipient=recipient,
                    subject="Required tenancy user is missing",
                    body="A qualified presence check found the required "
                    f"{purpose.lower()} user missing.\n\n"
                    + (
                        f"Review tenancy: {intent.application_origin}/tenancies/"
                        f"{intent.tenancy_id}#required-users\n"
                        if intent.application_origin
                        else "Sign in and open the tenancy's Required users section.\n"
                    )
                    + "This notice does not verify permissions or perform a repair.\n",
                ), attempt
            if isinstance(intent, CostFailureNotice):
                return Envelope(
                    notification_id=identifier,
                    recipient=recipient,
                    subject="Tenancy cost collection failed",
                    body="Current-month cost collection failed after automatic retries.\n\n"
                    + f"Review tenancy: {intent.application_origin}/tenancies/{intent.tenancy_id}\n"
                    if intent.application_origin
                    else "Sign in and open Tenancies to retry cost collection.",
                ), attempt
            return Envelope(
                notification_id=identifier,
                recipient=recipient,
                subject="Tenancy operation requires your attention"
                if intent.event == "action_required"
                else "Tenancy operation failed",
                body=f"An OCI Tenancy Manager operation requires review.\n\nOperation: {op['id']}\n"
                f"Stage: {intent.stage}\n\n"
                + (
                    f"Review operation: {intent.application_origin}/operations/{op['id']}\n"
                    if intent.application_origin
                    else "Sign in and open Operations to review it.\n"
                ),
            ), attempt

    # Reuse the same exact authority, assignment, route and transport fences at both send
    # boundaries.
    def _context_issue(self, connection, row, op, intent):
        if isinstance(intent, RecoveryPasswordNotice):
            from otm.tenancies.recovery_password_notices import delivery_issue

            return delivery_issue(self, connection, row, op, intent)
        if isinstance(intent, RequiredUserMissingNotice):
            from otm.tenancies.presence_alerts import delivery_issue

            return delivery_issue(self, connection, row, op, intent)
        if isinstance(intent, CostFailureNotice):
            return self._cost_context_issue(connection, row, op, intent)
        frozen = load_intent(connection, op, onboarding_only=False)
        authority_id, authority_revision, _ = execution_authority(connection, op, frozen)
        if (
            intent.responsible_subject != op["responsible_actor_subject"]
            or intent.intent_event_id != op["current_intent_event_id"]
            or intent.intent_hash != canonical_hash(frozen.model_dump(mode="json"))
            or intent.operation_state != op["state"]
            or intent.stage != op["stage"]
            or intent.wait_reason != op["wait_reason"]
            or authority_id != intent.administrator_id
            or authority_revision != intent.authorization_revision
        ):
            return "superseded", "EMAIL_CONTEXT_CHANGED"
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
            not grant
            or grant["status"] != "active"
            or grant["authorization_revision"] != authority_revision
            or grant["email"] != intent.original_recipient
        ):
            return "blocked", "EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE"
        try:
            recipient = self.policy_loader().guard(intent.route)
        except EmailPolicyBlocked:
            return "blocked", "EMAIL_ROUTE_BLOCKED"
        if intent.delivery_recipient != recipient:
            raise ValueError("NOTIFICATION_ROUTE_INVALID")
        if intent.application_origin != self.application_origin:
            return "blocked", "EMAIL_APPLICATION_ORIGIN_CHANGED"
        if intent.delivery_profile_hash != getattr(self.transport, "profile_hash", None):
            return "blocked", "EMAIL_TRANSPORT_CHANGED"
        return None

    # Persisted sending is rechecked just before SMTP; a known unsent context change is safe to
    # stop.
    def _preflight(self, identifier, attempt):
        with self.engine.begin() as connection:
            row, op = self._locked(connection, identifier)
            if row is None or row["state"] != "sending" or row["attempt_id"] != attempt:
                return False
            intent = decode_intent(row)
            problem = self._context_issue(connection, row, op, intent)
            if problem:
                self._change(connection, row, *problem, max(self.clock(), row["updated_at"]))
                return False
            return True

    # Attempt identity CAS prevents late or duplicate SMTP returns from rewriting an unknown
    # outcome.
    def _result(self, identifier, attempt, state, code):
        with self.engine.begin() as connection:
            row, _ = self._locked(connection, identifier)
            if row is None or row["state"] != "sending" or row["attempt_id"] != attempt:
                return
            at = max(self.clock(), row["updated_at"])
            if state == "pending" and row["attempts"] >= 3:
                state, code = "failed", "EMAIL_RETRIES_EXHAUSTED"
            self._change(connection, row, state, code, at)
            if state == "pending":
                self.enqueuer.enqueue(connection, identifier, delay_seconds=30)

    # Cost notices follow current grant/source/route authority, without lifecycle responsible
    # claims.
    def _cost_context_issue(self, connection, row, op, intent):
        from otm.financial.context import current_failure_source
        from otm.financial.notifications import recovered_after
        from otm.financial.records import decode_collection
        from otm.storage.tables import financial_collection, tenancy

        collection = (
            connection.execute(
                select(financial_collection).where(
                    financial_collection.c.workspace_id == self.workspace,
                    financial_collection.c.id == intent.collection_id,
                    financial_collection.c.operation_id == op["id"],
                    financial_collection.c.tenancy_id == intent.tenancy_id,
                )
            )
            .mappings()
            .one_or_none()
        )
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
        if (
            not grant
            or grant["status"] != "active"
            or grant["authorization_revision"] != intent.authorization_revision
            or grant["email"] != intent.original_recipient
        ):
            return "blocked", "EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE"
        if (
            not collection
            or collection["state"] != "failed"
            or collection["safe_code"] != "COST_RETRIES_EXHAUSTED"
            or collection["source_hash"] != intent.source_hash
            or collection["failure_scope_hash"] != intent.failure_scope_hash
        ):
            return "superseded", "EMAIL_CONTEXT_CHANGED"
        recovered = recovered_after(connection, self.workspace, intent.failure_scope_hash)
        if recovered and recovered >= intent.created_at:
            return "superseded", "EMAIL_CONTEXT_CHANGED"
        decode_collection(collection)
        registered = (
            connection.execute(
                select(tenancy).where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == intent.tenancy_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        # The captured target is authoritative only while registry generation/budget stay unchanged.
        if not registered or registered["status"] != "active":
            return "superseded", "EMAIL_CONTEXT_CHANGED"
        if self.cost_context_loader is None:
            return "blocked", "EMAIL_CONTEXT_CHANGED"
        current, profile = self.cost_context_loader()
        if current.execution_paused:
            return "blocked", "EMAIL_CONTEXT_CHANGED"
        policy = current.policy
        source = current_failure_source(registered, policy, profile)
        if source != intent.failure_scope_hash:
            return "superseded", "EMAIL_CONTEXT_CHANGED"
        try:
            recipient = self.policy_loader().guard(intent.route)
        except EmailPolicyBlocked:
            return "blocked", "EMAIL_ROUTE_BLOCKED"
        if recipient != intent.delivery_recipient:
            raise ValueError("NOTIFICATION_ROUTE_INVALID")
        if intent.application_origin != self.application_origin:
            return "blocked", "EMAIL_APPLICATION_ORIGIN_CHANGED"
        if intent.delivery_profile_hash != getattr(self.transport, "profile_hash", None):
            return "blocked", "EMAIL_TRANSPORT_CHANGED"
        return None

    # Head transition and append-only safe evidence always succeed or roll back together.
    def _change(self, connection, row, state, code, at):
        connection.execute(
            update(notification_outbox)
            .where(
                notification_outbox.c.workspace_id == self.workspace,
                notification_outbox.c.id == row["id"],
            )
            .values(
                state=state,
                safe_code=code,
                updated_at=at,
                next_attempt_at=at + timedelta(seconds=30) if state == "pending" else None,
                sent_at=at if state == "sent" else None,
            )
        )
        record_evidence(
            connection, row, state=state, attempts=row["attempts"], safe_code=code, at=at
        )
