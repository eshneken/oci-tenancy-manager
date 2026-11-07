# OCI Tenancy Manager test and merge policy

Current quality requirements and behavioral acceptance inputs. These describe required tests,
not a claim that the production application, hosted CI or 95% measured coverage exists.
[Chapter18](engineering-design/18-database-ci-and-build-order.md) defines implementation gates;
[the current design hub](engineering-design/README.md) resolves later decisions.
The dated test-plan record (private historical evidence; not distributed) preserves earlier
milestone counts and proposed file names without making them current build instructions.


## Live-provider qualification tracking

Maintain the [real OCI manual test manifest](how-to/real-oci-test-manifest.md) with each slice.
Every behavior that cannot be verified locally needs a pending live case with prerequisites,
steps and expected outcomes. Passing simulated tests does not close live qualification cases.
Checkpoint reports must distinguish local interactive checks, automated coverage and pending OCI tests.

## D53: required test and merge gates

Accepted 26 October 2026. These are mandatory engineering requirements, not claims that CI,
coverage tooling, Playwright or hosted branch protection have already been configured.

| Required gate | Acceptance |
|---|---|
| Unit tests and coverage | All unit tests pass and unit tests alone achieve **at least 95% line coverage** of first-party executable application code. Enforce backend and frontend unit coverage separately when both application codebases exist; combining them cannot hide a low-coverage codebase |
| Playwright UI integration | Browser tests exercise the running application and its UI/API/persistence interactions, including important success, validation and failure flows at desktop/mobile sizes |
| Database integration | Use a fresh disposable PostgreSQL database in a Docker container for real database operations, migrations, constraints and transaction/concurrency tests |
| Every build | Run unit/coverage, database integration and Playwright suites on every CI build, including PR builds and builds on protected `master`; required suites cannot be omitted by path filters or marked optional |
| Merge eligibility | Any test failure or coverage below 95% blocks merging into `master`; missing/failed/cancelled/timed-out checks, absent coverage reports and skipped required suites cannot satisfy the gate |
| Protected branch | `master` is the protected integration/default branch. Changes enter through PRs and required successful checks; block direct pushes, force pushes and deletion, with no routine actor/admin bypass of the required gates |
| Security (D56) | Every completed slice receives independent security review; required every-build secret/static/dependency and applicable image/IaC checks must pass. Blocking findings and real employee PII/secrets prevent merge/publication. See [security policy](security-review-policy.md) |

### Coverage measurement

The 95% gate is **line coverage**, measured over the complete first-party application source scope,
including files not imported by tests. Use the unrounded measurement for threshold enforcement;
94.99% is below 95%. Unit-only coverage must meet the threshold without adding execution from the
Playwright or database integration suites. Retain separate reports for those suites if useful.
Report branch coverage as additional diagnostic evidence; D53 does not silently impose a second
95% branch-coverage threshold.

Version the coverage include/exclude configuration in the repository. Exclude test code, generated
code and third-party/vendor artifacts; any additional first-party exclusion needs explicit reviewed
justification. Do not lower the threshold, omit untested files or add trivial tests just to inflate
the number. Critical authorization, scope, failure/retry, destructive-operation and credential
branches still require behavior assertions; 95% aggregate coverage is not proof of their correctness.
Exact Python/frontend test-runner tooling and report formats are implementation setup work.

### Complementary backend test lanes

The required backend lanes partition the complete authored suite by the postgres marker:

- Backend unit/coverage runs every test selected by `-m "not postgres"` through
  `scripts/check_unit_coverage.py`. Its complete-source, unit-only coverage must remain at least 95%.
- Database/browser integration runs every test selected by `-m postgres` through
  `scripts/run_backend_postgres_tests.py`, including the native HTTP/worker/Playwright cases hosted
  by PostgreSQL-marked fixtures. It uses disposable Docker PostgreSQL, never a saved preview.

Each backend test belongs to exactly one of these selections. Deselection by the complementary
marker is lane ownership, not a skipped required test; the separately required companion lane must
still pass. Frontend unit/coverage remains independently required. An integration result alone
cannot establish the complete test gate or unit coverage. Do not reclassify tests to avoid execution.

The integration runner previously repeated the non-database unit suite. Removing that duplicate
execution preserves the same assertions and required checks. On 6 November 2026 the user approved
a 600-second aggregate integration deadline after the growing suite exceeded 420 seconds without
test failures. Individual test/browser/database limits and the 95% coverage gate are unchanged.
Earlier timed-out runs remain incomplete evidence. A fresh complete manual-presence run now passes all 351 postgres cases in 429.457 seconds, with zero failures/errors/skips and valid JUnit. Separate unit lanes pass 1,556 backend and 446 frontend cases. The disjoint backend selections cover 1,907 tests, not an overlapping sum. [Final local receipt](history/manual-presence-checkpoint-2026-11-06.md). The earlier deadline-expired attempts supply no completed full-suite evidence. Missing, failed, skipped, cancelled, timed-out or
invalid reports still block qualification. Do not add counts from overlapping historical runs.

### Prototype-to-production transition

The 95% merge gate applies to production application source from its first slice. Do not postpone
it until feature completion. The retained prototype is a separate characterization/demo project;
its current coverage shortfall remains visible as diagnostic evidence and does not block starting
the separate production foundation. As logic or JavaScript is ported into production, include all
of that application source and its meaningful tests in the appropriate production gate immediately.
Do not import an unmeasured prototype package behind a production wrapper or combine reports to
conceal a shortfall. Preserve the reusable domain scenarios and real-database regressions during
extraction. Both Python projects use the same complete-source gate implementation.

The [backend bootstrap](../backend/README.md) has its own isolated environment. A passing bootstrap
only measures code already present there; it is not evidence of completed business workflows,
frontend tests, database migrations, SSO or hosted merge enforcement. All required jobs/protection
still need implementation and negative-enforcement qualification before normal feature PRs merge.

### UI and database tests

Playwright runs against the actual built application with synthetic fixtures and the OCI/Vault/mail
facades in simulated mode. Tests must verify behavior and persisted outcomes rather than only
loading static walkthroughs. Cover navigation/search/sort/pagination, upload/drift resolution,
lifecycle/manual waits, configuration/overrides, access/recovery and the consolidated cost dashboard
as those features are implemented. Exercise relevant keyboard/focus and responsive behavior.
Capture sanitized failure traces/screenshots and reports; never expose real recovery credentials.

Use a disposable Docker PostgreSQL instance or isolated per-job instance, with unique database/schema
scope and cleanup on success/failure. Apply the reviewed migrations before exercising repositories,
constraints, atomic enqueue/audit/outbox, competing writes and rollback. SQLite or a mock cannot
replace these database integration checks. CI must fail if its database is unavailable rather than
silently skipping PostgreSQL-marked tests. Keep this isolated from the persistent laptop database
and all OCI production data. A local PostgreSQL container does not qualify managed-service privileges,
backup/restore, performance or the accepted production RPO/RTO; those remain separate pilot gates.

### Required CI and repository setup

Publish stable, required status checks for unit tests/coverage, PostgreSQL integration and Playwright,
or a mandatory aggregate check that fails unless **every** required constituent actually ran and
passed. Missing reports, empty test collection, dependency/setup failure and a skipped test job are
not successes. Bind results to the current PR/merge candidate; an old green revision cannot authorize
a changed candidate. Check the candidate against the current `master` base through an up-to-date
branch requirement or qualified merge queue, rather than trusting unrelated build results.

Retain test/coverage artifacts with their source revision. Parallel jobs/shards may reduce duration,
but their complete results must be aggregated before merge. CI uses disposable credentials/data and
no production mutation or real email access. Do not deploy an artifact from a failed build.

P0 must configure the test runners, threshold, mandatory CI jobs and actual hosted protection for
`master` before normal feature PRs merge. Verify enforcement with a deliberately failing test, a
sub-threshold coverage report and a missing/skipped required job; each must block merging. Verify
that an unauthorized direct/force push and branch deletion are rejected. This document does not
configure a remote repository or claim that those enforcement probes have been executed.


## Planned execution branches

```text
Administrator UI / CLI / direct API
  |-- unauthenticated or not entitled --> reject, no disclosure/mutation
  |-- malformed or stale input -------> validation/conflict, no dispatch
  |-- repeated request identifier ----> original operation, or conflict on reuse
  `-- accepted mutation
       |-- operation + audit + job transaction fails --> all roll back
       `-- commit --> return operation ID
            |-- activation/manual prerequisite --> persist wait, release worker
            |-- lifecycle/object conflict -------> explicit wait/conflict
            |-- revoked entitlement/access ------> block affected work
            `-- eligible step --> target-specific provider
                 |-- accepted/pending --> poll/reconcile, not completed
                 |-- verified result --> record progress and audit
                 |-- known failure --> record failure and permitted recovery
                 `-- ambiguous outcome --> reconcile, no blind repeat

Organization feed
  |-- malformed/stale/identity conflict --> diagnostics, preserve trusted state
  `-- eligible candidate --> validate effective graph against starting revision
       |-- intervening revision/config change --> rebuild/revalidate
       |-- partial census --> eligible metadata only; no absence conclusions
       `-- qualified full census --> metadata + qualified absence review
            `-- atomic publish --> stable person IDs + hierarchy/routing/history
                 |-- owner absent --> admin review; no OCI deletion
                 |-- shared member absent --> manual cleanup review
                 `-- new employee --> provisioning candidate; no OCI creation

Configuration
  |-- invalid type/override/effective values --> reject
  |-- publish baseline --> available version, no OCI dispatch
  `-- preview + explicit rollout --> captured version/targets/effective values
       |-- access/collision/concurrent-edit conflict --> visible block/review
       `-- apply dedicated managed objects --> per-item verification
            |-- removed/modified --> drift, admin repair with sufficient access
            |-- incomplete inspection --> unverified, no false missing result
            `-- passed --> current verified version; unrelated objects preserved

