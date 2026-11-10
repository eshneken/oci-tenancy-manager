# Automation signing-key inventory checkpoint — 9 November 2026

**Targeted local UI qualification and preserved main installation: PASS.** This is **not** a new
complete-integration, milestone or PR qualification. [Field map and local steps](../reference/automation-signing-keys.md).

## Scope

A separate observation-only Automation signing keys panel below Required users reuses Refresh user
data and optional sealed evidence. It shows public provider key IDs/fingerprints/original creation
time and dated age; no PEM/private key, selected signer, custody, rotation, alerts or expiry/lifecycle/
password enforcement is introduced. Complete known-empty differs from unavailable; per-row Unknown
age differs from failed inventory. Existing setups are not backfilled. Only new opted-in simulated
configure records stable original public metadata. No table, migration or setting is added.

Current age uses server read time; historical Operations age uses the key check’s own recorded time.
Future-at-capture timestamps stay Unknown until a fresh qualified read. The exact automation-keys
fragment is supported by bounded return navigation and focus. Thirty-day retirement remains future
work; observed age cannot prove key expiry, signer usability or compliance.

## Exact qualification evidence

- Backend complete-source units: **2147 passed**, zero failures/skips; **11581/12144 lines
  (95.364%)**, 165 source files. Artifact `.local-dev/quality/unit-kr9u4as5`.
- Final frontend units: **621 passed**, zero failures; **2055/2112 lines (97.30%)**, 43 source files.
- Targeted disposable PostgreSQL/native-worker/HTTPS/SMTP/Playwright artifact
  `.local-dev/quality/backend-postgres-c1cnpx1g`: **4 passed**, zero failures/errors/skips/timeouts.
  This comprises three key-inventory PostgreSQL create/import/legacy cases and one broad actual
  native simulation journey. It is not the full integration suite. No persistent database was used.
- A nonvisual link-kind/date accessible name and full UTC title were added **after** that native run.
  Final frontend units/build and review cover these edits; no later behavior/layout change occurred.
  No native rerun of that final accessibility wording is claimed.
  A later cosmetic `.signing-key-panel .presence-missing` rule reuses the existing red warning
  palette: final build and actual-CSS Chromium spot checks at1280/390/320px verified red versus amber
  and no overflow, with independent UI approval; these post-native ARIA/CSS checks do not claim a
  new full/native run and add no layout or JavaScript behavior change.
- Build, generated 80-schema consistency, Ruff and inline documentation across 393 Python files pass.
  Final independent source security and UI reviews pass, with responsive 1280/1024/768/390/320 coverage.

Initial targeted attempts failed a build assertion and encountered normal session expiry after a
29-day disposable clock jump; they also exposed an existing setup-polling race. Fixtures reauthenticate
through normal MFA, not a bypass. Onboarding now polls waiting/configuring machine work and stops
at human/terminal phases. Independent inventory age changes no longer clear password consent or
displayed value; composed regressions cover both. These fixes preserve real readiness invalidation.
A later targeted attempt failed because a screenshot scrolled between viewport-relative gap
measurements. Moving the screenshot after all geometry assertions preserved the exact 24px
assertions; it did not fix or change application layout. Final c1cnpx1g passes all four targeted
cases. Earlier failed attempts are not qualification and no counts are added to the final run.

No dependencies or lockfiles changed. Normal `npm ci` reported zero vulnerabilities; candidate
privacy scans passed 861 files with zero leaks. These checks do not establish live-provider behavior.

## Preserved main publication

Main 8443 received matching API/native worker and five final immutable assets. All 32 preexisting
public table contents were preserved exactly; no new table. Private backup catalog validation passed;
**an actual restore drill remains pending**. Application settings and database connection notes stayed
byte-for-byte unchanged. The retired 8444 instance was not recreated and no OCI call was made.
This records local publication only, not a Git/hosted release or production provider qualification.

## Local review and remaining limits

Reload main 8443, normally create/import a NEW simulated child and complete setup. Open Required
users → Refresh user data, then inspect the separate signing-key panel and its dated historical
operation. Older setups without metadata correctly remain unavailable; refresh cannot enroll keys.
Do not edit main clocks/custody or create artificial drift for a demonstration.

Actual OCI key identifiers, pagination, permission/time evidence and sign-in remain Pending in the
[live matrix](../how-to/real-oci-test-manifest.md#automation-signing-key-inventory-qualification). API-key custody,
rotation, 30-day enforcement, parent/hosting key authority and broader retirement workflows remain
separate work. No current private key material or new enforcement promise is established here.
