"""Synthetic census fixtures and isolated, explicitly enabled PostgreSQL test stores."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from otm.organization.contracts import Configuration, Envelope, Lob, Record, SourcePolicy
from otm.organization.store import Store
from sqlalchemy import text

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


# Build a validated two-LOB source policy fixture with optional trust-policy overrides.
def example_config(**policy_changes):
    policy = SourcePolicy(
        source_id="fixture",
        population_id="fixture-org",
        root_email="root@example.test",
        allow_metadata=True,
        authoritative=True,
        census_contract_confirmed=True,
        max_age_seconds=86400,
        administrator_recipients=("admin@example.test",),
    )
    policy = SourcePolicy.model_validate({**policy.model_dump(), **policy_changes})
    return Configuration(
        id=uuid4(),
        policy=policy,
        lobs=(
            Lob(
                id="one",
                label="LOB One",
                leader_email="one@example.test",
                designee_emails=("delegate@example.test",),
            ),
            Lob(id="two", label="LOB Two", leader_email="two@example.test"),
        ),
    )


# Return a complete deterministic census with two leaders, one designee and one engineer.
def example_records():
    return tuple(
        Record(source_record_id=key, full_name=name, email=address, manager_email=manager)
        for key, name, address, manager in (
            ("root", "Root", "root@example.test", None),
            ("one", "Leader One", "one@example.test", "root@example.test"),
            ("two", "Leader Two", "two@example.test", "root@example.test"),
            ("delegate", "Delegate", "delegate@example.test", "one@example.test"),
            ("engineer", "Engineer", "engineer@example.test", "one@example.test"),
        )
    )


# Build source metadata for a fixture snapshot with configurable capture and
# completeness.
def envelope(key="first", capture=NOW, completeness="complete"):
    return Envelope(
        source_id="fixture",
        population_id="fixture-org",
        external_snapshot_id=key,
        captured_at=capture,
        declared_completeness=completeness,
    )


# Publish fixture rows using an observation one minute after capture, unless rows are
# supplied.
def ingest(store, records=None, key="first", capture=NOW, completeness="complete"):
    return store.ingest(
        example_records() if records is None else records,
        envelope(key, capture, completeness),
        capture + timedelta(minutes=1),
    )


# Yield an initialized store in a unique disposable test schema.
#
# Skip without the explicit test URL. Cleanup drops only the generated schema and
# disposes the engine even when a test fails; the persistent demo schema is untouched.
@pytest.fixture
def store():
    url = os.environ.get("OTM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("run scripts/run_postgres_tests.py for PostgreSQL integration coverage")
    schema = "otm_test_" + uuid4().hex
    value = Store(url, schema)
    value.initialize()
    value.configure_initial(example_config())
    try:
        yield value
    finally:
        # Only this fixture's freshly generated schema in its disposable local database.
        with value.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        value.engine.dispose()
