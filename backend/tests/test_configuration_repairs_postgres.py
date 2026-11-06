"""Real PostgreSQL repair admission, concurrency fences and retained findings on failure."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from test_baseline_pinning_postgres import publish
from test_configuration_drift_postgres import checks, scenario
from test_configuration_updates_postgres import children, updates
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.configuration.drift_contracts import ConfigurationCheckRequest
from otm.configuration.repair_contracts import ConfigurationRepairRequest
from otm.configuration.rollout_contracts import ConfigurationUpdate
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import configuration_check, tenancy, tenancy_configuration

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Establish actual qualified ownership, missing objects and a fresh sealed check before repair.
@pytest.fixture
def repair_case(workflow_case):
    c = workflow_case
    c.identifier = children(c, 1)[0]
    c.checks, check_worker = checks(c)
    for category in ("policy", "quota"):
        scenario(c, c.identifier, "missing", category)
    check = c.checks.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=c.identifier)
    )
    check_worker.run(check.operation_id)
    c.repairs, c.repair_worker, facade = updates(c)
    c.repairs.repair_facade = facade
    c.repair_facade = facade
    c.check_worker = check_worker
    return c


# Freeze a reviewed category against its assigned immutable baseline.
def command(c, categories=("policy",)):
    preview = c.repairs.preview_repair(
        c.principal, ConfigurationRepairRequest(tenancy_id=c.identifier, categories=categories)
    )
    return ConfigurationUpdate(
        client_request_key=uuid4(),
        tenancy_id=c.identifier,
        repair_categories=categories,
        preview_hash=preview.preview_hash,
    )


# Preserve findings and desired/verified heads; keep unselected drift after completion.
def test_repair_preserves_assignment_and_unselected_drift(repair_case):
    c = repair_case
    with c.engine.connect() as con:
        before = dict(
            con.execute(select(tenancy).where(tenancy.c.id == c.identifier)).mappings().one()
        )
        count = con.scalar(select(func.count()).select_from(tenancy_configuration))
    request = command(c)
    receipt = c.repairs.start(c.principal, request)
    assert c.checks.detail(c.principal, c.identifier).confirmed_issue_count == 2
    assert c.repairs.start(c.principal, request).operation_id == receipt.operation_id
    publish(c, "750")
    c.repair_worker.run(receipt.operation_id)
    c.repair_worker.run(receipt.operation_id)
    progress = c.repairs.progress(c.principal, receipt.operation_id)
    assert progress.state == "succeeded" and progress.change_kind == "repair"
    assert progress.baseline.id == before["baseline_version_id"]
    summary = c.checks.detail(c.principal, c.identifier)
    assert summary.state == "drifted" and summary.confirmed_issue_count == 1
    assert next(item for item in summary.categories if item.category == "quota").state == "missing"
    with c.engine.connect() as con:
        after = con.execute(select(tenancy).where(tenancy.c.id == c.identifier)).mappings().one()
        for key in (
            "baseline_version_id",
            "verified_baseline_version_id",
            "desired_configuration_id",
            "last_verified_configuration_id",
            "configuration_verified_at",
        ):
            assert after[key] == before[key]
        assert con.scalar(select(func.count()).select_from(tenancy_configuration)) == count
        assert (
            con.scalar(
                select(func.count())
                .select_from(configuration_check)
                .where(configuration_check.c.operation_id == receipt.operation_id)
            )
            == 1
        )


# A failed readback retains findings and supports an exact replay with a fresh independent read.
def test_repair_failure_retry_and_full_matching(repair_case):
    c = repair_case
    receipt = c.repairs.start(c.principal, command(c, ("policy", "quota")))
    with patch.object(c.repair_facade, "read", side_effect=ValueError("private provider message")):
        c.repair_worker.run(receipt.operation_id)
    assert c.repairs.progress(c.principal, receipt.operation_id).can_retry
    failed = c.checks.detail(c.principal, c.identifier)
    assert failed.confirmed_issue_count == 2 and failed.state != "checking"
    assert failed.pending_operation_id is None
    c.repairs.retry(c.principal, receipt.operation_id)
    c.repair_worker.run(receipt.operation_id)
    assert c.repairs.progress(c.principal, receipt.operation_id).state == "succeeded"
    summary = c.checks.detail(c.principal, c.identifier)
    assert summary.state == "matching" and summary.confirmed_issue_count == 0


# A stale form, another accepted mutation or an old pending check cannot authorize or green repair.
def test_repair_stale_preview_and_pending_check(repair_case):
    c = repair_case
    stale = command(c)
    with c.engine.begin() as con:
        con.execute(
            update(tenancy)
            .where(tenancy.c.id == c.identifier)
            .values(revision=tenancy.c.revision + 1)
        )
    with pytest.raises(OrganizationConflict):
        c.repairs.start(c.principal, stale)
    check = c.checks.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=c.identifier)
    )
    c.check_worker.run(check.operation_id)
    pending = c.checks.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=c.identifier)
    )
    receipt = c.repairs.start(c.principal, command(c))
    c.repair_worker.run(receipt.operation_id)
    c.check_worker.run(pending.operation_id)
    summary = c.checks.detail(c.principal, c.identifier)
    assert summary.confirmed_issue_count == 1 and summary.state == "drifted"


# Source evidence expiration is an explicit recheck requirement rather than permission to mutate.
def test_repair_expired_check_cannot_preview(repair_case):
    c = repair_case
    c.clock.return_value += timedelta(days=2)
    from test_local_auth_postgres import command as sign_in_command

    issued = c.service.sign_in(sign_in_command(c))
    c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    with pytest.raises(OrganizationConflict):
        command(c)
