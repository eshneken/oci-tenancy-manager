"""Manual reads, current authority, late callbacks and sealed PostgreSQL evidence."""

import csv
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import DBAPIError
from test_operation_responsibility_postgres import colleague
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.audit.contracts import AuditExportQuery, AuditQuery
from otm.operations.views import OperationQuery
from otm.providers.presence_simulator import simulated_presence_inspection
from otm.storage.admission import RequestConflict
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import SqlAuditExport
from otm.storage.enqueue import PRESENCE_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import administrator, tenancy
from otm.storage.tables import user_presence_check as checks
from otm.tenancies.presence import PresenceChecks
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.presence_worker import UserPresenceWorker
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Compose one real onboarding setup from an explicitly owned authorized workflow fixture.
def make_presence(c):
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, created = action(c, person.id, "create_tenancy")
    complete_setup(c, created.operation_id)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    service = PresenceChecks(
        c.store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=PRESENCE_TASK),
    )
    worker = UserPresenceWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.workflow.policy,
        simulated_presence_inspection,
    )
    c.workflow.presence_checks = service
    return SimpleNamespace(
        **{**vars(c), "child": child, "person": person, "service": service, "reader": worker}
    )


# Each scenario receives a separate authorized workspace and authenticated producer capture.
@pytest.fixture
def presence_case(workflow_case):
    return make_presence(workflow_case)


# Current-state assertions go through the same read-only projection used by the browser.
def view(c):
    return c.workflow.required_users(c.principal, c.child.id)


# Return the exact saved row for immutable-identity/replay tests without reading other workspaces.
def check_row(c, identifier):
    with c.engine.connect() as connection:
        return dict(
            connection.execute(
                select(checks).where(
                    checks.c.workspace_id == c.policy.workspace_id,
                    checks.c.operation_id == identifier,
                )
            )
            .mappings()
            .one()
        )


# Manual admission and same-key replay are atomic; provider reads occur outside database locks.
def test_admission_read_publication_and_directory(presence_case):
    c = presence_case
    command = PresenceCheckRequest(client_request_key=uuid4())
    before = c.workflow.tenancy_detail(c.principal, c.child.id)
    response = c.service.start(c.principal, c.child.id, command)
    assert c.service.start(c.principal, c.child.id, command).operation_id == response.operation_id
    assert view(c).pending_operation_id == response.operation_id
    assert all(u.presence.state == "not_checked" for u in view(c).users)
    with pytest.raises(RequestConflict):
        c.service.start(c.principal, uuid4(), command)
    with pytest.raises(OrganizationConflict, match="NOT_FOUND"):
        c.service.start(c.principal, uuid4(), PresenceCheckRequest(client_request_key=uuid4()))
    active = [0]

    # Instrument actual engine transaction lifetimes around provider work, not a mocked SQL
    # boundary.
    def began(connection):
        active[0] += 1

    # Every commit/rollback releases one observed transaction before adapter invocation.
    def ended(connection):
        active[0] -= 1

    # The production adapter fixture is selected explicitly, after every SQL transaction has closed.
    def factory(snapshot, source, clock):
        assert active[0] == 0
        return simulated_presence_inspection(snapshot, source, clock)

    event.listen(c.engine, "begin", began)
    event.listen(c.engine, "commit", ended)
    event.listen(c.engine, "rollback", ended)
    try:
        c.reader.inspection_factory = factory
        c.reader.run(response.operation_id)
    finally:
        event.remove(c.engine, "begin", began)
        event.remove(c.engine, "commit", ended)
        event.remove(c.engine, "rollback", ended)
    result = view(c)
    assert result.pending_operation_id is None and result.check_available
    assert [u.presence.state for u in result.users] == ["present", "present"]
    after = c.workflow.tenancy_detail(c.principal, c.child.id)
    assert after.tenancy.required_users.state == "present"
    assert (
        after.model_copy(
            update={
                "tenancy": after.tenancy.model_copy(
                    update={"required_users": before.tenancy.required_users}
                )
            }
        )
        == before
    )
    record = check_row(c, response.operation_id)
    c.reader.inspection_factory = Mock(side_effect=AssertionError("replay provider call"))
    c.reader.run(response.operation_id)
    assert check_row(c, response.operation_id) == record
    assert c.service.start(c.principal, c.child.id, command).state == "succeeded"
    detail = SqlOperationDirectory(c.engine).detail(c.policy.workspace_id, response.operation_id)
    assert (
        detail.operation.title == "Check required users"
        and detail.operation.result_tenancy_id == c.child.id
    )
    assert detail.steps[0].safe_code == "USER_PRESENCE_CHECK_COMPLETE"
    recorded = next(event for event in detail.events if event.kind == "required_user_check_outcome")
    assert len(recorded.user_checks) == 5
    assert recorded.user_checks[0].anchor == "automation-presence"
    assert recorded.user_checks[0].facts[0].state == "present"
    assert recorded.user_checks[-1].anchor == "recovery-policy"
    assert "context" not in recorded.model_dump_json()

    history = SqlAuditDirectory(c.engine).directory(
        c.policy.workspace_id, AuditQuery(query=str(response.operation_id))
    )
    outcome = next(e for e in history.items if e.kind == "required_user_check_outcome")
    assert outcome.category == "operations" and outcome.actor_name == "User presence worker"
    assert any(r.name == c.child.name for r in outcome.resources)
    exported = SqlAuditExport(c.engine, c.clock).export(c.principal, AuditExportQuery())
    rows = list(csv.DictReader(StringIO(exported.decode("utf-8-sig"))))
    assert any(row["kind"] == "required_user_check_outcome" for row in rows)

    assert (
        SqlOperationDirectory(c.engine)
        .directory(c.policy.workspace_id, OperationQuery())
        .attention_count
        == 0
    )
    # Every accepted distinct key is stored, so a lost response still replays after completion.
    extra = PresenceCheckRequest(client_request_key=uuid4())
    second = c.service.start(c.principal, c.child.id, extra)
    assert second.operation_id != response.operation_id
    c.reader.run(second.operation_id)
    assert c.service.start(c.principal, c.child.id, extra).operation_id == second.operation_id
    with pytest.raises(RequestConflict):
        c.service.start(c.principal, uuid4(), extra)
    for statement in (
        checks.delete().where(checks.c.operation_id == response.operation_id),
        update(checks).where(checks.c.operation_id == response.operation_id).values(state="queued"),
    ):
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            connection.execute(statement)


