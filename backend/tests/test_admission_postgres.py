"""Real migration, scope, append-only history and atomic native-enqueue integration tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import procrastinate
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from database_helpers import migrate
from sqlalchemy import MetaData, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.schema import BLANK_SCHEMA
from test_admission_service import NOW, admission

from otm.operations.acceptance import AcceptInspection
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict, SqlAdmissionStore
from otm.storage.enqueue import InspectionEnqueuer
from otm.storage.tables import audit_event, metadata, operation

pytestmark = pytest.mark.postgres
__all__ = ["admission"]


# Give each case a new workspace instead of disabling audit protections to truncate history.
@pytest.fixture
def pg_case(pg_engine, admission):
    workspace = "org-" + uuid4().hex
    request = admission.request.model_copy(update={"workspace_id": workspace})
    policy = admission.policy.model_copy(update={"workspace_id": workspace})
    admission.resolve.return_value = policy
    enqueuer = InspectionEnqueuer()
    store = SqlAdmissionStore(pg_engine, enqueuer)
    service = AcceptInspection(store, admission.auth, admission.resolve, admission.clock)
    return SimpleNamespace(
        engine=pg_engine,
        store=store,
        service=service,
        enqueuer=enqueuer,
        request=request,
        actor=admission.actor,
        policy=policy,
        auth=admission.auth,
        resolve=admission.resolve,
        principal=admission.principal,
    )


# Read committed workspace rows and matching native jobs independently.
def records(case):
    with case.engine.connect() as connection:
        ops = (
            connection.execute(
                select(operation).where(operation.c.workspace_id == case.request.workspace_id)
            )
            .mappings()
            .all()
        )
        events = (
            connection.execute(
                select(audit_event).where(audit_event.c.workspace_id == case.request.workspace_id)
            )
            .mappings()
            .all()
        )
        jobs = (
            connection.execute(
                text("""
          SELECT id,args,status::text FROM public.procrastinate_jobs
          WHERE queue_name='otm.operations' AND args->>'operation_id' IN
            (SELECT id::text FROM public.otm_operation WHERE workspace_id=:workspace)
        """),
                {"workspace": case.request.workspace_id},
            )
            .mappings()
            .all()
        )
        return ops, events, jobs


# Call the internal service with explicit test authorization.
def accepted(case, request=None):
    return case.service.accept(request or case.request, case.principal)


# Compare a test-only default-schema copy without filtering real constraint differences.
def schema_differences(engine):
    comparison = MetaData()

    # Normalize public references to PostgreSQL's default spelling in the copied metadata.
    def referred_schema(table, schema, constraint, referred):
        return BLANK_SCHEMA if referred == "public" else None

    for table in metadata.tables.values():
        table.to_metadata(comparison, schema=None, referred_schema_fn=referred_schema)

    # Leave all column/constraint comparisons active; only exclude non-application tables.
    def application_only(object_, name, kind, reflected, compare_to):
        return kind != "table" or name in {table.name for table in metadata.tables.values()}

    with engine.connect() as connection:
        assert connection.dialect.default_schema_name == "public"
        context = MigrationContext.configure(
            connection,
            opts={
                "include_schemas": True,
                "include_object": application_only,
            },
        )
        return compare_metadata(context, comparison)


# Apply the empty baseline and compare app tables to current metadata.
def test_empty_migration_and_current_metadata_agree(pg_engine):
    assert {"otm_operation", "audit_event", "procrastinate_jobs"} <= set(
        inspect(pg_engine).get_table_names()
    )
    assert schema_differences(pg_engine) == []
    migrate(pg_engine)


# Normalizing default-schema spelling must not conceal a changed deferred constraint.
def test_schema_comparison_detects_real_foreign_key_enforcement_changes(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE public.audit_event ALTER CONSTRAINT fk_audit_operation "
                "INITIALLY IMMEDIATE"
            )
        )
    try:
        assert schema_differences(pg_engine)
    finally:
        with pg_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE public.audit_event ALTER CONSTRAINT fk_audit_operation "
                    "INITIALLY DEFERRED"
                )
            )


# Freeze trusted fields and return queued only after the shared commit.
def test_acceptance_commits_exact_intent_and_reference_only_native_job(pg_case):
    result = accepted(pg_case)
    ops, events, jobs = records(pg_case)
    assert len(ops) == len(events) == len(jobs) == 1
    op, event, job = ops[0], events[0], jobs[0]
    assert op["id"] == result.operation_id == event["operation_id"]
    assert op["current_intent_event_id"] == event["id"]
    assert op["state"] == result.state == "queued" and op["completed_at"] is None
    assert op["initiating_actor_subject"] == pg_case.actor.key == event["actor_subject"]
    assert event["data_hash"] == canonical_hash(event["data"])
    import json

    frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
    assert frozen.intent.access_binding_id == pg_case.policy.access_binding_id
    assert frozen.intent.target.tenancy_ocid == pg_case.request.tenancy_ocid
    assert frozen.actor == pg_case.actor
    assert job["args"] == {"operation_id": str(result.operation_id)}
    with pg_case.engine.connect() as connection:
        xmins = connection.execute(
            text("""
          SELECT o.xmin::text,a.xmin::text,j.xmin::text FROM public.otm_operation o
          JOIN public.audit_event a ON a.id=o.current_intent_event_id
          JOIN public.procrastinate_jobs j ON j.args->>'operation_id'=o.id::text WHERE o.id=:id
        """),
            {"id": result.operation_id},
        ).one()
        assert len(set(xmins)) == 1


# A lost-response replay survives changed policy/display metadata without another dispatch.
def test_authorized_replay_keeps_frozen_policy_actor_snapshot_and_one_job(pg_case):
    original = accepted(pg_case)
    pg_case.auth.require_admin.return_value = pg_case.actor.model_copy(
        update={"display_name": "Changed Name"}
    )
    pg_case.resolve.side_effect = RuntimeError("current policy unavailable")
    assert accepted(pg_case) == original
    ops, events, jobs = records(pg_case)
    assert len(ops) == len(events) == len(jobs) == 1
    assert ops[0]["initiating_actor_snapshot"]["display_name"] == pg_case.actor.display_name


# Deny command replay before lookup after entitlement loss.
def test_unauthorized_replay_is_denied_before_database_lookup(pg_case):
    accepted(pg_case)
    pg_case.auth.require_admin.side_effect = PermissionError("NOT_AUTHORIZED")
    with patch.object(pg_case.store, "find", wraps=pg_case.store.find) as lookup:
        with pytest.raises(PermissionError):
            accepted(pg_case)
        lookup.assert_not_called()
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)


# Different target input cannot reuse a committed key or append another audit/job.
def test_conflicting_key_does_not_mutate_original_intent(pg_case):
    original = accepted(pg_case)
    other = pg_case.request.model_copy(update={"tenancy_ocid": "ocid1.tenancy.oc1..othertarget"})
    with pytest.raises(RequestConflict):
        accepted(pg_case, other)
    assert records(pg_case)[0][0]["id"] == original.operation_id
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)


# Matching client keys do not disclose or alias another authenticated actor's operation.
@pytest.mark.parametrize("field", ["issuer", "subject"])
def test_actor_issuer_and_subject_both_scope_request_ownership(pg_case, field):
    first = accepted(pg_case)
    value = "https://other.example.test" if field == "issuer" else "other-admin"
    pg_case.auth.require_admin.return_value = pg_case.actor.model_copy(update={field: value})
    second = accepted(pg_case)
    assert first.operation_id != second.operation_id
    assert tuple(map(len, records(pg_case))) == (2, 2, 2)


# Separate matching keys across permitted workspaces.
def test_workspace_is_bound_in_database_lookup_and_uniqueness(pg_case):
    first = accepted(pg_case)
    workspace = "other-' OR '1'='1-" + uuid4().hex
    request = pg_case.request.model_copy(update={"workspace_id": workspace})
    pg_case.resolve.return_value = pg_case.policy.model_copy(update={"workspace_id": workspace})
    second = accepted(pg_case, request)
    assert first.operation_id != second.operation_id
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)


# An exception after actual native deferral cannot leave a queued job or orphaned audit.
def test_native_enqueue_then_failure_rolls_back_application_and_queue_rows(pg_case):

    # Inject a known local error after the real queue insertion.
    class FailAfterEnqueue:
        # Use the same native connection before failing the caller transaction.
        def enqueue(self, connection, operation_id):
            pg_case.enqueuer.enqueue(connection, operation_id)
            raise RuntimeError("Controlled post-enqueue failure")

    pg_case.service.store = SqlAdmissionStore(pg_case.engine, FailAfterEnqueue())
    with pytest.raises(RuntimeError, match="post-enqueue"):
        accepted(pg_case)
    assert tuple(map(len, records(pg_case))) == (0, 0, 0)


# A native queue constraint rejection cannot commit application rows independently.
def test_actual_native_job_insert_failure_rolls_back_intent_and_audit(pg_case):
    with pg_case.engine.begin() as connection:
        connection.execute(
            text("""
          ALTER TABLE public.procrastinate_jobs ADD CONSTRAINT otm_test_enqueue_failure
          CHECK(queue_name<>'otm.operations') NOT VALID
        """)
        )
    try:
        with pytest.raises(procrastinate.exceptions.ConnectorException):
            accepted(pg_case)
        assert tuple(map(len, records(pg_case))) == (0, 0, 0)
    finally:
        with pg_case.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE public.procrastinate_jobs DROP CONSTRAINT otm_test_enqueue_failure"
                )
            )


# Even the test database owner cannot use ordinary DML/TRUNCATE while protection is active.
@pytest.mark.parametrize("mutation", ["update", "delete", "truncate"])
def test_audit_rows_reject_rewrite_deletion_and_truncation(pg_case, mutation):
    accepted(pg_case)
    statements = {
        "update": "UPDATE public.audit_event SET actor='changed' WHERE workspace_id=:workspace",
        "delete": "DELETE FROM public.audit_event WHERE workspace_id=:workspace",
        "truncate": "TRUNCATE public.audit_event,public.otm_operation CASCADE",
    }
    with pytest.raises(ProgrammingError, match="append-only"):
        with pg_case.engine.begin() as connection:
            connection.execute(
                text(statements[mutation]), {"workspace": pg_case.request.workspace_id}
            )
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)


# Deferred composite foreign keys reject cross-operation, revision and workspace pointers.
@pytest.mark.parametrize("field", ["event", "revision", "workspace"])
def test_current_intent_pointer_must_match_exact_operation_workspace_revision(pg_case, field):
    first = accepted(pg_case)
    second = accepted(pg_case, pg_case.request.model_copy(update={"client_request_key": uuid4()}))
    ops = {row["id"]: row for row in records(pg_case)[0]}
    changes = (
        {"current_intent_event_id": ops[second.operation_id]["current_intent_event_id"]}
        if field == "event"
        else {"current_intent_revision": 2}
        if field == "revision"
        else {"workspace_id": "other-org"}
    )
    with pytest.raises(IntegrityError):
        with pg_case.engine.begin() as connection:
            connection.execute(
                update(operation).where(operation.c.id == first.operation_id).values(**changes)
            )
    assert tuple(map(len, records(pg_case))) == (2, 2, 2)


# Race real READ COMMITTED transactions over one scoped request key.
@pytest.mark.parametrize("conflicting", [False, True])
def test_concurrent_admission_preserves_one_intent_and_native_job(pg_case, conflicting):
    barrier = Barrier(2)
    store = pg_case.store
    # Resolve a closed intent once, then race the atomic adapter. This avoids sharing mock
    # authorizer state between threads; service authorization is independently covered above.
    from otm.operations.contracts import InspectionIntent
    from otm.providers.inspection_contracts import InspectionTarget

    intent = InspectionIntent(
        contract_version="inspect-import-1",
        kind="inspect_import",
        workspace_id=pg_case.request.workspace_id,
        policy_revision=pg_case.policy.policy_revision,
        access_binding_id=pg_case.policy.access_binding_id,
        target=InspectionTarget(
            organization_id=pg_case.policy.organization_id,
            parent_tenancy_ocid=pg_case.policy.parent_tenancy_ocid,
            tenancy_ocid=pg_case.request.tenancy_ocid,
        ),
    )
    from sqlalchemy import event

    # Hold both checked-out physical transactions before either application insert.
    def release_transactions(connection):
        barrier.wait(timeout=5)

    # Race the same actor/key with either matching or conflicting target input.
    def submit(number):
        request = pg_case.request
        current = intent
        if conflicting and number:
            request = request.model_copy(update={"tenancy_ocid": "ocid1.tenancy.oc1..other"})
            current = intent.model_copy(
                update={
                    "target": intent.target.model_copy(
                        update={"tenancy_ocid": request.tenancy_ocid}
                    )
                }
            )
        try:
            return store.insert(request, pg_case.actor, current, NOW)
        except RequestConflict:
            return None

    event.listen(pg_case.engine, "begin", release_transactions)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
    finally:
        event.remove(pg_case.engine, "begin", release_transactions)
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)
    assert (sum(result is None for result in results)) == int(conflicting)
    if not conflicting:
        assert results[0].operation_id == results[1].operation_id


# A downgrade cannot silently drop accepted operations and administrative history.
def test_production_baseline_rejects_destructive_downgrade(pg_case):
    accepted(pg_case)
    with pytest.raises(RuntimeError, match="forward-only"):
        migrate(pg_case.engine, "base", downgrade=True)
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)


# Reject unsupported actual psycopg transaction modes before any INSERT is submitted.
@pytest.mark.parametrize("mode", ["AUTOCOMMIT", "REPEATABLE READ", "SERIALIZABLE"])
def test_unsupported_real_connection_modes_fail_before_application_insert(pg_case, mode):
    from sqlalchemy import event

    statements = []

    # Retain SQL structure only, never connection parameters or credentials.
    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = pg_case.engine.execution_options(isolation_level=mode)
    event.listen(engine, "before_cursor_execute", record_statement)
    pg_case.service.store = SqlAdmissionStore(engine, pg_case.enqueuer)
    try:
        with pytest.raises(RuntimeError, match="ACTIVE_READ_COMMITTED"):
            accepted(pg_case)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
    assert not any(statement.lstrip().upper().startswith("INSERT") for statement in statements)
    assert tuple(map(len, records(pg_case))) == (0, 0, 0)


# Exercise a real COMMIT-time failure after native queue insertion, not a mocked exit.
def test_real_deferred_commit_rejection_never_returns_acceptance_or_leaves_rows(pg_case):
    with pg_case.engine.begin() as connection:
        connection.execute(
            text("""
          CREATE FUNCTION public.otm_test_reject_commit() RETURNS trigger
          LANGUAGE plpgsql AS $$ BEGIN
            IF current_setting('otm.test_fail_commit',true) = 'yes' THEN
              RAISE EXCEPTION 'controlled deferred commit rejection' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
          END $$
        """)
        )
        connection.execute(
            text("""
          CREATE CONSTRAINT TRIGGER otm_test_deferred_rejection
          AFTER INSERT ON public.audit_event DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION public.otm_test_reject_commit()
        """)
        )

    # Arm a transaction-local deferred rejection only after the real native enqueue.
    class FailAtCommit:
        # Confirm all three writes precede the failure observed at transaction exit.
        def enqueue(self, connection, operation_id):
            pg_case.enqueuer.enqueue(connection, operation_id)
            connection.execute(text("SET LOCAL otm.test_fail_commit = 'yes'"))

    pg_case.service.store = SqlAdmissionStore(pg_case.engine, FailAtCommit())
    try:
        with pytest.raises(IntegrityError, match="controlled deferred commit rejection"):
            accepted(pg_case)
        assert tuple(map(len, records(pg_case))) == (0, 0, 0)
    finally:
        with pg_case.engine.begin() as connection:
            connection.execute(
                text("DROP TRIGGER otm_test_deferred_rejection ON public.audit_event")
            )
            connection.execute(text("DROP FUNCTION public.otm_test_reject_commit()"))


# A prior session temp table must not shadow the native migration-owned queue relation.
def test_native_enqueue_does_not_use_pooled_temporary_relation_shadow(pg_case):

    # Place a same-named temporary relation ahead of public before calling the adapter.
    class ShadowedSession:
        # Require safe lookup order and an untouched temporary decoy after native enqueue.
        def enqueue(self, connection, operation_id):
            connection.execute(
                text(
                    "CREATE TEMP TABLE procrastinate_jobs "
                    "(LIKE public.procrastinate_jobs) ON COMMIT DROP"
                )
            )
            connection.execute(text("SET LOCAL search_path = pg_temp, public, pg_catalog"))
            pg_case.enqueuer.enqueue(connection, operation_id)
            assert connection.execute(text("SHOW search_path")).scalar_one() == (
                "pg_catalog, public, pg_temp"
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_temp.procrastinate_jobs")
                ).scalar_one()
                == 0
            )

    pg_case.service.store = SqlAdmissionStore(pg_case.engine, ShadowedSession())
    accepted(pg_case)
    assert tuple(map(len, records(pg_case))) == (1, 1, 1)
