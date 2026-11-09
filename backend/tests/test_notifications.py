"""Offline delivery qualification across authority, routing, durable heads and SMTP uncertainty."""

import json
import smtplib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from otm.email_policy import MailPolicy
from otm.notifications.contracts import DeliveryResult, Envelope, NotificationIntent, mailbox
from otm.notifications.service import LifecycleNotifier, decode_intent, list_for_operation
from otm.notifications.transport import SmtpTransport
from otm.notifications.worker import (
    NotificationDeliveryWorker,
    NotificationEnqueuer,
    register_notification_task,
)
from otm.operations.contracts import canonical_hash

AT = datetime(2026, 11, 4, tzinfo=UTC)


# Every fixture address is synthetic; neither test doubles nor SMTP adapters open a network socket.
@pytest.fixture
def notice():
    policy = MailPolicy(environment="staging", email_override="capture@example.test")
    grant = {
        "id": uuid4(),
        "email": "admin@example.test",
        "status": "active",
        "authorization_revision": uuid4(),
    }
    operation = {
        "id": uuid4(),
        "workspace_id": "email-unit",
        "kind": "organization_action",
        "revision": 2,
        "current_intent_event_id": uuid4(),
        "responsible_actor_subject": "admin-key",
        "state": "waiting",
        "stage": "Activate tenancy",
        "wait_reason": "onboarding_handoff",
    }
    frozen = Mock(intent=SimpleNamespace(action="create_tenancy", onboarding_version=2))
    frozen.model_dump.return_value = {"frozen": True}
    intent = NotificationIntent(
        operation_id=operation["id"],
        operation_revision=2,
        intent_event_id=operation["current_intent_event_id"],
        intent_hash=canonical_hash({"frozen": True}),
        responsible_subject="admin-key",
        administrator_id=grant["id"],
        authorization_revision=grant["authorization_revision"],
        original_recipient=grant["email"],
        delivery_recipient="capture@example.test",
        route=policy.route(grant["email"]),
        event="action_required",
        operation_state="waiting",
        stage=operation["stage"],
        wait_reason=operation["wait_reason"],
        created_at=AT,
    )
    data = intent.model_dump(mode="json")
    row = {
        "id": uuid4(),
        "workspace_id": "email-unit",
        "operation_id": operation["id"],
        "intent": data,
        "intent_hash": canonical_hash(data),
        "state": "pending",
        "attempts": 0,
        "attempt_id": None,
        "created_at": AT,
        "updated_at": AT,
        "last_attempt_at": None,
        "next_attempt_at": None,
        "safe_code": None,
    }
    connection, engine = Mock(), Mock()
    engine.begin.return_value.__enter__ = Mock(return_value=connection)
    engine.begin.return_value.__exit__ = Mock(return_value=False)
    transport = Mock(profile_hash=None)
    queue = Mock()
    worker = NotificationDeliveryWorker(
        engine, "email-unit", lambda: AT, lambda: policy, transport, queue
    )
    return SimpleNamespace(**locals())


# Neither header controls nor a list/display-name address can enter a closed transport envelope.
@pytest.mark.parametrize(
    "address",
    [
        "a\r\nBcc:x@e.test",
        "a b@e.test",
        "a,b@e.test",
        "a:b@e.test",
        "a@@b.test",
        "a@",
        "é@e.test",
        "a\x7f@e.test",
    ],
)
def test_mailbox_rejects_header_injection(address):
    with pytest.raises(ValueError):
        mailbox(address)


# Production route objects are independently revalidated when persisted intent is reconstructed.
def test_intent_hash_scope_and_route(notice):
    c = notice
    assert decode_intent(c.row) == c.intent
    for bad in ({**c.row, "intent_hash": "0" * 64}, {**c.row, "operation_id": uuid4()}):
        with pytest.raises(ValueError):
            decode_intent(bad)
    for changed in ({"original_recipient": None}, {"delivery_recipient": "other@example.test"}):
        data = {**c.row["intent"], **changed}
        with pytest.raises(ValueError):
            decode_intent({**c.row, "intent": data, "intent_hash": canonical_hash(data)})
    with pytest.raises(ValidationError):
        Envelope(notification_id=uuid4(), recipient="a@example.test", subject="", body="body")


