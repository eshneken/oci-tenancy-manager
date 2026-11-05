# Organization prototype

This is the preserved, runnable organization and tenancy-association lab for OCI Tenancy Manager.
It implements CSV intake, applied/proposed organization state, drift reviews, identity merges and
simulated tenancy associations. OCI lifecycle actions succeed locally without contacting OCI.
It is not the production application: local actor labels, reset controls and synchronous simulated
operations must not become production authorization or workflow shortcuts.

## Run locally

From the repository root, enter this directory once. Python 3.12+ and uv are required.
The persistent database must already be running; starting a database requires Docker.

```sh
cd prototype
uv sync --python 3.12
uv run python scripts/organization_web.py
```

Open [the local app](http://127.0.0.1:8765). Existing local workspaces are retained.
If the database needs starting, run `uv run python scripts/start_local_postgres.py` from this
same directory. The helper reuses the existing named container/volume and private connection file.
A previously configured local installation may retain a private `.local-dev` link to the existing
runtime directory. That link and its credentials are not distributed or required by synthetic tests.
Do not replace a saved installation's state with an empty directory.

For a CLI scenario, also run from this directory:

```sh
uv run python scripts/demo_synthetic_organization.py
# Inspect the CLI options before connecting a separately configured persistent lab.
uv run python scripts/organization_cli.py --help
```

Private feeds remain outside the published fixture inventory; the public example is the invented
`backend/tests/fixtures/synthetic_organization.csv`. Every UI upload is a new snapshot, including contents seen in an older
upload. Valid metadata applies automatically; actionable and informational drift have separate views.
The UI's Clean workspace control resets only its scoped lab while retaining history and LOB settings.

## Verification

```sh
uv run pytest -q -m 'not postgres'
uv run python scripts/run_postgres_tests.py -q
uv run ruff check backend scripts
uv run ruff format --check backend scripts
uv run python ../scripts/check_inline_docs.py
uv run python scripts/export_contracts.py
```

The PostgreSQL driver uses an isolated disposable Docker container, never the persistent lab.
It now uses [the synthetic242-profile fixture](backend/tests/fixtures/synthetic_organization.csv)
and `scripts/demo_synthetic_organization.py`; no private HR export or saved connection is needed.
The workbook regression creates its invented281-row XLSX in a temporary test directory.
Run the synthetic demonstration without a database using:

```sh
uv run python scripts/demo_synthetic_organization.py
```

The synthetic helper's optional `--postgres` is test-only: it requires an explicit loopback
`otm_org_test` URL and rejects all connection query overrides. The older real-data demonstration
and launcher remain local tools; their private configuration is not a publication-approved fixture.

A unit-only run cannot prove database behavior or the required application-wide 95% coverage gate.
The existing tests and domain logic are intended for reuse; production extraction must preserve
behavior while adding SSO, durable processing and real provider adapters.

## Lab documentation

- [Web lab and CSV setup](docs/organization-web-lab.md)
- [Current/proposed working model](docs/organization-working-model.md)
- [Ten-table ER diagram and descriptions](docs/organization-er-diagram.md)
- [Field reference](docs/organization-field-reference.md)
- [Exception workflows](docs/exception-workflows.md)
- [Tenancy associations and offboarding](docs/tenancy-associations.md)
- [DIY feed changes](docs/organization-diy-feed-changes.md)
- [Implemented contract](docs/organization-m1-contract.md)

[The application design](../docs/engineering-design/README.md) is the go-forward authority.
[The reuse map](../docs/history/design-finalization-2026-10-28.md#prototype-behavior-retained-in-the-application) identifies
which prototype decisions remain requirements and which local harness features are excluded.
