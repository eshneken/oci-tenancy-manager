"""Launch the isolated laptop dashboard without importing a feed or modifying older labs."""

import argparse
import os
from pathlib import Path
from uuid import uuid4

import uvicorn
from organization_cli import local_store
from otm.organization.contracts import Configuration, Lob, SourcePolicy
from otm.organization.local_web import build_local_web
from sqlalchemy.exc import NoResultFound


# Declare the local CSV scenario contract and the six user-confirmed LOB mappings.
#
# Full uploads simulate an authoritative census with receipt time as scenario time. This
# enables absence demonstrations, not proof of production source authority/freshness. Organization leader
# is the configured boundary and intentionally has no employee row in this export.
def demo_configuration(workspace: str) -> Configuration:
    return Configuration(
        id=uuid4(),
        policy=SourcePolicy(
            source_id="local-csv-demo",
            population_id=workspace,
            root_email="example-ebc12eb0@example.test",
            allow_metadata=True,
            authoritative=True,
            census_contract_confirmed=True,
            required_root_profile=False,
            max_age_seconds=86400,
            administrator_recipients=("local-demo-admin@example.test",),
        ),
        lobs=(
            Lob(id="business-applications", label="Business Applications", leader_email="example-0b012040@example.test"),
            Lob(
                id="platform-engineering",
                label="Platform Engineering",
                leader_email="example-94504a07@example.test",
                designee_emails=("example-bb37ffc4@example.test", "example-29b5d6d6@example.test"),
            ),
            Lob(
                id="developer-experience",
                label="Developer Experience",
                leader_email="example-0e4a131d@example.test",
            ),
            Lob(id="partner-engineering", label="Partner Engineering", leader_email="example-265e8ea9@example.test"),
            Lob(id="data-services", label="Data Services", leader_email="example-f7a04f66@example.test"),
            Lob(id="infrastructure-services", label="Infrastructure Services", leader_email="example-0259f2a8@example.test"),
        ),
    )


# Reuse the persistent database in a separate workspace and bind the app only to loopback.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", default="root-leader-csv-lab")
    args = parser.parse_args()
    os.chdir(Path(__file__).resolve().parents[1])
    if not args.workspace.startswith(("root-leader-csv-", "ui-test-")):
        raise SystemExit(
            "Use a root-leader-csv-* or ui-test-* workspace to preserve existing JSON/XLSX labs."
        )
    store = local_store()
    try:
        store.initialize()
        try:
            store.configuration(args.workspace)
        except NoResultFound:
            store.configure_initial(demo_configuration(args.workspace))
        app = build_local_web(
            store, args.workspace, allow_local_prototype=True, allow_clean_workspace=True
        )
        print(f"OCI Tenancy Manager: http://127.0.0.1:{args.port} · {args.workspace}")
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
