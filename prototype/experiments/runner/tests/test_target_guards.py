"""Reject unsafe test connection targets before any engine or pool can be created."""

import pytest
from otm_runner_qualification import harness


# Test-only reset/schema operations cannot use a remote, overridden or ambiguous target.
@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://otm_qual:example@remote.example.test:5432/otm_runner_test",
        "postgresql+psycopg://otm_qual:example@localhost:5432/other_database",
        "postgresql+psycopg://other_user:example@localhost:5432/otm_runner_test",
        "postgresql+psycopg://otm_qual:example@localhost:5432/otm_runner_test?host=remote.example.test",
        "postgresql+psycopg://otm_qual:example@localhost:5432/otm_runner_test?service=external",
        "postgresql+psycopg://otm_qual:example@localhost/otm_runner_test",
        "postgresql+psycopg://otm_qual@localhost:5432/otm_runner_test",
        "postgresql+psycopg2://otm_qual:example@localhost:5432/otm_runner_test",
    ],
)
def test_unsafe_target_is_rejected_before_engine_construction(monkeypatch, url):
    monkeypatch.setenv("OTM_RUNNER_TEST_DATABASE_URL", url)

    # Fail if target validation allows an engine to be created.
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unsafe test target reached engine construction")

    monkeypatch.setattr(harness, "create_engine", forbidden)
    with pytest.raises(ValueError, match="disposable loopback"):
        harness.engine_for_test()


# A required integration test cannot silently fall back to the laptop database.
def test_missing_test_target_is_a_failure_instead_of_skip_or_saved_connection(monkeypatch):
    monkeypatch.delenv("OTM_RUNNER_TEST_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="Run scripts/run_qualification"):
        harness.engine_for_test()
