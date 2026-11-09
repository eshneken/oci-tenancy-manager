"""Offline required-user email tests."""

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, workflow_case
from test_user_presence_checks_postgres import presence_case

from otm.email_policy import MailPolicy
from otm.notifications.contracts import DeliveryResult
from otm.notifications.service import LifecycleNotifier, decode_intent
from otm.notifications.worker import NotificationDeliveryWorker, NotificationEnqueuer
from otm.providers.presence_simulator import simulated_presence_inspection
from otm.storage.enqueue import workspace_queue
from otm.storage.tables import administrator, notification_outbox, user_presence_check
from otm.tenancies.presence_contracts import PresenceCheckRequest

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case", "presence_case"]


# Only independent fixture facts change; expected canonical bindings and application state are
# untouched.
def missing_factory(*purposes, denied=False, unknown_purposes=()):
    # Assemble the existing provider with genuine simulated absence or denied coverage.
    def factory(snapshot, source, clock):
        inspection = simulated_presence_inspection(snapshot, source, clock)
        for purpose in purposes:
            user = getattr(source, purpose)
            inspection.provider._users.pop(
                (
                    source.workspace_id,
                    source.tenancy_ocid,
                    source.domain_ocid,
                    user.scim_resource_id,
                )
            )
        for purpose in unknown_purposes:
            user = getattr(source, purpose)
            key = (
                source.workspace_id,
                source.tenancy_ocid,
                source.domain_ocid,
                user.scim_resource_id,
            )
            inspection.provider.set_user(
                inspection.provider._users[key].model_copy(update={"fault": "denied"})
            )
        if denied:
            access = next(iter(inspection.provider._access.values()))
            inspection.provider.set_access(access.model_copy(update={"permitted": False}))
        return inspection

    return factory


# Compose real durable enqueue and email intent; submission uses an explicit offline transport
# capability.
def prepare(c):
    policy = MailPolicy(environment="staging", email_override="capture@example.test")
    enqueue = NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    notifier = LifecycleNotifier(policy, enqueue, application_origin="https://atlas.example.test")
    c.reader.notifications = notifier
    transport = Mock(profile_hash=None)
    transport.send.return_value = DeliveryResult(state="accepted", safe_code="SMTP_ACCEPTED")
    delivery = NotificationDeliveryWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        lambda: policy,
        transport,
        enqueue,
        application_origin=notifier.application_origin,
        presence_context_loader=c.loader,
    )
    return notifier, transport, delivery


# Results and queue admission go through the ordinary authenticated command and actual worker
# transactions.
def check(c, factory):
    c.clock.return_value += timedelta(seconds=1)
    c.reader.inspection_factory = factory
    command = PresenceCheckRequest(client_request_key=uuid4())
    receipt = c.service.start(c.principal, c.child.id, command)
    c.reader.run(receipt.operation_id)
    assert c.service.start(c.principal, c.child.id, command).operation_id == receipt.operation_id
    c.reader.run(receipt.operation_id)
    return receipt.operation_id


# Read only this fixture's new notice family; lifecycle history is a separate obligation.
def notices(c):
    with c.engine.connect() as connection:
        return list(
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.workspace_id == c.policy.workspace_id,
                    notification_outbox.c.intent["contract_version"].astext
                    == "required-user-missing-email-1",
                )
            ).mappings()
        )


# Repeated Missing and Unknown are one incident; verified per-subject Present alone permits relapse.
def test_presence_alert_episodes_replay_and_independent_subjects(presence_case):
    c = presence_case
    _, transport, delivery = prepare(c)
    first = check(c, missing_factory("recovery"))
    initial = notices(c)
    assert len(initial) >= 3
    assert {n["intent"]["purpose"] for n in initial} == {"recovery"}
    originals = [n["intent"]["original_recipient"] for n in initial]
    assert len(originals) == len(set(originals))
    assert all(n["intent"]["delivery_recipient"] == "capture@example.test" for n in initial)
    assert all(n["operation_id"] == first for n in initial)
    check(c, missing_factory("recovery"))
    check(c, missing_factory(denied=True))
    assert len(notices(c)) == len(initial)
    for notice in initial:
        delivery.run(notice["id"])
        delivery.run(notice["id"])
    assert transport.send.call_count == len(initial)
    assert all(n["state"] == "sent" for n in notices(c))
    check(c, missing_factory())
    check(c, missing_factory("recovery", "automation"))
    all_rows = notices(c)
    assert len(all_rows) == 3 * len(initial)
    assert {n["intent"]["purpose"] for n in all_rows} == {"automation", "recovery"}
    assert len({n["intent"]["episode_id"] for n in all_rows}) == 3


