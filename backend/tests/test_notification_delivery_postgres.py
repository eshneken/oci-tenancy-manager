"""Disposable PostgreSQL notification staging, no-duplicate delivery and append-only boundaries."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import DBAPIError
from test_operation_responsibility_postgres import colleague, pending
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.email_policy import MailPolicy
from otm.notifications.contracts import DeliveryResult
from otm.notifications.service import LifecycleNotifier, list_for_operation
from otm.notifications.worker import NotificationDeliveryWorker, NotificationEnqueuer
from otm.operations.responsibility import ResponsibilityCommand, take_responsibility
from otm.storage.enqueue import workspace_queue
from otm.storage.tables import audit_event, notification_outbox, operation

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Real native queue insertion occurs on the same PostgreSQL transaction as frozen message admission.
def email_case(c):
    policy = MailPolicy(environment="staging", email_override="capture@example.test")
    enqueue = NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    notifier = LifecycleNotifier(policy, enqueue)
    transport = Mock(profile_hash=None)
    worker = NotificationDeliveryWorker(
        c.engine, c.policy.workspace_id, c.clock, lambda: policy, transport, enqueue
    )
    actor = colleague(c, "Synthetic Mail Admin")
    identifier, _ = pending(c, actor)
    with c.engine.begin() as connection:
        row = (
            connection.execute(
                select(operation).where(operation.c.id == identifier).with_for_update()
            )
            .mappings()
            .one()
        )
        notification = notifier.stage(connection, row, c.clock())
        assert notifier.stage(connection, row, c.clock()) == notification
    return policy, notifier, transport, worker, actor, identifier, notification


# Read authoritative heads independently; all assertions remain scoped to the synthetic
# installation.
def email_row(c, identifier):
    with c.engine.connect() as connection:
        return dict(
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.workspace_id == c.policy.workspace_id,
                    notification_outbox.c.id == identifier,
                )
            )
            .mappings()
            .one()
        )


# SMTP accepted means one submission, immutable intent, scoped display and no repeat on native
# replay.
def test_delivery_acceptance_and_storage_guards(workflow_case):
    c = workflow_case
    _, _, transport, worker, _, operation_id, identifier = email_case(c)
    original = email_row(c, identifier)
    transport.send.return_value = DeliveryResult(state="accepted", safe_code="SMTP_ACCEPTED")
    worker.run(identifier)
    worker.run(identifier)
    assert transport.send.call_count == 1
    saved = email_row(c, identifier)
    assert saved["state"] == "sent" and saved["attempts"] == 1 and saved["sent_at"]
    assert saved["intent"] == original["intent"]
    with c.engine.connect() as connection:
        assert len(list_for_operation(connection, c.policy.workspace_id, operation_id)) == 1
        assert list_for_operation(connection, "foreign-workspace", operation_id) == ()
        payloads = (
            connection.execute(
                text(
                    "SELECT args FROM public.procrastinate_jobs "
                    "WHERE task_name='otm.lifecycle_email'"
                )
            )
            .scalars()
            .all()
        )
        assert payloads and all(set(payload) == {"notification_id"} for payload in payloads)
    for statement in (
        update(notification_outbox).where(notification_outbox.c.id == identifier).values(intent={}),
        update(notification_outbox)
        .where(notification_outbox.c.id == identifier)
        .values(state="pending", sent_at=None),
        notification_outbox.delete().where(notification_outbox.c.id == identifier),
        text("TRUNCATE public.otm_notification_outbox"),
    ):
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            connection.execute(statement)
    assert email_row(c, identifier) == saved


# Rejections use bounded deferred attempts, whereas a possibly accepted send is never retried.
@pytest.mark.parametrize(
    "outcome,expected,attempts", [("rejected", "failed", 3), ("uncertain", "unknown", 1)]
)
def test_retry_bound_and_unknown_never_resends(workflow_case, outcome, expected, attempts):
    c = workflow_case
    _, _, transport, worker, _, _, identifier = email_case(c)
    transport.send.return_value = DeliveryResult(
        state=outcome,
        safe_code="SMTP_REJECTED" if outcome == "rejected" else "SMTP_OUTCOME_UNKNOWN",
    )
    for _ in range(5):
        worker.run(identifier)
        c.clock.return_value += timedelta(seconds=31)
    row = email_row(c, identifier)
    assert row["state"] == expected and row["attempts"] == attempts
    assert transport.send.call_count == attempts


# A crash after sending was committed cannot be distinguished from acceptance, so replay stops.
def test_crash_and_uncertain_takeover_barrier(workflow_case):
    c = workflow_case
    policy, notifier, transport, worker, actor, operation_id, identifier = email_case(c)
    prepared = worker._prepare(identifier)
    assert prepared
    worker.run(identifier)
    assert email_row(c, identifier)["state"] == "unknown"
    replacement = colleague(c, "Synthetic Replacement")
    view = replacement.workflow.onboarding(replacement.principal, operation_id)
    take_responsibility(
        replacement.workflow,
        replacement.principal,
        operation_id,
        ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
    )
    with c.engine.begin() as connection:
        row = (
            connection.execute(
                select(operation).where(operation.c.id == operation_id).with_for_update()
            )
            .mappings()
            .one()
        )
        assert notifier.stage(connection, row, c.clock()) == identifier
        assert (
            connection.scalar(
                select(func.count())
                .select_from(notification_outbox)
                .where(notification_outbox.c.operation_id == operation_id)
            )
            == 1
        )
    transport.send.assert_not_called()


# A known-unsent takeover supersedes the old frozen recipient and admits a separate new notice.
def test_known_unsent_takeover_and_changed_profile(workflow_case):
    c = workflow_case
    _, notifier, transport, worker, _, operation_id, identifier = email_case(c)
    replacement = colleague(c, "Synthetic Replacement")
    view = replacement.workflow.onboarding(replacement.principal, operation_id)
    take_responsibility(
        replacement.workflow,
        replacement.principal,
        operation_id,
        ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
    )
    with c.engine.begin() as connection:
        row = (
            connection.execute(
                select(operation).where(operation.c.id == operation_id).with_for_update()
            )
            .mappings()
            .one()
        )
        new_id = notifier.stage(connection, row, c.clock())
    assert new_id != identifier and email_row(c, identifier)["state"] == "superseded"
    transport.profile_hash = "0" * 64
    worker.run(new_id)
    assert email_row(c, new_id)["safe_code"] == "EMAIL_TRANSPORT_CHANGED"
    assert email_row(c, new_id)["state"] == "blocked"
    transport.send.assert_not_called()


# An audit write failure cannot leave a frozen notice or native job accepted without its evidence.
def test_email_staging_rolls_back_with_audit_failure(workflow_case):
    c = workflow_case
    policy = MailPolicy(environment="staging", email_override="capture@example.test")
    notifier = LifecycleNotifier(
        policy, NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    )
    actor = colleague(c, "Synthetic Mail Admin")
    operation_id, _ = pending(c, actor)
    with c.engine.connect() as connection:
        before = connection.scalar(select(func.count()).select_from(notification_outbox))
        audits = connection.scalar(select(func.count()).select_from(audit_event))

    # Inject only the email evidence statement, leaving all unrelated lifecycle/setup events intact.
    def fail_email_audit(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.audit_event"):
            raise RuntimeError("synthetic audit failure")

    event.listen(c.engine, "before_cursor_execute", fail_email_audit)
    try:
        with pytest.raises(RuntimeError), c.engine.begin() as connection:
            row = (
                connection.execute(
                    select(operation).where(operation.c.id == operation_id).with_for_update()
                )
                .mappings()
                .one()
            )
            notifier.stage(connection, row, c.clock())
    finally:
        event.remove(c.engine, "before_cursor_execute", fail_email_audit)
    with c.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(notification_outbox)) == before
        assert connection.scalar(select(func.count()).select_from(audit_event)) == audits


# Returning to an earlier administrator is a fresh explicit responsibility event, not a hook replay.
def test_known_unsent_responsibility_cycle_gets_fresh_notice(workflow_case):
    c = workflow_case
    _, notifier, _, _, actor, operation_id, first_id = email_case(c)
    replacement = colleague(c, "Synthetic Replacement")
    ids = [first_id]
    for next_actor in (replacement, actor):
        view = next_actor.workflow.onboarding(next_actor.principal, operation_id)
        take_responsibility(
            next_actor.workflow,
            next_actor.principal,
            operation_id,
            ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
        )
        with c.engine.begin() as connection:
            row = (
                connection.execute(
                    select(operation).where(operation.c.id == operation_id).with_for_update()
                )
                .mappings()
                .one()
            )
            ids.append(notifier.stage(connection, row, c.clock()))
    assert len(set(ids)) == 3
    assert [email_row(c, identifier)["state"] for identifier in ids] == [
        "superseded",
        "superseded",
        "pending",
    ]


# Even the table owner cannot rewrite a pending recipient, while runtime roles have only head
# grants.
def test_pending_intent_and_runtime_column_boundaries(workflow_case):
    from psycopg import sql

    c = workflow_case
    _, _, _, _, _, _, identifier = email_case(c)
    for statement in (
        update(notification_outbox)
        .where(notification_outbox.c.id == identifier)
        .values(intent_hash="0" * 64),
        update(notification_outbox)
        .where(notification_outbox.c.id == identifier)
        .values(operation_id=uuid4()),
        update(notification_outbox)
        .where(notification_outbox.c.id == identifier)
        .values(state="sent", sent_at=c.clock()),
    ):
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            connection.execute(statement)
    role = "otm_notice_writer_" + uuid4().hex[:12]
    with c.engine.connect() as connection:
        tx = connection.begin()
        try:
            driver = connection.connection.driver_connection
            driver.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            driver.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
            driver.execute(
                sql.SQL(
                    "GRANT SELECT,UPDATE(state,safe_code,updated_at) "
                    "ON public.otm_notification_outbox TO {}"
                ).format(sql.Identifier(role))
            )
            driver.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            for column in ("intent", "intent_hash", "operation_id", "transition_key", "created_at"):
                assert not connection.scalar(
                    text(
                        "SELECT has_column_privilege(current_user,"
                        "'public.otm_notification_outbox',:c,'UPDATE')"
                    ),
                    {"c": column},
                )
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(
                    notification_outbox.delete().where(notification_outbox.c.id == identifier)
                )
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(text("TRUNCATE public.otm_notification_outbox"))
        finally:
            tx.rollback()


# Existing mail facts have a distinct read/export category without rewriting immutable history.
def test_email_audit_category_and_csv_are_separate_from_operations(workflow_case):
    import csv
    from io import StringIO

    from otm.audit.contracts import AuditExportQuery, AuditQuery
    from otm.storage.audit_directory import SqlAuditDirectory
    from otm.storage.audit_export import SqlAuditExport

    c = workflow_case
    email_case(c)
    reader = SqlAuditDirectory(c.engine)
    mail = reader.directory(c.policy.workspace_id, AuditQuery(category="email_delivery"))
    operations = reader.directory(
        c.policy.workspace_id, AuditQuery(category="operations", page_size=100)
    )
    assert mail.total == 1 and mail.items[0].kind == "email_delivery"
    assert mail.items[0].category == "email_delivery"
    assert operations.total > 0 and all(row.kind != "email_delivery" for row in operations.items)
    assert reader.directory("another-workspace", AuditQuery(category="email_delivery")).total == 0
    with c.engine.connect() as connection:
        original = (
            connection.execute(select(audit_event).where(audit_event.c.id == mail.items[0].id))
            .mappings()
            .one()
        )
    export = SqlAuditExport(c.engine, c.clock)
    for category in ("email_delivery", "operations"):
        content = export.export(c.principal, AuditExportQuery(category=category))
        rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
        assert rows and all(row["category"] == category for row in rows)
        assert all(
            (row["kind"] == "email_delivery") == (category == "email_delivery") for row in rows
        )
    all_rows = reader.directory(c.policy.workspace_id, AuditQuery(page_size=100))
    assert any(row.id == mail.items[0].id for row in all_rows.items)
    with c.engine.connect() as connection:
        after = (
            connection.execute(select(audit_event).where(audit_event.c.id == mail.items[0].id))
            .mappings()
            .one()
        )
    assert dict(after) == dict(original)


# The installed notification hook cannot roll back non-onboarding completion or failure reporting.
@pytest.mark.parametrize("outcome", ["complete", "blocked", "unexpected"])
def test_deletion_with_real_lifecycle_notification_hook(workflow_case, outcome):
    from test_organization_workflows_postgres import action, complete_setup

    from otm.providers.lifecycle import LifecycleBlocked
    from otm.storage.tables import tenancy, tenancy_membership
    from otm.tenancies.deletion import TenancyDeletionCommand
    from otm.tenancies.views import TenancyQuery

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, created = action(c, person.id, "create_tenancy")
    complete_setup(c, created.operation_id)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    preview = c.workflow.deletion_preview(c.principal, child.id)
    receipt = c.workflow.delete_tenancy(
        c.principal,
        TenancyDeletionCommand(
            client_request_key=uuid4(),
            tenancy_id=child.id,
            context=preview.context,
            confirm_deletion=True,
            confirm_shared=True,
            confirm_manager=True,
        ),
    )
    enqueue = Mock()
    c.worker.notifications = LifecycleNotifier(MailPolicy(), enqueue)
    effects = {"blocked": LifecycleBlocked("TARGET_CHANGED"), "unexpected": RuntimeError("TEST")}
    if outcome == "complete":
        c.worker.run(receipt.operation_id)
    else:
        with patch.object(c.provider, "apply", side_effect=effects[outcome]):
            c.worker.run(receipt.operation_id)
    with c.engine.connect() as connection:
        current = (
            connection.execute(select(operation).where(operation.c.id == receipt.operation_id))
            .mappings()
            .one()
        )
        status = connection.execute(
            select(tenancy.c.status).where(tenancy.c.id == child.id)
        ).scalar_one()
        links = (
            connection.execute(
                select(tenancy_membership.c.status).where(
                    tenancy_membership.c.tenancy_id == child.id
                )
            )
            .scalars()
            .all()
        )
        assert current["state"] == ("succeeded" if outcome == "complete" else "needs_attention")
        assert status == ("terminated" if outcome == "complete" else "terminating")
        assert links == (["removed"] if outcome == "complete" else ["removing"])
        notices = list_for_operation(connection, c.policy.workspace_id, receipt.operation_id)
        if outcome == "complete":
            assert notices == ()
        else:
            assert len(notices) == 1 and notices[0].state == "blocked"
            assert notices[0].original_recipient is None
            assert notices[0].safe_code == "EMAIL_ROUTE_BLOCKED"
    enqueue.enqueue.assert_not_called()
    c.worker.run(receipt.operation_id)


# Accept each workflow through real previews and grants, without editing stored intents.
def non_onboarding_case(c, action_name):
    from test_organization_fixtures import example_records
    from test_organization_workflows_postgres import action, complete_setup, feed

    from otm.tenancies.deletion import TenancyDeletionCommand
    from otm.tenancies.views import ReviewQuery, TenancyQuery

    actor = colleague(c, "Lifecycle Administrator")
    prepared = SimpleNamespace(
        **{
            **vars(c),
            "principal": actor.principal,
            "workflow": actor.workflow,
            "store": actor.store,
        }
    )
    people = {p.email: p.id for p in actor.store.head(actor.principal).people}
    owner, member = people["one@example.test"], people["engineer@example.test"]
    _, created = action(prepared, owner, "create_tenancy", tenancy_kind="shared")
    complete_setup(prepared, created.operation_id)
    child = actor.workflow.tenancies(actor.principal, TenancyQuery()).items[0]
    if action_name in {"remove_member", "transfer_owner", "offboard_person"}:
        _, joined = action(
            prepared,
            member,
            "join_shared",
            tenancy_id=child.id,
            parent_compartment_ocid=child.tenancy_ocid,
            compartment_name="member",
        )
        c.worker.run(joined.operation_id)
    if action_name == "delete_tenancy":
        preview = actor.workflow.deletion_preview(actor.principal, child.id)
        receipt = actor.workflow.delete_tenancy(
            actor.principal,
            TenancyDeletionCommand(
                client_request_key=uuid4(),
                tenancy_id=child.id,
                context=preview.context,
                confirm_deletion=True,
                confirm_shared=True,
                confirm_manager=True,
            ),
        )
    elif action_name == "offboard_person":
        feed(prepared, tuple(r for r in example_records() if r.email != "engineer@example.test"))
        review = next(
            r
            for r in actor.workflow.reviews(actor.principal, ReviewQuery()).items
            if r.person_id == member and r.kind == "PERSON_ABSENCE_REVIEW"
        )
        preview = actor.workflow.preview(actor.principal, member, review.id)
        _, receipt = action(
            prepared,
            member,
            action_name,
            review_id=review.id,
            confirm_shared=True,
            plan=tuple({"association_id": a.id, "action": "remove"} for a in preview.associations),
        )
    elif action_name == "transfer_owner":
        _, receipt = action(
            prepared,
            owner,
            action_name,
            tenancy_id=child.id,
            recipient_person_id=member,
            confirm_shared=True,
        )
    elif action_name == "remove_member":
        _, receipt = action(prepared, member, action_name, tenancy_id=child.id, confirm_shared=True)
    else:
        _, receipt = action(
            prepared,
            member,
            "join_shared",
            tenancy_id=child.id,
            parent_compartment_ocid=child.tenancy_ocid,
            compartment_name="member",
        )
    policy = MailPolicy(environment="staging", email_override="capture@example.test")
    enqueue = NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    notifier = LifecycleNotifier(policy, enqueue)
    transport = Mock(profile_hash=None)
    transport.send.return_value = DeliveryResult(state="accepted", safe_code="SMTP_ACCEPTED")
    delivery = NotificationDeliveryWorker(
        c.engine, c.policy.workspace_id, c.clock, lambda: policy, transport, enqueue
    )
    c.worker.notifications = notifier
    return actor, receipt.operation_id, notifier, delivery, transport


# Every lifecycle failure stages/delivers once; routine successes and worker replays send nothing.
@pytest.mark.parametrize(
    "action_name",
    ["join_shared", "remove_member", "transfer_owner", "offboard_person", "delete_tenancy"],
)
@pytest.mark.parametrize("outcome", ["success", "blocked", "unexpected"])
def test_non_onboarding_delivery_matrix(workflow_case, action_name, outcome):
    from otm.providers.lifecycle import LifecycleBlocked

    c = workflow_case
    actor, identifier, notifier, delivery, transport = non_onboarding_case(c, action_name)
    if outcome == "success":
        c.worker.run(identifier)
    else:
        error = LifecycleBlocked("TARGET_CHANGED") if outcome == "blocked" else RuntimeError("TEST")
        with patch.object(c.provider, "apply", side_effect=error):
            c.worker.run(identifier)
    c.worker.run(identifier)
    with c.engine.begin() as connection:
        row = (
            connection.execute(select(operation).where(operation.c.id == identifier))
            .mappings()
            .one()
        )
        assert row["state"] == ("succeeded" if outcome == "success" else "needs_attention")
        notices = list_for_operation(connection, c.policy.workspace_id, identifier)
        if outcome == "success":
            assert notices == ()
            return
        assert len(notices) == 1 and notices[0].original_recipient == actor.grant.email
        assert notices[0].recipient == "capture@example.test" and notices[0].state == "pending"
        assert notifier.stage(connection, row, c.clock()) == notices[0].id
    delivery.run(notices[0].id)
    delivery.run(notices[0].id)
    transport.send.assert_called_once()
    assert transport.send.call_args.args[0].subject == "Tenancy operation requires your attention"
    assert str(identifier) in transport.send.call_args.args[0].body
    assert email_row(c, notices[0].id)["state"] == "sent"


# Broader email loading never permits unclaimed responsibility or revoked/replaced recipient grants.
@pytest.mark.parametrize("change", ["revoked", "revision", "email", "responsible", "completed"])
def test_non_onboarding_send_time_guards(workflow_case, change):
    from otm.providers.lifecycle import LifecycleBlocked
    from otm.storage.tables import administrator

    c = workflow_case
    actor, identifier, _, delivery, transport = non_onboarding_case(c, "delete_tenancy")
    with patch.object(c.provider, "apply", side_effect=LifecycleBlocked("TARGET_CHANGED")):
        c.worker.run(identifier)
    with c.engine.begin() as connection:
        notice = (
            connection.execute(
                select(notification_outbox).where(notification_outbox.c.operation_id == identifier)
            )
            .mappings()
            .one()
        )
        if change in {"revoked", "revision", "email"}:
            values = {
                "revoked": {
                    "status": "revoked",
                    "revoked_at": c.clock(),
                    "authorization_revision": uuid4(),
                },
                "revision": {"authorization_revision": uuid4()},
                "email": {"email": "replacement@example.test"},
            }[change]
            connection.execute(
                update(administrator).where(administrator.c.id == actor.grant.id).values(**values)
            )
        else:
            values = (
                {"responsible_actor_subject": c.principal.actor.key}
                if change == "responsible"
                else {"state": "succeeded"}
            )
            connection.execute(
                update(operation).where(operation.c.id == identifier).values(**values)
            )
    if change == "responsible":
        with pytest.raises(ValueError, match="RESPONSIBILITY_PROOF_REQUIRED"):
            delivery.run(notice["id"])
    else:
        delivery.run(notice["id"])
        assert email_row(c, notice["id"])["state"] == (
            "superseded" if change == "completed" else "blocked"
        )
    transport.send.assert_not_called()