Break-glass grant
  |-- unauthorized/unverifiable credential --> no disclosure
  `-- persist grant/audit/notifications/deadline before disclosure
       |-- overlapping request --> separate audit; no deadline extension
       `-- rotation due --> priority at safe step boundary
            |-- verified rotation --> record new secret version and result
            `-- blocked/ambiguous rotation --> urgent alert and reconciliation

Monthly spend
  |-- actual/budget/forecast unavailable --> explicit reason, not zero
  |-- retained old data --> stale with coverage/collection provenance
  |-- incomparable scope/period/currency/basis --> no false comparison
  `-- usable OCI observations --> actual + non-overlapping forecast estimate
       `-- configured indicators --> show estimate source and freshness

Recovery
  |-- ordinary worker/API restart --> preserve progress, no duplicate effects
  `-- database restore --> compare restored intent with current OCI/Vault state
       |-- fence original dispatchers; block ordinary mutations
       |-- reconcile completed/uncertain operations and notification delivery
       |-- urgent credential recovery with verified live state or manual alert
       `-- administrator release --> recheck current guards before dispatch
```

Every branch above requires behavioral validation during its implementing milestone. The diagram describes planned paths, not existing functions or observed regressions. Provider-side mutations and application transactions remain separate.


## Critical journeys and scenario groups

| Journey | Scenarios and expected behavior | Specification |
|---|---|---|
| Sign-on and API entitlement | SSO user without admin entitlement cannot list, act, export or disclose secrets; expiration/revocation and direct API calls cannot bypass guards | AC01, AC10, AC44 |
| Fleet and hierarchy | Approximately 250 tenancies and 281-person sample; arbitrary manager depth, multi-tenancy ownership and shared membership; searchable/sortable/paginated results and accessible status icons | AC02, AC23–AC26 |
| Feed mapping/validation | Email normalization, whole names, source IDs, blank territory, missing manager profiles, cycles, malformed fields, unknown ancestry and source/LOB separation | AC23–AC28 |
| Organization publication | Reorg updates accountability without resource moves; complete immutable effective revisions retain people/history; partial/stale/duplicate snapshots, concurrent ingestion, configuration changes and pre/post-commit crashes preserve coherent applied revisions | D15; AC03–AC05, AC28, AC38, AC48 |
| Presence and owner review | Referenced-only managers are not departed; D17 manager-row gaps permit eligible partial publication with coverage alerts but no absence conclusions; last-known role/manager and multiple owned tenancies remain reviewable | AC06, AC24, AC27, AC50 |
| Create | Admin starts creation; email/MFA wait is explicit; close/reopen UI and restart workers; no duplicate child and no Ready state until mandatory verification | AC07, AC21, AC32–AC33 |
| Import | Wrong parent, temporary permission failure, collisions, partial provisioning, permanent identity verification and temporary-user cleanup failure | AC08, AC21, AC39 |
| Delete | Reject unregistered/non-child/parent/protected targets at acceptance and dispatch; manager/shared warning and last-known role; no bulk or automatic deletion; retain registry/history | AC09–AC11, AC22 |
| Configuration | Type schemas, overrides, immutable publication, explicit rollout, changed preview, partial results and preserved effective values; unrelated owner objects untouched | AC29–AC30, AC35, AC39, AC42 |
| Access health and repair | Required account/permission removal, revoked automation, ambiguous absence, incomplete inspection, daily/overdue checks; automated repair requires sufficient verified access | AC12–AC14, AC30, AC43 |
| Break glass | Unique per-tenancy secret; audit and notify before/after disclosure as specified; concurrent grants, restart and due/failed rotation; never claim password rotation proves session revocation | AC15–AC18, AC33, AC37 |
| Spend dashboard | Same scope/period/currency/basis; new-tenancy history gaps, stale/failed collection, actuals available without forecast, no custom fallback and no overlapping totals | AC31, AC40 |
| Jobs and transaction boundaries | Commit/rollback/insertion failure, lost response, duplicate submissions, multiple workers, delayed OCI calls and shared-parent object coordination | AC21, AC33, AC36–AC37, AC46 |
| Provider/access contexts | Shared result contracts; pending versus complete, unknown writes and diagnostic redaction; same/different hosting-parent tenancies and independent Vault/parent/child failure | AC32, AC41, AC43 |
| Administrative history | Append-only application interfaces/permissions, before/after provenance, actor/operation correlation, export and redaction; history retained after deletion | AC20, AC22 |
| Operational notifications | Automatic organization/access/configuration/grant/rotation alerts, explicit manually composed notices, frozen applied-revision recipients, administrator fallback for the listed non-lifecycle families (D50 lifecycle has none), bounded retries and uncertain delivery; unchanged incidents do not duplicate initial alerts | D14; AC47; sections 5, 7–8, 10 |
| Infrastructure and delivery | Terraform/Kubernetes repeatability, protected hosting, IMDSv1 disabled, generated clients, migration/restart/restore rehearsal and rollout compatibility | AC34, AC41, AC44–AC45; section 10 |

AC19 and security CSV/import/routing are V2 and excluded from V1 QA. Security auditing and audit-user provisioning are also V2. Administrative action history and operational access/configuration checks remain V1.


## Organization settings: leader and designee departure regressions

