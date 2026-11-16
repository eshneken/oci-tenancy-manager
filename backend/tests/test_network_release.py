"""Synthetic network inputs fail closed without cloud credentials or source leakage."""

import json
import runpy
import stat
from pathlib import Path

import pytest

from otm.network_release import main, render_network_inputs
from otm.recovery_console import parse_release_cidrs


# Mixed ranges/hosts use the same canonical policy fingerprint as the recovery-console release.
def test_render_exact_shared_policy_with_private_permissions(tmp_path):
    value = "203.0.113.7/32,198.51.100.0/24,203.0.113.8/32,203.0.113.7/32"
    output = tmp_path / "ingress.tfvars.json"
    policy = render_network_inputs(output, value)
    assert json.loads(output.read_text()) == {
        "app_ingress_allowed_cidrs": ["198.51.100.0/24", "203.0.113.7/32", "203.0.113.8/32"]
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert policy.fingerprint == parse_release_cidrs(value).fingerprint


# Invalid unions and unsupported address families cannot leave a partially accepted candidate.
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "203.0.113.7",
        "203.0.113.7/24",
        "0.0.0.0/0",
        "0.0.0.0/1,128.0.0.0/1",
        "198.51.100.0/24,",
        "198.51.100.0/24,$(touch /tmp/never)",
        "2001:db8::7/128",
        "198.51.100.0/24,2001:db8::7/128",
        "x" * 4097,
    ],
)
def test_reject_entire_candidate_before_file_creation(tmp_path, value):
    output = tmp_path / "ingress.tfvars.json"
    with pytest.raises(ValueError):
        render_network_inputs(output, value)
    assert not output.exists()


# Neither a valid existing file nor a symlink is ever truncated by a subsequent render.
def test_existing_candidate_and_symlink_are_preserved(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("preserve")
    alias = tmp_path / "alias.json"
    alias.symlink_to(output)
    for destination in (output, alias):
        with pytest.raises(FileExistsError):
            render_network_inputs(destination, "198.51.100.0/24")
    assert output.read_text() == "preserve"


# Success uses only the generic input and emits a private-policy digest rather than the list.
def test_cli_shared_input_and_sanitized_receipt(tmp_path, monkeypatch, capsys):
    output = tmp_path / "ingress.tfvars.json"
    value = "198.51.100.0/24,203.0.113.7/32"
    monkeypatch.setenv("OTM_ALLOWED_SOURCE_CIDRS", value)
    assert main(["--output", str(output)]) == 0
    receipt = capsys.readouterr().out
    assert "198.51" not in receipt and "203.0" not in receipt
    assert json.loads(receipt) == {
        "allowed_source_count": 2,
        "source_fingerprint": parse_release_cidrs(value).fingerprint,
    }


# Missing values and I/O failures produce fixed errors without operational ranges or file paths.
@pytest.mark.parametrize("missing", [True, False])
def test_cli_safe_failures(tmp_path, monkeypatch, capsys, missing):
    output = tmp_path / "ingress.tfvars.json"
    if missing:
        monkeypatch.delenv("OTM_ALLOWED_SOURCE_CIDRS", raising=False)
    else:
        monkeypatch.setenv("OTM_ALLOWED_SOURCE_CIDRS", "198.51.100.0/24")
        output.write_text("preserve")
    assert main(["--output", str(output)]) == 1
    assert capsys.readouterr().out == "NETWORK_INPUTS_REJECTED\n"
    assert output.exists() is not missing


# The documented python-module entry point exits successfully and produces usable private tfvars.
def test_module_entrypoint(tmp_path, monkeypatch, capsys):
    import otm.network_release

    output = tmp_path / "ingress.tfvars.json"
    monkeypatch.setenv("OTM_ALLOWED_SOURCE_CIDRS", "203.0.113.7/32")
    monkeypatch.setattr("sys.argv", ["otm.network_release", "--output", str(output)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(otm.network_release.__file__)), run_name="__main__")
    assert result.value.code == 0
    assert json.loads(output.read_text())["app_ingress_allowed_cidrs"] == ["203.0.113.7/32"]
    assert "203.0.113" not in capsys.readouterr().out
