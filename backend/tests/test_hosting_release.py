"""Hosting compartment inputs stay private references with no commands or default targets."""

import hashlib
import json
import runpy
import stat
from pathlib import Path

import pytest

from otm.hosting_release import main, render_hosting_input


# The exact environment value reaches one flat Terraform input with private permissions and digest.
def test_private_hosting_input(tmp_path):
    output = tmp_path / "hosting.tfvars.json"
    digest = render_hosting_input(output, "ocid1.compartment.oc1..synthetichosting")
    assert json.loads(output.read_bytes()) == {
        "hosting_compartment_ocid": "ocid1.compartment.oc1..synthetichosting"
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()


# Reject missing, wrong-resource, padded, injected, nonstring and oversized targets before writing.
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        1,
        "ocid1.tenancy.oc1..synthetic",
        "compartment-name",
        " ocid1.compartment.oc1..synthetic",
        "ocid1.compartment.oc1..synthetic\n",
        "ocid1.compartment.oc1..synthetic;false",
        "ocid1.compartment.oc1.." + "a" * 255,
    ],
)
def test_reject_invalid_hosting_input(tmp_path, value):
    output = tmp_path / "hosting.json"
    with pytest.raises(ValueError, match="^INVALID_HOSTING_COMPARTMENT$"):
        render_hosting_input(output, value)
    assert not output.exists()


# Re-rendering cannot overwrite an approved candidate or follow a malicious destination symlink.
def test_existing_candidates_are_preserved(tmp_path):
    existing = tmp_path / "existing.json"
    existing.write_text("keep")
    alias = tmp_path / "alias.json"
    alias.symlink_to(existing)
    for output in (existing, alias):
        with pytest.raises(FileExistsError):
            render_hosting_input(output, "ocid1.compartment.oc1..synthetic")
    assert existing.read_text() == "keep"


# CLI diagnostics expose only a digest on success or a fixed error without deployment coordinates.
def test_cli_input_is_required_and_not_disclosed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OTM_HOSTING_COMPARTMENT_OCID", "ocid1.compartment.oc1..synthetic")
    output = tmp_path / "hosting.json"
    assert main(["--output", str(output)]) == 0
    assert list(json.loads(capsys.readouterr().out)) == ["hosting_input_sha256"]
    monkeypatch.delenv("OTM_HOSTING_COMPARTMENT_OCID")
    assert main(["--output", str(tmp_path / "missing.json")]) == 1
    assert capsys.readouterr().out == "HOSTING_INPUT_REJECTED\n"


# The documented module entrypoint exercises the same nonsecret reference validation path.
def test_module_entrypoint(tmp_path, monkeypatch, capsys):
    import otm.hosting_release

    monkeypatch.setenv("OTM_HOSTING_COMPARTMENT_OCID", "ocid1.compartment.oc1..synthetic")
    monkeypatch.setattr(
        "sys.argv", ["otm.hosting_release", "--output", str(tmp_path / "entry.json")]
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(otm.hosting_release.__file__)), run_name="__main__")
    assert result.value.code == 0
    assert "hosting_input_sha256" in capsys.readouterr().out
