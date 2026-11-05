"""Numeric financial ordering and privacy-safe CI failure diagnostics."""

from decimal import Decimal

import pytest
from test_tenancy_workflow_units import attach, person, registry

from otm.financial.contracts import CostView
from otm.tenancies.directory import tenancy_directory
from otm.tenancies.views import TenancyQuery

__all__ = ["registry"]


# Sort exact numbers before paging; stale/null values and equal amounts retain stable ordering.
@pytest.mark.parametrize("column", ["actual", "budget", "forecast"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_monetary_sorts_before_pagination_with_unknown_last(registry, column, direction):
    owner = person(registry)
    views = {}
    expected = []
    for index in range(13):
        row, _ = attach(registry, owner, name=f"Example child {index}")
        amount = ["2.0000", "100.0000", "10.0000", "2.0000"][index % 4]
        state = "stale" if index == 11 else "current"
        value = None if index == 12 else amount
        views[row["id"]] = CostView(state=state, **{column: value})
        if state == "current" and value is not None:
            expected.append((row["id"], Decimal(value)))
    expected.sort(key=lambda item: str(item[0]))
    expected.sort(key=lambda item: item[1], reverse=direction == "desc")
    known = [item[0] for item in expected]
    unknown = sorted(set(views) - set(known), key=str)
    first = tenancy_directory(
        registry, TenancyQuery(sort=column, direction=direction, page_size=10), views
    )
    second = tenancy_directory(
        registry, TenancyQuery(sort=column, direction=direction, page=2, page_size=10), views
    )
    assert first.total == 13 and first.pages == 2
    assert [item.id for item in (*first.items, *second.items)] == known + unknown


# CI retains source test identity; private parameters and raw errors cannot appear in it.
def test_ci_failure_names_exclude_parameters_and_raw_errors(monkeypatch):
    import importlib
    from pathlib import Path
    from xml.etree.ElementTree import fromstring

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    diagnostics = importlib.import_module("run_backend_postgres_tests").failing_test_identifiers
    cases = list(
        fromstring(
            '<testsuite><testcase classname="tests.test_example" '
            'name="test_expected[private-parameter]"><failure>private SQL and credential</failure>'
            '</testcase><testcase classname="private/path" name="not a source test">'
            '<error>private raw error</error></testcase><testcase classname="tests.test_example" '
            'name="test_pass"/></testsuite>'
        )
    )
    result = diagnostics(cases)
    assert result == [
        {"module": "tests.test_example", "test": "test_expected"},
        {"module": "unknown", "test": "unknown"},
    ]
    assert all("private" not in str(row) for row in result)
