# Manual required-user presence checks — 6 November 2026

[Field, authority and storage reference](../reference/user-presence-checks.md) ·
[Required users display map](../reference/required-users-screen.md) ·
[Local review runbook](../how-to/required-users-runbook.md) ·
[Pending real OCI cases](../how-to/real-oci-test-manifest.md)

Manual Check now is qualified locally through the authenticated API, durable native queue/worker,
PostgreSQL and actual HTTPS browser flow. Fresh create/import onboarding retains exact domain/user
bindings and one selected simulated connection; the check independently records each subject's
existence and observation time. The selected adapter restores authenticated onboarding producer
fixtures. Present is a simulator result, not live OCI verification or usable access. Permissions
remains Not checked on both cards. Historical unbound/unconfigured children cannot check; no
startup, GET, redelivery or upgrade backfills identities/connections/results.

## Separate complete test lanes

| Required result | Final evidence |
| --- | --- |
| Backend unit-only complete 138-source inventory | 1,556 pass; 9,228/9,597 lines, 96.155048% (reported 96.155%); no integration execution contributes to coverage. |
| PostgreSQL/native worker/HTTPS Playwright | All 351 pass; zero failures, errors or skips; valid JUnit; no timeout; 429.457 seconds within the approved 600-second aggregate limit. |
| Complete backend partition | 1,556 non-postgres units plus 351 postgres integration cases = 1,907 distinct backend tests; neither lane substitutes for the other. |
| Frontend unit-only complete 35-source inventory | 446 pass; 1,770/1,816 lines (97.466960%; report displays 97.46%); measured separately from backend/browser execution. |
| Focused database and native browser checks | Five focused PostgreSQL cases and five actual HTTPS/native/Playwright cases pass, including both fresh create and import checks. These are additional targeted runs, not extra distinct cases added to the 1,907 total. |
| Contracts and packaging | 75 public schemas current; wheel validates 27 frozen SQL digests, including migration 0025. |
| Source/documentation quality | Ruff and above-declaration purpose checks pass; 337 Python files. Documentation/index/link checks pass. |
| Security | Strict locked Python/npm advisory audits report zero known vulnerabilities; Bandit and Gitleaks pass. Independent security review passes. |
| UI review | Independent actual native UI review passes all eight create/import frames at 1280, 768, 390 and 320 pixels. |

Earlier runs that exceeded the old 420-second aggregate limit remain discarded as incomplete
evidence, even though no test failures had been observed. A postgres-only attempt reached 326 of
351 cases before that deadline; it was not a completed pass. The user explicitly approved a
600-second aggregate integration budget on 6 November 2026. Individual browser/database/I/O
bounds, every assertion, 95% complete-source unit-only coverage and all five required CI jobs remain
unchanged. The integration wrapper now selects all postgres marked tests instead of repeating the
separately required non-postgres unit lane. Final qualification uses the complete fresh 351-case
run above, not partial logs or overlapping sums.

## Main preview upgraded; parallel test preview preserved

The main local preview on port 8443 was deliberately upgraded to migration 0025 with a verified
private backup. Exact row counts and content hashes match for all 28 preexisting public tables.
The only new table is otm_user_presence_check, with all 14 documented columns and zero rows after
installation. The matched API, foreground worker and per-instance immutable frontend snapshot
are healthy. Deep-link reload and protected GET returning 401 without a session were verified.
No historical check, identity or connection was seeded/backfilled during this upgrade.

The parallel preview on port 8444 was left unchanged: configuration, private state, runtime and
served index hash match their prior values, and it remains healthy. Do not assume both previews
have the new Check now behavior. Reload the upgraded main preview once before following the local
runbook. This checkpoint does not authorize a reset or an unrelated environment upgrade.

## Retained boundaries

Migration 0025 adds one 14-column check table, bringing application metadata to 25 tables, and
extends existing operation/step/audit allowlists. The accepted context, database admission order,
attempt UUID and current grant/binding/connection/lifecycle/policy checks fence acquisition and
publication. Latest admitted terminal sequence governs the current projection; older callbacks
cannot replace a newer attempt. Per-account evidence is stale at 24 hours. The 30-second late-return
fence is a publication check, not an SDK/network cancellation timeout.

No live OCI calls, daily CronJob, notification, privilege assertion, repair, password disclosure or
credential fallback is added. All real-provider qualification remains Pending in the manifest;
staging/Kubernetes machine admission and scheduling are future work. This is local qualification
and a preserved-data preview upgrade, not a hosted CI result, repository push, PR merge or cloud
deployment claim. Historical receipts retain their own dates, limits and pending states.