# Missing, denied and unnormalized failures remain independent per subject and replace prior
# evidence.
def test_subject_results_failures_and_freshness(presence_case):
    c = presence_case
    for fault in ("missing_recovery", "denied", "error", "timeout", "wrong_subject"):
        command = PresenceCheckRequest(client_request_key=uuid4())
        receipt = c.service.start(c.principal, c.child.id, command)

        # Fixture state changes independently of the immutable expected application bindings.
        def factory(snapshot, source, clock, fault=fault):
            inspection = simulated_presence_inspection(snapshot, source, clock)
            provider = inspection.provider
            if fault == "missing_recovery":
                provider._users.pop(
                    (
                        source.workspace_id,
                        source.tenancy_ocid,
                        source.domain_ocid,
                        source.recovery.scim_resource_id,
                    )
                )
            elif fault == "denied":
                access = next(iter(provider._access.values()))
                provider.set_access(access.model_copy(update={"permitted": False}))
            elif fault == "error":
                return Mock(
                    inspect=Mock(side_effect=RuntimeError("private credentials must not escape"))
                )
            elif fault == "timeout":
                c.clock.return_value += timedelta(seconds=31)
            else:
                original = inspection.inspect

                # Returning another exact subject must not certify the requested account.
                def swapped(request, original=original):
                    result = original(request)
                    return result.model_copy(
                        update={
                            "target": result.target.model_copy(update={"scim_resource_id": "wrong"})
                        }
                    )

                return Mock(inspect=swapped)
            return inspection

        c.reader.inspection_factory = factory
        c.reader.run(receipt.operation_id)
        result = view(c)
        expected = ["present", "missing"] if fault == "missing_recovery" else ["unknown", "unknown"]
        assert [u.presence.state for u in result.users] == expected
        assert all(u.presence.operation_id == receipt.operation_id for u in result.users)
    c.clock.return_value += timedelta(hours=24)
    # Inspect the age projection directly; the original browser session legitimately expired.
    from otm.tenancies.required_users import required_user_records

    with c.engine.connect() as connection:
        child = (
            connection.execute(select(tenancy).where(tenancy.c.id == c.child.id)).mappings().one()
        )
        records = required_user_records(connection, c.policy.workspace_id, child)
        aged = c.service.project(connection, c.policy.workspace_id, child, records)
    assert all(u.presence.stale for u in aged.users)


