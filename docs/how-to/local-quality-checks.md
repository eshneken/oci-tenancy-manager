# Local quality checks

Use the current application’s locked backend and frontend environments. The earlier organization
prototype and its separate diagnostic checks have been retired. Historical results remain in
[development progress](../history/development-progress.md); they do not qualify current source.

Follow the [required test policy](../engineering-test-plan.md#d53-required-test-and-merge-gates),
[backend guide](../../backend/README.md) and [frontend guide](../../frontend/README.md).
Run these commands from the repository root:

```sh
uv sync --project backend --locked
uv run --project backend python scripts/check_unit_coverage.py
uv run --project backend ruff check --config backend/pyproject.toml backend scripts
uv run --project backend python scripts/check_inline_docs.py
uv run --project backend python scripts/check_design_docs.py
uv run --project backend python scripts/export_backend_contracts.py --check
uv run --project backend python scripts/publication_guard.py
uv run --project backend python scripts/install_security_tools.py
uv run --project backend python scripts/check_secrets.py
```

The backend coverage checker includes unimported application modules and requires at least 95%
unit-only line coverage. The frontend has its own complete-source 95% unit-only gate. Database and
browser results cannot inflate either unit result; missing, skipped or failed required tests block
qualification. Current test counts belong in dated receipts rather than this command guide.

For the complete disposable PostgreSQL/native-worker/browser suite:

```sh
uv run --project backend python scripts/run_backend_postgres_tests.py
```

The runner owns a pinned disposable database and synthetic test data; it never uses the saved
application database. Docker, Node/npm and Playwright Chromium must be available. Run frontend
unit tests and browser tooling sequentially with this runner because its `npm ci` replaces shared
`frontend/node_modules`. Complete integration runs are required at milestone/PR checkpoints;
use affected units and focused cases during implementation under the approved local cadence.

## Docker cleanup

The PostgreSQL integration runner, container smoke test, Caddy check and Kubernetes schema
validator clean up their own Docker resources when they exit. Cleanup verifies the run's
ownership labels before removing a container or a built test image. Removing a test container
also removes its anonymous volumes. The Caddy check separately verifies its named volume and
network before removing them. Reports and logs stay in the local artifact directory.

Shared, digest-pinned upstream images remain available for subsequent runs. A Docker daemon
outage or a forced process kill can prevent cleanup. Inspect any leftovers on the Docker context
that ran the test and confirm their ownership before removing them. Atlas uses a separate
container and persistent database volume.

Security qualification also requires locked dependency audits, image checks and independent
review. See the [container guide](container-development.md),
[exact frontend advisory policy](../reference/frontend-security-exception.md) and
[security review policy](../security-review-policy.md). Raw diagnostics belong under ignored
`.local-dev/quality`; do not publish private inputs, credentials or scan artifacts. Local checks do
not substitute for all required hosted checks, protected PR-only merges or live OCI qualification.
