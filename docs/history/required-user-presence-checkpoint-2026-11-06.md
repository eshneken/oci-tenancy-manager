# Required-user presence foundation — 6 November 2026

[Implemented field map and limits](../reference/required-user-presence.md) ·
[Approved access design](../engineering-design/12-access-health-and-repair.md)

This first access-health checkpoint adds an internal read-only presence capability. Neutral typed
contracts, an exact-result validation wrapper and a separate explicit simulator distinguish Present,
Missing and Unknown for one automation/recovery subject at a time. OCI/SCIM identifiers, domain,
assignment/binding/access generations, execution/credential references and capture timing are paired.
A failed/unqualified domain read cannot become Missing. Same-name users are not adopted; unexpected
observed identifiers fail closed. No signing/admin/console/MFA/recovery-readiness authority follows.

Current onboarding discovery retains bootstrap/domain metadata but does not yet retain the exact
permanent users. No identities are reconstructed or backfilled from names or verified step labels.
Next integration must capture authoritative permanent bindings, establish durable scoped heads and
recheck current authority/generations before and after reads. Only then can the Required users page
and native read-check operations be composed safely. Current references are transport provenance,
not new SQL foreign keys or proof of a live assignment.

| Local qualification | Result |
| --- | --- |
| Focused presence and clean-import boundaries | 78 pass: 72 new presence cases plus six existing boundary cases |
| Backend unit-only complete 128-source inventory | 1,390 pass; 8,610/8,968 lines, 96.008% |
| Frontend unit-only complete 34-source inventory | 424 pass; 1,729/1,775 lines, 97.40% |
| Full disposable PostgreSQL/native worker/HTTPS Playwright regression | 1,695 pass; zero failures, errors or skips; no timeout |
| Generated public contracts | Existing 73 schemas unchanged/current; frontend build passes |
| Purpose comments, Ruff, document links and design contract checks | Pass |
| Publication/Gitleaks/Bandit, Python/npm dependency audits | Pass; zero reported leaks or known dependency vulnerabilities |
| Independent documentation and security review | Pass; no UI change requires a new visual review |

The full database/browser suite is regression evidence, not execution of an uncomposed presence
capability. Its new semantics are unit-tested against independent provider fixtures and pairing
failures. No API route, database table/migration, scheduled or native job, identity repair, account
provisioning, secret retrieval or saved-review server change is introduced. No SDK dependency,
empty OCI adapter, provider registry, automatic fallback or product simulation control is added.
Real account-read qualification remains explicitly Pending in the
[manual checklist](../how-to/configuration-drift-runbook.md#pending-required-user-presence-qualification).
This local source checkpoint does not claim a complete access-health feature or hosted deployment.
