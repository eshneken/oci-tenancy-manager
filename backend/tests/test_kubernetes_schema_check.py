"""The native schema gate must reject unavailable checks, invalid fields and missing resources."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "kubernetes_schema_check", SCRIPTS / "check_kubernetes_bundle.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# The only validator pin comes from a reviewed version+digest manifest, not an environment fallback.
def test_validator_pin_and_rejections(tmp_path):
    actual = MODULE.validator_image(MODULE.ROOT / "tools/kubeconform/Dockerfile")
    assert actual.startswith("ghcr.io/yannh/kubeconform:v") and "@sha256:" in actual
    path = tmp_path / "Dockerfile"
    for content in (
        "",
        "FROM ghcr.io/yannh/kubeconform:latest",
        "FROM other/tool@sha256:" + "a" * 64,
        "FROM a\nFROM b",
    ):
        path.write_text(content)
        with pytest.raises(ValueError, match="KUBERNETES_VALIDATOR_PIN_INVALID"):
            MODULE.validator_image(path)


# Both synthetic targets render normally while a separate strict-schema canary remains invalid.
def test_synthetic_schema_candidates(tmp_path):
    assert MODULE.candidates(tmp_path) == [
        "staging.json",
        "staging-oci.json",
        "staging-ingress.json",
        "production.json",
        "production-oci.json",
        "production-ingress.json",
    ]
    for environment in ("staging", "production"):
        data = json.loads((tmp_path / (environment + ".json")).read_text())
        assert len(data["items"]) == 8
        assert all(item["metadata"]["namespace"] == "otm-" + environment for item in data["items"])
    invalid = json.loads((tmp_path / "invalid.json").read_text())
    assert (
        invalid["kind"] == "Deployment"
        and invalid["spec"]["intentionallyInvalidForNegativeControl"] is True
    )


# A failed/partial/skipped schema check cannot become a passing native result.
@pytest.mark.parametrize(
    "fault", [None, "invalid", "skip", "error", "missing", "exit", "json", "timeout"]
)
def test_native_check_gate(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: "/bin/docker")
    removed = Mock()
    monkeypatch.setattr(MODULE, "remove_owned", removed)
    summary = {"valid": 18, "invalid": 0, "errors": 0, "skipped": 0}
    if fault in {"invalid", "skip", "error"}:
        summary[{"invalid": "invalid", "skip": "skipped", "error": "errors"}[fault]] = 1
    if fault == "missing":
        summary["valid"] = 0
    result = subprocess.CompletedProcess(
        [], 1 if fault == "exit" else 0, json.dumps({"summary": summary}), ""
    )
    if fault == "json":
        result.stdout = "unparseable"
    run = (
        Mock(side_effect=subprocess.TimeoutExpired("docker", 180))
        if fault == "timeout"
        else Mock(return_value=result)
    )
    monkeypatch.setattr(MODULE.subprocess, "run", run)
    if fault is None:
        MODULE.validate(
            tmp_path,
            ["staging.json", "production.json"],
            "pinned-image",
            expected_valid=18,
            expected_invalid=0,
        )
        args = run.call_args.args[0]
        assert "--read-only" in args and "no-new-privileges" in args
        assert "--strict" not in args and "-strict" in args
        assert "-ignore-missing-schemas" not in args
    else:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)):
            MODULE.validate(
                tmp_path, ["staging.json"], "pinned-image", expected_valid=18, expected_invalid=0
            )
    removed.assert_called_once()


# The strict rejection canary must report one invalid resource and the expected nonzero exit code.
def test_native_negative_control(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: "/bin/docker")
    monkeypatch.setattr(MODULE, "remove_owned", Mock())
    result = subprocess.CompletedProcess(
        [], 1, json.dumps({"summary": {"valid": 0, "invalid": 1, "errors": 0, "skipped": 0}}), ""
    )
    monkeypatch.setattr(MODULE.subprocess, "run", Mock(return_value=result))
    MODULE.validate(
        tmp_path, ["invalid.json"], "pinned-image", expected_valid=0, expected_invalid=1
    )


# Missing Docker fails before any subprocess or cleanup could act on an unowned container.
def test_native_missing_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="KUBERNETES_VALIDATOR_DOCKER_REQUIRED"):
        MODULE.validate(tmp_path, [], "pinned-image", expected_valid=18, expected_invalid=0)


# Top-level failure diagnostics never echo potentially sensitive subprocess output.
@pytest.mark.parametrize("failure", [False, True])
def test_native_main_receipt(monkeypatch, capsys, failure):
    validate = Mock(side_effect=RuntimeError("private-details")) if failure else Mock()
    monkeypatch.setattr(MODULE, "validate", validate)
    assert MODULE.main() == (1 if failure else 0)
    output = capsys.readouterr().out
    assert "private-details" not in output
    assert ("KUBERNETES_SCHEMA_CHECK_FAILED" in output) is failure
