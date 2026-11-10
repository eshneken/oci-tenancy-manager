"""Durable signing-key replacement, request replay, original scheduling and paused work."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_notification_mailpit_postgres import mail_capture
from test_organization_workflows_postgres import (
    action,
    factors,
    login_case,
    organization_case,
    workflow_case,
)

from otm.operations.views import OperationQuery
from otm.providers.automation_keys_simulator import SimulatedAutomationKeys
from otm.providers.signing_key_rotation_simulator import SimulatedSigningKeys
from otm.storage.enqueue import (
    ORGANIZATION_TASK,
    SIGNING_KEY_TASK,
    InspectionEnqueuer,
    workspace_queue,
)
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.tables import (
    audit_event,
    notification_outbox,
    operation,
    operation_step,
    signing_credential,
)
from otm.tenancies.onboarding_contracts import OnboardingCommand
from otm.tenancies.signing_key_contracts import SigningKeyRequest
from otm.tenancies.signing_key_records import SigningKeySetup, current_key
from otm.tenancies.signing_key_worker import SigningKeyWorker
from otm.tenancies.signing_keys import (
    SigningKeys,
    require_signing_admission,
    signing_dispatch_allowed,
)
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case", "mail_capture"]


# One real scoped source/workflow uses separate persistent custody and provider inventory fixtures.
@pytest.fixture
def signing_case(workflow_case, tmp_path):
    c = workflow_case
    inventory = SimulatedAutomationKeys(tmp_path / "inventory", c.clock)
    path = tmp_path / "signing"
    path.mkdir(mode=0o700)
    provider = SimulatedSigningKeys(path, inventory, c.clock)
    queue = InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=SIGNING_KEY_TASK)
    setup = SigningKeySetup(queue, c.loader)
    c.workflow.automation_key_inventory_enabled = True
    c.workflow.signing_key_setup_enabled = True
    c.workflow.signing_guard = require_signing_admission
    c.provider.automation_keys = inventory
    c.worker.signing_setup = setup
    reader = SigningKeyWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        provider,
        queue,
        InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=ORGANIZATION_TASK),
    )
    service = SigningKeys(c.store, c.loader, queue)
    return SimpleNamespace(
        **vars(c), keys=reader, signing=service, inventory=inventory, key_custody=provider
    )


# Audited human handoff lets the independent signer job unblock temporary cleanup.
def enroll(c):
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, created = action(c, person.id, "create_tenancy")
    c.worker.run(created.operation_id)
    handoff = c.workflow.onboarding(c.principal, created.operation_id)
    c.workflow.onboarding_action(
        c.principal,
        created.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=handoff.revision,
            action="verify_handoff",
            handoff=handoff.suggested_handoff,
        ),
    )
    c.worker.run(created.operation_id)
    reviewed = c.workflow.onboarding(c.principal, created.operation_id)
    c.workflow.onboarding_action(
        c.principal,
        created.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=reviewed.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    c.worker.run(created.operation_id)
    waiting = c.workflow.onboarding(c.principal, created.operation_id)
    assert waiting.phase == "configuring"
    with c.engine.connect() as connection:
        head = (
            connection.execute(
                select(signing_credential).where(
                    signing_credential.c.workspace_id == c.policy.workspace_id
                )
            )
            .mappings()
            .one()
        )
    c.keys.run(head["rotation_operation_id"])
    c.worker.run(created.operation_id)
    assert c.workflow.onboarding(c.principal, created.operation_id).phase == "complete"
    c.child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    return head["id"]


# Pointer switching and old removal are separate durable phases; replay cannot create another pair.
def test_enrollment_rotation_and_request_replay(signing_case):
    c = signing_case
    credential = enroll(c)
    view = c.signing.view(c.principal, c.child.id)
    assert view.state == "scheduled" and view.generation == 1 and view.available
    with c.engine.connect() as connection:
        head = dict(
            connection.execute(
                select(signing_credential).where(signing_credential.c.id == credential)
            )
            .mappings()
            .one()
        )
    original = current_key(head)
    assert view.starts_at == original.retire_at - timedelta(days=1)
    c.keys.run(view.operation_id)
    assert c.signing.view(c.principal, c.child.id) == view
    c.clock.return_value += timedelta(seconds=1)
    command = SigningKeyRequest(
        client_request_key=uuid4(), preview_hash=view.preview_hash, acknowledged=True
    )
    queued = c.signing.request(c.principal, c.child.id, command)
    assert c.signing.request(c.principal, c.child.id, command).operation_id == queued.operation_id
    with c.engine.connect() as connection:
        from otm.storage.organization import OrganizationConflict

        with pytest.raises(OrganizationConflict, match="SIGNING_KEY_MAINTENANCE_REQUIRED"):
            require_signing_admission(connection, c.policy.workspace_id, c.child.id, c.clock())
        assert signing_dispatch_allowed(connection, c.policy.workspace_id, c.child.id, c.clock())
    for _ in range(8):
        c.keys.run(queued.operation_id)
    completed = SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, queued.operation_id)
    assert completed.operation.state == "succeeded"
    assert completed.steps[0].safe_code == "SIGNING_KEY_ROTATED"
    result = c.signing.view(c.principal, c.child.id)
    assert (
        result.state == "scheduled"
        and result.generation == 2
        and result.operation_id != queued.operation_id
    )
    assert c.signing.request(c.principal, c.child.id, command).operation_id == queued.operation_id
    with c.engine.connect() as connection:
        head = dict(
            connection.execute(
                select(signing_credential).where(signing_credential.c.id == credential)
            )
            .mappings()
            .one()
        )
    selected = current_key(head)
    assert selected.version.fingerprint != original.version.fingerprint
    target = selected.version.target
    from otm.providers.required_user_contracts import ObservedRequiredUser

    user = ObservedRequiredUser(
        domain_ocid=target.domain_ocid,
        scim_resource_id=target.scim_resource_id,
        provider_ocid=target.provider_ocid,
        user_name=target.user_name,
    )
    facts = c.inventory.read(
        target.workspace_id, target.tenancy_id, target.tenancy_ocid, user
    ).facts
    assert [key.fingerprint for key in facts.keys] == [selected.version.fingerprint]
    assert "secret_reference" not in completed.model_dump_json()
    assert (
        SqlOperationDirectory(c.engine).directory(c.policy.workspace_id, OperationQuery()).total
        >= 4
    )


# Unknown mutation results stay held across native duplicates and reconcile only by explicit resume.
@pytest.mark.parametrize("phase", ["upload", "retire"])
def test_unknown_effect_requires_explicit_resume(signing_case, monkeypatch, phase):
    c = signing_case
    credential = enroll(c)
    view = c.signing.view(c.principal, c.child.id)
    c.clock.return_value += timedelta(seconds=1)
    requested = c.signing.request(
        c.principal,
        c.child.id,
        SigningKeyRequest(
            client_request_key=uuid4(), preview_hash=view.preview_hash, acknowledged=True
        ),
    )
    original = getattr(c.key_custody, phase)
    calls = []

    # Lose the reply after the exact provider mutation has already succeeded.
    def lost_reply(*args):
        calls.append(args)
        original(*args)
        raise OSError("synthetic unavailable reply")

    monkeypatch.setattr(c.key_custody, phase, lost_reply)
    for _ in range(8):
        c.keys.run(requested.operation_id)
        if c.signing.view(c.principal, c.child.id).state == "attention":
            break
    assert len(calls) == 1
    held = c.signing.view(c.principal, c.child.id)
    assert held.state == "attention" and held.available

    # Immutable evidence, attempt ownership and queued native references cannot change while held.
    def persisted():
        with c.engine.connect() as connection:
            step = dict(
                connection.execute(
                    select(operation_step).where(
                        operation_step.c.operation_id == requested.operation_id
                    )
                )
                .mappings()
                .one()
            )
            events = (
                connection.execute(
                    select(audit_event.c.id).where(
                        audit_event.c.operation_id == requested.operation_id
                    )
                )
                .scalars()
                .all()
            )
            head = dict(
                connection.execute(
                    select(signing_credential).where(signing_credential.c.id == credential)
                )
                .mappings()
                .one()
            )
            return step, events, head

    before = persisted()
    c.keys.run(requested.operation_id)
    c.keys.run(requested.operation_id)
    assert persisted() == before and len(calls) == 1
    monkeypatch.setattr(c.key_custody, phase, original)
    c.signing.request(
        c.principal,
        c.child.id,
        SigningKeyRequest(
            client_request_key=uuid4(),
            preview_hash=held.preview_hash,
            acknowledged=True,
            action="resume",
        ),
    )
    for _ in range(8):
        c.keys.run(requested.operation_id)
    assert c.signing.view(c.principal, c.child.id).generation == 2
    assert (
        SqlOperationDirectory(c.engine)
        .detail(c.policy.workspace_id, requested.operation_id)
        .operation.state
        == "succeeded"
    )
    assert len(calls) == 1


# A second native delivery cannot steal a phase while its first provider call is in flight.
def test_running_delivery_does_not_replace_attempt(signing_case, monkeypatch):
    c = signing_case
    enroll(c)
    view = c.signing.view(c.principal, c.child.id)
    c.clock.return_value += timedelta(seconds=1)
    requested = c.signing.request(
        c.principal,
        c.child.id,
        SigningKeyRequest(
            client_request_key=uuid4(), preview_hash=view.preview_hash, acknowledged=True
        ),
    )
    original = c.key_custody.stage
    calls = []

    # Re-enter on another database transaction during provider I/O, after SQL locks were released.
    def stage(old, context):
        calls.append(context.attempt_id)
        c.keys.run(requested.operation_id)
        with c.engine.connect() as connection:
            assert (
                connection.scalar(
                    select(operation_step.c.current_attempt_id).where(
                        operation_step.c.operation_id == requested.operation_id
                    )
                )
                == context.attempt_id
            )
        return original(old, context)

    monkeypatch.setattr(c.key_custody, "stage", stage)
    c.keys.run(requested.operation_id)
    assert len(calls) == 1
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == requested.operation_id)
            )
            == "queued"
        )
        assert (
            connection.scalar(
                select(operation_step.c.attempt_number).where(
                    operation_step.c.operation_id == requested.operation_id
                )
            )
            == 1
        )


# Unrecognized application waits are not a native retry authorization.
def test_unrelated_wait_is_held(signing_case):
    c = signing_case
    enroll(c)
    view = c.signing.view(c.principal, c.child.id)
    with c.engine.begin() as connection:
        connection.execute(
            update(operation)
            .where(operation.c.id == view.operation_id)
            .values(wait_reason="onboarding_activation")
        )
    c.keys.run(view.operation_id)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(operation_step.c.operation_id).where(
                    operation_step.c.operation_id == view.operation_id
                )
            )
            is None
        )


# Reversible termination cannot tombstone a working signer; confirmed termination always does.
@pytest.mark.parametrize("cancel", [True, False])
def test_termination_and_signing_custody(signing_case, cancel):
    from otm.tenancies.deletion import TenancyDeletionCommand

    c = signing_case
    credential = enroll(c)
    view = c.signing.view(c.principal, c.child.id)
    preview = c.workflow.deletion_preview(c.principal, c.child.id)
    accepted = c.workflow.delete_tenancy(
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
    c.clock.return_value = view.starts_at
    from test_local_auth_postgres import command as login_command

    issued = c.service.sign_in(login_command(c))
    c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    c.keys.run(view.operation_id)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(signing_credential.c.state).where(signing_credential.c.id == credential)
            )
            == "usable"
        )
    if cancel:
        action(c, c.child.owner_person_id, "cancel_simulation", operation_id=accepted.operation_id)
        for _ in range(8):
            c.keys.run(view.operation_id)
        assert c.signing.view(c.principal, c.child.id).generation == 2
    else:
        c.worker.run(accepted.operation_id)
        with c.engine.connect() as connection:
            assert (
                connection.scalar(
                    select(signing_credential.c.state).where(signing_credential.c.id == credential)
                )
                == "retired"
            )
            assert (
                connection.scalar(
                    select(operation.c.state).where(operation.c.id == view.operation_id)
                )
                == "cancelled"
            )
        c.keys.run(view.operation_id)
        assert c.signing.view(c.principal, c.child.id).state == "inactive"


# Exact incident delivery uses actual loopback SMTP without relaying to any employee address.
def test_signing_failure_real_smtp(signing_case, mail_capture, monkeypatch):
    import httpx

    from otm.email_policy import MailPolicy
    from otm.notifications.service import LifecycleNotifier
    from otm.notifications.transport import SmtpTransport
    from otm.notifications.worker import NotificationDeliveryWorker, NotificationEnqueuer

    c = signing_case
    enroll(c)
    transport = SmtpTransport(
        host="127.0.0.1", port=mail_capture.smtp_port, sender="otm@example.test", tls_mode="local"
    )
    policy = MailPolicy(environment="staging", email_override="capture@otm.test")
    mail_queue = NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    c.keys.notifier = LifecycleNotifier(
        policy,
        mail_queue,
        profile_hash=transport.profile_hash,
        application_origin="https://localhost:8443",
    )
    view = c.signing.view(c.principal, c.child.id)
    c.clock.return_value += timedelta(seconds=1)
    accepted = c.signing.request(
        c.principal,
        c.child.id,
        SigningKeyRequest(
            client_request_key=uuid4(), preview_hash=view.preview_hash, acknowledged=True
        ),
    )
    original = c.key_custody.upload

    # Only this owned test adapter loses acknowledgement after applying its synthetic effect.
    def lost(*args):
        original(*args)
        raise OSError("synthetic lost response")

    monkeypatch.setattr(c.key_custody, "upload", lost)
    for _ in range(3):
        c.keys.run(accepted.operation_id)
    delivery = NotificationDeliveryWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        lambda: policy,
        transport,
        mail_queue,
        application_origin="https://localhost:8443",
    )
    with c.engine.connect() as connection:
        rows = (
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.operation_id == accepted.operation_id
                )
            )
            .mappings()
            .all()
        )
    assert rows and all(row["state"] == "pending" for row in rows)
    for row in rows:
        delivery.run(row["id"])
    for row in rows:
        delivery.run(row["id"])
    with c.engine.connect() as connection:
        states = (
            connection.execute(
                select(notification_outbox.c.state).where(
                    notification_outbox.c.operation_id == accepted.operation_id
                )
            )
            .scalars()
            .all()
        )
    assert states == ["sent"] * len(rows)
    with httpx.Client(trust_env=False, timeout=3) as client:
        messages = client.get(mail_capture.url + "/api/v1/messages").json()
        assert messages["total"] == len(rows)
        for message in messages["messages"]:
            assert message["To"] == [{"Name": "", "Address": "capture@otm.test"}]
            body = client.get(mail_capture.url + "/api/v1/message/" + message["ID"]).json()["Text"]
            assert (
                str(c.child.id) in body
                and "secret_reference" not in body
                and "simulated-key-material" not in body
            )
