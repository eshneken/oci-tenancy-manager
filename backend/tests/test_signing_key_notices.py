"""Signing-key incidents preserve recipients, safe content and SMTP uncertainty rules."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_notifications import notice
from test_user_presence_check_units import result

from otm.email_policy import EmailPolicyBlocked
from otm.notifications.contracts import SigningKeyFailureNotice
from otm.notifications.service import LifecycleNotifier, decode_intent, list_for_operation
from otm.operations.contracts import canonical_hash
from otm.tenancies.signing_key_notices import delivery_issue, stage_failure

__all__ = ["notice"]


# Synthetic routing supplies explicit authorization, never a real employee contact.
def signing_notice(c):
    head = dict(
        id=uuid4(),
        tenancy_id=uuid4(),
        generation=1,
        retire_at=c.AT if hasattr(c, "AT") else c.intent.created_at,
        rotation_operation_id=c.operation["id"],
        state="attention",
    )
    intent = SigningKeyFailureNotice(
        operation_id=c.operation["id"],
        tenancy_id=head["tenancy_id"],
        credential_id=head["id"],
        generation=1,
        administrator_id=c.grant["id"],
        authorization_revision=c.grant["authorization_revision"],
        original_recipient=c.grant["email"],
        delivery_recipient=c.intent.delivery_recipient,
        route=c.intent.route,
        retire_at=head["retire_at"],
        created_at=c.intent.created_at,
    )
    data = intent.model_dump(mode="json")
    c.row.update(intent=data, intent_hash=canonical_hash(data))
    c.operation["state"] = "needs_attention"
    return head, intent


# A single original operation/admin pair produces at most one incident delivery, with audit
# metadata.
@pytest.mark.parametrize("mode", ["new", "duplicate", "blocked"])
def test_stage_failure_deduplicates_and_guards_route(notice, mode):
    c = notice
    head, intent = signing_notice(c)
    notifier = LifecycleNotifier(c.policy, c.queue)
    if mode == "blocked":
        notifier.policy = Mock(
            route=c.policy.route, guard=Mock(side_effect=EmailPolicyBlocked("EMAIL_ROUTE_BLOCKED"))
        )
    c.connection.execute.return_value = result([c.grant])
    c.connection.scalar.return_value = uuid4() if mode == "duplicate" else None
    stage_failure(notifier, c.connection, c.operation, head, c.intent.created_at)
    if mode == "duplicate":
        c.queue.enqueue.assert_not_called()
        assert c.connection.execute.call_count == 1
    else:
        values = c.connection.execute.call_args_list[1].args[0].compile().params
        assert values["intent"]["event"] == "signing_key_attention"
        assert values["intent"]["delivery_recipient"] == "capture@example.test"
        assert values["state"] == ("blocked" if mode == "blocked" else "pending")
        assert c.queue.enqueue.call_count == (mode == "new")


# A revoked grant, resolved generation, changed route or transport never causes silent retargeting.
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "grant",
        "email",
        "revision",
        "head",
        "generation",
        "resolved",
        "child",
        "route",
        "recipient",
        "origin",
        "transport",
    ],
)
def test_delivery_revalidates_exact_incident(notice, damage):
    c = notice
    head, intent = signing_notice(c)
    child = dict(status="active")
    grant = dict(c.grant)
    if damage == "grant":
        grant["status"] = "revoked"
    if damage == "email":
        grant["email"] = "other@example.test"
    if damage == "revision":
        grant["authorization_revision"] = uuid4()
    if damage == "generation":
        head["generation"] = 3
    if damage == "resolved":
        c.operation["state"] = "succeeded"
    if damage == "child":
        child["status"] = "terminated"
    if damage == "route":
        c.worker.policy_loader = Mock(
            return_value=Mock(guard=Mock(side_effect=EmailPolicyBlocked("EMAIL_ROUTE_BLOCKED")))
        )
    if damage == "recipient":
        c.worker.policy_loader = Mock(
            return_value=Mock(guard=Mock(return_value="different@example.test"))
        )
    if damage == "origin":
        c.worker.application_origin = "https://other.example.test"
    if damage == "transport":
        c.worker.transport.profile_hash = "a" * 64
    c.connection.execute.side_effect = [
        result(None if damage == "head" else head),
        result(child),
        result(grant),
    ]
    if damage == "recipient":
        with pytest.raises(ValueError, match="ROUTE_INVALID"):
            delivery_issue(c.worker, c.connection, c.row, c.operation, intent)
    else:
        problem = delivery_issue(c.worker, c.connection, c.row, c.operation, intent)
        assert (problem is None) == (damage is None)


# Standard decoding and message preparation handle the new incident without leaking key references.
def test_safe_envelope_and_public_delivery_summary(notice):
    c = notice
    head, intent = signing_notice(c)
    assert decode_intent(c.row) == intent
    c.worker._locked = Mock(return_value=(c.row, c.operation))
    c.worker._context_issue = Mock(return_value=None)
    envelope, attempt = c.worker._prepare(c.row["id"])
    assert envelope.subject == "Automation signing-key maintenance needs attention"
    assert "Credentials are never included" in envelope.body
    assert "secret_reference" not in envelope.model_dump_json()
    assert attempt
    rows = Mock()
    rows.mappings.return_value = [c.row]
    c.connection.execute.return_value = rows
    summary = list_for_operation(c.connection, c.operation["workspace_id"], c.operation["id"])
    assert summary[0].event == "signing_key_attention"


# A sealed pre-switch incident still describes the same unresolved original retirement after CAS.
def test_activation_does_not_supersede_unresolved_incident(notice):
    c = notice
    head, intent = signing_notice(c)
    head["generation"] = intent.generation + 1
    c.connection.execute.side_effect = [
        result(head),
        result(dict(status="active")),
        result(c.grant),
    ]
    assert delivery_issue(c.worker, c.connection, c.row, c.operation, intent) is None


# An overdue drain alerts administrators without stealing the recovery password closure path.
def test_overdue_drain_notice_remains_current(notice):
    c = notice
    head, intent = signing_notice(c)
    head["state"] = "rotating"
    c.operation["state"] = "waiting"
    c.connection.execute.side_effect = [
        result(head),
        result(dict(status="active")),
        result(c.grant),
    ]
    assert delivery_issue(c.worker, c.connection, c.row, c.operation, intent) is None


# Resuming before the deadline must not discard the sole frozen incident while it is in flight.
def test_predeadline_resume_preserves_pending_incident(notice):
    from datetime import timedelta

    c = notice
    head, intent = signing_notice(c)
    head["retire_at"] = intent.created_at + timedelta(days=1)
    intent = intent.model_copy(update={"retire_at": head["retire_at"]})
    for state in ["queued", "running", "needs_attention"]:
        head["state"] = "attention" if state == "needs_attention" else "rotating"
        c.operation["state"] = state
        c.connection.execute.side_effect = [
            result(head),
            result(dict(status="active")),
            result(c.grant),
        ]
        assert delivery_issue(c.worker, c.connection, c.row, c.operation, intent) is None
