# Historical engineering index — 5 November 2026

This is a dated design-development record, not the current navigation or implementation status.
Accepted decisions are maintained in [the decision ledger](../decisions/design-decisions.md);
[current documentation](../README.md) takes precedence for implemented behavior and limits.
Private screenshots and receipts are intentionally not distributed.

# OCI Tenancy Manager: engineering design

[Organization mapping settings proposal](../engineering-design/20-organization-mapping-settings.md) — 31 October 2026:
UI-managed industry segments, first-import setup gate and immediate preview/apply recalculation.
Implemented local preview/apply and role-repair behavior is mapped in the
[organization mapping guide](../reference/organization-mapping.md).

Current local configuration implementation includes [baseline publication](../reference/baseline-authoring.md),
[frozen assignments/overrides](../reference/tenancy-overrides.md) and
[on-demand drift checks](../reference/configuration-drift.md). Actual OCI qualification remains separate.

[Environment email routing and release guards](../engineering-design/21-environment-email-policy.md) — accepted 4 November 2026:
keep canonical identities unchanged, protect all OTM-controlled SMTP/OCI contact paths and enforce
test/production policy independently in both deployment pipelines. Runtime contracts are in progress.

28 October 2026 | Final design review candidate | D1–D58 retained; chapter18 approved; Astra review complete; whole-package user signoff pending; runtime qualification remains separate

This is the unified entry point for completing the production design requested on 20 October.
Its chapters, including journey, SDK, data, execution, delivery and environment-policy references, develop the current [product specification](../product/oci-tenancy-manager-spec.md),
[accepted engineering decisions D1–D17](../decisions/engineering-review-decisions.md), and tested prototype.
Existing accepted decisions remain binding. Proposals and unresolved decisions are labeled;
writing a proposal here does not approve new behavior or qualify an OCI integration.

