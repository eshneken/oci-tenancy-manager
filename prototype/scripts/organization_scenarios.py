"""Seed an isolated synthetic organization and generate feed files for pgAdmin walkthroughs."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from organization_cli import local_store
from otm.organization.contracts import Configuration, Envelope, Intake, Lob, Record, SourcePolicy


# Return a clearly fictional, complete five-person organization with two business
# branches.
def lab_records() -> tuple[Record, ...]:
    return tuple(
        Record(source_record_id=key, full_name=name, email=address, manager_email=manager)
        for key, name, address, manager in (
            ("root", "Synthetic Root", "root@example.test", None),
            ("one", "Synthetic Leader One", "one@example.test", "root@example.test"),
            ("two", "Synthetic Leader Two", "two@example.test", "root@example.test"),
            ("delegate", "Synthetic Designee", "delegate@example.test", "one@example.test"),
            ("engineer", "Synthetic Engineer", "engineer@example.test", "one@example.test"),
        )
    )


# Initialize the lab once and write ordered scenarios; never reset an already-used
# workspace.
def main() -> None:
    store = local_store()
    config = Configuration(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        policy=SourcePolicy(
            source_id="synthetic-lab",
            population_id="synthetic-lab",
            root_email="root@example.test",
            allow_metadata=True,
            authoritative=True,
            census_contract_confirmed=True,
            max_age_seconds=604800,
            administrator_recipients=("local-lab-admin@example.test",),
        ),
        lobs=(
            Lob(
                id="one",
                label="Synthetic LOB One",
                leader_email="one@example.test",
                designee_emails=("delegate@example.test",),
            ),
            Lob(id="two", label="Synthetic LOB Two", leader_email="two@example.test"),
        ),
    )
    directory = Path(".local-dev/scenarios")
    directory.mkdir(exist_ok=True)
    try:
        store.initialize()
        existing = store.engine.connect()
        try:
            from sqlalchemy import select

            initialized = existing.execute(
                select(store.tables["workspace"].c.id).where(
                    store.tables["workspace"].c.id == "synthetic-lab"
                )
            ).first()
        finally:
            existing.close()
        if initialized:
            print(
                "Synthetic lab already exists; its current state and scenario files were preserved."
            )
            return
        store.configure_initial(config)
        now = datetime.now(UTC)
        rows = lab_records()
        baseline = Envelope(
            source_id="synthetic-lab",
            population_id="synthetic-lab",
            external_snapshot_id="baseline-" + uuid4().hex,
            captured_at=now - timedelta(hours=1),
            declared_completeness="complete",
        )
        store.ingest(rows, baseline, now)
        rename = tuple(
            row.model_copy(update={"full_name": "Synthetic Engineer Renamed"})
            if row.email == "engineer@example.test"
            else row
            for row in rows
        )
        reorg = tuple(
            row.model_copy(update={"manager_email": "two@example.test"})
            if row.email == "engineer@example.test"
            else row
            for row in rename
        )
        absence = tuple(row for row in reorg if row.email != "engineer@example.test")
        partial = tuple(row for row in absence if row.email != "one@example.test")
        cases = [
            ("01-rename", rename, "complete"),
            ("02-reorg", reorg, "complete"),
            ("03-absence", absence, "complete"),
            ("04-partial-manager-gap", partial, "partial"),
            ("05-reappearance", reorg, "complete"),
        ]
        for index, (name, records, completeness) in enumerate(cases):
            incoming = Envelope(
                source_id="synthetic-lab",
                population_id="synthetic-lab",
                external_snapshot_id=name + "-" + uuid4().hex,
                captured_at=now - timedelta(minutes=50 - index * 10),
                declared_completeness=completeness,
            )
            (directory / (name + ".json")).write_text(
                Intake(envelope=incoming, records=records).model_dump_json(indent=2) + "\n"
            )
        print(
            json.dumps(
                {
                    "workspace": "synthetic-lab",
                    "scenario_directory": str(directory),
                    "scenarios": [name for name, _, _ in cases],
                    "no_OCI_or_notifications": True,
                },
                indent=2,
            )
        )
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
