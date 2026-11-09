# Required users identity-record screen — 6 November 2026

[Field and API map](../reference/required-users-screen.md) ·
[Local manual review](../how-to/required-users-runbook.md) ·
[Pending real OCI cases](../how-to/real-oci-test-manifest.md)

Tenancy detail now embeds two operational identity cards below Accountability & registration.
Automation and recovery identities show Recorded, Not recorded or Retired record independently.
Presence and permissions remain Not checked: registration is not evidence of account existence,
privileges, credentials or recovery readiness. Details retain exact domain/user OCIDs, SCIM ID,
source operation and recording/retirement times. Refresh reloads app records only.

The authenticated GET uses the principal's workspace and a repeatable read-only snapshot. It cannot
call providers, mutate bindings, create jobs or retrieve secrets. Invalid persisted references are
unavailable reads rather than empty inventories. Authorization loss hides previously cached facts
immediately; other failed refreshes label retained data. Historical onboarding is not backfilled.

Three closed DTOs expose 14 total fields, all mapped in the reference. Existing canonical bindings
supply persistence; no table, column, migration, credential head or fabricated health state is added.
Native browser coverage exercises pending-to-recorded create/import flows, keyboard disclosure,
source links and responsive layouts at 1280, 768, 390 and 320 pixels. Database cases cover installed
reads, foreign-workspace isolation, legacy unbound records, retirement and unchanged row counts.

| Final local qualification | Result |
| --- | --- |
| Backend unit-only complete source inventory | 1,467 pass; 8,794/9,152 lines, 96.0883%; 131 source files |
| Frontend unit-only complete source inventory | 433 pass; 1,743/1,789 lines, 97.42%; 35 source files |
| Disposable PostgreSQL/native worker/HTTPS Playwright gate | 1,801 pass; zero failures, errors or skips; no timeout |
| Focused database plus native create/import browser gate | Five pass |
| Public schemas, purpose comments, Ruff, links and design contracts | Pass; 74 schemas; 323 Python purpose-comment files |
| Privacy/secret/static scans and Python/npm dependency audits | Pass; no leaks or reported known vulnerabilities |
| Independent documentation, security and responsive UI reviews | Pass; final desktop/mobile create/import captures inspected |

The main saved local preview was backed up and upgraded as a coordinated API/worker/frontend
release. Every pre-existing row and column across its 26 tables was preserved, with the canonical
binding table added by the already-qualified migration. Frontend index and asset bytes match the
immutable per-instance snapshot; SPA deep links and the unauthenticated API boundary were checked.
Existing organization, administrator credentials, MFA and settings were retained. The separate
saved runbook instance remains on its previous revision. Private backups, preservation hashes and
browser captures stay local and are not publication artifacts.

This is a local source and preview checkpoint, not hosted CI or real OCI qualification. Actual
provider checks, readiness, repairs and recovery-password disclosure are not enabled by this view.
All new live-only cases remain Pending in the manifest. The existing large-bundle build warning
remains nonblocking; no dependency, budget, threshold or test gate was weakened.
