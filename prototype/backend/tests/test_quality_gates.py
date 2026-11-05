"""Quality-gate regressions: missing evidence and rounded percentages must not turn green."""

from copy import deepcopy
from xml.etree.ElementTree import ParseError

import pytest
from defusedxml.common import DefusedXmlException

from scripts.check_unit_coverage import coverage_result, junit_result

SOURCE = "backend/otm/example.py"


# Make one synthetic coverage artifact with consistent raw totals, not application coverage.
def report(covered=95, total=100):
    summary = {"covered_lines": covered, "num_statements": total, "excluded_lines": 0}
    return {"files": {SOURCE: {"summary": summary}}, "totals": deepcopy(summary)}


# Accept exactly 95%, reject rounded-up 94.99%, and reject untested source.
@pytest.mark.parametrize(
    "covered,total,expected", [(95, 100, True), (9499, 10000, False), (0, 100, False)]
)
def test_line_gate_uses_unrounded_counts(covered, total, expected):
    assert coverage_result(report(covered, total), {SOURCE})["pass"] is expected


# Keep branch coverage diagnostic rather than silently imposing a second 95% gate.
def test_branch_counts_do_not_change_line_threshold():
    data = report()
    data["totals"].update(covered_branches=1, num_branches=100)
    assert coverage_result(data, {SOURCE})["pass"]


# Reject incomplete scope, exclusions, inconsistent totals and malformed/empty counts.
@pytest.mark.parametrize("fault", ["missing", "extra", "exclusion", "totals", "boolean", "empty"])
def test_invalid_coverage_evidence_cannot_pass(fault):
    data = report()
    expected = {SOURCE}
    if fault == "missing":
        expected.add("backend/otm/unimported.py")
    elif fault == "extra":
        data["files"]["unrelated.py"] = deepcopy(data["files"][SOURCE])
    elif fault == "exclusion":
        data["files"][SOURCE]["summary"]["excluded_lines"] = 1
    elif fault == "totals":
        data["totals"]["covered_lines"] = 100
    elif fault == "boolean":
        data["files"][SOURCE]["summary"]["covered_lines"] = True
    else:
        data = report(0, 0)
    with pytest.raises(ValueError):
        coverage_result(data, expected)


# A generated empty test report is a failed gate even if pytest itself exits successfully.
def test_junit_requires_executed_cases(tmp_path):
    path = tmp_path / "empty.xml"
    path.write_text("<testsuites><testsuite /></testsuites>")
    with pytest.raises(ValueError, match="empty"):
        junit_result(path)


# Expose failed, errored and skipped selected cases to the required-job decision.
def test_junit_retains_failures_and_skips(tmp_path):
    path = tmp_path / "results.xml"
    path.write_text(
        '<testsuite><testcase name="ok"/><testcase name="bad"><failure/></testcase>'
        '<testcase name="error"><error/></testcase><testcase name="skip"><skipped/></testcase>'
        "</testsuite>"
    )
    assert junit_result(path) == {"tests": 4, "failed": 1, "errors": 1, "skipped": 1}


# Direct DDL callers cannot bypass identifier validation even without a Store wrapper.
@pytest.mark.parametrize(
    "schema", ['otm_test"; DROP SCHEMA public; --', "public", "otm_X", "otm_test.other"]
)
def test_ddl_guard_rejects_unsafe_identifiers_before_execute(schema):
    from otm.organization.schema import install_guards

    # Refuse every execution so rejection must happen at the local validation boundary.
    class NoDatabase:
        # Fail if malicious schema text reaches a database operation.
        def execute(self, *_args, **_kwargs):
            pytest.fail("Unsafe schema reached DDL execution")

    with pytest.raises(ValueError, match="invalid local schema"):
        install_guards(NoDatabase(), schema)


# Malformed or entity-bearing reports cannot be accepted as successful test evidence.
@pytest.mark.parametrize("content", ["<malformed", '<!DOCTYPE a [<!ENTITY x "no">]><a>&x;</a>'])
def test_junit_rejects_invalid_or_entity_xml(tmp_path, content):
    path = tmp_path / "untrusted.xml"
    path.write_text(content)
    with pytest.raises((ParseError, DefusedXmlException)):
        junit_result(path)
