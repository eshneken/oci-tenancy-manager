"""No-database reproductions of timeout/error cleanup for owned test process descendants."""

import os
import subprocess
import time

import pytest
from otm_runner_qualification.processes import run_python_group


# Wait for process exit; an OS-owned zombie is stopped and awaits its reaper, not running.
def assert_not_running(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True
        ).stdout.strip()
        if not state or state.startswith("Z"):
            return
        time.sleep(0.03)
    pytest.fail("Owned sentinel descendant is still running")


# A sentinel grandchild must not survive either a timed-out or failed Python test leader.
@pytest.mark.parametrize("timeout_case", [True, False])
def test_timeout_and_early_leader_failure_stop_owned_descendant(tmp_path, timeout_case):
    program = (
        "import subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "print(child.pid,flush=True)\n" + ("time.sleep(60)\n" if timeout_case else "sys.exit(7)\n")
    )
    result = run_python_group(["-c", program], cwd=tmp_path, env=dict(os.environ), timeout=0.5)
    assert result.timed_out is timeout_case
    assert result.returncode == (-9 if timeout_case else 7)
    assert_not_running(int(result.stdout.strip()))


# Ordinary passing checks retain output without a timeout or orphaned leader.
def test_successful_group_run_returns_output_and_reaps_leader(tmp_path):
    result = run_python_group(
        ["-c", "print('completed')"], cwd=tmp_path, env=dict(os.environ), timeout=5
    )
    assert result.returncode == 0 and result.stdout.strip() == "completed" and not result.timed_out
