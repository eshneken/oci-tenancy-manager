"""Accepted availability risks must not become a blanket image or future-version waiver."""

import copy
import importlib.util
import io
import json
import urllib.error
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
    monkeypatch.delenv("GH_TOKEN", raising=False)
    release = {"tag_name": "v" + MODULE.caddy_version(), "draft": False, "prerelease": False}
    if fault == "newer":
        release["tag_name"] = "v99.0.0"
    elif fault:
        release[fault] = True
    opener = Mock()
    opener.open.return_value = io.BytesIO(json.dumps(release).encode())
    builder = Mock(return_value=opener)
    monkeypatch.setattr(MODULE.urllib.request, "build_opener", builder)
    if fault:
        with pytest.raises(ValueError, match="CADDY_LATEST_STABLE_REQUIRED"):
            MODULE.check_latest()
    else:
        assert MODULE.check_latest() == release["tag_name"]
    kwargs = opener.open.call_args.kwargs
    assert kwargs["timeout"] == 25
    assert builder.call_args.args[0]._context.check_hostname is True
    assert opener.open.call_args.args[0].get_header("Authorization") is None


# Hosted lookup uses the read-only job token only for the fixed API and keeps TLS verification.
def test_authenticated_release_lookup(monkeypatch):
    token = "synthetic" + "-job-token"
    monkeypatch.setenv("GH_TOKEN", token)
    release = {"tag_name": "v" + MODULE.caddy_version(), "draft": False, "prerelease": False}
    opener = Mock()
    opener.open.return_value = io.BytesIO(json.dumps(release).encode())
    builder = Mock(return_value=opener)
    monkeypatch.setattr(MODULE.urllib.request, "build_opener", builder)
    anonymous = Mock(side_effect=AssertionError("anonymous fallback forbidden"))
    monkeypatch.setattr(MODULE.urllib.request, "urlopen", anonymous)
    assert MODULE.check_latest() == release["tag_name"]
    request = opener.open.call_args.args[0]
    assert request.full_url == MODULE.LATEST
    assert request.get_header("Authorization") == "Bearer " + token
    assert opener.open.call_args.kwargs == {"timeout": 25}
    https, redirect = builder.call_args.args
    assert https._context.check_hostname is True
    assert https._context.verify_mode == MODULE.ssl.CERT_REQUIRED
    assert isinstance(redirect, MODULE.NoCredentialRedirect)
    assert (
        redirect.redirect_request(request, None, 302, "redirect", {}, "https://example.test")
        is None
    )
    anonymous.assert_not_called()


# Authentication or rate-limit failures stay visible; no unauthenticated retry can hide a failure.
@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_authenticated_lookup_fails_closed(monkeypatch, status):
    monkeypatch.setenv("GH_TOKEN", "synthetic" + "-job-token")
    opener = Mock()
    opener.open.side_effect = urllib.error.HTTPError(MODULE.LATEST, status, "rejected", {}, None)
    monkeypatch.setattr(MODULE.urllib.request, "build_opener", Mock(return_value=opener))
    anonymous = Mock(side_effect=AssertionError("anonymous fallback forbidden"))
    monkeypatch.setattr(MODULE.urllib.request, "urlopen", anonymous)
    with pytest.raises(urllib.error.HTTPError) as error:
        MODULE.check_latest()
    assert error.value.code == status
    assert opener.open.call_count == 1
    anonymous.assert_not_called()


# Every CI caller supplies an ephemeral token only to its official-release checking commands.
def test_hosted_lookup_has_step_scoped_token():
    for name, job in (
        ("checkpoint.yml", "documentation"),
        ("caddy-security.yml", "caddy-security"),
    ):
        workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        assert workflow["permissions"] == {"contents": "read"}
        checks = [
            step
            for step in workflow["jobs"][job]["steps"]
            if any(
                command in step.get("run", "")
                for command in ("caddy_image_policy.py", "check_caddy_ingress.py")
            )
        ]
        assert len(checks) == 2
        assert all(step["env"] == {"GH_TOKEN": "${{ github.token }}"} for step in checks)


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