# A stale native callback cannot seal over a newer attempt or a later admitted check.
def test_attempt_and_acquisition_order_fences(presence_case):
    c = presence_case
    response = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    # SQL CHECK must reject NULL timestamps explicitly, rather than accepting UNKNOWN.
    with pytest.raises(DBAPIError), c.engine.begin() as connection:
        connection.execute(
            update(checks)
            .where(checks.c.operation_id == response.operation_id)
            .values(state="reading", attempt_id=uuid4(), attempt_number=1, started_at=None)
        )
    older = c.reader.begin(response.operation_id)
    newer = c.reader.begin(response.operation_id)
    assert newer[1]["attempt_number"] == 2
    inspection = simulated_presence_inspection(older[0].intent.snapshot, older[3], c.clock)
    old_results = tuple(inspection.inspect(command) for command in older[2])
    c.reader.finish(response.operation_id, older[1]["attempt_id"], older[2], old_results)
    assert check_row(c, response.operation_id)["state"] == "reading"
    inspection = simulated_presence_inspection(newer[0].intent.snapshot, newer[3], c.clock)
    results = tuple(inspection.inspect(command) for command in newer[2])
    c.reader.finish(response.operation_id, newer[1]["attempt_id"], newer[2], results)
    assert check_row(c, response.operation_id)["state"] == "complete"
    c.reader.finish(response.operation_id, older[1]["attempt_id"], older[2], old_results)
    assert check_row(c, response.operation_id)["attempt_number"] == 2
    c.clock.return_value += timedelta(seconds=1)
    other = colleague(c, "Read Colleague")
    other_service = PresenceChecks(
        other.store, policy=c.workflow.policy, policy_loader=c.loader, enqueuer=c.service.enqueuer
    )
    first = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    ticket = c.reader.begin(first.operation_id)
    second = other_service.start(
        other.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    c.reader.run(second.operation_id)
    inspection = simulated_presence_inspection(ticket[0].intent.snapshot, ticket[3], c.clock)
    c.reader.finish(
        first.operation_id,
        ticket[1]["attempt_id"],
        ticket[2],
        tuple(inspection.inspect(command) for command in ticket[2]),
    )
    assert all(u.presence.operation_id == second.operation_id for u in view(c).users)


# A revoked responsible grant never publishes positive evidence even when the provider read
# succeeded.
def test_admin_revocation_during_read(presence_case):
    c = presence_case
    other = colleague(c, "Read Administrator")
    service = PresenceChecks(
        other.store, policy=c.workflow.policy, policy_loader=c.loader, enqueuer=c.service.enqueuer
    )
    response = service.start(
        other.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    ticket = c.reader.begin(response.operation_id)
    inspection = simulated_presence_inspection(ticket[0].intent.snapshot, ticket[3], c.clock)
    results = tuple(inspection.inspect(command) for command in ticket[2])
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == other.grant.id)
            .values(status="revoked", authorization_revision=uuid4(), revoked_at=c.clock())
        )
    c.reader.finish(response.operation_id, ticket[1]["attempt_id"], ticket[2], results)
    assert check_row(c, response.operation_id)["state"] == "superseded"
    assert all(u.presence.state == "unknown" for u in view(c).users)


# Tenant termination between acquisition and publication retires authority and discards positive
# reads.
def test_termination_during_read(presence_case):
    c = presence_case
    response = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    ticket = c.reader.begin(response.operation_id)
    inspection = simulated_presence_inspection(ticket[0].intent.snapshot, ticket[3], c.clock)
    results = tuple(inspection.inspect(command) for command in ticket[2])
    _, deleted = action(c, c.person.id, "delete_tenancy", tenancy_id=c.child.id)
    c.worker.run(deleted.operation_id)
    c.reader.finish(response.operation_id, ticket[1]["attempt_id"], ticket[2], results)
    assert check_row(c, response.operation_id)["state"] == "superseded"
    assert not view(c).check_available and all(
        u.presence.state == "not_checked" for u in view(c).users
    )


