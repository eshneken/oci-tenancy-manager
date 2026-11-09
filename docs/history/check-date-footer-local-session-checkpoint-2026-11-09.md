# Check-date footer and local session checkpoint — 9 November 2026

Required-user cards now collect assignment/presence/policy dates beneath all badges. Date-only UTC
links open each exact check operation; full instants remain in hover titles and time metadata.
Laptop footer fields share two columns, with aligned date values even when captions wrap; mobile
fields stack. Identity details remain optional. No API timestamp or freshness semantics changed.

The approved local session policy is bundled in this same checkpoint: 28,800-second idle and absolute
limits. Staging and production retain 1,800-second idle / 28,800-second absolute limits. Existing
issued session deadlines are preserved; a new sign-in receives the local eight-hour idle limit.

## Qualification

- Backend units: 1,865 passed; 10,125/10,518 lines (96.2635%), complete source across 147 modules.
- Frontend units: 501 passed; 1,871/1,926 lines (97.14%), complete source across 38 modules.
- Final full disposable PostgreSQL/native-worker/SMTP/HTTPS-Playwright suite: 411 passed,
  no failures/errors/skips. No persistent database was used for tests.
- Browser checks cover exact date destinations, UTC formatting, date/link alignment, responsive
  footer placement, preserved results and whole-page section spacing. Actual login SQL checks
  issued policy; cleanup fixtures explicitly keep old/hosted 30-minute policy and strict expiry tests.
- Independent documentation, security and final UI reviews passed. Reviewed create/import captures
  cover laptop/mobile layouts; missing/stale screenshots are explicitly render-only fixtures.
- Ruff, inline documentation, frontend build, documentation/index links, publication/credential
  checks and whitespace checks passed. No dependency changes were introduced.

Earlier failing runs were not qualification. The final run includes the wrapped-caption alignment
fix, explicit old-policy cleanup fixtures and updated accessible date-link selectors. No assertion,
individual timeout, coverage threshold or hosted merge gate was relaxed.

## Saved preview and settings preservation

The main local preview received matching qualified frontend/API/worker with verified private database
and configuration backups. All 29 preexisting public table contents, including issued sessions, were
preserved exactly; no new table or migration. The local settings edit was model-checked to change
only idle timeout before atomic replacement. Hosted settings and the parallel 8444 snapshot stayed
unchanged. Connection/password notes were not rewritten.

Publication checked the exact owned/running container and loopback port against saved state, rejected
symlinked paths and verified the complete copied asset hash manifest from the final passed build.
No Git commit/push, live OCI call, feed replay, user repair or credential operation occurred.

See the [screen guide](../reference/required-users-screen.md#compact-check-dates--9-november-2026),
[local session settings](../reference/application-settings.md#local-eight-hour-sessions--9-november-2026)
and [publication safeguards](../reference/local-application.md#saved-preview-publication-safeguards--9-november-2026).

## Recovery overview and matching header actions

A subsequent UI refinement places Recovery's Identity record, Presence and Permissions in one
three-column laptop row, with its two policy controls paired below. Cards now stack at 900px and
below so tablet status words remain intact; inner facts/footer fields still stack at 700px.
Automation, check semantics and the previously installed session policy are unchanged.

Manage overrides now occupies the Overrides header, matching Refresh costs in the neighboring
panel. Compact paired headers at 1001–1150px give both actions the same right-aligned second row.
Visual review caught tablet word fragmentation before publication; the final browser regression
checks actual text-line ranges, header action centers/right insets and existing section gaps.

Fresh qualification passed: 1,865 backend units (96.2635% complete-source line coverage), 501 frontend
units (97.14%) and the complete 411-case disposable PostgreSQL/native-worker/SMTP/Playwright gate,
with no failures/errors/skips. Independent documentation, security and final UI reviews passed;
create/import and override editor/preview captures were reviewed across laptop/mobile widths.
Modal focus, scrolling and action reachability were exercised by the browser interaction tests.

The main preview received matching guarded frontend/API/worker snapshots with a verified database
backup and exact preservation of all 29 preexisting public tables. Application settings were
verified byte-for-byte unchanged; the local eight-hour policy remains installed. Parallel 8444
stayed unchanged. No new table, migration, live OCI action, credential operation or Git publication.
