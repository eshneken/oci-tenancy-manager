# Automation assignment UI checkpoint — 9 November 2026

The main saved Atlas preview now exposes independently scoped simulated automation Administrators
group and domain administrator role checks through Refresh user data. User existence, assignments,
recovery policy and credential readiness remain distinct. See the
[implemented field map and local review](../reference/administrator-assignments.md).

## Qualification

- Backend unit-only: 1,863 passed, no failures/errors/skips; 10,125/10,518 lines (96.2635%), 147 modules.
- Frontend unit-only: 499 passed; 1,869/1,925 lines (97.09%), 38 modules.
- Final complete disposable PostgreSQL/native-worker/SMTP/HTTPS-Playwright gate: 411 passed,
  no failures/errors/skips. Tests used no persistent database and built the frontend from source.
- A separate focused 35-case diagnostic passed before the final complete gate. Those are not extra
  cases added to the 411 total. Earlier red runs were not qualification: older JSON round-trip tests
  needed JSON-mode parsing and a recovery-only badge assertion needed proper card scope.
- Contracts, production frontend build, Ruff, inline purpose comments, documentation links,
  publication/credential scans, Bandit and Python/npm vulnerability audits passed.
- Independent documentation, security and UI reviews passed. UI reviewed actual create/import
  captures at 1280/1024/768/390/320px, whole-page boundaries, and explicitly render-only missing/stale
  browser fixtures. Actual negative provider evidence was independently exercised in PostgreSQL.

## Preserved preview

Main 8443 received matching qualified frontend/API/worker with a private verified database backup.
Complete contents of all 29 preexisting public tables were preserved; no new tables or migrations.
The parallel 8444 frontend fingerprint remained unchanged. Existing local connection/password notes
were not rewritten. No feed replay, person repair, destructive-operation replay, live OCI call,
credential disclosure/rotation, Git commit/push or hosted deployment occurred.

Older immutable captures remain unbackfilled. Refresh may show Unable to verify for assignments
until a future qualified discovery/repair flow is available. This does not configure or repair access.
Real provider discovery/pagination/authorization qualification remains in the
[real OCI test manifest](../how-to/real-oci-test-manifest.md#automation-administrator-assignment-qualification).
Broader effective privileges, recovery-account assignments, API-key rotation, recovery-password
custody/disclosure/rotation and staging Kubernetes schedules remain separate work.
