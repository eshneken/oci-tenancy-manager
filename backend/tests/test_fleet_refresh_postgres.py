"""Disposable SQL/native admission validates fleet read coverage, replay, joins and no repairs."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from test_configuration_drift_postgres import checks
from test_financial_postgres import costs
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case
from test_user_presence_checks_postgres import presence_case

from otm.storage.tables import operation, tenancy, user_presence_check
from otm.tenancies.refresh import refresh_fleet, refresh_status
from otm.tenancies.refresh_contracts import FleetRefreshRequest, FleetRefreshStatusRequest

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case", "presence_case"]


# Compose only the existing real SQL services and read workers around the registered presence child.
def compose(c):
    _, financial, _ = costs(c)
    _, configuration = checks(c)
    return {"costs": financial, "users": c.reader, "configuration": configuration}


# Existing read workers publish observations without changing registry or desired state.
def test_fleet_read_completion_replay_and_join(presence_case):
    c = presence_case
    workers = compose(c)
    with c.engine.connect() as connection:
        before = dict(
            connection.execute(select(tenancy).where(tenancy.c.id == c.child.id)).mappings().one()
        )
    command = FleetRefreshRequest(client_request_key=uuid4())
    first = refresh_fleet(c.workflow, c.principal, command)
    assert first.tenancy_count == 1
    assert all(
        len(category.operation_ids) == 1
        and not category.skipped_count
        and not category.failed_count
        for category in first.categories
    )
    joined = refresh_fleet(c.workflow, c.principal, FleetRefreshRequest(client_request_key=uuid4()))
    assert [category.operation_ids for category in joined.categories] == [
        category.operation_ids for category in first.categories
    ]
    assert refresh_fleet(c.workflow, c.principal, command) == first
    ids = tuple(key for category in first.categories for key in category.operation_ids)
    poll = FleetRefreshStatusRequest(operation_ids=ids)
    assert all(job.state == "pending" for job in refresh_status(c.workflow, c.principal, poll).jobs)
    for category in first.categories:
        workers[category.category].run(category.operation_ids[0])
    assert all(
        job.state == "finished" for job in refresh_status(c.workflow, c.principal, poll).jobs
    )
    assert refresh_fleet(c.workflow, c.principal, command) == first
    assert c.workflow.tenancy_detail(c.principal, c.child.id).tenancy.costs.state == "current"
    assert all(
        user.presence.state == "present"
        for user in c.workflow.required_users(c.principal, c.child.id).users
    )
    with c.engine.connect() as connection:
        after = dict(
            connection.execute(select(tenancy).where(tenancy.c.id == c.child.id)).mappings().one()
        )
        assert before == after
        assert (
            connection.execute(select(operation.c.id).where(operation.c.id.in_(ids))).rowcount != 0
        )


# Two concurrent callers cannot double-admit compatible checks through the existing workspace locks.
def test_concurrent_fleet_requests_join_existing_reads(presence_case):
    c = presence_case
    compose(c)
    with c.engine.connect() as connection:
        original_checks = set(connection.scalars(select(user_presence_check.c.operation_id)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(
            pool.map(
                lambda _: refresh_fleet(
                    c.workflow, c.principal, FleetRefreshRequest(client_request_key=uuid4())
                ),
                range(2),
            )
        )
    assert [category.operation_ids for category in receipts[0].categories] == [
        category.operation_ids for category in receipts[1].categories
    ]
    with c.engine.connect() as connection:
        checks_after = set(connection.scalars(select(user_presence_check.c.operation_id)))
        user_ids = set(receipts[0].categories[1].operation_ids)
        assert checks_after == original_checks | user_ids
        assert len(checks_after - original_checks) == 1


# Registry mis-parenting and inactive records never gain authority through the fleet wrapper.
@pytest.mark.parametrize("damage", ["inactive", "parent", "organization"])
def test_ineligible_registry_is_not_refreshed(presence_case, damage):
    c = presence_case
    compose(c)
    values = (
        {"status": "terminating"}
        if damage == "inactive"
        else {"tenancy_ocid": c.workflow.policy.parent_tenancy_ocid}
        if damage == "parent"
        else {"organization_id": "different-org"}
    )
    if damage == "parent":
        # The database rejects a parent record before the batch can gain any target authority.
        with (
            pytest.raises(IntegrityError, match="ck_tenancy_qualification"),
            c.engine.begin() as connection,
        ):
            connection.execute(update(tenancy).where(tenancy.c.id == c.child.id).values(**values))
        return
    with c.engine.begin() as connection:
        connection.execute(update(tenancy).where(tenancy.c.id == c.child.id).values(**values))
    result = refresh_fleet(c.workflow, c.principal, FleetRefreshRequest(client_request_key=uuid4()))
    assert result.tenancy_count == 0 and all(
        not category.operation_ids for category in result.categories
    )


# Paused execution skips work without clearing previous observations or publishing false progress.
def test_paused_fleet_retains_previous_records(presence_case):
    c = presence_case
    compose(c)
    c.loader.return_value.execution_paused = True
    result = refresh_fleet(c.workflow, c.principal, FleetRefreshRequest(client_request_key=uuid4()))
    assert result.tenancy_count == 1
    assert all(
        category.skipped_count == 1 and not category.failed_count and not category.operation_ids
        for category in result.categories
    )
