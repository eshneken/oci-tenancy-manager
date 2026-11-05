"""Actual two-administrator takeover, continuation authority and immutable history."""

import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text, update
from test_administrators import grant
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, workflow_case

from otm.audit.contracts import AuditQuery
from otm.auth.contracts import DisplaySnapshot
from otm.auth.service import SessionService
from otm.operations.responsibility import ResponsibilityCommand, take_responsibility
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.organization import OrganizationConflict, SqlOrganizationStore
from otm.storage.sessions import SqlSessionRepository
from otm.storage.tables import admin_session, administrator, audit_event, operation
from otm.tenancies.onboarding_contracts import OnboardingCommand
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# A real synthetic corporate grant/session is separate from the protected local recovery anchor.
def colleague(c, name):
    target = grant(
        workspace_id=c.policy.workspace_id,
        subject=name,
        display_name=name,
        email=name.lower().replace(" ", ".") + "@example.test",
    )
    handle = secrets.token_urlsafe(32)
    session = c.principal.session.model_copy(
        update={
            "id": uuid4(),
            "issuer": target.issuer,
            "subject": target.subject,
            "session_token_hash": hashlib.sha256(handle.encode()).hexdigest(),
            "entitlement_reference": str(target.id),
            "entitlement_revision": target.authorization_revision,
            "display_snapshot": DisplaySnapshot(display_name=name),
        }
    )
    with c.engine.begin() as connection:
        connection.execute(administrator.insert().values(**target.model_dump()))
        connection.execute(admin_session.insert().values(**session.model_dump()))
    grants = SqlAdministratorStore(
        c.engine,
        c.clock,
        local_issuer=c.policy.issuer,
        trusted_issuers=frozenset({c.policy.issuer, target.issuer}),
    )
    sessions = SessionService(SqlSessionRepository(c.engine), grants, target.issuer, c.clock)
    principal = sessions.authenticate(handle)
    store = SqlOrganizationStore(c.engine, sessions, c.clock)
    flow = OrganizationWorkflows(
        store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        facade=c.provider,
        enqueuer=c.workflow.enqueuer,
    )
    return SimpleNamespace(principal=principal, workflow=flow, store=store, grant=target)


# Start real guided work through one administrator, then expose its immutable waiting revision.
def pending(c, creator):
    person = next(
        person
        for person in creator.store.head(creator.principal).people
        if person.email == "engineer@example.test"
    )
    _, receipt = action(creator, person.id, "create_tenancy")
    c.worker.run(receipt.operation_id)
    view = creator.workflow.onboarding(creator.principal, receipt.operation_id)
    assert view.phase == "handoff"
    return receipt.operation_id, view


# Read authoritative rows independently of controller return values and UI labels.
def stored(c, identifier):
    with c.engine.connect() as connection:
        row = dict(
            connection.execute(select(operation).where(operation.c.id == identifier))
            .mappings()
            .one()
        )
        claims = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.operation_id == identifier,
                    audit_event.c.kind == "operation_responsibility_changed",
                )
            )
            .mappings()
            .all()
        )
        intent = (
            connection.execute(
                select(audit_event.c.data, audit_event.c.data_hash).where(
                    audit_event.c.id == row["current_intent_event_id"]
                )
            )
            .mappings()
            .one()
        )
        jobs = connection.scalar(
            text("SELECT count(*) FROM public.procrastinate_jobs WHERE args->>'operation_id'=:id"),
            {"id": str(identifier)},
        )

    return row, claims, dict(intent), jobs


# Takeover preserves intent/mailbox/owner pins, removes old UI actions and continues after
# creator revocation.
def test_takeover_and_revoked_creator_continuation(workflow_case):
    c = workflow_case
    a = colleague(c, "Creator")
    b = colleague(c, "Replacement")
    identifier, view = pending(c, a)
    before = stored(c, identifier)
    receipt = take_responsibility(
        b.workflow,
        b.principal,
        identifier,
        ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
    )
    after = stored(c, identifier)
    assert after[0]["responsible_actor_subject"] == b.principal.actor.key
    assert after[0]["revision"] == before[0]["revision"] + 1 and after[2] == before[2]
    assert len(after[1]) == 1 and after[3] == before[3]
    assert {
        key: value
        for key, value in after[0].items()
        if key not in {"responsible_actor_subject", "revision", "updated_at"}
    } == {
        key: value
        for key, value in before[0].items()
        if key not in {"responsible_actor_subject", "revision", "updated_at"}
    }
    assert not a.workflow.onboarding(a.principal, identifier).can_act
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == a.grant.id)
            .values(status="revoked", revoked_at=c.clock(), authorization_revision=uuid4())
        )
    current = b.workflow.onboarding(b.principal, identifier)
    b.workflow.onboarding_action(
        b.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=current.revision,
            action="verify_handoff",
            handoff=current.suggested_handoff,
        ),
    )
    c.worker.run(identifier)
    assert b.workflow.onboarding(b.principal, identifier).phase == "review"
    detail = SqlOperationDirectory(c.engine).detail(
        c.policy.workspace_id, identifier, b.principal.actor.key
    )
    assert detail.operation.responsible_administrator_name == "Replacement"
    assert (
        detail.operation.initiated_by == "Creator" and not detail.operation.can_take_responsibility
    )
    audit = SqlAuditDirectory(c.engine).directory(c.policy.workspace_id, AuditQuery(page_size=100))
    change = next(item for item in audit.items if item.kind == "operation_responsibility_changed")
    assert change.changes == ("Creator → Replacement",)
    assert receipt.state == "waiting"


