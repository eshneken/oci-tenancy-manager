"""Synthetic demo safety: test helpers must not initialize private or remote databases."""

import sys

import pytest

from scripts import demo_synthetic_organization


# Reject absent, malformed, persistent, remote or alternate-engine URLs before DB access.
@pytest.mark.parametrize(
    "database_url",
    [
        None,
        "not-a-database-url",
        "postgresql+psycopg://otm_dev@127.0.0.1:1/otm_org_dev",
        "postgresql+psycopg://otm_dev@untrusted.example.test/otm_org_test",
        "sqlite:///otm_org_test",
        "postgresql+psycopg://otm_dev@127.0.0.1/otm_org_test?host=untrusted.example.test",
        "postgresql+psycopg://otm_dev@127.0.0.1/otm_org_test?dbname=otm_org_dev",
        "postgresql+psycopg://otm_dev@127.0.0.1/otm_org_test?service=synthetic-service",
    ],
)
def test_synthetic_demo_rejects_non_disposable_targets(monkeypatch, database_url):
    monkeypatch.setattr(sys, "argv", ["demo_synthetic_organization.py", "--postgres"])
    if database_url is None:
        monkeypatch.delenv("OTM_TEST_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("OTM_TEST_DATABASE_URL", database_url)

    # Fail the test if any rejected target reaches repository or database initialization.
    def unexpected_store(*_args, **_kwargs):
        pytest.fail("Rejected demo target reached the database repository")

    monkeypatch.setattr(demo_synthetic_organization, "Store", unexpected_store)
    with pytest.raises(SystemExit):
        demo_synthetic_organization.main()


# Reject driver override options before creating an engine or contacting any database.
@pytest.mark.parametrize(
    "query",
    ["host=untrusted.example.test", "dbname=otm_org_dev", "service=synthetic-service"],
)
def test_local_store_rejects_driver_target_overrides(monkeypatch, query):
    from otm.organization import store as store_module

    # Fail if an overridden local URL reaches engine construction.
    def unexpected_engine(*_args, **_kwargs):
        pytest.fail("Driver override reached engine construction")

    monkeypatch.setattr(store_module, "create_engine", unexpected_engine)
    url = "postgresql+psycopg://otm_dev@127.0.0.1/otm_org_test?" + query
    with pytest.raises(ValueError, match="connection query overrides"):
        store_module.Store(url)
