# Explicit former-owner disposition — 7 November 2026

[Current workflow contract](../reference/organization-workflows.md) ·
[Domain flows](../engineering-design/01-domain-and-journeys.md) ·
[Live qualification manifest](../how-to/real-oci-test-manifest.md)

## Result

Shared-tenancy ownership transfer requires an explicit choice: keep the former owner as a
member, preserving the same user, compartment and existing permissions; or remove their recorded
personal identity and group memberships through the transfer operation. Individual tenancies
support removal only. The replacement owner's access must verify before requested removal;
registry publication waits for replacement and requested removal verification. Partial or unknown
effects retain the reservation and current registry owner pending reconciliation, never false success.
Legacy frozen transfers with no disposition retain their original mapping-only behavior.

Removal displays the exact recorded user, explicit danger consent and default-closed manual
cleanup guidance. Administrators coordinate resource preservation/removal, dedicated empty
compartment cleanup and additional manually created users/credentials with the current owner.
Shared/system resources and service/automation/recovery accounts must be preserved. Unknown
resource scope stays visible. OTM does not automatically discover/delete resources, compartments
or additional accounts or claim their manual cleanup is complete. Keep is neutral and explicitly
states retained administrator permissions. Standalone transfer/removal never offboards a person.
Offboarding plans use the same explicit disposition; omitted new offboard choices default to removal.

Existing contracts, frozen operation fields, membership rows, removal step receipts and managed
identity bindings carry this behavior. No new table, migration, child coordinator or live-provider
implementation is introduced. Worker UPDATE privileges add only the existing membership role column.

## Qualification

- Complete backend unit gate: 1,652 passed; 9,397/9,774 lines (96.1428%), all 139 application modules.
- Complete frontend unit gate: 484 passed; 1,853/1,906 lines (97.21%), all 38 application modules.
- Full disposable PostgreSQL/native HTTPS Playwright integration suite: 385 passed, zero failures,
  errors or skips; no overall timeout. Current source built for the browser tests.
- Coverage includes shared keep/remove, existing recipient binding preservation, missing/shared
  identity rejection, protected managed identities, stale previews, changed request replays,
  recipient binding changes, exact removal evidence, partial failures, absent-owner offboarding,
  individual-only removal and legacy frozen-intent compatibility. UI cases cover unchecked and
  programmatic submission, consent reset, retained permissions and cleanup disclosures.
- Independent documentation, security and UI/UX reviews pass. Fresh desktop/390/320 captures
  verify neutral/danger flows and readable expanded cleanup panels with contained scrolling.
- Ruff with the repository CI configuration, purpose comments, generated contracts, documentation,
  publication/secret checks, Bandit and dependency audits pass. No quality gate was relaxed.

## Saved preview and remaining qualification

Main Atlas on 8443 has matching API/worker and immutable built frontend after a private backup.
All 29 preexisting public tables retain exact counts/content hashes; no new tables. Health,
SPA links, frontend asset bytes and unauthenticated API refusal pass. Parallel 8444 remains
healthy with its original frontend fingerprint. No live row repair, test feed, destructive replay,
GitHub push or hosted CI result is claimed.

Real OCI identity replacement, permission preservation, exact group/user deletion, protected
account rejection and failure ordering remain pending in the live test manifest. Simulator
success is not evidence that OCI grants, credentials or resources changed.

To inspect locally, reload Atlas, open a shared tenancy and transfer ownership. Choose Keep to
review the neutral retained-access flow, or Remove to inspect exact-user consent and manual
cleanup help. These local operations are simulated; use disposable test records for mutations.
