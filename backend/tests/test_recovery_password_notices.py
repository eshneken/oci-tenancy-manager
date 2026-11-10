"""Secret-free disclosure/failure recipients, durable routing and send-time provenance guards."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_recovery_password_custody import custody
from test_recovery_password_units import NOW, password_case

from otm.email_policy import MailPolicy
from otm.notifications.contracts import RecipientReason, RecoveryPasswordNotice
from otm.notifications.service import decode_intent
from otm.operations.contracts import canonical_hash
from otm.tenancies.recovery_password_notices import delivery_issue, recipients, stage

__all__ = ["custody", "password_case"]
MODULE = "otm.tenancies.recovery_password_notices."


# Role provenance may overlap, but designees never receive recovery-password disclosure notices.
@pytest.mark.parametrize("failure", [False, True])
def test_distinct_recipient_sets(password_case, failure):
    c = password_case
    person = uuid4()
    other = dict(issuer="urn:example", subject="other", id=uuid4())
    own = dict(issuer=c.actor.issuer, subject=c.actor.subject, id=uuid4())
    contacts = {
        "owner@example.test": (RecipientReason(role="owner", person_id=person),),
        "designee@example.test": (RecipientReason(role="designee", person_id=person),),
        "admin@example.test": (
            RecipientReason(
                role="administrator", administrator_id=other["id"], authorization_revision=uuid4()
            ),
        ),
    }
    with patch(
        MODULE + "required_user_recipients", return_value=(contacts, ("designee_unavailable",))
    ) as routing:
        result, issues = recipients(
            Mock(), [own, other], c.child["id"], c.actor.key, failure=failure
        )
    assert "designee@example.test" not in result and issues == ()
    assert set(result) == (
        {"admin@example.test"} if failure else {"owner@example.test", "admin@example.test"}
    )
    assert len(routing.call_args.args[1]) == (2 if failure else 1)


# Each notice owns an unchanged original deadline, role reason and explicit staging route.
@pytest.fixture
def notice_case(password_case):
    c = password_case
    c.reason = RecipientReason(
        role="administrator", administrator_id=uuid4(), authorization_revision=uuid4()
    )
    c.mail = MailPolicy(environment="staging", email_override="capture@example.test")
    c.notifier = SimpleNamespace(
        policy=c.mail, application_origin=None, profile_hash=None, enqueuer=Mock()
    )
    c.state = SimpleNamespace(
        context=SimpleNamespace(applied_version_id=uuid4(), configuration_id=uuid4())
    )
    c.request = dict(id=uuid4(), first_disclosure_attempt_at=NOW, due_at=NOW + timedelta(hours=4))
    c.head.update(
        first_disclosure_at=NOW, rotation_due_at=c.request["due_at"], requester_subject=c.actor.key
    )
    c.notice = RecoveryPasswordNotice(
        operation_id=c.identifier,
        tenancy_id=c.child["id"],
        credential_id=c.head["id"],
        grant_id=c.request["id"],
        requester_subject=c.actor.key,
        organization_version_id=c.state.context.applied_version_id,
        configuration_id=c.state.context.configuration_id,
        reasons=(c.reason,),
        original_recipient="admin@example.test",
        delivery_recipient="capture@example.test",
        route=c.mail.route("admin@example.test"),
        application_origin=None,
        delivery_profile_hash=None,
        event="recovery_password_requested",
        first_disclosure_at=NOW,
        rotation_due_at=c.request["due_at"],
        created_at=NOW,
    )
    return c


# Frozen routing and audit acceptance share the transaction; duplicate polling stages no new email.
@pytest.mark.parametrize("fault", ["none", "duplicate", "blocked", "missing", "failure"])
def test_notice_staging_and_dedup(notice_case, fault):
    c = notice_case
    if fault == "blocked":
        c.notifier.policy = MailPolicy(environment="production")
    contact = None if fault in {"blocked", "missing"} else "admin@example.test"
    contacts = {contact: () if fault == "missing" else (c.reason,)}
    issues = ("administrator_unavailable",) if fault == "missing" else ()
    c.connection.scalar.return_value = uuid4() if fault == "duplicate" else None
    with (
        patch(MODULE + "require_transaction"),
        patch(MODULE + "registry_state", return_value=c.state),
        patch(MODULE + "recipients", return_value=(contacts, issues)),
        patch(MODULE + "record_evidence") as audit,
    ):
        stage(
            c.notifier,
            c.connection,
            c.intent.workspace_id,
            c.identifier,
            c.head,
            NOW,
            request=None if fault == "failure" else c.request,
            actor=c.actor,
        )
    assert audit.call_count == (0 if fault == "duplicate" else 1)
    assert c.notifier.enqueuer.enqueue.call_count == (fault in {"none", "failure"})


# Delivery never retargets changed context; immutable source and frozen route must still agree.
@pytest.mark.parametrize(
    "fault", ["none", "hash", "head", "request", "recipient", "route", "origin", "profile"]
)
def test_delivery_guard(notice_case, fault):
    c = notice_case
    data = c.frozen.model_dump(mode="json")
    source = dict(data=data, data_hash="b" * 64 if fault == "hash" else canonical_hash(data))
    saved = dict(
        accepted_operation_id=c.identifier,
        credential_id=c.head["id"],
        first_disclosure_attempt_at=NOW,
        due_at=c.request["due_at"],
        requesting_subject=c.actor.key,
    )
    if fault == "request":
        saved["credential_id"] = uuid4()
    first, second, third, fourth = Mock(), Mock(), Mock(), Mock()
    first.mappings.return_value.one.return_value = source
    second.mappings.return_value.one_or_none.return_value = None if fault == "head" else c.head
    third.mappings.return_value.one_or_none.return_value = saved
    fourth.mappings.return_value.all.return_value = []
    c.connection.execute.side_effect = [first, second, third, fourth]
    worker = SimpleNamespace(
        workspace=c.intent.workspace_id,
        policy_loader=lambda: MailPolicy(environment="production") if fault == "route" else c.mail,
        application_origin="https://different.example.test" if fault == "origin" else None,
        transport=SimpleNamespace(profile_hash="a" * 64 if fault == "profile" else None),
    )
    current = {} if fault == "recipient" else {"admin@example.test": (c.reason,)}
    with (
        patch(MODULE + "registry_state", return_value=c.state),
        patch(MODULE + "recipients", return_value=(current, ())),
    ):
        if fault == "hash":
            with pytest.raises(ValueError, match="SOURCE_INVALID"):
                delivery_issue(worker, c.connection, {}, c.row, c.notice)
        else:
            assert (delivery_issue(worker, c.connection, {}, c.row, c.notice) is None) == (
                fault == "none"
            )
    row = dict(
        operation_id=c.identifier,
        intent=c.notice.model_dump(mode="json"),
        intent_hash=canonical_hash(c.notice.model_dump(mode="json")),
    )
    assert decode_intent(row) == c.notice
