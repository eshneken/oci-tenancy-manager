"""Real onboarding, original exposure windows, scoped SQL guards and one-shot rotations."""

from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case
from test_recovery_console_checks_postgres import POLICY, refresh

from otm.email_policy import MailPolicy
from otm.notifications.service import LifecycleNotifier
from otm.notifications.worker import NotificationEnqueuer
from otm.providers.administrator_access_simulator import simulated_administrator_inspection
from otm.providers.presence_simulator import simulated_presence_inspection
from otm.providers.recovery_console_simulator import simulated_console_inspection
from otm.providers.recovery_password_simulator import SimulatedRecoveryPasswords
from otm.storage.enqueue import (
    PRESENCE_TASK,
    RECOVERY_PASSWORD_TASK,
    InspectionEnqueuer,
    workspace_queue,
)
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import (
    audit_event,
    notification_outbox,
    operation_step,
    tenancy,
)
from otm.storage.tables import (
    recovery_credential as heads,
)
from otm.storage.tables import (
    recovery_grant as grants,
)
from otm.storage.tables import (
    recovery_version as versions,
)
from otm.tenancies.presence import PresenceChecks
from otm.tenancies.presence_worker import UserPresenceWorker
from otm.tenancies.recovery_password import RecoveryPasswordAccess
from otm.tenancies.recovery_password_contracts import RecoveryPasswordRequest
from otm.tenancies.recovery_password_records import location_of
from otm.tenancies.recovery_password_setup import RecoveryPasswordSetup
from otm.tenancies.recovery_password_worker import RecoveryPasswordWorker
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Read exact scoped records independently of mutable request/service objects.
def records(c, table):
    with c.engine.connect() as connection:
        return list(
            connection.execute(
                select(table).where(
                    table.c.workspace_id == c.policy.workspace_id,
                )
            ).mappings()
        )


# Compose actual version4 admission, durable native deferral and separately owned private custody.
@pytest.fixture
def password_pg(workflow_case, tmp_path):
    c = workflow_case
    directory = tmp_path / "passwords"
    directory.mkdir(mode=0o700)
    c.vault = SimulatedRecoveryPasswords(directory)
    queue = workspace_queue(c.policy.workspace_id)
    enqueue = InspectionEnqueuer(queue, task=RECOVERY_PASSWORD_TASK)
    setup = RecoveryPasswordSetup(enqueue)
    c.workflow.recovery_password_setup = setup
    c.workflow.recovery_console = POLICY
    c.provider.recovery_console = POLICY
    c.worker.recovery_setup = setup
    c.notifier = LifecycleNotifier(
        MailPolicy(environment="staging", email_override="capture@example.test"),
        NotificationEnqueuer(queue),
    )
    c.rotation = RecoveryPasswordWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.vault,
        c.vault,
        enqueue,
        c.workflow.enqueuer,
        notifier=c.notifier,
    )
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id, expected_phase="configuring")
    (head,) = records(c, heads)
    assert head["state"] == "staging" and head["location"]["secret_reference"] is None
    view = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert (
        view.available_actions == ()
        and next(s for s in view.checks if s.key == "retire_temporary").state != "verified"
    )
    c.rotation.run(head["rotation_operation_id"])
    c.worker.run(receipt.operation_id)
    assert c.workflow.onboarding(c.principal, receipt.operation_id).phase == "complete"
    c.child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    c.person = person
    c.service = PresenceChecks(
        c.store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(queue, task=PRESENCE_TASK),
        recovery_console_loader=lambda: POLICY,
    )
    c.reader = UserPresenceWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.workflow.policy,
        simulated_presence_inspection,
        recovery_console_loader=lambda: POLICY,
        recovery_inspection_factory=simulated_console_inspection,
        administrator_inspection_factory=simulated_administrator_inspection,
    )
    c.access = RecoveryPasswordAccess(c.service, c.vault, enqueue, notifier=c.notifier)
    c.workflow.presence_checks = c.service
    c.workflow.recovery_passwords = c.access
    refresh(c)
    return c


