"""Owned native-worker process tests; SQL toy effects never imply exactly-once OCI behavior."""

import asyncio
import signal
import time
from datetime import UTC, datetime

from conftest import counts, operation_state, process, stop, wait_for
from otm_runner_qualification.harness import QUEUE, TASK, build_runner
from sqlalchemy import text
from test_transactions import accept


# Observe one native job's committed status and execution-attempt count.
def job_status(engine, identifier):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT status::text, attempts FROM procrastinate_jobs WHERE id=:id"),
            {"id": identifier},
        ).one()


# Release only the selected toy worker hold; both statement forms have fixed identifiers.
def release(engine, identifier, *, after_effect=False):
    query = (
        "UPDATE qualification.operation SET hold_after_effect=false WHERE id=:id"
        if after_effect
        else "UPDATE qualification.operation SET hold=false WHERE id=:id"
    )
    with engine.begin() as connection:
        connection.execute(text(query), {"id": identifier})


# A controlled transient error uses the configured native retry rather than losing the job.
def test_configured_known_no_effect_retry_runs_again_and_finishes(lab, tmp_path):
    identifier, job = accept(lab, failures_remaining=1)
    child = process(tmp_path, persistent=True)
    try:
        wait_for(lambda: job_status(lab.engine, job) == ("succeeded", 2))
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=10) == 0
        assert job_status(lab.engine, job) == ("succeeded", 2)
        assert operation_state(lab.engine, identifier) == "done"
        assert counts(lab.engine) == (1, 1, 1, 1)
    finally:
        stop(child)


# Two native workers cannot concurrently claim jobs with the same operation lock.
def test_duplicate_delivery_is_locked_and_local_sql_effect_remains_idempotent(lab, tmp_path):
    identifier, first_job = accept(lab, hold=True)
    with lab.engine.begin() as connection:
        raw = connection.connection.driver_connection
        second_job = lab.runner.task.configure(
            connection=raw, lock="operation:" + identifier
        ).defer(operation_id=identifier)
    first = process(tmp_path, persistent=True)
    second = None
    try:
        wait_for(lambda: operation_state(lab.engine, identifier) == "running")
        assert job_status(lab.engine, first_job)[0] == "doing"
        assert job_status(lab.engine, second_job)[0] == "todo"
        second = process(tmp_path)
        assert second.wait(timeout=10) == 0
        assert job_status(lab.engine, second_job)[0] == "todo"
        assert counts(lab.engine) == (1, 1, 2, 0)
        release(lab.engine, identifier)
        wait_for(lambda: job_status(lab.engine, second_job)[0] == "succeeded")
        first.send_signal(signal.SIGTERM)
        assert first.wait(timeout=10) == 0
        assert job_status(lab.engine, first_job)[0] == "succeeded"
        assert job_status(lab.engine, second_job)[0] == "succeeded"
        assert counts(lab.engine) == (1, 1, 2, 1)
    finally:
        stop(first)
        if second:
            stop(second)


# SIGTERM does not abandon an already running task that completes within its grace window.
def test_graceful_termination_waits_for_current_job_and_publishes_completion(lab, tmp_path):
    identifier, job = accept(lab, hold=True)
    child = process(tmp_path, persistent=True)
    try:
        wait_for(lambda: operation_state(lab.engine, identifier) == "running")
        child.send_signal(signal.SIGTERM)
        time.sleep(0.15)
        assert child.poll() is None and counts(lab.engine) == (1, 1, 1, 0)
        release(lab.engine, identifier)
        assert child.wait(timeout=10) == 0
        assert job_status(lab.engine, job)[0] == "succeeded"
        assert counts(lab.engine) == (1, 1, 1, 1)
    finally:
        stop(child)


# Use the supported heartbeat-aware query for this exact queue/task, not guessed job age.
async def stalled_jobs(engine):
    runner = build_runner(engine, worker=True)
    async with runner.app.open_async():
        return list(
            await runner.app.job_manager.get_stalled_jobs(
                queue=QUEUE,
                task_name=TASK,
                seconds_since_heartbeat=0.3,
            )
        )


# Worker restart alone does not recover doing jobs; explicit stalled recovery is required.
def test_killed_worker_stays_stalled_until_explicit_safe_retry(lab, tmp_path):
    identifier, job = accept(lab, hold=True)
    child = process(tmp_path, persistent=True)
    replacement = None
    restarted = None
    try:
        wait_for(lambda: operation_state(lab.engine, identifier) == "running")
        child.kill()
        child.wait(timeout=5)
        release(lab.engine, identifier)
        wait_for(lambda: any(item.id == job for item in asyncio.run(stalled_jobs(lab.engine))))
        replacement = process(tmp_path)
        assert replacement.wait(timeout=10) == 0
        assert job_status(lab.engine, job)[0] == "doing"
        assert counts(lab.engine) == (1, 1, 1, 0)
        # This toy job has no external effects. Production recovery must first reconcile its
        # operation-specific uncertain OCI outcome; this is not permission to retry all jobs.
        lab.runner.app.job_manager.retry_job_by_id(job, retry_at=datetime.now(UTC))
        restarted = process(tmp_path, persistent=True)
        wait_for(lambda: job_status(lab.engine, job) == ("succeeded", 2))
        restarted.send_signal(signal.SIGTERM)
        assert restarted.wait(timeout=10) == 0
        assert job_status(lab.engine, job) == ("succeeded", 2)
        assert counts(lab.engine) == (1, 1, 1, 1)
    finally:
        for value in (child, replacement, restarted):
            if value:
                stop(value)


# A retried local completed intent is a no-op; this does not establish OCI effect atomicity.
def test_crash_after_local_effect_commit_before_runner_ack_does_not_repeat_effect(lab, tmp_path):
    identifier, job = accept(lab, hold_after_effect=True)
    child = process(tmp_path, persistent=True)
    restarted = None
    try:
        wait_for(lambda: counts(lab.engine) == (1, 1, 1, 1))
        assert operation_state(lab.engine, identifier) == "done"
        assert job_status(lab.engine, job)[0] == "doing"
        child.kill()
        child.wait(timeout=5)
        wait_for(lambda: any(item.id == job for item in asyncio.run(stalled_jobs(lab.engine))))
        lab.runner.app.job_manager.retry_job_by_id(job, retry_at=datetime.now(UTC))
        restarted = process(tmp_path, persistent=True)
        wait_for(lambda: job_status(lab.engine, job) == ("succeeded", 2))
        restarted.send_signal(signal.SIGTERM)
        assert restarted.wait(timeout=10) == 0
        assert job_status(lab.engine, job) == ("succeeded", 2)
        assert counts(lab.engine) == (1, 1, 1, 1)
    finally:
        stop(child)
        if restarted:
            stop(restarted)