The [organization mapping settings design](engineering-design/20-organization-mapping-settings.md#required-leaderdesignee-regression-matrix)
defines required implementation tests for top-level manager and designee departures, role changes,
replacement/removal, multiple responsibilities, incomplete feeds, return and independent tenancy
versus mapping repair. Add these alongside implementation and require them to pass before slice
completion. Cover unit eligibility/reconciliation, disposable PostgreSQL transactions/history and
Playwright linked review/settings flows under D53. The implementation now includes these cases;
[the named regression trace](reference/organization-mapping.md#required-regression-matrix-trace)
maps each scenario to tests. The dated combined-suite validation receipt (private historical evidence; not distributed)
records the passing implementation gates and independent review dispositions.


## D17 declared-complete coverage cases

- A configured fresh declared-complete fixture omits a required manager profile but has unambiguous valid metadata changes. Apply eligible changes as partial data; preserve missing prior fields/edges or reference-only state; retain stable person/owner/membership IDs; record declared complete versus assessed incomplete.
- Repeat with every missing manager already present in the database and all effective paths reaching the root. Coverage must still be incomplete because the incoming rows are missing; no absent-owner/member conclusion is generated.
- Missing people elsewhere in that same census do not create absence exceptions; prior unresolved absence evidence is not erased merely because a new incomplete census arrives.
- Persist coverage diagnostics, incident and administrator alert intent atomically with effective publication. Rollback produces no new head or deliverable alert. Repeated same unresolved coverage incidents do not duplicate initial alerts.
- Invalid identity/graph, stale order and unconfigured/untrusted input retain their rejection/eligibility handling; D17 cannot turn them into eligible partial publication.
- Feed UI shows declared completeness, assessed coverage, publication outcome and blocked absence detection independently, with affected manager links and safe diagnostics.
- A later qualified complete snapshot is assessed from its own source/row evidence, permitting appropriate absence review; the old incomplete snapshot is never retrospectively promoted. No test creates/deletes tenancies or revokes users from feed processing.


## D16 organization browsing cases

- Open an organization result at R1, publish R2, then paginate and open a person/branch: all organization facts still use R1 and a new-data banner offers Refresh. No cache entry may substitute current routing into the pinned response.
- Refresh selects the new head coherently, preserves valid search/filter/sort controls and handles changed result counts or unavailable selection clearly. Back/deep links retain their explicit revision; unqualified fresh links start at the current head.
- Reject an unknown/unavailable explicit revision with a diagnostic rather than falling back to latest. A valid older revision remains readable despite a newer head.
- Continue current operation/check/incident updates while organization R1 is selected; display independent evidence without falsely claiming those live records are frozen.
- Start an action from R1 after relevant R2 metadata, parentage/access or entitlement changes: obtain current preview/recipients/guard facts, refresh changed evidence and recheck at acceptance/dispatch. Historical addresses and warning facts cannot authorize stale work.


## D15 immutable organization cases

- Publish two complete effective revisions around a manager/designee change; historical reads keep their original people, reporting and routing facts, and current reads use the new head. No current configuration joins may overwrite past accountability.
- Apply a partial feed: the new stored revision includes retained trusted people/edges and eligible updates; it creates no unsupported absence. A qualified missing owner remains represented with last-known evidence rather than losing its stable identity/tenancy links.
- Duplicate a source snapshot: link the original publication with no extra revision. Later capture with identical metadata refreshes presence evidence in a new effective revision.
- Reject cross-revision reporting references and attempts to modify published content through application interfaces; corrections create a new revision with change/audit evidence.
- Concurrent head/configuration changes require recomputation. Crash before commit exposes no new head/content; after commit, status recovery returns the published outcome without repeating effects or alerts.
- Organization-page pagination/detail links retain one revision. Live tenancy/operation/incident delivery facts are labeled separately rather than claimed to be frozen by that token.


## D14 notification cases

- With no administrator session or Send action, a committed qualified absence, access/configuration loss or unresolved rotation failure creates the required durable alert intent. A detector rollback creates no deliverable alert. Alert creation cannot enqueue a tenancy deletion or repair.
- Accepted break-glass grants persist their individual notification intents before credential disclosure; overlapping grants retain the original rotation deadline and have separate actor/notification evidence.
- Ordinary eligible manager/name updates apply without emails merely because metadata changed. Incomplete routing and invalid designee assignments produce administrator exceptions and alerts.
- Rechecking an unchanged incident creates no duplicate initial alert; recovery followed by a new loss creates a new incident. Partial/stale feeds create no unsupported absence alert.
- Change the manager/designee after intent acceptance: delivery retries keep the original recipients and routing revision. A corrected recipient request is separately audited. Missing routing for these D14 families reaches administrators; D50 lifecycle routing instead blocks without fallback. Secrets never enter messages.
- Manually composed notices send only after explicit submission with a current recipient preview; session/entitlement failure or stale preview prevents acceptance.
- Known transient channel errors retry under bounded policy; unknown delivery remains visible and uses provider-specific reconciliation. Restore tests retain D12 restrictions and never interpret restored intent as proof a message was unsent.

### D47 current delivery coverage

Planned email-only V1 tests retain all required recipient/urgency and committed-event/outbox assertions above; cover approved sender/endpoint configuration, known transient retry, partial/unknown delivery reconciliation, redaction and restore fencing. Ensure V1 has no Slack adapter/configuration/credential/delivery dependency; interface extensibility alone is not a Slack feature. Composed messages still require explicit Send; colored cost values cannot trigger email. These are planned tests, not executed provider qualification.

### D48 planned financial-failure notification coverage

- First transient acquisition failure is visible and retried without an email; retry exhaustion creates exactly one administrator notification intent, without an extra 24-hour wait.
- Further retries and later daily failures retain the episode and create no duplicate initial notice. A verified read recovery closes the episode internally; a later read-failure relapse and retry exhaustion may create a new initial notice.
- Missing optional forecast, normal old provider computation and an over-budget amount create no failed-acquisition email. A financial-read-only event does not expand recipients to owners/managers/designees; independently confirmed access loss retains its required notice routing and urgency.
- Preserve existing immediate disclosure/urgent rotation notices, durable event/outbox atomicity and restore-safe deduplication. No recovery/reminder emails are introduced. Inject a versioned test retry/backoff policy without claiming its fixture numbers as accepted runtime defaults.

These are planned assertions; this documentation update does not execute the worker, send mail or qualify the provider.

### D49 planned lifecycle-notification coverage

- Cover create/import/delete/shared membership/ownership transfer/person offboarding: committed `waiting` with human-action reason and `needs_attention` requiring administrator action notify; terminal `failed` notifies.
- Provider/retry/reconciliation waits without manual action and `queued`, `running`, `succeeded`, `cancelled` create no automatic lifecycle email. Operations retains routine progress and successful outcomes.
- Unknown provider effects remain unknown, not terminally failed; a notice is appropriate only if the state requires manual intervention. Preserve D47 channel/uncertainty guards, D48 financial notices and urgent access/disclosure/rotation alerts.
- D50 selects only the current responsible administrator; no owner/manager/designee/admin-team copy or automatic fallback. These are planned tests, not executed delivery qualification.

### D50 planned responsible-only routing coverage

- Initial responsibility equals the initiating authorized administrator. Authorized audited takeover changes the responsible actor while preserving initiator and activation mailbox; notice acceptance captures only the current responsible administrator.
- Unavailable, unauthorized, unresolvable or bounced responsible recipients remain visibly blocked; no automatic email to other administrators, owner, manager or designees. Explicit authorized takeover/correction is required.
- Reassignment cannot modify an accepted outbox recipient set. Preserve original delivery context and reconcile uncertain submissions before a corrected send; do not blindly resend to a new responsible actor.
- D48 administrator financial-failure emails and other required access/recovery/urgent-rotation recipient lists retain their independent scope. These are planned assertions, not executed delivery or entitlement qualification.


## Administrator interactions

The local harness implements three organization read routes in [generated OpenAPI](../prototype/docs/contracts/organization-openapi.json). Other routes/layouts are not finalized; identify those screens by their specification names until the corresponding inventory is approved.

- Fleet/Organization: search, sort, pagination, hierarchy expansion, clickable person/tenancy details, incomplete ancestry and multiple simultaneous status indicators; D16 pinned organization navigation, new-head banner/Refresh and current action preview checks. AC49 applies to organization read context, not a frozen fleet inventory.
- Owner review: inspect missing person's known manager/role and all associated tenancies; Start deletion opens the guarded per-tenancy flow. Shared-member review cannot delete the shared tenancy implicitly.
- Create/Import: validate fields, show ownership/baseline preview, submit once or twice, leave/reopen the page, complete a manual prerequisite, inspect partial failure and resume.
- Managed configuration: edit typed values, see rejected overrides, publish without rollout, preview selected targets/effective values, start explicitly and inspect per-target outcomes.
- Access health: view last check and reason; Repair appears only with verified sufficient automation access. Unverified automation is informational manual recovery, not a working repair button.
- Break glass: explicit request/reason, limited credential display, overlapping grants, notification status and due/failed rotation; credentials never enter logs/export.
- Spend: distinguish actuals from OCI estimates, missing from zero and stale from current; inspect scope/period/currency and linked exception details.
- Operations/History: waiting, failed, partial and uncertain states; retries keep original intent; audit filters/export cannot modify recorded events.
- Across screens: expired sessions, slow responses, validation errors, stale previews, double-clicks, direct API attempts, browser closure and keyboard/mobile layout. Human confirmation remains specific to guarded actions rather than ordinary metadata updates.


## Fleet/performance validation (D13 accepted)

Queue checks for approximately 250 eligible tenancies using the real local PostgreSQL runner and a stateful simulator with injected slow calls, throttling and one unavailable child. Verify bounded concurrency, independent outcomes, stable scheduling keys, duplicate/missed-trigger recovery and last-success versus last-attempt timestamps. Introduce due credential work during backlog and verify reserved capacity without bypassing mutation coordination. Dashboard requests must use stored observations, with deterministic pagination and bulk-related queries. Measure query count, queue age, backlog completion and export memory; calibrate actual limits with live OCI instead of publishing unmeasured targets.


## Database-restore rehearsal (D12 accepted)

Restore an older application/queue snapshot while the simulator retains later external state. Cover a child already created, deletion already submitted/completed, password already rotated and notification already delivered. Verify old workers are fenced, normal dispatch stays blocked, read-only reconciliation reports current evidence and administrator release is audited and rechecks guards. Unknown outcomes cannot be replayed merely because old queue records exist. Due/overdue credentials have an urgent controlled recovery path; stale passwords are not disclosed as current. Test ordinary restarts separately to ensure they remain automatic. Repeat the restore/fencing procedure against managed PostgreSQL in the authorized M5 environment.


## C5 executable design controls — 25 October 2026

[The contract guide](engineering-design/16-c5-contract-review.md) and
receipt (private historical evidence; not distributed) record49 positive and 43
negative shape/reference-predicate checks. Run `uv run --no-project scripts/check_c5_contracts.py`.
This is additional design evidence, not a new claim about the historical runtime test counts above.

The production implementation must reuse these inputs against generated Python/client models and
add real DB/runner race and crash tests: failed-read prior scope, replaced source-context ordering,
same-collection conflicting facts, coherent partial values, stale source despite fresh retrieval,
month rollover and observed reset/processing changes. Provider qualification must verify conversion,
cycle/currency/permission/forecast behavior; assumed fixture profiles are not evidence of those facts.
Email tests must cover exact recipient partition, accepted versus delivered, authorized same-context
credential rotation, responsible-admin reassignment before dispatch and immutable correction only
while known unsent. Actual/unknown submissions retain original context through restore. No SMTP,
OCI call, concurrency or production service is tested by the pure reference checker.



## D51/D52 planned recovery acceptance

The accepted objectives are 15-minute RPO/4-hour RTO for in-region recovery. Reproduce the
[C6 recovery cases](engineering-design/06-platform-and-delivery.md#planned-qualification-cases)
against the selected service and implementation: ordered contiguous committed-write recovery,
corrupting migration, old/new deployment fencing, endpoint/schema/runner incompatibility,
post-recovery-point create/delete/rotation/email effects, lost disclosure anchors, read-only versus
safe-service timing and scoped quarantine. Restore to an older safe point or exceed the deadline
only with an explicit measured miss, never a reset clock or bypassed guard. Full-region loss is
outside these V1 objectives. This adds planned release criteria AC71/AC72, not executed restore tests.






## D54 planned simple credential/restore tests — 26 October 2026

[The accepted V1 contract](engineering-design/17-recovery-and-release.md) replaces the withdrawn
external control/journal. Test a restored old version row resolving stable secret OCID plus CURRENT;
record the actual returned version. Do not use LATEST/PENDING/old version as ordinary password source.
Test candidate staging failure, interrupted child write, failed CURRENT promotion, original exposure
deadline and unexpected CURRENT change while a window remains open. Exact candidate/API-key version
checks remain. In disposable PostgreSQL/simulator tests, restore paused with workers/mail disabled,
revoke restored app sessions (including post-backup revocations), hold active work and explicitly
resume reviewed safe operations; no blind create/delete/
rotation/email replay. The manual managed-service drill measures D51/D52. D53 still applies, and
retired proposal checker results are not application-test evidence. No live drill has been executed.


## Astra final-review regression cases — 28 October 2026

- Create handoff requires child/bootstrap/activation-administrator user OCIDs; imports preserve existing
  humans. Wrong-domain, ambiguous, protected and changed cleanup targets block removal. A verified
  exact target is previewed/confirmed and removed only after permanent replacement/last-admin checks.
- Automation and recovery subjects can simultaneously open the same `inspection/access` condition.
  Their issue IDs and deduplication scopes differ; resolving one never resolves the other. Repeated
  observations deduplicate only within the same complete coverage-subject scope.

These are planned production integration/simulator assertions, not newly executed prototype tests.


## D56: security and publication acceptance

Require the [standing security reviewer](security-review-policy.md) for P0–P5 and security-sensitive
changes. P0 must sanitize the candidate repository before any first commit/push: preserve private HR
sources locally and replace real names/emails in source, fixtures, design examples and generated
artifacts with synthetic records. Review non-text images/decks/metadata as well as staged text and
Git history. Keep security reports sanitized; no copied secret or HR values in findings.

Test denial paths for authorization/IDOR, wrong OCI targets, injection/XSS/CSRF/SSRF, upload/path/parser
limits and secret redaction as the relevant code is implemented. Run static/secret and resolved
dependency advisory checks in required `security` CI, adding image/IaC checks with those artifacts.
A failed/unavailable/skipped required scan fails the aggregate. Verify with safe synthetic negative
fixtures; do not install unsafe packages into the application merely to test scanner enforcement.
Scans do not prove packages are non-malicious; review source/provenance and lockfile additions.

## Guided local onboarding regression scope — 31 October2026

Keep the95% unit-only gates separate from provider/database/browser tests. The guided subset adds
closed handoff validation, exact discovery pairing, request replay/revision/responsibility checks,
manual wait persistence, ordered permanent-access verification, verified-prefix retries, preserved
known effects on later failure and no-effect cancellation refusal. Disposable PostgreSQL exercises
the actual step/audit constraints; the installed-role HTTPS/native-worker Playwright journey drives
create/import handoff and explicit cleanup review, reloads persisted state, corrects bad bootstrap
input, and checks checkbox/control geometry and overflow at desktop/tablet/mobile widths. A cached
same-revision operation switch must clear cleanup consent. Simulator successes do not qualify OCI,
Vault or MFA; those live qualification cases remain in chapters07–09 and the existing test plan.

### Import continuity and create-name errors — 2 November 2026

Implemented regression coverage: imported OCID is prefilled/read-only without clicking sample fill;
bootstrap-only entry submits that exact target, while create remains editable. Unit and PostgreSQL
tests reject forged targets without changing operation revision or consuming the valid handoff.
Local active/pending/terminating name collisions cause zero writes. Database rollback/corrected retry
and frontend preservation of type/region plus focus/corrected submission are exercised. These checks
do not establish OCI-wide uniqueness.

Required before live C03/C04: definitive provider name rejection pauses the same operation; audited
replacement-name revision preserves pending record/owner/type/region and receives a new retry token.
Test repeated rejections, successful correction, stale preview, duplicate commands/jobs, reload and
revocation. Contrast definite rejection against timeout/lost response/ambiguous work-request failure:
unknown effects block changed create requests pending reconciliation. Qualify the actual OCI error
codes; generic conflict status alone must not authorize another child request. These provider cases
remain planned, not executed in the current no-OCI simulator.

## Explicit organization root replacement regression scope — 2 November 2026

The root-replacement extension supersedes the former prohibition on all post-import root edits.
Unmarked changes must still fail; explicit change_root intent must bind both Preview and Apply.
Added cases pass in the final1,014-test backend/database/browser aggregate and175frontend units.
The root-replacement receipt (private historical evidence; not distributed) records
this extension; the earlier base-mapping receipt remains historical.

- Pure mapping cases cover successors present and absent in the latest source, old/new root and
  before/after ancestry, unresolved counts, immutable segment IDs, no invented reporting edges and
  unchanged observation/census/absence evidence. Fresh non-root rows without a manager remain fatal;
  only reuse of validated former-root evidence has a nonfatal mapping-only diagnostic.
- Real disposable PostgreSQL verifies the narrow root-only policy change, configuration/version/audit
  atomicity, exact unchanged associations and clocks, stale Apply rejection, another mapping edit on
  reused evidence, then a corrected feed resolving the graph. The former root is retained for normal
  qualified absence review. Cover pending-work, authorization, rollback and cross-workspace guards
  without weakening existing mapping acceptance tests.
- Frontend tests cover explicit unlock/focus, missing-successor and unresolved-path warnings,
  confirmation before Apply, change_root in the submitted request, saved-root relocking and Cancel
  restoring the saved root. Edits invalidate the review; uncertain Apply requires read/preview recovery.
- Manual/browser qualification must distinguish the new root from segment-leader replacement, confirm
  that no tenancy is reassigned or deleted, and verify the subsequent feed's real source edges. Use
  synthetic fixtures in a disposable installation. Do not mutate the user's saved mappings to test.

Named source cases and validation boundaries are recorded in the [runtime regression trace](reference/organization-mapping.md#required-regression-matrix-trace).
No provider invocation, notification delivery or production OCI qualification is implied.


### Root replacement manual qualification

Follow [the manual runbook](how-to/organization-mapping-runbook.md) with its six synthetic CSVs.
`test_manual_mapping_runbook_csv_sequence` validates those exact files against the production
CSV/reconciliation functions, including qualified absences and new-root graph repair.
`replaceOrganizationLeader` exercises the real HTTPS dialog and corrected upload; the dedicated
PostgreSQL case preserves source clocks and associations and checks immutable root audit evidence.
These supplement all existing qualified-return and per-segment departure regressions.


### Readable immutable organization audit details

Mapping events show selected historical root, segment-name, leader and designee changes without
joining current mappings or serializing raw evidence. Initial/add/remove, rename, leader/nominee
changes, no-op and legacy/no-details cases require unit coverage. Queued offboarding must say
Requested; only the recorded immediate completion receipt permits completed wording. Feed receipt
must not invent a zero row count from default metadata. Directory/CSV must agree on the12field
projection; changes are a JSON array in CSV with existing formula/control-character neutralization.

A disposable PostgreSQL case makes two mapping edits and verifies the first audit/CSV keeps its
original old/new values, with workspace isolation and no raw configuration. Real HTTPS Playwright
opens/closes View changes by keyboard, shows the exact old/new root and verifies44px touch targets
and narrow-screen table scrolling. React must render script-like change text as text. Existing
hash/actor validation, authentication, filtering, export limits and rollback gates remain mandatory.


### Corrected industry-segment reviews and targeted provisioning

Two disposable PostgreSQL reproductions must fail before the fix: repaired employees retaining open
LOB_MAPPING_REVIEW rows, and unmapped employees being offered provisioning. After repair, automatically
resolve only the no-longer-active mapping review for the same stable person whose current accountability
is valid, retaining history with mapping_corrected. Absence/setup episodes and legitimate unmapped
neighbors remain open; repeated feeds do not revive corrected conditions, and a later genuine regression
opens a fresh episode. Ignore does not authorize provisioning. The exact configured root has its explicit
boundary exemption; stale segment IDs, wrong accountable leaders and incomplete ancestry fail validation.

Pure units exercise the shared predicate and narrow closure, plus cleanup/root preservation. Real
PostgreSQL verifies all three create/import/join requests are denied before mapping and available after
repair where the simulated provider supports them. Browser checks confirm a clear repair notice/link,
missing provisioning choices, continued no-association offboarding, review/count refresh after Apply and
absence/setup independence. The auth browser fixture has no lifecycle provider, so it proves repaired
mapping state rather than cloud provisioning availability; native worker/DB tests cover that boundary.
No changes to source-observation clocks, ownership, tenancy membership or permanent-ignore rules.

### Latest-feed information and readable segment changes — 2 November 2026

Unit tests cover feed-provenance selection across mapping reapplies, independent unfiltered counts,
retained full history, open-versus-resolved warnings, exclusion of completed actionable decisions,
and pinned before/after segment labels without mutating stored identifiers. PostgreSQL tests cover
baseline replacement by later feeds, repeated identical deliveries retaining current warnings, source
correction clearing the latest-feed information count, and preservation of older history. React tests
cover the new badge/query, human segment names and revised empty state. Playwright checks that an old
baseline does not appear after a later upload and compares the leader button/helper vertical centers.

### Configured root without a tenancy — 2 November 2026

A no-association configured root can choose No tenancy required, which closes setup and records
an exemption without changing the reporting boundary, descendants, role health or tenant links.
Units prove the original guard failure and protect actual root offboarding; PostgreSQL covers
idempotent replay, later identical feeds, preserved graph/role health, no renewed setup review,
and explicit re-onboarding. The real HTTPS browser replaces the root, imports the successor feed,
records the exemption and verifies that root mapping and role health remain intact. Its dialog is
checked at1280/390/320pixels. Existing association guards and qualified-return regressions still apply.

### Latest-feed/all-history switch — 2 November 2026

Frontend regressions cover latest scope by default, the opt-in history API, selected-scope counts,
page reset with retained search/sort, scope memory across tabs and hiding the control on Actionable.
A real QueryClient test covers refreshing inactive mapping context after a decision. HTTPS/Playwright
checks an earlier baseline is hidden by default, becomes visible with Show all history and disappears
when cleared; responsive captures cover1280/390/320pixels. The same isolated PostgreSQL-backed browser
journey continues through mapping repair and successor-leader exemption after these interactions.

### Direct page reload and landing route — 2 November 2026

Public-shell unit tests enumerate all implemented feature entry paths and UUID detail routes,
including Organization Mapping, while proving near-prefix/extra-path/private API requests still
require authentication. React units cover root/login landing at Tenancies, explicit page intent,
brand-home navigation and logout/cache behavior. Real HTTPS/Playwright signs in to Tenancies, then
loads and reloads every implemented tab, checks HTTP200, retained URL and heading, and observes fresh
API reads. Tests use the protected real session and disposable Docker PostgreSQL, never an auth bypass.

### Navigation counts — 2 November 2026

Backend units and PostgreSQL cover the workspace-wide actionable waiting/needs_attention workflow
count independently of search, page and selected state; read-only inspections are excluded; queued/running/completed states and other workspaces are excluded.
Frontend cases cover positive/zero counts, open-actionable versus historical organization items,
shared-cache invalidation, stale/unavailable reads and denied-session expiry. Real HTTPS verifies the
organization badge against its protected API. Desktop/390/320 screenshots additionally use an explicit
three-digit DOM-only layout fixture, restored immediately afterward; it is not a business-data assertion.

### Prompt navigation counts and shared dropdown bounds — 2 November 2026

A deterministic before-fix unit failure proves that a persistent sidebar did not reread counts when
switching pages. Regressions now cover every navigation revision, reselecting the same menu item,
Back/Forward and a worker transition observed by the five-second fallback without navigation. Actual
HTTPS/worker tests create a tenancy, leave it waiting, navigate through Audit and Administrators,
and match the Operations badge to its scoped API count before opening Operations.

Shared picker tests inventory19 Select uses and open visible/enabled controls in the seven feature
pages and a workflow dialog at1280/900/768/390/320pixels. Inert background controls are excluded while
a modal is open. Checks retain strict option viewport bounds, short-label single-row height, Escape
focus/value preservation and keyboard opening. Isolated CSS probes additionally exercise30 placements
with long identifiers and above/below safe fallbacks. Native OS/forced-color renderers are not claimed
as browser-qualified by these Chromium cases; the standing UX review gate retains that distinction.

## P3.1 baseline draft regression matrix

| Boundary | Required evidence |
|---|---|
| Authoring | One policy block and one quota block; nonempty LF/CRLF/CR lines map to ordered statements; blank lines ignored; 1–50 statements of at most2,000characters; whole-unit budget authoring with exact four-place archival money; static tags; closed field/bounds validation; no OCI action/publication |
| Concurrency | One draft per workspace; concurrent identical initial saves yield one row/event; changed stale revision rejects without losing browser edits; identical content is a no-op |
| Persistence | PostgreSQL round trip; hash/content corruption refused; immutable published rows; identity/revision database guards |
| Authority | Current verified administrator on save, same-origin/custom-header protection, scoped IDs, bounded JSON, safe errors; API role cannot publish or delete |
| Audit | Same-transaction typed before/after; failed audit rolls back draft; human-readable historical changes and baseline target |
| Local reset | Nonempty baseline included in explicit nine-table reset; rollback restores rows/triggers; auth/history preserved; no CASCADE |
| Browser | Actual HTTPS/restricted PostgreSQL role; save/edit/reload; unknown baseline link; responsive1280/390/320 layouts; no whole-page overflow |

The existing unit-only95% gates apply independently to backend and frontend. These tests do not
qualify OCI statement grammar, actual billing currency or provider application; those are later slices.


### Policy/quota block editor correction — 2 November 2026

User-approved authoring uses one block per category, without per-statement Add/Remove controls.
Unit cases must cover newline variants, blank lines, whitespace/order retention, reload, and invalid
empty/51-line/2,001-character input retaining edits without a request. Actual HTTPS/PostgreSQL browser
coverage saves two policy lines, verifies the stored ordered array and reopens the same block on
1280/390/320 layouts. Existing backend arrays and stored legacy multiline entries remain supported;
loading alone never rewrites them. An explicit Save interprets displayed physical lines as statements.


### Whole-unit monthly budget authoring — 2 November 2026

New baseline saves accept positive integral currency amounts only (whole dollars forUSD). Test
250/250.0000 equivalence, fractional rejection at HTTP/command boundaries, unchanged stored-content
hashes/history, and explicit correction of a legacy fractional draft. Keep NUMERIC(20,4) and the
archival BaselineContent contract; reject cents at SaveBaselineDraft rather than making old rows
unreadable. UI display removes zero-only decimal suffixes; no rounding, digit stripping or numeric
float conversion. Test whole-value save/reload display, numeric keyboard, native pattern, raw-invalid
input retention, and legacy250.5000 preservation until explicitly changed. Actual/forecast cost
observations retain their existing precision and are outside this budget authoring rule.


### Fifty statements per policy/quota block — 2 November 2026

Each block independently accepts1–50statements; statement51is rejected in both categories. Keep
2,000characters per statement. Raise the raw browser cap to105,000characters per block and the
streamed JSON body cap to2MiB before parsing. Test both50/51boundaries, an authenticated valid
multibyte request larger than the former256KiBcap, and refusal above2MiBwithout a service write.
Actual HTTPS/PostgreSQL coverage must round-trip50policies plus50quotas and reopen them in order.
No SQL migration or existing recipe/hash rewrite is needed; generated schema maxItems changes.


### Actionable Operations badge — 2 November 2026

Count currently supported human work, not every raw waiting/needs_attention state. Require the exact
current organization intent, workspace/stable-person/pending-operation match and a supported guided
handoff/review/blocked retry or existing safe no-effect local cancellation. Read-only inspect_import
outcomes, orphaned records and unsupported waits with known effects contribute0. Do not alter their
recorded state/history, invent acknowledgment or grant authority from the counter.

Regressions cover inspection failures remaining queryable at count0; real create waiting, invalid
bootstrap retry, review, partial required-access failure with known effects and successful completion
(count0→1→0); global/filter/foreign-workspace boundaries; supported cancellation versus unsupported
known effects and missing pending subject. Playwright must show diagnostic history without a badge,
then a waiting create badge while navigating other tabs. Existing organization-drift badge behavior
and refresh/privacy/expiry policies remain unchanged.


### P3.2a local publication and immutable history — 2 November 2026

Unit tests cover exact saved-ID/revision publication, live authority and explicit qualifier
availability before replay; closed whole-unit USD-profile qualification; corrupt hash rejection;
typed audit orchestration, stale/missing/foreign IDs and parent fencing; scoped repeatable-read history,
page sizes and exact immutable snapshots. The default core application cannot publish without an
explicit qualifier. Local composition infrastructure-services a simulated qualifier; no OCI calls are made.

Disposable PostgreSQL tests cover publication/history/cloning, concurrent replay producing one
audit event, rollback on audit insert failure, immutable published UPDATE/DELETE rejection, real
foreign-workspace records, and narrowly granted publisher writes rejected for missing/unsupported
mode or missing name. Preserve all prior migration hashes and validate the new frozen0012 digest.

Frontend units and real HTTPS Playwright exercise confirmation/cancel, heading focus, short-mobile
dialog scrolling, closed auth/stale/validation/unavailable failures, immutable statement/budget/tag
display, history paging and cloning the latest publication. Capture desktop/390/320 layouts; saved
source version stays unchanged. No current pointer, assignment, override or OCI-success assertion
is fabricated. Both independent unit-only coverage gates remain>=95%; all required results must
execute without failures or skips. Upgrade saved local instances only after private backup and
compare all pre-migration columns across all15application tables.


### Latest-only default and create/import pinning — 3 November 2026

New create/import always snapshots the highest published version in its workspace. Test that a
retained old/default-null metadata value has no effect, including publications predating0014.
The removed selection endpoint must return404; no manual adoption button or client command exists.
Published historical rows are view-only; drafts do not affect new admissions until published.

Retain both createv1→wait→publishv2→resumev1→newimportv2 and the reverse order, original command
replay, publication rollback, stale-preview rejection, foreign/corrupt evidence, registry-pin
mismatch before provider work, and old-format unpinned operation completion. Never fall back to an
older version when the latest is invalid. Preserve historical selection audits as read-only data.

Unit, disposable PostgreSQL and HTTPS Playwright suites cover latest history and new-draft derivation,
absence of selection controls, frozen original pins and1280/390/320layouts. Both unit-only coverage
gates stay>=95%. Migration0014 only increments registry_revision once; private-backup/fingerprint
verification must prove all other values, obsolete metadata and frozen pins are unchanged.

## Baseline-only asynchronous update regression matrix

The current field/transaction map is [configuration updates](reference/configuration-updates.md).
Qualify the simulator without claiming live OCI support or override conflict resolution:

| Boundary | Required regression |
| --- | --- |
| Preview | Exact latest immutable recipe; whole active candidate set; pending excluded; any busy/foreign/unavailable child gates the complete batch; stale publication/registry revisions rejected |
| Admission | Single and fleet scope; actor/request-key replay; desired pins, reservations, full intent/audit and native job commit together; audit/queue failure rolls all changes back |
| Execution | Recheck current authority, parent, child, exact pin/revision; separate category writes/readbacks; advance verified pin/time only after all four match; persist partial simulated state |
| Recovery | Later publication cannot retarget accepted work; successful children and matching category prefixes survive retry; prior verification preserved on failure; only responsible authorized administrator can retry |
| Input | Allowed50x2000 Unicode/control-character statements remain serializable, stored and readable; closed4096-byte commands cannot inject actor, version or arbitrary target lists |
| UI | Context-aware version links and16px backlink gap; create/import values survive recipe inspection and Back/Forward; frozen batch dialog and blockers; individual/fleet progress and native worker completion;1280/390/320px geometry |
| Privacy | Auth/Origin/header protection; private query cleanup; no raw provider errors/secrets; actionable badge excludes unsupported historical failures |
| Upgrade | Private backups and full old-column fingerprints for both saved local instances;15 existing tables and all existing values preserved, three new fields nullable |

Run unit-only coverage separately for frontend/backend, disposable PostgreSQL and real HTTPS
Playwright/native workers, documentation/purpose-comment checks and independent security/UI reviews.
Final evidence is recorded in development progress; no validation is implied merely by this matrix.

### Baseline concurrency and presentation regressions

Exercise two simultaneous real PostgreSQL admissions against one preview: distinct request keys
produce one accepted operation and one stale-preview conflict; identical request keys return the
same durable receipt. Verify a single native job and a single reservation per child. Deliver that
operation concurrently to two workers and require exactly one verification event per child.
These complement existing publication/replay/stale-preview and atomic rollback cases.

Playwright checks actual description/button centers at desktop/tablet widths, narrow layouts,
completed individual-panel removal, no successful Refresh progress button, bulk Acknowledge and
reload without a completion list, current-state styling, and retained Operations history. Unit and
PostgreSQL checks cover exact assigned/latest versions, UTC completion timestamps, friendly scoped
audit resources, corrupt/cross-workspace intent rejection and safe escaped links. No new database
column/table is required for these projections or presentation-only acknowledgement.


## Authored overrides and staged-plan qualification matrix

The 0016 local implementation has completed D53: separate backend/frontend unit gates, disposable
PostgreSQL/native worker, actual HTTPS/browser, independent reviews and preserved saved-instance
upgrade checks pass. Focused/partial results or generated models alone would not satisfy these gates. Current [field/flow dictionary](reference/tenancy-overrides.md)
and [implemented ER](architecture/diagrams/tenancy-overrides-implemented.mmd) define the exact 18-table subset,
10 override DTOs / 55 fields and 12 rollout DTOs / 76 fields under test. Preserve prior receipts as historical.

| Trigger/invariant | Required verification |
| --- | --- |
| Policy/quota full-list override or clear | Null inherits; 1–50 complete strings replace whole authored category; no append/merge/empty-delete. Unit boundaries plus actual SQL JSON null rejection and API errors. |
| Independent monthly budget | Whole positive 20/4 money, no rounding/tag/currency/scope override; carries across compatible baseline amount/tag changes without invented statement review. |
| Assigned editor and text blocks | Required OverrideContext matches baseline/tenancy/configuration; late publication never upgrades editor. Exact original block retains legacy boundaries; edited LF/CRLF/CR splits at most 50 nonblank lines. Preview/Cancel/Back do not mutate. |
| New same-baseline revision | Desired configuration ID advances independently from baseline ID; worker fully verifies effective content before verified head/time advance. Partial failure retains prior verified revision and advanced-time evidence. |
| One of several conflicts unresolved | Stage exact choices for one target, assert all live heads/operations/jobs unchanged; bypassed Start rejects entire batch until every required category/target/blocker clears. |
| Stale plan/editor | Later publication, separate override edit, registry/candidate changes and another staged-save revision invalidate source-bound review. GET reload retains original evidence or accepted operation; never silently rebases. |
| Durable staging and uncertain response | Plan create same UUID/scope replays same owner plan; changed scope conflicts. Staged Save uses optimistic revision; after lost response reload saved choices rather than claim idempotent command replay. |
| Whole-plan acceptance | All immutable configurations, desired heads, plan/target links, operation/audit and native job commit together. Failed target/audit/enqueue rolls all back; child verification remains independent after acceptance. |
| SQL scope/immutability and roles | Published baseline/same-tenancy predecessor, complete scoped FKs, accepted target INSERT/UPDATE/DELETE denial, new plan cannot preclaim accepted operation, immutable revision/no-TRUNCATE, narrow API/worker grants. |
| Legacy compatibility | Old original 3-field request digest and original raw intent JSON hash stay unchanged; old accepted baseline-only work resumes; nullable new heads remain null until explicit acceptance. Existing values preserved after upgrade. |
| Actual UI journey | Chooser excludes current busy/inactive children using has_pending_operation, not history fallback; independent checkboxes/whole budget, full old/new/override comparison, plan URL reload, all-blockers gate, progress/retry/history and native keyboard/mobile behavior. |

Additional PostgreSQL cases race same-key and different-key override acceptance against the same
reviewed context and inject enqueue failure after revision/head/audit writes. Verify one shared
operation/revision/job for replay, one winner for competing commands, and complete rollback when
enqueue fails. The preview also exposes collapsible exact effective policy/quota text and inherited
tag defaults. Browser checks cover staged-flow Back/Forward restoration and focus after acceptance;
these additions are included in the completed local qualification, without claiming real OCI behavior.

Source cases live in [unit policies](../backend/tests/test_tenancy_overrides.py),
[HTTP boundaries](../backend/tests/test_tenancy_overrides_http.py),
[real PostgreSQL](../backend/tests/test_tenancy_overrides_postgres.py),
[React interactions](../frontend/tests/tenancy-overrides.test.tsx) and
[HTTPS browser journey](../frontend/e2e/tenancy-overrides.ts), with complete existing suites retained.
Stubbed unit checks prove orchestration/business rules, not real SQL locking/rollback or OCI behavior.
Use synthetic disposable installations; no saved-workspace reset/direct permission edits to inject
failure. The [manual review steps](reference/tenancy-overrides.md#manual-review-after-qualification)
are for an explicitly upgraded isolated local runtime after qualification.


Local qualification passes: 985 backend unit tests cover 6,311 of 6,576 executable lines
(95.9702%) across all 88 source modules. The 251 frontend unit tests cover 1,484 of 1,525 lines
(97.3115%) across 28 files. All 1,212 combined backend/PostgreSQL/HTTPS-browser cases pass without
failures, errors or skips, including native worker execution. Unit-only coverage is measured
separately from database/browser execution. All 59 schema exports, 233 purpose-comment files,
208 formatted Python files, Ruff and document links pass. Dependency audits, Bandit and scoped
Gitleaks report zero findings. Independent security, documentation and final actual-screen UI
reviews pass.

Both saved installations are upgraded from 0015 to 0016 with private 0600 backups. All existing
columns and rows across the 15 pre-existing application tables retain identical fingerprints;
baselines, pins and history are unchanged. There are now 18 application tables and 20 baseline
columns. The three new tables are empty and both new configuration heads remain null on existing
rows: no synthetic revision or assignment was backfilled. Current assets, liveness/direct-route
HTTP 200 responses and protected new-API HTTP 401 checks pass on both ports. No reset, seed,
credential change, real OCI call or Git publication occurred.

Local qualification receipt (private historical evidence; not distributed) · Independent review (private historical evidence; not distributed).


## Six tenancy refinement regressions — 3 November 2026

Local qualification and both saved-instance installations pass. Keep new complete-source unit gates separate from actual transaction/worker/
HTTPS-browser evidence; historical receipts do not qualify this source.

- Existing-compartment choice: valid child/non-root binding, new-compartment alternative, exclusive
  request fields, root/foreign/unknown/changed target rejection, no replacement create, unchanged
  historical digest when optional field is absent/null.
- Shared removal: exact association/child/user receipt and two durable identity steps; missing,
  duplicate/extra/wrong-target receipt denies retirement; transactional rollback; known scoped user
  and groups removed in simulation; unrelated members, compartment and resources retained.
- New onboarding v2: exact frozen published recipe applied/read back for all four categories; later
  publication during handoff/retry never retargets; partial observation and prefix retry; full
  category completion advances verified baseline/time; fresh automation/required-access checks after
  root-policy writes; failure preserves temporary access and pending ownership.
- Compatibility: accepted v1/absent-version graphs, original stored hashes and request keys remain
  unchanged; no new table/column/backfill; old baseline/configuration history preserved.
- UI: dedicated Overrides panel and inherited/verification states; redundant top shortcut absent
  while owner/member links and Transfer owner work; registration-time tooltip hover/focus/Escape;
  existing/new compartment picker and actual guided baseline steps at wide/narrow widths.

[Isolated manual review](how-to/tenancy-refinements-runbook.md).


## On-demand configuration drift matrix — 3 November 2026

Local qualification and both saved-instance upgrades pass. Separate full-source unit gates from disposable PostgreSQL/
native-worker/HTTPS-browser evidence; prior receipts do not qualify this new source.

- Exact assigned baseline/accepted full-list and budget overrides; later publication is no drift.
- Four complete matching results, authorized explicit missing, content different, unavailable/
  timeout/malformed state, conflicting identity/category and uninitialized legacy records.
- All-four coverage gating: partial cannot confirm/clear; earlier same-context drift retained
  after failed reads; later full current matching resolves projection but preserves history.
- Context/revision/policy/binding changes, busy mutation, old-generation supersession, serialized
  database acquisition ordinals, 24-hour freshness, duplicate delivery and exact request replay.
- Real transaction rollback/unique/scoped/append-only guards, restricted-role permissions, current
  grant/session/policy, foreign target and pause handling. No apply call, configuration head or
  observation mutation by ordinary checks.
- Actual native worker plus responsive browser: tab distinction, truthful empty/error/stale/retained
  states, counters, search/sort/page, detail/category/Back deep links, read-only expected/observed text
  and queued receipt versus actual result.

External-change scenarios use disposable synthetic fixtures only. There is no operator simulator
CLI or authorization to edit saved observations. Daily infrastructure, repair, email and real OCI
coverage are separate gates. [Manual review](how-to/configuration-drift-runbook.md).


## D50 guided takeover regression matrix — 4 November 2026

Application capability qualified locally and installed in both saved instances. The new responsibility API is an application decision with
no provider dispatch/job on claim. Separate complete-source unit gates from actual database/native
worker/browser proof.

- Eligible waiting/needs_attention guided v1/v2 create/import; reject self, queued/running/terminal,
  other kinds/actions, absent-version, foreign/unknown, stale, revoked/expired or paused/changed policy.
- Two active claimants at one revision: one success/one conflict; GET/refetch/cancel no mutation;
  commit responsible subject/revision/time and audit atomically; injected audit failure rolls back.
- Actor/operation-scoped key replay: original acceptance time/current state, no duplicate event/job/
  revision; changed body conflicts; earlier replay after later claim never takes work back.
- Original provider intent/raw hash/creator/mailbox/owner/baseline/steps unchanged. Only current
  responsible can handoff/start setup. Creator revoked after takeover can be replaced; claimant
  revoked/regranted before dispatch cannot reuse captured authority. Numeric latest-claim ordering
  and exact intent context validation fail closed on forged/malformed/future evidence.
- Four derived OperationSummary fields: separate creator/current administrator, revision and guarded
  claim affordance; null/false defaults outside guided detail. Native confirmation no Reason,
  polling preserves reviewed revision, useful conflict/uncertainty/focus states, narrow layouts.

Use disposable synthetic authorized administrator sessions for multi-admin/revocation cases; no
new saved identity or temporary simulation UI is implied.
[Review runbook](how-to/responsibility-runbook.md).


## Environment email policy and lifecycle-notice matrix — accepted 4 November 2026

Local qualification passed; see the final validation checkpoint below. [Chapter21](engineering-design/21-environment-email-policy.md)
is required for both application and configuration release gates, not just a unit-only recipient
helper or an SMTP-only override.

- Preserve canonical employee/manager/SSO identifiers, multiple distinct account usernames, owner
  identity and the null original local-recovery contact. Override effective contacts only.
- Single configured local/staging destination on SMTP recipients and every supported child-
  activation/user-invitation/recovery/notification contact field. Missing route cannot fall back
  to an engineer/creator/owner/admin email. Original-null plus explicit test route is audited.
- Production startup and both separate release paths reject override/bypass, untrusted expected-
  environment mismatch and invalid policy. Staging requires test routing before delivery/OCI
  credentials or deployment. Offline validator has no provider/SMTP/secret dependency.
- API/worker fingerprint consistency, changed destination/profile after acceptance, immutable
  original/effective routing, old queued dispatch blocked, accepted/uncertain submission not blindly
  duplicated, and prior activation mailbox never rewritten.
- Legacy serialized intent/audit/request hashes and canonical typed responsibility proofs remain
  readable and unchanged; new optional evidence does not invent prior delivery authority.
- Imported existing real contacts, username-as-delivery behavior, contact uniqueness and uncontrolled
  provider mail require qualified guards; missing visibility denies email-capable mutation. No
  sweeping/rewrite of unrelated users or promise to intercept spontaneous/manual OCI mail.
- D49/D50 initial create/import action/failure only, current responsible admin only, no fallback,
  durable deduplication/known-unsent handling and uncertain-delivery evidence. No secret, private key
  or activation-link leakage. Ordinary view/progress/success does not send.

Fake SMTP/provider and disposable PostgreSQL/browser tests must prove positive and negative behavior
without sending to real employees. Hosted CI/OCI/SMTP production qualification remains separate, and
no GitHub workflow or repository publishing is authorized by this requirement.


## Email runtime proof matrix — source candidate

Local qualification passed. [Runtime field/state map](reference/lifecycle-email.md) and
[capture/offline release runbook](how-to/lifecycle-email-runbook.md) define the source subset.
Require real disposable PostgreSQL/native-worker/local-SMTP/browser integration, separately from
complete-source unit coverage. Prove atomic staging+deferral, deduplication, readonly diagnostics,
three known-rejection attempts, interrupted/uncertain DATA no-resend and exact attempt-CAS.

Cover policy/profile/origin/contact/authority changes before egress, direct local missing-override
with nonnull employee address, original-null recovery plus override, no production/staging fallback,
old raw/typed intent compatibility, no identity rewrite and retained outbox on owned reset. Test both
release kinds independently before credentials/apply, including hosted cleartext/origin and wrong
expected-environment rejection. No live SMTP/OCI/Vault behavior is inferred from fake/capture tests.

Live OCI qualification must include multiple distinct usernames in one SAME shared tenancy/domain
using the same test mailbox; verify actual contact uniqueness/invitation/recovery. Rejecting duplicate
contact must fail closed with no employee fallback or unapproved alias feature.


### Lifecycle email final local qualification — 4 November 2026

The final validation record (private historical evidence; not distributed) supersedes this feature's source-only pending checkpoints: 1,421 full-suite tests pass, both unit-only coverage gates exceed 95%, reviews are complete, and both saved local instances were upgraded with all existing rows preserved. The release-check command covers both application and configuration paths. Hosted CI/OKE deployment, production Vault/SMTP and live OCI contacts remain separately unqualified; the feature is not a claim of complete V1 delivery.


## Email delivery category regression — 5 November 2026

Validation pending. Verify existing delivery events project/filter as email_delivery and are
excluded from Operations while retained under All categories. Directory/export must use identical
category predicates and preserve existing date/search/sort/paging/workspace guards. Actual browser
checks cover the Email delivery label and filtered rows; unit/source checks cover every allowed
kind/category without changed actor interpretation. No migration, stored audit rewrite, recipient/
delivery change or operation-detail notification-panel change is part of this refinement.


## Configuration freshness regression matrix — 5 November 2026

Refinement qualification pending. Test source/unit behavior separately from actual disposable
PostgreSQL/native-worker/HTTPS browser behavior. Confirmed Missing/Different category counts must
not include unknown, conflicting, unseen or stale-only observations. Preserve prior complete
same-context findings through stale, failed/partial and in-progress attempts; only a qualifying
complete result resolves them. No stored check state or prior evidence may be rewritten.

Cover exactly 24 hours, 24 hours plus one microsecond and 35 hours; matching-only evidence becomes
out of date without invented confirmed drift. A clock-advanced protected test must perform fresh
real MFA sign-in after expiry, never extend/bypass session authority. Assert stale_count separately
and exclude stale rows from unchecked_count; counters overlap independently of page/filter/tab.
Exercise all existing state filters plus the stale query alias: fresh-only matching, nonstale
not_checked, retained-positive drifted even while unavailable/checking, and latest-attempt filters.

Actual browser coverage must compare shared labels/counts across inventory, tenancy detail, check
directory/detail and the empty confirmed queue. Observe real completion to refresh all relevant
caches, including inactive child detail, externally started checks and fast fleet matching rows
that disappear from Confirmed drift. Queueing/failed completion cannot fabricate fresh green
status. No new migration, repair, notification, local CronJob or simulator controls are part of this
slice. Future daily acquisition is deferred until staging/Kubernetes and requires qualified
noninteractive scheduled admission/authority through the existing worker, not reused browser SSO.

[Manual regression procedure](how-to/configuration-drift-runbook.md#freshness-and-confirmed-drift-regression-review-5-november-2026).


## Accepted configuration freshness refinement — 5 November 2026

Confirmed drift counts only complete same-assignment Missing/Different findings. Check out of date,
Unable to verify, Not checked and Checking are independent verification messages, consistently
shown in inventory and Configuration Drift. Known findings survive failed/expired/in-progress
checks; fresh complete matching alone clears them. Empty Confirmed drift explains outstanding
verification, and the stale filter is distinct from Not checked. Terminal rechecks refresh all
related read caches; protected-read authorization loss is handled independently of server errors.

Local validation (private historical evidence; not distributed) records the
unit-only coverage gates, controlled-clock/PostgreSQL regressions, native browser/worker checks
and completed documentation/security/UI reviews. Existing stored rows and schema were preserved.
The drift-detection CronJob is explicitly deferred until staging/Kubernetes deployment and scheduled
noninteractive authority is qualified. Local checks remain explicitly triggered; progress polling
only reads results and never schedules a check. No local scheduler or mock-drift controls were added.

## Implemented current-month financial regression matrix

Unit suites: test_financial_values, test_financial_units, test_financial_http and
test_financial_notifications qualify canonical decimals/overflow/NaN, independent nullable values,
calendar/freshness/qualification, immutable hashes, source/authorization fences, replay/join,
continuing failure visibility, stable email episodes and environment recipient override. Unit-only
coverage remains >=95% independently per application source tree.

Disposable PostgreSQL test_financial_postgres qualifies exact composite FK/immutability, concurrent
admission, no DB transaction across GET, partial replacement, late older calculation, cycle rollover,
finite retries/peer isolation, grant/config/profile changes during GET, and email dedup/delivery/recovery.
The real HTTPS/native-worker test_financial_browser_postgres plus e2e/financial-costs.spec.ts covers
list/detail manual refresh, automatic results/ack clearing, sort controls, retrieval tooltip, route
reload and desktop/mobile320/390 layouts. Saved-instance data is never a mutating test target.

Daily scheduling, live Budget response/billing semantics, provider timeouts/permissions and OKE CronJob
qualification remain staging work. No new simulator-control page or test-only production endpoint is
a prerequisite for these checks. [Field/run contract](reference/cost-visibility.md).


## Selected configuration repair regression matrix — 6 November 2026

The [implemented flow and field map](reference/configuration-repair.md) requires these cases:

| Scenario | Required evidence |
| --- | --- |
| Missing/different, fresh complete check | Preview and admission freeze exact categories, assigned content, source check, context and bindings |
| Stale, unknown, foreign, busy, changed observations or assignment | Fail closed before provider writes; no latest-baseline substitution |
| Selected policy with unselected quota drift | Only policy written; quota finding remains, no desired revision or false whole-config verification time |
| Partial write/readback failure | Prior findings retained; explicit retry independently rereads exact bindings; no duplicate accepted work |
| New publication while queued | Original assigned baseline and overrides remain frozen |
| Concurrent/pending old check and repeated worker delivery | Final-generation check wins; superseded reads cannot green; exactly one sealed successful repair check |
| All-category repair writes | Unit and SQL: 4 categories × Missing/Different × inherited/override profile; exact values, unchanged unselected objects and desired revisions |
| Concurrent admission with independent request keys | Same administrator submits two simultaneous requests; one accepted, one blocked, no duplicate operation |
| Real UI preview/confirm/reload at desktop/mobile | Existing protected HTTPS session, native worker and disposable PostgreSQL; sequential selected repairs of all four categories with accepted overrides; no fake production endpoint |

Both unit-only 95% gates and independent documentation, security and responsive UI reviews remain
required. A local simulator result does not qualify OCI writes or deploy daily drift scheduling.


### Real OCI configuration drift and repair manual gate

Hands-on validation is explicitly deferred until a real provider and disposable child tenancy are
available. The [pending manual checklist and current automated coverage](how-to/configuration-drift-runbook.md#pending-real-oci-manual-validation)
cover each managed category, selected-only repair, overrides/assigned baseline, authorization loss,
partial/unknown effects, real object recreation/OCID rebinding and overlapping reads. All live cases
remain Pending. No local drift-injection scaffolding or saved-instance mutation is requested.
The 20-case unit comparison matrix remains distinct from the 16-case repair-write matrix and
all-category browser journey. None is a claim of live OCI qualification. See the
[all-category repair field/coverage note](reference/configuration-repair.md#all-category-repair-qualification--6-november-2026).


## Required-user presence boundary — 6 November 2026

[Source field map and integration limits](reference/required-user-presence.md) define this internal
read-only capability. Units must distinguish exact authorized complete presence/absence from
unqualified domain, denied/timeout/delayed/partial/unsupported reads; isolate automation/recovery
subjects; reject same-name adoption, wrong-domain404, changed actual IDs, cross-attempt/generation
facts and out-of-window timestamps. Unknown cannot carry confirmed identity facts. Models reject
secret fields and the deferred audit-user purpose. Neutral modules must load without simulators.
Existing full database/browser suites remain regressions, not execution of an uncomposed capability.
No new production binding/check/secret storage or public screen is qualified here.


## Permanent-user capture regression matrix — 6 November 2026

- Unit: separate automation/recovery OCI and SCIM identities, correct workspace/organization/parent/
  child/domain, exclusion of both temporary identities, duplicate/null subjects, sanitized failures,
  forbidden secret extras, evidence pairing, version 1/2 compatibility and capture-before-retirement.
- PostgreSQL: version 3 create/import retain the same exact capture in operation-step and immutable
  audit evidence; completed worker redelivery preserves it. Forward migration 0022 changes only the
  step allowlist and must retain earlier data and valid legacy step keys.
- Playwright: normal guided create/import displays the verified permanent-user capture step through
  the real API/worker/store path. Existing handoff/reload/responsive regressions remain required.
- Live OCI: exact returned identities, interrupted setup, same-name/different-ID protection and
  post-policy checks before temporary retirement remain in the [manual manifest](how-to/real-oci-test-manifest.md).

Do not treat retained onboarding provenance as canonical current access bindings or current health.


## Canonical identity-binding regression matrix — 6 November 2026

- Unit: typed capture/hash/current-step/current scope and version gates, exact three-row shape,
  idempotent IDs/generation, partial/conflicting mappings, transaction guard and closed DB failures.
- PostgreSQL: actual create/import rows and immutable source, wrong workspace/child/domain/event/
  operation/identifiers, no identity rewrite/delete/truncate, partial-insert rollback before cleanup,
  retry, whole-tenancy and employee-flow termination retirement, failed termination preservation,
  historical v1/v2 and already-captured v3 no-backfill behavior.
- Installed roles: API SELECT only; denied insert/update/delete/truncate; worker insertion and narrow
  retirement columns, with identity rewrite denied. Full native worker/browser onboarding remains
  required and exercises the new table through actual runtime grants.
- Migration/reset: no historical adoption, preserved operation/audit/step rows, reviewed local-only
  reset table set and foreign-key ordering; no CASCADE or weakened owner/container guards.
- Live: binding identity/provenance agreement and accepted-termination ordering remain Pending in
  the [manual test manifest](how-to/real-oci-test-manifest.md). Active identity is not access health.


## Required users read-only screen — 6 November 2026

The [field/behavior reference](reference/required-users-screen.md) and
[local review runbook](how-to/required-users-runbook.md) define this identity-record subset.
Required cases: exactly two independent purposes; pending and legacy unrecorded states; actual
create/import IDs and immutable source links; retained retired facts; scoped foreign-workspace404;
no provider/job/audit/binding mutation on read; malformed target/auth/expiry/safe-error behavior;
initial loading vs read failure vs successfully unrecorded identities; failed refresh with qualified
retained records; no retained facts after401/403; private cache isolation/invalidation; native
keyboard disclosures/refresh/source links and responsive widths1280/768/390/320. Use actual SQL
and installed worker/browser flows as well as unit assertions. No live health/readiness claim is
qualified; those cases remain Pending in the [OCI manifest](how-to/real-oci-test-manifest.md).


## Presence-only connection regression matrix — 6 November 2026

See the [implemented field/model guide](reference/user-presence-connections.md). Required cases:
create/import capture; old marker-absent v3 captures remain unbound; exact replay versus conflict;
whole capture rollback/retry before cleanup; current domain/automation role/source FKs; forged
inserts while the child is legitimately pending; an in-memory marker cannot alter accepted intent;
both deletion entry points retire, failed initiation preserves; API SELECT only, worker immutable
columns denied; owner-only reset inventory; package includes frozen SQL/version/hash. Internal
version 2 rejects obsolete assignment and credential fields, with independent connection-revision
and user/domain fixture tests. No new UI control or live presence evidence is claimed by this slice.

## Manual user-presence checks — locally qualified, 6 November 2026

Source scope and all fields: [check reference](reference/user-presence-checks.md). Required cases:

- Exact fresh create/import capture and accepted connection; historical/partial/unconfigured/pending/
  inactive/busy children disabled, no name-based or read-triggered backfill.
- Current session/admin/revision/actor, CSRF/Origin, foreign scope, one-key replay, different-request
  conflict, distinct-key independent admission and atomic intent/check/audit/native deferral.
- Provider reads outside transactions; independent subject results and timestamps, exact response
  scope/read window, malformed/denied/domain/absence cases, no expected-ID-to-observed-fact shortcut.
- Attempt reclaim/late callback fences, no terminal overwrite, changed binding/connection/child/
  policy/grant before or after read, paused execution, superseded results and backward clocks.
- Latest admission sequence wins even when older work finishes later. Freshness at 24 hours,
  per-account stale labels, pending progress preserving dated results, new unavailable results not
  silently borrowing earlier success. The 30-second window is late-result validation, not SDK timeout.
- Real PostgreSQL provenance/guard/grant/rollback/reset evidence; authenticated native browser
  Check now → independent Present/Permissions Not checked → View check, cache/auth handling,
  uncertain-response key reuse while mounted, keyboard focus and responsive containment.
- Read-only behavior: no cloud mutation, credential disclosure, repair, notification or scheduler.
  Actual OCI credentials, SDK bounded I/O, exact-domain absence and propagation stay Pending in the
  [live manifest](how-to/real-oci-test-manifest.md). All required local lanes, independent reviews and main-preview preservation now pass; the parallel preview remains unchanged. [Final receipt](history/manual-presence-checkpoint-2026-11-06.md).

## Required-user inventory summary — locally qualified

The [complete field map](reference/required-users-summary.md) and
[manual review](how-to/required-users-runbook.md#inventory-summary-source-checkpoint) define this
source follow-up. Required cases:

- Exact four-field summary and per-user four-field views, independent UTC times/provenance, safe
  defaults and no changes to the existing 22-field directory or persisted check schema.
- State matrix: fresh dated Missing first; unsupported positive with no date/check reference becomes unavailable; then stale, Unknown/unavailable, both fresh dated Present, otherwise Not checked. Cover mixed Present/Unknown/stale and both DTO/frontend positive guards; historical unconfigured identities remain Not checked and inactive rows hide the link.
- List/detail equivalence using shared strict context/evidence/age logic; latest admission order,
  changed valid context versus configured broken canonical domain/signer/source references, missing/corrupt audit evidence, invalid pending intent and no older green fallback. Configured corruption must be per-child unavailable in inventory and closed 503 in detail, not a clean default.
- Four added queries for active visible page IDs only, every query workspace/ID-scoped; empty or
  non-active input adds no queries. Use real SQL/scoping tests as well as isolated unit fixtures;
  mocked query-count assertions do not prove database isolation or transaction behavior.
- Native Users link targets the real required-users section on the exact child; focus follows terminal success or 503 but never 401/403, with no retained unauthorized data. Cover reload/new tab, per-account accessible descriptions/UTC, pending refreshes, Users:/Config: visible/ARIA consistency and unchanged detail configuration labels. Verify actual 320-pixel body containment, including hidden description positioning; keep existing paging/search/sort and all configuration-link assertions.
- No GET provider call, new job, mutation, navigation badge, daily scan, email, credential or
  privilege/repair claim. All required lanes/reviews and the main update pass: 1,587 backend units, 458 frontend units, all 352 integration/native/browser cases in 430.159 seconds; no failures/errors/skips/timeout. All 29 existing public tables are preserved and port 8444 is unchanged. [Final summary receipt](history/required-users-summary-checkpoint-2026-11-06.md).


## Lifecycle notice parity regressions — 6 November 2026

The [implemented lifecycle scope](reference/lifecycle-email.md#lifecycle-notice-parity--6-november-2026)
retains the existing outbox and contracts. Required units cover every additional action's
attention/failure notice, responsible-only frozen test routing, excluded local decisions/legacy
unguided onboarding and silence for routine states or provider-only waits. PostgreSQL tests
accept join/remove/transfer/offboard/delete through real previews and active grants, exercise
normal completion and both blocked/unexpected provider failures, and verify one notice on
replay. Send-time grant revocation, replaced authorization revision/email, unclaimed responsibility
and resolved operation must prevent delivery. Email-less recovery failures remain blocked without
fallback; ordinary success sends nothing. Existing known-rejection, uncertain-acceptance and
transaction rollback protections remain required. Native worker/loopback Mailpit/HTTPS Playwright
exercise a non-onboarding deletion notice through the installed runtime roles and existing
read-only delivery panel, category and export. No product fault-injection control is introduced.
These are local simulation assertions; staging/production provider mail remains a manual gate.

## Directory restoration and destructive consent — source correction, qualification pending

[Workflow fields/rules](reference/organization-workflows.md#destructive-consent-and-directory-return-correction--source-checkpoint)
and [manual review](how-to/organization-mapping-runbook.md#return-and-destructive-consent-correction-review-after-installation)
require the following regression matrix, without weakening complete-census departure inference:

- Fresh applied full and partial actual employee rows restore already-offboarded stable identities,
  settle only handled absence on an immutable evaluation copy and open one setup episode as needed.
  Cover legacy removed_capture_at=null with prior source/publication fallback and no absence cycle. Include merged survivor → cleanup → absence/explicit offboard → fresh current-email return, resolving canonical supplied rows to the retained stable UUID rather than immutable original org_person.email.
- No restoration from references, stale/equal/replayed/staged/rejected/config-only evidence or while
  pending, exempt or merged. Repeated presence creates no duplicate setup episode. No source/audit/
  operation history, tenancy, user or association resurrection; role defects stay independently open.
- Standalone whole/person tenancy deletion, member removal and owner transfer preserve directory
  status/independent absence for both present and absent zero-link people, including review rows, source-derived absence flags and application-decision/reclassification paths. Source-present last-link
  cleanup can set existing setup flags, without automatic provisioning or absence settlement.
- Only explicit offboard_person for an actually absent eligible employee changes offboarding state;
  current actual-row presence hides/refuses it. Root, kept-obligation and pending-work guards remain.
- New admissions for exactly offboard_person/delete_tenancy/remove_member/transfer_owner/merge need
  confirm_destructive=true. Missing/false consent produces no mutation/queue/audit transition. False
  omission preserves old canonical hashes and current-authenticated exact committed replay precedes
  the new guard; changed requests still conflict. Consent resets on action/target/plan/preview changes.
- Separate TenancyDeletionCommand keeps its seven fields/confirm_deletion; DeletionPerson's seven
  fields retain leaves_directory, always false. OrganizationAction has 21 fields; no storage change.
- Unit, disposable PostgreSQL and actual browser coverage must include all cross-surface directory/
  review/cache outcomes and consent UI/API negatives. Current notification parity work is preserved;
  new full validation and saved-preview qualification are not claimed yet.

## Accept onboarding without a tenancy

Required regression cases for keep_without_tenancy: ordinary and unmapped current employees remain
included with zero associations; only setup review closes; replay is exact; repeated feeds and
name changes do not reopen setup; later create/import/join remains available. Reject absent,
exempt, merged, pending, associated and unrelated-review targets or stale context. Preserve
independent mapping/role and future departure work. Cover admission and database persistence
in unit/disposable PostgreSQL tests and the real dialog in HTTPS Playwright, including narrow
viewports, no destructive checkbox, immediate decision receipt and repeat upload. No live OCI
qualification is needed for this application-only decision.

## Shared-tenancy member entry and user-data refresh

Required UI coverage: Add member is visible only for active shared tenancies and disabled for known
pending work; search requires at least two characters, bounded query/25-result page, and filters
existing/absent/excluded/pending candidates. No valid selected employee means no continuation,
including script submission. Search changes clear selection; cancel/Escape releases the modal
without mutation. Authorization failure hides choices, expires the session, and cannot advance.
A native HTTPS case selects an employee from the tenancy detail, verifies the exact preselected
child, and completes the existing membership workflow. Toolbar centering and picker width are
checked at desktop and 320/390-pixel widths.

Required-user acquisition is now labeled Refresh user data; tests still exercise the same queued
check endpoint, eligibility, pending/polling, exact-key retry and dated presence publication.
There is one normal acquisition button per section, with no separate saved-record user refresh.
Page-level refresh/background reads remain GET-only, with Retry loading users only on read failure.
Capture the acquisition control at desktop and narrow widths. No new provider call, grant, table or OCI-specific qualification
case is introduced; existing shared membership and presence live cases remain mandatory.
