# OCI Tenancy Manager frontend

React, TypeScript, TanStack Query/Table and Vite implement the approved Field Console visual design.
The current application provides real local sign-in, session handling and administrator read/revoke
screens, [Audit History](../docs/reference/audit-history.md), [Operations list/detail](../docs/reference/operations.md) and explicit
[simulated inspection submission](../docs/reference/simulation.md). Tenancies, Organization,
configuration baselines/overrides/updates and read-only configuration checks are implemented locally;
OCI provider effects remain simulated.

Use the [local HTTPS guide](../docs/reference/local-application.md) to run the application. Bootstrap
factors belong only in your private terminal and authenticator. The development server does not
replace the guarded same-origin backend composition.

From the repository root:

```sh
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run contracts:check
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend exec -- playwright install chromium
uv run --project backend python scripts/run_backend_postgres_tests.py
```

`test` enforces at least 95% unit-only line coverage using raw counts and the complete `src/` inventory,
including unimported files. Empty, failed, skipped or missing required results fail. Evidence stays
in ignored `frontend/.local-dev/`. Generated types derive from backend schemas; update them with
`node frontend/generate-contracts.mjs` after exporting authoritative backend models.

The disposable database runner rebuilds the locked frontend, then runs backend, database and actual
HTTPS/Chromium integration together. It supplies private synthetic factors to the browser harness;
`test:ui` alone requires that isolated fixture environment. No user database or real administrator
is used. Traces/video are disabled; responsive screenshots contain only synthetic administrator
records and empty credential inputs. No hosted CI or publication clearance is implied.

The Activity & history menu separates Operations/Audit History from daily management and Application
settings/Administrators. Audit displays redacted immutable evidence, not actionable tasks or raw
payloads. Simulated issues explicitly require no action while preserving the recorded state. There
is no generic Retry or audit-edit control. Filtered Audit History CSV export is implemented;
contextual real-resource remediation remains separately qualified.