# Request new intentional access using exactly the safe readiness preview a browser receives.
def request(c):
    view = c.access.view(c.principal, c.child.id)
    assert view.available
    command = RecoveryPasswordRequest(
        client_request_key=uuid4(), preview_hash=view.preview_hash, acknowledged=True
    )
    return command, c.access.disclose(c.principal, c.child.id, command)


# Setup and request replay never allocate again; later deliberate requests keep the same deadline.
def test_original_window_rotation_and_retained_history(password_pg):
    c = password_pg
    command, first = request(c)
    (before,) = records(c, heads)
    assert before["rotation_due_at"] - before["first_disclosure_at"] == timedelta(hours=4)
    assert c.access.disclose(c.principal, c.child.id, command)["request_id"] == first["request_id"]
    assert len(records(c, grants)) == 1
    c.clock.return_value += timedelta(minutes=1)
    _, second = request(c)
    assert second["rotation_due_at"] == first["rotation_due_at"]
    assert second["password"] == first["password"]
    assert len(records(c, grants)) == 2
    with c.engine.connect() as connection:
        assert (
            connection.scalar(select(tenancy.c.operation_id).where(tenancy.c.id == c.child.id))
            is None
        )
        jobs = (
            connection.exec_driver_sql(
                "SELECT args FROM public.procrastinate_jobs WHERE task_name='otm.recovery_password'"
            )
            .scalars()
            .all()
        )
        assert jobs and all(set(j) == {"operation_id"} for j in jobs)
    c.rotation.run(before["rotation_operation_id"])
    assert records(c, heads)[0] == before
    c.clock.return_value = before["rotation_due_at"]
    c.rotation.run(before["rotation_operation_id"])
    c.rotation.run(before["rotation_operation_id"])
    (after,) = records(c, heads)
    assert after["state"] == "usable" and after["generation"] == 2
    assert after["first_disclosure_at"] is None and after["rotation_due_at"] is None
    assert len(records(c, versions)) == 2 and len(records(c, grants)) == 2
    assert c.vault.current(location_of(after)).password.get_secret_value() != first["password"]

    assert all(
        first["password"] not in str(row)
        for table in (heads, versions, grants, audit_event, operation_step, notification_outbox)
        for row in records(c, table)
    )
    with pytest.raises(OrganizationConflict, match="REQUEST_CLOSED"):
        c.access.disclose(c.principal, c.child.id, command)


# API consent and destructive workflows cannot bypass an outstanding password obligation.
def test_consent_and_termination_guard(password_pg):
    c = password_pg
    view = c.access.view(c.principal, c.child.id)
    with pytest.raises(OrganizationConflict, match="CONFIRMATION_REQUIRED"):
        c.access.disclose(
            c.principal,
            c.child.id,
            RecoveryPasswordRequest(
                client_request_key=uuid4(), preview_hash=view.preview_hash, acknowledged=False
            ),
        )
    assert records(c, grants) == []
    request(c)
    with pytest.raises(OrganizationConflict, match="ROTATION_REQUIRED"):
        action(c, c.person.id, "delete_tenancy", tenancy_id=c.child.id)
    assert c.workflow.tenancy_detail(c.principal, c.child.id).tenancy.status == "active"


# Unknown CURRENT is a hold before release; transient read failure retains a retryable root request.
@pytest.mark.parametrize("fault", ["read", "version"])
def test_read_failure_and_unexpected_current(password_pg, fault):
    c = password_pg
    if fault == "read":
        with patch.object(c.vault, "current", side_effect=OSError("private")):
            with pytest.raises(OrganizationConflict, match="READ_UNAVAILABLE"):
                request(c)
        assert records(c, heads)[0]["state"] == "usable"
    else:
        original = c.vault.current
        # Return another already-normalized immutable candidate, with no child or pointer write.

        head = records(c, heads)[0]
        ref = c.vault.stage(location_of(head), uuid4())
        with patch.object(c.vault, "current", return_value=c.vault.candidate(ref)):
            with pytest.raises(OrganizationConflict, match="UNAVAILABLE"):
                request(c)
        assert records(c, heads)[0]["state"] == "unknown"
        assert original(location_of(head)).reference != ref
    assert len(records(c, grants)) == 1


