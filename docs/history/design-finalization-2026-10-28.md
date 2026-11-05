# Design finalization and prototype reuse

28 October 2026 | Review candidate; whole-package approval pending

[Application design hub](../engineering-design/README.md) · [Specification](../product/oci-tenancy-manager-spec.md) ·
[Screen authority](../ui-screen-authority.md) · [Prototype guide](../../prototype/README.md)

The [local HTTPS application](../reference/local-application.md) now implements real password/TOTP
sign-in, session/logout and administrator directory/revocation. This is an approved local development
subset, separate from the preserved organization prototype and the whole proposed tenancy product.
No local launch waives the finalization, publication or production qualification gates below.

## Finalization gates

1. Separate the runnable prototype and its lab artifacts from the application design. Preserve source,
   tests, local data and adopted business rules; repair launch paths and documentation links.
2. Reconcile specification, current journeys, screen fields, proposed ER models and acceptance contracts.
   Clearly distinguish implementation/pilot qualification from unresolved product decisions.
3. Obtain an independent **Astra** design review of this consolidated candidate. Record findings,
   severity, supporting paths, disposition and any required user decision. A different-model review
   is independent review assistance, not external security certification or live OCI qualification.
4. Address material findings and repeat the affected validations. Review again if a material design
   change invalidates the earlier assessment. Avoid adding machinery solely for unlikely edge cases.
5. Present the checkpoint for explicit user final approval. **No Git check-in, push, PR or repository
   publishing before that approval.** Earlier chapter approvals do not finalize the whole package.

The review result belongs beside this checklist as [the Astra review](astra-design-review-2026-10-28.md).
Astra has completed the review and rechecked both bounded corrections; see the report for disposition.
Whole-package user approval remains pending.

## Prototype behavior retained in the application

These are application requirements backed by executable prototype evidence, not optional lab ideas.
The prototype remains intact for demonstrations and regression characterization during extraction.

| Retained behavior | Prototype source / evidence | Application design authority |
|---|---|---|
| Current/proposed organization, immutable source evidence, coherent publication and automatic valid metadata | [Working model](../../prototype/docs/organization-working-model.md), [contracts](../../prototype/backend/otm/organization/contracts.py), [reconciliation](../../prototype/backend/otm/organization/reconcile.py) | [Domain](../engineering-design/01-domain-and-journeys.md), [production model](../engineering-design/11-production-data-model.md), accepted D5/D15–D17 |
| Four-column CSV adapter; each upload is a new snapshot; qualified complete census alone permits absence inference | [CSV adapter](../../prototype/backend/otm/organization/csv_feed.py), [CSV/web tests](../../prototype/backend/tests/test_csv_web.py) | [Specification](../product/oci-tenancy-manager-spec.md), domain/source contracts; production transport and authority still require qualification |
| Separate actionable and informational/history drift; persistent exception decisions; no automatic tenancy deletion | [Exception workflows](../../prototype/docs/exception-workflows.md), [review workflow](../../prototype/backend/otm/organization/review_workflow.py), [review tests](../../prototype/backend/tests/test_review_workflows.py) | Domain/journeys and immutable administrative action history |
| Stable internal identity and explicit audited email/name merge preserving all tenancy associations | [Identity and association behavior](../../prototype/docs/tenancy-associations.md), [store](../../prototype/backend/otm/organization/store.py) | Domain and production person/association model; no automatic fuzzy identity matching |
| Individual/shared ownership and multiple memberships; owner-inclusive distinct counts; shared ownership transfer | [Association implementation](../../prototype/backend/otm/organization/associations.py), [registry tests](../../prototype/backend/tests/test_tenancy_registry.py) | [Onboarding/member/transfer/offboarding journeys](../engineering-design/07-onboarding-journeys.md), production model |
| Last-association cleanup hides a person from managed directory but preserves source/history; returning after qualified absence opens fresh onboarding; retained associations and exemptions require explicit decisions | [Association walkthrough](../../prototype/docs/tenancy-associations.md), registry/review tests | [Domain managed-directory section](../engineering-design/01-domain-and-journeys.md), [production model](../engineering-design/11-production-data-model.md) |
| Search, sorting, pagination, clickable identity links, consistent action controls, generic copy and no Reason fields | [Prototype UI](../../prototype/backend/otm/organization/static/index.html), [client behavior](../../prototype/backend/otm/organization/static/app.js), evidence (private historical evidence; not distributed) | [DESIGN.md](../../DESIGN.md), screen authority and approved production walkthroughs; D16 pins organization revision |

