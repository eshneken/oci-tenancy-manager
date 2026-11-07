# Confirmed missing required-user notices — 7 November 2026

[Field-complete alert contract](../reference/required-user-alerts.md) ·
[Presence checks](../reference/user-presence-checks.md) ·
[Pending live qualification](../how-to/real-oci-test-manifest.md#pending-confirmed-missing-required-user-notices)

## Result

New manual checks retain independent automation/recovery incident state in existing sealed evidence.
Qualified Missing opens an incident and stages owner/manager/designee/administrator notices through
the existing email queue. Repeated Missing and Unknown keep the same incident; verified Present
closes it. A later relapse opens a new one. An Unknown peer cannot hide an independently qualified
Missing. Transport disabling preserves incident state without backfill on re-enable. Legacy accepted
checks remain non-alerting; optional absent fields preserve their original canonical bytes.

Frozen normalized original recipients retain all role reasons before staging redirection. Missing
contacts have visible routing issues, including the email-less local recovery administrator; its
existing explicit testing capture remains supported. Before submission, the original sealed Missing,
current incident, exact subject/connection/policy and at least one surviving frozen role/address must
still match. Still-present former roles, revoked/changed admin authority, replaced targets, resolved
incidents, changed routes/origin/transport cannot silently send or retarget an obsolete notice.

Operations shows purpose-specific notice headings, role evidence, original/test contacts, routing
issues and mail-server status. Cost failure headings are also distinguished from lifecycle failure.
The panel is read-only and never claims inbox receipt or identity repair. There are no new menus,
provider fault switches, tables, columns, migrations, OCI adapters or daily scheduling. Two incident
entries travel in existing check evidence JSON; outbox intents and queue deferral commit atomically.

## Final qualification

- Complete backend unit gate: 1,730 passed; 9,622/10,000 lines (96.22%), all 141 application modules.
- Complete frontend unit gate: 490 passed; 1,858/1,911 lines (97.22%), all 38 application modules.
- Complete disposable PostgreSQL/native HTTPS Playwright/Mailpit suite: 395 passed; zero failures,
  errors or skips. Final profiled run completed in 565.84 seconds under the unchanged 600-second
  aggregate limit; individual browser limits and all assertions remain unchanged.
- An earlier complete attempt exceeded the aggregate limit and is not valid completion evidence.
  A diagnostic group covering new alerts, real SMTP/browser capture and the final guard group passed
  all 19 cases. Full-suite profiling sampled no database lock waits, then completed all 395 cases.
  No deadline/coverage relaxation, assertion removal, test skipping or fixture consolidation was used.
  Aggregate runtime headroom remains limited; additional suite growth should prompt an explicit
  test-lane/runtime-budget decision rather than silently changing this gate.
- Coverage includes per-subject scope independence, repeated/partial/Unknown conditions,
  recovery/relapse, disabled delivery/no-backfill, legacy marker compatibility, late callbacks,
  recipient dedup, current-role/admin-authorization checks, termination, route/origin/transport,
  schema/evidence corruption and atomic check/outbox/enqueue rollback. Existing SMTP rejection and
  unknown-outcome protections remain unchanged and green.
- The loopback SMTP test verified actual test-mailbox-only acceptance, deduplicated originals and
  credential-free tenancy links. Playwright exercised the real restricted API/native worker and
  read-only notice/presence views. No real recipient or OCI resource was used.
- Independent documentation, security and UI reviews pass. Null administrator contact warnings and
  disabled-delivery incident preservation were corrected and regression-tested. Fresh native
  1280/390/320 frames were inspected; contact/status/role information stays readable and contained.
- Ruff, purpose comments, 75 generated schemas/client contracts, documentation/link checks,
  publication/credential scans, Bandit and both dependency advisory scans pass. No dependency added.

## Main preview and remaining work

Main 8443 received paired API/worker and immutable frontend after a private backup. All 29
preexisting public tables retain exact row counts/content hashes; no new table. Health, deep links,
asset-byte identity and unauthenticated API refusal pass. Parallel 8444 stays healthy with its
original asset fingerprint. No live feed, row repair, destructive replay, credential reset or
historical alert backfill was performed. This is a local checkpoint, not a hosted CI or live OCI claim.

Normal simulated producer facts are Present, so ordinary browsing/refreshing does not fabricate a
Missing condition to generate mail. Controlled Missing scenarios are automated in disposable
fixtures; the native screen renders are private local review evidence. Real OCI Missing versus
permission-denied behavior, hosted SMTP and daily admission remain Pending in the manual manifest.
