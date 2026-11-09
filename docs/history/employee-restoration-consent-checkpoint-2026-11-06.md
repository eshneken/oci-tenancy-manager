# Employee restoration and destructive consent — 6 November 2026

[Current workflow and field map](../reference/organization-workflows.md) ·
[Whole-tenancy deletion](../reference/tenancy-deletion.md) ·
[Manual review](../how-to/organization-mapping-runbook.md#return-and-destructive-consent-correction-review-after-installation)

## Result

Tenancy deletion, member removal and ownership transfer never offboard employees or settle
independent absence decisions, even for absent people losing their last association. Only
explicit offboarding of an actually absent employee changes directory status.

A fresh applied full/partial employee row restores an already-offboarded stable directory
identity and one setup episode as needed, without an intervening absence. Canonical row IDs
work after identity merge; original immutable anchor email is not the return key. References,
stale/replayed/staged/config-only inputs, exemptions, merged-away identities and pending work
remain protected. Source, audit, tenancy/member and provider history remain intact; no deleted
infrastructure, user access or credentials are recreated.

Five destructive person actions require explicit unchecked consent bound to the reviewed action,
people, targets, recipients, plan and preview. The browser and API enforce it independently.
Historical authenticated request replay precedes new-admission checks; omitted false preserves
old request digests. Whole-tenancy deletion keeps its existing confirmation.

## Qualification

| Lane | Final result |
| --- | --- |
| Complete backend unit coverage | 1,631 pass; 9,333/9,708 lines, 96.1372%, all 139 application modules. |
| Complete frontend unit coverage | 468 pass; 1,814/1,863 lines, 97.36%, all 36 application modules. |
| Disposable PostgreSQL/native worker/SMTP/HTTPS Playwright | All 377 pass; zero failures, errors or skips; 536.884 seconds, no timeout within the approved 600-second aggregate limit. |
| Source/contracts | Ruff, above-declaration comments across 341 Python files, all 75 generated schemas and frontend bindings pass. |
| Independent reviews | Documentation, security and responsive UI/UX pass; fresh 1280/390/320-pixel controls/deletion frames inspected privately. |
| Security/publication | Dependency advisory scans, Bandit, publication and credential scans pass. No runtime dependency or CI-gate weakening. |

Regressions cover fresh full/partial legacy restoration, duplicate setup suppression, staged/stale/
reference/config-only rejection, exempt/merged/pending controls, actual merged-survivor return,
explicit absence/offboarding, historical replay and shared multi-person cleanup. UI units cover unchecked clicks; native browser
checks prove Enter/script submission and direct API denial, reset consent when
context changes, and await each actual committed upload instead of an old success notice.
Only two existing setup columns were added to the worker's scoped UPDATE grant; actual runtime
roles verify those rights and deny identity/email/workspace mutation. No table or migration changed.
A test-only long-string lint correction was proved AST-identical, preserving its SQL and assertions.

## Saved preview publication

The notification checkpoint and this correction were published together to the main preview on
port 8443 after a verified private custom-format backup. Exact counts/content hashes for all
29 preexisting public tables match across installation; no business row was repaired, backfilled
or reset, and no destructive operation was resubmitted. Matching API, worker and immutable
frontend assets are healthy; deep links and unauthenticated API refusal were verified.
The parallel 8444 preview is unchanged and healthy, with its original served asset fingerprint.

Reload the main preview once. To exercise restoration, apply a genuinely newer fresh feed with
the affected person's employee row; this creates directory/onboarding state only. Retained
no-tenancy exemptions still require explicit re-onboarding. Live OCI/hosted delivery remain
Pending in the [manual manifest](../how-to/real-oci-test-manifest.md). This is local qualification,
not a GitHub push/merge, hosted CI run or cloud deployment.
