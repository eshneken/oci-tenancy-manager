"""Accepted availability risks must not become a blanket image or future-version waiver."""

import copy
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "caddy_image_policy", ROOT / "scripts/caddy_image_policy.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# Model both currently accepted findings without importing private scan artifacts into fixtures.
def report():
    policy = json.loads((ROOT / "tools/caddy/security-exceptions.json").read_text())
    findings = [
        dict(
            zip(
                ("VulnerabilityID", "PkgName", "InstalledVersion", "Severity"),
                (item["id"], item["package"], item["version"], item["severity"]),
                strict=True,
            )
        )
        for item in policy["exceptions"]
    ]
    return {
        "Results": [{"Target": "usr/bin/caddy", "Type": "gobinary", "Vulnerabilities": findings}]
    }


# Approved findings remain explicit and disappearing fixed findings do not require a dummy failure.
def test_exact_acceptance_and_clean_scan():
    result = MODULE.evaluate(report())
    assert len(result["accepted"]) == 2 and result["blocked"] == []
    clean = report()
    clean["Results"][0]["Vulnerabilities"] = []
    assert MODULE.evaluate(clean) == {"accepted": [], "blocked": []}


# New IDs, escalated severity, other versions or another binary remain blocking findings.
@pytest.mark.parametrize(
    "field,value",
    [
        ("VulnerabilityID", "CVE-2099-0001"),
        ("Severity", "CRITICAL"),
        ("PkgName", "other/package"),
        ("InstalledVersion", "v99.0.0"),
    ],
)
def test_no_broader_exemption(field, value):
    candidate = report()
    candidate["Results"][0]["Vulnerabilities"][0][field] = value
    assert len(MODULE.evaluate(candidate)["blocked"]) == 1
    candidate = report()
    other = copy.deepcopy(candidate["Results"][0])
    other["Target"] = "other/binary"
    candidate["Results"].append(other)
    assert len(MODULE.evaluate(candidate)["blocked"]) == 2


# Missing language scanning or changed Caddy release requires fresh evidence and review.
def test_incomplete_scan_and_new_version_fail(monkeypatch):
    for invalid in ({}, {"Results": []}, {"Results": [None]}, {"Results": [{"Type": "alpine"}]}):
        with pytest.raises(ValueError, match="CADDY_SCAN_RESULTS_REQUIRED"):
            MODULE.evaluate(invalid)
    monkeypatch.setattr(MODULE, "caddy_version", lambda: "2.99.0")
    with pytest.raises(ValueError, match="CADDY_EXCEPTION_REVIEW_REQUIRED"):
        MODULE.evaluate(report())


# Verify upstream TLS with bounded time; newer, draft and prerelease tags cannot count as current.
@pytest.mark.parametrize("fault", [None, "newer", "draft", "prerelease"])
def test_latest_official_release(monkeypatch, fault):
    release = {"tag_name": "v" + MODULE.caddy_version(), "draft": False, "prerelease": False}
    if fault == "newer":
        release["tag_name"] = "v99.0.0"
    elif fault:
        release[fault] = True
    opener = Mock(return_value=io.BytesIO(json.dumps(release).encode()))
    monkeypatch.setattr(MODULE.urllib.request, "urlopen", opener)
    if fault:
        with pytest.raises(ValueError, match="CADDY_LATEST_STABLE_REQUIRED"):
            MODULE.check_latest()
    else:
        assert MODULE.check_latest() == release["tag_name"]
    kwargs = opener.call_args.kwargs
    assert kwargs["timeout"] == 25
    assert kwargs["context"].check_hostname is True


# Daily detection never deploys; reviewed Dependabot proposals and checkpoint scans remain active.
def test_continuous_watch_and_update_proposals():
    workflow = yaml.safe_load((ROOT / ".github/workflows/caddy-security.yml").read_text())
    assert workflow[True]["schedule"] == [{"cron": "20 11 * * *"}]
    commands = [step.get("run", "") for step in workflow["jobs"]["caddy-security"]["steps"]]
    assert any("check_caddy_ingress.py" in value for value in commands)
    assert workflow["permissions"] == {"contents": "read"}
    updates = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())["updates"]
    assert any("/tools/caddy" in item.get("directories", []) for item in updates)


# An empty mapping is malformed scanner output, not an empty list of vulnerabilities.
@pytest.mark.parametrize("findings", [{}, "", [None]])
def test_malformed_findings_fail_closed(findings):
    candidate = report()
    candidate["Results"][0]["Vulnerabilities"] = findings
    with pytest.raises(ValueError, match="CADDY_SCAN_FINDINGS_INVALID"):
        MODULE.evaluate(candidate)


# An unpinned or unrelated Dockerfile cannot claim the reviewed official release.
def test_official_image_pin_is_required(tmp_path, monkeypatch):
    directory = tmp_path / "tools/caddy"
    directory.mkdir(parents=True)
    (directory / "Dockerfile").write_text("FROM caddy:latest\n")
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="CADDY_OFFICIAL_PIN_REQUIRED"):
        MODULE.caddy_version()


# A similarly named result of a different scanner type cannot reuse a Go-binary exception.
def test_wrong_result_type_cannot_share_exceptions():
    candidate = report()
    other = copy.deepcopy(candidate["Results"][0])
    other["Type"] = "alpine"
    candidate["Results"].append(other)
    assert len(MODULE.evaluate(candidate)["blocked"]) == 2
