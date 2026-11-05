# Development progress

29 October 2026 | Local P0 preparation | Git check-ins/publication remain on hold

[Build order](../engineering-design/18-database-ci-and-build-order.md) ·
[Security policy](../security-review-policy.md) · [Finalization gates](design-finalization-2026-10-28.md)

## Synthetic test milestone

**P0.1: complete locally.** The preserved organization suite no longer needs either private HR
sample. The inputs are independently invented, not anonymized copies of the real reporting graph.

| Change | Evidence / retained behavior |
|---|---|
| Four-column CSV | [Synthetic fixture](../../prototype/backend/tests/fixtures/synthetic_organization.csv):242 unique fictional profiles, a root, six leaders, eighteen managers and217 engineers; all addresses use `example.test` |
| Legacy workbook adapter | [Workbook regression](../../prototype/backend/tests/test_reconcile.py) creates281 rows in a temporary workbook, including20 missing manager profiles and34 empty territories; verifies exact missing-manager evidence without qualifying absences |
| Full-hierarchy demo | [Synthetic demo](../../prototype/scripts/demo_synthetic_organization.py) reconciles242 people; explicitly non-authoritative and undated, so it cannot establish absence conclusions |
| Disposable integration runner | [Runner](../../prototype/scripts/run_postgres_tests.py) now runs the synthetic demo instead of reading the private workbook/configuration |
| Directory labels | Missing source names use the observed name or email fallback; no hardcoded executive identity. Two API regressions cover root profile present/absent |
| Local connection safety | Synthetic publication requires psycopg + loopback + exact `otm_org_test`; both demo and local Store reject query parameters that could override host/database/service. Eleven negative tests prove rejection before repository/engine access |

Validation from a clean test-only export with a fresh editable environment:

- **147 tests passed**, including 101 PostgreSQL-marked cases; a separate non-database run passed46.
- The driver's synthetic PostgreSQL publication completed with242 people and no absence eligibility.
- Imports resolved inside that export, not the working prototype or its saved environment.
- The export omitted the private input directory, saved connection state and original private-data
  demo scripts. The existing CLI source was included because a preserved regression exercises it.
- Ruff, format and named-definition documentation checks passed. Independent security review
  rechecked the query-option bypass correction; documentation and bounded display reviews passed.
- Private CSV/XLSX input checksums are unchanged; the persistent lab was not used by these tests.

A clean export initially exposed a missing CLI module; it was added rather than dropping the
regression. Security review found URL query options could override parsed connection targets;
this is now blocked in the demo and shared local-only Store with meaningful negative tests.
No new application dependencies were introduced. The only test configuration change makes the
local script import path explicit for either pytest entry point.

Sanitized local validation receipt (private historical evidence; not distributed)
records scope, results and limitations. A private source-only checkpoint and clean-export manifest
are retained under ignored `.local-dev`; neither includes the persistent database or credentials.

## Local quality tooling checkpoint

**P0.2: tooling validated locally; coverage and publication gates remain open.**
See [local quality checks](../how-to/local-quality-checks.md) for commands, scope and remaining work.

- Full regression run: **165 passed**, including 101 PostgreSQL cases in a disposable container.
- Unit-only gate: **64 passed; 693/1,878 lines (36.901%)** across all 15 application modules.
  The command correctly returns failure against 95%; no excluded source or integration coverage.
- Locked advisory inventory: **64 external dependencies**, including the pinned build backend
  and inactive-platform entries; no known vulnerabilities or missing/skipped packages.
- Bandit findings were five identifier-SQL false positives. Direct schema validation and four
  rejection-before-execution tests protect the boundary; narrow B608 annotations were reviewed.
- Pinned Gitleaks installation verifies official checksums and extracts only its executable.
  The initial 418 matches were synthetic UUID references; independent review verified all of them.
  Obvious placeholder IDs preserve fixture relationships without scanner exceptions. The final
  167-file candidate had zero secret findings; the generated fake-token check detected its sample.
- Independent security review found no new blockers in the reviewed gate, installer or SQL changes.
  It does not grant publication clearance, provider qualification or whole-application certification.

Sanitized validation receipt (private historical evidence; not distributed) records
the exact counts and open gates; a source-only private checkpoint is retained under ignored
`.local-dev/checkpoints/p0-quality-2026-10-28`.

The source candidate still has real identity examples. No Git changes were staged or committed,
no hosted repository was created, and neither the persistent database nor original feeds were modified.

## Reusable organization decision tests

**P0.3: isolated business decisions covered; production extraction remains pending.**
This batch adds 120 unit cases without changing application behavior, dependencies, screens or
source scope. The working prototype continues to support demonstrations.

| Reusable test suite | What it establishes |
|---|---|
| [Registry decisions](../../prototype/backend/tests/test_registry_decisions.py) — 64 cases | Context/workspace checks; employee eligibility; create/import/shared membership; tenancy naming and ownership restrictions; complete offboarding plans; last-link removal; transfer; return/re-onboarding; inventory action projection |
| [Review decisions](../../prototype/backend/tests/test_review_decisions.py) — 30 cases | Allowed actions; episode-specific closure vs permanent exemptions; explicit email alias chains/cycle rejection; source/effective conflict fingerprints; stale/closed/informational case rejection; delegation to the same association coordinator |
| [Registry evidence](../../prototype/backend/tests/test_registry_evidence.py) — 26 cases | Deterministic legacy state projection; conservative ambiguous deletion; qualified absence/return chronology; durable explicit exemptions; reference-only and cross-employee evidence isolation |

The tests invoke actual business decisions with synthetic domain models. Persistence and selected
projection seams are stubbed; evidence tests supply already-fetched rows. They do not establish
SQL scoping, database rollback, production SSO or real OCI behavior. The 101 PostgreSQL cases remain
separate and required. Production extraction must port these decision scenarios, adapt the repository
seams, and retain integration tests; local actor identities and simulated synchronous success remain
prototype-only.

- Unit-only result: **184 passed**, zero skips/failures; **1,028/1,878 lines (54.7391%)** across all
  15 modules, up from 36.901%. The unchanged 95% gate correctly exits 1.
- Full regression result: **285 passed**, including the existing 101 PostgreSQL cases and synthetic
  242-person publication in a disposable container. The existing framework warning remains visible.
- Independent security and documentation reviewers inspected the new tests; the final two evidence
  cases implement the security review's identity-isolation suggestions.

Validation receipt (private historical evidence; not distributed) records
the completed test runs and review dispositions. The 170-file local source candidate has zero
Gitleaks findings; publication privacy clearance remains open. Dependencies and application source
are unchanged from P0.2, so their recorded scan scope is unchanged.

This is preserved reusable logic, not a production application bootstrap. No Git check-in or
publication is authorized by this checkpoint.

## Separate production backend bootstrap

**P0.4: local production package started; P0 and hosted merge enforcement remain incomplete.**
The user's coverage clarification applies the 95% gate to production from its first slice. The
preserved prototype remains a separate diagnostic/characterization project. All behavior ported
into production must enter its complete-source unit gate immediately; imported prototype packages
are not an allowed way to hide application source from measurement.

- [Production setup](../../backend/README.md): isolated Python environment and pinned lockfile,
  `backend/src/otm` package, application factory and process-only `/health/live` endpoint. No
  business routes, local actor/reset endpoints, credentials, SSO or migrations are mounted.
- Seven production bootstrap tests pass; all **11 statements across two modules** are covered.
  This tiny result describes the bootstrap, not future business features. A real temporary
  unimported-file probe failed the gate at **11/12 (91.6667%)** despite passing tests; it was removed.
- [Shared coverage checker](../../scripts/check_unit_coverage.py) now serves both Python projects.
  The prototype entry point is a thin fixed-path adapter; production code does not import the lab.
  The retained 18 gate regressions and 120 isolated decision cases pass against the shared tool.
- The production wheel and source distribution build successfully. Generated distributions,
  virtual environments and test reports stay ignored. The documentation checker now includes
  production source/tests as well as the preserved lab and tools.
- All **57 external production lock entries** were audited with no known vulnerabilities or
  skipped/missing packages; Bandit reports no production-source findings. Independent security
  review passed the small application boundary, lock evidence and shared-gate extraction.

The full **285-test** prototype suite and synthetic publication passed again after tool extraction.
Bootstrap validation receipt (private historical evidence; not distributed)
records the local scope and open gates.

Prototype tests remain retained; their coverage is still **54.7391%** and the diagnostic command
continues to return failure. This does not lower the production threshold or complete hosted CI,
frontend, database/browser tests or publication privacy review. No Git check-in or publishing.

## Internal inspection facade and simulator

**P0.5: first typed production read capability implemented locally.**
[Field/behavior guide](../reference/inspection.md) maps every implemented context, target,
observation and evidence field back to the approved execution/data design. No table or migration
was added; the proposed ER remains unchanged.

- `InspectionProvider` defines one explicit internal `inspect_tenancy` method. The pairing service
  validates exact attempt, child, parent, organization, non-self-parent relationship and capture
  times before returning confirmed facts. It cannot claim onboarding or termination completion.
- Closed, strict, frozen models reject undeclared input and invalid generations. Safe result
  families distinguish confirmed, unobservable and unsupported reads. Unexpected adapter errors
  and malformed results become fixed diagnostics without chained raw provider content.
- The simulator has independent per-workspace provider/binding state, revoked/rotated access,
  delayed visibility, named read faults, retained in-memory read evidence and an explicit clock.
  Populated overlapping workspace fixtures verify scope isolation. No SDK, network, secret,
  database, email or mutation capability is used.
- Runtime facts preserve `home_region_key` separately from nullable `home_region_identifier`, as
  chapter 11 requires. No mapping is invented. This expands the older C2 draft's ambiguous region
  shorthand; the Python models and generated artifacts define the current implemented subset.
- [Schema exporter](../../scripts/export_backend_contracts.py) generates two structural artifacts
  from the runtime models and checks drift. Custom UTC/nonblank validation and request/result
  pairing remain runtime responsibilities; JSON Schema alone does not encode every invariant.
- **62 production tests pass**, with **182/182 statements across all six source files (100%)**.
  The unchanged 95% complete-source gate passes, without excluded lines or integration coverage.
  The original HTTP boundary tests still require that only process liveness is mounted.
- Independent security and documentation review passed, including the final workspace-isolation
  and region-field corrections. No dependencies changed from the audited P0.4 production lock.

Inspection validation receipt (private historical evidence; not distributed) records
scope and limits. This does not implement the durable import-inspection workflow, real OCI adapter,
SSO/dispatch authorization, persistent audit/evidence or any tenancy mutation. The retained prototype
and its last 285-test regression evidence are unchanged; they were not relabeled production tests.

## Native runner qualification

**P0.6: candidate transaction and worker mechanics qualified locally; production integration pending.**
The [isolated experiment](../../prototype/experiments/runner/README.md) keeps candidate Procrastinate
3.10.0, SQLAlchemy 2.0.54 and psycopg 3.3.6 separate from both the production backend and the preserved
organization demo. There is no custom connector, replacement dispatcher or new production table.

- **29 cases passed**, with no failures, skips or timeout: 12 transaction/acceptance cases, five
  native-worker lifecycle cases, nine target guards and three no-database process-cleanup probes.
- Matching PostgreSQL transaction IDs and independent worker/reader visibility confirm native
  enqueue uses the exact SQLAlchemy-owned psycopg transaction. Caller error, queue insertion
  failure and a real deferred-constraint rejection at COMMIT all roll back intent/audit/job.
  A real AUTOCOMMIT-mode connection is rejected before any application write.
- Two physical database transactions race scoped request keys. Same intent recovers one operation;
  conflicting intent rejects one caller. Lost responses and SIGKILL immediately before/after commit
  preserve the same all-or-none/recoverable outcome.
- Real workers qualify configured no-effect retries, operation locking, duplicate delivery,
  graceful SIGTERM, abrupt SIGKILL and the local effect-commit/runner-ack gap. SQL idempotency is
  not an OCI exactly-once guarantee. Native heartbeat-aware stalled discovery plus explicit retry
  is required; worker restart alone does not recover stalled work.
- The first expanded test setup incorrectly used drain mode for long-lived worker behavior.
  Three failures exposed that distinction. Tests now select native wait mode where required,
  keep the same assertions, and still use drain mode for the empty-queue visibility probe.
- Security review caught a timeout descendant-process leak. The driver now owns a separate process
  group, stops it on timeout/error/completion and reaps its leader. Sentinel-grandchild tests verify
  cleanup; nested finally blocks preserve owned-container cleanup even on report errors.
- The candidate lock's **53 external entries** have no reported advisories or missing/skipped
  dependencies. Final source Bandit and the reviewed narrow local-process suppressions are recorded.
  Independent security review passed after the cleanup correction; documentation review corrections
  clarify immediate child cleanup and persistent-vs-drain mode.
- Production source and dependency lock remain unchanged. Its **62 unit tests still pass**, with
  **182/182 statements across six files**. The experiment is not counted as production unit coverage.

Qualification validation receipt (private historical evidence; not distributed) records
scope and limits. The toy audit is not immutable production history, digest strings are not the final
canonical fingerprint implementation, and fixture actor labels provide no authentication. Managed
PostgreSQL privileges, real OCI effects and production operation/step/runner integration remain work.
The existing production ER and live laptop database are unchanged; no Git check-in or publishing.

## Production operation admission

**P0.7: internal migration-backed acceptance implemented locally.**
[Implemented ER and field map](../reference/admission.md) lists every actual operation/audit
column and closed intent field. Canonical chapters 02/11/18 link this checkpoint and distinguish the
two production application tables from the separate ten-table prototype and full 28-table target.

- Required injected authorization precedes request/replay lookup. Issuer+subject qualify actor
  identity; the command cannot supply admin claims, parent policy, access bindings or credentials.
- One native PostgreSQL transaction accepts operation, immutable intent and reference-only queue
  job. It returns queued only after COMMIT. Scoped request uniqueness handles concurrent matching
  and conflicting callers; compatible replay preserves the original intent despite changed policy.
- Frozen forward-only Alembic SQL includes the stock qualified runner schema and upstream license.
  Deferred composite FKs enforce the exact current intent. Audit UPDATE/DELETE/TRUNCATE fail.
  The initial schema accepts intent events only; worker outcomes require a forward migration.
- **95 unit tests pass**, covering **322/322 statements across all 15 runtime source files (100%)**.
  The 95% unit-only gate includes unimported modules and has no exclusions. Migration deployment
  artifacts receive mandatory real PostgreSQL validation rather than entering mock unit coverage.
- **120 total tests pass** against a fresh disposable PostgreSQL 16 container: the 95 unit cases
  plus 25 database cases, with no failures/skips/timeouts. Tests prove same transaction IDs, scoped
  replay/concurrency, real enqueue rollback and deferred COMMIT rejection, unsupported actual
  transaction modes, temporary-table shadow resistance and append-only history. A negative schema
  comparison test verifies that actual FK changes remain detectable after default-schema normalization.
- All 72 external lock entries have zero reported advisories or skipped/missing dependencies.
  Production Bandit, Ruff/format, all 86 Python files' inline documentation and five generated
  structural contract checks pass. The wheel contains exactly seven explicit migration assets.
- Shared owned-process cleanup extraction retains all 12 qualification cleanup/target-guard tests.
  The unchanged organization demo was not rerun or relabeled production; its last 285-test evidence
  remains separate. The two private input checksums remain unchanged; no saved database was used.
