"""Synthetic root scripts remain private and are parsed without executing worker installation."""

import hashlib
import json
import runpy
import stat
import subprocess
from pathlib import Path

import pytest

from otm.worker_bootstrap_release import main, render_worker_inputs, validate_worker_script

SCRIPT = "#!/bin/bash\nset -euo pipefail\nprintf 'synthetic only\\n'\n"


# Preserve exact UTF8 script bytes, mark its output owner-only and report a digest instead of code.
def test_private_render_preserves_script_and_permissions(tmp_path):
    output = tmp_path / "worker.tfvars.json"
    digest = render_worker_inputs(output, SCRIPT)
    assert json.loads(output.read_text()) == {"worker_cloud_init": SCRIPT}
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert digest == hashlib.sha256(SCRIPT.encode()).hexdigest()


# Reject absent, malformed, NUL-containing, oversized and syntactically invalid whole candidates.
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "#!/bin/sh\ntrue\n",
        "#!/bin/bash\r\ntrue\n",
        "#!/bin/bash\n\x00",
        "#!/bin/bash\nif then\n",
        "#!/bin/bash\n#" + "x" * 12288,
    ],
)
def test_invalid_script_never_creates_candidate(tmp_path, value):
    output = tmp_path / "worker.tfvars.json"
    with pytest.raises(ValueError, match="^INVALID_WORKER_BOOTSTRAP$"):
        render_worker_inputs(output, value)
    assert not output.exists()


# Parsing must not execute command substitutions, filesystem writes or inherited Bash startup files.
def test_syntax_check_never_executes_script_or_bash_env(tmp_path, monkeypatch):
    sentinel = tmp_path / "must-not-exist"
    startup = tmp_path / "bash-env"
    startup.write_text(f"touch '{sentinel}'\n")
    monkeypatch.setenv("BASH_ENV", str(startup))
    script = f"#!/bin/bash\necho $(touch '{sentinel}')\n"
    assert validate_worker_script(script) == script.encode()
    assert not sentinel.exists()


# Exclusive creation protects candidates and refuses symlinks without truncating their targets.
def test_existing_or_symlink_output_is_preserved(tmp_path):
    existing = tmp_path / "existing.json"
    existing.write_text("preserve")
    alias = tmp_path / "alias.json"
    alias.symlink_to(existing)
    for output in (existing, alias):
        with pytest.raises(FileExistsError):
            render_worker_inputs(output, SCRIPT)
    assert existing.read_text() == "preserve"


# The command reads only the secret input and prints no script, source URL or private output path.
def test_cli_receipt_and_safe_error(tmp_path, monkeypatch, capsys):
    output = tmp_path / "worker.tfvars.json"
    monkeypatch.setenv("OTM_WORKER_CLOUD_INIT", SCRIPT)
    assert main(["--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "worker_bootstrap_sha256": hashlib.sha256(SCRIPT.encode()).hexdigest()
    }
    assert main(["--output", str(output)]) == 1
    assert capsys.readouterr().out == "WORKER_BOOTSTRAP_REJECTED\n"
    monkeypatch.delenv("OTM_WORKER_CLOUD_INIT")
    assert main(["--output", str(tmp_path / "missing.json")]) == 1
    assert capsys.readouterr().out == "WORKER_BOOTSTRAP_REJECTED\n"


# Syntax-check timeout is a fixed failure and cannot leave a supposedly validated candidate behind.
def test_syntax_timeout_is_sanitized(tmp_path, monkeypatch, capsys):
    # Model a hung parser without executing any subprocess or leaking its input through errors.
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("bash", 5)

    monkeypatch.setenv("OTM_WORKER_CLOUD_INIT", SCRIPT)
    monkeypatch.setattr("otm.worker_bootstrap_release.subprocess.run", timeout)
    output = tmp_path / "worker.tfvars.json"
    assert main(["--output", str(output)]) == 1
    assert capsys.readouterr().out == "WORKER_BOOTSTRAP_REJECTED\n"
    assert not output.exists()


# Exercise the documented module entry point, which creates private tfvars and exits successfully.
def test_module_entrypoint(tmp_path, monkeypatch, capsys):
    import otm.worker_bootstrap_release

    output = tmp_path / "worker.tfvars.json"
    monkeypatch.setenv("OTM_WORKER_CLOUD_INIT", SCRIPT)
    monkeypatch.setattr("sys.argv", ["otm.worker_bootstrap_release", "--output", str(output)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(otm.worker_bootstrap_release.__file__)), run_name="__main__")
    assert result.value.code == 0 and output.exists()
    assert "synthetic only" not in capsys.readouterr().out
