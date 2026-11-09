# Recovery assignments UI checkpoint — 9 November 2026

Local source and UI qualification pass. Real OCI remains unqualified.

The [current reference](../reference/administrator-assignments.md) defines the exact field map,
local UI steps and qualification limits. New create/import capture and manual refresh retain
independent recovery assignment facts beside automation assignments without adding tables.
Recovery keeps the three-field overview, compact Permissions summary and expanded group/role
results. Dated operation links stay in the two-column footer. Legacy captures are not backfilled.
Password custody/disclosure/rotation remain separate unimplemented work.

## Manual review

1. Create or import a new simulated tenancy and complete setup.
2. Refresh user data. Automation shows its two assignments; Recovery Permissions shows Assigned.
3. Expand Recovery Identity details: group and domain administrator role each show Verified in simulation.
4. Follow the assignment date into its operation, return, navigate away and reload: evidence persists.
5. Inspect at laptop and mobile widths; the overview stays readable and dates follow the badges.
6. Older tenancies without recovery source capture remain Unverified after refresh. No password
   action appears, and no live OCI grants or credentials are changed.


## Validation and review

- Backend unit-only: 1,871 pass; 10,129/10,521 lines, 96.2741% across all 147 source modules.
- Frontend unit-only: 509 pass; 1,878/1,932 lines, 97.20% across all 38 source modules.
- Final complete disposable PostgreSQL/native-worker/SMTP/Playwright suite: 418 pass,
  zero failures/errors/skips/timeouts. The prior 416/418 run is superseded: its two obsolete
  placeholder assertions were corrected to check the new summaries and individual results.
- Unit and PostgreSQL cases cover separate subjects, missing/disabled grants, incomplete/denied
  reads, wrong resources, cross-subject captures/result slots, legacy omission, persisted
  inventory/detail parity and late/current-context publication fences.
- Real create/import browser flows verify summary, keyboard disclosure, exact date links,
  retained reload and responsive structure at 1280/1024/768/390/320 pixels. Labelled negative
  browser fixtures check rendering only; independent PostgreSQL cases exercise actual negative
  provider facts. All captures use synthetic disposable data.
- Independent documentation/purpose-comment, security and UX source/visual reviews pass.
  Ruff, above-declaration documentation, schema/codegen consistency, link/index, publication,
  credential scan, runtime Bandit and dependency audits pass. No dependencies changed.

## Scope and Git checkpoint

This is a local simulator UI checkpoint, not live OCI or password-access qualification.
[Real OCI assignment cases](../how-to/real-oci-test-manifest.md#automation-administrator-assignment-qualification)
remain pending. The accumulated milestone's remote /ship review is separately blocked by its
2 MB diff ceiling; no passing release receipt, push or PR is claimed. Split the accumulated
work into smaller sequential reviewable PRs rather than weaken the review guard.


## Preserved main preview

The main HTTPS preview on 8443 is now upgraded with a private restorable database backup,
label/loopback-port/process ownership checks, exact immutable qualified asset manifest,
and matching API/worker. Complete contents of all 29 existing public tables are preserved.
No migration, settings rewrite, session-deadline recalculation, credential-note update or
organization reset occurred. SPA routes and the unauthenticated required-user boundary pass.
The parallel preview on 8444 was not upgraded; its frontend fingerprint is unchanged.
