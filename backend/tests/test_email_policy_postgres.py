"""Real admission freezes contact routing without rewriting the organizational identity graph."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, workflow_case

from otm.email_policy import MailPolicy
from otm.notifications.service import LifecycleNotifier
from otm.notifications.worker import NotificationEnqueuer
from otm.storage.enqueue import workspace_queue
from otm.storage.tables import administrator, audit_event, notification_outbox, operation
from otm.tenancies.onboarding_contracts import OnboardingCommand

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# A recovery administrator needs no fictional profile address when explicit capture is configured.
@pytest.mark.parametrize("kind", ["create_tenancy", "import_tenancy"])
def test_frozen_contacts_and_atomic_lifecycle_notice(workflow_case, kind):
    c = workflow_case
    policy = MailPolicy(environment="staging", email_override="tester@example.test")
    c.workflow.mail_policy = policy
    c.workflow.notifications = c.worker.notifications = LifecycleNotifier(
        policy, NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    )
    c.worker.mail_policy_loader = lambda: policy
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    before = c.store.head(c.principal).people
    preview = c.workflow.preview(c.principal, person.id)
    assert preview.email_contacts.activation.original_email is None
    assert preview.email_contacts.owner.original_email == person.email
    assert preview.email_contacts.owner.effective_email == "tester@example.test"
    extra = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimcontactsimport"}
        if kind == "import_tenancy"
        else {}
    )
    _, receipt = action(c, person.id, kind, **extra)
    c.worker.run(receipt.operation_id)
    view = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert view.phase == "handoff"
    assert view.email_contacts.owner == preview.email_contacts.owner
    assert view.administrator_email is None
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(administrator.c.email).where(
                    administrator.c.subject == c.principal.session.subject
                )
            )
            is None
        )
        rows = (
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.operation_id == receipt.operation_id
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == 1 and rows[0]["state"] == "pending"
        assert rows[0]["intent"]["delivery_recipient"] == "tester@example.test"
        event = connection.scalar(
            select(audit_event.c.data)
            .join(operation, operation.c.current_intent_event_id == audit_event.c.id)
            .where(operation.c.id == receipt.operation_id)
        )
        assert event["intent"]["activation_email"] == "tester@example.test"
        assert event["intent"]["email_contacts"]["owner"]["original_email"] == person.email
    assert c.store.head(c.principal).people == before
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=view.revision,
            action="verify_handoff",
            handoff=view.suggested_handoff,
        ),
    )
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(notification_outbox.c.state).where(
                    notification_outbox.c.operation_id == receipt.operation_id
                )
            )
            == "superseded"
        )


# A destination change cannot retarget already accepted child activation work to another mailbox.
def test_changed_email_policy_stops_before_provider(workflow_case):
    c = workflow_case
    c.workflow.mail_policy = MailPolicy(environment="staging", email_override="one@example.test")
    c.worker.mail_policy_loader = lambda: MailPolicy(
        environment="staging", email_override="two@example.test"
    )
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    original = c.worker.facade
    facade = Mock(wraps=original)
    facade.policy = original.policy
    c.worker.facade = facade
    c.worker.run(receipt.operation_id)
    facade.apply.assert_not_called()
    with c.engine.connect() as connection:
        row = (
            connection.execute(select(operation).where(operation.c.id == receipt.operation_id))
            .mappings()
            .one()
        )
        assert row["state"] == "needs_attention"
        outcomes = connection.scalars(
            select(audit_event.c.data).where(
                audit_event.c.operation_id == receipt.operation_id,
                audit_event.c.kind == "organization_action_outcome",
            )
        ).all()
        assert outcomes[-1]["safe_code"] == "EMAIL_ROUTING_CHANGED"
