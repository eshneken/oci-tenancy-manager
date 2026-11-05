# Manual review: configuration drift visibility

3 November 2026 · Qualified and installed local implementation · Read-only local checks

[Runtime guide and field map](../reference/configuration-drift.md) ·
[Configuration behavior](../engineering-design/03-templates-and-drift.md)

## Choose the installation deliberately

Use a dedicated synthetic test installation for workflow review. The saved main instance is usually
on 8443 and Atlas Test on 8444, but a port is not proof that its data is disposable. Confirm the
installation/workspace before submitting anything. Preserve all existing data, baselines, accepted
pins, credentials and history. This runbook authorizes no reset, direct SQL edits, OCI action,
credential extraction or publication. Sign in privately with an existing enrolled administrator.

The API and its separately started foreground worker must both run. Follow the
[parallel-instance guide](parallel-local-instance.md) with the installation's explicit directory
for ordinary startup. Stable saved previews use their own qualified frontend snapshot; do not
replace it with an unqualified development build. There is no operator simulation CLI for changing
saved observations. Missing/different/unavailable/conflict fixtures belong only to the disposable
synthetic PostgreSQL/browser test harness.

## 1. Inspect both views before checking

Open Configuration → Configuration drift. Confirmed drift is the default tab and contains only
qualified current-context Missing/Different evidence, not unverified checks, older baseline age or
pending conflict reviews. An empty list must not claim all children are healthy. Open Checks to
see active children before their first check, with Not checked state and readable category labels.
Use search, allowed sorting, paging and row count controls. Counters refer to tenancies across the
full current scope, not just the filtered page. A tenancy can contribute to both confirmed drift
and Unable to verify when older confirmed evidence is retained after a failed latest attempt.

## 2. Run an explicit read-only check

For a synthetic active child with a fully verified local baseline/configuration, open its check
detail and choose Check now. Acceptance is queued and links to Operations; it is not proof of
matching state. The separate worker records results asynchronously. No page load/Refresh secretly
queues work. Check all tenancies uses current eligible nonbusy children; single-child busy requests
are refused rather than silently switched to another target.

After completion, review all four bundles: Policy statements, Quota statements, Monthly budget
and Tag defaults. The assigned baseline link opens its exact version. Full-list and budget overrides
are reflected in expected values; tags inherit. Publishing a new baseline alone must not become
drift or retarget this assignment. Expected and observed blocks render as text; check the UTC
attempt/evidence timestamps, retained-state message and operation link. A completed operation can
contain Unable to verify results; native/business completion is not universal healthy status.

## 3. Review controlled drift scenarios in disposable tests

These cases are provided by synthetic fixture setup in the disposable PostgreSQL/native-worker/
HTTPS-browser test harness. Do not reproduce them by editing saved databases or manually deleting
objects in OCI. This milestone exposes no simulation-helper command and no Repair button.

- Matching: all four retained objects agree with the assigned effective content and original
  bindings. Complete current results can show Matching; object age and newer publications do not
  invent differences.
- Different: change one fixture's observed payload while retaining its exact bound identity. A
  complete four-category attempt appears in Confirmed drift and detail explains expected/observed.
- Missing: use an explicit complete authorized-absence envelope for an established retained binding.
  A missing JSON key, null/uninitialized state or failed request must instead be Unable to verify.
- Unavailable: deny/fail one category. The entire attempt cannot confirm or clear drift; no
  fabricated empty inventory or green status.
- Conflict: return a different object identity/category from the retained binding. Show binding
  conflict/check issue; never adopt the object by name or classify it as safe Missing.

## 4. Verify retention and context changes

With fixtures, first confirm Different/Missing against the assigned context. Then fail one read.
Earlier confirmed drift remains in Confirmed drift with its original evidence time and a retained
message; the newest check says Unable to verify. Other categories in that partial attempt cannot
clear the confirmation. A later fully complete current Matching attempt removes the current
confirmed projection while preserving all immutable history.

Accept an override/baseline update or change the relevant target context between acquisition and
execution. The old attempt must be superseded/unavailable, never current green. Resume/replay
deliveries and verify one sealed child record/outcome per operation/child, ordered by database
acquisition sequence. Advance the test clock past 24 hours: previous Matching must become out of
date, while confirmed drift retains its age. No real wait or scheduled infrastructure is needed.

