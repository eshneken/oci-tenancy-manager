"""Apply exact Caddy availability-risk exceptions; keep all other image findings blocking."""

import json
import re
import ssl
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
LATEST = "https://api.github.com/repos/caddyserver/caddy/releases/latest"


# The exception belongs to one reviewed official release, not arbitrary images or future versions.
def caddy_version():
    source = (ROOT / "tools/caddy/Dockerfile").read_text()
    match = re.search(
        r"^FROM caddy:([0-9]+\.[0-9]+\.[0-9]+)-alpine@sha256:[0-9a-f]{64}$",
        source,
        re.M,
    )
    if match is None:
        raise ValueError("CADDY_OFFICIAL_PIN_REQUIRED")
    return match[1]


# Fail closed when the approved version is outdated or the official release cannot be verified.
def check_latest():
    request = urllib.request.Request(
        LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "otm-caddy-security",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, context=context, timeout=25) as response:
        release = json.loads(response.read(1048576))
    if (
        release.get("tag_name") != "v" + caddy_version()
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("CADDY_LATEST_STABLE_REQUIRED")
    return release["tag_name"]


# Retain accepted findings in the receipt; only exact approved binary/package/version tuples pass.
def evaluate(report):
    policy = json.loads((ROOT / "tools/caddy/security-exceptions.json").read_text())
    if policy["caddy_version"] != caddy_version():
        raise ValueError("CADDY_EXCEPTION_REVIEW_REQUIRED")
    results = report.get("Results")
    if (
        not isinstance(results, list)
        or any(not isinstance(result, dict) for result in results)
        or not any(
            result.get("Target") == "usr/bin/caddy" and result.get("Type") == "gobinary"
            for result in results
        )
    ):
        raise ValueError("CADDY_SCAN_RESULTS_REQUIRED")
    allowed = {
        tuple(entry[key] for key in ("id", "package", "version", "severity"))
        for entry in policy["exceptions"]
    }
    accepted, blocked = [], []
    for result in results:
        findings = result.get("Vulnerabilities")
        if findings is not None and not isinstance(findings, list):
            raise ValueError("CADDY_SCAN_FINDINGS_INVALID")
        for finding in findings or []:
            if not isinstance(finding, dict):
                raise ValueError("CADDY_SCAN_FINDINGS_INVALID")
            identity = tuple(
                finding.get(key)
                for key in (
                    "VulnerabilityID",
                    "PkgName",
                    "InstalledVersion",
                    "Severity",
                )
            )
            # A severity change, different binary or package version must receive a fresh review.
            permitted = (
                result.get("Target") == "usr/bin/caddy"
                and result.get("Type") == "gobinary"
                and identity in allowed
            )
            record = dict(
                zip(("id", "package", "version", "severity"), identity, strict=True)
            )
            (accepted if permitted else blocked).append(record)
    return {"accepted": accepted, "blocked": blocked}


if __name__ == "__main__":
    print(json.dumps({"latest_official_release": check_latest()}))
