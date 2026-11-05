"""Synthetic production-domain fixtures independent of local databases and private exports."""

from datetime import UTC, datetime
from uuid import uuid4

from otm.organization.contracts import Configuration, Envelope, Lob, Record, SourcePolicy

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