# Exact replay never takes work back; returning to the creator uses a new audited current authority.
def test_replay_cycles_and_scope(workflow_case):
    c = workflow_case
    a = colleague(c, "Creator")
    b = colleague(c, "Replacement")
    identifier, view = pending(c, a)
    command = ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision)
    take_responsibility(b.workflow, b.principal, identifier, command)
    next_view = a.workflow.onboarding(a.principal, identifier)
    take_responsibility(
        a.workflow,
        a.principal,
        identifier,
        ResponsibilityCommand(client_request_key=uuid4(), expected_revision=next_view.revision),
    )
    current = stored(c, identifier)
    take_responsibility(b.workflow, b.principal, identifier, command)
    assert stored(c, identifier) == current
    assert current[0]["responsible_actor_subject"] == a.principal.actor.key and len(current[1]) == 2
    with pytest.raises(OrganizationConflict):
        take_responsibility(b.workflow, b.principal, uuid4(), command)
    with pytest.raises(OrganizationConflict):
        take_responsibility(
            b.workflow,
            b.principal,
            identifier,
            ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
        )


# The replacement grant must still match its captured revision when resumed work reaches dispatch.
def test_replacement_revoked_before_dispatch(workflow_case):
    c = workflow_case
    a = colleague(c, "Creator")
    b = colleague(c, "Replacement")
    identifier, view = pending(c, a)
    take_responsibility(
        b.workflow,
        b.principal,
        identifier,
        ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
    )
    current = b.workflow.onboarding(b.principal, identifier)
    b.workflow.onboarding_action(
        b.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=current.revision,
            action="verify_handoff",
            handoff=current.suggested_handoff,
        ),
    )
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == b.grant.id)
            .values(authorization_revision=uuid4())
        )
    c.worker.run(identifier)
    assert stored(c, identifier)[0]["state"] == "needs_attention"
    with c.engine.connect() as connection:
        outcome = (
            connection.execute(
                select(audit_event.c.data).where(
                    audit_event.c.operation_id == identifier,
                    audit_event.c.kind == "organization_action_outcome",
                )
            )
            .scalars()
            .all()
        )
    assert outcome[-1]["safe_code"] == "AUTHORIZATION_CHANGED"


# Row locks and expected revision allow one winner without assigning responsibility merely by
# reading.
def test_competing_claims(workflow_case):
    c = workflow_case
    a = colleague(c, "Creator")
    b = colleague(c, "Replacement")
    d = colleague(c, "Another admin")
    identifier, view = pending(c, a)
    command = ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision)

    # A stale competing request returns a closed conflict rather than overwriting the winning actor.
    def claim(user):
        try:
            return take_responsibility(user.workflow, user.principal, identifier, command).state
        except OrganizationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, (b, d))) == ["conflict", "waiting"]
    assert len(stored(c, identifier)[1]) == 1


# An audit insert failure rolls back responsibility, revision and time along with the missing
# evidence.
def test_audit_failure_rolls_back(workflow_case):
    c = workflow_case
    a = colleague(c, "Creator")
    b = colleague(c, "Replacement")
    identifier, view = pending(c, a)
    before = stored(c, identifier)

    # Interrupt only this command's evidence insertion, leaving all domain setup and reads genuine.
    def fail_audit(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("INSERT INTO public.audit_event")
            and parameters.get("kind") == "operation_responsibility_changed"
        ):
            raise RuntimeError("fixture audit write failure")

    event.listen(c.engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError):
            take_responsibility(
                b.workflow,
                b.principal,
                identifier,
                ResponsibilityCommand(client_request_key=uuid4(), expected_revision=view.revision),
            )
    finally:
        event.remove(c.engine, "before_cursor_execute", fail_audit)
    assert stored(c, identifier) == before