With disposable fixtures, pause execution without changing the trusted policy. Earlier confirmed
drift must remain visible with unavailable capability, checks disabled and no green status. Change
the parent/policy instead: old evidence cannot confirm or green the new context. Also verify that
inventory/detail share the same confirmed-only category count, latest check state/time and stale flag;
these are read projections, not extra database columns.

## 5. Check the scope and mutation boundary

Open an exact child/category deep link from the list and verify heading focus, expected/observed
evidence and allowed Back route. Test keyboard access and narrow layouts. Refresh must preserve
truthful loading/error/prior-evidence behavior. An unknown submission response can retry the same
mounted request key; after a full reload review Operations before different work.

Automated assertions must separately prove that checks do not call ConfigurationFacade.apply or
change baseline/configuration heads, configuration_observation, membership or owner data. They may
append operation, native queue, step, audit and check evidence. Revoked/foreign/paused/wrong-target
cases remain guarded. Duplicate delivery and transaction failure must not duplicate or half-publish
evidence. Do not infer database atomicity from stub-only unit tests.

Daily scheduling, repair, notifications, full required-policy rendering, separate tag bindings,
budget-alert inspection and real OCI authorization/completeness remain unqualified future work.
All source-unit, disposable PostgreSQL/native-worker, actual browser and independent review gates
pass. Both saved instances are upgraded to 0018 with private 0600 backups, unchanged-old-data
fingerprints across all 18 pre-existing tables and matching qualified frontend snapshots. There
are 19 current tables; the 20-column baseline table, accepted pins, overrides and history are
preserved. No reset, backfill, live OCI call or publication occurred. Reload an open saved-preview
page once to load the qualified interface; the API and its worker serve the matching build.


Final local qualification and installation receipt (private historical evidence; not distributed).


## Daily scheduling stays deferred

Accepted 5 November 2026: do not create a local drift-detection CronJob or simulator/demo controls
for this review. Continue using the real explicit check action and disposable test-clock fixtures
for freshness assertions. Actual daily authorized read-only admission through the existing worker
will be qualified with staging/Kubernetes deployment, including missed runs and overlap/restarts.
A 24-hour stale label does not establish a running schedule. Session-cleanup jobs are separate.


## Freshness and confirmed-drift regression review: 5 November 2026

Refinement validation pending. Use only disposable fixtures and their controlled clock for these
cases; do not change saved observation rows or create a local scheduler/simulation helper.

1. Start with a complete Matching check. At exactly 24 hours it is still fresh. At 24 hours plus one
   microsecond, and at 35 hours, show Check out of date with zero confirmed categories. Do not show
   Not checked or claim configuration drift solely because time passed. The Stale filter matches;
   Matching and Not checked exclude that row. After the clock exceeds session lifetime, sign in
   again with real MFA before making protected requests; do not bypass authentication for the test.
2. Confirm a real fixture Missing/Different category with a complete four-category result. Let it
   age, then fail or queue a recheck. Its confirmed count remains visible alongside Check out of
   date and Unable to verify/Checking. Both drifted and stale filters can match it. The independent
   counters may count this child more than once; never add them into a claimed unique total.
3. Compare inventory, tenancy detail, Checks and check detail. They use the same named status and
   confirmed category count. Inventory omits a fresh Matching-only message; detail can show it.
   Unknown/unseen status may have an evidence link without inventing a drift-count link.
4. Recheck through the real API/native worker and wait for actual terminal completion. A complete
   current result refreshes inventory/detail, directory counters/filter membership and child check
   detail without a manual reload. Cover a fast fleet result disappearing from Confirmed drift and
   an externally started check finishing while another view is open, including cached child detail.
   Matching clears retained differences only after complete current evidence; failed/partial reads
   retain them and never reset freshness by acceptance alone.

These tests refine read projections and messaging only. The current check/summary states, SQL
schema and immutable evidence remain unchanged; stale is only an additional query-filter alias.
Daily drift admission/worker qualification remains deferred to staging/Kubernetes.


5 November freshness validation (private historical evidence; not distributed)
records passing unit, PostgreSQL, native-worker/browser and review gates. Both saved local instances
have the same qualified build and unchanged data. Manual check actions remain available; the daily
drift-detection CronJob waits for staging/Kubernetes deployment.
