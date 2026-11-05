"""Run backend unit tests and enforce the real, complete-source 95% line-coverage gate."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

ROOT = Path(__file__).resolve().parents[1]
MINIMUM_PERCENT = 95


# Validate complete, exclusion-free source accounting before comparing raw line counts.
def coverage_result(report: dict, expected_files: set[str]) -> dict:
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise ValueError("Coverage report must contain a source-file map")
    files = report["files"]
    if not expected_files or set(files) != expected_files:
        raise ValueError("Coverage must contain every backend module, including unimported files")
    covered = statements = 0
    for entry in files.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("summary"), dict):
            raise ValueError("Coverage file summary must be an object")
        summary = entry["summary"]
        values = [summary.get(key) for key in ("covered_lines", "num_statements", "excluded_lines")]
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Coverage report has invalid raw counts")
        seen, total, excluded = values
        if seen > total or excluded:
            raise ValueError("Coverage cannot omit first-party lines or invent covered lines")
        covered += seen
        statements += total
    totals = report.get("totals", {})
    if not isinstance(totals, dict) or any(
        type(totals.get(key)) is not int
        for key in ("covered_lines", "num_statements", "excluded_lines")
    ):
        raise ValueError("Coverage totals must contain integer counts")
    if (
        not statements
        or totals.get("covered_lines") != covered
        or totals.get("num_statements") != statements
        or totals.get("excluded_lines") != 0
    ):
        raise ValueError("Coverage totals must match all source files")
    # Integer arithmetic enforces 94.99 < 95; rounded display and branch totals cannot bypass it.
    passed = covered * 100 >= statements * MINIMUM_PERCENT
    return {
        "pass": passed,
        "covered_lines": covered,
        "statements": statements,
        "line_percent": round(100 * covered / statements, 4),
        "required_line_percent": MINIMUM_PERCENT,
        "source_files": len(files),
        "branch_coverage_is_diagnostic": True,
    }


# Require executed test cases and report failures, errors and skips for the gate.
def junit_result(path: Path) -> dict:
    cases = list(ElementTree.parse(path).iter("testcase"))
    if not cases:
        raise ValueError("Unit test collection was empty")
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return {"tests": len(cases), "failed": failed, "errors": errors, "skipped": skipped}


# Write isolated unit evidence and fail on test failure, invalid reports or low coverage.
def main(project: Path | None = None, source_directory: str = "src/otm") -> int:
    project = (project or ROOT / "backend").resolve()
    source = project / source_directory
    if not source.is_dir():
        raise ValueError("Application source directory is missing")
    artifact_root = project / ".local-dev/quality"
    artifact_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="unit-", dir=artifact_root))
    report_path = directory / "coverage.json"
    junit_path = directory / "junit.xml"
    environment = {**os.environ, "COVERAGE_FILE": str(directory / ".coverage.unit")}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "not postgres",
        "--cov",
        "--cov-report=json:" + str(report_path),
        "--cov-config=" + str(project / "pyproject.toml"),
        "--junitxml=" + str(junit_path),
    ]
    with (directory / "pytest.log").open("w") as log:
        process = subprocess.run(
            command,
            cwd=project,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    summary = {"status": "fail", "pytest_exit_code": process.returncode}
    try:
        tests = junit_result(junit_path)
        report = json.loads(report_path.read_text())
        expected = {str(path.relative_to(project)) for path in source.rglob("*.py")}
        result = coverage_result(report, expected)
        summary.update(tests=tests, coverage=result)
        if process.returncode == 0 and not any(tests[k] for k in ("failed", "errors", "skipped")):
            summary["status"] = "pass" if result["pass"] else "fail"
    except (OSError, ValueError, TypeError, ParseError, DefusedXmlException) as error:
        summary["error"] = type(error).__name__ + ": invalid or missing unit evidence"
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({**summary, "artifacts": str(directory.relative_to(project))}, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
