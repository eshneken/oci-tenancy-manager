"""Read the unchanged sample and report development-only candidate/publication facts."""

import argparse
import hashlib
import json
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from otm.organization.contracts import (
    Configuration,
    Envelope,
    Lob,
    SourcePolicy,
    SupplementalEdge,
)
from otm.organization.reconcile import prepare
from otm.organization.store import Store
from otm.organization.xlsx import read_xlsx
from sqlalchemy.exc import NoResultFound


# Read the supplied workbook without modification and emit a local reconciliation report.
#
# Uses explicitly non-authoritative, undated development policy. Optional PostgreSQL
# mode publishes to the guarded sample schema; notification rows remain intents only.
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres", action="store_true", help="Use OTM_TEST_DATABASE_URL")
    parser.add_argument("--output", type=Path, default=Path("evidence/sample-reconciliation.json"))
    args = parser.parse_args()
    source = Path("data/organizational_feed.xlsx")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style.*")
        records = read_xlsx(source)
    config = Configuration(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        policy=SourcePolicy(
            source_id="development-sample",
            population_id="root-leader-sample",
            root_email="example-ebc12eb0@example.test",
            allow_metadata=True,
            authoritative=False,
            census_contract_confirmed=False,
            max_age_seconds=86400,
            allow_undated_development_metadata=True,
            administrator_recipients=("local-demo-admin@example.test",),
        ),
        lobs=(
            Lob(id="business-applications", label="Business Applications", leader_email="example-0b012040@example.test"),
            Lob(
                id="developer-experience",
                label="Developer Experience",
                leader_email="example-0e4a131d@example.test",
            ),
            Lob(id="partner-engineering", label="Partner Engineering", leader_email="example-265e8ea9@example.test"),
            Lob(id="data-services", label="Data Services", leader_email="example-f7a04f66@example.test"),
            Lob(id="infrastructure-services", label="Infrastructure Services", leader_email="example-0259f2a8@example.test"),
            Lob(
                id="platform-engineering",
                label="Platform Engineering",
                leader_email="example-94504a07@example.test",
                designee_emails=("example-bb37ffc4@example.test", "example-29b5d6d6@example.test"),
            ),
        ),
        supplemental_edges=(
            SupplementalEdge(
                employee_email="example-265e8ea9@example.test",
                manager_email="example-ebc12eb0@example.test",
                provenance="user-provided Organization leader-1 LOB leader mapping; profile missing",
            ),
            SupplementalEdge(
                employee_email="example-0259f2a8@example.test",
                manager_email="example-ebc12eb0@example.test",
                provenance="user-provided Organization leader-1 LOB leader mapping; profile missing",
            ),
            SupplementalEdge(
                employee_email="example-9268edb7@example.test",
                manager_email="example-94504a07@example.test",
                provenance="user-confirmed supplemental relationship",
            ),
        ),
    )
    envelope = Envelope(
        source_id=config.policy.source_id,
        population_id=config.policy.population_id,
        external_snapshot_id="sample-" + digest,
        captured_at=None,
        declared_completeness="unconfirmed",
    )
    now = datetime.now(UTC)
    candidate = prepare(records, envelope, config, None, now)
    report = {
        "mode": "development-only; capture/authority unconfirmed; no outbound delivery",
        "input_sha256": digest,
        "input_rows": len(records),
        "effective_people": len(candidate.people),
        "missing_required_manager_profiles": sum(
            d.code == "MANAGER_PROFILE_MISSING" for d in candidate.diagnostics
        ),
        "resolved_employee_paths": sum(
            p.ancestry == "resolved" and p.profile == "employee" for p in candidate.people
        ),
        "assessed_coverage": candidate.assessed_coverage,
        "absence_eligible": candidate.absence_eligible,
        "absence_reviews": sum(p.absence_review for p in candidate.people),
        "supplemental_edges": "User-confirmed Example manager -> Example leader; user-provided Example leader and Example leader -> Organization leader",
        "configured_lobs": [lob.label for lob in config.lobs],
        "unmapped_lobs": "Six configured LOBs; other branches remain explicit.",
    }
    if args.postgres:
        url = os.environ.get("OTM_TEST_DATABASE_URL")
        if not url:
            raise SystemExit("OTM_TEST_DATABASE_URL is required for --postgres")
        store = Store(url, os.environ.get("OTM_DEMO_SCHEMA", "otm_sample_demo"))
        try:
            store.initialize()
            # Reusing the helper must preserve audited administrator configuration changes.
            # Bootstrap only an empty workspace. Stored configuration is authoritative thereafter.
            try:
                active_config = store.configuration(config.policy.population_id)
            except NoResultFound:
                store.configure_initial(config)
                active_config = config
            if active_config.policy.source_id != envelope.source_id:
                raise ValueError("sample source no longer matches this workspace configuration")
            outcome = store.ingest(records, envelope, now, digest)
            report["database_outcome"] = outcome.model_dump(mode="json")
            applied = store.head(config.policy.population_id)
            if applied is None:
                raise ValueError("sample did not produce an applied organization")
            report["published_people"] = len(applied.people)
            report["configured_lobs"] = [lob.label for lob in active_config.lobs]
            report["resolved_employee_paths"] = sum(
                person.ancestry == "resolved" and person.profile == "employee"
                for person in applied.people
            )
        finally:
            store.engine.dispose()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "input_rows",
                    "missing_required_manager_profiles",
                    "assessed_coverage",
                    "absence_eligible",
                    "absence_reviews",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
