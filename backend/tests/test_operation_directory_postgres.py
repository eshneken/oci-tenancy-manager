"""Real scoped operation projections across acceptance, worker publication and read snapshots."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_admission_postgres import accepted, admission, pg_case
from test_execution_postgres import worker_case

from otm.operations.contracts import InspectImportRequest
from otm.operations.views import OperationQuery
from otm.storage.operation_directory import SqlOperationDirectory

pytestmark = pytest.mark.postgres
__all__ = ["admission", "pg_case", "worker_case"]


# Read real accepted/verified state, keeping successful simulated inspection distinct from import.
def test_read_accepted_then_worker_outcome(worker_case):
    c = worker_case
    reads = SqlOperationDirectory(c.case.engine)
    workspace, identifier = c.case.request.workspace_id, c.receipt.operation_id
    queued = reads.detail(workspace, identifier)
    assert queued.operation.state == "queued" and queued.steps == []
    assert queued.operation.provider_mode == "simulated"
    assert queued.events[0].kind == "operation_intent"
    assert reads.detail("foreign", identifier) is None
    assert reads.detail(workspace, uuid4()) is None
    c.worker.run(identifier)
    completed = reads.detail(workspace, identifier)
    assert completed.operation.state == "succeeded"
    assert completed.steps[0].safe_code == "TENANCY_INSPECTED"
    assert completed.steps[0].verified_at is not None
    assert len(completed.events) == 3
    assert "access_binding_id" not in completed.model_dump_json()
    assert "raw" not in completed.model_dump_json()
    assert reads.directory(workspace, OperationQuery(state="succeeded")).total == 1
    assert reads.directory(workspace, OperationQuery(state="queued")).total == 0


# Literal target/ID searches, filters, stable sorts and page clamping use only the authorized scope.
def test_real_directory_query_controls(pg_case):
    reads = SqlOperationDirectory(pg_case.engine)
    workspace = pg_case.request.workspace_id
    assert reads.directory(workspace, OperationQuery()).items == []
    identifiers = []
    for index in range(12):
        request = InspectImportRequest(
            workspace_id=workspace,
            client_request_key=uuid4(),
            tenancy_ocid=f"ocid1.tenancy.oc1..sandbox{index:02}",
        )
        identifiers.append(accepted(pg_case, request).operation_id)
    second = reads.directory(workspace, OperationQuery(page=2, sort="state", direction="asc"))
    assert second.total == 12 and second.pages == 2 and len(second.items) == 2
    assert reads.directory(workspace, OperationQuery(page=100)).page == 2
    assert reads.directory(workspace, OperationQuery(query="sandbox01")).total == 1
    assert (
        reads.directory(workspace, OperationQuery(query=str(identifiers[0]))).items[0].id
        == identifiers[0]
    )
    assert reads.directory(workspace, OperationQuery(query="%_")).total == 0
    assert reads.directory(workspace, OperationQuery(query="' OR 1=1 --")).total == 0
    assert reads.directory(workspace, OperationQuery(kind="inspect_import")).total == 12
    assert reads.directory(workspace, OperationQuery(kind="signing_key")).total == 0
    assert (
        reads.directory(workspace, OperationQuery(kind="inspect_import", query="sandbox01")).total
        == 1
    )
    assert (
        reads.directory(workspace, OperationQuery(kind="inspect_import", state="succeeded")).total
        == 0
    )
    assert reads.directory("foreign", OperationQuery(kind="inspect_import")).total == 0
    assert reads.directory("foreign", OperationQuery()).total == 0


# Snapshot reads cannot write, and subsequent transactions observe committed worker changes.
def test_projection_transaction_is_repeatable_and_read_only(pg_case):
    reads = SqlOperationDirectory(pg_case.engine)
    with reads.snapshot() as connection:
        assert connection.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert connection.scalar(text("SHOW transaction_read_only")) == "on"
        with pytest.raises(DBAPIError):
            connection.execute(text("CREATE TABLE forbidden_read_side(id int)"))


# A worker commit between projection queries cannot leak a newer step/history into an older state.
def test_concurrent_worker_commit_preserves_snapshot(worker_case):
    from sqlalchemy import func, select

    from otm.storage.tables import audit_event, operation, operation_step

    c = worker_case
    reads = SqlOperationDirectory(c.case.engine)
    workspace, identifier = c.case.request.workspace_id, c.receipt.operation_id
    with reads.snapshot() as connection:
        statement = reads.selection().where(
            operation.c.workspace_id == workspace, operation.c.id == identifier
        )
        before = connection.execute(statement).mappings().one()
        assert before["state"] == "queued"
        c.worker.run(identifier)
        assert connection.execute(statement).mappings().one()["state"] == "queued"
        assert (
            connection.scalar(
                select(func.count())
                .select_from(operation_step)
                .where(
                    operation_step.c.workspace_id == workspace,
                    operation_step.c.operation_id == identifier,
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.workspace_id == workspace,
                    audit_event.c.operation_id == identifier,
                )
            )
            == 1
        )
    after = reads.detail(workspace, identifier)
    assert after.operation.state == "succeeded" and len(after.steps) == 1 and len(after.events) == 3


# Read-only diagnostic inspections never badge, including waiting/attention states; history remains.
def test_readonly_inspections_do_not_badge(pg_case):
    from sqlalchemy import update

    from otm.storage.tables import operation

    workspace = pg_case.request.workspace_id
    identifiers = [
        accepted(
            pg_case,
            InspectImportRequest(
                workspace_id=workspace,
                client_request_key=uuid4(),
                tenancy_ocid=f"ocid1.tenancy.oc1..attention{i}",
            ),
        ).operation_id
        for i in range(4)
    ]
    with pg_case.engine.begin() as connection:
        for identifier, state in zip(
            identifiers, ("waiting", "needs_attention", "running", "queued"), strict=True
        ):
            connection.execute(
                update(operation)
                .where(operation.c.workspace_id == workspace, operation.c.id == identifier)
                .values(state=state)
            )
    reads = SqlOperationDirectory(pg_case.engine)
    assert reads.directory(workspace, OperationQuery()).attention_count == 0
    assert reads.directory(workspace, OperationQuery(state="needs_attention")).total == 1
    listing = reads.directory(
        workspace, OperationQuery(state="succeeded", query="not-found", page=20)
    )
    assert listing.total == 0 and listing.attention_count == 0
    assert reads.directory("foreign", OperationQuery()).attention_count == 0
    with pg_case.engine.begin() as connection:
        connection.execute(
            update(operation)
            .where(operation.c.workspace_id == workspace, operation.c.id.in_(identifiers[:2]))
            .values(state="succeeded")
        )
    assert reads.directory(workspace, OperationQuery()).attention_count == 0