# A list query produces only the scoped read projection, not a whole database/provider record.
def test_list_projection(notice):
    c = notice
    c.connection.execute.return_value.mappings.return_value = [c.row]
    item = list_for_operation(c.connection, "email-unit", c.operation["id"])[0]
    assert item.recipient == "capture@example.test" and item.redirected and item.attempts == 0
    assert "email-unit" in str(c.connection.execute.call_args.args[0].compile().params)


# Named stager dependencies isolate database boundary tests from a native queue or provider engine.
def stager_patches(c):
    return (
        patch("otm.notifications.service.require_transaction"),
        patch("otm.notifications.service.load_intent", return_value=c.frozen),
        patch(
            "otm.notifications.service.execution_authority",
            return_value=(c.grant["id"], c.grant["authorization_revision"], None),
        ),
    )


# Admission, duplicate suppression and no-email local identities all preserve explicit route
# outcomes.
@pytest.mark.parametrize(
    "state,email,active",
    [
        ("waiting", "admin@example.test", True),
        ("needs_attention", "admin@example.test", True),
        ("failed", None, True),
        ("waiting", "admin@example.test", False),
    ],
)
def test_stager_freezes_and_defers_only_deliverable(notice, state, email, active):
    c = notice
    c.operation["state"] = state
    c.grant.update(email=email, status="active" if active else "revoked")
    policy = MailPolicy() if email is None else c.policy
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
    c.connection.scalar.return_value = None
    patches = stager_patches(c)
    with (
        patches[0],
        patches[1],
        patches[2],
        patch("otm.notifications.service.latest_claim", return_value=None),
    ):
        identifier = LifecycleNotifier(policy, c.queue).stage(c.connection, c.operation, AT)
    assert identifier
    if email is None or not active:
        c.queue.enqueue.assert_not_called()
    else:
        c.queue.enqueue.assert_called_once_with(c.connection, identifier)
    inserts = [
        call.args[0]
        for call in c.connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False)
    ]
    assert len(inserts) == 2


# Repeated hook calls return one existing notice rather than one email per operation revision.
def test_stager_duplicate_and_non_notice_states(notice):
    c = notice
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
    c.connection.scalar.return_value = c.row["id"]
    p = stager_patches(c)
    with p[0], p[1], p[2], patch("otm.notifications.service.latest_claim", return_value=None):
        assert (
            LifecycleNotifier(c.policy, c.queue).stage(c.connection, c.operation, AT) == c.row["id"]
        )
        for change in ({"kind": "inspect_import"}, {"state": "succeeded"}):
            assert (
                LifecycleNotifier(c.policy, c.queue).stage(
                    c.connection, {**c.operation, **change}, AT
                )
                is None
            )
        c.frozen.intent.action = "no_tenancy_required"
        assert LifecycleNotifier(c.policy, c.queue).stage(c.connection, c.operation, AT) is None
    c.queue.enqueue.assert_not_called()


# An uncertain old recipient cannot be bypassed by staging a new notice for the replacement person.
@pytest.mark.parametrize("state", ["sending", "unknown"])
def test_stager_does_not_replace_uncertain_attention(notice, state):
    c = notice
    c.operation["responsible_actor_subject"] = "replacement"
    c.connection.execute.return_value.mappings.return_value.all.return_value = [
        {**c.row, "state": state}
    ]
    with (
        patch("otm.notifications.service.require_transaction"),
        patch("otm.notifications.service.load_intent", return_value=c.frozen),
    ):
        assert (
            LifecycleNotifier(c.policy, c.queue).stage(c.connection, c.operation, AT) == c.row["id"]
        )
    c.queue.enqueue.assert_not_called()
    assert len(c.connection.execute.call_args_list) == 1


# Only known-unsent changed contexts are superseded; matching repeats retain their existing head.
def test_supersede_and_route_change(notice):
    c = notice
    c.connection.execute.return_value.mappings.return_value.all.return_value = [c.row]
    notifier = LifecycleNotifier(c.policy, c.queue)
    notifier._supersede(c.connection, c.operation, AT)
    assert len(c.connection.execute.call_args_list) == 1
    notifier._supersede(
        c.connection, {**c.operation, "responsible_actor_subject": "replacement"}, AT
    )
    assert len(c.connection.execute.call_args_list) == 4
    c.connection.reset_mock()
    notifier.policy = MailPolicy(environment="staging", email_override="different@example.test")
    notifier._supersede(c.connection, c.operation, AT)
    assert len(c.connection.execute.call_args_list) == 3


