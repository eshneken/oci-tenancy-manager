"""Qualify atomic acceptance with real PostgreSQL and the native connection hook."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import procrastinate
import pytest
from conftest import boundary_ready, counts, operation_state, process, stop, wait_for
from otm_runner_qualification.harness import RequestConflict, stage_acceptance
from sqlalchemy import text


# Commit toy intent/audit/job together, returning only after SQLAlchemy's transaction exits.
def accept(lab, key=None, **options):
    with lab.engine.begin() as connection:
        return stage_acceptance(connection, lab.runner.task, key or str(uuid4()), **options)


# Matching row xmins and independent visibility prove the job does not commit separately.
def test_job_shares_backend_transaction_and_is_invisible_until_commit(lab):
    with lab.engine.begin() as connection:
        identifier, job = stage_acceptance(connection, lab.runner.task, str(uuid4()))
        assert counts(lab.engine) == (0, 0, 0, 0)
        row = connection.execute(
            text("""
          SELECT o.xmin::text, a.xmin::text, j.xmin::text, j.args
          FROM qualification.operation o JOIN qualification.audit a ON a.operation_id=o.id
          JOIN procrastinate_jobs j ON j.args->>'operation_id'=o.id WHERE o.id=:id
        """),
            {"id": identifier},
        ).one()
        assert row[0] == row[1] == row[2]
        assert row[3] == {"operation_id": identifier} and isinstance(job, int)
    assert counts(lab.engine) == (1, 1, 1, 0)


# A real native worker finds no job until the application's acceptance transaction commits.
def test_worker_cannot_dispatch_uncommitted_intent(lab, tmp_path):
    with lab.engine.begin() as connection:
        identifier, _ = stage_acceptance(connection, lab.runner.task, str(uuid4()))
        child = process(tmp_path)
        try:
            assert child.wait(timeout=10) == 0
            assert counts(lab.engine) == (0, 0, 0, 0)
        finally:
            stop(child)
    child = process(tmp_path)
    try:
        assert child.wait(timeout=10) == 0
        assert operation_state(lab.engine, identifier) == "done"
        assert counts(lab.engine) == (1, 1, 1, 1)
    finally:
        stop(child)


# Caller failure after a successful defer leaves neither accepted intent nor runnable work.
def test_exception_after_job_insert_rolls_back_all_records(lab):
    with pytest.raises(RuntimeError, match="abort acceptance"):
        with lab.engine.begin() as connection:
            stage_acceptance(connection, lab.runner.task, str(uuid4()))
            raise RuntimeError("abort acceptance")
    assert counts(lab.engine) == (0, 0, 0, 0)


# A real runner queue constraint failure cannot leave application records committed alone.
def test_job_insert_failure_rolls_back_operation_and_audit(lab):
    with lab.engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE procrastinate_jobs ADD CONSTRAINT qualification_reject_job "
                "CHECK (queue_name <> 'qualification')"
            )
        )
    try:
        with pytest.raises(procrastinate.exceptions.ConnectorException):
            accept(lab)
        assert counts(lab.engine) == (0, 0, 0, 0)
    finally:
        with lab.engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE procrastinate_jobs DROP CONSTRAINT qualification_reject_job")
            )


# Resubmitting a committed key recovers acceptance rather than creating another audit/job.
def test_lost_response_retry_returns_original_operation_without_second_job(lab):
    key = str(uuid4())
    original, job = accept(lab, key)
    recovered, new_job = accept(lab, key)
    assert original == recovered and job is not None and new_job is None
    assert counts(lab.engine) == (1, 1, 1, 0)
    with pytest.raises(RequestConflict):
        accept(lab, key, digest="different-intent")
    assert counts(lab.engine) == (1, 1, 1, 0)


# A real unique constraint arbitrates competing transactions, including conflicting reuse.
@pytest.mark.parametrize("different_intent", [False, True])
def test_concurrent_request_reuse_has_one_committed_winner(lab, different_intent):
    key, barrier = str(uuid4()), Barrier(2)

    # Race independent SQL connections with the same scoped request key.
    def submit(number):
        try:
            with lab.engine.begin() as connection:
                # Both physical connections/transactions must be open before either insert.
                connection.execute(text("SELECT pg_backend_pid()"))
                barrier.wait(timeout=5)
                return stage_acceptance(
                    connection,
                    lab.runner.task,
                    key,
                    digest=str(number) if different_intent else "same-intent",
                )
        except RequestConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, number) for number in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert counts(lab.engine) == (1, 1, 1, 0)
    if different_intent:
        assert results.count("conflict") == 1
    else:
        assert results[0][0] == results[1][0]
        assert sum(result[1] is not None for result in results) == 1


# A matching client key from another actor/workspace does not alias existing intent.
def test_actor_and_workspace_are_independent_request_key_scopes(lab):
    key = str(uuid4())
    references = [
        accept(lab, key)[0],
        accept(lab, key, actor="other-admin")[0],
        accept(lab, key, workspace="other-org")[0],
    ]
    assert len(set(references)) == 3 and counts(lab.engine) == (3, 3, 3, 0)


# An abrupt caller death leaves all-or-none records on either side of the actual commit.
@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
def test_process_kill_at_explicit_acceptance_boundary(lab, tmp_path, boundary):
    key = str(uuid4())
    child = process(tmp_path, boundary, request_key=key)
    try:
        boundary_ready(child)
        child.kill()
        assert child.wait(timeout=5) != 0
        expected = (0, 0, 0, 0) if boundary == "before_commit" else (1, 1, 1, 0)
        wait_for(lambda: counts(lab.engine) == expected)
        recovered, _ = accept(lab, key)
        assert recovered and counts(lab.engine) == (1, 1, 1, 0)
    finally:
        stop(child)


# A deferred database constraint can fail at COMMIT after all three inserts succeeded.
def test_database_rejecting_commit_rolls_back_intent_audit_and_job(lab):
    from sqlalchemy.exc import IntegrityError

    with lab.engine.begin() as connection:
        connection.execute(
            text("""
          CREATE FUNCTION qualification.reject_commit() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE check_violation USING MESSAGE='Controlled commit rejection'; END $$;
          CREATE CONSTRAINT TRIGGER qualification_commit_failure
          AFTER INSERT ON qualification.audit DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION qualification.reject_commit();
        """)
        )
    try:
        with pytest.raises(IntegrityError, match="Controlled commit rejection"):
            with lab.engine.begin() as connection:
                identifier, job = stage_acceptance(connection, lab.runner.task, str(uuid4()))
                assert identifier and job is not None
                assert counts(lab.engine) == (0, 0, 0, 0)
                # The constraint fires when this context attempts COMMIT, not at insert time.
        assert counts(lab.engine) == (0, 0, 0, 0)
    finally:
        with lab.engine.begin() as connection:
            connection.execute(
                text("""
              DROP TRIGGER qualification_commit_failure ON qualification.audit;
              DROP FUNCTION qualification.reject_commit();
            """)
            )


# A misconfigured engine cannot leave partial intent/audit before enqueue rejects its mode.
def test_autocommit_connection_is_rejected_before_any_application_write(lab):
    with lab.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with pytest.raises(RuntimeError, match="active SQLAlchemy psycopg transaction"):
            stage_acceptance(connection, lab.runner.task, str(uuid4()))
    assert counts(lab.engine) == (0, 0, 0, 0)