# A resolved episode or a removed recipient role cannot leak a now-obsolete alert to SMTP.
@pytest.mark.parametrize("change", ["resolved", "role", "admin", "termination", "origin"])
def test_presence_alert_delivery_rechecks_roles_and_episode(presence_case, change):
    c = presence_case
    _, transport, delivery = prepare(c)
    check(c, missing_factory("recovery"))
    rows = notices(c)
    if change == "admin":
        notice = next(
            n for n in rows if any(r["role"] == "administrator" for r in n["intent"]["reasons"])
        )
        admin = notice["intent"]["reasons"][0]["administrator_id"]
        with c.engine.begin() as connection:
            connection.execute(
                update(administrator)
                .where(administrator.c.id == admin)
                .values(authorization_revision=uuid4())
            )
    else:
        notice = next(n for n in rows if any(r["role"] == "owner" for r in n["intent"]["reasons"]))
    if change == "resolved":
        check(c, missing_factory())
    if change == "role":
        recipient = next(
            p for p in c.store.head(c.principal).people if p.email == "delegate@example.test"
        )
        _, transferred = action(
            c,
            c.person.id,
            "transfer_owner",
            tenancy_id=c.child.id,
            recipient_person_id=recipient.id,
        )
        c.worker.run(transferred.operation_id)
        assert not next(
            p for p in c.store.head(c.principal).people if p.id == c.person.id
        ).absence_review
    if change == "termination":
        from otm.tenancies.deletion import TenancyDeletionCommand

        preview = c.workflow.deletion_preview(c.principal, c.child.id)
        receipt = c.workflow.delete_tenancy(
            c.principal,
            TenancyDeletionCommand(
                client_request_key=uuid4(),
                tenancy_id=c.child.id,
                context=preview.context,
                confirm_deletion=True,
                confirm_shared=True,
                confirm_manager=True,
            ),
        )
        c.worker.run(receipt.operation_id)
    if change == "origin":
        delivery.application_origin = "https://changed.example.test"
    delivery.run(notice["id"])
    transport.send.assert_not_called()
    retained = next(n for n in notices(c) if n["id"] == notice["id"])
    assert retained["state"] in {"blocked", "superseded"}
    assert decode_intent(retained).episode_id == decode_intent(notice).episode_id


# Finishing an older acquisition cannot copy/reset current incident state, even with Present facts.
def test_presence_alert_late_completion_and_atomic_failure(presence_case):
    c = presence_case
    notifier, _, _ = prepare(c)
    first = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    ticket = c.reader.begin(first.operation_id)
    _, old, commands, source = ticket
    old_results = tuple(
        simulated_presence_inspection(ticket[0].intent.snapshot, source, c.clock).inspect(command)
        for command in commands
    )
    current = check(c, missing_factory("recovery"))
    before = notices(c)
    c.reader.finish(first.operation_id, old["attempt_id"], commands, old_results)
    check(c, missing_factory("recovery"))
    assert len(notices(c)) == len(before)
    assert all(n["operation_id"] == current for n in notices(c))
    check(c, missing_factory())
    notifier.enqueuer = Mock()
    notifier.enqueuer.enqueue.side_effect = RuntimeError("synthetic enqueue failure")
    receipt = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    c.reader.inspection_factory = missing_factory("recovery")
    with pytest.raises(RuntimeError, match="synthetic enqueue failure"):
        c.reader.run(receipt.operation_id)
    assert len(notices(c)) == len(before)
    with c.engine.connect() as connection:
        result = (
            connection.execute(
                select(user_presence_check).where(
                    user_presence_check.c.operation_id == receipt.operation_id
                )
            )
            .mappings()
            .one()
        )
        assert result["state"] == "reading" and result["evidence_event_id"] is None


# Disabling delivery preserves the incident instead of manufacturing another initial notice.
def test_presence_alert_disabled_delivery_keeps_episode(presence_case):
    c = presence_case
    notifier, _, _ = prepare(c)
    check(c, missing_factory("recovery"))
    before = notices(c)
    episode = before[0]["intent"]["episode_id"]
    c.reader.notifications = None
    check(c, missing_factory(denied=True))
    check(c, missing_factory("recovery"))
    c.reader.notifications = notifier
    check(c, missing_factory("recovery"))
    assert len(notices(c)) == len(before)
    assert {n["intent"]["episode_id"] for n in notices(c)} == {episode}


# A denied peer must not hide the other account's independently qualified Missing condition.
def test_presence_alert_partial_subject_and_no_backfill(presence_case):
    c = presence_case
    notifier, _, _ = prepare(c)
    check(c, missing_factory("recovery", unknown_purposes=("automation",)))
    original = notices(c)
    assert original and {n["intent"]["purpose"] for n in original} == {"recovery"}
    check(c, missing_factory("recovery", unknown_purposes=("automation",)))
    assert len(notices(c)) == len(original)
    check(c, missing_factory())
    c.reader.notifications = None
    check(c, missing_factory("recovery"))
    c.reader.notifications = notifier
    check(c, missing_factory("recovery"))
    assert len(notices(c)) == len(original)
