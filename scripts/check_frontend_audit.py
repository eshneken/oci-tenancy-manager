"""Apply one owner-approved development dependency exception without hiding audit findings."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADVISORY = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"
VERSION = "4.0.7"


# npm 11 can call a forced older-major tooling downgrade a fix where npm 12 reports none.
# This never authorizes a downgrade: compatible upgrades, direct root fixes and unknown proposals
# require review, while the exact advisory/version/dev-only checks still apply independently.
def no_compatible_fix(fix, lock):
    if fix is False:
        return True
    if not isinstance(fix, dict) or fix.get("isSemVerMajor") is not True:
        return False
    name, proposed = fix.get("name"), fix.get("version")
    if not isinstance(name, str) or name == "picomatch" or not isinstance(proposed, str):
        return False
    installed = lock["packages"].get("node_modules/" + name, {})
    version = installed.get("version", "")
    return bool(
        installed.get("dev") is True
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", proposed)
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
        and int(proposed.split(".")[0]) < int(version.split(".")[0])
    )


# Accept only development-only findings whose complete dependency chain has this one root cause.
# A compatible fix, changed package/version/severity or another advisory requires fresh review.
def evaluate(report, lock):
    if (
        report.get("auditReportVersion") != 2
        or "error" in report
        or not isinstance(report.get("vulnerabilities"), dict)
        or lock.get("lockfileVersion") != 3
        or not isinstance(lock.get("packages"), dict)
    ):
        raise ValueError("NPM_AUDIT_EVIDENCE_REQUIRED")
    findings = report["vulnerabilities"]
    counts = report.get("metadata", {}).get("vulnerabilities", {})
    severities = ("info", "low", "moderate", "high", "critical")
    if counts.get("total") != len(findings) or any(
        counts.get(severity)
        != sum(v.get("severity") == severity for v in findings.values())
        for severity in severities
    ):
        raise ValueError("NPM_AUDIT_COUNTS_INVALID")
    accepted, blocked = [], []

    # npm peer-dependency cycles are normal; traverse their complete closure and require an actual
    # approved advisory, so a rootless cycle or mixed new finding can never inherit acceptance.
    def approved(name):
        pending, visited, rooted = [name], set(), False
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if current not in findings:
                return False
            finding = findings[current]
            if (
                finding.get("name") != current
                or finding.get("severity") != "high"
                or not no_compatible_fix(finding.get("fixAvailable"), lock)
                or not isinstance(finding.get("nodes"), list)
                or not finding["nodes"]
                or not isinstance(finding.get("via"), list)
                or not finding["via"]
            ):
                return False
            for node in finding["nodes"]:
                package = lock["packages"].get(node, {})
                if package.get("dev") is not True or not node.endswith(
                    "node_modules/" + current
                ):
                    return False
                if current == "picomatch" and package.get("version") != VERSION:
                    return False
            for cause in finding["via"]:
                if isinstance(cause, str):
                    pending.append(cause)
                elif (
                    isinstance(cause, dict)
                    and current == "picomatch"
                    and cause.get("name") == "picomatch"
                    and cause.get("dependency") == "picomatch"
                    and cause.get("url") == ADVISORY
                    and cause.get("severity") == "high"
                    and cause.get("range") == "<=4.0.7"
                ):
                    rooted = True
                else:
                    return False
        return rooted

    for name in findings:
        (accepted if approved(name) else blocked).append(name)
    return {
        "accepted": sorted(accepted),
        "blocked": sorted(blocked),
        "advisory": ADVISORY,
    }


# Keep the complete original report private; scanner failures never become an empty clean audit.
def main():
    result = subprocess.run(
        ["npm", "audit", "--json"],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    report = json.loads(result.stdout)
    if result.returncode not in {0, 1} or (result.returncode == 0) != (
        report.get("metadata", {}).get("vulnerabilities", {}).get("total") == 0
    ):
        raise ValueError("NPM_AUDIT_FAILED")
    directory = ROOT / ".local-dev/quality"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "frontend-audit.json").write_text(result.stdout)
    outcome = evaluate(
        report, json.loads((ROOT / "frontend/package-lock.json").read_text())
    )
    print(json.dumps(outcome))
    return int(bool(outcome["blocked"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
    ):
        print(json.dumps({"status": "fail", "code": "NPM_AUDIT_EVIDENCE_UNVERIFIED"}))
        raise SystemExit(1) from None
