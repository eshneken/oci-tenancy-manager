"""Exercise a synthetic full hierarchy without reading private feed files or local credentials."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from otm.organization.contracts import Configuration, Envelope, Lob, SourcePolicy
from otm.organization.csv_feed import read_csv
from otm.organization.reconcile import prepare
from otm.organization.store import Store
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, NoResultFound

BRANCHES = ("platform", "product", "research", "solutions", "operations", "partners")


# Provide invented routing under explicit development-only, non-authoritative policy.
def configuration() -> Configuration:
    return Configuration(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        policy=SourcePolicy(
            source_id="synthetic-fixture",
            population_id="synthetic-ci",
            root_email="org-root@example.test",
            allow_metadata=True,
            authoritative=False,
            census_contract_confirmed=False,
            allow_undated_development_metadata=True,
            max_age_seconds=86400,
            administrator_recipients=("admin@example.test",),
        ),
        lobs=tuple(
            Lob(id=branch, label=branch.title(), leader_email=f"leader-{branch}@example.test")
            for branch in BRANCHES
        ),
    )


# Reconcile invented data, optionally publish only to an explicitly supplied test database.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    source = (
        Path(__file__).resolve().parents[1] / "backend/tests/fixtures/synthetic_organization.csv"
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    records = read_csv(source)
    config = configuration()
    incoming = Envelope(
        source_id=config.policy.source_id,
        population_id=config.policy.population_id,
        external_snapshot_id="fixture-" + digest,
        captured_at=None,
        declared_completeness="complete",
    )
    now = datetime.now(UTC)
    candidate = prepare(records, incoming, config, None, now)
    if candidate.rejected or candidate.absence_eligible:
        raise RuntimeError("synthetic development data cannot establish source authority")
    if len(candidate.people) != 242 or any(
        p.ancestry not in {"root", "resolved"} for p in candidate.people
    ):
        raise RuntimeError("synthetic full hierarchy failed to resolve")
    report = {
        "synthetic_only": True,
        "input_rows": len(records),
        "rooted_people": len(candidate.people),
        "assessed_coverage": candidate.assessed_coverage,
        "absence_eligible": candidate.absence_eligible,
        "private_inputs_read": False,
        "outbound_notifications": 0,
    }
    if args.postgres:
        url = os.environ.get("OTM_TEST_DATABASE_URL")
        if not url:
            raise SystemExit("OTM_TEST_DATABASE_URL is required for --postgres")
        # Driver query options can override host/dbname/service after URL parsing; reject them.
        # The opt-in flag cannot redirect this helper into the persistent inspection database.
        try:
            target = make_url(url)
        except ArgumentError:
            raise SystemExit("Test database URL is invalid") from None
        if (
            target.drivername != "postgresql+psycopg"
            or target.host not in {"127.0.0.1", "localhost"}
            or target.database != "otm_org_test"
            or target.query
        ):
            raise SystemExit("Synthetic publication requires loopback otm_org_test PostgreSQL")
        # Never fall back to the saved persistent lab connection or its private organization.
        store = Store(url, "otm_synthetic_ci")
        try:
            store.initialize()
            try:
                stored = store.configuration(config.policy.population_id)
            except NoResultFound:
                store.configure_initial(config)
                stored = config
            if stored != config:
                raise RuntimeError("existing synthetic workspace has different configuration")
            result = store.ingest(records, incoming, now, digest)
            if result.state != "published":
                raise RuntimeError("synthetic fixture was not published")
            applied = store.head(config.policy.population_id)
            if applied is None or len(applied.people) != 242:
                raise RuntimeError("synthetic publication is incomplete")
            report["published_people"] = len(applied.people)
        finally:
            store.engine.dispose()
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError("synthetic fixture changed during reconciliation")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