# The inventory and detailed cards share current facts, bounded SQL and exact workspace scope.
def test_inventory_summary_parity_and_fixed_reads(presence_case, pg_engine, tmp_path, factors):
    from test_local_auth_postgres import login_case as make_login
    from test_organization_storage_postgres import organization_case as make_org
    from test_organization_workflows_postgres import workflow_case as make_workflow

    from otm.tenancies.presence_summary import summaries

    c = presence_case
    # A separately authorized workspace owns its own real child and complete provider evidence.
    (tmp_path / "foreign").mkdir()
    other_login = make_login.__wrapped__(pg_engine, tmp_path / "foreign", factors)
    other_org = make_org.__wrapped__(other_login)
    other_flow = make_workflow.__wrapped__(other_org)
    other = make_presence(other_flow)
    other_request = other.service.start(
        other.principal, other.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    other.reader.run(other_request.operation_id)
    request = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    assert c.workflow.tenancies(c.principal, TenancyQuery()).items[0].required_users.checking
    c.reader.run(request.operation_id)
    directory = c.workflow.tenancies(c.principal, TenancyQuery())
    child = next(item for item in directory.items if item.id == c.child.id)
    assert child.required_users.state == "present" and not child.required_users.checking
    assert all(item.id != other.child.id for item in directory.items)
    detailed = c.workflow.required_users(c.principal, c.child.id)
    assert child.required_users.automation == detailed.users[0].presence
    assert child.required_users.recovery == detailed.users[1].presence
    assert (
        c.workflow.tenancy_detail(c.principal, c.child.id).tenancy.required_users
        == child.required_users
    )
    reads = []

    # Count actual database SELECTs for this projection rather than mocking a claimed query budget.
    def queried(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    event.listen(c.engine, "before_cursor_execute", queried)
    try:
        with c.engine.connect() as connection:
            row = (
                connection.execute(select(tenancy).where(tenancy.c.id == c.child.id))
                .mappings()
                .one()
            )
            reads.clear()
            current = summaries(c.service, connection, c.policy.workspace_id, (row,))
            assert len(reads) == 4 and current[row["id"]] == child.required_users
            assert summaries(c.service, connection, "foreign", ()) == {}
    finally:
        event.remove(c.engine, "before_cursor_execute", queried)


# Real membership work preserves saved reads across service reconstruction and registry edits.
def test_saved_reads_survive_shared_membership(workflow_case):
    from test_baseline_pinning_postgres import publish
    from test_financial_postgres import costs, request

    c = workflow_case
    publish(c)
    people = {p.email: p for p in c.store.head(c.principal).people}
    _, created = action(c, people["one@example.test"].id, "create_tenancy", tenancy_kind="shared")
    complete_setup(c, created.operation_id)
    child = c.workflow.onboarding(c.principal, created.operation_id).tenancy_id
    service = PresenceChecks(
        c.store,
        policy=c.workflow.policy,
        policy_loader=c.loader,
        enqueuer=InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=PRESENCE_TASK),
    )
    reader = UserPresenceWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        c.workflow.policy,
        simulated_presence_inspection,
    )
    c.workflow.presence_checks = service
    financial, collector, facade = costs(c)
    checked = service.start(c.principal, child, PresenceCheckRequest(client_request_key=uuid4()))
    reader.run(checked.operation_id)
    collected = financial.start(c.principal, request(child))
    collector.run(collected.operation_ids[0])
    before_users = c.workflow.required_users(c.principal, child)
    before_cost = c.workflow.tenancy_detail(c.principal, child).tenancy.costs
    assert before_cost.state == "current"
    assert all(u.presence.state == "present" for u in before_users.users)
    parent = c.workflow.tenancy_detail(c.principal, child).compartment_parents[0].ocid
    _, joined = action(
        c,
        people["engineer@example.test"].id,
        "join_shared",
        tenancy_id=child,
        parent_compartment_ocid=parent,
        compartment_name="member",
    )
    c.worker.run(joined.operation_id)
    after_users = c.workflow.required_users(c.principal, child)
    after_cost = c.workflow.tenancy_detail(c.principal, child).tenancy.costs
    assert [u.presence for u in after_users.users] == [u.presence for u in before_users.users]
    assert after_cost == before_cost
    inventory = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert inventory.costs == before_cost
    assert inventory.required_users.state == "present"

    # Projection compatibility ignores only registry revision, not billing identity or authority.
    from otm.financial.context import source_context
    from otm.financial.records import current_records

    with c.engine.connect() as connection:
        current = connection.execute(select(tenancy).where(tenancy.c.id == child)).mappings().one()
        source = source_context(current, c.workflow.policy, financial.profile)
        for field in (
            "tenancy_id",
            "tenancy_ocid",
            "parent",
            "organization",
            "baseline_id",
            "configuration_id",
            "policy_revision",
            "access_binding_id",
            "budget_ocid",
            "profile",
        ):
            changed = {
                **source,
                field: {**source["profile"], "retry_delays_seconds": [1]}
                if field == "profile"
                else "changed",
            }
            assert current_records(connection, c.policy.workspace_id, {child: changed}) == ({}, {})
        assert current_records(connection, "foreign-workspace", {child: source}) == ({}, {})
        # Reconstructed services cannot depend on in-memory caches or fetch the provider.
        facade.read_managed_budget = Mock(
            side_effect=AssertionError("Projection must not fetch provider")
        )
        costs(c, facade=facade)
        c.workflow.presence_checks = PresenceChecks(
            c.store,
            policy=c.workflow.policy,
            policy_loader=c.loader,
            enqueuer=InspectionEnqueuer(workspace_queue(c.policy.workspace_id), task=PRESENCE_TASK),
        )
        assert c.workflow.tenancy_detail(c.principal, child).tenancy.costs == before_cost
        assert [u.presence for u in c.workflow.required_users(c.principal, child).users] == [
            u.presence for u in before_users.users
        ]