Current configuration authority: [D30 object model](../decisions/design-decisions.md#d30-accepted-complete-managed-objects-and-full-list-overrides),
[D31 bulk review gate](../decisions/design-decisions.md#d31-connected-publication-flow-and-all-conflicts-before-bulk-start)
[D32 navigation](../decisions/design-decisions.md#d32-baseline-history-override-entry-points-and-focused-issue-queues) and
[D33 terminology](../decisions/design-decisions.md#d33-organization-and-organization-drift-terminology) and
[D34 screen authority](../decisions/design-decisions.md#d34-approved-prototype-page-authority-and-shared-design-menu).
Current policy composition: [D35 protected required access](../decisions/design-decisions.md#d35-visible-protected-required-access-in-the-single-policy). Earlier D29 numeric-only editor text below is historical.

## Current access decision: D40, 24 October 2026

One V1 human-access flow uses the persistent per-tenancy recovery password. Temporary named-support
creation/enrollment/cleanup is deferred; D19/D37 named-flow entries below are historical and superseded.
Automation remains a separate persistent user. D39's recovery-only MFA exemption remains selected.
Each retrieval is audited/notified; first authorized disclosure attempt fixes a shared +4h rotation
window, repeat requests do not extend it, and unknown child/Vault rotation blocks release. Retain
independent outside-application custody. See [chapter13](../engineering-design/13-local-support-and-emergency-access.md)
and the [current proposed model](../engineering-design/11-production-data-model.md#identity-access-and-credential-model).


## Current recovery objectives: D51/D52, 25 October 2026

Accepted engineering targets: **15-minute RPO / 4-hour RTO, in-region recovery in V1**.
These require a measured restore; regional loss is outside those targets. See the
[recovery measurement and evidence contract](../engineering-design/06-platform-and-delivery.md#d51d52-accepted-recovery-objectives-and-in-region-qualification).


## Current testing and merge requirements: D53, 26 October 2026

Require **at least 95% unit-only line coverage**, Playwright UI integration and disposable Docker
PostgreSQL tests, all on every CI build. Any failure or coverage shortfall blocks merging to
protected `master`; PR-only changes and mandatory checks apply without routine bypass.
[The canonical policy](../engineering-test-plan.md#d53-required-test-and-merge-gates) defines coverage
scope and enforcement acceptance. CI/protection setup remains P0 work; no measured coverage claim.

## Current simplification: D54, 26 October 2026

Use stable Vault secret OCID plus CURRENT for normal recovery-password retrieval. Keep exact versions
for audit/staged rotation, and use deployment maintenance plus a manual restore procedure. The
external control/journal proposal is withdrawn, not an implementation prerequisite. Prefer the
simplest adequate design and ask before adding substantial edge-case machinery. See [the accepted
V1 boundary](../engineering-design/17-recovery-and-release.md).

## Final design approval gate — 28 October 2026

Before any Git check-in, complete an independent final review with OpenAI Astra against the current specification, eighteen chapters, approved screen authority and D1–D54. Resolve material design contradictions and distinguish implementation work from later OCI/corporate qualification. Then present the final package and remaining integration gates for explicit user approval. Chapter18 approval does not grant whole-package approval. Do not create commits or publish the project until the user finalizes the design. No production architecture is added by this review gate.

## D58 administrator implementation checkpoint — 29 October 2026

[Chapter19](../engineering-design/19-administrator-provisioning.md#detailed-checkpoint-two-new-tables-existing-sessions-and-audit)
now specifies the two-table administrator/credential extension, exact grant/revision session binding,
restricted operator MFA bootstrap/reset, atomic login/audit and the Administrators screen contract.
The full proposed inventory is 30 tables; the A1 production subset is now six, including the two
[administrator foundation tables](../reference/administrators.md). Local
recovery sign-in requires password plus independent MFA and never depends on corporate SSO.
Implementation proceeds grants/audit → local sign-in → UI → corporate integration. This is a
reviewable design checkpoint, not completed authentication code or whole-package signoff.

Application and configuration releases now have [separate deployment paths](../engineering-design/18-database-ci-and-build-order.md#application-and-configuration-deployment-paths).
Supported settings changes reuse the deployed image, validate its schema and roll consumers;
all existing CI/test/merge requirements remain binding. No hosted pipeline or OKE job is deployed.

## D58 local password/MFA backend checkpoint

[Local application authentication](../reference/local-authentication.md) now implements restricted
one-time operator bootstrap/reset and explicitly composed password-plus-TOTP sign-in, replay-safe
sessions and atomic login/logout history. No passwords/seeds/default account are added to source or
the settings file; local test custody is owner-only and production Vault remains a qualified facade
adapter. The actual model is still six application tables, now six frozen migration revisions.
Next work is the real sign-in/Administrators UI, ordinary grants and corporate provider qualification.
No OKE resources, hosted pipeline or real human account were created by local backend validation.

## Current local preparation

[Development progress](development-progress.md) records preserved synthetic regressions and
the [separate backend foundation](../../backend/README.md), now including a typed internal
inspection boundary and stateful simulator. Its complete source passes the shared 95% unit gate; prototype coverage remains diagnostic during extraction. P0 overall, business
features, frontend/database/browser gates and hosted CI remain incomplete. Git check-ins/publication still require final user approval and publish-set review.

## Authority and current evidence

1. The user's latest decisions supersede older contradictory draft text.
2. Adopted specification addenda, D1–D57 and later prototype decisions define current requirements.
3. The organization/association implementation, tests and approved UI are reusable evidence.
4. This package is the current production-design candidate. Chapter18 was reviewed and approved on 28 October; this is not whole-package final signoff. Pending proposals are not requirements.
5. Earlier milestone reports remain historical; their test counts and capability limits are dated.

The current reusable prototype has 285 passing tests, including 101 disposable PostgreSQL cases.
The 147-test clean synthetic export and earlier 134-test result are dated historical evidence.
[Local P0.1 progress](development-progress.md) documents the invented fixtures, private-file
independence and connection-query guard correction. No private feed or persistent lab is needed
for the suite; the rest of the repository still requires publication cleanup.
It does not implement a durable runner, OCI/Vault, corporate SSO, React, CI/CD or production hosting.
The existing ten-table [ER model](../../prototype/docs/organization-er-diagram.md) describes implemented storage;
new production entities must be distinguished from those tables until migrations are designed.

A verified local asset checkpoint preserves 164 files with SHA-256 manifest under
`.local-dev/checkpoints/design-baseline-2026-10-20/`. It includes source, tests, scripts, fixtures,
docs, diagrams and evidence. It excludes credentials, runtime state, Git history and database
contents. It is not a database backup. The project currently has no initial Git commit or remote;
shared repository/bootstrap is a development task, not something this checkpoint implies exists.

## Design checkpoints

These are design checkpoints, distinct from implementation milestones M0–M5 in the older plan.

| Checkpoint | Contents | Review evidence / exit criterion | Status |
|---|---|---|---|
| C0: reconcile and preserve | Scope, accepted decisions, prototype reuse, gaps, document map | Preserve evidence and distinguish current requirements from history | Design review candidate; final cross-tier and independent review |
| C1: domain and journeys | Lifecycle, identity, create/import, ownership, shared membership, offboarding, delete/recovery; physical data model | Every journey has actor, inputs, preview, durable acceptance, verification, failure/recovery and annotated screen flow | Design review candidate; implementation/provider qualification separate |
| C2: durable execution and OCI facade | Operations/steps, transaction boundaries, scheduling, retries, locks, uncertain effects, provider contracts and simulator | State/sequence diagrams, endpoint contracts, provider capability matrix and failure-injection test plan | Design review candidate; implementation/runner qualification separate |
| C3: managed configuration | Managed root objects, immutable versions, tenancy overrides, baseline history, rollout, per-item drift and repairs | Worked examples for root policy/tag-default/quota/budget; extension recipe; effective-value and repair renders | Design review candidate; implementation/provider qualification separate |
| C4: access and credentials | Admin SSO, owner/member access, activation/bootstrap, Vault/key lifecycle, emergency grants/rotation, recovery | Permission/secret matrix, rotation failure state machine, break-glass and manual-recovery renders | Design review candidate; D39/D40/D54 selected; provider behavior and corporate integration qualify later |
| C5: financial and operational visibility | Monthly actual/budget/native forecast, attribution, freshness, thresholds, operational alerts/history | Source/scope/period/currency contracts, collection jobs and financial/incident renders | Design review candidate; D41–D50 selected, dashboard approved and typed pack checked; live source/runtime qualification separate |
| C6: production and development handoff | OKE/Terraform, CI/CD, migrations/indexes/security, backups/restore, SLOs, work packages and integration strategy | Recovery rehearsal plan, CI gates, reviewed ER/API, risk register and executable development backlog | Chapter18 approved 28 October; final package review pending; migrations/CI/managed restore evidence are implementation/pilot work |

C1 and C2 iterate together; activation and identity feasibility in C4 feed their final contracts.
C3 relies on C2 observations/execution. C5 uses C2 collection and C3 budget semantics.
C6 is developed throughout, then closes the package. No future provider access is required for
local design/simulation; real capability and security qualification remain explicit pilot gates.
Each checkpoint updates this hub, its chapter, decision ledger, diagrams, UI evidence and test
traceability. A checkpoint is reviewed only after its unresolved choices are answered or clearly
classified as external blockers with a safe behavior. Whole-package completion requires the final independent Astra review and explicit user signoff below; unexecuted implementation tests and unknown deployment values are not themselves missing design decisions.

## Chapters

- [01: domain, workflows, data and screens](../engineering-design/01-domain-and-journeys.md)
- [02: durable operations, facade and simulator](../engineering-design/02-operations-and-provider.md)
- [03: managed configuration, overrides and drift](../engineering-design/03-templates-and-drift.md)
- [04: identities, access, credentials and break glass](../engineering-design/04-identity-and-access.md)
- [05: usage, observations, notifications and history](../engineering-design/05-cost-and-observability.md)
- [06: production operations and development handoff](../engineering-design/06-platform-and-delivery.md)
- [07: create/import journeys, readiness and operation screens](../engineering-design/07-onboarding-journeys.md)
- [08: OCI SDK call design, permissions and qualification](../engineering-design/08-oci-sdk-call-design.md)
- [09: facade messages, workflow states and onboarding execution](../engineering-design/09-execution-contracts.md)
- [10: explicit configuration fields, ER and screen/API mapping](../engineering-design/10-configuration-data-model.md)
- [11: unified proposed production model and complete UI field guide](../engineering-design/11-production-data-model.md)
- [12: required access, scoped observations, repair and field audit](../engineering-design/12-access-health-and-repair.md)
- [13: administrator password access, independent recovery and field inventory](../engineering-design/13-local-support-and-emergency-access.md)
- [14: financial journeys, source selection and field coverage](../engineering-design/14-financial-journeys.md)
- [15: financial collection, publication, simulator and operational-notification contracts](../engineering-design/15-collection-and-operational-events.md)
- [16: checked financial/email design contracts and field mapping](../engineering-design/16-c5-contract-review.md)
- [17: simple V1 credential resolution and manual restore](../engineering-design/17-recovery-and-release.md)
- [18: database, CI and incremental build order](../engineering-design/18-database-ci-and-build-order.md)

The package contains eighteen chapters plus this hub and adds no runtime classes/services. It retains the accepted modular API/worker architecture. Production migrations, executable models and CI enforcement implement this design after final approval.

## Requirements and reuse traceability

| Area | Existing evidence | Remaining design |
|---|---|---|
| Feed, identity and organization | `prototype/backend/otm/organization/`; org/CSV/migration/review tests | Production source authority/connectors; split pure domain from laptop-only storage/auth boundaries |
| Registry and associations | `associations.py`, `test_tenancy_registry.py`, current ten-table ER | Real OCIDs/origin, asynchronous pending relationships, verified changes and production migrations |
| Existing UI | `DESIGN.md`, static client and latest review (private historical evidence; not distributed) | React implementation retaining approved behavior; operation/configuration/spend/secret/recovery states |
| Operation/provider foundation | D2–D4/D10/D13; no runner/provider implementation | Typed contracts, durable steps, qualification, realistic simulator and common adapter tests |
| Baselines and overrides | D1/D6/D9 | Exact schemas, comparison semantics, bindings, dependencies and explicit rollout/repair |
| Financial visibility | D7 | Collection source, budget attribution, period/currency/cost basis and stale/unavailable states |
| Security/hosting/recovery | D8/D12/D14 | SSO, independent access contexts, Vault, rotation/session limits, network/DB roles, delivery and restore |

Preserve business invariants and tests rather than copying the local harness unmodified.
`Store` currently enforces local database/schema guards; `local_web` uses local actor labels and
immediate simulation; `local_lab` provides test resets. These must not become production bypasses.
Retain fixture/adaptor tests and characterization evidence when extracting production modules.
Do not replace the approved prototype during design; add separate design artifacts/renders.

## UI evidence plan

Use the [shared current menu and screen authority](../ui-screen-authority.md), page-specific cards, owner-inclusive inventory
counts, employee association counts, linked names, complete offboarding plans and no Reason inputs.
Keep generic copy, visible status/freshness, keyboard focus and responsive internal table scrolling.
Production removes Clean workspace. Preserve separate actionable decisions and informational history.

C1/C2 renders: tenancy/person detail; shared create/import wizard; offboarding checklist; operation
list/detail with manual-wait, provider-pending, uncertain and partial variants. C3: template editor,
override/effective-value preview, rollout and per-item drift. C4: secret disclosure, rotation failure
and recovery. C5: spend overview/detail and unavailable data. C6: restore recovery/admin release.
Use complete desktop journeys plus focused 390px variants and 320px constraints; not a distinct
full-page drawing for every status. Proposed renders must link each button to a reviewed contract.

### 20 October onboarding checkpoint

The [detailed create/import reference](../engineering-design/07-onboarding-journeys.md) now covers input/preview, durable
acceptance, manual activation, read-only import inspection, verified handoff, replacement access,
partial cleanup, cancellation and recovery. D20 A now separates setup completion from owner sign-in;
no runtime/API enums,
physical tables or provider guarantees are approved merely by writing this draft.

The separate [eight-screen walkthrough](../walkthroughs/onboarding-walkthrough.html)
runs at `http://127.0.0.1:8766/onboarding-walkthrough.html` while its local static server is running.
It can also be opened directly as a self-contained HTML file. Its controls switch sample states only;
it has no application/OCI requests and does not replace the prototype on port8765.
Desktop activation (private historical evidence; not distributed),
import (private historical evidence; not distributed),
partial setup (private historical evidence; not distributed) and
verified setup (private historical evidence; not distributed), plus
390px activation (private historical evidence; not distributed) and
320px verified setup (private historical evidence; not distributed) captures are saved.
Browser measurements (private historical evidence; not distributed)
cover all eight states at 1440px, 390px and 320px: no page overflow, controls at least44px and contextual
navigation; no browser console errors. This is design evidence, not completed OCI integration testing.
Independent documentation review found no material contract issues. Final UI review is tracked in
the review note (private historical evidence; not distributed).

### Shared-member screen checkpoint: D21–D24

The walkthrough's [Add shared member state](../walkthroughs/onboarding-walkthrough.html#member)
adds explicit profile selection, create-new/select-existing mode, an existing parent hierarchy,
compartment name and a local-only setup preview. The administrator selects a parent inside the
selected shared tenancy; creation's parent is not the member's grant target. Selection binds OCIDs,
shows full paths and preserves D23 owner-directed manual cleanup. The hierarchy is illustrative;
no OCI discovery/creation or membership change is implemented by this artifact.

Desktop member setup (private historical evidence; not distributed),
390px member setup (private historical evidence; not distributed) and
320px member setup (private historical evidence; not distributed) evidence accompanies
the shared-member UI review (private historical evidence; not distributed).
The original onboarding review remains historical; current sizing evidence includes all eight states.
No production schema, API or prototype behavior changed. C1 still needs remaining flow renders and
physical data-model review; C2 still needs exact durable-state/locking/contracts before implementation.

### Transfer/offboarding and operation-data checkpoint

The walkthrough adds [shared-owner transfer](../walkthroughs/onboarding-walkthrough.html#transfer)
and [complete employee offboarding](../walkthroughs/onboarding-walkthrough.html#offboard).
The transfer preview uses accepted D20–D24, including the previous owner's Remove/Remain-member
selection. The offboarding preview includes multiple individual ownerships and one shared membership,
with explicit Keep/Transfer/Delete/Remove choices. D25 A is accepted: one reviewed person plan may
initiate its selected actions, including multiple owned-tenancy deletions. The walkthrough remains
an inert preview and does not actually accept or dispatch work.

View the transfer desktop render (private historical evidence; not distributed),
offboarding desktop render (private historical evidence; not distributed) and
offboarding narrow-screen render (private historical evidence; not distributed).
The transfer/offboarding UI review (private historical evidence; not distributed)
records branch checks, bounded fixes and all 24 responsive measurements across the eight views.

The [candidate operation model](../engineering-design/02-operations-and-provider.md#candidate-operation-persistence-review-draft)
proposes operation/step storage and existing audit/registry extensions. It is deliberately separate
from the implemented ten-table ER, not a migration or final production table count. It traces atomic
acceptance/continuation, persisted waits, uncertain effects, association publication and partial parents.
C1/C2 remain in progress; configuration, credentials, usage and operational storage are not omitted
from the remaining design merely because this first slice uses two candidate tables.

### OCI SDK call-design checkpoint

[Chapter08](../engineering-design/08-oci-sdk-call-design.md) traces create/import/bootstrap SDK calls and maps deletion,
shared-owner/member operations, managed configuration, Vault/password work and actual/native forecast.
The [call inventory](../contracts/oci-provider-call-inventory.json) statically verifies 91 selected
methods across 10 clients and 23 model definitions at Oracle SDK 2.188.0's recorded source commit.
D27 narrows identity implementation to domains: 76 planned method candidates, one conditional ID
bridge and 14 legacy identity methods retained only as inspected reference; no legacy adapter.
Source-check evidence (private historical evidence; not distributed) is not
an OCI integration test or an application SDK dependency pin. No new runtime code/schema/UI or
credentials were introduced. C1/C2 remain in progress; C3–C5 payload/verification and live permission,
MFA/password/origin/reconciliation qualification remain open. Notable constraints are separate OCI
and SCIM IDs, body-less create/termination responses, and one-time reset versus known-password change.
Independent review and checks (private historical evidence; not distributed)
found no material issues in the saved call map; no live capability was qualified.

### Facade/workflow contract checkpoint

[Chapter09](../engineering-design/09-execution-contracts.md) specifies internal request/result envelopes, seven operation
states with independent stage/wait reasons, guarded acceptance/resume/amend/stop semantics and the
create/import step graph. The [schema](../contracts/oci-execution.schema.json) and [examples](../contracts/oci-execution-examples.json)
are design-only; generated production Python/OpenAPI models remain a later deliverable. The
[scenario catalog](../contracts/oci-execution-scenarios.json) lists 28 planned DB/worker/provider cases.
Structural validation (private historical evidence; not distributed)
passed 27 positive message examples, 26 negative controls and 10 graph-consistency examples; it does
not execute those 28 workflows or qualify OCI/Procrastinate. No runtime schema, dependency or DB changed.

The separate [Operations walkthrough](../walkthroughs/operations-walkthrough.html)
is available at `http://127.0.0.1:8766/operations-walkthrough.html#activation`. It shows six sample
states, linked operation/tenancy previews, local search/sort/pagination and handoff/error/verification
states. UI review (private historical evidence; not distributed) records 18
responsive combinations; no prototype/backend/OCI call occurs. Existing onboarding/prototype remain intact.
Contract review (private historical evidence; not distributed) records
two corrected findings and the remaining runtime/qualification gates.

## Scope carried forward

Administrator-only application; owners retain full OCI administration and may create other users.
Required automation/recovery accounts, D40 recovery-password administrator access and administrative history stay V1. Temporary named support is deferred. Security-findings
workflows, security auditing and mandatory audit/governance-user provisioning stay V2 unless the
user changes that scope. Extensible user/group template handlers can support later roles without
making a deferred role mandatory now. No automatic tenancy creation/deletion from a feed.
An owner transfer, IAM grant/revocation and shared resource cleanup are distinct effects that need
explicitly reviewed contracts; organizational metadata alone does not prove OCI access changed.

## Design review evidence and gaps

- Existing main spec §6.4 and later addenda supersede older per-tenancy/separate-person removal text.
- `screen-flow-design.md` has pre-prototype Reason/manual-only cleanup/mobile statements.
- `organization-m1-contract.md` and parts of older review/test plans contain earlier table counts,
  test counts and read-only/no-frontend claims. Use current implementation/ER and dated evidence.
- No external integrations, deployment pipeline or restore behavior have been runtime-qualified.
- The detailed baseline/item schemas, bootstrap identity, IAM grants, session expiry, financial
  dimensions and production entitlement source still require decisions/qualification. D51/D52 now
  select 15-minute RPO/4-hour RTO for in-region recovery; actual restore behavior remains unqualified.

REALITY: premise-table finding Prototype receipts exist; real integration claims remain unverified docs/engineering-design/README.md:15
REALITY: already-done finding No initial commit or remote exists; remote history cannot establish completed work docs/engineering-design/README.md:25
REALITY: surface-check pass Existing prototype routes/contracts are evidence; no new runtime routes promised prototype/docs/contracts/organization-local-web-openapi.json:1
REALITY: binding-decisions pass D1–D17 and latest user refinements carried forward docs/engineering-review-plan.md:1
REALITY: numbers pass 134 collected; prior successful execution not rerun; 164 checkpoint files verified docs/engineering-design/README.md:19
REALITY: deferred-asks pass All requested areas mapped to C1–C6; security findings/audit-user scope retained V2 docs/engineering-design/README.md:35
REALITY: pr-count pass No implementation PR split proposed; work-package strategy remains pending docs/engineering-design/06-platform-and-delivery.md:1

## Decision ledger

### D18: initial activation responsibility

Finding: C1-01; medium design gap; high confidence. Existing create flow names administrator
activation but does not distinguish the OTM operator from the future engineer owner.
Evidence: [specification §6.1](../product/oci-tenancy-manager-spec.md#61-create), and current
[Oracle child-tenancy creation documentation](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm).
Plan baseline: creation pauses for manual activation/password/MFA; which identity activates is unresolved.
Runtime evidence: prototype creates a local simulated registry entry; it has no activation integration.

| Choice | Current | A | B |
|---|---|---|---|
| Recipient/responsibility for initial activation | Unspecified | OTM administrators using a designated bootstrap administrator identity | Engineer/tenancy owner activates, then provides the reviewed bootstrap handoff |
| Final owner rights | Full administration approved | Unchanged | Unchanged |
| Application users | Administrators only | Unchanged | Unchanged |
| Manual wait and resume | Approved | Admin activation wait | Owner activation/bootstrap wait |
| Exact email/MFA/identity/credential lifecycle | Pending qualification | Still pending C4 | Still pending C4 |
| Owner access timing/required readiness checks | Pending detail | Remains pending | Remains pending |
| Engineering action now | Design only | Design admin-led activation branch | Design owner-led activation branch |

Question D18: Who should activate a newly created child tenancy?
OCI sends an activation message to the designated initial administrator. We need to choose who
performs that step, because it determines the waiting screen, instructions and bootstrap handoff.
Recommendation: A, OTM administrators, because the first release is an administrator-operated service.
A) OTM administrators (recommended): A designated bootstrap administrator receives activation
instructions and an OTM administrator completes the manual step. This keeps onboarding centrally
operable and makes the human wait clear, but requires an approved bootstrap identity, email handling
and MFA procedure. It does not decide when the engineer receives full admin access.
B) Tenancy owner: The engineer receives activation instructions and performs the step. This uses
their own initial identity, but onboarding waits on an external person and requires a secure handoff
before the tool can complete provisioning. The engineer's eventual full administration is unchanged.
Options differ in operating model, not completeness; no coverage score.
Net: Choose who owns the manual activation step; credential details and owner-access timing follow separately.

State: accepted with refinement, 20 October 2026. Actual answer: A. Use the authenticated
initiating OTM administrator's name/email, not a generic shared activation identity. That person
manually activates the child and establishes temporary SDK access. The app then creates the owner,
permanent operational identities and baseline, and removes the temporary child-local human
administrator and bootstrap access after replacement access is verified. Keep the initiating actor
in immutable history. A requested name/home region is needed before the provider create request;
resumed provisioning discovers the actual name/region from OCI and preserves requested values separately;
provide only the public bootstrap key to the person. Exact grants, owner handoff and emergency
MFA/recovery mechanisms require C4 qualification; D18 does not approve those new alternatives.
History: this refines option A's generic designated-identity wording. D1–D17 remain accepted.
Documentation findings and the proposed safe sequence: [chapter04](../engineering-design/04-identity-and-access.md#administrator-led-creation-d18).

### D19: routine support versus independent emergency recovery

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

Finding: C4-01; high recovery impact; high confidence. An on-demand human account can only be
created while the automation identity and its required privileges still work. Owners retain full
administration and can remove those privileges. This is a dependency problem, not an SDK feature gap.
Evidence: [chapter04 research and qualifications](../engineering-design/04-identity-and-access.md#support-and-emergency-access-proposal-d19).

| Choice | Current accepted baseline | A: hybrid support and recovery | B: recovery account only |
|---|---|---|---|
| Routine organizational support | Disclose shared emergency password | Named, temporary MFA-protected human access created by working automation | Continue using existing emergency disclosure flow |
| Independent last-resort account | Persistent local recovery identity | Retained with an out-of-band access procedure | Retained with an out-of-band access procedure |
| Automation identity | Persistent API administration | Unchanged | Unchanged |
| Engineer owner | Full administration | Unchanged | Unchanged |
| Added workflow | None yet implemented | Named grant, enrollment, expiry/revocation and cleanup | No named support grant workflow |
| Emergency MFA choice | Narrow exemption previously selected | Separate decision, not approved by this choice | Separate decision, not approved by this choice |
| Four-hour limit | Rotation scheduled; session cutoff unqualified | Grant cleanup and recovery rotation require separate verified contracts | Existing rotation contract still needs qualification |

Question D19: Should routine support use named on-demand accounts, while retaining an independent
emergency recovery account? Recommendation: A. This reduces routine sharing without making recovery
depend on the automation identity it may need to repair.
A) Hybrid (recommended): add named, time-limited support access, and keep an independent emergency
account for loss of automation or the application. This adds an enrollment/cleanup workflow and more
qualification work, but separates everyday support from last-resort recovery.
B) Existing recovery flow only: keep the persistent emergency account and audited password-disclosure
workflow for support as well. This is simpler, but routine support continues to use a shared identity.
Options differ in kind, not coverage; no completeness score. No delivery-time estimate established.
Net: choose the support/recovery operating model; the emergency MFA method remains a separate decision.
State: accepted, 20 October 2026. Actual answer: A. Named on-demand support plus independent
persistent emergency recovery. Owner full administration and persistent automation are unchanged.
The user explicitly requires further work on MFA for the non-named custodial recovery account.
Its factor choice, enrollment, custody, backup/recovery and deployment feasibility remain open;
this answer does not adopt an MFA mechanism or confirm a hard four-hour session cutoff.

### D18 refinement: requested name versus actual tenancy identity

Accepted requirement, 20 October 2026: a name selected before activation may not be the final
OCI name. Record and display the actual OCI tenancy identity after handoff; do not require the
administrator to retype its name. The user reports global name collisions during activation;
qualify exactly when the deployed creation path validates/reselects the name rather than claiming
that every activation flow supports renaming.

The create API still requires a requested name and home region. Retain these provisional inputs
for app-initiated creation. Given the supplied/resolved tenancy OCID, bootstrap access resolves
actual name/home region and domain context, and the parent context verifies real child membership.
Requested values and provider attempt history are retained separately from verified current values.
A name difference alone does not authorize a second create, a region change or an OCID substitution.
Wrong parent, protected/already-managed targets or a changed target OCID require a blocked/reviewed
handoff before configuration writes. Confirmed name rejection can request a new name and produce
an audited new attempt; an uncertain create must reconcile first.

Alternative noted, not selected: omit initial name/region only if initial OCI creation is manual
outside OTM, or another qualified provider interface supplies those required values. This changes
the automatic create boundary and is not implied by accepting discovery at resume.
See [discovery and collision design](../engineering-design/04-identity-and-access.md#requested-name-and-verified-tenancy-identity).

### D20: owner first sign-in versus verified tool setup

Finding: C1-02; medium workflow impact; high confidence. Earlier text says owner handoff must be
ready without distinguishing configured, MFA-enforced access from a human completing first login.
Evidence: [onboarding readiness contract](../engineering-design/07-onboarding-journeys.md#readiness-decision-d20-owner-first-sign-in).
Runtime evidence: current prototype simulates success and has no OCI human-login evidence.

| Boundary | A: separate owner sign-in | B: wait for owner sign-in |
|---|---|---|
| Owner full administration and enforced MFA | Required | Required |
| Independent operational recovery and all mandatory setup checks | Required | Required |
| Onboarding completion | After tool configuration/verification and temporary cleanup | Same checks plus confirmed first owner login/MFA |
| Owner human wait | Separate explicit unconfirmed-access status | Operation stays Waiting for owner |
| Proof | Invitation is not proof of delivery/enrollment; show only observed or attributed facts | Same evidence limits; no fabricated API signal |
| Other V1 constraints | Admin-only app; no owner approval added | Admin-only app; no owner approval added |

Question D20: Must onboarding wait for the engineer's first sign-in? Recommendation: A, finish tool
setup when mandatory controls are verified, while separately showing whether owner sign-in is confirmed.
This keeps a provisioning workflow from waiting on an engineer but does not claim the engineer used it.
A) Separate statuses (recommended): complete OTM setup after verified controls, owner grants and
cleanup; show owner sign-in as unconfirmed until supported evidence exists. This avoids a human
bottleneck and retains honest visibility, but administrators must distinguish the two statuses.
B) Wait for first sign-in: keep onboarding open until the engineer completes MFA/first login and
that is verified. This makes completion include human access, but operations may remain open for days.
Options differ in operating model, not coverage; no completeness score or unmeasured delivery estimate.
Net: decide whether first human use blocks setup completion or appears as a separate access status.
State: accepted, 20 October 2026. Actual answer: A. Complete OTM onboarding after mandatory
configuration, owner grants/MFA enforcement, independent recovery and temporary-access cleanup are
verified. Track first owner sign-in independently; missing/unsupported evidence stays unconfirmed.
No first-login confirmation/approval is required to complete tool setup. Owner full administration,
MFA requirements and the unresolved custodial recovery qualification remain unchanged.

### D21: access for members of a shared tenancy

Finding: C1-03; high effect on privilege/cleanup; high confidence. The prototype tracks shared
membership but has no OCI principal, compartment or IAM changes. Owner full administration is
accepted; that does not specify privileges for additional shared-tenancy members.
Evidence: [shared journey/access draft](../engineering-design/01-domain-and-journeys.md#shared-tenancy-access-design-draft).

| Boundary | A: explicit access profile | B: all members administer tenancy | C: membership tracking only |
|---|---|---|---|
| Owner | Full administration | Full administration | Full administration unchanged |
| Additional member access | Administrator chooses compartment-scoped or full tenancy administrator | Always full tenancy administrator | OTM records association; external access is manual |
| Compartment-scoped option | Proposed default; exact supported service scope must be qualified | Not part of this rule | No automated provisioning |
| Preview | Identity, permissions, scope, shared objects and cleanup effects | Explicit warning that member can administer other members' resources/access | Explicitly says no OCI grant/revocation performed |
| Removal | Revoke exact managed grant; distinct identity/resource checks | Remove managed administrator grant; other access may remain | Manual access cleanup evidence required |
| Engineering cost | Profile schema, scope and handler/verification cases | Simpler grant path, broad access and difficult total revocation | Smallest provider scope; more administrator work |

Question D21: What access should Add to shared tenancy create? Recommendation: A, explicitly
select a profile, with compartment-scoped access as the proposed default and full administration
available when deliberately chosen. Owner rights remain unchanged and the app remains admin-only.
A) Explicit profiles (recommended): choose scoped member access or tenancy administrator per
association. This supports different shared workloads and makes intended access/cleanup visible,
but requires qualifying and maintaining more than one grant profile.
B) All members are tenancy administrators: every added member gets full administration. This is
simple and flexible for demos, but members can change other people's resources, identities and controls.
C) Track membership only: retain associations but leave shared-user/access setup and cleanup manual
for V1. This keeps initial automation small, but the UI must not report OCI access granted or revoked.
Options differ in access/operating model, not completeness; no coverage score or delivery estimate.
Net: select shared-member access behavior; the owner always retains full administration.
State: accepted, 20 October 2026. Actual answer: A. Administrators explicitly select a shared-member
access profile. Compartment-scoped access is the default; full tenancy administration is an explicit
alternative. Owner full administration and admin-only application access are unchanged. Exact scopes,
service dependencies, identity bindings and verification remain C3/C4 qualification work. No prototype
IAM implementation or production profile schema is implied by this decision.

### D22: previous owner's access after a shared ownership transfer

Finding: C1-04; high offboarding/privilege impact; high confidence. Establishing replacement-owner
administration does not specify whether the previous owner remains a member, keeps administration
or leaves the shared tenancy. The prototype transfer retires the old ownership relationship but
has no OCI grants to revoke. Preserve that distinction when designing production behavior.
Evidence: [transfer flow and failure boundaries](../engineering-design/01-domain-and-journeys.md#transfer-shared-ownership).

| Boundary | A: explicit previous-owner disposition | B: always remove | C: retain full administration |
|---|---|---|---|
| Replacement owner | Verify full administration before changing accountability | Same | Same |
| Previous owner | Select remove access or remain member with D21 profile | Remove managed owner access/relationship | Remains member with full administration |
| Offboarding default | Remove; retaining access must be explicitly selected and remains an outstanding/kept association | Remove | Keep unless a separate removal operation succeeds |
| Standalone transfer | Explicit selection; no implicit keep/remove | Removal is automatic consequence of confirmed transfer | Retention is automatic consequence of confirmed transfer |
| Resources and other identities | Not automatically deleted | Not automatically deleted | Not automatically deleted |
| Partial cleanup | New accountability can publish; old access cleanup remains visible and offboarding incomplete | Same | No revocation implied by transfer |
| Residual access | Show unmanaged/other grants; never equate one grant removal with universal revocation | Same | Full old-owner privileges are intentional |

Question D22: After transferring shared ownership, what happens to the previous owner's access?
Recommendation: A, make the disposition explicit in the transfer preview and default to removal
when the transfer is part of offboarding. This supports both departures and a continuing team member.
A) Explicit disposition (recommended): remove the previous owner's access, or keep them as a member
with a selected scoped/admin profile. This makes the resulting permissions visible and reuses D21,
but adds a required choice to the transfer form. Offboarding defaults to Remove.
B) Always remove: transferring ownership also removes the previous owner's managed access. This is
simple for departures, but a continuing colleague may need to be added back as a member.
C) Always retain full administration: transfer changes accountable ownership and keeps the previous
owner as an administrator member. This avoids interrupting ongoing work, but a departure needs a
separate removal and old privileges persist until that succeeds.
Options differ in access/operating model, not completeness; no coverage score or delivery estimate.
Net: choose the previous owner's post-transfer relationship; replacement-owner access is verified first.
State: accepted, 20 October 2026. Actual answer: A. Every shared ownership transfer explicitly
selects the previous owner's disposition: Remove access or Remain a member with a selected D21
profile. Offboarding defaults to Remove; retaining an association is an explicit choice. Replacement
administration must be verified before old grants are removed; incomplete cleanup remains visible
and does not complete offboarding. Resources are not deleted by ownership transfer.

### D23: shared-member compartment/resource cleanup in V1

Historical review brief below; its proposed resource deletion/verification was superseded by the
user's custom answer. The accepted contract at the end of this entry is authoritative.

Finding: C1-05; meaningful implementation scope; high confidence. Removing membership/access is
different from disposing of workloads. The original shared-tenancy use case includes member
compartment cleanup, but its automation was explicitly left light in the initial design. OCI
requires an empty compartment before deletion; deleting a non-empty scope needs service-specific
resource/dependency handling. Evidence: [removal flow](../engineering-design/01-domain-and-journeys.md#remove-member--offboard)
and [Oracle compartment deletion](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_delete_a_compartment.htm).

Common requirement: explicitly choose Keep/reassign responsibility or Clean up the selected scope;
never infer resource deletion from removing a person or transferring tenancy ownership. Full-admin
membership does not prove that all tenancy resources belong to that member. The shared tenancy,
other members, protected identities and unrelated resources remain outside this cleanup intent.

| Boundary | A: manual workload cleanup in V1 | B: supported automated workload cleanup in V1 |
|---|---|---|
| Access removal | Automated scoped grant/user handling with verification | Same |
| Keep resources | Explicit choice plus continuing responsible person; no claimed resource move | Same |
| Clean up non-empty scope | Manual wait/checklist; inspect/recheck after administrator cleanup | Explicit preview of supported resources/dependencies, then automated handlers |
| Delete empty compartment | Only after explicit choice, ownership/scope checks and qualified empty verification | Same |
| Unsupported or uncertain resources | Manual cleanup/review; no empty/success inference from missing visibility | Same fallback; never a generic blind purge |
| Completion | Required cleanup verified or explicitly retained/reassigned; no early directory removal | Same |
| Added engineering scope | Compartment binding/checks and resumable manual step | Also resource inventory, per-service retirement, dependency order and partial-recovery tests |

Question D23: How much workload cleanup should shared-member offboarding automate in V1?
Recommendation: A, automate access changes and safe empty-compartment deletion, while guiding and
verifying manual cleanup of non-empty compartments. This retains the required flow without making
V1 a general OCI resource-deletion engine.
A) Guided manual workload cleanup (recommended): administrators explicitly keep/reassign or clean
up resources; OTM removes access, tracks any required manual step and verifies the selected result.
OTM can delete an explicitly selected, verified-empty managed compartment. Non-empty workloads are
cleaned outside OTM, adding manual work but a smaller qualified provider surface.
B) Automate supported workload cleanup: add reviewed resource/dependency handlers for a defined V1
service set, with inventory, destructive preview, verification and resumable partial failures.
Unsupported or unverified resources still require manual cleanup; this extends the automation/test scope.
Options differ in automation/operating model, not completeness; no coverage score or delivery estimate.
Net: choose whether non-empty workload cleanup is a guided manual stage or a supported automated V1 stage.
State: accepted custom answer, 20 October 2026. Actual answer: automate removal of the member's
child-tenancy user ID and group memberships; guide the administrator to direct the shared-tenancy
owner to manually clean resources in the specified compartment. **No automated resource or
compartment cleanup/deletion in V1, including empty compartments.** This supersedes both original
options' proposed empty-compartment automation and resource-cleanup verification/completion gate.

V1 completion verifies the selected identity and membership removal, then retires that association.
Manual workload cleanup is owner follow-up guidance, not an OTM-verified result or a gate on completed
membership removal/directory offboarding. The tenancy owner remains accountable for retained
resources/cost. Display the owner and known compartment name/OCID; missing scope is shown honestly,
not replaced with an inferred whole-tenancy target. No automatic cleanup message is sent by this
choice; the administrator receives guidance to direct the owner. Future automation remains V2+.

Safety qualification: only the inspected, bound child-local personal user may be deleted. Shared,
protected operational, upstream corporate identities or a user still required by another obligation
must not be deleted blindly. Ambiguous/unsupported deletion remains blocked/manual and cannot be
reported as successful user removal. Removing access does not prove every session or independently
created identity has been revoked. Existing independent-recovery/MFA requirements remain unchanged.

### D24: providing a compartment for scoped shared-member access

Finding: C1-06; medium onboarding scope; high confidence. D21 selects compartment-scoped access
by default, but no decision specifies who creates the target compartment. D23 forbids automatic
resource/compartment cleanup, not provisioning. The initial scope must be explicit and bound by OCID.
Evidence: [shared profile contract](../engineering-design/01-domain-and-journeys.md#shared-member-profile-contract-d21-accepted)
and [Oracle compartment creation](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm).

| Boundary | A: create or select | B: select existing only |
|---|---|---|
| Scoped-member onboarding | Default to create a compartment; explicit select-existing alternative | Administrator selects an existing compartment; creates it externally if needed |
| Preview | Parent, proposed name/description and scope, or inspected existing OCID | Inspected existing name/OCID and scope |
| OCI changes | Qualified compartment creation plus identity/grants; no workload creation | Identity/grants only |
| Binding | Record actual OCID and whether created or adopted; do not adopt by name | Same explicit adoption checks |
| Failures | Name conflict, permission loss, uncertain create and partial setup require reconciliation | Missing/inaccessible target blocks grants; no implicit fallback to root/admin |
| Offboarding | D23 owner-directed manual cleanup; no automatic compartment deletion | Same |

Question D24: For scoped shared-member access, should OTM create the compartment or require one
that already exists? Recommendation: A, offer Create new by default and Select existing explicitly.
It completes member onboarding without an external setup dependency while preserving existing layouts.
A) Create or select (recommended): show compartment creation/selection in preview, create if selected,
then verify the returned scope before granting access. It adds a small qualified provisioning step,
including partial/uncertain failure handling; offboarding still leaves the compartment untouched.
B) Existing only: the administrator supplies an existing compartment, which OTM inspects/binds before
granting access. This reduces V1 provisioning scope but requires external setup for a new compartment.
Options differ in provisioning/operating model, not completeness; no coverage score or delivery estimate.
Net: decide whether new compartment provisioning is part of member onboarding; cleanup remains manual.
State: accepted with refinement, 20 October 2026. Actual answer: A. Default to Create new with
an explicit Select existing alternative. For creation, the administrator selects the parent from
the existing compartment hierarchy of the target shared tenancy. Do not hardcode a parent or assume
the tenancy root. Show full paths and bind by OCID; recheck target tenancy, parent lifecycle and
creation permission before execution. New-compartment creation does not grant the member access to
its parent/siblings. D23 still leaves all compartments/workloads unchanged during offboarding.

### D25: initiation of multi-tenancy offboarding

Finding: C1-07; high deletion-authorization impact; high confidence. The spec says no bulk deletion,
while accepted person-level offboarding requires a complete plan and permits multiple owned tenancies.
Evidence: [spec §6.3](../product/oci-tenancy-manager-spec.md#63-delete) and
[offboarding preview](../engineering-design/01-domain-and-journeys.md#person-level-offboarding-preview-and-d25-boundary).
Runtime evidence: prototype simulates local association changes, not actual deletion authorization.

| Boundary | A: one complete person plan | B: individual deletion starts |
|---|---|---|
| Preview | Every association and exact selected target/disposition | Same complete inventory/plan |
| Initiation | One confirmation can accept selected scoped actions, including multiple owned-tenancy deletions | Each tenancy deletion needs its own explicit Start; plan links their operations |
| Deletion guards/warnings | Per target at acceptance and execution; no relaxation or extra approver | Same |
| Scope | One selected person's associations; no fleet-wide arbitrary bulk-delete endpoint | One tenancy per deletion initiation |
| Partial results | Linked operations retain independent verified/failed/unknown outcomes | Same linked progress; more administrator interactions |
| Completion | Required effects verified, no retained links; D23 resource guidance does not block | Same |

Question D25: Can one offboarding confirmation start all selected actions for that person, including
multiple owned-tenancy deletions? Recommendation: A, one complete preview/confirmation with exact
per-target guards and independent operations. This avoids a fragmented workflow without adding a
fleet bulk-delete feature, but explicitly refines the earlier no-bulk-deletion wording.
A) One person plan (recommended): review every association and confirm the complete selected plan.
Each target retains its own execution guards, warnings and result; failures do not hide completed work.
This is convenient but one confirmation can authorize more than one tenancy deletion.
B) Separate deletion starts: review the complete plan, then individually confirm/start each tenancy
deletion. Member removals/transfers can still be linked, but deleting several owned tenancies requires
more interactions. This preserves a strict one-tenancy-per-deletion-initiation boundary.
Options differ in authorization/operating model, not completeness; no coverage score or delivery estimate.
Net: choose the initiation boundary; all target safeguards and verified-completion rules remain required.
State: accepted A, 20 October 2026. Actual answer: "a". One complete person-plan confirmation
may initiate all selected scoped actions, including multiple individually owned-tenancy deletions.
Each target retains the existing warnings, current registration/parent/protected-target/eligibility
and permission checks, independent operation/results and scoped resume. No additional approver,
Reason field or fleet-wide arbitrary bulk deletion is introduced. Acceptance is not verified
completion. D26 defines confirmed provider initiation as the required deletion effect.


### D26: deletion scope ends at confirmed termination initiation

State: accepted custom direction, 20 October 2026. Actual user instruction:
"We don't need to worry about the official termination after 30 days. Our job is just to initiate termination."
This supersedes the unaccepted draft alternatives requiring suspension verification or finality monitoring.

OTM's deletion workflow completes when the qualified OCI response/evidence confirms termination
initiation for the intended tenancy. Local operation/job acceptance alone is insufficient. Persist
provider confirmation/correlation and the result; retire the deletion association then. If that is
the last required association and no links are kept, complete the person's managed-directory removal.
Other selected member-removal/transfer operations still need their own verified results.

Label the result **Termination initiated**, never **Permanently deleted**. Retain tenancy and audit
history with last-known owner/OCID. No 30-day wait, scheduled final-deletion monitoring or finality
state machine is required. Timeout/lost response stays unverified until reconciled; rejection/failure
remains actionable in Operations. Do not issue a duplicate termination blindly. Existing protected
parent/child/registration/eligibility guards and imported-origin feasibility constraints remain.
See [the confirmed-initiation contract](../engineering-design/01-domain-and-journeys.md#deletion-completion-d26-accepted).


### D27: identity-domain scope confirmed

State: accepted clarification, 20 October 2026. Actual answer: "All use identity domains".
V1 uses an identity-domain user/group/credential adapter; no standalone legacy-IAM identity
implementation or parallel legacy simulator is required. Keep IAM infrastructure APIs for metadata,
domain discovery, compartments and root policies. Import must still inspect actual domain/endpoint,
OCID-to-SCIM bindings and permission/capability requirements. No assumption that every tenancy uses
Default, shares a domain, or has identical federation/MFA follows from this answer. Unsupported
identity models are reported and blocked with no automatic fallback. The inspected 91-call source
inventory remains evidence, with per-call scope labels distinguishing planned, conditional bridge
and reference-only legacy calls. Custodial MFA and password/session qualification remain open.


### D28: removing a managed configuration item

Finding: C3-01; high configuration/access impact; confidence9/10 that a product boundary is needed.
[Chapter03](../engineering-design/03-templates-and-drift.md#extensible-item-contract) explicitly leaves
apply/update/retire and remove/unset semantics to define; D6 binds dedicated managed objects but
neither that binding nor a conditional SDK delete method approves automatic removal.
The following question records the original alternatives; accepted A is recorded below. It changes
the design boundary, not the working prototype.

Question: when the resolved desired configuration explicitly removes a whole managed item, may
an explicitly confirmed rollout delete its tool-managed OCI object? Example: baseline v1 creates a
quota and baseline v2 removes it, with no remaining assignment requiring it. This does not decide
field-level unset/inherit semantics or imply that deleting an override deletes a baseline object. Publishingv2 still changes nothing under D1; the question concerns a later reviewed rollout.

| Boundary | A: previewed managed-object removal | B: report manual removal required |
|---|---|---|
| Rollout diff | Show exact owned policy/quota/budget object and Remove action | Show retained object and manual-removal requirement |
| Execution | After explicit rollout confirmation, remove only eligible bound objects in dependency-safe order and verify | Tool does not delete the object through baseline removal; admin cleans it outside the tool and verifies |
| Unknown/partial effects | Retain bindings/history and reconcile; no blind retry or delete/recreate repair | Preserve observation/history until manual outcome is verified |
| Mandatory safeguards | Never remove required automation/recovery or active-owner/member access by omission; preserve unrelated/shared objects; protected/locked scope blocks | Same protected/unrelated-object rules |

A (recommended) supports complete automated configuration lifecycle within a reviewed rollout.
This is not automatic deletion on publication/feed processing. Identity/group changes with active
association obligations route through their dedicated workflows; generic omission cannot bypass
D18–D27. D23 still forbids workload/compartment cleanup, and D26 tenancy termination remains separate.
B keeps removals manual in V1; stale managed objects remain visible with explicit cleanup requirements,
rather than disappearing from governance because a template stopped mentioning them.
Completeness: options differ in who performs removal, not in whether it must be accounted for.
State: accepted A, 20 October 2026. Actual answer: "a". A confirmed rollout may delete obsolete,
eligible explicitly bound tool-managed configuration objects and verify removal. Publication/feed
processing alone still performs no writes. Apply dependency, live binding/permission and ownership
checks; preserve unrelated/shared objects and protect mandatory automation/recovery and active
owner/member access. Whole-item removal is distinct from clearing an inherited field override.
No resource/compartment cleanup or automatic tenancy termination is added. Overlay add/exclude
permissions are a separate unresolved C3 choice, not implicitly approved by this answer.


### C3 historical pre-D29 checkpoint: 20 October 2026

Historical evidence below predates D29; its broader examples and counts are superseded by the
limited-V1 checkpoint below. D28 is recorded; [chapter03](../engineering-design/03-templates-and-drift.md#worked-configuration-checkpoint) now describes
field inheritance, explicit rebase, typed dependencies, symbolic intent/late verified bindings,
per-item application/observation and guarded removal/repair. The proposed three storage concepts are
not added to the implemented ER model or database. C3 remains in progress.

Review the [four Configuration views](../walkthroughs/configuration-walkthrough.html),
[six JSON fixtures](../contracts/configuration-examples/baseline-v1.json) and
bounded resolver check receipt (private historical evidence; not distributed).
The checker executes4 positive,19 negative and7 additional invariants, with no OCI calls. It does not
implement full production schemas, a rollout/drift engine or provider payload generation. The UI review (private historical evidence; not distributed)
covers12 responsive view/viewport combinations; its amounts/identifiers are illustrative and
need not equal the machine fixtures. The working organization app and database remain unchanged.

### D29: historical numeric-limit model, superseded by D30

State: accepted custom limited approach, 20 October 2026. Actual answer: "lets go with the limited v1
approach. I can see some tenancies, like shared tenancies, needing larger budgets than others".
This was accepted on20 October and is now superseded by D30 below. Its no-policy-override and numeric-rule-only restrictions no longer describe V1.

One baseline lineage has immutable versions and one current-for-new published version. New creation
and import pin that version at operation acceptance; in-flight work never switches to latest.
Existing tenancies remain assigned until a previewed, confirmed bulk/single update. Version age alone
is Update available, not configuration drift. This refines D1's earlier manual new-version selection.

Baseline categories: root policies, root defined-tag defaults, budget and quota rules. Only budget
amount and supported named quota-rule numeric limit can be overridden per tenancy. No tag/policy
changes or item additions/exclusions through overrides in V1. A shared tenancy can explicitly keep
budget 500 while standard defaults move 200→300. Currency/period and quota service/metric/unit/scope
are fixed; compatible values persist through a baseline update. Removed/redefined overridden settings
block the affected target before writes until the override is cleared/replaced and preview refreshed.

Resolve target baseline plus values first, then apply a guarded diff; never strip all old controls
before applying the new baseline. D28 eligible removals remain part of confirmed baseline updates.
Identity/bootstrap/recovery access stays in its separately defined mandatory onboarding flow.
General/additive overrides are deferred. No runtime app/DB change is introduced by this acceptance.

The revised [chapter03](../engineering-design/03-templates-and-drift.md), [numeric examples](../contracts/configuration-examples/grant-overlay.json)
and [Configuration views](../walkthroughs/configuration-walkthrough.html) now follow
this model. The former general-overlay walkthrough/fixtures/checker are retained as
superseded history (private historical evidence; not distributed).
Current bounded design checks cover 9 positive, 33 negative and 8 invariants; production schemas,
pointer/rollout/drift execution and real OCI qualification remain open. C3 is not complete.


### D30: accepted complete managed objects and full-list overrides

State: accepted direct user requirements, 21 October 2026. Supersedes D29's numeric quota editor and
no-policy-override restriction. One root OTM policy with administrator-authored statement list;
one root OTM quota policy with administrator-authored statement list; one root monthly budget with
no alert rules; one root OTM namespace with defined keys/static values and root default per key.
Policy/quota overrides copy the assigned baseline list, then replace that complete category's list
inside the same bound object. Budget amount alone is overridden; tag overrides remain outside V1.

The user also explicitly selected required review when a new baseline changes an overridden
policy/quota: compare old baseline/new baseline/full override, then keep/edit/clear before updating
that target. No automatic merge/discard or append. Review is tied to exact content/revisions. Other
eligible targets could proceed under this earlier boundary; D31 below supersedes that pre-start
behavior and requires all reviews resolved. Current-for-new version capture and existing explicit bulk updates
remain accepted; an older assigned version alone is not drift.

[Chapter03](../engineering-design/03-templates-and-drift.md) specifies root bindings, in-place statement replacement,
namespace/key/default dependencies and daily comparisons. Preserve mandatory access through a single
coordinated root policy binding; no separate hidden OTM policies per workflow/profile. Exact access
composition and provider qualification remain open C3/C4 work. Child-root budget placement is required
and must be qualified, not silently replaced by a parent-owned budget. Defaults do not backfill tags.

The [walkthrough](../walkthroughs/configuration-walkthrough.html),
[full-list fixtures](../contracts/configuration-examples/grant-overlay.json) and
bounded check receipt (private historical evidence; not distributed)
now follow D30. Prior D29 artifacts are retained as history (private historical evidence; not distributed).
The reference checker covers9 positive,34 negative and7 invariants without OCI calls; no production
resolver/rollout/drift engine or database migration is introduced. C3 remains in progress.

Current D30 checkpoint review (private historical evidence; not distributed)
records corrected scope references, bounded evidence and remaining qualification gaps.


### D31: connected publication flow and all conflicts before bulk start

State: accepted direct user instruction,21 October2026. The baseline walkthrough must show the actual
button journey from creation/publication to Update existing tenancies, not depend on a screen selector.
Bulk review shows only ready count plus conflict exceptions. Click a tenancy to compare old baseline,
new baseline and override, then choose Use new baseline or Keep override and return. No inline edit
required for conflict resolution; regular override editing remains a separate assigned-version flow.

**All reviews must resolve before the bulk update starts.** This supersedes D30's early ready-subset
execution. Decisions stage the proposed plan only, with no active assignment/override changes or OCI
writes. Counts are per tenancy; several block conflicts do not double-count a tenancy. The start
button and server gate require zero unresolved reviews and current complete plan/revision evidence.
No skipping/deselecting conflicts to start a subset. After acceptance, independent target progress,
provider failures/unknown outcomes/retries remain; this is not atomic fleet-wide OCI execution.

[Chapter03](../engineering-design/03-templates-and-drift.md#d31-baseline-publication-to-existing-tenancy-update) defines the
connected screens, stage boundary and stale-review handling. The [walkthrough](../walkthroughs/configuration-walkthrough.html)
implements the journey in memory with explicit simulated publication/queueing; it does not change
the organization app/database or create real OCI operations. The earlier D30 artifact is retained as
history (private historical evidence; not distributed).

D31 design review (private historical evidence; not distributed)
and batch-gate receipt (private historical evidence; not distributed)
retain the bounded design evidence.

The D31 UI review (private historical evidence; not distributed)
records the actual connected journey and18 responsive checks, with screen captures linked there.

### D32: baseline history, override entry points and focused issue queues

State: accepted direct user instruction, 21 October 2026. Configuration opens on a tabular published
baseline history with **New baseline** and **Create tenancy override** actions. Historical version
views are read-only and do not change current-for-new, assignments or bulk targets. Override creation
starts from Configuration or tenancy inventory/details, not the baseline editor; it uses the
selected tenancy's assigned version. The connected D31 publication/bulk journey remains unchanged.

Organization Exceptions belongs under Employees. Configuration → Drift restores an exception-only
queue for confirmed Missing/Different observations. Healthy objects, unable-to-verify checks, older
baseline versions and pending bulk conflict reviews are distinct. Tenancy table exception icons
open an exact issue, or a tenancy-filtered list when several issues exist; check/access issues remain
reachable without inflating the confirmed-drift count. Detail pages expose expected/observed facts,
observation freshness and appropriate guarded repair/manual recovery. Queued repair is not verified
resolution. Deep links preserve identity and unknown targets show a visible error.

[Chapter03](../engineering-design/03-templates-and-drift.md#configuration-navigation-and-issue-resolution-d32) and
[specification screens](../product/oci-tenancy-manager-spec.md#screens) record the navigation contract. The
[configuration walkthrough](../walkthroughs/configuration-walkthrough.html)
implements illustrative navigation in memory only; no local application, database or OCI changes
are introduced. The prior D31 walkthrough is retained as
history (private historical evidence; not distributed).
C3 remains in progress; navigation approval does not qualify provider capabilities or production
execution contracts.

D32 UI review (private historical evidence; not distributed) and
browser receipt (private historical evidence; not distributed)
record the connected navigation, retained bulk gate and responsive evidence. The documentation
review found no material inconsistency across chapter03, the specification and this ledger.

### D33: Organization and Organization drift terminology

Accepted direct user instruction, 21 October 2026. Rename the Employees navigation area to
**Organization** and its review submenu to **Organization drift**, matching **Configuration drift**.
Update headings, breadcrumbs, links, back actions and empty-state language consistently. This changes
navigation terminology, not the existing actionable/informational review behavior. Configuration drift
remains a separate queue for confirmed OCI configuration differences. The walkthrough uses canonical
`#organization` / `#organization-drift` routes and preserves old route aliases. The local organization
application remains unchanged in this design checkpoint. The previous D32 walkthrough is preserved
as history (private historical evidence; not distributed).

D33 UI review (private historical evidence; not distributed)
verified the renamed routes, legacy aliases, labels and navigation at desktop and mobile widths.

### D34: approved prototype page authority and shared design menu

Accepted direct user clarification, 21 October 2026. The working organization prototype's directory
and review layouts remain correct and authoritative. Configuration walkthrough Organization and
Organization drift bodies are placeholders, not alternative approved designs. Make those menu
entries non-clickable to avoid implying otherwise; preserve compatibility direct routes with an
explicit placeholder only, no fake employee list or misleading empty queue.

Back-propagate the current menu structure into the earlier onboarding and operations walkthroughs.
Use one small shared design menu manifest/renderer and stylesheet for current walkthroughs, keeping
labels, order, nested grouping, context and responsive treatment consistent. Existing workflow pages
and gates remain intact. Preserve historical checkpoints and the working application's UI/data.
The [screen authority map](../ui-screen-authority.md), [UI baseline](../../DESIGN.md) and
[review policy](../ui-ux-review-policy.md) establish how future changes avoid conflicting designs.

D34 follow-up: retain **Assigned baseline** and a clickable **Configuration issues** indicator as
explicit additions to the approved tenancy inventory. Keep its existing fields, counts and controls;
assignment does not imply verified application, and unknown checks are distinct from confirmed drift.
This is a design requirement, not a claim that live OCI data exists in the prototype.

D34 validation: the UI review (private historical evidence; not distributed)
and browser receipt (private historical evidence; not distributed)
record the common menu, non-interactive organization context, retained tenancy columns/issue links,
query-preserving local navigation and representative workflow checks. Root inspected the desktop
and mobile captures; the documentation reviewer found no material source-authority inconsistency.

## Configuration data-model catch-up — 21 October 2026

The user selected catching the design up before expanding more functional screens. The new
[chapter10](../engineering-design/10-configuration-data-model.md) is a proposed physical/logical model for accepted
baseline, override, bulk-review and drift behavior: eight C3 tables plus explicit existing-table
extensions, reusing the two C2 operation proposals. It includes field/key/index proposals,
transaction boundaries, readable query projections, screen/API mappings and failure-test scenarios.
The [separate proposed ER](../architecture/diagrams/configuration-data-model-proposed.svg) does not replace
the [implemented ten-table ER](../../prototype/docs/organization-er-diagram.md).

Proposed simplification for review: one immutable per-tenancy configuration revision contains the
baseline reference and complete override object; no separate override-head/assignment-history
truth. Desired versus last-verified pointers, immutable observations and persistent issue episodes
remain distinct. Plans stage changes until all D31 candidate reviews and current guards pass.
Outbox/audit reuse requires explicit production extensions; today's outbox cannot send config alerts
without an organization recommendation. No migrations, runtime behavior or UI changes are made.

Next: review the proposed grouping, then finish required-access/credential and usage/notification
contracts and reconcile the unified production ER before implementation. C1–C6 remain open; rendered
diagrams and document consistency checks are not database/OCI qualification.

## Full production model and explicit configuration fields — 21 October 2026

The user requested all data-model areas be caught up and every UI/prose field accounted for.
[Chapter11](../engineering-design/11-production-data-model.md) now covers registry name/OCID/home region, organizational
reuse, association transitions, operations, identity/access/credentials/sessions, financial captures,
audit/outbox, recurring work and restore evidence. [Chapter10](../engineering-design/10-configuration-data-model.md) now
uses explicit policy/quota statement array columns, numeric budget fields, typed tag defaults and
nullable override columns instead of opaque baseline/override blobs. Created per-tenancy object
OCIDs remain in managed bindings; reusable baseline rows never contain fleet-instance OCIDs.

Shared proposed checks/observations/issues are now named otm_tenancy_check, otm_object_observation
and otm_tenancy_issue, with typed configuration/access intent references. The proposal totals 28
application tables (10 reused +2 operations +8 configuration/shared +6 access/session +2 finance),
not 28 implemented tables. The implemented ER remains ten tables. Multiple scoped diagrams and the
screen-field coverage guide replace any implication that abbreviated figures are full field lists.

All area chapters link this common contract. UI layouts/prototype data are unchanged. Remaining
provider/MFA/billing/runner/concurrency/migration/performance qualification gates remain explicit;
field completeness alone is not implementation readiness.

## Access-health design slice — 21 October 2026

[Chapter12](../engineering-design/12-access-health-and-repair.md) connects the first C4 Required access screen to explicit
check/observation/assignment/repair fields. The [new walkthrough](../walkthroughs/access-walkthrough.html#missing)
separates confirmed missing user, failed automation authentication, identity/grant matching, and
unqualified console recovery. It reuses the shared menu and has a scoped tenancy-detail entry;
no organization layout or prototype state changed. At that first access checkpoint D35 was pending (now accepted below): a
visible required-access statement section in the single policy was initially a proposal. D35 below
now adopts it and refines full-block overrides. Named support and disclosure/rotation screens follow.

The access-health UI review (private historical evidence; not distributed)
passed 17 interaction checks and 16 responsive layouts; field review corrected a combined-check display
to expose each assignment’s own evidence/time. [The standing field-coverage gate](../ui-screen-authority.md#field-coverage-gate-for-every-design-slice)
now governs future narrative, renders, contracts and model updates. C4 remains in progress; D35 composition is selected below, while
MFA/provider qualification remain open. No database, migration or working prototype changed.

## D35: visible protected required access in the single policy

Accepted 21 October 2026, option A. Each OTM policy combines administrator-authored baseline/override
statements and visible read-only generated required-access statements. An override replaces the
authored block only. The same bound OCI policy object receives the combined list; no second policy
or hidden grant is created. Owner OCI administration is unchanged. Quota/budget/tag semantics and
D31’s all-conflict batch gate remain binding.

The immutable tenancy configuration adds `required_policy_manifest`,
`required_policy_manifest_hash` and `policy_render_contract_version`. The generated statement
provenance/resolved arrays live in typed immutable rendering evidence. Root-policy requirement
changes create a new local configuration revision using the same baseline/overrides; no new global
baseline is published. [The exact field contract](../engineering-design/10-configuration-data-model.md#d35-required-policy-manifest-and-rendered-evidence)
and [access behavior](../engineering-design/12-access-health-and-repair.md#required-grant-composition-d35-a-accepted)
govern the editor, override/conflict preview, operation payload and complete policy drift comparison.

Global baseline screens show per-tenancy required examples; current tenant screens show the combined
list. Historical baseline values remain authored-only. Template/profile updates are explicitly pinned,
not live-library rewrites. No prototype/database/provider change occurs in this design checkpoint.

D35 validation: the UI review (private historical evidence; not distributed)
records 18 targeted checks and 32 representative layouts, with a bounded later generated-context
staleness/refresh recheck. Field audit and regenerated ER include all three new manifest/renderer
columns and resolved statement provenance. `scripts/check_design_docs.py`, JS syntax, inline docs
and Ruff pass. The older D30 authoring-phase checker still passes 9 positive/34 negative/7 invariant
cases; those are structural examples, not a production composer or executed DB/OCI tests.

During this update an edit accidentally copied the hub into the product spec. It was restored from
the SHA-verified source checkpoint plus exact subsequent task-local edits. All 57 prior criteria
remain, with AC58 added for D35; the documentation reviewer verified restoration and hashes.
A retained header/section/criteria guard rejects this overwrite in an in-memory regression probe.
The recovery receipt (private historical evidence; not distributed)
records provenance. A source-only D35 artifact checkpoint is saved under
`.local-dev/checkpoints/d35-design-2026-10-21/`; it is not a database or full-project backup.

## D36: local human console accounts

Confirmed 21 October 2026, option A. Human console users in child tenancies use local identity-domain
accounts. OTM administrator SSO stays separate; V1 does not depend on child federation. This does
not select an MFA exemption for the custodial recovery account.

[Chapter13](../engineering-design/13-local-support-and-emergency-access.md) and the [human access walkthrough](../walkthroughs/human-access-walkthrough.html#access-ready)
now develop named activation/MFA/grants/cleanup and separate emergency review/disclosure/uncertain
rotation states. All screen fields map to named grant/assignment/binding/credential/observation
records or transient/secret-response boundaries. D37 now fixes named support cleanup four hours from acceptance, with no extensions or early-end control; the
existing emergency four-hour first-disclosure rotation rule does not change. No prototype data,
provider accounts or credentials are created. C4 remains in progress.


D36 design validation: the human access UI review (private historical evidence; not distributed)
records 28 interaction checks and 28 responsive combinations. Field review closed the domain
label/console-destination gap: the separately verified `domain_metadata` properties cannot reuse the
API/SCIM endpoint as a login URL. Chapter13 maps every screen value/control to explicit fields or
transient/nonsecret/secret-response boundaries. The proposed core ER exports are regenerated.
The retained design checker validates 18 documents, 13 configuration fields, five human-access
fields and the 28-table proposed inventory; inline documentation, Ruff and JS syntax pass. These
are static design checks, not executed provider permissions, MFA, cleanup, credential or DB tests.
A verified source-only checkpoint is saved at `.local-dev/checkpoints/d36-design-2026-10-21/`;
it excludes runtime state, live data and secrets.


## D37: fixed named-support deadline and mandatory cleanup

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

Accepted 24 October 2026, option A. Named support has a fixed four-hour deadline from request
acceptance, including activation/MFA setup. Cleanup is mandatory even for abandoned setup. No
extensions and no user-facing End access/session early action. The existing grant fields capture
14400 seconds, request_acceptance and accepted_at+4h; no new table/column is needed. Failed/unknown
cleanup remains visible and blocks replacement grants until verified. Chapter13 and the walkthrough
are updated together. The separate independent recovery account/credential exists to handle loss of
automation authority; the user is revisiting whether its in-app disclosure UI is needed. D37 does
not remove D19 recovery or select custodial MFA. No prototype data, account or credential changed.


## D38: independent recovery retained; app-style walkthroughs

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

Accepted 24 October 2026. Retain independent recovery alongside routine named support. The two access
walkthroughs now model short product screens and confirmation/status interactions rather than showing
flow documentation. Request → setup → grants, cleanup attention/complete, recovery confirmation/window
and uncertain rotation remain backed by the existing proposed model. Optional scenarios are collapsed;
engineering detail and the exact field/transition map live in chapter13. Required-user diagnostics
are collapsed, and repair acknowledgment leaves the issue open. No new table/column or real credential.

[Open Administrator access](../walkthroughs/human-access-walkthrough.html#access-ready),
[Recovery](../walkthroughs/human-access-walkthrough.html#emergency-review), or
[Required users](../walkthroughs/access-walkthrough.html#missing).
The current app-flow review (private historical evidence; not distributed)
supersedes earlier layouts; current validation is recorded there. Custodial MFA/permissions remain
qualification work; production-ready recovery is not implied. This presentation rule applies to future
design slices while preserving the accepted organization prototype and other workflow semantics.


## Access UI approval and C4 contract checkpoint — 24 October 2026

The user approved the D38 app-style access walkthroughs and asked to proceed. Preserve that presentation
for subsequent screens. This is not approval of custodial MFA, a deployable permission profile or a
hard session-cutoff guarantee. [Chapter04's profile/secret/dependency matrix](../engineering-design/04-identity-and-access.md#access-profiles-and-secret-boundaries--c4-checkpoint-24-october-2026)
now documents each app/parent/child/human context, exact secret boundaries and due-work behavior when
automation or OTM is unavailable. Eight named provider/facade cases are planned, not claimed executed.
Existing fields suffice; no new table, migration, prototype data or OCI account changed.

D39/D40 now select recovery-only MFA exemption and the single access flow. Exact provider behavior, independent custody and operational qualification keep C4 open. C5 next expands financial dashboard/detail/freshness interactions,
and C6 closes infrastructure, restore/CI/CD and development packages. No blanket design-complete claim.


## D39: V1 recovery authentication and workflow scope

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

24 October 2026. The user selects an MFA exemption for only the persistent recovery user, with
one distinct OCI Vault secret/password per managed tenancy and rotation in both the child user
and corresponding secret after use. Ordinary named human accounts keep MFA. No central federation
or shared TOTP custody service is adopted for V1. This is an accepted design direction, not a live
sign-on policy change or proof that every identity-domain page supports the same exemption.

Bind the exception to the exact managed recovery identity, or a dedicated group restricted to that
identity. Never exempt the general Administrators group, all OTM admins or all users. Observe its
policy scope/precedence and group membership as managed access intent/drift. Qualify console access
and actual automation-restoration tasks: My Profile/My Apps have separate MFA enforcement. No
unsupported workaround or domain-wide MFA removal is authorized by this choice.

Preserve the accepted per-tenancy first-authorized-disclosure exposure window and four-hour rotation
obligation; this message specifies no replacement timer. Stage a candidate Vault version before the
child password write; reconcile and publish the exact usable version only through qualified evidence.
A Vault update alone is not a child-password update; partial/unknown effects block further disclosure.
Manual independent recovery is still required when automation cannot perform the rotation.

The user initially retains temporary local named administrator creation, then asks whether rare human
access should instead use only the recovery mechanism. D40 now accepts that consolidation: named provisioning/cleanup is deferred and current UI/model requirements use recovery-password access only. The comparison is named MFA-protected access and
identity-bound activity/cleanup versus a simpler shared-password retrieval/rotation path. Rotation
is not proof that an existing shared-account session has ended, and checkout audit is not exact
attribution of every subsequent OCI action. No new table/column, production account or real secret.

## D40: single V1 administrator-access flow

Accepted 24 October 2026. The user approved simplifying human access to the persistent recovery account
and requested model, design and screen updates. This resolves the consolidation question in D39 and
supersedes D19/D37 named-account provisioning/cleanup for V1. D38's concise product-screen treatment
and independent recovery requirement remain. There is no temporary support-account operation in V1.

The persistent recovery user and automation signer remain separate. Use distinct per-tenancy Vault
passwords, the selected recovery-only MFA exemption, audit/notifications on every retrieval and a
four-hour rotation obligation anchored at the first authorized disclosure attempt. Joining retrievals
share the original deadline/version; lost responses count. Stage and reconcile child/Vault rotation,
block unknown outcomes and preserve independent recovery. Rotation does not imply session termination
or exact attribution of actions under a shared account.

Chapter11/core ER simplify the retained disclosure-request table and remove grant-owned access
assignments/cleanup fields, keeping 28 proposed application tables. Chapters04/13 and the current access
screens describe the same single flow. This is proposed design only; the working prototype database,
provider accounts, secrets and application operations have not changed.

D40 validation: final design/UI review (private historical evidence; not distributed)
records84 passing browser checks plus retained documentation, field/ER, syntax and lint checks.
Independent source/screenshot review and narrative/model consistency review found no remaining
material issue. Source-only verified checkpoint: `.local-dev/checkpoints/d40-design-2026-10-24/`;
this is not a database backup, migration or provider qualification.

## C5 started: financial visibility, D41 resolved — 24 October 2026

The user approved D40's single human-access walkthrough and asked to proceed. That approval concerns
the design, not live provider qualification or implementation. [Chapter14](../engineering-design/14-financial-journeys.md)
starts the financial screen/field contract using the two existing proposed financial tables. No
prototype/schema/UI or OCI change was made in this initial slice.

D41 now selects each child’s managed Budget object through its existing automation context. The earlier parent-first recommendation was not accepted. Historical budget/cost reporting and Usage API backfill are post-V1. Subsequent
review covers reporting basis/currency/cadence/freshness, UI details/thresholds, facade fixtures and
operational history/alerts. No new C4 authentication decision is reopened.

## D41: accepted child Budget financial source; history post-V1

Accepted 24 October 2026. Read the exact bound root OTM Budget in each child through existing automation.
One snapshot supplies budget amount, current-cycle actual, complete cycle-end forecast and OCI spend
computation time. Never add actual to forecast, infer unknown currency, substitute parent budgets or
turn missing/unverified values into0. OTM retrieval time is distinct from OCI calculation time.
Historical reporting, prior-month selection, trends/backfill and parent Usage API financial collection
are post-V1. Retained observations/audit are correctness evidence, not a history-reporting feature.

Chapters05/08/11/14, the finance ER, product requirements and call-inventory scope are aligned. Two
existing proposed financial tables suffice; no prototype migration or provider call occurs. Exact
no-alert-budget calculations, current cycle/rollover, currency, permissions and decimal normalization
remain real-provider qualification. D42 accepts daily plus manual refresh. Dashboard indicators and rendered cost screens follow that reporting-policy review.

## D42: accepted daily collection plus manual refresh

Accepted 24 October 2026, option A. Daily jobs read eligible children’s bound Budget objects; admins
may request an additional refresh. Keep OCI calculation time distinct from collection time. Manual
refresh does not imply OCI recalculation. Preserve independent child progress, stable delivery keys,
request idempotency, original source/cycle context and credential-work capacity. Fleet and single-child
scope are explicit; the dashboard itself reads persisted snapshots. Exact runtime time/jitter and
qualified freshness policy remain implementation/operations settings. No additional OCI alert rule,
resource action or historical reporting is introduced.

## D43: accepted spend indicators; original separate-list layout superseded by D44

Accepted 24 October 2026, option A. Amber indicates qualified forecast above observed budget; red
indicates actual above observed budget. Data status remains separate; there is no 80% early warning,
cost-email dispatch or automatic resource action. The current provider budget is the comparison,
with desired/pending override shown separately. Historical reporting remains post-V1.

[Cost list](../walkthroughs/financial-walkthrough.html#costs) and
[shared-tenancy detail](../walkthroughs/financial-walkthrough.html#tenancy?tenancy=jordan)
now demonstrate the proposed layouts. Existing inventory and tenancy pages link them; the working
organization prototype is unchanged. Layouts are ready for user review, not already accepted as final.
Chapter14 records each control/status field and its model/derivation. Current-cycle snapshot, currency,
source timestamps and per-child uncertainty remain explicit. C5 notification/operations contracts,
provider qualification and C6 handoff still remain; this is not a blanket design-complete claim.

Financial slice validation: review and captures (private historical evidence; not distributed)
record 99 passing browser checks plus retained model/doc/syntax/lint checks. Source-only verified
checkpoint: `.local-dev/checkpoints/d43-design-2026-10-24/`. No production database or provider state
changed; cost layouts remain ready for user review.

## D44: accepted unified Tenancies dashboard

Accepted direct user instruction, 24 October 2026. There is one Tenancies dashboard, no Inventory/Costs
tabs. Five columns consolidate existing fields: Tenancy (name/type/owner-inclusive count plus cost-data
information), Owner/LOB, Configuration (assigned baseline/override/linked issues), Actual/Budget and
Forecast. Timestamp details may use a hover/focus/tap information control; important missing/stale/
unverified data remains visible. D41 source, D42 cadence, D43 warnings and post-V1 financial history
scope do not change. Counts include the active owner and distinct members, using the full filtered
scope for summaries and preserving existing query/navigation controls.

The shared Tenancies menu and legacy list aliases resolve to
[one dashboard](../walkthroughs/financial-walkthrough.html#tenancies). Tenancy detail
and its existing Configuration links remain. [Chapter14](../engineering-design/14-financial-journeys.md), [DESIGN.md](../../DESIGN.md)
and the [authority map](../ui-screen-authority.md) record field/interaction ownership. No table, column,
prototype/database or provider change is implied. D44 source/layout/browser review (private historical evidence; not distributed) passes 29 focused journeys and 84 responsive/popup checks with independent source/screenshot review. D46 subsequently approves the final dashboard; real-provider qualification remains separate. Earlier D43 receipts describe the superseded two-list layout.

## D45: accepted independent spend highlights and retrieval-only list tooltip

Accepted 25 October 2026. Keep the unified five-column Tenancies dashboard. Actual and forecast compare independently to the same qualified observed budget: red actual above budget and amber forecast above budget may appear simultaneously (Grant actual240/budget200/forecast320). Qualified below-budget numbers may be green; exact-at-budget and unqualified/unavailable numbers stay neutral. Number backgrounds replace redundant second-row spend badges and the list's overall warning badge, with screen-reader-only per-value status and hover titles preserving textual meaning. Detail may retain a highest-severity summary alongside independent values.

The accessible hover/focus/tap tooltip exposes OTM retrieval time, optionally status/cycle, but no OCI calculation timestamp. Important missing/stale/prior-cycle/unverified-currency and pending-budget messages remain visible. Retain calculation time in the internal snapshot and stale-data qualification and technical detail. D45 supersedes D43's exclusive overall-warning presentation only: D41 source/observed-budget qualification, D42 daily/manual cadence and post-V1 history remain unchanged. No model field/table or cost automation is added. [Chapter14](../engineering-design/14-financial-journeys.md) and [UI authority](../ui-screen-authority.md) carry the field contract. D45 final design/UI review (private historical evidence; not distributed) passes 38 browser journeys and 84 responsive/popup checks with independent source/screenshot review. User visual acceptance and provider qualification remain separate.

## D46: approved dashboard and independent monetary sorting

Accepted 25 October 2026. The user approved the final D45 dashboard and explicitly retained separate
Actual and Budget sort controls inside the shared Actual/Budget header. Actual selects
`actual_spend`; Budget selects `observed_budget_amount`, never a pending desired override. Each key
has ascending/descending behavior, with unavailable values last in either direction. A new key starts
ascending; activating the selected key toggles direction. Sorting resets the page to 1 and preserves
filters/page size; detail return preserves the selection and valid page. These are query-state
controls over existing snapshot facts, not additional visual columns or stored sort-status fields.

This approves the final five-column layout, independent amount colors, retrieval-only tooltip and
existing contextual links, not production OCI behavior. The D45 review (private historical evidence; not distributed)
records 38 interaction and 84 responsive checks; no new runtime/browser run is claimed for this
acceptance-only update. AC66, the [UI baseline](../../DESIGN.md), [authority map](../ui-screen-authority.md),
[financial journeys](../engineering-design/14-financial-journeys.md) and proposed model now record the same contract.

Next design slice: [C5 collection and operational events](../engineering-design/15-collection-and-operational-events.md).
Finish its facade/normalization, publication/query, scheduling/failure and notification-policy
contracts before declaring C5 closed. C6 then develops production delivery, database security/indexes,
backup/restore and executable development packages. Earlier chapters' remaining provider/API/schema
qualification gates remain explicit; dashboard approval does not mark all checkpoints complete.

## D47: accepted email-only operational delivery

Accepted 25 October 2026: email in V1; Slack later. Keep the notification port extensible but do not
build Slack setup, credentials or dispatch for V1. Required triggers, recipients, urgency, source-
event/outbox atomicity, manual Send boundaries and uncertainty/restore guards remain unchanged.
The [delivery contract](../engineering-design/15-collection-and-operational-events.md#d47-delivery-contract-email-in-v1)
maps messages, sender references and attempt results to the existing runtime policy, outbox and audit
fields. No new table, migration, UI or actual email send is part of this design update. AC67 records
channel scope. Email provider/sender/endpoint and result semantics remain C6 qualification work.

D48 now selects one administrator email after bounded cost-read retries are exhausted. It does not change immediate access-loss, disclosure or urgent rotation notifications, and it cannot add cost-threshold emails. C5 remains open for lifecycle notification policy and remaining source/fixture contracts.

D47 validation: delivery design review (private historical evidence; not distributed)
records the cross-tier audit and captured-provider-context correction. Documentation, field/link,
inline-documentation and Ruff checks pass; no live email/provider or new browser test is claimed.

## D48: accepted failed-cost-read email after retry exhaustion

Accepted 25 October 2026, recommended option. Failed acquisition attempts are visible immediately;
only bounded automatic retry exhaustion creates the initial administrator email. Continuing retries,
manual refreshes and daily failures remain one incident until verified same-source read recovery;
relapse is a new episode. No recovery/reminder emails, 24-hour delay or owner/manager/designee
expansion is introduced. Null forecast, normal computation lag and over-budget values are not this
trigger; existing urgent access/disclosure/rotation notices remain binding.

[Chapter15](../engineering-design/15-collection-and-operational-events.md#d48-accepted-alert-after-automatic-cost-read-retries-are-exhausted)
and chapter11 trace the episode to immutable audit data, current collection/operation context and
existing outbox uniqueness. Source-scoped coordination must prevent late/duplicate results from
reopening or duplicating an incident. AC68 records the policy. No new tables, runtime delivery,
UI or database changes are part of this design adoption. Retry counts/backoff and real provider/
email/transaction behavior remain explicit implementation/C6 qualification.

C5 continuation now has an explicit [remaining-review matrix](../engineering-design/15-collection-and-operational-events.md#remaining-c5-review-items).
D49 now accepts lifecycle email for administrator action or terminal failure; D50 selects the responsible administrator only, with no automatic fallback. Collection/notification model examples and
normalization fixtures remain design work; real email/OCI and runner/restore qualification remain
later implementation/pilot evidence. No C5 completion is claimed merely from accepting D48.

D48 validation: incident-policy review (private historical evidence; not distributed)
records cross-tier/model review with no remaining material issue. Documentation/link/field, inline
and Ruff checks pass; incident-concurrency and provider/delivery cases remain planned, not executed.

## D49: accepted lifecycle action/failure emails

Accepted 25 October 2026. Email when an accepted lifecycle operation requires administrator action
or reaches known terminal failure. Routine progress and success stay in Operations; no new operation
state is introduced. Human-action waits and actionable Needs attention have deduplicated episodes;
provider/retry waits and uncertain external outcomes cannot be relabeled terminal failures to send
mail. [The contract](../engineering-design/15-collection-and-operational-events.md#d49-accepted-lifecycle-email-only-for-action-or-terminal-failure)
links exact operation/intent/step/transition evidence, affected children, partial-resource context and
existing outbox intent. AC69 records the policy. D50 selects responsible-admin-only routing with no automatic fallback. No UI,
provider, database or actual email change occurs in this design adoption. C5 stays open for the remaining typed source/normalization examples before C6 delivery/operations handoff.

D49 validation: lifecycle-policy review (private historical evidence; not distributed)
records cross-tier/state/model review with no remaining material finding. Documentation/link/field,
inline and Ruff checks pass; production transition/concurrency/email cases remain planned tests.

## D50: accepted lifecycle emails to responsible administrator only

Accepted 25 October 2026. The user selected only the responsible administrator, overriding the
previous proposed admin-team fallback. Initially this is the initiating authorized administrator;
explicit audited takeover may reassign responsibility without changing creator/activation history.
Lifecycle notices do not copy all admins, owners, managers or designees. Missing/ineligible/unreachable
routing stays visible/blocked for explicit correction or takeover. Other notification families keep
their required recipients. AC70 records the rule.

[Chapter15](../engineering-design/15-collection-and-operational-events.md#d50-accepted-responsible-administrator-only) and
chapter11 map assignment/revision, frozen recipient, correction and delivery-context evidence to
existing fields. Reassignment cannot rewrite accepted email recipients or bypass uncertain-send
reconciliation. No automatic takeover, new table/column, UI or actual delivery is implemented by
this adoption. C5 notification policy decisions are settled through D50; typed source/normalization
examples and contract validation remain before the C6 production/development handoff.

D50 validation: routing-policy review (private historical evidence; not distributed)
records the cross-tier/model review with no remaining material issue. Documentation/link/field,
inline and Ruff checks pass; actual entitlement/reassignment/delivery race tests remain planned.


## C5 technical contract review — 25 October 2026

[Chapter16](../engineering-design/16-c5-contract-review.md) adds a closed, design-only Budget/email schema,49 positive
examples,43 negative controls, an isolated checker and a field-to-model map. The independent
review closed failed-read prior-scope, obsolete-source retention/order and monthly-response
qualification gaps. The receipt (private historical evidence; not distributed)
records exact hashes and limits. Provider Budget field inspection is pinned; no live calls or mail.

No new product decision, UI change, application dependency, migration or table is introduced.
The model remains10 existing plus18 proposed tables; cycle facts fit existing `period_evidence`,
and mail context/corrections fit typed event/outbox evidence. This establishes a reviewable C5
contract checkpoint, not full C1–C5/provider/production completion. [C6](../engineering-design/06-platform-and-delivery.md)
next settles recovery targets, environment/deployment design, database security/indexes/restore,
CI gates and implementation packages. D46's approved dashboard and D47–D50 remain binding.


## C6 opened: production and development handoff — 25 October 2026

[The working plan](../engineering-design/06-platform-and-delivery.md#c6-working-plan--25-october-2026) now proposes environment
boundaries, one modular service image with API/worker roles, least-privilege database grants,
query-driven index acceptance, externally fenced recovery, CI/promotion gates and dependency-ordered
P0–P5 work packages. A narrative-to-model map assigns operational metadata to existing runtime,
workspace, operation/audit and infrastructure authorities. No production migration or new table.

D51 accepts 15-minute RPO/4-hour RTO; D52 limits these to in-region recovery in V1.
Neither target extends credential deadlines or qualifies managed-service restore behavior. External
fencing/evidence, provider/service access, exact DDL and runner atomicity remain gates. One engineer
with Codex remains a valid staffing default; parallel work follows stable P0/P1 contracts and a single
migration owner, with calendar estimates revisited after measured vertical-slice throughput.


Source-only checkpoint for this review: `.local-dev/checkpoints/c5-contracts-c6-start-2026-10-25/`.
Its archive/manifest include the current design, proposed ER, approved walkthrough assets and new
C5 contracts/checker/validation receipts. It complements earlier full-project/prototype checkpoints;
it is not a database, secret, runtime-state or Git backup.


## D51/D52 accepted: production recovery objectives — 25 October 2026

D51 accepts **15-minute RPO** and **4-hour RTO** engineering targets. D52 scopes them to **in-region
recovery** in V1; full-region loss requires separately reviewed future disaster recovery. These
are not measured service guarantees. [Chapter06](../engineering-design/06-platform-and-delivery.md#d51d52-accepted-recovery-objectives-and-in-region-qualification)
defines incident/recovery clocks, committed-write evidence, read-only versus safe-service readiness,
external fencing, quarantined unknown effects and independent credential-deadline recovery.

The nonsecret runtime-policy example maps targets to existing workspace settings; typed recovery
receipts map to existing operation/audit storage. No application table, migration, UI or real restore
is introduced. AC71/AC72 record the accepted objectives/scope; provider retention/lag/fencing and
measured qualification remain C6 gates. Next, make the external recovery controls and deployment
release protocol concrete without letting a restored database authorize its own replay.


## D53 accepted: testing and protected master — 26 October 2026

The user requires unit tests with 95% or greater coverage, Playwright UI integration, database tests
using a disposable Docker database, all tests on every build and mandatory pass/coverage gates for
PR merges to protected `master`. [The canonical test/merge policy](../engineering-test-plan.md#d53-required-test-and-merge-gates)
operationalizes line coverage over complete first-party source, separate prototype/backend/frontend unit reports,
real UI/API/persistence and PostgreSQL checks, fail-closed required statuses and P0 protection probes.

Updated spec AC73–AC76, platform/implementation/review plans, README and AGENTS. No production table,
application dependency or remote repository setting is changed; the existing reusable prototype/test
work remains intact. Do not infer 95% measured coverage or implemented Playwright/CI from this decision.




## D54 accepted: Vault CURRENT, manual restore and simplicity — 26 October 2026

Normal passwords resolve the bound stable secret OCID with `stage="CURRENT"`. Exact returned versions
remain audit evidence; staged candidate versions remain required for interrupted rotation. API-key
selection is unchanged. [Chapter17](../engineering-design/17-recovery-and-release.md) now contains the short manual restore
runbook. Pause the deployment, hold restored work, review OCI/Vault/mail state and explicitly resume
safe work. Original credential deadlines and D51–D53 remain binding.

The external control buckets, per-dispatch receipt/dependency/exposure journal, independent release
CLI/manifest, extra execution envelope and their active schemas/checker/reports have been removed.
Their earlier source-only checkpoint is historical, not current work or evidence. Unused workspace
recovery mirrors were removed from the proposed ER. No extra secret-locator column/table is added.

The standing design rule is simplest adequate V1 behavior, with human recovery for rare cases where
appropriate. Retain critical correctness/security checks and ask before introducing substantial
edge-case infrastructure. Continue C6 with minimal feature-ordered migrations, query-driven indexes
and concrete required CI jobs. Do not implement all 28 proposed tables before a vertical slice.


## C6 database/CI handoff — approved 28 October 2026

[Chapter18](../engineering-design/18-database-ci-and-build-order.md) continues after the accepted D54 simplification.
It translates the existing model into feature-ordered migration/constraint/index tasks and D53
into concrete required CI jobs and enforcement checks. Start with the reusable org slice, test/
migration foundation and one durable simulated operation. Do not create all proposed tables or
add scale/recovery infrastructure before a working vertical slice needs it.

The simplicity audit removes the unapproved recovery machinery, retains essential targeting,
transaction, credential and quality guarantees, and defers unmeasured optimization. Chapter18 was reviewed and approved on 28 October. It is not a production migration, hosted-CI setup or whole-package final approval. Actual coverage gaps, runner/managed-PostgreSQL integration and remaining corporate/provider
inputs stay explicit implementation/pilot tasks.


## D55 accepted: explicit activation administrator identity at create handoff

28 October 2026. Following independent Astra review, the user selected a required create-only
activation administrator user OCID alongside tenancy/bootstrap OCIDs. Verify and preview/confirm
the exact same-child domain/OCI/SCIM cleanup binding before removal; retain immutable operation
intent/provenance and existing last-admin/replacement guards. Import preserves unrelated humans.
Existing intent/binding tables suffice; no new table or service. [Chapter11 field mapping](../engineering-design/11-production-data-model.md#create-only-activation-administrator-binding-d55).

Astra also identified a contradictory candidate open-issue unique key. It now includes both coverage
subject fields, preserving the already-designed independent automation/recovery incident scopes.
See [review and disposition](astra-design-review-2026-10-28.md). Whole-package user approval remains pending.


## D56 accepted: security review for each development slice

28 October2026. Add the persistent `security_review` subagent alongside documentation and UX review.
Review each completed slice/security-sensitive change for OWASP/application vulnerabilities,
authorization/target isolation, secret and real employee PII leakage, and dependency/CI/IaC supply
chain risks. [The security policy](../security-review-policy.md) defines the lightweight workflow
and blockers. Required automated `security` CI complements the independent review. P0 must sanitize
the first publish set and provide synthetic test fixtures; current local HR inputs/examples and
raw screenshots are not cleared for GitHub. Private repository status is not an exemption.


## D57 accepted: original A / Field Console

28 October 2026. After the side-by-side comparison, the user chose **left / original A** over
rounded A2. [DESIGN.md](../../DESIGN.md) is the visual authority: navy navigation, cobalt accents,
cool light surfaces, crisp 3px corners and technical typography. Apply it to future production
components and screen updates while preserving approved UX, fields and all quality/security gates.
The comparison (private historical evidence; not distributed) remains reference evidence;
no runtime/model/workflow change or whole-package Git/publication approval is implied.


## D58 accepted: OTM-managed administrator grants and independent local recovery

29 October 2026. The user selected application-managed administrator grants and a non-SSO initial
administrator retained as the application's break-glass path. Implement local authentication first
for testing; add corporate SSO later while retaining recovery. This is separate from child tenancy
D39/D40 recovery accounts. [Chapter19](../engineering-design/19-administrator-provisioning.md) records accepted scope,
bootstrap/admin-management requirements and the accepted strong-password plus SSO-independent MFA
policy (also used for local testing). Detailed schema/ER,
audit/API/UI integration was the next checkpoint at that decision. The later local implementation
below now supplies the grant/authentication foundation and React directory/revocation screens;
corporate integration and ordinary add/regrant remain future work.


## Configurable session policy and housekeeping

29 October 2026. The user accepted 30-minute idle/eight-hour absolute defaults with configuration,
logout invalidation and daily expired/revoked-session cleanup. The nonsecret
[application settings](../../backend/config/application.toml) and [implementation/usage guide](../reference/application-settings.md)
now define pinned per-session limits, explicit activity separate from polling, bounded cleanup and
the shared-config daily UTC CronJob renderer. No scheduler is installed or D58 sign-in enabled by
this change. Migration 0004 adds the sixteenth session field without a new application table.

## Current local application: HTTPS sign-in and administrator screens

The [local application guide](../reference/local-application.md) describes explicit setup,
private password/TOTP bootstrap and foreground HTTPS startup at localhost:8443. The real React
screens use current sessions/grants for login, logout, administrator listing and ordinary-grant
revocation. Search/sort/pagination and whole-workspace statistics are server-backed; Add remains
disabled without verified corporate identity enrollment. Tenancy/organization workflows and OCI
operations are not implemented by these screens.

The local launcher creates independent persistent Docker/private file state when explicitly run;
it never uses the organization prototype database or seeds a default account. Database-role
separation is real locally, but the same OS user can read owner/runtime state; this is not production
isolation. Current models remain six application tables with 23 generated structural schemas, including Operations, simulation and Audit History;
settings have 14 scalar keys. Final current-slice test/coverage/security results are recorded in
[development progress](development-progress.md), separately from dated earlier receipts. Corporate
SSO, Vault/ingress/API-role/OKE qualification, hosted CI and Git/publication clearance remain open.

## Current read-only Operations implementation

[Operations list/detail](../reference/operations.md) now provides real persisted inspection
visibility beside Administrators. Current intent/hash and session/workspace checks protect closed
public summaries, current steps and newest-50 event views in a read-only repeatable snapshot.
The source/field map states how every visible value is derived and why simulated inspection success
is not adoption. No table/migration, fake activity, OCI write, retry/start action, admission HTTP or
configured worker process is added. Full P1 remains incomplete. Final current-slice evidence belongs
in development progress; cloud operator-pod/Vault/OKE qualification remains separate.

## Current local durable simulation path

[Simulated submission and foreground worker](../reference/simulation.md) now extend read visibility
with a configured virtual-target form/API, atomic native enqueue and asynchronous recorded outcomes.
Explicit setup adds only missing worker custody/role and simulator configuration while retaining
existing accounts/data/owner/API passwords; it never seeds operations. Run API and worker separately.
Known-key backend replay is durable, while current-modal key memory does not survive navigation or
reload; the UI directs the administrator to check Operations before new work after uncertainty.
This adds no real OCI call/adoption/write, generic mutation recovery or production qualification.
The accepted cloud operator-pod procedure remains a separate future infrastructure gate.

## Current navigation and Audit History direction

30 October 2026: daily work remains Tenancies, Organization → Organization drift, and Configuration
→ Baselines / Configuration drift. **Activity & history** separately contains Operations and Audit
History; **Application settings** contains Administrators. Operations is visibility/troubleshooting,
with contextual remediation from higher-level resource/organization/configuration/access screens
and no generic Retry. Current simulated issue detail explicitly requires no action while retaining
`needs_attention`. Audit History's first slice reads existing immutable events with safe scoped
search/category projections and no raw JSON/edit/export; exact field authority follows its contracts.
Static Audit History remains inert without a fabricated page. Historical evidence/prototype logic
are preserved; this local decision does not authorize publishing or cloud deployment.

## Audit History implementation field authority

[The implemented Audit History guide](../reference/audit-history.md) now defines the exact public
query/entry/directory source mapping and historical actor cases. The feature reads existing immutable
events through current workspace/session authority and a coherent read-only snapshot. Search/category/
sort/paging expose safe metadata only; no raw JSON/edit/export or new table is introduced. Audit export
remains planned MVP work. The static menu keeps its Audit label inert because no static destination
exists. Current model totals are23 schemas/45 runtime modules; final evidence follows in development
progress. Cloud/operator, publication and full-MVP qualification remain separate.

## Validated local Organization workflow parity — 30 October 2026

[Checkpoint and validation status](organization-parity-checkpoint.md) ·
[Actual fields/ER and boundaries](../reference/organization-workflows.md).

The accepted prototype interactions now run locally with durable review episodes/history,
stable-person managed controls, registered simulated tenancies/memberships and asynchronous native
operations. Production physical names are `otm_tenancy`/`otm_tenancy_membership`; prototype counterparts
remain in their separate preserved database. Three new tables bring actual application storage to14
with nine forward revisions. Required gates and independent reviews passed; exact evidence is linked
from the checkpoint. Review
handoff is atomic at acceptance; association/directory finalization requires verified simulation.
Real OCI lifecycle, activation/IAM and full configuration/cost screens remain qualification work.

## Guided onboarding runtime checkpoint — 31 October2026

[Working local journey and storage/API dictionary](../reference/tenancy-onboarding.md): persisted create/import handoff, exact discovery, cleanup review and ordered simulated access verification;14tables, migration0010. Production OCI/Vault/baseline qualification remains separate.
