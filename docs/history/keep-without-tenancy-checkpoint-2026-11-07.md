# Keep in organization without a tenancy — 7 November 2026

[Current workflow contract](../reference/organization-workflows.md#keep-in-organization-without-a-tenancy)

## Result

An administrator can close onboarding while retaining an included employee with zero tenancies.
The decision clears only setup_required, retains episode/identity/history and leaves later
create/import/shared membership available. It is not a permanent exemption, cloud workflow or
destructive decision. Independent mapping, role and absence work remains open as appropriate.
Ordinary subsequent feeds and name changes do not reopen the accepted setup episode.
The existing audit displays a friendly action label. No database migration or new state is added.

## Local qualification

- Backend: 1,639 unit tests pass, 9,341/9,716 lines (96.1404%), all 139 application modules.
- Frontend: 469 unit tests pass, 1,814/1,863 lines (97.36%), all 36 application modules.
- Disposable PostgreSQL/native worker/SMTP/HTTPS Playwright: all 378 pass in 434.191 seconds;
  zero failures, errors or skips, with no aggregate timeout.
- PostgreSQL tests prove persistence, exact replay, independent mapping reviews, repeated/name
  feeds and later provisionability. Native UI proves normal-directory visibility, no cloud job,
  repeated upload without another setup review and later provisioning choices. Unit guards reject
  absent/exempt/pending/associated/unrelated-review targets and already accepted episodes.
- Independent documentation, security and UI/UX reviews pass. Fresh 1280/390/320-pixel dialog
  frames were inspected privately; no remaining responsive or alignment issue.
- Ruff, above-declaration comments, generated contracts, design-shape checks, documentation links,
  publication/credential scanners, Bandit and both dependency audits pass.

## Saved preview

Main 8443 was updated with matching API/worker and immutable frontend assets after a private
custom-format backup. Exact count/content fingerprints for all 29 preexisting public tables
match across installation. No live employee row was repaired or test feed imported. Main health,
SPA deep links, asset bytes and unauthenticated API refusal pass. Parallel 8444 remains unchanged
with its previous asset fingerprint. This is local qualification, not a GitHub push/merge or
cloud deployment; this metadata-only action needs no additional live OCI call qualification.

## Try it

Reload main Atlas, open Organization drift and review a current new employee with no association
or pending operation. Choose **Keep in organization without a tenancy**, then **Keep in organization**.
The receipt is **Decision saved**, the setup review closes and the employee stays in Organization.
A later ordinary upload does not reopen that review. Open the employee record to provision later.
