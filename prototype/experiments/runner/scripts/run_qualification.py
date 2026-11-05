"""Run qualification only inside a fresh pinned, loopback Docker PostgreSQL container."""

import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from otm_runner_qualification.processes import run_python_group

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
IMAGE = "postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"


# Require real tests in isolated state, then remove only this owned container.
def main() -> int:
    artifacts = PROJECT_ROOT / ".local-dev/quality"
    artifacts.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="runner-qualification-", dir=artifacts))
    name = "otm-runner-test-" + uuid4().hex[:12]
    password = secrets.token_hex(24)
    # Explicit connection values plus removal of inherited libpq overrides protect the target.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.pop("PYTEST_ADDOPTS", None)
    env["POSTGRES_PASSWORD"] = password
    created = False
    try:
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
                "POSTGRES_USER=otm_qual",
                "--env",
                "POSTGRES_DB=otm_runner_test",
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
                ["docker", "exec", name, "pg_isready", "-U", "otm_qual"], capture_output=True
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
        env["OTM_RUNNER_TEST_DATABASE_URL"] = (
            f"postgresql+psycopg://otm_qual:{password}@127.0.0.1:{port}/otm_runner_test"
        )
        result = run_python_group(
            [
                "-m",
                "pytest",
                "-q",
                "--junitxml=" + str(directory / "junit.xml"),
                "--basetemp=" + str(directory / "tmp"),
            ],
            cwd=ROOT,
            env=env,
            timeout=180,
        )
        (directory / "pytest.log").write_text(result.stdout.replace(password, "[REDACTED]"))
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
        summary = {
            "status": "pass" if passed else "fail",
            "tests": len(cases),
            **counts,
            "pytest_exit": result.returncode,
            "timed_out": result.timed_out,
            "valid_test_evidence": evidence_valid and bool(cases),
            "database": "disposable Docker PostgreSQL16",
            "persistent_database_used": False,
            "artifacts": str(directory.relative_to(PROJECT_ROOT)),
        }
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary))
        return 0 if passed else 1
    finally:
        try:
            # Scrub this run's generated credential from retained child/report diagnostics too.
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in {".log", ".xml"}:
                    content = path.read_text(errors="replace")
                    if password in content:
                        path.write_text(content.replace(password, "[REDACTED]"))
        finally:
            # Report cleanup must never prevent removal of the container owned by this run.
            if created:
                subprocess.run(["docker", "stop", name], check=True, capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