# SMTP creation validates TLS boundaries and never accepts arbitrary cleartext mail relays.
@pytest.mark.parametrize(
    "changes",
    [
        {"port": 0},
        {"timeout": 0},
        {"tls_mode": "bad"},
        {"username": "only"},
        {"start_tls": False, "host": "mail.example.test"},
        {"sender": "a\nb@example.test"},
    ],
)
def test_transport_configuration_guards(changes):
    with pytest.raises(ValueError):
        SmtpTransport(
            **{"host": "127.0.0.1", "port": 1025, "sender": "app@example.test", **changes}
        )


# The remote acceptance boundary determines retries, including TLS/login setup and socket loss.
@pytest.mark.parametrize(
    "case,expected",
    [
        ("accepted", "accepted"),
        ("mail", "rejected"),
        ("rcpt", "rejected"),
        ("data_reject", "rejected"),
        ("data_error", "rejected"),
        ("before", "rejected"),
        ("during", "uncertain"),
        ("close", "accepted"),
    ],
)
def test_smtp_acceptance_boundary(case, expected):
    smtp = Mock()
    smtp.mail.return_value = (250, b"ok")
    smtp.rcpt.return_value = (250, b"ok")
    smtp.data.return_value = (250, b"ok")
    if case in {"mail", "rcpt"}:
        getattr(smtp, case).return_value = (550, b"synthetic rejection")
    if case == "data_reject":
        smtp.data.return_value = (550, b"no")
    if case == "data_error":
        smtp.data.side_effect = smtplib.SMTPDataError(550, b"no")
    if case == "during":
        smtp.data.side_effect = OSError("synthetic disconnect")
    if case == "before":
        smtp.ehlo.side_effect = OSError("synthetic disconnect")
    if case == "close":
        smtp.close.side_effect = OSError("closed")
    with patch("otm.notifications.transport.smtplib.SMTP", return_value=smtp):
        transport = SmtpTransport(
            host="localhost",
            port=1025,
            sender="app@example.test",
            username="account",
            password_loader=lambda: "synthetic-only",
        )
        result = transport.send(
            Envelope(
                notification_id=uuid4(),
                recipient="capture@example.test",
                subject="Notice",
                body="Hello",
            )
        )
    assert result.state == expected
    smtp.close.assert_called_once()


# Local capture, implicit TLS and startup failures are qualified without opening network sockets.
def test_smtp_modes_and_constructor_failure():
    envelope = Envelope(
        notification_id=uuid4(), recipient="capture@example.test", subject="Notice", body="Hello"
    )
    for mode, cls in (("local", "SMTP"), ("implicit", "SMTP_SSL")):
        smtp = Mock()
        smtp.mail.return_value = smtp.rcpt.return_value = smtp.data.return_value = (250, b"ok")
        with patch("otm.notifications.transport.smtplib." + cls, return_value=smtp):
            transport = SmtpTransport(
                host="127.0.0.1", port=1025, sender="app@example.test", tls_mode=mode
            )
            assert transport.send(envelope).state == "accepted"
            smtp.starttls.assert_not_called()
    with patch("otm.notifications.transport.smtplib.SMTP", side_effect=OSError("offline")):
        assert (
            SmtpTransport(host="127.0.0.1", port=1025, sender="app@example.test")
            .send(envelope)
            .state
            == "rejected"
        )


# Context helpers reuse one deterministic intent; no unit test silently skips an authority check.
def context_patches(c):
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
    return (
        patch("otm.notifications.worker.load_intent", return_value=c.frozen),
        patch(
            "otm.notifications.worker.execution_authority",
            return_value=(c.grant["id"], c.grant["authorization_revision"], None),
        ),
    )


# Changed recipient, assignment, privilege, environment or mail service fences prevent any send.
def test_worker_context_fences(notice):
    c = notice
    p = context_patches(c)
    with p[0], p[1]:
        assert c.worker._context_issue(c.connection, c.row, c.operation, c.intent) is None
        assert (
            c.worker._context_issue(
                c.connection, c.row, {**c.operation, "state": "succeeded"}, c.intent
            )[0]
            == "superseded"
        )
        c.grant["status"] = "revoked"
        assert (
            c.worker._context_issue(c.connection, c.row, c.operation, c.intent)[1]
            == "EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE"
        )
        c.grant["status"] = "active"
        c.worker.policy_loader = lambda: MailPolicy(
            environment="staging", email_override="other@example.test"
        )
        assert (
            c.worker._context_issue(c.connection, c.row, c.operation, c.intent)[1]
            == "EMAIL_ROUTE_BLOCKED"
        )
        c.worker.policy_loader = lambda: c.policy
        c.transport.profile_hash = "0" * 64
        assert (
            c.worker._context_issue(c.connection, c.row, c.operation, c.intent)[1]
            == "EMAIL_TRANSPORT_CHANGED"
        )
        c.transport.profile_hash = None
        wrong = c.intent.model_copy(update={"delivery_recipient": "other@example.test"})
        with pytest.raises(ValueError):
            c.worker._context_issue(c.connection, c.row, c.operation, wrong)


