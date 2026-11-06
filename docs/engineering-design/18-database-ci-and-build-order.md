# 18: database, CI and incremental build order

28 October 2026 | C6 handoff reviewed and approved | Whole-package signoff pending; local implementation evidence is tracked in development progress

[Design hub](README.md) · [Production data model](11-production-data-model.md) ·
[Test and merge policy](../engineering-test-plan.md#d53-required-test-and-merge-gates) ·
[Simple restore contract](17-recovery-and-release.md)

## Keep the first build small

Use the existing organization/association implementation, fixtures and tests. Keep one repository,
one modular backend and the agreed OCI facade/simulator. Add the production migration foundation and
one complete durable operation before building all workflows. The 30-table proposed inventory, including the D58 administrator extension, describes the
whole application, not a requirement to create every table before the first working slice.

Use one migration/contract owner. Other developers/Codex contexts can work against those shared
interfaces once the first slice works; they do not independently invent schema versions or job states.
No extra queue, cache, graph service, recovery coordinator or microservice is needed for this plan.

## P0.9 implementation status

The first [production admission slice](../reference/admission.md) now implements operation and
immutable-intent storage, a forward-only frozen Alembic migration and native enqueue on the caller's
transaction. It requires an injected administrator authorizer but exposes no business routes or SSO
substitute. Actual runtime source meets the 95% unit-only gate; mandatory disposable PostgreSQL tests
separately qualify migrations, concurrency, COMMIT failure, queue rollback and append-only history.
Migration SQL/environment are deployment artifacts outside the runtime unit denominator and remain
integration-tested/reviewed; all modules in `backend/src/otm` are included without exclusions.

The [registered simulated worker](../reference/worker.md) now executes one complete read with
injected current-authority checks, short claim/publication transactions, immutable normalized
observations and guarded generations. Forward migration 0002 adds the approved logical step and
expands audit events without weakening exact-intent pointers. No accepted inspection adopts a registry
entry or dispatches configuration. Hosted CI/master protection, real authority/credential composition,
managed PostgreSQL privileges and publication clearance remain incomplete. The retained experiment
continues to qualify process mechanics separately from this actual production-package read worker.

[Session verification](../reference/authentication.md) now adds the fourth production table,
current injected administrator authorization and optional protected `/api/session` context. It
connects that authority to internal command admission and guards configured requests with HTTPS,
Host and unsafe Origin/custom-header rules. It deliberately adds no login/issuance route or default
provider. The maintained SSO/session-library and live corporate integration requirement is not yet
fulfilled by Starlette request middleware alone. Browser route tests use ASGI; Playwright remains
required when the production UI arrives.


## Application settings and housekeeping checkpoint

The [versioned TOML settings and maintenance command](../reference/application-settings.md)
implement configurable session lifetimes and daily bounded cleanup, with a CronJob rendered from
that same schedule. Migration 0004 pins idle policy and revokes legacy sessions. Exact runtime/touch/
cleanup expiry predicates are integration-tested. This introduces no table and no separate scheduler
service. Terraform/OKE must still install the rendered job, ConfigMap, qualified image and restricted
maintenance credentials; nothing is deployed automatically. The local React frontend now wires
explicit input activity separately from session polling; production browser/deployment qualification
remains separate.

## Database implementation checklist

Chapter 11 remains the field dictionary. Convert the tables needed by each slice into reviewed
SQLAlchemy/Alembic migrations, preserving the prototype's organization behavior and stable identities.
Do not write a second competing SQL schema by hand as a design artifact.

| Area | Required constraints / transaction behavior | Initial access paths |
|---|---|---|
| Organization | Preserve current/proposed versions, stable people, source provenance and exception-resolution/return rules; publish atomically | Existing workspace/current-version/person keys; manager/LOB filters actually used by screens |
| Registry/associations | Unique bound tenancy identity; one active owner per tenancy and one active person/tenancy association under the agreed state contract; same-workspace references | Tenancy listing, owner/member lookups and FK-side indexes |
| Operations/steps | Request-key/intent uniqueness, scoped step identity and revision/generation guards; acceptance/audit/enqueue and continuations commit together | Operation target/state, step identity and due-work lookup; reuse runner indexes |
| Configuration | Immutable published baseline/effective versions, scoped exact object bindings and protected required-policy composition | Assigned baseline, current configuration/binding and unresolved issue lookup |
| Access/credentials | Scoped principal/credential/version/window references, serialized first disclosure and original deadline; CURRENT resolution for passwords | Exact credential/binding, active window and due rotation lookup |
| Observations/finance | Unique logical acquisition/observation identities, exact child scope and one coherent Budget response; null stays unknown | Per-child current compatible observation, binding/cycle and source/capture ordering |
| Audit/outbox | Immutable intent/evidence, command/source-event uniqueness and frozen routing; ordinary roles cannot edit history | Bounded target/time history, due notifications and idempotency lookup |

Implement database uniqueness/FKs for invariants that must hold under concurrent writes, with
application validation for good diagnostics. A Python pre-check alone is not enough. Keep claim/
publication transactions short; no OCI/network call inside them. Prove that the chosen runner can
enqueue in the same DB transaction; if that integration fails, raise that specific issue rather
than building a second runner.

Start with PK/unique/FK and the concrete lookup/due-work indexes above. Inspect representative query
plans in disposable PostgreSQL before adding specialized covering or JSON indexes. At this scale,
there is no current requirement for partitioning, sharding, read replicas or a separate reporting DB.
Serve the consolidated dashboard from stored views/queries, with stable pagination and no per-row OCI
calls. Preserve independent Actual/Budget sorting over observed values and the accepted null ordering.

Separate migration ownership from runtime access. Validate actual effective grants: authenticated
private TLS connections, parameterized SQL, no runtime DDL or audit rewrite, and current workspace/
application authorization. Additional DB roles should follow a real permission difference rather
than a diagram alone. Pool limits and timeouts remain small configurable deployment settings, tuned
against measured API/worker/runner connections. Managed PostgreSQL privileges still need integration
qualification; a Docker database is the local test authority, not proof of production compatibility.
Pin the test image to the selected production PostgreSQL major when that service choice is qualified.

For each migration, test an empty database and the prior supported application schema, then rerun
existing organization/association scenarios. Use expand/contract changes when rolling versions can
overlap. Never use the prototype workspace-reset endpoint in production. Image rollback is allowed
only while schema/job contracts remain compatible; DB restore follows D54's manual procedure.

## Concrete CI jobs

Use a single required build workflow with parallel jobs where independent. Stable check names below
are implementation proposals; once configured, make them required for protected `master`.

| Job | Required work / pass condition |
|---|---|
| `quality` | Locked install, lint/format/type checks, inline docs, current design/schema/generated-client consistency and application build |
| `backend-unit` | All backend unit tests pass; complete first-party backend source, including unimported files, reaches at least 95% unit-only line coverage |
| `frontend-unit` | All frontend unit tests pass; complete first-party frontend source reaches at least 95% unit-only line coverage; do not silently omit existing/reused application JS |
| `postgres-integration` | Fresh disposable Docker PostgreSQL, migrations and real repository/transaction/constraint/runner scenarios all pass; missing DB means failure |
| `playwright-ui` | Built application plus isolated prototype/backend/database and simulator; required real browser journeys pass, including desktop/mobile and failure behavior |
| `security` | Required secret/static/resolved dependency checks; applicable built-image/IaC checks; scan failure, unavailable/missing/skipped required results block merge. Independent slice review and pre-first-push PII publication review follow [D56](../security-review-policy.md) |
| `required-ci` | Fail-closed aggregate: every required job actually ran and succeeded, required coverage reports exist and meet thresholds, and results match the current candidate |

Run on every CI build, including pushes and PR candidates; do not path-filter away required suites.
The frontend job becomes operational with the application frontend test setup, which includes any
prototype JS retained in production. P0 must identify the prototype coverage gaps and close those relevant to each production
extraction; the complete production source must reach 95% from its first slice. Prototype coverage
remains diagnostic and is not a prerequisite for creating the separate production foundation. Tests execute behavior and negative cases; trivial tests
or exclusions are not a remedy for a low coverage result. Branch coverage is reported separately;
D53's numeric gate is unit-only line coverage, not merged unit/integration/browser coverage.

The integration jobs use real disposable PostgreSQL and fake OCI/Vault/mail, not production data or
live tenancy mutations. Preserve reports/coverage and sanitized Playwright failure traces with the
source revision. Generated API/client drift is checked against the actual application models. No
container image is promoted from a failed build. Exact tool versions are locked during P0 setup;
this document adds no unverified dependency or actual GitHub workflow.

Protect `master` with PR-only changes and required current-candidate checks; direct/force pushes,
branch deletion and routine bypass are prohibited. Use an up-to-date candidate or qualified merge
queue so an old passing head cannot authorize a changed merge result. Before normal feature merges,
prove that a failing test, insufficient/missing coverage and skipped/missing job each block a merge.
The repository currently has no initial commit or remote, so hosted protection is not yet configured.
Remote owner/name and corporate CI permissions are setup inputs, not guessed from this design.

## D58 A1 administrator implementation checkpoint

The [administrator foundation](../reference/administrators.md) now adds current OTM grants,
the reserved local credential shape and internal ordinary-grant revocation with exact session
reference/revision checks and atomic audit. Production has six application tables and six frozen
migration revisions; the full 30-table target is still introduced incrementally. [Local bootstrap/reset and password/MFA sign-in](../reference/local-authentication.md) are
now implemented; ordinary grant creation/regrant and corporate
identity qualification remain future work. The later [laptop application launcher](../reference/local-application.md)
now creates private persistent local credentials and a restricted Docker-PostgreSQL API role only
when explicitly run; it never creates a default human account. No OCI role/hosted resource is
provisioned. Automated DB/browser scenarios use separate disposable fixtures.

## Application and configuration deployment paths

29 October 2026: the user selected separate application and configuration deployment flows.
Both use reviewed changes and protected `master`. These are deployment paths after the same D53
merge checks; a settings-only change does not skip unit, database, browser or security gates.
Neither flow is installed in GitHub or OKE yet.

| Path | Input and validation | Deployment work |
|---|---|---|
| Application release | Reviewed source, locked dependencies, every required test/security check, built image and supported settings schema | Publish/promote the immutable image digest; apply reviewed migrations when needed; deploy API/workers/jobs with compatible settings; verify readiness |
| Configuration release | Reviewed nonsecret `application.toml`, strict validation using the **currently deployed application's** settings schema, safe change summary and maintenance-manifest generation | Retain the deployed image digest; update the settings ConfigMap and affected CronJob definition; roll long-running consumers; verify loaded settings and readiness |

No image rebuild is needed for changing an existing supported setting. Introducing a new settings
field or behavior requires a compatible application release first. The release pipeline must reject
unknown keys and invalid values rather than silently accepting them. Workspace/local issuer are installation identity: routine configuration deployment must reject
changes to them after bootstrap; a deliberate installation migration is separate operator work.
Settings remain operator-managed
in V1; there is no application UI for editing runtime configuration. Child-tenancy configuration
baselines/overrides are a different feature and do not edit this file.

Keep one deployment owner/pipeline per environment. Serialize application/configuration deployments
through that environment's deployment lock; validate against the actual deployed image and recheck
its digest before apply. An application release and a settings change must not race and accidentally
restore an older image or incompatible configuration. This is a normal CI environment lock, not a
new application coordinator or database table.

Publish a ConfigMap containing key `application.toml`; put a checksum of that exact nonsecret file
in each consuming API/worker pod template so a settings change triggers a rolling restart. No hot
reload or reliance on eventual mounted-file updates is assumed. Running pods keep their loaded
settings until replacement. New maintenance Jobs load the mounted file when they start; already
running Jobs finish with the settings they loaded. Changing cleanup hour/minute also requires
regenerating and applying the CronJob schedule. Record settings hash, source revision, deployed
image digest and sanitized deployment outcome; never record credentials or entire secret-bearing
process environments.

A configuration rollback reapplies a previously validated compatible file and the matching CronJob
schedule, then rolls consumers. It does not roll back application images, database migrations or
external OCI actions. Session limits remain pinned at issuance: even after a settings rollback,
existing sessions retain their original limits. No automatic session revocation is implied.

When OKE is provisioned, Terraform establishes the cluster, namespaces, identities and initial
resources. The environment deployment path owns subsequent settings/CronJob updates; the Terraform
and deployment definitions must share one source and an explicit ownership boundary so a later
Terraform apply cannot undo a reviewed runtime configuration release. Exact chart/manifests and
state ownership are implementation work for the infrastructure slice.

## Build order and useful review milestones

| Slice | Concrete outcome | Evidence before expanding |
|---|---|---|
| P0: reusable foundation | Private repo/master protection after design approval and sanitized publication review, locked tools, CI/coverage/security harness, generated-model conventions and migration baseline around existing org slice | Existing behavior retained with synthetic fixtures, no real employee PII/secrets in publish set, complete production source measured at 95% or higher, CI negative-enforcement probes; no live OCI required |
| P1: one durable operation | Admin command → atomic acceptance/audit/job → worker → simulated OCI result → verified publication → Operations UI | Duplicate/retry, crash, uncertain result, wrong target, transaction rollback and manual restore-hold scenarios |
| P2: tenancy journeys | Create/manual activation/bootstrap, import, shared membership/ownership and offboarding through accepted screens | Per-flow acceptance, partial failure/recovery and registered-child deletion guards; test simulator first |
| P3: managed configuration/access | Versioned baseline/override rollout, drift/repair and recovery password CURRENT/rotation flow | Exact bound objects, protected access, original disclosure windows and unknown rotation tests |
| P4: unified visibility | Approved Tenancies dashboard, current-cycle Budget reads, operational history and responsible-admin email | Stored-data sorting/freshness, coherent partial values, episode/delivery/routing and UI integration cases |
| P5: live pilot/release | Terraform/OKE/managed PostgreSQL/SSO/email setup, temporary operator-pod bootstrap/reset and narrowly authorized provider qualification | Actual permissions/SDK capabilities, independent operator RBAC/DB/Vault custody and outage/reset drills, manual restore, runbooks and monitored release |

[Read-only Operations](#operations-read-visibility-checkpoint) now implements list/detail visibility
over the existing durable tables without fake activity or new mutation actions. Full P1 remains
broader than the first read milestone. The subsequent [simulation checkpoint](#local-durable-simulation-checkpoint)
now adds bounded local admission and a separate worker; real tenancy flows remain later work. The accepted cloud
operator procedure belongs to the infrastructure/pilot slice below.

P5 environment preparation can run alongside earlier application work, but it does not block local
simulator-first development. One engineer with Codex is a reasonable default. Extra engineers can
own bounded frontend, adapter or platform packages after P0/P1 interfaces stabilize. Keep a single
migration/contract owner and merge small working slices; measure the first slice before promising a
calendar. No separate services are introduced just to create parallel tasks.

## Simplicity audit of the existing design

| Area | Disposition / reason |
|---|---|
| External recovery coordinator/journal | Removed by D54; manual paused restore is adequate for V1 |
| Secret version evidence | Keep for staged rotations/audit/API keys; normal passwords resolve Vault CURRENT |
| Durable runner and atomic enqueue/audit | Keep; ordinary process failure is routine, and duplicate destructive effects matter |
| Target bindings, tenancy/owner associations and revisions | Keep; required for correct OCI targeting, accountability and concurrent changes |
| Proposed table inventory | Build by feature; re-evaluate a table if it duplicates an existing authority before migration |
| Index/scale features | Minimum query-driven indexes first; add measured optimizations only when needed |
| CI and coverage | Keep D53 unchanged; simplicity does not mean weakening the requested test/merge gates |
| Rare incomplete provider/restore evidence | Visible held state and human review; ask before adding substantial automatic reconstruction |

The user reviewed and approved this handoff on 28 October 2026, retaining D54's simplification. Astra review and its corrections are complete; whole-package final user approval remains pending; this does not claim implemented/qualified C1–C6 behavior
or all provider dependencies qualified. Remaining external inputs are production feed authority,
corporate SSO/admin entitlement, approved mail service, hosting/parent access and live OCI permissions.
They are named integration/pilot gates; no one needs to invent them to build the local vertical slice.


## D56: security review on every slice

Before calling any slice complete, obtain independent `security_review` assessment and address its
blocking findings. [The security policy](../security-review-policy.md) covers OWASP/application risks,
secret/PII exclusion and supply-chain review. P0 first clears the proposed publish set, including
real identities currently present in design examples/source and non-text evidence; default ignores
are defense in depth, not sanitization. No real source HR data is added to satisfy CI fixtures.
Add the required `security` job to `required-ci`; no scan or agent pass is claimed by this document.


## D57: original A selected for production UI

Build the application shell and reusable components using **original A / Field Console**, chosen
28 October 2026 after the rounded-A comparison. [DESIGN.md](../../DESIGN.md) defines the navy/cobalt
palette, cool light surfaces and crisp 3px geometry. Retain approved interactions, field coverage,
accessibility and security; do not adopt A2's softer geometry by default.


## Local P0.1 checkpoint — 28 October2026

[Development progress](../history/development-progress.md) records the synthetic-only test milestone:
147 passing tests from a clean export, including directory name-fallback and connection-target
negative cases. Private HR exports and the persistent lab remain unchanged. This is reusable
prototype/test preparation; P0 overall and production app/CI setup are not complete. No Git
check-in or repository publishing has occurred; final approval/publication gates remain binding.

## Infrastructure slice: cloud administrator bootstrap/reset

30 October 2026: implement [chapter19's accepted temporary operator-pod procedure](19-administrator-provisioning.md#accepted-cloud-operator-procedure--30-october-2026)
within the Terraform/OKE delivery work. Use an approved digest-pinned image, interactive TTY,
independently authorized `kubectl` RBAC, separately qualified operator database privileges and the
production OCI Vault adapter. The ordinary API runtime identity cannot invoke that authority.
The operator's Kubernetes access must remain usable without OTM or corporate SSO, with approved
network/authentication controls retained.

Prepare nonsecret pod/configuration templates, RBAC, database/Vault permission boundaries and the
manual runbook. Factor values are interactive input/enrollment material only: never put passwords,
TOTP seeds/codes in YAML, CLI arguments, logs, Terraform state or captured CI sessions. The current
file-secret-bound `otm-admin` composition must gain the qualified cloud adapter before this can run
in OCI; `otm-local` remains a laptop wrapper. `reset-local` names the application-local identity,
not the location of the cluster. Keep bootstrap one-time and reset identity-preserving, with revision,
session invalidation and audit committed together.

Required infrastructure evidence:

- Unauthorized Kubernetes pod creation/exec and ordinary API attempts at bootstrap/reset fail.
- Repeated/concurrent bootstrap cannot reseed; explicit reset preserves the grant identity and
  invalidates prior sessions while producing the expected immutable audit.
- An independently authorized operator can recover during an app/corporate SSO outage; DB/Vault
  failures and uncertain commit preserve honest status and safe secret-reference inspection.
- Synthetic factor values do not appear in manifests, args, logs, CI/captures or deployment state.
- The temporary pod is removed after completion or approved abandonment, without deleting a
  potentially committed secret version; nonsecret verified operator evidence remains available.

This records infrastructure acceptance work, not deployed resources, tested cloud permissions or
production qualification. It creates no Git/publication or live-cloud authorization.

## Operations read visibility checkpoint

The [Operations guide](../reference/operations.md) now documents authorized list/detail over
existing `otm_operation`, `otm_operation_step` and `audit_event`. The two GET APIs and React pages
reuse committed state/intent/evidence under current session/workspace authority. Each response comes
from one read-only repeatable snapshot; current intent/hash and returned payloads are validated.
Steps are current-intent-only and recent events are limited to 50 without removing immutable history.

That first checkpoint provided read visibility only. The subsequent simulation slice below now
adds explicit local admission and a separate foreground worker. It adds no table, fake activity,
OCI write or generic retry/resume/cancel workflow. Simulated inspection
success remains distinct from adoption or native runner completion. Final complete-source backend/
frontend unit, real PostgreSQL/browser and independent-review evidence is recorded in development
progress after final gates. Cloud operator-pod qualification remains a separate infrastructure task.

## Local durable simulation checkpoint

[The implemented simulation slice](../reference/simulation.md) extends the read-only milestone
with current-admin UI/API submission, real atomic operation/intent/native enqueue, a workspace-scoped
native queue and a separately started foreground worker. It preserves existing data/owner/API
credentials while explicit setup adds nullable legacy worker custody, a restricted worker role and
configuration-only virtual scenarios. API and worker are independent processes; stopped execution
leaves accepted jobs queued. No activity is preseeded.

Typed pause/target/policy rules, current actor grants, original intent and whole-config runtime
revision govern dispatch/publication. Known-key replay is durable; mounted-modal retry identity is
not reload-durable. No OCI credentials/calls, adoption, generic mutation actions or production worker
installation is implied. There are 21 schemas, 41 runtime modules, six application tables and the
same six migrations/17 assets. The application TOML still has 14 scalar keys; separate JSON holds
sandbox policy/private worker custody. Final tests and independent reviews are recorded in progress.
Cloud operator-pod/Vault/RBAC qualification remains the accepted separate infrastructure procedure.

## Activity/history read checkpoint

[Audit History's field/source guide](../reference/audit-history.md) documents the new scoped
read directory over existing immutable events. It shares a read-only repeatable snapshot helper
with Operations and returns safe category/actor/target/code projections, not raw JSON. No table,
migration, generic Retry, edit or export route is added; export remains planned MVP work.

Daily management and Activity & history/Application settings navigation now have separate roles.
Current simulated issues retain their state and explicitly require no action. Real future corrective
actions originate from higher-level tenancy/org/config/access context. Source/field shape is23
schemas/45 runtime modules with six tables/six migrations/17 assets and14 unchanged TOML keys;
final unit/PostgreSQL/browser and independent-review evidence follows the current gate run.
Cloud operator-pod/Vault/OKE qualification remains separate and its accepted procedure is unchanged.


## Instance-brand configuration releases

The accepted Atlas display identity uses the same `application.toml` configuration release path.
The public allowlisted branding view contains name/logo/icon only; authentication, database and
credential configuration remain private. Name/path changes to already provisioned assets require
validation plus a rolling process restart, not an application image rebuild. New raster assets
require coordinated provisioning into the same-origin public branding asset directory (bundled
image or reviewed read-only mount). No arbitrary filesystem path or remote image URL is accepted.
This adds no database columns/tables, no tenant identifier rename, no live settings-editor UI and
no hot reload. Local files/commands retain their OTM names.


## Audit export and organization extraction checkpoints

30 October2026. Audit History now has tested UTC date bounds and a guarded CSV export, with
server-side authority checks and immutable preparation evidence before disclosure. Forward
migration0007 adds only the allowed export event and scoped time/event index; no new table or
runtime grant is needed. A private local database backup precedes the laptop upgrade; unchanged
administrator/credential/configuration fingerprints verify state preservation. Disposable tests
continue to use separate Docker databases.

The reusable organization CSV/contracts/reconciliation/review modules and synthetic scenarios
are now in the production package. This completes domain extraction, not organization persistence
or deployment. The next organization vertical slice must wire trusted source/configuration,
snapshot receipt/idempotency, atomic publication, persisted recommendations/metadata history and
current-session authorization before enabling the approved Organization UI. Do not expose the
pure helper as a permissive publication endpoint or copy prototype success/actor shortcuts.

Both checkpoints retain complete-source unit coverage, real PostgreSQL/Playwright gates,
independent security/documentation/UI review and unchanged locked dependencies. Hosted CI,
protected GitHub master and whole-repository publication clearance remain separate work.

## Earlier organization workflow parity checkpoint

Migration0009 adds three registry/review tables and managed-person/registry-fence fields to the
existing snapshot foundation. [The current field guide/ER](../reference/organization-workflows.md)
maps actual fourteen-table scope, native queue handoff, simulated publication, local cancellation and
the explicit eight-table development reset. No application schema is precreated for unimplemented
full-OCI features. Required backend/frontend complete-source unit gates, disposable PG (including
restricted roles/rollback/uniqueness), actual built UI browser journeys and security/dependency
reviews must complete before a passing checkpoint is recorded. At that earlier source checkpoint validation was in progress; later local results are recorded in
development progress. No hosted CI/OKE/Vault/SSO or Git/publication clearance is implied.

## P2 guided onboarding checkpoint — 31 October2026

Create/import now have a [persisted simulated handoff and cleanup review](../reference/tenancy-onboarding.md), extending the organization parity foundation. Next is P3 baseline/override/drift implementation; real OCI SDK, Vault and identity-domain permission/activation qualification remain explicit gates. This adds no approval to publish or bypass quality checks.

## P2 whole-tenancy deletion — 31 October2026

[The tenancy-level deletion extension](../reference/tenancy-deletion.md) supports both types without new tables. Preserve per-person offboarding and whole-tenancy termination as distinct intents while sharing admission/native jobs/audit/provider boundaries. Real registered-child provider qualification remains pending.


## P3.1: baseline draft authoring

This section records the historical0011 draft-only checkpoint. The current publication/history
extension is [P3.2a below](#p32a-simulated-publication-and-history); its updated scopes do not relabel
the earlier test receipts.

This implementation checkpoint adds only read/save of one editable managed-OCI recipe. The new
[baseline authoring guide](../reference/baseline-authoring.md) maps all26content/draft/evidence
fields (including nested tags), the18columns of the new fifteenth application table,
otm_baseline_version, and immutable administrative before/after evidence. The [separate implemented ER](../architecture/diagrams/baseline-authoring-implemented.mmd) supplements the fourteen-table workflow foundation. Migration0011_baseline_drafts
follows0010_guided_onboarding; no other proposed baseline/overlay/binding/observation tables are
precreated. Organization settings and application.toml remain separate authorities.

The baseline table uses explicit policy/quota arrays, exact NUMERIC(20,4) money, structural currency,
fixed MONTHLY/OTM scope, static tag defaults, content hash, version/edit revision and reserved publication
provenance. Only one draft can be editable in a workspace. Workspace locking plus ID/revision checks
serialize changed edits; reconstructed content is checked against its canonical hash before reads,
edits or same-content no-op replay. No-op returns the current draft without extra audit/revision. A changed save
and baseline_draft_saved audit evidence commit atomically. Existing current-principal and scoped
browser guards apply; API privileges omit publication-column edits and draft DELETE/TRUNCATE.

The current checkpoint does not publish, choose a current pointer, apply/roll out to children, call
OCI or claim provider-valid policy/quota/currency. Publication preflight, semantic/provider currency
qualification, immutable published versions and subsequent assignments/bindings/drift remain staged
work. Reserved published_by/published_at columns and their SQL guards are not a publication workflow.
Existing tenancy flows must remain behaviorally intact.

The previously eight-table local organization test reset becomes an explicit nine-table set including
the baseline FK table. It deletes test drafts as well as organization/registry test rows, preserving
auth/session/Operations/audit history without CASCADE. This is the owner-only local test reset, not a
production cleanup endpoint. Every command must choose its instance directory. The current
code/schema compatibility upgrade covers both primary8443 and runbook8444 because the frontend
build is shared, while preserving all existing rows, settings and credentials. It must not invoke
this reset or substitute either saved organization's data; backup/upgrade evidence remains separate
from disposable automated tests.

P3.1 is validated locally: complete-source backend/frontend95% unit gates, migration constraints,
exact decimal/no-op/revision checks, restricted-role transaction/rollback/concurrency tests, API
boundary cases, generated contract/build parity, affected browser flows and independent reviews
have passed. The linked receipt records this candidate rather than relying on an earlier slice. Hosted CI/OKE,
real OCI/Vault, publication clearance and the full P3 milestone remain separate qualifications.


P3.1 local qualification, 2 November 2026: migration0011 and draft authoring are now validated and
installed in both saved local instances with all14previous application tables preserved. The
checkpoint receipt (private historical evidence; not distributed) records the final
1,083-case combined backend/PostgreSQL/browser run, separate95%unit gates and independent reviews. The one new table makes
15actual application tables; no publication, baseline assignment or OCI application is implemented.

### Statement-block UI refinement after P3.1

The user selected a single policy block and a single quota block, without per-statement Add/Remove
controls. Convert nonempty LF/CRLF/CR-separated lines to ordered array items only on explicit Save;
preserve each nonblank line's whitespace/order and retain existing item/count limits. The physical
JSONB arrays and API shape are unchanged; this is not another migration or TEXT/statement-row model.
Legacy embedded-newline items remain accepted by the backend and are not rewritten by reads or
opening the editor. Explicit Save normalizes the visible lines and can create a normal audited edit.

Keep the original P3.1 validation counts/receipt intact as historical evidence for its per-entry UI.
The revised frontend helper/editor passed201frontend units at97.48%complete-source coverage and
2actual HTTPS/PostgreSQL browser cases. Documentation, security and UI reviews pass. Backend publication/provider gates remain future work. See the [editor/storage contract](../reference/baseline-authoring.md#statement-block-editor-decision).

### Whole-unit baseline authoring after the block-editor refinement

The approved authoring rule now requires positive whole-unit monthly budgets, without cents. The
editor removes only zero-only decimal suffixes for display and validates digits-only new values;
SaveBaselineDraft.content independently rejects fractional amounts. Do not round a legacy value or
weaken the current revision/no-op/authority checks to make a save succeed.

Keep BaselineContent read/history/canonical handling and NUMERIC(20,4) unchanged. Previously saved
fractional recipes/audit evidence must remain readable/hash-valid, with no migration or background
rewrite. Saving such a draft later requires an explicitly chosen whole amount and normal before/after
audit. The physical schema and contract fields remain; the new command validator narrows authoring
semantics rather than altering retained precision. No provider/currency qualification is implied.

Add regression evidence for equivalent whole encodings, fractional-save rejection before writes,
zero/negative/bounds denial, display without zero-only suffixes, legacy read/hash/audit compatibility,
no rounding on open/cancel and explicit correction before Save. Validation passed904backend units
at96.3274%,203frontend units at97.49%and1,090combined backend/PostgreSQL/browser tests. Independent
reviews pass. Earlier foundation/block-editor receipts retain their historical scope.
[Current whole-unit behavior](../reference/baseline-authoring.md#whole-unit-budget-authoring).

### Raise policy/quota authoring lists to fifty

The user selected a separate1–50statement limit for each policy and quota array, rejecting51 while
retaining2000characters per item. Increase the editor's raw-block cap from42000to105000characters
and the Save endpoint's streamed body cap from256KiB to2MiB; keep both character/item and request-byte
bounds enforced. No SQL schema/migration, row-per-statement model or hash-format change is needed.
Tag/budget/concurrency/authority/audit rules are unchanged.

New unit/API/browser evidence must cover50accepted,51rejected, unchanged per-item length, nonblank
line conversion and large UTF8payloads within/above the new body cap. Earlier receipts/counts remain
historical for their20-item source scope. New bounds passed906backend units at96.3274%,205frontend units at97.49%and1,092combined
backend/PostgreSQL/browser tests, with independent reviews complete. No publication/provider gate
is waived. [Current list and body limits](../reference/baseline-authoring.md#fifty-statements-per-policyquota-list).


Actionable Operations navigation count, 2 November 2026: raw needs_attention alone is not actionable
work. attention_count remains a read-only projection over waiting/needs_attention organization
workflows with a matching current intent and stable person's pending-operation pointer, and a
supported guided handoff/review/retry or the current simulator's safe no-effect cancellation.
Read-only inspection diagnostics and unsupported/orphaned work remain in history at count0. Do not
delete, dismiss, force-success or rewrite records merely to clear a badge. The counter is a workspace
action hint, not command authorization or a guarantee a retry succeeds. Existing live authority/
context guards still apply. No new table, state, acknowledgment, migration or generic retry control
is introduced. See the [Operations guide](../reference/operations.md) for capabilities.


## P3.2a: simulated publication and history

This records the validated0012 checkpoint. The current0013 extension is
[P3.2b below](#p32b-current-for-new-and-onboarding-pins); its new pointer/pin behavior supersedes the
original no-pointer scope without changing earlier receipts.

This bounded checkpoint adds publication/history before create/import baseline pinning. It reuses
15application tables, adding only published_by_name and publication_mode to otm_baseline_version
through forward migration0012. The [baseline guide](../reference/baseline-authoring.md) and
[ER](../architecture/diagrams/baseline-authoring-implemented.mmd) map20columns and10DTOs/55effective fields.
A migration precondition stops on pre-existing manual publications for operator review; no old
publication is silently qualified or given invented publisher metadata.

The version list includes the sole editable draft and SQL-paged immutable published history,
10/25/50 publications per page, with exact UUID read-only detail and original publication actor/time.
Latest published is independent of pagination and does not mean current for new tenancies. New
drafts copy latest content in the editor and submit its exact parent UUID; workspace-locked server
checks reject a stale parent, while existing drafts retain their original parent. Editing/publication
keeps recipe hashes and original creator provenance; publication advances edit revision.

Publication is an explicit exact-ID/revision command with live authorization and same-transaction
full snapshot audit. Optional BaselineQualifier defaults to unavailable, never an automatic simulator;
local composition explicitly injects structural whole-unit USD qualification. Simulated mode and
baseline-structure-simulated-1 remain visible in immutable evidence, not claims of OCI grammar or
billing/provider qualification. Original-request replay does not duplicate publication/audit and
still requires current authority and an available qualifier. Runtime API publication-column UPDATE
is narrow; published mutation and ordinary DELETE/TRUNCATE stay blocked. The nine-table owner-only
local test reset also destroys test publications, without becoming an Unpublish/Delete UI action.

No current pointer, assignment, create/import pinning, effective override, rollout, provider-object
binding, drift collection/repair or OCI write is added. Protected access composition and real
currency/region/provider validation remain qualification gates. Full P3 and deployment/SSO/Vault/
Git publication approval are separate. Existing flows and both saved instances must be preserved;
P3.2a upgrades are complete on8443and8444 with private backups and unchanged old-column
fingerprints for all15application tables; both servers and restricted endpoints are healthy.

Validation passes:920backend units96.3838%,216frontend units97.67% and1,114combined
backend/PostgreSQL/HTTPS-browser cases, with documentation/security/UI reviews complete. Required
cases include exact replay/live revocation, concurrent publication/edits, failed-audit rollback,
stale parent, exact selection/pagination/workspace isolation, corrupt content/actor evidence,
qualifier absent/rejection, immutable published rows, migration precondition and narrow installed
API-role grants. Both primary8443 and parallel8444 compatibility upgrades require private backups
and preservation evidence; no reset or human-data substitution is part of qualification.

Final P3.2a receipt (private historical evidence; not distributed) records results and limits.


## P3.2b: current-for-new and onboarding pins

This is the historical validated0013 checkpoint. The user subsequently removed older-version
selection; [the0014 correction below](#latest-publication-only-default-correction) supersedes
its selectable default/pointer while preserving original receipts and accepted operation pins.

This checkpoint connects validated local publication/history to new create/import admission. It adds
only two nullable columns through0013_baseline_pinning: org_workspace.current_baseline_id and
otm_tenancy.baseline_version_id, both scoped to existing published baseline rows. There remain15tables
and20baseline columns. All old rows retain null defaults/pins; the upgrade performs no automatic
selection, assignment, publication or historical intent rewrite. An operator can explicitly choose
Use for new for an existing publication. See the [current field map](../reference/baseline-authoring.md)
and [ER](../architecture/diagrams/baseline-authoring-implemented.mmd).

Publish now commits its immutable publication, current-for-new pointer, registry_revision+1 and typed
audit together. Existing-publish replay never changes the pointer. Explicit selection requires an
expected prior pointer and live authorization/dependency availability; already-current selection is
a no-op. The new baseline_default_changed audit contains the complete target snapshot and prior UUID.
Configuration contracts total12DTOs/61effective fields; the current/latest distinction is explicit.
The new draft still derives from latest published content, independently of selected older defaults.

New create/import uses the same workspace lock and registry-context fence, captures the complete
published BaselineVersion in OrganizationIntent.baseline and registers its UUID on the pending
tenancy. The public OrganizationAction remains unchanged to preserve request-digest compatibility.
No selected default means no new operation/audit/registry/job writes. Existing request replay returns
the original operation after live authority and before new default/stale-preview checks. Other
membership, cleanup and application-only workflows retain independent guards.

Through activation waits and retries, worker checks the exact frozen published snapshot/hash/mode,
not current/latest. A subsequent publication does not retarget or invalidate an otherwise valid pin;
live administrator/parent/runtime-policy checks remain enforced. Legacy intents have no pin and keep
old behavior. OnboardingView.baseline is read-only (22fields;52across six onboarding DTOs), and the
registry exposes TenancyView.baseline_version_id. UI labels state selected/pinned simulated recipe,
not applied or verified baseline. No baseline apply/read-back capability, configuration revision/
override, binding, rollout or real OCI adapter is implemented by this slice.

Validation passes:934backend units96.4141%,222frontend units97.38% and1,135combined
backend/PostgreSQL/HTTPS-browser cases. Independent reviews pass. Both saved instances are upgraded
to0013 with private backups, unchanged old-column fingerprints for15tables and no default/pin
backfill. Required checks include null-preserving migration,
explicit/default publication transaction rollback, stale selection/preview, old publish replay not
moving current, create/import wait→new publication→old-pin resume, replay without duplication,
legacy operation/tenancy compatibility, no-default rejection before writes, foreign/corrupt pins,
live revocation and preserved application state. Both saved instances require explicit-directory
private backup and old-column preservation evidence; no reset or human-data substitution is part of
qualification. P3.2a receipts retain their original publication-only source scope.

Final P3.2b receipt (private historical evidence; not distributed) records scope and verification.


## Latest-publication-only default correction

New create/import always uses the latest published baseline in its workspace, ordered by version
number descending. History remains read-only, with no choice of an older default. Remove the
SelectBaseline command/route and Use for new controls. Preserve org_workspace.current_baseline_id,
its scoped FK and published-target trigger as deprecated historical metadata; new selection ignores
it and publication no longer writes it. Forward0014 changes no schema or stored selection value and
only increments registry_revision once to invalidate old previews. Publication continues to increment that revision atomically with
its immutable row/audit. No new table, recipe/hash/money-format change or historical audit rewrite
is introduced;15application tables and20baseline columns remain.

The latest lookup also covers existing publications immediately: no adoption/select command or
additional publication is required. No-publication still blocks new create/import before writes.
New admission freezes the complete latest published BaselineVersion once and stores its UUID in
otm_tenancy.baseline_version_id. Existing tenancy pins and immutable intents survive unchanged,
including older accepted pins and legacy nulls. Resume/retry validates the exact stored publication
and registry pin, never reselects latest. Original request-key compatibility and live authorization/
parent/policy checks remain. Historical baseline_default_changed events remain readable evidence,
not an active default authority. Configuration contracts total11DTOs/58effective fields, removing
SelectBaseline and BaselineDirectory.current while retaining the historical selection-evidence reader.
Required-access checks remain separate from future baseline apply.

Correction validation and both saved-instance upgrades pass:929backend units96.4001%,
219frontend units97.38%,1,130combined backend/PostgreSQL/HTTPS-browser cases and independent
reviews. Private backups preserve all15tables except the verified one-time registry revision bump.
Correction receipt (private historical evidence; not distributed). Prove automatic latest for pre-existing
publications, absent selector API/UI, publication/preview concurrency and rollback, old request replay,
wait→new publication→original-pin resume, preserved old/null pins and migration preview invalidation.
Use private backups and old-column/row preservation checks for both saved installations; no reset,
seeding, reassignment or real OCI operation is part of qualification. Earlier0013 receipts stay
historical. [Current baseline field map](../reference/baseline-authoring.md).


## Baseline-only configuration updates

The implemented baseline-only slice adds context-aware exact version links and individual/fleet asynchronous
baseline updates while preserving latest-only new-admission selection. Forward0015 adds only three
nullable existing-tenancy fields: verified_baseline_version_id, configuration_verified_at and
configuration_observation. There remain15application tables and20baseline columns. No full
configuration revision, override, persisted plan/target, binding or observation-history table is
precreated. See the [new complete source/field guide](../reference/configuration-updates.md)
and [implemented relationship map](../architecture/diagrams/configuration-updates-implemented.mmd).

Preview/Start freezes latest baseline and complete eligible active candidate membership, including
all blockers. Pending onboarding keeps its original pin. All exceptions must clear before any
acceptance writes; no ready-subset shortcut or browser-selected target list. The workspace/revision/
preview hash and durable request UUID fence stale or repeated commands. Desired pins/reservations,
one configuration_update operation, immutable full intent and native enqueue commit atomically.
Later publication cannot retarget accepted work; queued receipt is not verified completion.

Execution stays pure local simulation, committing independently per child so a failed child cannot
undo prior successes. The explicit facade models four managed category records and separate apply/
read paths with deterministic fake IDs/hash validation. Partial state persists without advancing
last complete verification; all four successful comparisons are required for last-verified baseline/
time. Existing onboarding verification remains separate. Verified children are skipped on retry;
matching persisted categories are read/validated and their writes skipped only when exact desired
objects still match. This preserves successful prefixes without bypassing fresh readback. One unchanged accepted batch owns
its original baseline/targets; queued Start/Retry receipts use HTTP202, while receipt replay in another
existing state uses HTTP200. Retry requires responsible current authority and supported recovery,
adds immutable evidence and reuses the operation identity. No real OCI/network adapter can be
substituted into these database transactions without split dispatch/reconciliation qualification.

UI offers Configuration and active-tenancy update context, frozen confirmation/exception counts,
read-only recipe inspection, safe return links, per-child progress and contextual retry. Exact
version-number/ID links distinguish selected and last fully verified simulated baselines. History
remains in Operations/Audit; no generic Operations retry or forced badge-clearing action is added.
New contracts comprise11DTOs/57fields, with reused baseline/actor/receipt models mapped separately.

Validation passes:960backend units96.4005%,229frontend units97.26%,1,171combined
backend/PostgreSQL/HTTPS-browser cases with no failures/errors/skips, plus a focused time-advanced
PostgreSQL verification-preservation test. Source/docs/contracts and independent documentation,
security and actual-responsive-visual reviews pass. Both saved installations are0015 after private
backups; all existing columns/rows across15application tables preserve exact fingerprints. No reset,
seed, Git publication or real OCI effect occurred. Full P3, overrides and live provider qualification
remain separate milestones. Receipt (private historical evidence; not distributed)
and [manual guide](../how-to/baseline-update-runbook.md).


### Baseline presentation and concurrent-update qualification

The follow-up uses existing storage for friendly audit resources, inventory latest/completed reads,
compact Status and local bulk-result acknowledgment. Completed individual panels and successful
Refresh controls are removed. No new schema or queue is introduced. Real PostgreSQL same/different-
key starts and concurrent duplicate worker invocations prove one operation/job and one verification
per child.964backend units96.4268%,232frontend97.21%,1,178combined tests and independent reviews
pass; both saved instances are updated with all existing data preserved. This does not implement
overrides, cost columns or live OCI calls.
Receipt (private historical evidence; not distributed).


## Authored overrides and staged-plan local qualification

The qualified local implementation uses the accepted grouping from chapters 03/10: immutable
otm_tenancy_configuration, explicit owner-scoped otm_configuration_plan and closed proposal/review
otm_configuration_plan_target. Forward 0016 adds 14 + 11 + 10 columns plus desired/last-verified configuration
heads on existing registry rows, for 18 source tables and unchanged 20 baseline columns. Legacy data/
intents/heads are preserved without fabricated revision backfill. [Complete current mapping](../reference/tenancy-overrides.md)
and [implemented ER](../architecture/diagrams/tenancy-overrides-implemented.mmd) supersede the old baseline-only
field inventory while keeping its receipts historical.

Implement and qualify independent NULL/inherit or full 1–50 statement lists and positive whole budget,
with no tag/currency/scope/required-access override. A same-baseline edit accepts a new immutable
configuration ID and separate verification obligation. The assigned editor requires exact current
baseline/tenancy/configuration context; background/latest publication never silently changes it.
One textarea per statement category preserves existing exact text boundaries and splits changed
blocks on hard line endings, not per-statement editor widgets or grammar inference.

Baseline upgrade plans capture complete candidate proposals/hash and target publication. Staged
full-list choices are local/audited only. All required categories and all batch exceptions must clear
before any desired head/operation/job is accepted; no ready-subset shortcut. Changed source/target/
registry membership makes a plan stale rather than reusing content-free approval. Plan URLs reload
same owner context; uncertain staged-save recovery reads the saved revision instead of inventing
request-key idempotence. Whole acceptance commits configurations/heads/intent/plan links/native job
atomically; child execution, partial state and fresh full verification remain independent afterward.

The qualified source has 10 override DTOs with 55 fields, 12 rollout DTOs with 76 fields and 59 schema
artifacts. Unit, disposable PostgreSQL, native worker, HTTP/browser, independent security/UI/documentation
and saved-runtime upgrade gates pass. Required cases
include full-list/no-tags/whole-money boundaries, same-baseline desired/verified separation, stale
assigned editor/plan/candidate set, all-conflicts gate, immutable accepted inserts/updates/deletes,
rollback/replay and exact legacy original JSON/digest compatibility. Prove narrow runtime roles and
private caches, preserve all existing values with backups on both saved installations, and never
reset/seed human data to make qualification easier. The owner-only test reset adds three tables to
its prior 9, for 12. Real required-policy rendering/OCI qualification and remaining P3 stay separate.


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


## Qualified local refinement: shared access and applied onboarding baseline

3 November 2026 · Local simulation qualified and installed in both saved instances. Keep one bounded slice across the existing
organization-action worker, guided steps, configuration facade and tenancy detail. Existing-
compartment selection, exact identity-removal receipt/steps and onboarding version 2 reuse existing
tables. Migration 0017 changes step allowlists only; there are still 18 application tables.

Required checks include legacy digest/intent compatibility, both compartment choices and wrong-scope
rejection, removal receipt mismatch/rollback plus manual-resource boundary, baseline pin retained
across publication during handoff, four-category apply/readback and partial retry, fresh access
verification after root configuration, temporary-user preservation on failure, and the actual
responsive UI/keyboard flows. New unit code enters complete-source 95% gates; disposable PostgreSQL
checks separately prove atomicity. Saved instances require private backups and preservation checks
before an approved forward upgrade; no reset/backfill is part of the slice.

[Runtime mapping](../reference/tenancy-onboarding.md) ·
[Manual review](../how-to/tenancy-refinements-runbook.md). Final source, database/native-worker, browser and independent reviews pass. Both saved-instance
upgrades and runtime checks also pass, with existing data preserved.


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


## Qualified local slice: configuration drift visibility

3 November 2026 · Local implementation qualified and installed in both saved instances. Explicit one-child/fleet commands enqueue
read-only checks through the existing native worker; one 13-column immutable check table brings the
qualified local schema to 19 application tables. Do not couple this slice to repair, daily infrastructure,
notifications or full provider qualification. Existing assignments/history and worker/queue authority
remain intact.

Required checks cover complete matching/missing/different, authorized absence versus unknown,
conflicting bindings, legacy/uninitialized inventory, assigned override content versus newer
publication, failed/partial retention, current-context resolution, generation supersession, monotonic
acquisition/replayed dispatch, stale freshness, live authorization and no provider writes/head
mutation. Actual PostgreSQL proves sealed check/audit/step/enqueue atomicity; unit gates separately
measure full source. Use only disposable synthetic fixtures for external-change scenarios; no local
operator observation-editing CLI is included. Both saved instances are upgraded with private 0600 backups, unchanged fingerprints of all
old columns/rows across the 18 existing tables, and matching per-instance qualified frontend
snapshots. The new check table brings the inventory to 19; baselines, pins and history are preserved.

[Runtime field guide](../reference/configuration-drift.md) ·
[Manual review](../how-to/configuration-drift-runbook.md).


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


## Qualified OCI-independent slice: audited administrator takeover

4 November 2026 · Application capability qualified locally and installed in both saved instances. The user chose permanent application
responsibility takeover under accepted D50 while a parent tenancy is unavailable, without adding
temporary simulation controls. This is workload responsibility, not automation-key handoff or
provider credential transfer. Use existing operation head/revision and audit, with 0019 extending
only the audit-kind allowlist (19 application tables unchanged).

Required qualification covers two-actor compare/revision claims, no view mutation, actor-scoped
request replay after later claims, stale/self/wrong-scope/state/policy denial, immutable original
provider intent/mailbox/owner/pin/progress, replacement authority after creator revocation, claimant
revoke/regrant blocking, actual transactional audit failure rollback and native resumed execution.
Real HTTPS/browser tests must distinguish creator/current responsible, confirmation/cancel/focus,
conflict feedback and current-responsible-only setup actions. No second admin is invented in saved
installations; synthetic positive cases use disposable authorized fixtures.

[Field guide](../reference/responsibility.md) ·
[Manual review](../how-to/responsibility-runbook.md). All gates and both saved-instance preservation checks pass. Notifications/packaging and real OCI qualification are later choices, not started here.


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


## Required email-environment gate in both release paths — 4 November 2026

Accepted requirement; implementation/qualification pending. Apply
[chapter21](21-environment-email-policy.md) independently in the application-release and configuration-
release pipelines. Each validates against a trusted expected environment separate from candidate
settings. Production must reject test override/bypass; staging must require the explicit test
destination before email/OCI delivery credentials or deployment. Neither pipeline may trust that
the other already checked, and a settings-only change cannot bypass the policy.

Use an offline standalone validator and negative policy tests before hosted CI exists. The app path
validates the candidate schema/image/settings; the config path validates with the deployed compatible
application while preserving its image digest and existing deployment lock. API/worker policy
fingerprints must agree before external work is enabled. At dispatch, frozen route/policy evidence
is checked again; changed profile/destination blocks old queued work, without silent retargeting.

No GitHub Actions, repository publication, delivery/OCI credentials or deployment is authorized by
this documentation work. Current schema/legacy intent and responsibility-proof hashes must remain
compatible; configuration changes cannot rewrite employee/SSO keys or prior activation mailbox.
Exact runtime fields and actual gate results will follow settled source contracts.


## Email source/release checkpoint — 4 November 2026

Local qualification and saved-instance installation passed; see the final checkpoint below. The standalone otm-validate-release gate now implements both
--release-kind application and configuration with --expected-environment from the trusted target.
It requires no SMTP/Vault/OCI credentials, rejects mismatched/unsafe profiles, and emits only fixed
diagnostics or nonsecret hashes/metadata. Both deployment paths must call it independently before
credentials/apply; hosted CI/OKE workflows are not installed.

Settings define environment, optional testing override and 8 notification fields, with strict
production no-testing and staged test-destination requirements. API/worker composition shares
routing/profile/origin. Fresh worker checks block changed settings until coordinated restart; no
hot-reload/recall guarantee is made. [Runtime fields](../reference/lifecycle-email.md) ·
[Settings dictionary](../reference/application-settings.md).

The source adds one 15-column outbox through 0020 (20 tables total). Default packaged local settings
remain offline/disabled; explicit per-instance loopback capture requires capture@otm.test and matching
SMTP/UI ports. The digest-pinned Mailpit setup has no relay configured, ordinary bridge networking
and loopback publication; it is not an egress firewall. Saved upgrades/backups/preservation and all
source-unit/PG/native-worker/SMTP/browser reviews passed, as recorded in the final local checkpoint.


### Lifecycle email final local qualification — 4 November 2026

The final validation record (private historical evidence; not distributed) supersedes this feature's source-only pending checkpoints: 1,421 full-suite tests pass, both unit-only coverage gates exceed 95%, reviews are complete, and both saved local instances were upgraded with all existing rows preserved. The release-check command covers both application and configuration paths. Hosted CI/OKE deployment, production Vault/SMTP and live OCI contacts remain separately unqualified; the feature is not a claim of complete V1 delivery.


## Deferred build slice: daily drift detection in staging/Kubernetes

Accepted 5 November 2026. Implement the drift-detection CronJob only when the staging environment
and Kubernetes deployment are available. No local CronJob, polling daemon, demo scheduler or
simulator-control UI is part of the current freshness refinement. The accepted daily read-only
requirement remains; existing session-cleanup manifests and native task retry scheduling are
separate and unchanged.

The later CronJob should perform authorized noninteractive daily read-check admission and then
exit, using the existing durable operation/native worker/evidence path. Qualify the machine
authority, trusted environment/scope and schedule-occurrence idempotency rather than reusing a
browser session or bypassing current admission. Missed/overlapping/restarted jobs must not cause
duplicate admission, provider writes, repair or new mail. Stage acceptance must prove daily enqueue,
worker execution, coverage/freshness, stale visibility after a missed run, and current-context
resolution with actual Kubernetes behavior. Exact deployment manifests/entry point are future work;
none is created or deployed by this checkpoint.


The 5 November local freshness qualification (private historical evidence; not distributed) completes the display/counter/refetch refinement only. Daily scheduled drift admission remains deferred to staging/Kubernetes; it is not implemented by the manual read-check UI or its progress polling.

## Cost visibility milestone — 5 November 2026

The [current-month read implementation](../reference/cost-visibility.md) follows the approved next
milestone: immutable collection/storage, exact read facade, native bounded retries, unified inventory
UI and D48 email episodes. All related slices share one milestone branch/PR under the
[checkpoint policy](../how-to/github-checkpoints.md). Daily cost/drift admission remains deferred to
staging/Kubernetes alongside live OCI qualification; current-month history is internal evidence, not
a historical reporting product.

Local financial gates and both preserved-preview upgrades are qualified in the
[5 November cost checkpoint](../history/cost-visibility-checkpoint-2026-11-05.md). Hosted results
remain bound to each checked commit; scheduling/live-provider qualification remains deferred.


## Required-user presence foundation — 6 November 2026

The [internal implemented boundary and full field map](../reference/required-user-presence.md)
separates automation/recovery subject identity, inspecting authority and returned presence evidence.
Only Present/Missing/Unknown are implemented; no privilege, signer, console or recovery-readiness
qualification follows. These are typed transport models, not new database tables or established
foreign keys. ER diagrams and current persisted schema are unchanged. Current onboarding does not
yet retain permanent user bindings; verified binding capture and live-head checks must precede
worker/UI composition. There is no guessed backfill, API route, schedule, repair, secret retrieval
or saved-instance change. The broader proposed access model above remains future work.


## Implemented onboarding identity capture — 6 November 2026

Newly accepted create/import intents now use onboarding version 3. After baseline application and
fresh access probes, a required capture step retains exact automation/recovery domain, SCIM and OCI
identifiers in existing `otm_operation_step.last_outcome` and immutable `audit_event.data` before
retiring temporary access. Failed capture blocks retirement. Historical accepted version 1/2/absent
intents keep their graphs; no name-based adoption or historical binding backfill occurs.

See the [implemented field/storage map](../reference/tenancy-onboarding.md#permanent-user-capture--6-november-2026).
Migration 0022 only expands the existing step constraint. No table, column, credential store or new
ER relationship is added. This supersedes earlier statements that onboarding retains no permanent
identifiers, while keeping the proposed canonical managed-object binding, access-assignment heads,
current-generation checks and full access-health model as future implementation. Capture evidence
alone must not authorize repair, disclosure or live operations. Saved previews are not changed.
Live qualification remains Pending in the [manual manifest](../how-to/real-oci-test-manifest.md).


## Implemented canonical identity bindings — 6 November 2026

Migration 0023 adds the first 18-column subset of `otm_managed_object_binding`: an observed domain
reference and managed automation/recovery users from fresh typed onboarding capture. Same-child
foreign keys, immutable capture/operation provenance, verified setup prerequisites, unique active
identities and atomic three-row persistence precede temporary cleanup. Verified termination
initiation retires management while retaining history. No historical capture is automatically adopted.

The [complete implemented field map](../reference/managed-object-bindings.md) and
[rendered ER](../architecture/diagrams/managed-identities-implemented.svg) distinguish physical fields
from the fuller proposed model above. This supersedes earlier notes that canonical binding rows are
entirely future work. Configuration objects keep their existing storage; future kinds require their
own handlers/migrations. Access assignments, context/credential heads, current-generation checks,
replacement and Required users UI remain future integration. An active binding is an identity mapping,
not healthy access or authority to repair/disclose credentials. Saved previews remain unchanged.
