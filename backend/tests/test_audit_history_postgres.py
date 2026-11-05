"""Existing immutable event formats and real scoped history reads across administrators/workers."""

import pytest
from sqlalchemy import update
from test_admission_postgres import admission, pg_case
from test_execution_postgres import worker_case
from test_local_auth import factors
from test_local_auth_postgres import command, login_case

from otm.audit.contracts import AuditQuery
from otm.auth.local import LocalAuthFailure
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.tables import administrator

pytestmark = pytest.mark.postgres
__all__ = ["admission", "pg_case", "worker_case", "factors", "login_case"]


# Read actual acceptance/worker rows while preserving their distinct immutable actors.
def test_real_completed_operation_history(worker_case):
    c = worker_case
    c.worker.run(c.receipt.operation_id)
    reads = SqlAuditDirectory(c.case.engine)
    result = reads.directory(c.case.request.workspace_id, AuditQuery(category="operations"))
    assert result.total == 3
    assert sum(row.actor_name == "Inspection worker" for row in result.items) == 2
    assert (
        next(row for row in result.items if row.kind == "operation_intent").actor_name
        == c.committed.actor.display_name
    )
    assert {row.safe_code for row in result.items} == {None, "TENANCY_INSPECTED"}
    assert all(row.operation_id == c.receipt.operation_id for row in result.items)
    assert reads.directory("foreign", AuditQuery()).total == 0
    assert (
        reads.directory(
            c.case.request.workspace_id, AuditQuery(query=str(c.receipt.operation_id))
        ).total
        == 3
    )
    assert (
        reads.directory(c.case.request.workspace_id, AuditQuery(query="Inspection worker")).total
        == 2
    )
    assert reads.directory(c.case.request.workspace_id, AuditQuery(query="%_")).total == 0
    assert reads.directory(c.case.request.workspace_id, AuditQuery(query="' OR 1=1 --")).total == 0
    page = reads.directory(
        c.case.request.workspace_id, AuditQuery(page=999, sort="kind", direction="asc")
    )
    assert page.page == 1 and page.total == 3


# Preserve unverified sign-in attribution and distinguish operator evidence from named people.
def test_real_security_history_actor_categories(login_case):
    c = login_case
    issued = c.service.sign_in(command(c))
    with pytest.raises(LocalAuthFailure):
        c.service.sign_in(command(c))
    c.sessions.logout(issued.handle.get_secret_value())
    reads = SqlAuditDirectory(c.engine)
    result = reads.directory(c.policy.workspace_id, AuditQuery(sort="actor_name", direction="asc"))
    assert result.total == 4
    bootstrap = next(row for row in result.items if row.kind == "administrator_bootstrapped")
    assert bootstrap.actor_name == "Database operator" and bootstrap.category == "administration"
    failure = next(row for row in result.items if row.kind == "local_sign_in_failed")
    assert failure.actor_name is None and failure.category == "authentication"
    assert result.items[-1].actor_name is None
    assert reads.directory(c.policy.workspace_id, AuditQuery(category="authentication")).total == 3
    assert (
        reads.directory(
            c.policy.workspace_id, AuditQuery(category="administration", query="Database operator")
        ).total
        == 1
    )
    assert reads.directory(c.policy.workspace_id, AuditQuery(query=str(c.identifier))).total == 4
    assert c.seed not in result.model_dump_json()
    assert c.reference not in result.model_dump_json()


# Names are current workspace-scoped labels, searchable even after a display-name change.
def test_target_administrator_names(login_case):
    c = login_case
    reads = SqlAuditDirectory(c.engine)
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == c.identifier)
            .values(display_name="Renamed target")
        )
    result = reads.directory(c.policy.workspace_id, AuditQuery(query="Renamed target"))
    assert result.total == 1
    assert result.items[0].administrator_id == c.identifier
    assert result.items[0].administrator_name == "Renamed target"
    assert reads.directory("foreign", AuditQuery(query="Renamed target")).total == 0
