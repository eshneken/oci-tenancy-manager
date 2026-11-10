"""Run production database tests only in a fresh, owned loopback PostgreSQL container."""

import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from process_groups import run_python_group

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "backend"
IMAGE = "postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"


# Expose bounded source-style identifiers; parameters, failures, SQL and credentials stay private.
def failing_test_identifiers(cases):
    failing_tests = []
    for case in cases:
        if any(case.find(kind) is not None for kind in ("failure", "error", "skipped")):
            module = case.get("classname", "")
            name = case.get("name", "").split("[", 1)[0]
            failing_tests.append(
                {
                    "module": module
                    if len(module) <= 160
                    and re.fullmatch(r"tests\.[A-Za-z0-9_.]+", module)
                    else "unknown",
                    "test": name
                    if len(name) <= 160 and re.fullmatch(r"test_[A-Za-z0-9_]+", name)
                    else "unknown",
                }
            )
    return failing_tests


# Reveal only bounded locations in known public browser sources, never raw assertion/context text.
def browser_failure_locations(cases):
    names = {
        "auth.spec.ts",
        "signing-key-rotation.spec.ts",
        "simulation.spec.ts",
        "financial-costs.spec.ts",
        "configuration-drift.spec.ts",
        "recovery-network.spec.ts",
        "recovery-access.ts",
        "email-delivery.spec.ts",
        "operation-responsibility.spec.ts",
        "mapping-helpers.ts",
        "configuration-updates.ts",
        "tenancy-overrides.ts",
        "select-audit.ts",
        "baseline-authoring.ts",
        "configuration-drift.ts",
        "shared-membership.ts",
    }
    pattern = re.compile(
        r"^\s*(?:E\s+)?at\s+[^\r\n]*?frontend[/\\]e2e[/\\]"
        r"([a-z0-9][a-z0-9.-]{0,80}\.ts):([1-9][0-9]{0,5}):([1-9][0-9]{0,3})\)?\s*$",
        re.MULTILINE,
    )
    locations = []
    for case in cases:
        for kind in ("failure", "error"):
            failure = case.find(kind)
            if failure is None:
                continue
            text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", failure.text or "")
            for match in pattern.finditer(text):
                name, line, column = match.groups()
                if name not in names:
                    continue
                # Bound numeric positions to public source too, rather than echoing arbitrary IDs.
                try:
                    lines = (
                        (PROJECT_ROOT / "frontend" / "e2e" / name)
                        .read_text()
                        .splitlines()
                    )
                except OSError:
                    continue
                if (
                    int(line) > len(lines)
                    or int(column) > len(lines[int(line) - 1]) + 1
                ):
                    continue
                location = {
                    "file": "frontend/e2e/" + name,
                    "line": int(line),
                    "column": int(column),
                }
                if location not in locations:
                    locations.append(location)
                if len(locations) >= 10:
                    return locations
    return locations


# Require real tests in isolated state, then remove only this owned container.
def main() -> int:
    artifacts = PROJECT_ROOT / ".local-dev/quality"
    artifacts.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="backend-postgres-", dir=artifacts))
    name = "otm-backend-test-" + uuid4().hex[:12]
    password = secrets.token_hex(24)
    # Explicit connection values plus removal of inherited libpq overrides protect the target.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.pop("PYTEST_ADDOPTS", None)
    env["POSTGRES_PASSWORD"] = password
    created = False
    try:
        # Rebuild the exact locked frontend so browser tests cannot pass against stale assets.
        build_environment = {
            key: value
            for key, value in env.items()
            if not key.startswith("OTM_") and key != "POSTGRES_PASSWORD"
        }
        with (directory / "frontend-build.log").open("w") as log:
            for arguments in (
                ["npm", "ci", "--ignore-scripts"],
                ["npm", "run", "contracts:check"],
                ["npm", "run", "build"],
            ):
                built = subprocess.run(
                    arguments,
                    cwd=PROJECT_ROOT / "frontend",
                    env=build_environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                if built.returncode:
                    summary = {
                        "status": "fail",
                        "stage": "frontend-build",
                        "exit": built.returncode,
                    }
                    (directory / "summary.json").write_text(json.dumps(summary) + "\n")
                    print(json.dumps(summary))
                    return 1
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=otm_test",
                "--env",
                "POSTGRES_DB=otm_backend_test",
                "--publish",
                "127.0.0.1::5432",
                IMAGE,
            ],
            env=env,
            check=True,
            capture_output=True,
        )
        created = True
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "otm_test",
                ],
                capture_output=True,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        output = subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", name]
        )
        port = json.loads(output)["5432/tcp"][0]["HostPort"]
        env["OTM_BACKEND_TEST_DATABASE_URL"] = (
            f"postgresql+psycopg://otm_test:{password}@127.0.0.1:{port}/otm_backend_test"
        )
        result = run_python_group(
            [
                "-m",
                "pytest",
                "-q",
                # The independently required unit/coverage gate owns non-database tests.
                "-m",
                "postgres",
                "--tb=short",
                "--junitxml=" + str(directory / "junit.xml"),
                "--basetemp=" + str(directory / "tmp"),
            ],
            cwd=ROOT,
            env=env,
            # The 7 November approval raises only the aggregate integration budget to 15 minutes.
            # Individual browser, database and I/O limits remain independently bounded.
            timeout=900,
        )
        (directory / "pytest.log").write_text(
            result.stdout.replace(password, "[REDACTED]")
        )
        evidence_valid = True
        try:
            cases = list(ElementTree.parse(directory / "junit.xml").iter("testcase"))
        except (OSError, ParseError, DefusedXmlException):
            cases, evidence_valid = [], False
        counts = {
            kind: sum(case.find(kind) is not None for case in cases)
            for kind in ("failure", "error", "skipped")
        }
        passed = (
            result.returncode == 0
            and not result.timed_out
            and evidence_valid
            and bool(cases)
            and not any(counts.values())
        )
        failing_tests = failing_test_identifiers(cases)
        summary = {
            "status": "pass" if passed else "fail",
            "failing_tests": failing_tests,
            "browser_failure_locations": browser_failure_locations(cases),
            "tests": len(cases),
            **counts,
            "pytest_exit": result.returncode,
            "timed_out": result.timed_out,
            "valid_test_evidence": evidence_valid and bool(cases),
            "database": "disposable Docker PostgreSQL16",
            "persistent_database_used": False,
            "frontend_built_from_current_source": True,
            "browser_integration_included": True,
            "artifacts": str(directory.relative_to(PROJECT_ROOT)),
        }
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary))
        return 0 if passed else 1
    finally:
        try:
            # Scrub all owned disposable runtime credentials, including installer qualification DBs.
            disposable_credentials = {password}
            for state_path in (directory / "tmp").rglob("state.json"):
                try:
                    state = json.loads(state_path.read_text())
                    disposable_credentials.update(
                        value
                        for key, value in state.items()
                        if key in {"owner_password", "api_password", "worker_password"}
                        and isinstance(value, str)
                        and value
                    )
                except (OSError, ValueError, AttributeError):
                    continue
            # Short tracebacks plus exact redaction retain failures without connection arguments.
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in {".log", ".xml"}:
                    content = path.read_text(errors="replace")
                    for credential in disposable_credentials:
                        content = content.replace(credential, "[REDACTED]")
                    path.write_text(content)
        finally:
            # Report cleanup must never prevent removal of the container owned by this run.
            if created:
                subprocess.run(
                    ["docker", "stop", name], check=True, capture_output=True
                )


if __name__ == "__main__":
    raise SystemExit(main())
