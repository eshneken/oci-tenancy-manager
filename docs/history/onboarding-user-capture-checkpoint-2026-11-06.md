# Permanent-user onboarding capture — 6 November 2026

[Implemented field map](../reference/tenancy-onboarding.md#permanent-user-capture--6-november-2026) ·
[Pending real OCI tests](../how-to/real-oci-test-manifest.md)

New create/import admissions use version 3 and record separate permanent automation and recovery
user identities after baseline/access checks, before temporary cleanup. Typed readback validates
workspace, organization, parent, child, domain, distinct OCI/SCIM identities and exclusion of the
bootstrap/activation users. Failed capture blocks retirement; retry appends evidence and completes
through the existing workflow. Completed-work redelivery preserves captured evidence.

Version 1/2 and absent-version accepted operations retain their original semantics. There is no
name-based adoption, guessed historical backfill or new credential material. The neutral lifecycle
contract and explicit simulator remain separate. Migration 0022 widens one existing step constraint;
it adds no table, column or privilege. The operation-step outcome and immutable audit event retain
the same typed capture. Existing ER relationships remain unchanged.

| Local qualification | Result |
| --- | --- |
| Focused onboarding, notification, responsibility and import regressions | Pass |
| Backend unit-only complete 129-source inventory | 1,419 pass; 8,661/9,019 lines, 96.0306% |
| Frontend unit-only complete 34-source inventory | 424 pass; 1,729/1,775 lines, 97.40% |
| Full disposable PostgreSQL/native worker/HTTPS Playwright regression | 1,729 pass; zero failures, errors or skips; no timeout |
| Capture PostgreSQL scenarios | Create/import evidence agreement, completed redelivery, legacy 1/2 continuation, capture failure and retry |
| Forward migration | Existing operation/audit/step data unchanged across 0021-to-head upgrade; installed runtime/browser regression passes |
| Generated public contracts | 73 schemas current; frontend build passes |
| Purpose comments, Ruff, links, publication, Gitleaks and Bandit | Pass |
| Python/npm advisory audits | Zero known vulnerabilities reported |
| Independent documentation, security and UI review | Pass; findings resolved before final qualification |

These are local simulator-backed results. They do not qualify actual OCI account creation/readback,
SDK failures, propagation, credential cleanup or full access health. Captured identities are immutable
onboarding provenance, not current binding/access-assignment heads. Presence reads, current-generation
publication, Required users UI, repair and credential custody remain later slices.

Saved review instances and their data were not changed. Once this revision is deliberately installed,
the normal local create/import flow shows **Record permanent user identities** in its simulated
checklist; no separate Access page is introduced. All live-only cases remain Pending in the manifest.
No repository push, PR, deployment, live OCI call or dependency addition accompanies this checkpoint.
