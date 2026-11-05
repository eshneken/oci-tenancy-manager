"""Export the current executable prototype schemas without connecting to a database."""

import json
from pathlib import Path

from otm.organization.api import build_local_read_api
from otm.organization.contracts import Configuration, Intake
from otm.organization.local_web import build_local_web
from otm.organization.store import Store, schema_tables
from sqlalchemy import create_mock_engine


# Write current OpenAPI, input/configuration JSON schemas and prototype DDL without database
# I/O.
def main():
    destination = Path("docs/contracts")
    destination.mkdir(parents=True, exist_ok=True)
    store = Store("postgresql+psycopg://otm_dev@127.0.0.1/otm_contract")
    app = build_local_read_api(store, "contract", allow_local_prototype=True)
    (destination / "organization-openapi.json").write_text(
        json.dumps(app.openapi(), indent=2) + "\n"
    )
    local_app = build_local_web(store, "contract", allow_local_prototype=True)
    (destination / "organization-local-web-openapi.json").write_text(
        json.dumps(local_app.openapi(), indent=2) + "\n"
    )
    for name, model in (("intake", Intake), ("configuration", Configuration)):
        (destination / f"organization-{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2) + "\n"
        )
    statements = [
        "-- Generated local prototype table DDL; not a production migration.",
        "-- Store.initialize also infrastructure-services immutable-content and sealed-revision triggers.",
        'CREATE SCHEMA IF NOT EXISTS "otm_org";',
    ]

    # Collect dialect-compiled DDL from SQLAlchemy mock execution for the contract
    # artifact.
    def capture(statement, *_args, **_kwargs):
        statements.append(str(statement.compile(dialect=engine.dialect)).strip() + ";")

    engine = create_mock_engine("postgresql+psycopg://", capture)
    metadata, _tables = schema_tables("otm_org")
    metadata.create_all(engine)
    (destination / "organization-schema.sql").write_text("\n\n".join(statements) + "\n")
    store.engine.dispose()
    print("Exported organization OpenAPI, canonical input/configuration schemas and table DDL.")


if __name__ == "__main__":
    main()