- Independent security review passed after hardening queue lookup order to `pg_catalog,public,pg_temp`.
  A source-only candidate secret scan covered 230 files with zero findings. This does not clear
  real identities in legacy design/examples for GitHub. No Git files were staged or committed.

Admission validation receipt (private historical evidence; not distributed) records exact
scope and limits. The HTTP app still exposes only liveness; corporate SSO/session composition,
registered worker dispatch and observations, managed database role qualification and real OCI
integration remain to build. No task is registered to falsely turn queue acceptance into success.

## Durable simulated inspection

**P0.8: first registered read workflow implemented locally.**
[Worker flow and implemented ER/field map](../reference/worker.md) documents the three production
application tables, all 16 logical-step fields and the closed dispatch/outcome records. The
canonical execution/data/delivery chapters and backend guides now distinguish this implemented
subset from the separate ten-table prototype and full 28-table design.

- Fixed native task registration consumes only the queued operation UUID; no default worker launch,
  permissive authorizer, business route or OCI adapter was introduced. Current authority is required
  before claim, before the read and after the read. It cannot silently retarget frozen intent.
- Claim and publication are short transactions around a provider read outside the database.
  Exact operation revision, intent, step, attempt and generation prevent stale publication.
  Normalized simulated facts survive in immutable audit; the step points at that durable event.
- Forward migration 0002 adds the existing approved logical-step entity. Non-intent audit rows
  use null revision while intent requires a non-null positive value. Ordinary NULLS DISTINCT
  uniqueness and the exact-intent FK suffice, without a new pointer kind/index/coordinator.
  Migration 0001 and audit rewrite protection remain unchanged.
- Confirmed inspection completes only the read. Denied/unknown/unsupported observations remain
  Needs attention. Native runner success is separate from business success. No tenancy is adopted,
  created, configured or deleted. Read redelivery after interruption advances generation; no
  automatic retry or generic mutation-redelivery behavior was added.
- **152 unit tests pass**, covering **505/505 statements across all 19 runtime files (100%)**.
  All **192 tests pass** in disposable PostgreSQL: 152 unit plus 40 database cases, with no
  failures, errors, skips or timeout. Tests cover actual native worker execution, revocation,
  concurrent claims, stale-result rejection, publication rollback/read recovery and SQL constraint
  negatives. A real admission written under migration 0001 survives the upgrade to head.
- The migration-preservation test first exposed duplicate imported session-fixture registration.
  Moving the database fixture to shared conftest makes the old-schema setup execute once; the
  unchanged preservation assertions now pass. The initial failing evidence is retained privately.
- Independent security review caught missing nested-result checks at durable publication. Added
  attempt/code/exact-target/self-parent checks and negative tests before writes; re-review passes.
  The reviewer independently ran all 152 unit tests and inspected database evidence.
- Documentation review mapped all 16 step fields and checked all 27 new runtime/migration named
  definitions. Admission-time prose was corrected to acknowledge the now-implemented read guards.
  Inline documentation across 94 Python files, Ruff/format, seven generated contracts, production
  Bandit and the wheel's nine explicit migration assets pass.

Worker validation receipt (private historical evidence; not distributed) captures the final
source checkpoint, scanners and scope. The lock is unchanged from the audited 72 external-package
admission baseline. Production SSO/authority and credentials, real OCI, managed database grants,
operational recovery UI and hosted CI/protected master remain work. No live database or private
input was used, and no Git staging/check-in/publication occurred.

## Session verification and request authorization

**P0.9: session-backed request/command verification implemented locally; SSO lifecycle pending.**
[Session guide, ER and field map](../reference/authentication.md) documents the fourth production
application table and all 15 session fields. Current identity/data/delivery chapters and earlier
backend guides now link the staged four-table implementation, separately from prototype ten and
proposed target 28. No engineer/person directory or role table was added.

- Default app composition remains liveness-only. Explicit session service plus HTTPS-origin
  settings adds only protected `GET /api/session`. No login/callback/mint/logout endpoint,
  permissive provider, trusted-identity-header bypass or business API route was introduced.
- Strict bounded opaque-cookie parsing precedes unique digest lookup. Trusted issuer, expiry,
  revocation and current exact-subject/workspace administrator entitlement are required. The
  repository releases SQL connections before external verification. Admission rechecks the
  session and current role rather than trusting an earlier request principal.
- Configured non-health requests require HTTPS and exact Host; unsafe requests require the exact
  Origin and a custom header. Duplicate security headers/cookies fail before access. Content-type
  parsing stays per route to preserve planned multipart CSV uploads. Session/error responses are
  minimal and non-cacheable; authentication errors use three enforced public status/code pairs.
- Frozen migration 0003 implements hash-only metadata, uniqueness and timestamp/hash constraints.
  Scoped revocation matches UUID/digest/workspace and retains its first timestamp. No raw handle,
  identity/access/refresh token or arbitrary claim is stored. No repository issuance method exists.
- **225 unit tests pass**, with **740/740 statements across all 24 runtime files (100%)**. The
  full disposable-PostgreSQL suite passes **280 tests: 225 unit plus 55 database cases**, without
  failures/errors/skips/timeouts. This includes real request revocation, current-session admission,
  forged-cookie/header rejection, unsafe Origin rules, scoped SQL revocation and metadata constraints.
- Independent security review passed and independently ran 73 focused session/HTTP/storage unit
  cases. Documentation review mapped all 15 fields and checked 45 affected named definitions.
  Prior-guide three-table wording was corrected; no new UI flow is represented as implemented.
- Ruff/format, production Bandit, inline documentation across 104 Python files and eight generated
  schemas pass. The built wheel matches all 24 runtime files and 11 explicit migration assets with
  valid frozen checksums; local state is excluded. No dependency was added or upgraded.

Session verification receipt (private historical evidence; not distributed) records final
source/scanner scope. Starlette request middleware does **not** fulfill the required maintained
SSO/session-library integration: provider registration, OIDC validation, secure cookie issuance,
fixation handling, lifetime/logout, CLI authentication and revocation/proxy semantics remain work.
No live SSO/OCI or saved database was used. The organization prototype and private inputs remain
untouched. No Git staging, check-in or publication occurred.

## Function documentation placement — user preference

**29 October 2026: all active function purpose documentation now precedes definitions.**
[Code-documentation policy](../code-documentation-policy.md) and AGENTS.md persist the user's rule for
the inline-documentation reviewer and every later slice: same-indent `#` purpose blocks immediately
above a function or its entire decorator block. Class/module docstrings and existing critical-section
comments remain. No feature development proceeded during this change.

- Relocated 690 function docstrings mechanically across 89 files; the checker's two original functions
  were rewritten under the same rule while its placement enforcement was updated. All 692 original
  functions now follow the new convention. With six new checker-test helpers, all 698 current named
  functions across 105 active Python files have zero function docstrings remaining.
- Twelve Protocol methods that previously contained only a docstring now use the neutral `...`
  placeholder. Independent AST comparison preserves all executable structure after normalizing
  function doc metadata/empty Protocol syntax; every existing comment was preserved in order.
  Function `__doc__` intentionally changes. Module/class metadata and CLI module descriptions remain.
- The tokenizer-based checker verifies standalone, nonempty, same-indent adjacent comments above
  the earliest decorator/definition; string data and trailing comments cannot satisfy it. New
  regression cases cover nested/async functions, multiline/decorated forms and rejected old placement.
- **302 production tests pass**: 247 unit plus 55 real PostgreSQL cases, including 22 checker cases.
  Complete-source unit coverage remains **740/740 statements across 24 runtime files (100%)**.
  The preserved prototype passes 285 tests and synthetic publication of 242 fictional profiles;
  all 29 runner-qualification cases pass. Only fresh owned Docker databases were used.
- Independent security/correctness review recomputed the 89-file AST/comment proof and ran the 22
  checker cases. Ruff/format across active code, 105-file documentation validation, eight unchanged
  generated schemas, backend build and production Bandit all pass. No dependencies or frozen SQL
  changed. No UI behavior or critical-section documentation was rewritten.

Documentation-placement receipt (private historical evidence; not distributed)
records proof and test artifacts. The two private inputs and persistent laptop database remain
untouched. No staging, commit or publishing occurred.

## Class documentation placement — follow-up preference

**29 October 2026: the above-declaration convention now also applies to classes.**
The user confirmed that class purpose text should sit above `class`, just like function text above
`def`. [Policy](../code-documentation-policy.md), AGENTS.md, the persistent inline-documentation reviewer
and the tokenizer-based checker now enforce this for both declarations and their complete decorator
blocks. Module documentation and existing critical-section comments remain unchanged.

- Moved all 103 class docstrings above their declarations across 34 active Python files. Nine
  doc-only empty classes now contain an inert `pass`. Independent normalized-AST/comment comparison
  confirms no executable changes or existing comment losses; no class/function docstrings remain
  in active authored declarations.
- Regenerated eight production model schemas: exactly 25 descriptive annotation changes, with
  fields, types, required values and validation constraints preserved. Class `__doc__` intentionally
  changes; current code does not rely on it for runtime behavior. No bespoke documentation runtime
  machinery or exception to the requested source convention was introduced.
- Checker regressions now include 32 cases covering class/function decoration, nesting, multiline
  declarations, malformed/missing/misplaced comments and rejected old docstrings. The whole-source
  check passes across 105 Python files.
- All 312 production tests pass (257 unit plus 55 PostgreSQL), with complete-source unit coverage
  **742/742 statements across 24 runtime files (100%)**. The preserved prototype passes 285 tests
  and synthetic publication; native runner qualification passes all 29 cases. Tests use disposable
  databases rather than the saved laptop workspace.
- Independent security/correctness review reproduced the 34-file AST/comment proof, eight-schema
  annotation-only comparison and 32 checker cases. Build, Ruff/format, generated-contract checks
  and production Bandit pass. No dependencies or frozen SQL changed; no feature buildout advanced.

Class-placement receipt (private historical evidence; not distributed) records
source proof and final validation. Private inputs remain unchanged; no Git staging or publishing.

## Administrator provisioning direction — D58

**29 October 2026: product/authentication direction accepted; implementation not yet started.**
The user selected OTM-managed administrator grants, an initial persistent non-SSO application
recovery administrator, and strong password plus SSO-independent MFA. Use the real MFA path during
local testing before adding corporate SSO. Ordinary administrators will use SSO; retain independent
local recovery afterwards. This is separate from child-tenancy D39/D40 recovery identities.

[Chapter19](../engineering-design/19-administrator-provisioning.md) records operator bootstrap,
protected local identity, administrator-management services/UI, explicit authentication sources,
audit/session revocation, and initial authenticator-app TOTP approach. The security review found
no blocker in the direction; it requires atomic revocation/reset and session invalidation, no
identity linking by email, and throttling that cannot permanently lock the sole recovery account.
The spec, identity chapter, design hub and implemented-auth guide now point at this decision.

Detailed grant/credential fields, the expanded ER inventory, audit events, bootstrap/sign-in
implementation and screens are the next checkpoint. Existing 28-table proposed diagrams predate
this additional requirement; they are not presented as its final schema. No administrator grant,
local credential, default password or login endpoint was created in this decision-recording step.
Design/link validation passes for the updated design package. No application/runtime/test
behavior, existing database or dependency changed.

## Configurable session policy and cleanup

**29 October 2026: application settings, timeout enforcement and bounded cleanup implemented locally.**
The [central TOML file](../../backend/config/application.toml) and [settings/maintenance guide](../reference/application-settings.md)
record all seven scalar settings: schema version, 30-minute idle/eight-hour absolute defaults, daily
UTC cleanup hour/minute, batch size 500 and run cap 20. Secrets remain separately injected. A strict
bounded loader and generated schema reject unknown/invalid settings without raw private diagnostics.

- New sessions pin absolute expiry and idle duration through the lifetime helper. Configuration
  changes apply to future issuance; existing expired sessions cannot be revived by raising limits.
  Runtime checks reject idle/absolute boundaries before and after entitlement, independent of cleanup.
- Polling never updates activity. The explicit guarded activity endpoint atomically refreshes only
  the exact still-live session with monotonic server time. Client assertion is not proof of a human.
  Narrow same-origin logout works without SSO/current-role availability and clears the secure host
  cookie; a storage error reports revocation unavailable rather than false success.
- Migration 0004 adds the sixteenth session field with no new-row database default and revokes legacy
  pre-policy sessions. The production subset still has four application tables. D58 grant/credential
  schema, local MFA bootstrap/login and production SSO are not implemented by this slice.
- Bounded cleanup removes only revoked/idle/absolute-expired session rows, using SKIP LOCKED and a
  rechecked deletion predicate. It preserves live sessions, operations and immutable audit. Its work
  limit flag does not imply locked rows are gone. The real CLI is tested against disposable PostgreSQL.
- A daily UTC CronJob is rendered from the same configuration with pinned image, dedicated secret
  reference, bounded execution/retries and restricted container settings. Remote database connections
  require verify-full TLS, explicit CA and disabled GSSAPI; libpq/query redirects are rejected. The
  restricted-role test proves required column privileges and denies identity/audit access and role/
  revocation mutation. No scheduler was installed and no saved database was used.
- **389 production tests pass**, including 322 unit and 67 PostgreSQL cases. Unit-only complete-source
  coverage is **931/932 statements across 27 runtime files (99.8927%)**, above the unchanged 95% gate.
  No exclusions/integration coverage hide the remaining module-entrypoint line.
- Independent security review caught and resolved GSSAPI precedence and an inaccurate cleanup backlog
  flag; final review passes and independently ran 70 focused tests. Documentation review maps all 16
  session fields, seven configuration keys and 65 affected declarations; corrected stale logout/
  packaging prose preserves the actual HTTPS/Host/Origin guards and implementation boundaries.
- Ruff/format, 112-file documentation checks, nine generated schemas, production Bandit and the built
  wheel pass. Packaging includes 13 frozen migration assets plus the settings file. Dependencies are
  unchanged. No UI implementation/Playwright result, managed service or real SSO/OCI qualification is claimed.

Settings/cleanup validation receipt (private historical evidence; not distributed)
records source and evidence. Terraform/OKE must still provision/apply the job, ConfigMap and restricted
credentials. Nothing was staged, committed or published; the organization prototype/private inputs
remain untouched. Continue the local administrator/MFA implementation under D58 after this checkpoint.

## D58 detailed administrator design and separate configuration releases

**29 October 2026: reviewable design checkpoint; no authentication runtime changes.**