The implemented organization/association ER lives in [prototype/diagrams](../../prototype/docs/organization-er-diagram.md).
The proposed production ER lives in [chapter10](../engineering-design/10-configuration-data-model.md) and
[chapter11](../engineering-design/11-production-data-model.md). There are ten implemented tables and
eighteen proposed additions; the proposed diagrams are not executed migrations.

### Tests that accompany production extraction

The [P0.3 decision checkpoint](development-progress.md#reusable-organization-decision-tests)
adds 120 isolated scenarios in
[registry decisions](../../prototype/backend/tests/test_registry_decisions.py),
[review decisions](../../prototype/backend/tests/test_review_decisions.py) and
[registry evidence](../../prototype/backend/tests/test_registry_evidence.py).
Retain these alongside the existing PostgreSQL regressions when moving the business logic into
production services. Adapt their persistence seams to the production repository interfaces;
no simulated local success, local actor bypass or schema initializer becomes a production API.
These tests establish domain decisions rather than SQL transactions or production authorization.

## Prototype boundaries

Preserve the pure domain logic, constraints, regression cases and approved UX. Replace loopback-only
local actor authentication with corporate SSO/authorization, simulated synchronous success with
accepted durable Operations, and local schema initialization with reviewed production migrations.
Clean workspace, fixture configuration and laptop database helpers remain lab-only. Generated
prototype schemas/OpenAPI describe that harness and are not production API contracts.

## Artifact disposition

| Material | Location / treatment |
|---|---|
| Runnable organization lab, unit/database tests, samples, local scripts, generated lab contracts and lab documentation | `prototype/` |
| Current application requirements and engineering chapters | `docs/`; start at the engineering design hub |
| Current proposed contracts and executable design predicates | `docs/contracts/`, `scripts/` and `scripts/design/`; no OCI or production behavior is implemented by these checks |
| Approved interactive application screen flows | `docs/walkthroughs/`; current Organization interactions still use the prototype authority |
| Referenced current design evidence | `docs/design-evidence/`; dated evidence is not a competing requirements source |
| Older planning, superseded screen alternatives and management presentation | `reference/history/` and `reference/presentation/`; clearly historical, not implementation instructions |
| Pre-move source/reference checkpoint and relocation manifest | Private ignored `.local-dev/checkpoints/pre-layout-2026-10-28/` and `.local-dev/layout-map-2026-10-28.json`; checksum verified, excludes database/runtime credentials and Git |
| Live lab connection/configuration and historical runs | Existing ignored `.local-dev/`; `prototype/.local-dev` points to it; database/volume untouched |

Nothing from the prototype is silently promoted to production implementation. The current test and
merge policy remains mandatory, including 95% unit-only coverage, disposable Docker PostgreSQL and
Playwright. File reorganization and static contract checks do not establish those runtime results.


## Reorganization validation — 28 October 2026

Validation receipt (private historical evidence; not distributed) records134 passing prototype
tests against disposable Docker PostgreSQL, current design-contract checks,45 authoritative/lab
documents with590 checked links, Ruff/format/docstring checks and18 browser route/viewport checks.
The independent UI reviewer inspected both changed flows at1440/390/320 and verified the final
checklist correction. Original modules/tests, source feeds and package files are checksum-preserved.

These results verify preservation and static design consistency. They do not establish95% unit-only
coverage, production Playwright integration, live OCI permissions or a measured managed-service
restore. No live lab database, credentials or Git history was changed.


## D56 security gate before development publishing

The user added [independent security review for every slice](../security-review-policy.md). This does
not reopen accepted application features or authorize publishing. P0 must clear the first candidate
repository of real employee PII/secrets, including current design examples and generated evidence,
and establish required automated security checks alongside the existing coverage/test gates.
The current local package is not yet publication-cleared. Originals remain private; repository
fixtures and examples must be synthetic. Independent subagent review and scanner results complement
each other and do not replace actual runtime/provider qualification.


## Selected appearance — D57

The user chose **left / original A** after comparing A and rounded A2 (private historical evidence; not distributed).
[DESIGN.md](../../DESIGN.md) now records A's navy/cobalt palette and crisp 3px treatment as the visual
authority. All approved workflows and security/accessibility gates remain binding. Final
whole-package approval and publication clearance remain separate.


## Local preparation while Git remains held

The user's continuation started [P0.1 synthetic-test preparation](development-progress.md): invented
fixtures, fresh-export validation and local connection guards. This does not mark the full design
approved or publish the project. Production application bootstrap and remaining P0 gates are separate.
