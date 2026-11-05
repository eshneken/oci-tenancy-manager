"""Migration preservation and rollback against an isolated historical-schema fixture."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import NOW, envelope, example_records
from otm.organization.contracts import Record, Revision
from otm.organization.migration import migrate_legacy
from otm.organization.reconcile import prepare
from sqlalchemy import MetaData, select, text

pytestmark = pytest.mark.postgres


# Create two applied historical revisions and a receipt each in a disposable legacy
# schema.
def legacy_fixture(store):
    legacy = "otm_legacy_test_" + uuid4().hex
    ddl = (Path(__file__).parent / "fixtures/legacy_organization_schema.sql").read_text()
    ddl = ddl.replace('"otm_org"', f'"{legacy}"').replace("otm_org.", legacy + ".")
    with store.engine.begin() as connection:
        connection.execute(text(ddl))
        metadata = MetaData(schema=legacy)
        metadata.reflect(connection)
        tables = {table.name: table for table in metadata.tables.values()}
        config = store.configuration("fixture-org")
        connection.execute(
            tables["org_configuration"]
            .insert()
            .values(id=str(config.id), data=config.model_dump(mode="json"))
        )
        connection.execute(
            tables["org_population"]
            .insert()
            .values(id="fixture-org", configuration_id=str(config.id))
        )
        previous = None
        for index in range(2):
            rows = tuple(
                row.model_copy(update={"full_name": f"Engineer {index}"})
                if row.email == "engineer@example.test"
                else row
                for row in example_records()
            )
            # Punctuated email identities expose differences between PostgreSQL collation
            # and Python lexical ordering; migration must compare facts by identity.
            rows += tuple(
                Record(
                    source_record_id=key,
                    full_name=key,
                    email=address,
                    manager_email="one@example.test",
                )
                for key, address in (
                    ("punctuated", "a.b@example.test"),
                    ("unpunctuated", "ab@example.test"),
                )
            )
            incoming = envelope("legacy-" + str(index), NOW + timedelta(hours=index))
            candidate = prepare(rows, incoming, config, previous, incoming.captured_at)
            feed_id = uuid4()
            payload = {
                "envelope": incoming.model_dump(mode="json"),
                "records": [row.model_dump(mode="json") for row in rows],
            }
            connection.execute(
                tables["org_snapshot"]
                .insert()
                .values(
                    id=str(feed_id),
                    population_id="fixture-org",
                    source_id="fixture",
                    external_id=incoming.external_snapshot_id,
                    digest=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                    data=payload,
                )
            )
            revision = Revision(
                id=uuid4(),
                predecessor_id=previous.id if previous else None,
                configuration_id=config.id,
                snapshot_id=feed_id,
                population_id="fixture-org",
                published_at=incoming.captured_at,
                source_captured_at=incoming.captured_at,
                declared_completeness="complete",
                assessed_coverage=candidate.assessed_coverage,
                absence_eligible=candidate.absence_eligible,
                people=candidate.people,
            )
            connection.execute(
                tables["org_revision"]
                .insert()
                .values(
                    id=str(revision.id),
                    population_id="fixture-org",
                    predecessor_id=str(previous.id) if previous else None,
                    snapshot_id=str(feed_id),
                    configuration_id=str(config.id),
                    sealed=True,
                    data=revision.model_dump(mode="json", exclude={"people"}),
                )
            )
            people = {person.email: person for person in revision.people}
            if index == 0:
                connection.execute(
                    tables["org_person"].insert(),
                    [{"id": str(p.id), "email": p.email} for p in revision.people],
                )
            connection.execute(
                tables["org_state"].insert(),
                [
                    {
                        "revision_id": str(revision.id),
                        "person_id": str(p.id),
                        "email": p.email,
                        "manager_person_id": str(people[p.manager_email].id)
                        if p.manager_email
                        else None,
                        "data": p.model_dump(mode="json"),
                    }
                    for p in revision.people
                ],
            )
            connection.execute(
                tables["org_result"]
                .insert()
                .values(
                    snapshot_id=str(feed_id),
                    state="published",
                    revision_id=str(revision.id),
                    diagnostics=[],
                )
            )
            connection.execute(
                tables["org_receipt"]
                .insert()
                .values(
                    id=str(uuid4()),
                    snapshot_id=str(feed_id),
                    received_at=incoming.captured_at,
                    disposition="new",
                )
            )
            connection.execute(
                tables["org_event"]
                .insert()
                .values(
                    id=str(uuid4()),
                    revision_id=str(revision.id),
                    actor="service:fixture",
                    kind="organization_published",
                    at=incoming.captured_at,
                    data={"changes": [], "diagnostics": []},
                )
            )
            previous = revision
        connection.execute(tables["org_population"].update().values(head_id=str(previous.id)))
    return legacy, previous


# Copy two revisions exactly, retain source tables and return the same marker on rerun.
def test_migration_keeps_ids_source_history_and_original_schema(store):
    legacy, original = legacy_fixture(store)
    # The fixture store has only bootstrap settings; the migration target must be unpopulated.
    with store.engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{store.schema}" CASCADE'))
    try:
        summary = migrate_legacy(store, legacy)
        assert summary["people"] == 7 and summary["historical_applied_versions"] == 2
        migrated = store.head("fixture-org")
        assert migrated.model_dump(exclude={"people"}) == original.model_dump(exclude={"people"})
        assert {p.email: p for p in migrated.people} == {p.email: p for p in original.people}
        assert migrate_legacy(store, legacy) == summary
        with store.engine.connect() as connection:
            assert (
                connection.execute(text(f'SELECT count(*) FROM "{legacy}".org_state')).scalar_one()
                == 14
            )
            assert len(connection.execute(select(store.tables["feed"])).all()) == 2
            assert len(connection.execute(select(store.tables["version"])).all()) == 4
    finally:
        with store.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{legacy}" CASCADE'))


# Rollback all copied records when proposal reconstruction fails after historical state
# import.
def test_migration_failure_leaves_source_intact_and_target_unpopulated(store, monkeypatch):
    legacy, _ = legacy_fixture(store)
    with store.engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{store.schema}" CASCADE'))

    # Inject a failure after history copy to exercise migration transaction rollback.
    def fail(*_args, **_kwargs):
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(store, "_persist_version", fail)
    try:
        with pytest.raises(RuntimeError):
            migrate_legacy(store, legacy)
        with store.engine.connect() as connection:
            assert not connection.execute(select(store.tables["person"])).all()
            assert (
                connection.execute(text(f'SELECT count(*) FROM "{legacy}".org_person')).scalar_one()
                == 7
            )
    finally:
        with store.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{legacy}" CASCADE'))