- [Chapter19](../engineering-design/19-administrator-provisioning.md#detailed-checkpoint-two-new-tables-existing-sessions-and-audit)
  now defines all 12 grant columns and 10 local-credential columns, bootstrap/reset, replay-safe
  password-plus-MFA sign-in, generic failures/throttling, management services/screens and sequential
  implementation slices. Two added tables bring the full proposed inventory to 30; actual production
  remains four, with migrations0001–0004. The existing session and audit entities are reused.
- Session entitlement must match exact grant reference and revision; revocation/reset/regrant cannot
  revive an old session. The next code slice must add that check before issuing real sessions.
  Required audit changes remain atomic with grant/credential/session writes.
- Independent security review identified immutable MFA secret references, consumed reset enrollment
  codes and uncertain-bootstrap-commit inspection. These are included without a new journal/service.
  The actual API role must fail bootstrap/reset credential writes in disposable-PostgreSQL tests;
  separately privileged operator commands are not merely hidden browser routes.
- [Separate deployment paths](../engineering-design/18-database-ci-and-build-order.md#application-and-configuration-deployment-paths)
  retain every D53 merge/test gate while configuration releases reuse the deployed image. Validation
  uses that image's settings schema, deployments serialize per environment, checksum annotations roll
  consumers and schedule changes update CronJobs. Config rollback does not rewrite pinned sessions.
- The model field index, focused [administrator ER source](../architecture/diagrams/application-administrators-proposed.mmd),
  spec, design hub and settings guide now agree. The checker enforces all 20 proposed added entities
  and exact equality of the inline administrator ER and its source. Historical core/config/finance
  renders remain scoped domain diagrams; the new administrator extension is rendered as Mermaid
  in chapter19. No conflicting application screen is introduced.
- Documentation review passes. Production tests remain the previously measured 389/99.8927%; no
  runtime implementation changed and those counts are not claimed as new authentication evidence.
  No credentials, databases, secret stores, cluster resources or hosted pipelines were created.

Next checkpoint: implement slice A (grants, security audit and exact session authorization) against
fresh disposable databases, then local password/MFA bootstrap/sign-in, then actual screens. No Git
staging, commits or publication. Detailed fields/flows are ready for user review before that schema slice.

## D58 A1: administrator grants and atomic revocation

**29 October 2026: accepted administrator foundation implemented and validated locally.**

[Administrator guide and six-table ER](../reference/administrators.md) maps all 12 grant columns,
10 reserved local-credential columns and the audit extension to current services/constraints.
Migration0005 creates the two tables, discards only pre-grant operational sessions before adding
the scoped identity FK and extends existing append-only audit for `administrator_revoked` only.
No bootstrap/default account, password, MFA seed, login or new HTTP mutation route is created.

- Current-grant lookup uses an explicit issuer registry and exact workspace/issuer/subject. Session
  verification now requires both current grant UUID reference and current authorization revision.
  A later regrant cannot revive an old session even if its revocation timestamp were cleared.
- The internal ordinary-grant revoke transaction locks the protected workspace anchor, rechecks the
  live actor/session/grant, compares target revision, changes grant revision, invalidates affected
  sessions and inserts closed audit in one commit. Protected recovery, stale/cross-scope targets
  and unavailable authority fail closed. A current-revision repeat makes no new event.
- Database protections preserve administrator identities/history, allow at most one local recovery
  principal per workspace and require operator privileges for local writes. Concurrent initial
  fixture seeding has exactly one winner. A real restricted role can revoke ordinary grants and
  update replay metadata but cannot bootstrap local access or replace password/MFA material.
  Those are test roles in disposable PostgreSQL; deployment roles remain infrastructure work.
- Independent security review found temporary-catalog shadowing in the initial operator privilege
  check. Both trigger functions now have a fixed search path and qualified catalog references; the
  real restricted-role regression infrastructure-services a catalog decoy successfully before verifying target
  writes fail with the expected SQLSTATE. UTC normalization also prevents valid non-UTC database
  presentation from causing authentication failure. Both fixes and evidence refinements re-reviewed.
- **438 production tests pass: 354 unit and 84 PostgreSQL**, no failures/errors/skips/timeouts.
  Unit-only complete-source coverage is **1066/1067 statements across 29 files (99.9063%)**,
  with no exclusions. The remaining module-entrypoint line is not hidden by integration coverage.
  Tests prove schema parity, scoped FKs/kinds, audit and deferred-COMMIT rollback, protected-account
  denial, real role privileges, replayed revocation and concurrent mutual revocation/initial seeding.
- Ruff/format, 117-file above-declaration documentation checks, 11 generated schemas, build and
  production Bandit pass. The wheel has 15 frozen migration assets plus the nonsecret settings
  sample; all 29 runtime files match source. No dependencies were added. Main design, spec and
  backend guides agree on six actual versus 30 proposed application tables; the design checker now
  also checks all backend guide links. Independent documentation review passes.

Validation receipt (private historical evidence; not distributed)
records evidence and source checkpoint. Corporate enabled-status checks, ordinary grant creation/
regrant, operator bootstrap/reset, real password/MFA issuance and UI remain subsequent work. Current
DB grant authority is not claimed to establish corporate account status. No saved prototype DB,
HR input, live OCI secret/resource or hosted CI was touched. No Git staging, commits or publication.

Next: implement the real restricted bootstrap and password-plus-TOTP path, with maintained hashing/
OTP libraries and secret facade, retaining all request guards and the 95% gate; then build sign-in
and Administrators UI. No additional design permission is needed for these accepted D58 slices.

## D58 B: real local bootstrap, password/TOTP sign-in and logout audit

**29 October 2026: local backend implementation complete; UI and production deployment remain separate.**

[Local authentication guide](../reference/local-authentication.md) documents the real `otm-admin`
bootstrap/reset command and explicitly composed guarded sign-in API. The default factory remains
liveness-only. No default password, first-visitor registration, password-only test flag, real human
administrator or saved lab DB was created. Every enrollment/credential used by validation is synthetic
and belongs only to disposable PostgreSQL or private temporary custody.

- Operator bootstrap checks actual table-owner membership before prompts, stages a fresh seed and
  requires a real code before atomically committing grant, verifier/reference, consumed enrollment
  step and audit. Every later bootstrap is refused; reset is separate, revision-checked and audited.
  Concurrent full enrollment leaves exactly one grant, credential and event. An issuer change cannot
  reset/rebind the existing protected identity. Uncertain commit never triggers automatic seed deletion.
- Maintained locked Argon2-cffi25.1.0 and PyOTP2.9.0 implement real factors. Passwords use Argon2id
  (64MiB, three passes, one lane); codes use six digits/30s/one adjacent step. Consume the greatest
  matching counter to handle adjacent-code collisions; final row locks prevent concurrent reuse.
  Reset consumes its new enrollment proof, changes revision and invalidates prior sessions.
- The MFA facade has an explicitly selected laptop adapter. Its owner-only0700 directory and0600
  regular single-link files reject symlinks in every path component; permissions remain exact even
  under restrictive umask. Random immutable IDs plus a SHA-256 content digest reject altered content,
  including well-formed edits. Seeds never enter SQL/settings/audit. Production exact-version OCI
  Vault custody is still a qualification/adapter milestone, with no local fallback implied.
- Shared failure windows/cooldown live in PostgreSQL; attempts during cooldown do not extend it.
  Per-process hash concurrency is bounded. The optional route retains HTTPS/Host/Origin/custom-header
  guards, bounds the body before copying/decoding and emits only fixed errors. Session handles are
  random32-byte values, hashed in SQL and issued only as secure host-only cookies after commit.
- First explicit logout now commits exact handle revocation and closed `session_logged_out` audit
  together, without querying an IdP/current role. Repeated/absent handles are idempotent. Audit or
  COMMIT failure rolls back server mutation, clears the browser cookie and returns unavailable.
  No fake tenancy operation, new table, challenge service or coordinator was added. Migration0006
  only extends the closed auth/logout event family; there are still six actual application tables.
- **507 production tests pass: 408 unit and 99 PostgreSQL**, no failures/errors/skips/timeouts.
  Unit-only complete-source coverage is **1427/1430 statements across35 files (99.7902%)**, with no
  exclusions. Real tests cover CLI one-time proof, replay/collisions, two-worker login and full-bootstrap
  races, reset, cooldown, exact custody, restricted API-role login/logout and audit/deferred-COMMIT
  rollback with no false success cookie. These are ASGI/SQL tests, not Playwright UI evidence.
- Independent security review found/fixed adjacent-code collision handling, zero-row credential reset,
  restrictive-umask handling and the missing atomic logout event. The reviewer independently ran67
  focused tests; final scope passes. The exact77 external locked versions were freshly audited with
  zero advisories/skips, including platform-conditional packages; five external packages were added.
- Ruff/format,127-file purpose-comment checks,13 generated schemas, production Bandit and build pass.
  Packaging includes17 frozen migration assets across six revisions plus the settings sample; all35
  runtime files match source. Gitleaks false positives were a frozen migration integrity digest and
  static prose. The reviewed scanner config keeps all upstream rules and exempts only that exact
  checksum line/path; canaries still detect a different key in the same file and that checksum outside
  the scoped path. The six added auth settings bring the file to13 scalar keys. Field-purpose
  catch-up added27 comment blocks; AST/executable-token checks preserve the prototype configuration
  behavior. Original private HR inputs remain unchanged; the prototype suite was not rerun for comments.

Validation receipt (private historical evidence; not distributed) records reviewed
scope and gates. Frontend screens, corporate SSO, ordinary administrator addition/regrant, production
Vault/operator custody, ingress/IP limits, actual API DB roles, OKE and hosted pipelines remain future
qualification. Nothing was staged, committed, pushed or published. Next: actual sign-in and
Administrators screens using the selected original-A style and these real backend services.

## Local HTTPS application and administrator UI

**29 October 2026: implementation checkpoint; final current-slice validation is recorded below.**

The [local application guide](../reference/local-application.md) now provides explicit setup,
private human-terminal bootstrap and repeated HTTPS startup. The launcher preserves an independent
instance-labeled, digest-pinned Docker PostgreSQL database and private application directory. It
creates no default administrator and does not connect to the preserved organization prototype.
Owner/runtime credentials are separate, but the same OS user can read both from private state;
production isolation is not implied. TLS is a 30-day self-signed localhost certificate, not a
machine-wide trust installation or production certificate. Reset is a separate operator command.

The real React screens implement password/TOTP login, logout, session verification/expiry, input-only
idle activity, and the administrator directory with server search/sort/paging, whole-workspace
statistics and confirmed ordinary-grant revocation. Protected recovery is operator-managed. Add is
disabled without corporate identity enrollment; ordinary add/regrant, SSO and tenancy workflows are
not implemented. The same backend authorization, revision and immutable audit boundaries apply.

The actual subset remains six application tables and six frozen migrations/17 migration assets;
there are now 15 generated schemas and 14 scalar application settings. Backend/frontend unit gates,
disposable PostgreSQL and Playwright gates pass locally: **440 backend unit tests**, **1730/1740
lines (99.4253%) across all 37 source files**; **29 frontend unit tests**, **150/150 lines (100%)
across all seven source files**; **542 combined backend/database tests**, including actual
HTTPS/Chromium sign-in, grant revocation, logout and 1280/390/320px geometry, with zero failures,
errors or skips. The browser suite uses only synthetic factors in a disposable database. The
separate frontend gate verifies complete file inventory and raw counts; database/browser execution
never contributes to either unit percentage. Independent documentation, UI and security reviews
pass. All 77 exact locked Python packages and all 182 frontend lock entries have zero known
advisories; Bandit and source-only Gitleaks report zero findings. Narrow subprocess suppressions
were independently reviewed at their exact operator-only call sites. These are dated local results,
not hosted merge controls. No Git/publication, production Vault/ingress/role/OKE or hosted
pipeline qualification is claimed. Persistent human local state must remain outside test fixtures.

## Operations read visibility

**30 October 2026: read visibility implemented and final local unit/database/browser gates passed.**

[The Operations guide](../reference/operations.md) maps every displayed DTO/UI field to existing
operation/step/audit columns, exact current-intent JSON or snapshot derivation. Two guarded GET routes
and real React pages provide state/search/sort/pagination, detail/back navigation, current-intent
steps, recorded UTC dates and newest-50 event history with an explicit limit notice. Older immutable
history remains stored. An empty database produces an honest empty view; no example activity is seeded.

Current session/workspace checks and closed query/response models protect the reads. Each response
uses one PostgreSQL read-only repeatable snapshot; exact intent/hash/actor binding is checked before
summary projection. The simulated-mode label describes only the current supported inspection kind/
worker, not a real OCI read or verified adoption. This adds no table/migration, operation-admission
HTTP, configured worker process, provider write or retry/start/resume/cancel action. Full P1 remains
incomplete. Cloud operator-pod qualification is separate and its accepted procedure is unchanged.

The actual subset remains six tables/six migrations and now has 18 exported schemas across 39 backend
runtime modules. Final local results:

- **449 backend unit tests pass**, with **1868/1878 executable lines (99.4675%) across all 39 runtime
  files** and no exclusions.
- **45 frontend unit tests pass**, with **240/240 lines (100%) across all nine source files** after
  formatting. Database/browser execution does not contribute to either unit percentage.
- **555 combined backend/PostgreSQL/browser tests pass**, with zero failures, errors or skips. Actual
  restricted-role API/HTTPS/Chromium scenarios read real queued and simulated-verified operations,
  exercise keyboard detail/back/filter/deep-link reload, and check 320/390/1280px geometry.
- Independent UI and security reviews pass. All 77 exact locked Python packages and 182 frontend
  lock entries have zero known advisories; Bandit reports zero findings. Exact reviewed scope,
  source secret-scan results and evidence hashes belong in the validation receipt (private historical evidence; not distributed).

Unit fixtures check malformed hashes and the bounded history/public projections; real PostgreSQL
checks transaction read-only/repeatable behavior and worker publication across snapshots. These
claims do not turn mocked rows into database-lock proof. All unit, database and browser tests use
synthetic/disposable fixtures separate from the human's persistent local administrator/database and
the preserved organization prototype. No Git/publication, live cloud deployment or production
qualification is implied. The local app can be restarted against its retained state without seeding
fake Operations activity.

## Durable simulated inspection submission

**30 October 2026: local UI/API admission and a separate native worker are implemented; final unit/database/browser gates pass.**

[The simulation guide](../reference/simulation.md) maps all new public/configuration/private-state
fields and gives setup/start/worker instructions. Explicit setup preserves legacy installation,
owner/API credentials, account/MFA and all user data, adds private worker custody/role and creates
`simulation.json` only if missing. Virtual targets are configuration; no operation/job/activity is
seeded. API and worker run separately against the same owned loopback state, with native scoped
`otm.sim.<32 workspace-hash characters>` queue names sized for PostgreSQL's NOTIFY limit.

The authenticated form selects healthy, denied, timeout, unsupported or unobservable virtual reads.
A 202 receipt follows atomic operation/intent/native-job commit; the foreground worker rechecks
current grant/policy/pause/target and publishes a real step/outcome/audit transaction. Compatible
known-key replay remains durable and precedes policy reload, while the UI's uncertain key memory
lasts only for the mounted list form. It instructs users to check Operations after a reload before
new work. There are no OCI calls/credentials/adoption/writes, fake success or generic retry actions.

Current shape is 21 exported schemas/41 backend modules, six tables, six migrations/17 assets and
14 unchanged application TOML keys. Final confirmed local results: **484 backend unit tests**, with
**2092/2107 lines (99.2881%) across41 runtime files**; **62 frontend unit tests**, with **301/301 lines
(100%) across ten source files**; and **593 combined backend/PostgreSQL/browser tests**, zero failures
or skips. Two real Playwright scenarios use separate restricted API/worker roles and synthetic
isolated test fixtures; unit percentages exclude DB/browser execution. Human persistent app state
and the organization prototype remain separate. Independent reviews and exact source-scan/evidence
hashes are recorded in the validation receipt (private historical evidence; not distributed).
These local results do not establish full tenancy lifecycle/MVP, live OCI/SSO/OKE or cloud operator
qualification, hosted CI or Git/publication approval.

## Activity & history navigation and Audit History

**30 October 2026: accepted navigation/visibility decision, implemented Audit History and passing final local unit/database/browser gates.**

Daily Tenancies, Organization/Organization drift and Configuration/Baselines/Configuration drift
remain separate from Activity & history (Operations/Audit History) and Application settings
(Administrators). Operations supplies visibility/troubleshooting, not an inbox or generic Retry.
Current simulated issue detail says “Simulation ended with an issue. No action is required.” The
stored `needs_attention` value is unchanged; real future remediation belongs to its higher-level
resource/org/config/access context. Static shared menus and the selected style dashboard reflect
the groups, without an invented audit destination or Operations task-count badge. Historical images
and prototype behavior remain untouched.

[Audit History's source matrix](../reference/audit-history.md) now covers six bounded query, nine
safe entry and five directory fields over existing immutable events. Current session/workspace,
payload hash/actor validation and read-only repeatable snapshots govern the route. Worker events
show Inspection worker; protected operator events use a generic label; failed sign-ins are unverified
attempts, not authenticated humans. There is no raw JSON/edit/export or new history store. Planned
MVP export remains future work. Totals are 23 schemas/45 backend modules, six tables/six migrations/
17 assets and 14 unchanged TOML keys. Final local results:

- **501 backend unit tests pass**, covering **2188/2203 executable lines (99.3191%) across all 45
  runtime files** without exclusions.
- **74 frontend unit tests pass**, covering **357/357 lines (100%) across all 11 source files**.
- **612 combined backend/PostgreSQL/browser tests pass**, with zero failures, errors or skips.
  Synthetic isolated fixtures exercise actual history/API/worker attribution, scoped reads and
  browser navigation; backend/frontend unit percentages exclude database/browser execution.
- Current shared static menus/style pages retain visible history/settings groups on desktop and
  narrow layouts; Audit History has no invented static link, and Operations has no task-count badge.

Exact test/scope hashes, static/actual UI captures, source secret-scan results and independent review
dispositions are recorded in the validation receipt (private historical evidence; not distributed).
Human persistent app data and the organization prototype remain separate from test fixtures. These
local results do not complete planned audit export/full MVP or production OCI/SSO/Vault/OKE/operator
qualification, hosted CI or Git/publication approval.

## What this does not complete

P0 overall is **in progress**. The runnable local React/backend application does not establish
production SSO/deployed tenancy workflows, hosted CI/master protection, whole-repository publication clearance or
managed OCI qualification. Bounded local security checks are recorded above. One existing framework deprecation warning remains; no new failure or
private workbook style warning is hidden by the replacement.

The whole project is **not cleared for GitHub publication**. Other design/screens/history and
local demo configuration still need synthetic replacements or private exclusion. Even the test-only
export retains legacy workspace identifiers in CLI compatibility code; it is evidence of private-file
independence, not an approved repository publish set. Do not unignore real inputs to fix test/doc links.

## Next local work

1. Finish the publish-set inventory and replace remaining real identities in publishable source,
   examples and generated artifacts; preserve originals privately. Validate the approved publish
   set in a fresh checkout/export, including docs and browser artifacts.
2. Port reusable behavior/tests into production modules incrementally, retaining the complete-source
   95% production gate and independent PostgreSQL regressions; keep prototype coverage diagnostic.
3. Extend the backend foundation and configure the remaining CI gates from chapter18, with the selected original-A
   component styling. Repository creation/check-ins remain gated on final user design approval
   and a passing publication review; no such approval is inferred from visual selection alone.
4. Build on internal simulated reads and request verification: qualify the maintained SSO/session
   library and real current-policy provider before enabling production business routes. Port the
   preserved organization behavior/read models without local bypasses; qualify OCI credentials separately.
   Keep native worker/process regressions and immutable intent/state semantics as shared contracts.


## Audit administrator target names

Audit History now shows the current target administrator display name above the recorded UUID.
Target names participate in the existing literal search. This is directory context, not a mutation
of historical actor snapshots. The workspace-and-ID-scoped left join includes revoked grants and
retains audit rows without matching names, showing **Name unavailable** and the original UUID.
No administrator-detail route, schema migration, permission expansion or new table was added.
The API contract/source matrix now contains nine entry fields.

Unit gates pass: 501 backend tests with 2190/2205 lines (99.3197%); 75 frontend tests with
357/357 lines (100%). Independent security/UI/documentation review found no material issues.
Database/browser validation includes a renamed target, name search, workspace isolation, and
visible target names/UUIDs in the real browser.

Final combined backend/disposable-PostgreSQL/Playwright result: **613 passed**, no failures,
errors or skipped tests (`.local-dev/quality/backend-postgres-5hgr08ph/summary.json`).
Local app restarted with existing administrator data preserved.


## Instance branding — Atlas

30 October 2026. Public display identity is now configured by the optional `[branding]` block:
`display_name`, `logo_url`, `icon_url`. This installation selects **Atlas** while code, commands,
headers, database identifiers and technical documentation remain OCI Tenancy Manager / OTM.
Sign-in, navigation, document title and favicon use the same runtime identity. Generic text
branding remains the default, with accessible image names and browser-load fallback.

A three-field public view is the only configuration exposed before authentication. Asset paths
are restricted same-origin raster filenames; traversal, external/executable URLs and configured
symlinks/missing assets fail validation. Existing protected API/session checks are unchanged.
No tables, migrations, role grants or dependencies were added. Current inventory:24schemas,
45backendmodules,12frontendsourcefiles,17applicationTOMLscalarsettings.

[Settings and deployment](../reference/application-settings.md#instance-branding) and
[artwork provenance](../branding-assets.md) document operation without an image rebuild for supported
name/path changes, along with asset provisioning and process restart. The preserved prototype and
historical walkthroughs remain reference artifacts. Local settings were updated without changing
administrator identity, credentials or stored data.

Validation:522backendunit tests,2217/2232lines(99.328%);82frontendunit tests,382/382lines(100%).
634combinedbackend/disposable-PostgreSQL/Playwright tests pass with no failures/errors/skips;
artifact `.local-dev/quality/backend-postgres-xfcifoy7/summary.json`. Real browser checks exercise
the public view, loaded logo/favicon, browser title and sign-in/sidebar at1280/390/320pixels.
Independent security/documentation and UI/UX reviewers found no material issues. Dependency
manifests/locks are unchanged. This does not qualify production OKE/SSO/Vault or authorize Git
publication.


## Review-ready development slices — audit export and organization core

**30 October2026: three bounded slices complete, final local gates and independent reviews pass.**

1. **Audit date filtering.** UTC-aware inclusive **From** and exclusive **Before** predicates are
   shared between directory reads and downloads. Invalid dates/ranges retain the last valid result,
   show guidance and disable export. Responsive toolbar sizing preserves readable search and44px
   action controls at1280/390/320pixels.
2. **Audited CSV export.** Authenticated same-origin POST exports every matching row across pages
   up to an explicit10,000-event cap. CSV cells neutralize spreadsheet formulas/control characters;
   only the nine-field safe projection is included. Oversized/invalid/uncommitted requests disclose
   no partial file. Current session/grant checks run after lock acquisition, and immutable
   **Audit export prepared** evidence commits before bytes are released. The record does not prove
   browser receipt. Forward migration0007 extends the closed kind constraint and adds the scoped
   time/event index without a new table or grant.
3. **Production organization core.** Four-column CSV intake, canonical models, graph reconciliation
   and review rules are extracted into the production package, with84synthetic regression cases.
   Repeated uploads remain distinct observations; incomplete census evidence cannot invent absence.
   Review found and fixed an inherited excluded-reference resurrection bug, including retired-email
   aliases: an incompatible removed manager/designee/reference now rejects publication instead of
   silently recreating a managed person. Diagnostic placeholders remain only in rejected candidates.

The [organization guide](../reference/organization-domain.md) distinguishes pure domain
behavior from still-pending snapshot persistence, publication, durable review/history, tenancy
association coordination and guarded Organization UI routes. Organization remains disabled in the
production navigation; the existing prototype remains intact and usable.

Final validation: **629 backend unit tests**, **2845/2860 lines(99.4755%) across51runtime modules**;
**98 frontend unit tests**, **445/445 lines(100%) across12source files**; **744 combined backend,
disposable-PostgreSQL and Playwright tests**, zero failures/errors/skips. Unit-only coverage is
measured separately and excludes database/browser execution. The organization subset has
**84tests and506/506lines(100%)**. Exact evidence paths, hashes, captures, scan results and review
dispositions are in the validation receipt (private historical evidence; not distributed).

Current inventory:25generated structural schemas, six application tables, seven frozen migrations/
19migration assets,17applicationTOMLscalar settings. The wheel matches all51runtime modules and
packaged frozen-artifact hashes. Ruff/format,162-file purpose-comment validation and cross-tier
design links pass. Independent security, documentation and UI reviews have no remaining material
findings. Exact locked dependency audits (77Python packages and182external frontend packages;183lock entries
including the project) report zero
known advisories; Bandit and final source-only secret scan report no findings.

The local app and simulation worker are restarted. A private80KB database backup preceded the
upgrade; administrator grant, credential, application settings and private-state fingerprints match
before/after setup. No live OCI actions, notification delivery, seeded organization/operation
activity, Git commit or publication occurred. One existing framework deprecation warning remains.

### Suggested return review

Open **Audit history**, try UTC date/category/search filters, then **Export CSV** and compare its
rows against the complete filtered result rather than just the visible page. Clear the filters to
see **Audit export prepared** in Administration. Existing authentication/branding remain unchanged.
The next substantial vertical slice is production organization persistence and authorized feed
publication, followed by wiring the approved Organization/Organization drift screens.


## Production organization persistence checkpoint

**30 October2026: five-table authorized snapshot storage is implemented and qualified locally.**

[The field dictionary and embedded ER](../reference/organization-storage.md) map all49stored
columns in `org_workspace`, `org_person`, `org_feed`, `org_version` and `org_member`, plus the
nine private organization-audit evidence fields and six processing-outcome fields. The two
readable views, `current_organization` and `proposed_organization`, show only selected sealed
versions and derive names/LOB labels from the same frozen version/configuration. Authentication
workspace is independent of the source population. The retained prototype is not imported or migrated.

Writes require fresh session/grant authority, the shared post-lock authorization helper and an
active READCOMMITTED psycopg transaction. Feeds retain immutable canonical/raw-digest evidence
and separate receive/capture clocks. Delivery replay, changed-key conflicts, newest-source ordering,
raw/effective validation and exact head/configuration checks preserve staged/applied semantics.
Stable person IDs survive reorgs and reviewed email remaps. Atomic source/member/version/head/audit
publication rolls back together on failure. Original identity anchors and sealed snapshots cannot
be rewritten through ordinary DML; presealed insertion, append-after-seal and table truncation fail.
Accepted nonfatal diagnostics remain available on the persisted feed and replay receipt.

Shared Audit History/CSV now accepts the closed **Organization** family. Administrator configuration/
receipt and service computation have distinct verified actor representations. Public history shows
**Workspace organization** without an invented detail link, raw configuration or employee payload.
The Organization menu itself remains disabled: source-profile/intake HTTP, recommendation/history
coordination and approved page wiring are the next slice. No fake create/delete/import success,
notification delivery or OCI action is introduced.

The user approved a required **Organization data as of** confirmation, defaulted from current
server UTC, for the future manual upload screen. It maps to the existing capture-time fields,
not receive time; all source/census/freshness guards remain. The four-column CSV is unchanged.

Final gates: **673 backend unit tests**, **3088/3105lines(99.4525%) across54runtime modules**;
**99 frontend unit tests**, **445/445lines(100%) across12source files**; **810 combined backend/
disposable-PostgreSQL/Playwright tests**, no failures/errors/skips. These include44new repository
unit cases and22actual organization-storage PostgreSQL cases. The latter exercise both heads,
views, source replay/order, warnings, raw/override rejection, concurrent delivery, atomic rollback,
immutability/scoped constraints, stable email-merge survivors and an actual foreign-workspace
merge rejection. A temporary restricted SQL role publishes successfully with column-scoped grants
and cannot rewrite historical data; these fixture grants are not installed on the running API.

Current inventory is11actual application tables,8frozen migrations/21migration assets,27generated
schemas,54runtime Python modules and17application TOML scalar keys. The wheel matches all54
modules and frozen SQL/artifact hashes; ER source matches all49new columns. Ruff/format,
168-file purpose-comment validation and cross-tier links pass. Independent security, documentation
and UI reviews have no remaining material findings; accepted-warning persistence and presealed
insert findings were fixed and re-reviewed. Exact-lock dependency audits cover77Python packages
and182external frontend packages(183lock entries including the project), with no known advisories.
Static/secret scan and source hashes are in the
validation receipt (private historical evidence; not distributed).

A private local database backup preceded migration0008. Existing administrator grants, credentials,
operational/audit rows, settings and private state match before/after fingerprints; the five new
organization tables are empty. The app and simulation worker are running. This does not qualify
OCI/SSO/OKE, managed-service roles/backups or hosted CI/protected master, and authorizes no Git
commit, push or publication. The existing framework deprecation warning remains visible.

### Next reviewable slice

Persist recommendation/metadata-history projections and wire the approved Organization directory,
manual CSV/as-of upload and Organization drift screens through current administrator authority.
Workflow resolution must close on accepted real operations; source graphs and tenancy associations
remain separate authorities. The new SQL views/field dictionary can be inspected now in pgAdmin;
there is no seeded production organization to demonstrate until intake setup is wired.


## Production Organization screens checkpoint — 30 October 2026

**Organization → Organization drift** is now enabled in the actual Atlas application. The
[screen/API guide](../reference/organization-screens.md) maps all33 public contract fields,
input limits, capture-time trust, source-profile setup and current scope. The directory uses live
production snapshots with sortable columns, literal search, server paging/page numbers and counts.
The guarded CSV dialog accepts the four-column format, refreshes the server UTC default and requires
an explicit source-time/complete-census attestation. Rejected uploads preserve the applied head.
Every new upload has a new delivery identity; unchanged same-dialog retries reuse it. No production
code connects to the prototype database.

Current actionable and informational drift comes from the domain rules against the same immutable
applied snapshot/frozen configuration. Missing-manager/designee/reference cases remain visible,
qualified suppression targets remain intact, and stable-ID metadata comparisons preserve remaps.
Changes show the latest applied feed; this slice does not claim the full dated-history interface,
a durable recommendation inbox, tenancy association counts or accepted onboarding/offboarding/
merge/ignore/resolve commands. There are no simulated-success lifecycle buttons. These remain next
production integrations using the preserved prototype as interaction authority. No additional table
or migration was introduced; the actual inventory stays11application tables/eight migrations.

Validation: **690 backend unit tests**, **3277/3295lines (99.4537%) across56runtime modules**;
**108 frontend unit tests**, **563/566lines (99.46%) across13source files**. The complete disposable
PostgreSQL/real-HTTPS/Playwright run passed **828 tests**, zero failures/errors/skips. It exercises
malformed uploads, source ordering, literal SQL/script-looking values, valid leader-boundary handling,
absence display, actual installed-role write denials, real audit events and responsive320/390/1280
screens. Browser/database tests do not inflate unit coverage. The wheel matches all56current runtime
modules.29generated contracts, Ruff/format,171-file purpose comments and documentation links pass.

Independent security, inline-documentation and visual UI reviews passed after correcting domain
issue projection, qualified suppression targets, stable-ID deltas, frozen configuration and narrowing
runtime UPDATE grants. Current exact-lock audits cover77Python external packages and the locked
frontend dependency graph with no known advisories. Bandit and Gitleaks report no findings; the
existing narrowly scoped frozen-SQL-checksum exception remains unchanged. No new dependency was
introduced. The framework TestClient deprecation warning remains visible.

Private initial policy/LOB configuration was prepared locally from the previously approved mapping,
without employee rows or prototype decisions. The restricted runtime grants are installed; all11table
row/count fingerprints and private settings/state hashes matched before/after. The production
organization remains empty for the user's first upload. Atlas was restarted at
[https://localhost:8443/organization](https://localhost:8443/organization). Tests used synthetic data
and disposable databases; no human data was ingested by test automation. This does not qualify real
OCI/SSO/OKE, managed-service backups or hosted CI/protected master, and authorizes no Git publication.

Validation and source hashes: private checkpoint receipt (private historical evidence; not distributed).
Next: integrate association-aware onboarding/review decisions and their real durable operations,
without reintroducing the prototype's fake-success shortcuts.


## Local test organization reset — 30 October 2026

The approved local-only reset is available as
`uv run --project backend otm-local reset-organization --confirm-reset-organization`.
[The reset guide](../reference/organization-screens.md#local-test-reset) maps scope, safeguards,
configuration and UI behavior. The **Reset test organization** control opens command instructions;
**Refresh organization** is read-only, closes natively, restores focus, clears stale upload notices
and reloads the directory. It never dispatches an owner command through HTTP. The shipped
`[local_server].organization_reset_enabled` defaults false; it is explicitly enabled in this laptop's
private settings and the application has been restarted. The user's organization was not reset.

The operator command verifies the owned Docker label/exact loopback port, database owner/name,
local recovery issuer/scope and fixed five-table schema. It refuses future tenancy/unknown
organization tables. An enforced READ COMMITTED transaction takes exclusive locks and temporarily
disables only five truncate guards; the fixed five tables are cleared without CASCADE and guards
are restored before commit. Any error rolls back data and trigger state together. Source/LOB profile
custody survives if present, ready for the next upload. Administrators, credentials, sessions,
operations and immutable audit remain; old audit correlation IDs intentionally outlive removed test
snapshots. No runtime-role privilege, table or migration was added.

Validation: **710 backend unit tests**, **3330/3348lines(99.4624%) across57runtime modules**;
**109 frontend unit tests**, **576/579lines(99.48%) across13source files**. The full disposable
PostgreSQL/HTTPS/Playwright run passed **849tests**, zero failures/errors/skips, in two clean
qualification runs. New coverage includes19local reset unit cases, a no-reset-HTTP negative case,
actual owned-installation CLI reset/reload, six preserved auth/audit/operation fingerprints,
AUTOCOMMIT refusal, rollback after truncation, restored guard denial and responsive instruction
screens/focus restoration at1280/390/320px. Independent security, documentation and UI review passed.
Ruff/format,173-file purpose comments,29generated schemas and documentation links pass; the wheel
matches57current runtime modules. Static and secret scans are clear. Dependency locks are unchanged
from the prior exact-lock advisory audit; no package was added.

An existing simulator/browser test intermittently timed out with a queued second job during two
qualification attempts. Its fixture now retains private redacted worker diagnostics and launches
the same underlying worker function in a separate process so exceptions are visible. No production
worker behavior, test assertion, timeout or retry policy was weakened. Two subsequent full clean
runs passed; the earlier timeout's root cause is unproven and retained in the validation receipt.
The existing framework deprecation warning also remains visible.

Private validation receipt (private historical evidence; not distributed)
records exact artifacts/source hashes. No Git check-in, publication, real OCI action or human-data
reset was performed. The next product slice remains association-aware tenancy/review workflows.

## Organization workflow parity — validated local review checkpoint

The [organization parity milestone](organization-parity-checkpoint.md) is ready for local review.
[Current fields/ER and boundaries](../reference/organization-workflows.md) cover the three new
review/registry tables, managed-person controls, durable simulation handoffs, local cancellation,
safe audit targets and ten-column CSV, and eight-table local reset.

Required gates passed:902combined backend/database/real-HTTPS-browser tests;752backend units at
96.01% complete-source line coverage;131frontend units at98.51%. Independent security/documentation/
desktop-mobile UI review passed. Ruff/format,186-file purpose checks,37generated contracts, design
links,67-module wheel/source equality and all frozen SQL asset checks pass. Bandit/Gitleaks found
zero findings; exact Python and full frontend lock advisory checks found no known vulnerabilities.

The local installation was backed up, migrated0008→0009 and restarted with API/worker. Existing
employee/feed/version/audit and authentication evidence was preserved; no human data reset or real
OCI mutation was performed. Private CSV exercises matching the configured organization are available
under `.local-dev/application/scenarios`. The checkpoint links the receipt and exact local artifacts.
No Git check-in/publication or hosted/real-OCI qualification is implied.


## Excluded-profile visibility fix — 30 October2026

The Organization HTTP route accepted `include_removed` but failed to pass it into the existing
scoped directory query. It now forwards the checkbox value; managed status and authentication/
authorization are unchanged. The checked-flag regression failed before the fix and passes afterward.
The real HTTPS browser flow records No tenancy required, verifies default exclusion, checks the
control to reveal the employee with its status, then unchecks to hide it again.

All904combined backend/database/browser tests pass. The separate unit gates pass with754backend
tests at96.01% line coverage and131frontend tests at98.51%. Independent security/documentation/UI
review, Ruff/format, purpose comments, static/secret checks and unchanged-dependency-lock comparison
pass. The local API was restarted without database changes.
Validation receipt (private historical evidence; not distributed).


## Shared control consistency — 30 October2026

Shared checkbox styling now prevents inherited text-input padding and aligns the control to its
label/first wrapped line. Native selects use a small reusable render wrapper for bounded selected
text, a clear inset chevron and a progressively styled anchored native picker. The browser retains
keyboard/form behavior. Existing Field Console colors/corners and all application workflows remain.
The UI-review policy now explicitly requires open menus, single/wrapped checkbox alignment,
keyboard, touch/zoom checks and accurate unsupported-browser qualifications.

All904backend/database/real-browser tests pass.131frontend units pass at98.51% complete-source line
coverage across17source modules; the unchanged backend retains its754-unit96.01% coverage gate.
Independent security/documentation/UI review passed, including final actual desktop/mobile captures.
No dependency/CSP/data/schema changes were made. The local API serves the current built UI; existing
tabs need a refresh. Validation receipt (private historical evidence; not distributed)
distinguishes actual browser evidence from isolated DOM/touch-emulation/CSS-zoom stress checks.


## Shared-tenancy inventory shortcut — 30 October2026

Tenancies now has a Shared tenancies only checkbox alongside search. It defaults off; toggling
returns to page one while preserving search/sort. The server applies `shared_only` before paging
and combines it with search. Whole-inventory cards retain their scope; filtered rows/footer have
the matching count. Switching modes cannot display stale individual rows. A scoped wrapping toolbar
keeps the checkbox and search usable at tablet widths; no schema or role changes are required.
The generated query contract and workflow field dictionary include the new boolean.

All905combined backend/database/browser tests pass. Separate755backend units pass at96.03% line
coverage;132frontend units pass above98.5%. Independent security/documentation/UI reviews passed.
Actual captures and geometry checks cover1280/900/768/390/320px. Static/secret scans, documentation,
contracts and code checks pass. The local API was restarted and serves the current built UI; refresh
existing tabs to load the checkbox. Validation receipt (private historical evidence; not distributed).


## Explicit employee action choice — 31 October2026

General employee/review dialogs now start at Choose an action. They show no action-specific fields
and disable Continue until a selection is made, even if only one action is available. Valid explicit
task buttons may still preselect their named action; unavailable tasks never fall back to creation.
An unchanged retry preview may retain a choice the administrator already made.

The new default-choice regression failed against the previous implementation and passes after the
change. All905backend/database/real-browser tests and134frontend unit tests pass; frontend coverage
remains above98.5%. The unchanged backend retains its755-unit96.03% gate. Independent reviews,
source documentation/code checks and secret scanning passed. The local app serves the current
built UI; no backend/schema/data/dependency changes were needed.
Validation receipt (private historical evidence; not distributed).

## Guided create/import onboarding — 31 October 2026

New create/import operations now persist a manual activation/bootstrap handoff, exact target/account
inspection, explicit cleanup review and dependency-ordered simulated access setup. Actual name/home
region are discovered at handoff; initial forms select owner/type and, for import, the synthetic OCID.
Pending tenancy detail and guided operation detail share one current-action panel. Technical history
is collapsed by default; input, checks and consent survive reload appropriately, and switching to
another operation clears consent. Import preserves unrelated administrators.

This reuses operation, step and immutable audit authorities: migration0010 extends allowed values
only, retaining14application tables. Historical accepted intents remain compatible. The simulator
issues no usable keys, sends no email and contacts no OCI service; baseline/Vault/MFA/provider
qualification remains future work. [The implementation guide](../reference/tenancy-onboarding.md)
names all49contract fields and maps screens/evidence to storage; product/design/ER references agree.

All938backend/database/real-browser tests pass, including incorrect-bootstrap correction/reload,
actual restricted API/worker roles and known-effect cancellation guards. Separate786backend units
pass at96.0731% line coverage across69modules;147frontend units pass at97.6471% across18modules.
Independent security, inline-documentation and UI reviews are clear. Ruff,190-file purpose check,
39generated schemas, design links, package byte/migration checks, Bandit and source secret scans pass.
The local database was backed up, migrated0009→0010 and all14application-table row fingerprints
preserved; the current API/worker were restarted and HTTPS verified. No Git publication occurred.
Validation receipt (private historical evidence; not distributed).

## Whole-tenancy deletion — 31 October 2026

Tenancy detail now exposes Delete tenancy for registered individual and shared children. The
complete tracked owner/member preview includes exact child/parent IDs, last-known manager/shared
warnings, other associations and each person's managed-directory outcome. One explicit consent
initiates an existing durable operation: tenancy/link states become terminating/removing. Only
verified simulated initiation retires every target link; other tenancy associations and unresolved
absence work survive. Last-link people leave the managed directory, while the configured root and
immutable source/audit history remain. No-effect cancellation restores all participants.

[The field guide](../reference/tenancy-deletion.md) maps all19public fields and the server-only
frozen JSON additions. No tables/columns/migration are added; the restricted worker receives only
four review-update columns for last-link case closure. Consent resets on changed previews/routes;
private workflow caches clear on logout/expiry. Mobile confirmation/action controls remain in the
normal scroll flow, and untracked owner-created OCI users are explicitly outside the tracked list.

All945backend/database/real-browser tests and154frontend units pass. Separate791backend units
achieve96.06% line coverage across70modules; frontend achieves97.27% across19modules. The actual
installed API/worker browser journey exercises both shared and imported-individual termination,
retained other associations, mobile checkbox clicks and long-title controls. Independent security,
UI and purpose/field-documentation reviews are clear; static/secret/contracts/package checks pass.
The owned laptop database was backed up and all14application-table fingerprints preserved while
runtime grants/API/worker were refreshed. No real OCI effects or Git publication occurred.
Validation receipt (private historical evidence; not distributed).

## Create request metadata and completion navigation — 31 October 2026

Create now requires a valid requested tenancy name and a home region from the provider's parent
subscription list before accepting an operation. The activation handoff repeats those frozen values;
observed metadata is still verified afterward. This corrects the earlier guided-onboarding omission.
Import continues to discover metadata independently. Local region choices are explicit simulator
fixtures, pending qualification against OCI.

Successful organization operations expose Open tenancy using an exact workspace-scoped registered
OCID match, including historical operations. Embedded onboarding avoids duplicate completion links.
Current contract field maps and design/ER references capture the requested and observed values.

All952backend/database/real-browser tests and156frontend units pass. Separate797backend units
achieve96.05% line coverage across70modules; frontend achieves97.21% across19source files.
Independent security and UI reviews pass; documentation field-map corrections, static checks,
41schemas and installed-wheel source checks pass. Atlas was restarted after a private backup;
all14application-table fingerprints and schema0010 were preserved. OCI remains simulated.
Validation receipt (private historical evidence; not distributed).

## Documented OCI handoff checklist — 31 October 2026

The setup screen now explains the actual OCI manual steps with official Oracle documentation links:
activation/password/MFA for create, copying distinct child/activation/bootstrap OCIDs, Default-domain
bootstrap creation, separate OCI Administrators membership and domain-administrator grant, and
uploading only the app-provided public PEM. Imports link created-child transfer approval separately
from invited-child removal and invitation acceptance. Temporary access remains until verified setup
and cleanup review. The simulator explicitly directs local testers to skip real OCI actions.

The operator guide, engineering journey, static activation sample and screen authority agree.
No contract/schema/backend/dependency changes were required. All952backend/database/real-browser
tests and157frontend units pass; separate797backend units retain96.05% coverage, and frontend
retains97.21%. Fresh create/import captures cover1280/390/320px with the transfer disclosure open.
The local app serves the rebuilt checklist; no human database records were changed.
Validation receipt (private historical evidence; not distributed).

## Import target continuity and local name-conflict feedback — 2 November 2026

Import setup carries the original selected tenancy OCID read-only and requests only bootstrap user
OCID. The browser constructs the exact bound target from the server projection; the server independently
rejects forged retargeting. Create handoff remains editable. Local duplicate-name admission keeps the
form/type/region choices and returns focus to the rejected name; editing permits corrected submission.

Regression tests cover active/pending/terminating registry collisions with no writes, actual database
rollback/corrected retry, import tampering followed by successful verification, and browser read-only
controls. All959backend/database/real-browser tests pass. Separate801backend units achieve96.07%
line coverage across70modules;159frontend units achieve97.42% across19modules. Security, UI and
documentation reviews pass. Atlas serves the rebuilt UI without changing human data/schema.

The simulator still makes no real OCI create call. OCI-wide name rejection and same-operation name
amendment remain explicitly required future adapter work, with definitive no-effect versus uncertain
outcomes separated in the operator guide, engineering journey/call map and test plan. Registry tests
do not claim global availability or live provider qualification.
Validation receipt (private historical evidence; not distributed).

## Organization Mapping and independent role repair — 2 November 2026

Application Settings now supports explicit root/industry-segment setup, typed emails and employee
suggestions, mapping CRUD, read-only server preview, paginated impact, and immediate guarded Apply.
Every edit invalidates its preview. Apply binds exact candidate/configuration/applied/proposed/registry
revisions, recomputes under lock and rejects pending work or ineligible replacements. Initial CSV
imports require saved mappings; the legacy file cannot silently initialize or overwrite settings.

Leaders/designees are checked per segment regardless of tenancy ownership, hidden profiles, invalid
leadership or old acknowledgments. Role repairs stay separate from tenancy cleanup. Mapping-only
recalculation preserves observation/absence/lifecycle evidence; only newly recorded administrative
decisions can settle their own absence. Qualified returns after completed offboarding still renew
onboarding and reevaluate roles. Segment IDs/history and frozen accepted targets are preserved.

The [runtime guide](../reference/organization-mapping.md) maps all52newDTO fields and3audit fields
to existing authorities and traces every required matrix scenario. Spec, design20, model/ER, source
guides, screen authority and test plan agree. No table/column/migration or production grant added.
An installed-role regression prevented a descriptive-data rewrite; current labels are projected
without changing historical payloads. The browser fixture now mirrors existing installer grants.

All1,006backend/database/real-browser tests pass with zero skips. Separate833backend units achieve
96.13% line coverage across74modules;172frontend units achieve97.46% across20modules. Documentation,
security and UI/UX reviews are clear. Actual keyboard, lookup/Add alignment and1280/390/320px flows
pass. The app was backed up/refreshed and all14application-table fingerprints preserved, without
seeding/changing saved mappings. OCI remains simulated; no Git publication occurred.
Validation receipt (private historical evidence; not distributed).


## Organization Mapping UI refinement — 2 November 2026

Moved saved organization role health above the editor, gave segment/designee fields shared form
typography and breathing room, and removed the misleading native suggestion indicator from Leader
email. Designee lookup/add remains available after a feed. Preview is now a native modal with impact
counts, separate segment/employee sections and bounded scrolling. Back to editing/Escape retains the
draft and restores launcher focus; Cancel edits separately restores saved mappings. Closing during
requests is disabled. Heading focus, keyboard dismissal, exact Apply, failed writes and retained drafts
are covered. No backend, contract, database, dependency or live-data change.

Independent documentation, security and UI/UX reviews passed. Synthetic desktop/390px/320px captures
and the complete final test results are recorded in the
validation receipt (private historical evidence; not distributed).

Final validation: all1,006backend/database/HTTPS-browser tests and174frontend units pass with zero
failures or skips. Separate unit-only coverage is96.13% backend and97.48% frontend. Source-purpose,
Ruff, formatting, contracts and design-link checks pass; scoped secret scanning found no leaks.


## Explicit organization leader replacement — 2 November 2026

The root remains read-only in ordinary editing. Change organization leader explicitly unlocks it;
preview shows the saved/proposed roots, whether the successor appears in accepted source evidence,
unresolved-path count and per-person ancestry deltas. Browser confirmation is required before Apply.
The exact server binding includes change_root; ordinary calls cannot bypass the root lock. The
existing reapply guard permits only this root field to differ, retaining all other source policy.
No new table/migration/privilege/dependency; existing configuration/version/audit JSON remains authority.

A successor may not yet be in the feed. Mapping-only recomputation preserves clocks, absence and
associations, leaving real reporting gaps visible until the next corrected feed. A manager-less
former-root row in already accepted evidence is nonfatal only in configuration-only work. Fresh CSV
validation stays strict. Former-root cleanup remains independent, as do leader/designee reviews.

All1,014backend/database/real-browser tests and175frontend units pass, zero failures/skips. Separate
unit-only coverage96.14% backend/97.51% frontend. Documentation, security and desktop/mobile UI reviews
passed; Bandit and scoped secret scans are clear. The
[manual test runbook](../how-to/organization-mapping-runbook.md) links six synthetic CSVs validated by
unit tests. Validation receipt (private historical evidence; not distributed).


## Compact designee controls — 2 November 2026

The mapping editor now puts lookup/Add beside the two-row email list on wide screens, reducing
vertical space per segment. It stacks the fields at1100px and Add below search at480px to avoid tiny
inputs. No behavior, contract, data model or backend change. Existing frontend units and a real HTTPS
mapping/root-replacement browser flow validate the affected controls; responsive checks cover1280,
900,768,600,390and320px, including a minimum usable lookup width and keyboard Add. Final evidence is
recorded in the scoped receipt (private historical evidence; not distributed).


## Readable organization audit details — 2 November 2026

AuditHistory replaces the unhelpful empty outcome-code column with Details: readable action summary
and native View changes for selected recorded root, segment-name, leader and designee edits. Changes
come only from hash-validated immutable typed evidence, not today's mappings. Initial/no-op/legacy
records are distinguished; unrecorded details are not invented. Asynchronous offboarding says
Requested; only an immediate completed receipt says Offboarded. Feed receipt does not infer a zero
count. CSV carries the same12fields, including a JSON-array changes column, with existing protections.
No new table, permission, dependency or audit rewrite; filtering/search scope remains unchanged.

All1,025backend/database/real-browser tests and176frontend units pass with no failures/skips.
Separate unit-only coverage96.17% backend/97.51% frontend. A real PostgreSQL case changes mappings
twice and verifies original display/export values persist; UI tests open/collapse disclosure with
keyboard, verify escaped text,44px targets and visible old/new root in narrow table viewports.
Documentation, security and UI/UX reviews passed. Both security-review findings about misleading
queued offboarding and unrecorded feed counts were fixed and retested. The app was refreshed without
changing its14table rows. Validation receipt (private historical evidence; not distributed).


## Audit category filter width — 2 November 2026

Added a scoped13rem minimum width to the Audit history Category filter and native select, preventing
Administration/Authentication labels from wrapping midword. Existing toolbar wrapping and mobile
full-width behavior remain. Open-menu browser checks cover1280/900/390/320px, option row heights,
viewport fit and Escape focus; no application state, API, schema or dependency change.


## Parallel Atlas Test for manual organization testing — 2 November 2026

Prepared a separate laptop installation under `.local-dev/runbook`, workspace runbook-lab, with its
own owned PostgreSQL container, database credentials, issuer, TLS/MFA custody and simulated worker.
Atlas Test is served at127.0.0.1:8444; existing Atlas remains localhost:8443. Distinct hostnames isolate
host-only login cookies. The synthetic source policy supports the six runbook CSVs but initializes no
organization/admin. The user must privately enroll a separate recovery administrator and TOTP factor.
No employee data or credentials were copied; original settings hashes and existing org/admin presence
were verified. Both instances share application source/build, not data/settings.

The [parallel guide](../how-to/parallel-local-instance.md) and
[manual runbook](../how-to/organization-mapping-runbook.md) explicitly target the runbook directory for
bootstrap/setup/start/worker/reset. Organization's reset guidance now requires a non-runnable explicit
installation-path template; the CLI default is unchanged, and no reset endpoint was added. Initial
heading focus makes the warning visible on mobile. No reset was performed in either instance.
The previous private current-instance restart helper was narrowed to its TLS path/recorded worker
rather than killing all OTM processes. Runtime ownership is recorded separately for Atlas Test.

Validation:18local-launcher units,176frontend units at97.52% line coverage, and real HTTPS/PostgreSQL
browser flow pass. Both live public login/health/branding endpoints respond; the test worker is
registered and its admin/org tables remain empty. Documentation/security/UI reviews pass; desktop
and390px public login plus320px reset safety guidance were visually checked. Authenticated testing
in the new installation awaits the user's private enrollment. No production backend/schema/grant or
OCI changes. Scoped receipt (private historical evidence; not distributed).


## Corrected mapping review lifecycle and provisioning guard — 2 November 2026

Root cause: review reconciliation intentionally retained actionable lifecycle episodes but accidentally
retained LOB_MAPPING_REVIEW after the actual mapping condition had been corrected. Read-only inspection
of Atlas Test confirmed four open rows already had valid current mappings. Two deterministic disposable
PostgreSQL regressions failed before the fix (stale rows, advertised provisioning) and pass afterward.

A shared pure accountability predicate matches stable person/current root or resolved active segment
and its configured leader. No-longer-active mapping reviews auto-resolve as mapping_corrected; history,
permanent ignores, later recurrence and absence/setup decisions remain independent. PersonWorkflow adds
one derived mapping_required field (15total); the UI explains the repair and removes only create/import/
join, while server admission enforces the same rule. Cleanup and unaffected branches remain usable.
The user explicitly selected targeted provisioning blocking over global Organization blocking.

All1,041backend/database/native-worker/browser tests and177frontend units pass, with separate unit-only
coverage96.18%/97.52%. Documentation/security/UI reviews pass. An owned runbook-only operator transaction,
after backup and review, closed exactly four stale mapping reviews and appended an operator audit event.
It verified every other application table, every non-target review field and all prior audit events
unchanged. Atlas Test was restarted; its inbox now has only Acting Alpha's genuine tenancy-setup review.
Original Atlas remains running; no repair was made to its data. No reset, table, grant or source-clock
change. gstack was updated under the existing auto-upgrade preference. This investigation spans review
reconciliation and UI; scope was kept manually to those modules/tests/docs, without a freeze token.
Validation receipt (private historical evidence; not distributed).

## Latest-feed information and readable segment changes — 2 November 2026

Organization drift now shows Latest feed information, counting only open source warnings and change
records supported by the latest applied feed. Version-to-feed provenance includes mapping reapplies;
rejected uploads do not displace accepted information. Completed actionable decisions and resolved
warnings are excluded from this tab, while stored history and the history API remain unchanged.
Industry-segment change details display names pinned to the review's original before/after
configuration, retaining immutable lob_id evidence. Root-replacement helper copy is vertically centered
with its button and can wrap responsively. No schema migration or additional dependency is required.

Validation: 1,043 backend/database/browser tests; a final focused HTTPS browser run passes 2 tests;
865 backend units at96.186% and177 frontend units at97.53%. Independent documentation, security and
UI/UX reviews passed. Original Atlas and Atlas Test restarted with their existing data/configuration;
original-instance restart verified14application tables unchanged and retained its schema revision.
Real OCI qualification remains outside this local UI/read-model slice. No Git commit/publication.

Validation receipt (private historical evidence; not distributed).

## Root tenancy exemption versus offboarding — 2 November 2026

The reported successor-leader error was reproduced by a deterministic failing unit regression.
The directory advertised No tenancy required, but an overly broad application-decision guard treated
that onboarding exemption as root offboarding. The failed request raised before mutation.

The guard now prohibits actual root offboarding only. Zero-association exemption retains source
identity, root configuration, reporting paths and segment roles while hiding the ordinary managed
row until Include excluded profiles is selected. Explicit re-onboarding remains available. The
preview removes root offboard/merge choices and admission still enforces association/operation guards.
No schema, credential, tenancy-resource or dependency changes. Runbook step6 now exercises this case.

Validation qualified the full run’s 1,044 passing cases plus a passing affected HTTPS browser rerun (2 tests) after correcting test-only navigation/locator mistakes. Separate unit gates passed: 866 backend units at96.1874% and177 frontend units at97.53%. The initial browser failures are retained as investigation evidence, not reported as passing full-run receipts. Independent documentation/security/UI reviews pass. Both local instances restarted with existing data retained; original restart verified14tables unchanged. Validation receipt (private historical evidence; not distributed).

## Optional full organization history — 2 November 2026

Informational & history defaults to latest applied feed, with Show all history exposing the existing
retained history API. Badge, copy and empty state follow the selected scope. Toggling resets page1
and retains search/sort/page size; scope is remembered across tabs until the page unmounts.

The browser journey also exposed stale inactive mapping context after an organization decision.
The shared refresh now refetches existing inactive mapping queries; employee-action success appears
after refresh attempts settle. A real QueryClient test protects this case. Server context checks and
failed-read handling remain authoritative; no backend/schema/dependency or data migration is required.

Validation passed:178frontend units (97.54% complete-source line coverage) and2real HTTPS/browser
cases against disposable PostgreSQL, including history toggles, mapping repair and root exemption.
Independent documentation/security/UI reviews passed; both live local instances serve the updated
frontend without resetting their data. Validation receipt (private historical evidence; not distributed).

## Reloadable feature routes and Tenancies landing — 2 November 2026

The mapping screen was reachable through client navigation but absent from the backend's explicit
shell route list and public-shell allowlist. A failing unit HTTP reproduction confirmed the mismatch.
Both exact entries are now present; private APIs/near-prefix routes remain guarded. No catch-all,
new authorization, router dependency or database migration was introduced.

Root/login landing and the brand home link now open Tenancies. Explicit valid feature URLs survive
sign-in and document reload, with fresh API reads. Full reload does not persist in-memory drafts or
filters beyond existing URL state. Both local instances restarted with their saved data; the original
restart verified14application tables unchanged.

Validation:866backend units at96.1881%,179frontend units at97.55%,6focused shell tests and2real
HTTPS/browser cases covering direct navigation and reload for all7implementedtabs. Documentation,
security and UI/UX reviews passed. Validation receipt (private historical evidence; not distributed).

## Navigation counts for organization and operations — 2 November 2026

Organization drift and Operations now have cobalt numeric navigation badges with stable accessible
link names and separate count descriptions. Organization uses open actionable reviews; Operations
uses waiting or needs_attention, excluding queued/running and terminal history. Zero hides the circle;
retained stale counts are described as last known rather than fresh results. Existing private query
keys support automatic30-second refresh and current invalidation/logout behavior.

OperationDirectory adds derived attention_count, counted under the same read snapshot and workspace
as its list but independently of filters. No new table, migration, endpoint, dependency or workflow
mutation. All1047backend/database/browser tests and184frontend units passed, with separate unit-only
coverage96.1896%/97.57%. Documentation/security/UI reviews and scoped scans passed. Both local
instances restarted with their saved data; original restart fingerprints verify14tables unchanged.

Validation receipt (private historical evidence; not distributed).

## Prompt navigation counts and shared picker audit — 2 November 2026

The persistent sidebar's original interval could miss a queued-to-waiting transition after command
acceptance, while opening Operations caused a fresh list read. A before-fix regression reproduced the
missing navigation refresh. Navigation now publishes a refresh revision for every ordinary menu
activation, including the current path, and Back/Forward. Badges refetch on that signal, observed
workflow transitions and existing invalidations, with a five-second active-page fallback. CSV upload
also refreshes related review counts using the shared helper. No server/authority/schema changes.

The UX reviewer inspected the supplied screenshot and all19 Select uses. Shared popups now grow to
content within viewport limits; state/category controls share a13rem minimum. When field-aligned
placement cannot fit, CSS position-try fallbacks safely center the popup in the viewport inline area
below/above the field. This fixed a real narrow-dialog Home region overflow caught by the expanded
browser tests. DESIGN and the persistent UX policy now require cross-screen/open-menu checks.

Validation:187frontend units at97.58% complete-source coverage;8real HTTPS/PostgreSQL/native-worker
integration cases passed;30isolated picker positioning cases passed. Independent documentation,
security and actual-screen UI reviews passed. Existing backend qualification remains unchanged;
this is a frontend-only change. Data in both local instances is preserved.

Validation receipt (private historical evidence; not distributed).


## P3.1 — Baseline draft authoring, 2 November 2026

Complete locally and available in the primary Atlas app at https://localhost:8443/configuration.
Configuration now saves/edits one draft with complete root policy and quota statement entries,
exact monthly budget/currency and static OTM tag defaults. Line breaks remain part of each statement;
there is no statement parser or numeric-policy substitution. Changed saves record typed immutable
before/after audit in the same transaction. Identical retries are no-ops; changed stale revisions
retain local edits until explicit reload. Runtime grants cannot publish or delete recipes.

The [field map and ER](../reference/baseline-authoring.md) describe all26DTO fields and18columns
in the one new otm_baseline_version table. Migration0011 makes15application tables; the native queue
retains its separate tables. Guarded local test reset now includes nine explicit application tables,
including drafts; auth, Operations and immutable history remain preserved. No CASCADE is used.

Validation:898backend unit tests at96.3234% and195frontend unit tests at97.47% complete-source line
coverage; the final combined backend/PostgreSQL/browser suite passed1,083cases with no failures,
errors or skips, including actual HTTPS/Playwright/native-worker flows. Frozen migration/package,
48generated contract schemas, Ruff, source-purpose docs and design links pass. Documentation,
security and actual-screen UI reviews passed. Narrow Bandit/secret scans report no findings; no
runtime dependency versions changed. Initial failed diagnostics remain retained, not passed receipts.

Both owned local instances were backed up privately and upgraded to0011. All14previous application
tables' row fingerprints are unchanged in each installation. No feed/reset, organization decision,
credential reseed, draft seed or OCI operation was performed on saved user data. Main 8443 is the
primary review app; the separate 8444runbook environment remains available with its own saved state.

This is draft-only. Publication, current-for-new selection, create/import baseline capture, overlays,
bindings, application, rollout and drift remain following P3 slices. No Git check-in/publication.
Validation receipt (private historical evidence; not distributed).


## Policy/quota block editor correction — 2 November 2026

User-selected correction: one multiline policy editor and one quota editor, with one statement per
nonempty physical line. Add/Remove statement controls are gone. Explicit Save converts LF/CRLF/CR
lines into the existing ordered arrays, skips blank lines and preserves other whitespace/order.
Existing1–20statement/2,000character limits remain, with a42,000character browser block cap.
Errors preserve edits. Read/open/Cancel never rewrites saved data; explicit Save normalizes legacy
embedded newlines and can produce a normal audited revision. Tags and budgets retain their controls.
This supersedes the initial per-statement editor and its UI-specific line-boundary wording above.

Validation:201frontend unit tests at97.48%complete-source line coverage;2affected actual HTTPS/
restricted-PostgreSQL browser cases passed, including round trip/reopen and1280/390/320layouts.
Build/generated contracts, documentation and scoped secret scan pass; independent documentation,
security and actual-screen UI reviews pass. Backend/API/schema/dependencies are unchanged, so the
original backend gate remains applicable. Both local instances serve matching current assets;
no reset, migration, seeding or saved business-data mutation was required by this UI update.
Refinement receipt (private historical evidence; not distributed).


## Whole-unit monthly budget authoring — 2 November 2026

Monthly budget input displays250rather than250.0000and accepts positive whole currency units only.
Both the editor and SaveBaselineDraft enforce the rule; API requests with cents are rejected before
writes/no-op handling. The form uses strings, a numeric keyboard and accessible whole-unit guidance.
Storage/read/history retain exact Decimal/NUMERIC(20,4) and fixed-scale hashes. Existing fractional
values stay readable and are never rounded or rewritten automatically; a future save requires an
explicit whole replacement. Actual/forecast cost precision is unchanged. No schema migration.

Validation:904backend units at96.3274%,203frontend units at97.49%, and1,090combined backend/
PostgreSQL/browser cases passed with zero failures/errors/skips. Actual browser coverage verifies
whole250display after save/reload; PostgreSQL covers legacy250.5history and explicit251correction.
Generated contracts/build, lint/purpose docs, design links and scoped scans pass. Independent
security/documentation/UI reviews pass. Both local APIs/workers were restarted with private backups;
all15application tables' row fingerprints remain unchanged in each instance, including saved drafts.
Validation receipt (private historical evidence; not distributed).


## Fifty statements per policy/quota block — 2 November 2026

Each category now independently supports1–50statements, raised from the initial20. Keep2,000characters
per statement and the single newline-separated editor. Browser blocks allow105,000raw characters;
streamed JSON remains bounded at2MiB before parsing. Generated maxItems constraints match. Storage,
field names, canonical hashes, whole-unit budgets and audit semantics are unchanged; no SQL migration.

Validation:906backend units at96.3274%,205frontend units at97.49%, and1,092combined backend/
PostgreSQL/browser tests passed without failures/errors/skips. Both50/51boundaries, valid large
multibyte requests above the old256KiBcap, oversized refusal without service writes and actual
50policy+50quota save/reopen are covered. Generated contracts/build, source docs, lint, design links,
scoped scans and independent documentation/security/UI reviews pass. Both local instances were
backed up and restarted; all15application tables' row fingerprints are unchanged in each, including
saved baselines. Validation receipt (private historical evidence; not distributed).


## Actionable Operations navigation counts — 2 November 2026

A raw waiting/needs_attention state no longer automatically lights the menu badge. The counter
requires an exact current organization intent, matching workspace/person/pending-operation anchor,
and a supported guided handoff/review/blocked retry or existing safe no-effect simulator cancellation.
Read-only inspection failures, orphaned records and unsupported known-effect waits contribute0.
Keep all history/states/list filters; no Delete/Dismiss/Ack/force-success action is introduced.
The count is a workspace hint, not command authorization or a guarantee of provider success.

Validation:906backend units at96.3301%,205frontend units at97.49%,1,094combined backend/PostgreSQL/
browser tests all passed. Real flows cover invalid bootstrap correction, partial required-access
failure after known effects and retry, completion clearing, safe-cancel eligibility and orphaned/
unsupported negatives. Playwright retains diagnostic issue rows without a badge, then shows a real
waiting-create badge on other tabs. Source docs, lint/contracts, scoped scans and independent reviews
pass. Both local runtimes are healthy/current; all15application tables' row fingerprints are unchanged.
No schema, state, baseline, grant, dependency or stored-history rewrite was needed.
Validation receipt (private historical evidence; not distributed).


## P3.2a local baseline publication and history — 2 November 2026

Configuration now publishes the exact saved draft with an explicit confirmation, captures an
immutable typed audit snapshot, and displays paginated published history and read-only exact-version
details. New baseline copies the latest publication and captures its parent; server-side revision
and latest-parent fences reject stale commands. Original-command replay is safe and rechecks live
authority and qualifier availability. The local qualifier checks structure and whole-unit USD
profile only; every publication remains explicitly simulated, without OCI grammar/application claims.

Migration0012 adds publication_mode and frozen publisher display name to the existing baseline
table, now20columns; the application remains15physical tables. Published state requires complete
metadata, including nonnull supported mode. A security review caught SQL CHECK NULL permissiveness;
the explicit nonnull constraint and narrow-role rawSQL regression now protect that boundary.

Validation:920backend units at96.3838%,216frontend units at97.67%,1,114combined backend/PostgreSQL/
HTTPS-browser tests all pass without failures/errors/skips. Atomic audit rollback, concurrent replay,
foreign workspaces, immutable rows, parent races, closed HTTP contracts and responsive confirmation/
history/read-only detail are covered. Lint/format, purpose comments,51schemas and design links pass;
scoped scans report zero findings. Independent documentation, security and actual UI reviews pass.

Both primary8443and preserved test8444 were privately backed up, migrated and restarted. All existing
rows across15application tables are unchanged when comparing pre-migration columns; saved drafts
remain intact. Direct Configuration reload, unauthenticated API denial and current assets verify.
No current-for-new pointer, assignment, create/import pinning, override/rollout, provider binding,
OCI action, workspace reset or Git publishing is included. The next checkpoint connects the
qualified baseline selection to create/import while preserving local-vs-real provider gates.
Validation receipt (private historical evidence; not distributed).


## P3.2b explicit defaults and frozen onboarding pins — 2 November 2026

Publishing now atomically selects the immutable version for future create/import. Use for new
explicitly selects an existing publication with a frozen expected-current token and typed audit.
Default for new is separate from Latest published; history reads never select a default, and new
drafts still derive from latest. The existing registry-revision fence invalidates stale previews
without changing public organization request fields or historical request digests.

New create/import requires a current published simulated recipe and freezes its full snapshot in
immutable intent, with a matching registry pin. Workers verify that exact snapshot/hash/mode and
registry ID, never the later default. Publication during activation and original-request replay keep
the old recipe; newly started work uses the new default. Old accepted operations/tenancies keep
NULL pins and their original behavior. Selection is not policy/quota/budget/tag application/read-back.

Migration0013 adds two nullable scoped-FK columns to existing workspace/tenancy tables, retaining
15application tables and20baseline columns. No existing default or tenancy assignment is invented.
The default has a published/simulated guard; worker credentials can read recipes but cannot update
either selection pointer. Required access, parent/target and administrator guards remain independent.

Validation:934backend unit tests at96.4141%,222frontend units at97.38%,1,135combined backend/
PostgreSQL/HTTPS-browser tests all pass without failures/errors/skips. Tests cover both create/import
wait/publication directions, replay, default-vs-latest selection, confirmation context, rollback,
concurrency, scoped/corrupt data, legacy unpinned completion and registry-pin mismatch before facade.
Security review found the missing registry/intent comparison; it is fixed with unit/PG regression.
UI review corrected summary geometry, selection errors and frozen confirmation context; audit
target labels correctly distinguish drafts from published/default events. All independent reviews,
188-file format,215-file purpose comments, lint,52schemas and design links pass; scoped scans find0.

Both8443and8444 are privately backed up, migrated and healthy with current assets. Old-column
fingerprints across all15application tables are unchanged, and new columns remain NULL for old
records. No workspace reset, seed, credential change, OCI action or Git publication occurred.
Next: apply and verify the pinned recipe through the simulator facade, before real OCI qualification
and later overrides/rollout/drift work. Validation receipt (private historical evidence; not distributed).


## Latest published baseline only — 3 November 2026

User correction supersedes the manual default choice introduced in P3.2b: latest published is
automatically the default for all new create/import operations. Older versions are view-only;
there is no Use for new button, client command or selection endpoint. BaselineDirectory.current
and SelectBaseline are removed. Existing publications take effect for new admissions immediately;
no republish/adoption is required. Drafts do not affect that default until published.

Existing accepted operations keep their full frozen recipe and registry pin, including legacyNULL.
History and historical selection audit events remain readable. The obsolete current_baseline_id
column/FK/guard is retained as unused metadata to avoid discarding stored state; runtime selection
ignores it, and API UPDATE is revoked.0014 only increments registry_revision once, invalidating old
previews. The application remains15tables/20baseline columns and11configurationDTOs/58fields.

Validation:929backend units at96.4001%,219frontend units at97.38%,1,130combined backend/
PostgreSQL/HTTPS-browser tests pass without failures/errors/skips. Tests prove latest wins despite
old/null metadata, removed endpoint404 and no chooser UI, pre-existing publication availability,
publication rollback, stale previews, pinned activation/retry/replay and legacy behavior. Source
checks,51schemas,216purpose-comment files,189formatted files, scoped scans and independent
documentation/security/visual reviews pass. Both saved instances are0014 with private backups,
verified registry revision increments and all other business data/metadata/pins unchanged. Runtime
role lookup, direct Configuration reload, private API denial and current assets verify. No OCI
call, reset, reassignment, data deletion or Git publishing occurred.
Validation receipt (private historical evidence; not distributed).


## Baseline-only async updates and contextual navigation — 3 November 2026

Implemented exact clickable version numbers, contextual baseline return routes and16px backlink
spacing. Create/import inline inspection retains entered values through Back/Forward. Configuration
and active tenancy detail now preview and start latest-baseline updates for the complete fleet or
one child. Any blocker gates the complete batch. Admission atomically freezes recipe/targets,
desired pins/reservations, immutable evidence and a native job. Each child commits independently;
all four readbacks are required before its last-verified pin/time advance. Partial simulated state
and verified prefixes survive supported retries by the responsible authorized administrator.
Operations links back to progress and badges only supported owned retries. Private caches clear
on sign-out. This is local simulation, with no overrides or real OCI qualification claimed.

Forward0015 adds three nullable tenancy fields and extends existing operation/step/audit checks;
there remain15application tables/20baseline columns. The new11DTOs/57fields are mapped in the
[complete implementation guide](../reference/configuration-updates.md) and
[ER supplement](../architecture/diagrams/configuration-updates-implemented.mmd). Main design, spec, UI authority,
test matrix, operations/audit/local guides and build order are synchronized.

Validation:960backend units96.4005%,229frontend units97.26%,1,171combined backend/PostgreSQL/
HTTPS-browser cases, plus a focused time-advanced preservation regression, all pass.54schemas,
225purpose-comment files,188formatted files and independent documentation/security/UI reviews pass.
Bandit, scoped Gitleaks and locked dependency audits report no findings. Both saved instances are
running0015 with current assets, correct direct-route reloads and401private API denial. Private
backups were taken; all existing data fingerprints across15tables remain identical. No reset,
seed, credential change, OCI action or Git publishing occurred.
Validation receipt (private historical evidence; not distributed) ·
[Manual runbook](../how-to/baseline-update-runbook.md).


## Baseline presentation, audit resources and concurrent updates — 3 November 2026

Descriptions/actions now use dedicated center-aligned rows with margins reset. Successful individual
update panels disappear; selected/verified fields retain the result. Bulk success has no Refresh,
and Acknowledge clears only the presentation/URL. Unfinished work and history persist. No-work
eligibility uses a green oval, suppressed when eligibility reads fail. Inventory Status groups exact
assigned baseline, latest/update indicator and a UTC-date-only completed-operation link, reserving
space for later override indicators and cost data. Version links return to the inventory. Latest
selection is green only when it also matches verified state. No override or cost value is fabricated.

Audit keeps operation links and adds scoped friendly employee/tenancy context; registered tenancy
names are clickable and large sets collapse. Original intent hashes/workspaces are validated;
current registry labels do not rewrite historical names. New public fields are derived from existing
storage; CSV remains unchanged. Main design/dictionaries/ER notes, UI authority/policy, audit guide,
test matrix and manual runbook are synchronized; no database migration/column/table is added.

964backend unit tests pass at96.4268%,232frontend units at97.21%, and1,178combined backend/
PostgreSQL/HTTPS-browser cases pass. Real concurrent starts prove one distinct-key winner, same-key
receipt recovery and one native job; duplicate worker invocations prove one verification per child.
Actual loaded desktop/mobile screenshots and navigation/geometry/acknowledgement checks pass.
54schemas,226purpose files,189formatted files, independent documentation/security/UI reviews and
scoped scans pass. Both local saved instances remain0015 with current assets and healthy protected
routes. Private backups and all15table old-column fingerprints confirm existing data preserved.
No reset, seed, credential change, OCI call or Git publication occurred.
Receipt (private historical evidence; not distributed) ·
[Manual guide](../how-to/baseline-update-runbook.md).


## Authored overrides and staged-review local qualification — 3 November 2026

Implementation and local qualification are complete against accepted chapters 03/10. The new
[guide/field map/manual review](../reference/tenancy-overrides.md) and
[implemented ER](../architecture/diagrams/tenancy-overrides-implemented.mmd) capture 10 override DTOs / 55 effective fields,
12 updated rollout DTOs / 76 fields, 3 new tables/35 columns and 2 nullable existing-tenancy configuration
heads. The 0016 source schema has 18 application tables and 20 baseline columns; 59 schema artifacts are
exported. Both saved instances are upgraded and all required local gates pass.

The editor binds assigned baseline/context, supports independent complete policy/quota list and
whole-budget overrides, and leaves tags/required access separate. Staged owner plans preserve exact
proposals/hash/choices without touching live heads or jobs; every conflict/blocker must clear before
whole-batch atomic acceptance. Immutable configuration revisions distinguish same-baseline edits
from complete verification. Current/null legacy rows and original accepted JSON/request digests
remain compatible; no invented backfill is part of the source migration.

Complete separate 95% backend/frontend unit gates, disposable PostgreSQL/worker/browser regressions,
independent reviews and preserved-data backups/upgrades pass. The [test matrix](../engineering-test-plan.md#authored-overrides-and-staged-plan-qualification-matrix)
and [build checkpoint](../engineering-design/18-database-ci-and-build-order.md#authored-overrides-and-staged-plan-local-qualification)
record this completed local scope and the separate future provider milestones. No reset, seed,
credential change, live OCI call or Git publication occurred.


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


## Shared-access and onboarding application refinement — 3 November 2026

Local implementation, all required qualification checks and both saved-instance upgrades pass.
Six coordinated refinements reuse the existing modular app and providers: dedicated override detail,
removal of a redundant owner/association shortcut, registered creation-time tooltip, existing/new
shared compartment choice, exact identity-removal receipt and steps, and onboarding v2 applying its
frozen baseline followed by post-configuration access checks before temporary-account retirement.

Migration 0017 extends existing operation-step allowed values; 18 application tables remain. Optional
existing-compartment input is omitted when null for replay compatibility. Previously accepted
onboarding v1/legacy intents are not rewritten. Four-category partial observations and verification
heads reuse current storage; manual shared-compartment/resource cleanup remains outside the tool.

[Runtime workflow guide](../reference/organization-workflows.md) ·
[Onboarding steps/fields](../reference/tenancy-onboarding.md) ·
[Manual review runbook](../how-to/tenancy-refinements-runbook.md). Required source-unit/PG/browser gates, independent reviews and artifact checks pass.
Saved-runtime preservation checks pass for both saved instances in this new slice. Real OCI/secret custody/provider qualification and full-MVP completion remain future work.


### Local qualification results

The final combined backend/PostgreSQL/native-worker/HTTPS-browser run passes 1,237 cases with no
failures, errors or skips. Backend unit-only coverage is 6,405 of 6,673 lines (95.9838%) across all
90 runtime modules, from 1,002 unit tests. The 266 frontend unit tests cover 1,496 of 1,537 lines
(97.33%) across 28 files. A separate final actual HTTPS/browser/PostgreSQL check passes the native
selected-content existing/create/existing mode transition and successful assignment/removal after
the last picker fix; it is additional evidence, not a relabeled all-database test count.

All 59 generated schemas, 238 Python purpose-comment files, 213 formatted Python files, Ruff and
document links pass. Dependency audits, Bandit and scoped Gitleaks report zero findings. Independent
security, migration/installer and final actual-screen UI reviews pass. This qualifies local
simulation only. Both saved instances are upgraded from 0016 to 0017 with private 0600 backups. Old columns/rows
across all 18 application tables have identical fingerprints; baselines, pins and history are
preserved. The 18-table inventory and 20-column baseline table are unchanged; no table/column or
backfill was added. Matching per-instance frontend snapshots, API/worker liveness, current assets,
direct-route HTTP 200 and protected-API HTTP 401 checks pass on both ports.


Local qualification and saved-instance receipt (private historical evidence; not distributed).


## On-demand configuration drift visibility — 3 November 2026

Local implementation, final gates and both saved-instance upgrades pass.
The authored source adds explicit asynchronous single/fleet checks against assigned immutable
baseline plus accepted overrides, separate confirmed-drift/check views, category evidence and
retained confirmation after failed reads. One 13-column immutable table takes the qualified local schema
to 19 application tables; operation/step/audit/native queue infrastructure is reused.

All four local bundles must have complete authorized observations to confirm or clear drift.
Unknown/malformed/incomplete data is not missing; old generations cannot green current assignments.
Database acquisition ordinals and a 24-hour freshness limit keep history/current health distinct.
Checks never apply configuration or change assignment/verified/observation heads. Daily scheduling,
repair/email and full real OCI bindings/grants/tag/budget-alert qualification remain future work.
No simulator helper edits saved observations; negative scenarios use disposable synthetic fixtures.

[Runtime fields](../reference/configuration-drift.md) ·
[Implemented ER](../architecture/diagrams/configuration-drift-implemented.mmd) ·
[Manual review](../how-to/configuration-drift-runbook.md). Source-unit, PostgreSQL/native-worker, actual-browser, independent reviews and saved-runtime
preservation evidence all pass for this slice.


### Final local qualification and installation

All 1,306 combined backend/PostgreSQL/native-worker/HTTPS-browser cases pass with no failures,
errors or skips, using disposable synthetic databases. The 1,060 backend unit tests cover 6,953 of
7,248 executable lines (95.9299%) across all 99 runtime modules. The 320 frontend unit tests cover
1,571 of 1,613 lines (97.396%) across 29 files. Unit-only coverage is separate from database/browser
evidence. The final focused actual native-browser check also passes after workflow-based fixture
setup in its own disposable database; it uses real API/native-worker behavior, not a mocked browser
response or a user simulator helper. Final UI review covers three viewport widths.

All 63 generated schemas, 253 Python purpose-comment files, 229 formatted Python files, Ruff and
document links pass. Fresh dependency audits report zero known vulnerabilities across 75 locked
Python packages with no skips and zero npm findings; Bandit and scoped Gitleaks also report zero.
Independent security, migration/installer, documentation and final actual-screen UI reviews pass.

Both saved instances are upgraded from 0017_membership_onboarding to 0018_configuration_drift.
Private 0600 backups are retained; fingerprints of every old column/row across all 18 existing
tables match. The one new check table brings the inventory to 19; the 20-column baseline table,
accepted pins, overrides and history are preserved. Both API/worker pairs are alive, with matching
private qualified frontend snapshots. Liveness/current assets/direct drift HTML return HTTP 200;
private drift APIs reject unauthenticated requests with HTTP 401. No saved-data reset, backfill,
credential change, live OCI action or Git publication occurred.

This completes read-only on-demand local drift visibility. Repair, daily scheduling/infrastructure,
email and full real OCI binding/permission coverage remain separate future qualification. The next
review is the implemented checks and evidence; this checkpoint does not silently start those later
workstreams.


Final local qualification and installation receipt (private historical evidence; not distributed).


## D50 explicit guided responsibility takeover — 4 November 2026

Application implementation, all final gates and both saved-instance upgrades pass. The user agreed
to continue OCI-independent application work while parent-tenancy access is unavailable, selecting
accepted D50 workload responsibility takeover instead of adding temporary simulator controls. No
automation-key/provider-permission handoff or new credential flow is inferred.

The source adds explicit self-claim for waiting/needs_attention guided create/import, real audited
responsibility updates, optimistic revision/replay guards and replacement continuation authority
validated against exact original intent plus current grant/revision. Creator, activation mailbox,
owner, provider intent/pin and prior progress remain unchanged; claiming queues no job. Only current
responsible can submit setup actions. The new audit-kind constraint migration 0019 adds no table/
column, retaining 19 application tables and 20 baseline columns. Four computed detail fields expose
current responsible/revision/eligibility; they are not new database columns.

[Runtime field/authority guide](../reference/responsibility.md) ·
[Manual review](../how-to/responsibility-runbook.md). Required source-unit/PostgreSQL/native-worker/actual-browser gates, independent reviews and
saved-instance preservation checks all pass.
Notifications/packaging require a later choice; no later slice is started. Real OCI and email
transport qualification remain separate.


### Final qualification and preserved-data installation — 4 November 2026

All 1,330 combined backend/PostgreSQL/native-worker/HTTPS-browser cases pass with no failures,
errors or skips, in disposable synthetic databases. The 1,077 backend unit tests cover 7,062 of
7,362 executable lines (95.925%) across all 100 runtime modules. The 338 frontend unit tests cover
1,600 of 1,642 lines (97.4421%) across 29 files. Unit-only coverage is measured separately from
transaction/browser proof. The final focused actual native-browser case also passes after rebuilding
the corrected Initiated by subtitle; create/import component checks preserve the original contact.
Final independent UI review approves all six synthetic screen captures.

All 64 generated schemas, 260 Python purpose-comment files, Ruff/format and document links pass.
Fresh audits report zero known vulnerabilities across 75 locked Python packages with zero skips,
zero npm vulnerabilities, and zero Bandit/scoped Gitleaks findings. Independent security, migration/
installer, documentation and final actual-screen UI reviews pass.

Both saved instances are upgraded from 0018_configuration_drift to 0019_operation_responsibility
with private 0600 backups. Every old column/row across all 19 existing application tables retains
identical fingerprints; there are still 19 tables, no new table/column and 20 baseline columns.
Baselines, accepted pins, overrides, administrator accounts and history are preserved. Both API/
worker pairs serve matching private qualified frontend snapshots. Liveness and Operations HTML
return HTTP 200; unauthenticated takeover POST returns HTTP 401. No saved-data reset, backfill,
extra saved administrator, real OCI call or Git publication occurred.

The current main installation has one local administrator, so already-responsible work correctly
hides Take responsibility. Review the positive multi-admin capability through its disposable
qualification rather than expecting a second-account simulator control. This completes the selected
OCI-independent application feature; notification transport, corporate identity issuance and live
OCI qualification remain future work requiring their own review. No next workstream is started.


Final application qualification and saved-instance receipt (private historical evidence; not distributed).


## Notification and environment email policy — accepted 4 November 2026

The next authorized slice is responsible-admin create/import action/failure email plus an operator
environment email policy covering SMTP and OTM-controlled OCI activation/invitation/recovery
contacts. Canonical employee/manager/SSO keys stay unchanged. Local/staging uses one explicit test
destination; missing test routing blocks email-capable external work, production rejects test
overrides/bypasses, and production unresolved responsible contact has no all-admin fallback.

[Accepted decision and release gates](../engineering-design/21-environment-email-policy.md) capture
immutable original/effective routes, policy fingerprints, queued policy-change blocking and legacy
intent/responsibility-proof compatibility. Both independent release paths need offline validation
against a trusted expected environment before delivery/OCI credentials/deployment. No hosted CI,
repository publication, actual mail or OCI call is performed by this design/documentation update.
Runtime contracts, field dictionary and qualification are in progress; no completion/install claim
is made for this slice. Imported/uncontrolled OCI contact behavior remains explicit qualification.


## Durable lifecycle email source checkpoint — 4 November 2026

Implementation/qualification pending. Source contracts now map frozen environment and OCI-contact
routes, responsible-admin create/import action/failure SMTP, one 15-column retained outbox (20
application tables), bounded known-rejection retries and terminal unknown/no-blind-resend knowledge.
Original contacts including local-recovery null and all canonical employee/SSO identifiers remain
unchanged. Optional contacts excluded when null retain legacy typed takeover proof compatibility.

[Field-complete guide](../reference/lifecycle-email.md) ·
[Source/rendered ER](../architecture/diagrams/lifecycle-email-implemented.mmd) ·
[Local capture and both offline release paths](../how-to/lifecycle-email-runbook.md). Missing local
test routing denies egress even with a real original contact. Production rejects testing; staging
requires one override. SMTP/profile/origin/settings changes fence old work and require coordinated
restart. No OCI adapter or Vault/hosted SMTP/CI qualification is claimed. Gates and saved-instance
upgrade/preservation are pending; no reset, real email/OCI action or publication was performed by
this documentation work.


## Lifecycle email qualified locally — 4 November 2026

The final validation record (private historical evidence; not distributed) supersedes
this slice's earlier source-only pending checkpoints. The complete disposable PostgreSQL/browser
suite passed 1,421 tests with no failures/errors/skips. Backend unit-only coverage is 95.8244%;
frontend 371 tests pass at 97.4592%. Documentation/inline, UI/UX and independent security reviews pass.

Both saved Atlas instances are backed up and upgraded to 0020 with all existing columns/rows from
19 application tables preserved. The 15-column notification outbox is table 20; no historical work
is backfilled with email. Main 8443 uses local capture 8025; separate 8444 uses 8026. Both route NEW
controlled delivery to capture@otm.test without rewriting organization/administrator identities.
The local recovery administrator still has no profile email. Real OCI remains simulated.

The two executable release gates validate trusted expected environment independently: staging
requires a test destination; production forbids testing settings. CI wiring/credentials/deploy,
production Vault/SMTP and real OCI-contact qualification remain infrastructure/provider work.
The [manual runbook](../how-to/lifecycle-email-runbook.md) covers the review. No Git publication or
real recipient mail was performed. Security evidence records that image-CVE scanning was unavailable.


## Separate Email delivery audit category — 5 November 2026

Source/UI refinement qualified locally. Existing email_delivery audit events now have the distinct
Email delivery category instead of being mixed into the Operations audit filter. All categories
and retained history remain available; directory/CSV share the same category projection. The
operation-detail notification panel and actual delivery/routing behavior are unchanged.

No database migration/table/column, audit-record rewrite or saved-data change is required.
[Audit filter/source semantics](../reference/audit-history.md#separate-email-delivery-category-5-november-2026) ·
[Lifecycle email scope](../reference/lifecycle-email.md). The validation record (private historical evidence; not distributed) records passing backend/frontend unit gates, 56 focused PostgreSQL/SMTP/browser tests and documentation/security/UI reviews. Both saved apps were refreshed with private backups and every row/column in all 20 application tables preserved. Capture services and settings were untouched.


## Configuration freshness messaging — 5 November 2026

Source/UI refinement qualified locally; both saved instances are refreshed with all existing
rows preserved. Existing issue_count now aliases confirmed_issue_count: unknown/stale/unseen evidence
cannot manufacture drift, while complete same-context findings survive age, failed reads and
rechecks. One computed stale_count brings ConfigurationDriftDirectory to 11 fields; unchecked_count
excludes stale. Nine drift DTOs now have 83 fields and the generated contract inventory is 68
schemas. Stale is a query-filter alias, not a new persisted or summary check state. No table,
column, migration, evidence rewrite or ER change is needed.

The shared UI shows confirmed drift separately from Check out of date, Unable to verify, Not
checked and Checking, with matching fresh only. Counters overlap independently of paging/filter.
Actual recheck completion must refresh inventory/detail, directory and child check-detail caches;
acceptance cannot clear findings or evidence age. Source/disposable-clock/browser regressions
cover exact 24-hour boundaries, retained findings and legitimate fresh MFA after long clock steps.
[Runtime field/filter guide](../reference/configuration-drift.md#filter-and-counter-interpretation) ·
[Manual review](../how-to/configuration-drift-runbook.md#freshness-and-confirmed-drift-regression-review-5-november-2026).

The user expressly deferred the drift-detection CronJob until staging/Kubernetes deployment. No
local CronJob, scheduler demo or simulation controls will be added now. Later scheduled read-only
admission needs qualified noninteractive authority/overlap/restart handling through the existing
worker; this does not presume the interactive administrator endpoint is a scheduler identity.
Repair and real OCI/provider binding qualification remain separate future work.


Freshness validation record (private historical evidence; not distributed):
1,171 backend unit tests pass at 95.826% line coverage; 398 frontend tests pass at 97.4985%.
The focused PostgreSQL/HTTP suite (81 tests) and final native HTTPS/worker/browser+metadata (2 tests)
pass. Documentation, independent security and responsive UI reviews pass. Both saved instances
were privately backed up/refreshed with all 20 tables' existing rows/columns preserved; no schema,
history, credentials, settings or capture-service change. The daily drift CronJob remains explicitly
deferred until staging/Kubernetes; no local scheduling or simulation controls were introduced.