# Immutable histories, scoped versions and original deadlines are enforced by PostgreSQL itself.
def test_database_guards_preserve_original_records(password_pg):
    c = password_pg
    request(c)
    before = records(c, heads)[0]
    grant = records(c, grants)[0]
    version = records(c, versions)[0]
    statements = [
        update(heads)
        .where(heads.c.id == before["id"])
        .values(rotation_due_at=before["rotation_due_at"] + timedelta(hours=1)),
        update(heads).where(heads.c.id == before["id"]).values(location={}),
        update(grants).where(grants.c.id == grant["id"]).values(requesting_subject="foreign"),
        versions.delete().where(versions.c.id == version["id"]),
        text("TRUNCATE public.otm_human_access_grant"),
    ]
    for statement in statements:
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            connection.execute(statement)
        assert records(c, heads)[0] == before


# Conflict deferrals retain the deadline and deduplicate the urgent administrative notice.
def test_due_busy_notice_and_rotation_survives_requester_session(password_pg):
    c = password_pg
    request(c)
    head = records(c, heads)[0]
    c.clock.return_value = head["rotation_due_at"]
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == c.child.id)
            .values(operation_id=head["source_operation_id"])
        )
    c.rotation.run(head["rotation_operation_id"])
    notice_count = len(records(c, notification_outbox))
    c.rotation.run(head["rotation_operation_id"])
    assert len(records(c, notification_outbox)) == notice_count
    assert records(c, heads)[0]["rotation_due_at"] == head["rotation_due_at"]
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy).where(tenancy.c.id == c.child.id).values(operation_id=None)
        )
    c.rotation.run(head["rotation_operation_id"])
    assert records(c, heads)[0]["state"] == "usable"


# Concurrent browser retries share one admission/window/job without duplicating exposure history.
@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_disclosures_are_serialized(password_pg, same_key):
    from concurrent.futures import ThreadPoolExecutor

    c = password_pg
    preview = c.access.view(c.principal, c.child.id)
    command = RecoveryPasswordRequest(
        client_request_key=uuid4(), preview_hash=preview.preview_hash, acknowledged=True
    )
    commands = (
        command,
        command if same_key else command.model_copy(update={"client_request_key": uuid4()}),
    )

    # Return only a nonsecret request ID or fixed conflict, never password material from threads.
    def submit(item):
        try:
            return c.access.disclose(c.principal, c.child.id, item)["request_id"]
        except OrganizationConflict:
            return "preview_changed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, commands))
    assert len(records(c, grants)) == 1
    if same_key:
        assert results[0] == results[1]
    else:
        assert results.count("preview_changed") == 1
    assert records(c, heads)[0]["exposure_generation"] == 1


# Email uses the real delivery worker/context guards; only the existing transport is stubbed.
def test_disclosure_email_is_frozen_secret_free_and_not_retargeted(password_pg):
    from otm.notifications.contracts import DeliveryResult
    from otm.notifications.worker import NotificationDeliveryWorker, NotificationEnqueuer

    c = password_pg
    _, response = request(c)
    transport = Mock(profile_hash=None)
    transport.send.return_value = DeliveryResult(state="accepted", safe_code="SMTP_ACCEPTED")
    worker = NotificationDeliveryWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        lambda: c.notifier.policy,
        transport,
        NotificationEnqueuer(workspace_queue(c.policy.workspace_id)),
    )
    notices = records(c, notification_outbox)
    assert notices
    for notice in notices:
        worker.run(notice["id"])
    assert transport.send.call_count
    for call in transport.send.call_args_list:
        envelope = call.args[0]
        assert envelope.recipient == "capture@example.test"
        assert response["password"] not in envelope.body
    sent = transport.send.call_count
    for notice in notices:
        worker.run(notice["id"])
    assert transport.send.call_count == sent