# Prepare persists sending before transport and handles stale, future and crash-replayed jobs
# safely.
def test_worker_prepare_states(notice):
    c = notice
    with (
        patch.object(c.worker, "_locked", return_value=(c.row, c.operation)),
        patch.object(c.worker, "_context_issue", return_value=None),
        patch("otm.notifications.worker.record_evidence"),
    ):
        envelope, attempt = c.worker._prepare(c.row["id"])
        assert envelope.recipient == "capture@example.test" and attempt
        for changes in ({"state": "sent"}, {"next_attempt_at": AT + timedelta(seconds=30)}):
            with patch.object(
                c.worker, "_locked", return_value=({**c.row, **changes}, c.operation)
            ):
                assert c.worker._prepare(c.row["id"]) is None
        with patch.object(c.worker, "_change") as change:
            for changes, expected in (
                ({"state": "sending"}, "unknown"),
                ({"attempts": 3}, "failed"),
            ):
                with patch.object(
                    c.worker, "_locked", return_value=({**c.row, **changes}, c.operation)
                ):
                    assert c.worker._prepare(c.row["id"]) is None
                    assert change.call_args.args[2] == expected
            with patch.object(
                c.worker, "_context_issue", return_value=("blocked", "EMAIL_ROUTE_BLOCKED")
            ):
                assert c.worker._prepare(c.row["id"]) is None
                assert change.call_args.args[2] == "blocked"
        with patch.object(c.worker, "_locked", return_value=(None, None)):
            assert c.worker._prepare(c.row["id"]) is None


# The second pre-send validation closes UI/worker policy changes before the external capability
# call.
def test_preflight_and_result_cas(notice):
    c = notice
    attempt = uuid4()
    row = {**c.row, "state": "sending", "attempt_id": attempt, "attempts": 1}
    with (
        patch.object(c.worker, "_locked", return_value=(row, c.operation)),
        patch.object(c.worker, "_context_issue", return_value=None),
        patch("otm.notifications.worker.record_evidence"),
    ):
        assert c.worker._preflight(row["id"], attempt)
        assert not c.worker._preflight(row["id"], uuid4())
        with patch.object(
            c.worker, "_context_issue", return_value=("blocked", "EMAIL_ROUTE_BLOCKED")
        ):
            assert not c.worker._preflight(row["id"], attempt)
        c.worker._result(row["id"], uuid4(), "sent", "SMTP_ACCEPTED")
        c.worker._result(row["id"], attempt, "pending", "SMTP_REJECTED")
        c.queue.enqueue.assert_called_once_with(c.connection, row["id"], delay_seconds=30)
        with (
            patch.object(c.worker, "_locked", return_value=({**row, "attempts": 3}, c.operation)),
            patch.object(c.worker, "_change") as changed,
        ):
            c.worker._result(row["id"], attempt, "pending", "SMTP_REJECTED")
            assert changed.call_args.args[2] == "failed"


# SMTP cannot run for a stale preflight; accepted/rejected/uncertain results each use the attempt
# CAS.
@pytest.mark.parametrize(
    "state,result",
    [
        ("accepted", "sent"),
        ("rejected", "pending"),
        ("uncertain", "unknown"),
        ("throws", "unknown"),
    ],
)
def test_worker_run_transport_outcomes(notice, state, result):
    c = notice
    envelope = Envelope(
        notification_id=c.row["id"],
        recipient="capture@example.test",
        subject="Notice",
        body="Hello",
    )
    attempt = uuid4()
    if state == "throws":
        c.transport.send.side_effect = RuntimeError("synthetic transport bug")
    else:
        c.transport.send.return_value = DeliveryResult(
            state=state,
            safe_code={
                "accepted": "SMTP_ACCEPTED",
                "rejected": "SMTP_REJECTED",
                "uncertain": "SMTP_OUTCOME_UNKNOWN",
            }[state],
        )
    with (
        patch.object(c.worker, "_prepare", return_value=(envelope, attempt)),
        patch.object(c.worker, "_preflight", return_value=True),
        patch.object(c.worker, "_result") as finish,
    ):
        c.worker.run(c.row["id"])
        assert finish.call_args.args[2] == result
        with patch.object(c.worker, "_preflight", return_value=False):
            c.worker.run(c.row["id"])
            assert finish.call_count == 1
        with patch.object(c.worker, "_prepare", return_value=None):
            c.worker.run(c.row["id"])
            assert finish.call_count == 1


