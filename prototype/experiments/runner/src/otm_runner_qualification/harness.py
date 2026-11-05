"""Toy records and native runner hooks for disposable transaction qualification only.

These three tables are test fixtures, not production migrations or a competing OTM data model.
No application actor authorization, OCI effect or production exactly-once guarantee is implemented.
"""

import os
import time
from dataclasses import dataclass
from uuid import uuid4

import procrastinate
import psycopg
from psycopg.conninfo import make_conninfo
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url

QUEUE = "qualification"
TASK = "qualification.process"
metadata = MetaData(schema="qualification")
operations = Table(
    "operation",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace", String, nullable=False),
    Column("actor", String, nullable=False),
    Column("request_key", String, nullable=False),
    Column("digest", String, nullable=False),
    Column("state", String, nullable=False),
    Column("hold", Boolean, nullable=False),
    Column("hold_after_effect", Boolean, nullable=False),
    Column("failures_remaining", Integer, nullable=False),
    UniqueConstraint("workspace", "actor", "request_key"),
)
audit = Table(
    "audit",
    metadata,
    Column("id", String, primary_key=True),
    Column("operation_id", ForeignKey(operations.c.id), nullable=False, unique=True),
)
effects = Table(
    "effect", metadata, Column("operation_id", ForeignKey(operations.c.id), primary_key=True)
)


# Reject reuse of a scoped request key for different toy intent.
class RequestConflict(ValueError):
    pass


# Inject a known no-effect failure to qualify the runner's configured retry behavior.
class ControlledRetry(RuntimeError):
    pass


# Accept only a query-free loopback qualification database before any connection is opened.
def connection_config(raw_url=None):
    raw_url = raw_url or os.environ.get("OTM_RUNNER_TEST_DATABASE_URL")
    if not raw_url:
        raise ValueError("Run scripts/run_qualification.py; no database is configured")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.database != "otm_runner_test"
        or url.username != "otm_qual"
        or not url.port
        or not url.password
        or url.query
    ):
        raise ValueError("Only the disposable loopback runner database is allowed")
    options = {
        "hostaddr": "127.0.0.1",
        "connect_timeout": 5,
        "options": (
            "-c statement_timeout=10000 -c lock_timeout=5000 "
            "-c idle_in_transaction_session_timeout=20000"
        ),
    }
    conninfo = make_conninfo(
        host="127.0.0.1",
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.database,
        **options,
    )
    return url, options, conninfo


# Build a bounded SQLAlchemy pool without printing a connection URL or database parameters.
def engine_for_test():
    url, options, _ = connection_config()
    return create_engine(
        url, connect_args=options, pool_size=3, max_overflow=3, hide_parameters=True, echo=False
    )


# Keep the native app/task pair together for enqueue and worker qualification.
@dataclass
class Runner:
    app: procrastinate.App
    task: object


# Use native sync psycopg for acceptance and native async psycopg for worker execution.
def build_runner(engine, *, worker=False):
    _, _, conninfo = connection_config()
    connector = procrastinate.PsycopgConnector if worker else procrastinate.SyncPsycopgConnector
    app = procrastinate.App(connector=connector(conninfo=conninfo, min_size=1, max_size=4))

    # Apply only a local idempotent SQL effect; never stand in for an idempotent OCI write.
    @app.task(
        name=TASK,
        queue=QUEUE,
        retry=procrastinate.RetryStrategy(
            max_attempts=1, wait=0, retry_exceptions=(ControlledRetry,)
        ),
    )
    def process(operation_id):
        should_retry = False
        with engine.begin() as connection:
            row = (
                connection.execute(
                    select(operations).where(operations.c.id == operation_id).with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] == "done":
                return
            should_retry = row["failures_remaining"] > 0
            connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(state="running", failures_remaining=max(0, row["failures_remaining"] - 1))
            )
        if should_retry:
            raise ControlledRetry("Controlled no-effect retry")

        # A DB flag makes process-signal tests deterministic. No DB transaction is held while
        # waiting; test timeouts/cleanup own this artificial hold, not a production workflow.
        # Expose a deterministic test-only signal boundary without holding a transaction.
        def wait_for_release(column):
            deadline = time.monotonic() + 15
            while True:
                with engine.connect() as connection:
                    hold = connection.execute(
                        select(column).where(operations.c.id == operation_id)
                    ).scalar_one()
                if not hold:
                    return
                if time.monotonic() > deadline:
                    raise RuntimeError("Qualification hold was not released")
                time.sleep(0.03)

        wait_for_release(operations.c.hold)
        with engine.begin() as connection:
            row = (
                connection.execute(
                    select(operations).where(operations.c.id == operation_id).with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] != "done":
                connection.execute(effects.insert().values(operation_id=operation_id))
                connection.execute(
                    update(operations).where(operations.c.id == operation_id).values(state="done")
                )

        wait_for_release(operations.c.hold_after_effect)

    return Runner(app, process)


# Insert toy intent/audit/job in the caller's transaction, returning only stable references.
#
# This verifies a supported native connection hook. It does not commit, open a second dispatch
# connection, call a runner stored function directly, or implement production acceptance guards.
def stage_acceptance(
    connection,
    task,
    request_key,
    digest="same-intent",
    *,
    workspace="synthetic-org",
    actor="synthetic-admin",
    hold=False,
    failures_remaining=0,
    hold_after_effect=False,
):
    # Reject unsupported autocommit before the first application insert, not after it.
    raw = connection.connection.driver_connection
    if not isinstance(raw, psycopg.Connection) or raw.autocommit:
        raise RuntimeError("Expected the active SQLAlchemy psycopg transaction")
    identifier = str(uuid4())
    inserted = connection.execute(
        insert(operations)
        .values(
            id=identifier,
            workspace=workspace,
            actor=actor,
            request_key=request_key,
            digest=digest,
            state="queued",
            hold=hold,
            hold_after_effect=hold_after_effect,
            failures_remaining=failures_remaining,
        )
        .on_conflict_do_nothing(
            index_elements=[operations.c.workspace, operations.c.actor, operations.c.request_key]
        )
        .returning(operations.c.id)
    ).scalar_one_or_none()
    if not inserted:
        existing = (
            connection.execute(
                select(operations).where(
                    operations.c.workspace == workspace,
                    operations.c.actor == actor,
                    operations.c.request_key == request_key,
                )
            )
            .mappings()
            .one()
        )
        if existing["digest"] != digest:
            raise RequestConflict("Request key was reused for different intent")
        return existing["id"], None
    connection.execute(audit.insert().values(id=str(uuid4()), operation_id=identifier))
    job = task.configure(connection=raw, lock="operation:" + identifier).defer(
        operation_id=identifier
    )
    return identifier, job


# Create runner-owned schema and three toy tables only inside the guarded disposable DB.
def initialize(engine, runner):
    runner.app.schema_manager.apply_schema()
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA qualification"))
        metadata.create_all(connection)
