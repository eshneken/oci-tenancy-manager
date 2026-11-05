"""Bound and clean up an owned local Python process group, including test worker descendants."""

import os
import signal

# Local interpreter invocations only; this test tool accepts no shell or external command input.
import subprocess  # nosec B404
import sys
from dataclasses import dataclass


# Retain bounded-run status/output without treating timeout or missing evidence as success.
@dataclass(frozen=True)
class GroupResult:
    returncode: int
    stdout: str
    timed_out: bool


# Start a new owned session and stop its descendants on success, failure or timeout.
#
# Only this interpreter is executed, with internal test arguments and no shell. The leader is
# reaped here; orphaned descendants are stopped as a group and reaped by the operating system.
# Never target the caller's inherited process group or assume killing pytest kills its workers.
def run_python_group(arguments, *, cwd, env, timeout):
    child = subprocess.Popen(
        [sys.executable, *arguments],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )  # nosec B603

    # Signal only the new session created above; absence means it already finished.
    def kill_owned_group():
        if child.pid == os.getpgrp():
            raise RuntimeError("Refusing to signal the caller process group")
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    timed_out = False
    try:
        try:
            output, _ = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_owned_group()
            output, _ = child.communicate(timeout=5)
        return GroupResult(child.returncode, output, timed_out)
    finally:
        # Also clean up descendants if the leader exited early or Python interrupted this wait.
        kill_owned_group()
        child.wait(timeout=5)
        if child.stdout:
            child.stdout.close()