# The queue payload contains only an ID; native ETA and nonretry registration preserve worker
# knowledge.
def test_native_deferral_and_registration(notice):
    c = notice
    with (
        patch("otm.notifications.worker.procrastinate.App") as app,
        patch("otm.notifications.worker.require_transaction", return_value="tx"),
    ):
        enqueue = NotificationEnqueuer("synthetic-email")
        enqueue.enqueue(c.connection, c.row["id"], delay_seconds=30)
        assert app.return_value.configure_task.call_args.kwargs["schedule_in"] == {"seconds": 30}
        app.return_value.configure_task.return_value.defer.assert_called_once_with(
            notification_id=str(c.row["id"])
        )
        enqueue.enqueue(c.connection, c.row["id"])
        assert app.return_value.configure_task.call_args.kwargs["schedule_in"] is None
    native = Mock()
    native.task.return_value = lambda function: function
    handler = register_notification_task(native, c.worker, "synthetic-email")
    with patch.object(c.worker, "run") as run:
        handler(str(c.row["id"]))
        run.assert_called_once_with(c.row["id"])
    assert native.task.call_args.kwargs["retry"] is False


# Scoped lock ordering never reads a foreign notification and permits a missing row to remain a
# no-op.
def test_worker_lock_scope(notice):
    c = notice
    c.connection.execute.return_value.scalar_one_or_none.return_value = c.operation["id"]
    c.connection.execute.return_value.mappings.return_value.one.side_effect = [c.operation, c.row]
    with patch("otm.notifications.worker.require_transaction"):
        assert c.worker._locked(c.connection, c.row["id"]) == (c.row, c.operation)
        assert "email-unit" in str(c.connection.execute.call_args.args[0].compile().params)
        c.connection.execute.return_value.scalar_one_or_none.return_value = None
        assert c.worker._locked(c.connection, uuid4()) == (None, None)


# A frozen HTTPS origin yields a usable operation link and blocks delivery after origin changes.
def test_trusted_operation_link_and_origin_fence(notice):
    c = notice
    intent = c.intent.model_copy(update={"application_origin": "https://atlas.example.test"})
    data = intent.model_dump(mode="json")
    row = {**c.row, "intent": data, "intent_hash": canonical_hash(data)}
    c.worker.application_origin = "https://atlas.example.test"
    with (
        patch.object(c.worker, "_locked", return_value=(row, c.operation)),
        patch.object(c.worker, "_context_issue", return_value=None),
        patch("otm.notifications.worker.record_evidence"),
    ):
        envelope, _ = c.worker._prepare(row["id"])
        assert f"https://atlas.example.test/operations/{c.operation['id']}" in envelope.body
    p = context_patches(c)
    with p[0], p[1]:
        c.worker.application_origin = "https://other.example.test"
        assert c.worker._context_issue(c.connection, row, c.operation, intent) == (
            "blocked",
            "EMAIL_APPLICATION_ORIGIN_CHANGED",
        )
    for origin in (
        "http://plain.example.test",
        "https://atlas.example.test/redirect",
        "https://user@atlas.example.test",
    ):
        with pytest.raises(ValidationError):
            NotificationIntent.model_validate_json(
                __import__("json").dumps({**data, "application_origin": origin})
            )


# Even a real-looking responsible address cannot bypass missing local capture configuration.
def test_stager_local_missing_override_blocks_original(notice):
    c = notice
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
    c.connection.scalar.return_value = None
    p = stager_patches(c)
    with p[0], p[1], p[2], patch("otm.notifications.service.latest_claim", return_value=None):
        assert LifecycleNotifier(MailPolicy(), c.queue).stage(c.connection, c.operation, AT)
    c.queue.enqueue.assert_not_called()
    inserted = next(
        call.args[0]
        for call in c.connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False)
    )
    assert inserted.compile().params["state"] == "blocked"


