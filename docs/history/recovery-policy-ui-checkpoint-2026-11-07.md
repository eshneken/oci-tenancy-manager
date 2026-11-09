# Recovery-policy UI checkpoint — 7 November 2026

Qualified local simulation; main saved preview published; real OCI remains unqualified.

[Current implementation/field boundaries](../reference/recovery-console-verification.md) ·
[Manual UI steps](../how-to/recovery-policy-ui-checkpoint.md) ·
[Selected design](../engineering-design/22-credential-security-lifecycles.md)

## Outcome

New configured create/import setup captures and validates the exact recovery-only console policy
before temporary access cleanup. Manual Refresh user data checks presence and recovery policy
independently. The Recovery card has separate MFA-exemption and approved-network-restriction states,
policy timestamps and an operation link. Inventory links policy drift/out-of-date observations to
the same record. Changed desired policy stales policy evidence without discarding compatible presence.
Legacy captures remain unverified; reads never backfill policy or repair objects.

Normalized source rules/CIDRs are private immutable setup evidence. Ordinary onboarding, required-user,
Operations and audit/CSV projections retain safe allowlists. No password retrieval or rotation action
is enabled by these results. Both API and actual queued worker recheck current desired policy, including
while setup waits; cached equality cannot authorize stale setup/capture/cleanup.

## Qualification

| Gate | Final result |
| --- | --- |
| Backend complete-source unit-only | 1829 passed, zero failed/errors/skipped; 9966/10358 lines =96.2155%, all145 modules |
| Frontend complete-source unit-only | 493 passed; 1864/1918 lines =97.18%, all38 modules |
| Complete disposable PostgreSQL/native-worker/SMTP/HTTPS Playwright | 402 passed, zero failures/errors/skips;604.137 seconds, within approved900-second aggregate budget |
| Static/contracts/privacy | Ruff, above-declaration comments,75 generated schemas, TypeScript/build, documentation links, publication guard and credential scan pass |
| Supply chain | Bandit clean; npm audit zero vulnerabilities; Python dependency audit no known vulnerabilities; no new dependency |
| Independent reviews | Documentation, security and actual create/import visuals pass;1280/768/390/320 widths |

Earlier build-rejected, interrupted and failed runs are incomplete/not qualifying. The first complete
attempt found JSONB nested-array decoding blocked setup plus an outdated browser expectation. Stored
evidence now uses JSON-mode validation with unchanged hash/scope/identity guards and a dedicated unit
round-trip regression. A focused diagnostic then isolated a freshness test that reused an expired
session; it now performs a real fresh MFA sign-in after advancing time. The final full402-case receipt
is fresh and includes every required scenario; diagnostic counts are not added to it. No assertions,
authentication guard, per-test timeout, skip check or95% coverage gate was weakened.

## Saved preview preservation

Only the main8443 instance was upgraded after qualification. Its API/worker use one matched immutable
frontend release. An owner-only PostgreSQL dump and settings backup precede update; exact before/after
contents of all29 preexisting public tables match, with no new tables or migration. Existing organization,
registry, sessions, audit and notification data remain preserved. No employee row repair, feed replay,
tenancy deletion or live OCI action was performed.

The previously supplied operational CIDRs were privately validated/rendered into the main local
settings. Other settings retain identical model values. Real ranges are absent from this document,
Git and test artifacts. This desired setting is not fleet enforcement. The main deep route, exact built
assets and unauthenticated401 boundary were checked after publication. Parallel8444's existing index
hash is unchanged. No hosted deployment/settings or repository publication was performed.

## Remaining work

Guarded recovery-policy repair/distribution, full user recreation, password Vault custody/disclosure
and original four-hour rotation,30-day automation-key retirement, operational policy-drift alerts,
installed daily scheduling and actual provider qualification remain subsequent work. The accepted
requirements are retained, not declared satisfied by this read-only checkpoint. See the
[real-OCI manifest](../how-to/real-oci-test-manifest.md#credential-security-lifecycles).
