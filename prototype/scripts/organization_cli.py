"""Local inspection and scenario controls; no OCI calls, outbound messages or production SSO."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from otm.organization.contracts import Intake, PersonOverride
from otm.organization.csv_feed import csv_envelope, read_csv
from otm.organization.local_lab import LocalLab
from otm.organization.migration import migrate_legacy
from otm.organization.store import Store
from sqlalchemy import URL


# Read ignored private connection properties without printing the database credential.
def local_store(schema: str | None = None) -> Store:
    settings = json.loads(Path(".local-dev/postgres-connection.json").read_text())
    url = URL.create(
        "postgresql+psycopg",
        username=settings["user"],
        password=settings["password"],
        host=settings["host"],
        port=settings["port"],
        database=settings["database"],
    )
    return Store(url, schema or settings["schema"])


# Parse an optional aware scenario clock; repository validation rejects naive timestamps.
def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


# Run local current/proposed inspection, staged feed, correction or explicit legacy-copy
# commands.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema")
    parser.add_argument("--workspace", default="root-leader-sample")
    parser.add_argument("--at", help="Explicit ISO-8601 scenario clock with UTC offset")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show")
    show.add_argument(
        "view", choices=("current", "proposed", "reconciliation", "pending", "context")
    )
    intake = commands.add_parser(
        "feed", help="Ingest an employee CSV or canonical Intake JSON file"
    )
    intake.add_argument("file", type=Path)
    intake.add_argument("--stage-only", action="store_true")
    intake.add_argument(
        "--partial", action="store_true", help="CSV is partial; do not infer absences"
    )
    apply = commands.add_parser("apply")
    apply.add_argument("proposed_version_id", type=UUID)
    override = commands.add_parser("override")
    override.add_argument("email")
    override.add_argument("--manager")
    override.add_argument("--name")
    override.add_argument("--clear", action="store_true")
    override.add_argument("--actor", required=True)
    override.add_argument("--reason", required=True)
    override.add_argument("--expected-applied", type=UUID, required=True)
    override.add_argument("--expected-proposed", type=UUID, required=True)
    override.add_argument("--expected-configuration", type=UUID, required=True)
    acknowledgment = commands.add_parser("acknowledge")
    acknowledgment.add_argument("recommendation_id", type=UUID)
    acknowledgment.add_argument("--actor", required=True)
    acknowledgment.add_argument("--reason", required=True)
    acknowledgment.add_argument("--expected-applied", type=UUID, required=True)
    acknowledgment.add_argument("--expected-proposed", type=UUID, required=True)
    migration = commands.add_parser("migrate-legacy")
    migration.add_argument("--source-schema", default="otm_sample_demo")
    args = parser.parse_args()
    store = local_store(args.schema)
    now = parse_time(args.at)
    try:
        # The stable lab name follows the latest clean run, matching the browser. Historical
        # run IDs still work directly; older XLSX/synthetic workspaces keep their usual scope.
        if (
            args.workspace.startswith(("root-leader-csv-", "ui-test-"))
            and store.configuration(args.workspace).policy.source_id == "local-csv-demo"
        ):
            args.workspace = LocalLab(store, args.workspace).active()
        if args.command == "show":
            if args.view == "context":
                result = store.workspace_context(args.workspace)
            else:
                names = {
                    "current": "current_organization",
                    "proposed": "proposed_organization",
                    "reconciliation": "organization_reconciliation",
                    "pending": "pending_organization_reviews",
                }
                result = store.inspection_rows(names[args.view], args.workspace)
        elif args.command == "feed":
            if args.file.suffix.lower() == ".csv":
                records = read_csv(args.file)
                envelope, _digest = csv_envelope(
                    store,
                    args.workspace,
                    args.file.read_bytes(),
                    complete=not args.partial,
                    now=now or datetime.now(UTC),
                )
                value = Intake(envelope=envelope, records=records)
            else:
                value = Intake.model_validate_json(args.file.read_text())
            if value.envelope.population_id != args.workspace:
                raise ValueError("feed workspace does not match selected workspace")
            if args.stage_only:
                feed_id, matching = store.register(
                    value.envelope, value.records, now or datetime.now(UTC)
                )
                if not matching:
                    raise ValueError("source identity was already used for different content")
                result = store.stage(feed_id, now).model_dump(mode="json")
                if result["state"] == "duplicate":
                    if result["original_state"] == "published":
                        result["message"] = (
                            "This feed was already applied. --stage-only does not undo it. "
                            "Stage an unused later snapshot to inspect a new proposal."
                        )
                    else:
                        result["message"] = (
                            "This feed already has a terminal outcome; no new proposal was staged."
                        )
            else:
                result = store.ingest(value.records, value.envelope, now).model_dump(mode="json")
        elif args.command == "apply":
            if store.revision(args.proposed_version_id).population_id != args.workspace:
                raise ValueError("proposal does not belong to selected workspace")
            result = store.apply(args.proposed_version_id, now).model_dump(mode="json")
        elif args.command == "override":
            config = store.configuration(args.workspace)
            values = {
                key: value
                for key, value in (("full_name", args.name), ("manager_email", args.manager))
                if value
            }
            if args.clear and values or not args.clear and not values:
                raise ValueError("provide correction values or --clear")
            overrides = tuple(
                item for item in config.overrides if item.email != args.email.strip().lower()
            )
            if not args.clear:
                overrides += (
                    PersonOverride(
                        email=args.email, values=values, actor=args.actor, reason=args.reason
                    ),
                )
            updated = config.model_copy(update={"id": uuid4(), "overrides": overrides})
            result = store.update_configuration(
                updated,
                expected_version_id=args.expected_applied,
                expected_proposed_id=args.expected_proposed,
                expected_configuration_id=args.expected_configuration,
                actor=args.actor,
                reason=args.reason,
                observed_at=now,
            ).model_dump(mode="json")
        elif args.command == "acknowledge":
            store.acknowledge(
                args.recommendation_id,
                expected_version_id=args.expected_applied,
                expected_proposed_id=args.expected_proposed,
                actor=args.actor,
                reason=args.reason,
                observed_at=now,
            )
            result = {"status": "acknowledged; source issue remains under review"}
        else:
            if not args.schema:
                raise ValueError("explicit --schema target required for migration")
            result = migrate_legacy(store, args.source_schema)
        print(json.dumps(result, indent=2, default=str))
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
