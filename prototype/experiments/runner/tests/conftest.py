"""Guarded real-database fixtures and owned worker processes for runner qualification."""

import os
import select as io_select
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from otm_runner_qualification.harness import build_runner, engine_for_test, initialize
from sqlalchemy import text


# Initialize only a guarded disposable database; missing configuration fails, never skips.
@pytest.fixture(scope="session")
def database():
    engine = engine_for_test()
    runner = build_runner(engine)
    runner.app.open()
    try:
        initialize(engine, runner)
        yield engine, runner
    finally:
        runner.app.close()
        engine.dispose()


# Clear toy/runner rows between tests after each test has stopped its owned child processes.
@pytest.fixture
def lab(database):
    engine, runner = database
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE qualification.operation, procrastinate_jobs, "
                "procrastinate_workers RESTART IDENTITY CASCADE"
            )
        )
    return SimpleNamespace(engine=engine, runner=runner)


# Observe committed toy intent/audit/job/effect rows through an independent SQL connection.
def counts(engine):
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text("""
            SELECT (SELECT count(*) FROM qualification.operation),
                   (SELECT count(*) FROM qualification.audit),
                   (SELECT count(*) FROM procrastinate_jobs WHERE queue_name='qualification'),
                   (SELECT count(*) FROM qualification.effect)
        """)
            ).one()
        )


# Bound state waits and fail instead of accepting missing evidence.
def wait_for(predicate, *, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.03)
    pytest.fail("Qualification state did not arrive before its deadline")


# Launch an owned worker: persistent selects --wait; otherwise drain visible jobs and exit.
def process(tmp_path, mode="worker", *, request_key=None, persistent=False):
    arguments = [sys.executable, "-m", "otm_runner_qualification.worker", mode]
    if persistent:
        arguments.append("--wait")
    if request_key:
        arguments += ["--request-key", request_key]
    with (tmp_path / (mode + "-" + uuid4().hex[:8] + "-process.log")).open("w") as log:
        return subprocess.Popen(
            arguments,
            env=dict(os.environ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE if mode != "worker" else log,
            stderr=log,
        )


# Kill any still-running owned child, reap it and close its pipes.
def stop(child):
    if child.poll() is None:
        child.kill()
    child.wait(timeout=5)
    for stream in (child.stdin, child.stdout):
        if stream:
            stream.close()


# Require an explicit before/after-commit signal instead of guessing timing from a sleep.
def boundary_ready(child):
    ready, _, _ = io_select.select([child.stdout], [], [], 10)
    assert ready and child.stdout.readline().strip() == b"boundary-ready"


# Read a scoped toy state without opening a transaction across a worker wait.
def operation_state(engine, identifier):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT state FROM qualification.operation WHERE id=:id"), {"id": identifier}
        ).scalar_one()
