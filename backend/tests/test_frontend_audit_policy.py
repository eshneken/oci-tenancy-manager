"""One accepted development advisory must not suppress new findings or failed audit evidence."""

import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "frontend_audit", ROOT / "scripts/check_frontend_audit.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# Synthetic npm evidence includes a peer cycle and one concrete accepted advisory root.
def evidence():
    root = {
        "name": "picomatch",
        "dependency": "picomatch",
        "url": MODULE.ADVISORY,
        "severity": "high",
        "range": "<=4.0.7",
    }
    findings = {
        name: {
            "name": name,
            "severity": "high",
            "fixAvailable": False,
            "nodes": ["node_modules/" + name],
            "via": via,
        }
        for name, via in (
            ("picomatch", [root]),
            ("tool", ["picomatch", "peer"]),
            ("peer", ["tool"]),
        )
    }
    report = {
        "auditReportVersion": 2,
        "vulnerabilities": findings,
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 0,
                "moderate": 0,
                "high": 3,
                "critical": 0,
                "total": 3,
            }
        },
    }
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "node_modules/" + name: {
                "version": "4.0.7" if name == "picomatch" else "1.0.0",
                "dev": True,
            }
            for name in findings
        },
    }
    return report, lock


# Every reachable cause must be accepted, including peer cycles; clean audits need no exception.
def test_exact_advisory_and_clean_audit():
    report, lock = evidence()
    assert MODULE.evaluate(report, lock)["accepted"] == ["peer", "picomatch", "tool"]
    report["vulnerabilities"] = {}
    report["metadata"]["vulnerabilities"].update(high=0, total=0)
    assert MODULE.evaluate(report, lock)["accepted"] == []
    assert MODULE.evaluate(report, lock)["blocked"] == []


# A reported forced older-major tooling downgrade is not a compatible patch; other proposals
# remain blocking, including direct root replacements and newer or malformed tool versions.
@pytest.mark.parametrize(
    "proposal,accepted",
    [
        ({"name": "tool", "version": "0.9.0", "isSemVerMajor": True}, True),
        ({"name": "tool", "version": "0.9.0", "isSemVerMajor": False}, False),
        ({"name": "tool", "version": "2.0.0", "isSemVerMajor": True}, False),
        ({"name": "tool", "version": "1.0.0", "isSemVerMajor": True}, False),
        ({"name": "picomatch", "version": "3.0.0", "isSemVerMajor": True}, False),
        ({"name": "missing", "version": "0.9.0", "isSemVerMajor": True}, False),
        ({"name": "tool", "version": "0.9.0-beta", "isSemVerMajor": True}, False),
        ({"name": "tool", "version": None, "isSemVerMajor": True}, False),
    ],
)
def test_forced_downgrade_is_not_a_patch(proposal, accepted):
    report, lock = evidence()
    report["vulnerabilities"]["picomatch"]["fixAvailable"] = proposal
    assert ("tool" in MODULE.evaluate(report, lock)["accepted"]) is accepted
    lock["packages"]["node_modules/tool"]["dev"] = False
    assert not MODULE.no_compatible_fix(proposal, lock)


# Name, URL, severity, version, runtime use, missing paths and newly available fixes cannot inherit
# this approval; mixed roots and rootless/unknown dependency chains also remain blocking.
@pytest.mark.parametrize(
    "fault",
    [
        "advisory",
        "package",
        "range",
        "severity",
        "version",
        "runtime",
        "dependent_runtime",
        "missing_node",
        "fix",
        "dependent_fix",
        "mixed",
        "unknown",
        "rootless",
        "empty_via",
        "empty_nodes",
    ],
)
def test_narrow_exception_only(fault):
    report, lock = evidence()
    root = report["vulnerabilities"]["picomatch"]
    cause = root["via"][0]
    if fault in {"advisory", "package", "range", "severity"}:
        cause[
            {"advisory": "url", "package": "name", "range": "range", "severity": "severity"}[fault]
        ] = "unaccepted"
    elif fault == "version":
        lock["packages"]["node_modules/picomatch"]["version"] = "4.0.8"
    elif fault in {"runtime", "dependent_runtime"}:
        lock["packages"][
            "node_modules/" + ("tool" if fault == "dependent_runtime" else "picomatch")
        ]["dev"] = False
    elif fault == "missing_node":
        del lock["packages"]["node_modules/picomatch"]
    elif fault in {"fix", "dependent_fix"}:
        report["vulnerabilities"]["tool" if fault == "dependent_fix" else "picomatch"][
            "fixAvailable"
        ] = True
    elif fault == "mixed":
        extra = copy.deepcopy(cause)
        extra["url"] = "https://github.com/advisories/GHSA-new"
        root["via"].append(extra)
    elif fault == "unknown":
        root["via"] = ["missing"]
    elif fault == "rootless":
        root["via"] = ["tool"]
    elif fault == "empty_via":
        root["via"] = []
    else:
        root["nodes"] = []
    result = MODULE.evaluate(report, lock)
    assert "tool" in result["blocked"]
    assert result["blocked"]


# Truncated, inconsistent or error-bearing reports are not successful clean scans.
@pytest.mark.parametrize("fault", ["format", "error", "missing", "counts", "lock"])
def test_incomplete_evidence(fault):
    report, lock = evidence()
    if fault == "format":
        report["auditReportVersion"] = 1
    elif fault == "error":
        report["error"] = {"code": "NETWORK_UNAVAILABLE"}
    elif fault == "missing":
        del report["vulnerabilities"]
    elif fault == "counts":
        report["metadata"]["vulnerabilities"]["total"] = 0
    else:
        lock["lockfileVersion"] = 2
    with pytest.raises(ValueError):
        MODULE.evaluate(report, lock)


# The CLI preserves raw reports and returns failure for new findings or scanner process errors.
@pytest.mark.parametrize("fault", [None, "blocked", "exit", "inconsistent_exit", "network", "json"])
def test_cli_scan_evidence(monkeypatch, tmp_path, fault):
    report, lock = evidence()
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package-lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    if fault == "blocked":
        report["vulnerabilities"]["picomatch"]["via"][0]["url"] = "other"
    result = SimpleNamespace(
        returncode=2 if fault == "exit" else 0 if fault == "inconsistent_exit" else 1,
        stdout="invalid" if fault == "json" else json.dumps(report),
    )

    # Inspect the fixed executable/cwd/timeout boundary without issuing real network traffic.
    def run(arguments, **kwargs):
        assert arguments == ["npm", "audit", "--json"]
        assert kwargs["cwd"] == frontend and kwargs["timeout"] == 90
        if fault == "network":
            raise subprocess.TimeoutExpired(arguments, 90)
        return result

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    if fault in {"exit", "inconsistent_exit", "network", "json"}:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)):
            MODULE.main()
    else:
        assert MODULE.main() == int(fault == "blocked")
        assert (
            json.loads((tmp_path / ".local-dev/quality/frontend-audit.json").read_text()) == report
        )
