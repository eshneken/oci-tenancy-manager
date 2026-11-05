"""Real financial transactions, concurrency, immutable storage and failure episodes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_configuration_updates_postgres import children
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.financial.contracts import CostPolicy, CostRefreshRequest
from otm.financial.service import CostCollections, CostConflict
from otm.financial.worker import CostCollectionWorker
from otm.providers.budget import BudgetReadUnavailable, SimulatedBudgetFacade
from otm.storage.admission import RequestConflict
from otm.storage.enqueue import COST_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.tables import (
    administrator,
    financial_collection,
    financial_observation,
    operation,
    tenancy,
)
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Compose real admission and native transactional queue; only provider response facts are
# replaceable.
def costs(c, *, facade=None, profile=None, notifications=None):
    profile = profile or CostPolicy(retry_delays_seconds=(1, 1))
    facade = facade or SimulatedBudgetFacade(c.loader().policy)
    queue = InspectionEnqueuer(queue=workspace_queue(c.policy.workspace_id), task=COST_TASK)
    service = CostCollections(
        c.store, policy=c.loader().policy, policy_loader=c.loader, enqueuer=queue, profile=profile
    )
    worker = CostCollectionWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        facade,
        queue,
        profile=profile,
        notifications=notifications,
    )
    c.workflow.cost_collections = service
    return service, worker, facade


# Use a new command identity for deliberate refreshes; supplied identity is reserved for replay
# tests.
def request(identifier=None, key=None):
    return CostRefreshRequest(client_request_key=key or uuid4(), tenancy_id=identifier)


# Reads join compatible work, replay after completion, and preserve every configuration column.
def test_read_replay_join_and_immutable_scope(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = costs(c)
    with c.engine.connect() as connection:
        before = dict(
            connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        )
    command = request(identifier)
    first = service.start(c.principal, command)
    joined = service.start(c.principal, request(identifier))
    assert joined.joined_count == 1 and joined.operation_ids == first.operation_ids
    assert c.workflow.tenancies(c.principal, TenancyQuery()).costs_pending_count == 1
    worker.run(first.operation_ids[0])
    worker.run(first.operation_ids[0])
    assert service.start(c.principal, command) == first
    view = c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs
    assert (
        view.state == "current"
        and view.actual == "0.0000"
        and view.budget == "200.0000"
        and not view.pending
    )
    with c.engine.connect() as connection:
        assert (
            dict(
                connection.execute(select(tenancy).where(tenancy.c.id == identifier))
                .mappings()
                .one()
            )
            == before
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(financial_observation)
                .where(financial_observation.c.workspace_id == c.policy.workspace_id)
            )
            == 1
        )
    with pytest.raises(RequestConflict):
        service.start(c.principal, request(None, command.client_request_key))
    with c.engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            update(financial_observation)
            .where(financial_observation.c.workspace_id == c.policy.workspace_id)
            .values(actual_spend=1)
        )
    with c.engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            update(financial_collection)
            .where(financial_collection.c.workspace_id == c.policy.workspace_id)
            .values(state="queued")
        )


# Concurrent manual refreshes share one immutable collection instead of double billing a child.
def test_concurrent_admission_shares_work(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, _ = costs(c)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(
            pool.map(lambda _: service.start(c.principal, request(identifier)), range(2))
        )
    assert receipts[0].operation_ids == receipts[1].operation_ids
    assert sum(r.accepted_count for r in receipts) == sum(r.joined_count for r in receipts) == 1
    worker.run(receipts[0].operation_ids[0])
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(financial_collection)
                .where(financial_collection.c.workspace_id == c.policy.workspace_id)
            )
            == 1
        )


# Real DB connections remain available during provider calls; partial facts never borrow old
# forecasts.
def test_partial_overrun_and_late_result_order(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, facade = costs(c)
    original = facade.read_managed_budget
    result = {}

    # The SDK seam deliberately obtains the same workspace lock to prove no transaction
    # spans its GET.
    def read(target, stored, at):
        with c.engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout='100ms'"))
            connection.execute(
                text("SELECT id FROM org_workspace WHERE id=:id FOR UPDATE"),
                {"id": c.policy.workspace_id},
            )
        return original(target, stored, at).model_copy(update=result)

    facade.read_managed_budget = read
    result.update(actual_spend="201.0000", forecasted_spend="320.0000")
    first = service.start(c.principal, request(identifier))
    worker.run(first.operation_ids[0])
    view = c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs
    assert view.actual_over_budget and view.forecast_over_budget
    c.clock.return_value += timedelta(seconds=2)
    result.update(actual_spend="210.0000", forecasted_spend=None)
    second = service.start(c.principal, request(identifier))
    worker.run(second.operation_ids[0])
    view = c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs
    assert view.state == "partial" and view.forecast is None and view.actual == "210.0000"
    result.update(actual_spend="999.0000", time_spend_computed=c.clock() - timedelta(seconds=10))
    c.clock.return_value += timedelta(seconds=2)
    third = service.start(c.principal, request(identifier))
    worker.run(third.operation_ids[0])
    assert c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs.actual == "210.0000"
    c.clock.return_value += timedelta(days=32)
    with c.engine.connect() as connection:
        registered = (
            connection.execute(select(tenancy).where(tenancy.c.id == identifier)).mappings().one()
        )
        assert (
            service.summaries(connection, c.policy.workspace_id, [registered])[identifier].state
            == "prior_cycle"
        )


# Failed reads preserve facts and use finite native retry delays without blocking successful peers.
def test_fleet_isolation_and_bounded_retries(workflow_case):
    c = workflow_case
    identifiers = children(c)
    service, worker, facade = costs(c)
    original = facade.read_managed_budget

    # One child's read fails while a peer independently publishes its own complete response.
    def read(target, stored, at):
        if target.configuration.tenancy_id == identifiers[0]:
            raise BudgetReadUnavailable("COST_READ_UNAVAILABLE")
        return original(target, stored, at)

    facade.read_managed_budget = read
    receipt = service.start(c.principal, request())
    for _ in range(3):
        worker.run(receipt.operation_ids[0])
        c.clock.return_value += timedelta(seconds=2)
    assert (
        c.workflow.tenancy_detail(c.principal, identifiers[0]).tenancy.costs.state == "unavailable"
    )
    assert c.workflow.tenancy_detail(c.principal, identifiers[1]).tenancy.costs.state == "current"
    with c.engine.connect() as connection:
        rows = (
            connection.execute(
                select(financial_collection).where(
                    financial_collection.c.workspace_id == c.policy.workspace_id
                )
            )
            .mappings()
            .all()
        )
        assert sorted((r["state"], r["attempts"]) for r in rows) == [
            ("failed", 3),
            ("succeeded", 1),
        ]
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == receipt.operation_ids[0])
            )
            == "failed"
        )


# A budget revision or revoked grant during GET fences publication even when the remote read
# succeeds.
@pytest.mark.parametrize("change", ["revision", "grant", "profile", "cycle"])
def test_dispatch_and_publication_fences(workflow_case, change):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, facade = costs(c)
    original = facade.read_managed_budget

    # Mutate only disposable registry/grant state between the committed claim and publication.
    def read(target, stored, at):
        response = original(target, stored, at)
        with c.engine.begin() as connection:
            if change == "revision":
                connection.execute(
                    update(tenancy)
                    .where(tenancy.c.id == identifier)
                    .values(revision=tenancy.c.revision + 1)
                )
            if change == "grant":
                connection.execute(
                    update(administrator)
                    .where(administrator.c.workspace_id == c.policy.workspace_id)
                    .values(authorization_revision=uuid4())
                )
        if change == "profile":
            worker.profile_loader = lambda: CostPolicy(source_max_age_seconds=1)
        if change == "cycle":
            c.clock.return_value += timedelta(days=32)
        return response

    facade.read_managed_budget = read
    receipt = service.start(c.principal, request(identifier))
    worker.run(receipt.operation_ids[0])
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(financial_observation)
                .where(financial_observation.c.workspace_id == c.policy.workspace_id)
            )
            == 0
        )
        assert (
            connection.scalar(
                select(financial_collection.c.state).where(
                    financial_collection.c.workspace_id == c.policy.workspace_id
                )
            )
            == "superseded"
        )


# Cross-child hash/context substitutions are rejected by the composite FK before views can read
# them.
def test_observation_exact_context_foreign_key(workflow_case):
    c = workflow_case
    children(c)
    service, worker, _ = costs(c)
    receipt = service.start(c.principal, request())
    worker.run(receipt.operation_ids[0])
    with c.engine.connect() as connection:
        row = dict(
            connection.execute(
                select(financial_observation).where(
                    financial_observation.c.workspace_id == c.policy.workspace_id
                )
            )
            .mappings()
            .first()
        )
    row["id"] = uuid4()
    with (
        c.engine.begin() as connection,
        pytest.raises(IntegrityError, match="ck_financial_observation_period"),
    ):
        # PostgreSQL validates row CHECKs before its duplicate-collection uniqueness check.
        row["period_end"] = None
        connection.execute(financial_observation.insert().values(**row))
    row["period_end"] = row["period_start"] + timedelta(days=30)
    row["collection_id"] = uuid4()
    with c.engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(financial_observation.insert().values(**row))
    with pytest.raises(CostConflict, match="COST_TARGET_NOT_FOUND"):
        service.start(c.principal, request(uuid4()))


# Exhausted episodes notify active admins once, preserve stage routing and reset after a
# successful read.
def test_exhausted_cost_email_episode_and_delivery(workflow_case):
    from otm.email_policy import MailPolicy
    from otm.notifications.contracts import DeliveryResult
    from otm.notifications.service import LifecycleNotifier, decode_intent
    from otm.notifications.worker import NotificationDeliveryWorker, NotificationEnqueuer
    from otm.storage.tables import notification_outbox

    c = workflow_case
    identifier = children(c, 1)[0]
    mail = MailPolicy(environment="staging", email_override="capture@example.test")
    queue = NotificationEnqueuer(workspace_queue(c.policy.workspace_id))
    notifier = LifecycleNotifier(mail, queue)
    service, worker, facade = costs(
        c, profile=CostPolicy(retry_delays_seconds=()), notifications=notifier
    )
    original = facade.read_managed_budget
    facade.read_managed_budget = Mock(side_effect=BudgetReadUnavailable("safe"))
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.workspace_id == c.policy.workspace_id)
            .values(email="operator@example.test")
        )
    first = service.start(c.principal, request(identifier))
    worker.run(first.operation_ids[0])
    c.clock.return_value += timedelta(seconds=1)
    second = service.start(c.principal, request(identifier))
    worker.run(second.operation_ids[0])
    with c.engine.connect() as connection:
        rows = (
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.workspace_id == c.policy.workspace_id
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == 1 and rows[0]["state"] == "pending"
        intent = decode_intent(rows[0])
        assert (
            intent.delivery_recipient == "capture@example.test"
            and intent.original_recipient == "operator@example.test"
        )
    # A malformed no-observation completion and unrelated registry edit cannot reopen the episode
    # or suppress its still-unsent administrator notice.
    c.clock.return_value += timedelta(seconds=1)
    facade.read_managed_budget = Mock(return_value={})
    malformed = service.start(c.principal, request(identifier))
    worker.run(malformed.operation_ids[0])
    with c.engine.begin() as connection:
        connection.execute(
            update(tenancy)
            .where(tenancy.c.id == identifier)
            .values(revision=tenancy.c.revision + 1)
        )
    c.clock.return_value += timedelta(seconds=1)
    facade.read_managed_budget = Mock(side_effect=BudgetReadUnavailable("safe"))
    unchanged = service.start(c.principal, request(identifier))
    worker.run(unchanged.operation_ids[0])
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(notification_outbox)
                .where(notification_outbox.c.workspace_id == c.policy.workspace_id)
            )
            == 1
        )
    transport = Mock(profile_hash=None)
    transport.send.return_value = DeliveryResult(state="accepted", safe_code="SMTP_ACCEPTED")
    delivery = NotificationDeliveryWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        lambda: mail,
        transport,
        queue,
        cost_context_loader=lambda: (c.loader(), worker.profile),
    )
    delivery.run(rows[0]["id"])
    assert transport.send.call_args.args[0].recipient == "capture@example.test"
    delivery.run(rows[0]["id"])
    assert transport.send.call_count == 1
    c.clock.return_value += timedelta(seconds=1)
    facade.read_managed_budget = original
    recovery = service.start(c.principal, request(identifier))
    worker.run(recovery.operation_ids[0])
    c.clock.return_value += timedelta(seconds=1)
    facade.read_managed_budget = Mock(side_effect=BudgetReadUnavailable("safe"))
    renewed = service.start(c.principal, request(identifier))
    worker.run(renewed.operation_ids[0])
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(notification_outbox)
                .where(notification_outbox.c.workspace_id == c.policy.workspace_id)
            )
            == 2
        )


# Retained numbers stay degraded through retries and new pending requests until a real read.
def test_failure_stays_visible_through_new_pending_work(workflow_case):
    c = workflow_case
    identifier = children(c, 1)[0]
    service, worker, facade = costs(c)
    first = service.start(c.principal, request(identifier))
    worker.run(first.operation_ids[0])
    original = c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs.retrieved_at
    facade.read_managed_budget = Mock(side_effect=BudgetReadUnavailable("safe"))
    c.clock.return_value += timedelta(seconds=1)
    failed = service.start(c.principal, request(identifier))
    for attempt in range(3):
        worker.run(failed.operation_ids[0])
        view = c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs
        assert (
            view.state == "unavailable"
            and not view.actual_over_budget
            and view.retrieved_at == original
        )
        assert view.pending == (attempt < 2)
        c.clock.return_value += timedelta(seconds=2)
    service.start(c.principal, request(identifier))
    assert c.workflow.tenancy_detail(c.principal, identifier).tenancy.costs.state == "unavailable"