# Supported cloud lifecycle actions retain the same responsible-only routing and frozen intent.
@pytest.mark.parametrize(
    "action",
    ["join_shared", "remove_member", "transfer_owner", "offboard_person", "delete_tenancy"],
)
@pytest.mark.parametrize("state", ["needs_attention", "failed"])
def test_non_onboarding_lifecycle_notices(notice, action, state):
    c = notice
    c.frozen.intent = SimpleNamespace(action=action, onboarding_version=None)
    c.operation.update(state=state, stage="Review lifecycle operation", wait_reason=None)
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
    c.connection.scalar.return_value = None
    p = stager_patches(c)
    with (
        p[0],
        p[1] as read,
        p[2],
        patch("otm.notifications.service.latest_claim", return_value=None),
    ):
        identifier = LifecycleNotifier(c.policy, c.queue).stage(c.connection, c.operation, AT)
        read.assert_called_once_with(c.connection, c.operation, onboarding_only=False)
    c.queue.enqueue.assert_called_once_with(c.connection, identifier)
    data = next(
        call.args[0].compile().params["intent"]
        for call in c.connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False)
    )
    intent = NotificationIntent.model_validate_json(json.dumps(data))
    assert intent.administrator_id == c.grant["id"]
    assert intent.original_recipient == c.grant["email"]
    assert intent.delivery_recipient == "capture@example.test"
    assert intent.event == ("terminal_failure" if state == "failed" else "action_required")


# Local organization decisions and legacy unguided onboarding never become email-capable handoffs.
@pytest.mark.parametrize(
    "action,version",
    [
        ("ignore", None),
        ("resolve", None),
        ("merge", None),
        ("reonboard", None),
        ("mark_returned", None),
        ("cancel_simulation", None),
        ("create_tenancy", None),
        ("import_tenancy", None),
    ],
)
def test_unrelated_or_legacy_actions_do_not_stage(notice, action, version):
    c = notice
    c.frozen.intent = SimpleNamespace(action=action, onboarding_version=version)
    with (
        patch("otm.notifications.service.require_transaction"),
        patch("otm.notifications.service.load_intent", return_value=c.frozen),
    ):
        assert LifecycleNotifier(c.policy, c.queue).stage(c.connection, c.operation, AT) is None
    c.queue.enqueue.assert_not_called()
    c.connection.execute.assert_not_called()


# Non-onboarding mail reads the same authenticated intent while keeping every send-time fence.
def test_non_onboarding_delivery_authenticates_original_intent(notice):
    c = notice
    c.frozen.intent = SimpleNamespace(action="delete_tenancy", onboarding_version=None)
    p = context_patches(c)
    with p[0] as read, p[1]:
        assert c.worker._context_issue(c.connection, c.row, c.operation, c.intent) is None
        read.assert_called_once_with(c.connection, c.operation, onboarding_only=False)
    with (
        patch.object(c.worker, "_locked", return_value=(c.row, c.operation)),
        patch.object(c.worker, "_context_issue", return_value=None),
        patch("otm.notifications.worker.record_evidence"),
    ):
        envelope, _ = c.worker._prepare(c.row["id"])
    assert envelope.subject == "Tenancy operation requires your attention"
    assert str(c.operation["id"]) in envelope.body and c.operation["stage"] in envelope.body


# Only explicitly implemented human waits notify; provider waits and routine work remain silent.
@pytest.mark.parametrize(
    "state,reason",
    [
        ("queued", None),
        ("running", None),
        ("succeeded", None),
        ("cancelled", None),
        ("waiting", None),
        ("waiting", "provider_reconciliation"),
        ("waiting", "provider_retry"),
    ],
)
def test_no_nonhuman_lifecycle_notice(notice, state, reason):
    c = notice
    c.frozen.intent = SimpleNamespace(action="delete_tenancy", onboarding_version=None)
    c.operation.update(state=state, wait_reason=reason)
    with (
        patch("otm.notifications.service.require_transaction"),
        patch("otm.notifications.service.load_intent", return_value=c.frozen),
        patch.object(LifecycleNotifier, "_supersede") as supersede,
    ):
        assert LifecycleNotifier(c.policy, c.queue).stage(c.connection, c.operation, AT) is None
        supersede.assert_called_once_with(c.connection, c.operation, AT)
    c.queue.enqueue.assert_not_called()
