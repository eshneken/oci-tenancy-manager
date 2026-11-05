# 06: production operations, database and development handoff

28 October 2026 | Chapter18 approved; whole-package final review pending | D51/D52 recovery objectives and D53 test/merge gates accepted; no deployment authorized

[Design hub](README.md) · Existing delivery plan (private historical evidence; not distributed) ·
[Simple V1 restore and credential resolution](17-recovery-and-release.md) ·
[Database/CI build order](18-database-ci-and-build-order.md)

## Current proposed data-model catch-up — 21 October 2026

[Chapter11](11-production-data-model.md#recurring-work-platform-recovery-and-database-operations)
maps scheduling, deadlines, recovery epoch/release evidence, runtime policy and backup references
to workspace, operation/step and immutable audit storage. Infrastructure/queue state retain their
own authorities. Actual migration DDL, service privileges, restore and performance tests remain open.


## Hosting and infrastructure

Retain OKE and OCI Database with PostgreSQL, built from Terraform and declarative Kubernetes
configuration. Hosting is a dedicated compartment of a configurable tenancy, not necessarily the
organization parent. Explicitly design private network paths, DNS/TLS/ingress, identity federation,
image registry, secrets/KMS, telemetry and admin access. No VM may enable IMDSv1.
Define dev/simulator, integration, staging/pilot and production boundaries, allowed live credentials
and disposable targets. Terraform manages hosting; application handlers manage bound child objects.

## Database production design

Review the ten-table prototype before proposing additions. Use Alembic expand/contract migrations,
separate migration ownership and least-privilege runtime access with authenticated connections.
Add worker/export roles only when an actual permission difference warrants them.
Specify TLS/certificate validation, private networking, encryption/key ownership, parameterized
queries, row/workspace isolation, immutable audit protections and safe retention/export policies.
No application/reset endpoint may drop/truncate a production workspace.

Choose indexes from real reads/writes and EXPLAIN evidence, not blanket JSONB indexing. Candidate
paths include organization version/person/manager/LOB reads; active tenancy owner/member uniqueness;
operation/step tenancy+state and due-work lookup; credential rotation deadlines; observations by
entity/time; deduplication/idempotency keys. Validate FK indexes, write amplification, autovacuum,
query timeouts, lock contention, pool limits across API/worker replicas, queue connections and
managed-service privileges/extensions. State scale/history assumptions and benchmark realistic feeds,
fleet scans and operation bursts before selecting sizes or partitioning. Indefinite history is not
permission to ignore growth, but premature sharding/read replicas are not assumed requirements.

## Backups, restore and recovery

Design provider automatic backups/PITR, retention, optional regional copies and periodic restore
exercises. D51 accepts 15-minute RPO/4-hour RTO engineering targets; D52 limits these to in-region
recovery in V1. Measure them against the selected service and external dependencies. A restored database does not roll back OCI/Vault, grants, emails or IAM
writes. D12 requires recovery mode, fencing normal mutations, reconciliation and administrator
release; overdue credential work must remain urgent. Document external recovery evidence, new
DB endpoint/network cutover, schema/queue compatibility, secrets, unknown effects and drill criteria.

Oracle's [PostgreSQL PITR documentation](https://docs.oracle.com/en-us/iaas/Content/postgresql/point-time-recovery.htm)
says a point-in-time restore creates a new DB system. Plan endpoint/network cutover and validation,
not an assumed in-place rewind. This is documented capability, not an executed restore qualification.

## CI/CD and operational acceptance

Application and nonsecret settings releases use [separate deployment paths](18-database-ci-and-build-order.md#application-and-configuration-deployment-paths): configuration updates reuse the deployed image, validate against its schema and roll consumers without an image rebuild. Both retain all required test/merge gates.

Define protected shared repository, review ownership, reproducible locked toolchains, formatting,
type/lint/domain/PostgreSQL/facade-contract/UI tests, migration and generated-client checks, image
scanning/signing, immutable builds and Terraform validation/plan. Protect environment credentials;
PR jobs do not receive production mutation access. Build once/promote; gate deploy and schema/job
compatibility, graceful worker drain and readiness. Rollback of application image is different from
irreversible schema or provider changes. Production release needs smoke tests, alerts and runbooks.

## Development structure recommendation, pending final contracts

Use one modular repository and a named integration/schema/contract owner. Start serially with
shared DTOs, migrations, operation state, facade errors and test fixtures. Then independent lanes
can implement frontend, real/simulated adapters, configuration handlers and platform delivery against
reviewed interfaces. Merge small vertical slices with shared contract tests; avoid multiple branches
independently redefining states, tables or migrations.

One engineer driving Codex is a valid default at this scale; add engineers only to bounded work
packages with clear inputs/outputs and CI evidence. Multiple Codex contexts may help even with one
human, but concurrency does not remove review/integration work. Do not promise a calendar speedup
before a first vertical slice establishes actual throughput. Final work-package lane count, staffing,
branch ownership, merge order and development milestones are C6 outputs, not prerequisites for
this design pass. No new microservices are proposed for parallelism.

## Email integration qualification — D47 scope

V1 operational notifications use email only; Slack is deferred. C6 must choose an organization-
approved delivery service, sender/domain and environment-specific recipients, qualify transport
credentials or workload identity, private/egress network access and limits, and reference secrets
without exposing them in Terraform state, message payloads or logs. The channel choice does not
select an OCI mail API/SMTP feature or authorize real sends in local/CI tests.

Qualify provider acceptance versus actual delivery evidence, duplicate-submission protection,
partial-recipient response, timeout/reconciliation, bounce handling and durable correlation after
restore. Dev/CI use the simulator; any live pilot uses explicitly approved test recipients. Delivery
outage/backlog health needs independent operator monitoring because the broken email service cannot
be its own sole alert path. Use existing outbox/audit storage; no separate delivery microservice or
Slack fallback is introduced. See [the delivery contract](15-collection-and-operational-events.md#d47-delivery-contract-email-in-v1).

## C6 working plan — 25 October 2026

The [checked C5 contract pack](16-c5-contract-review.md) is now available. The following is a concrete
engineering proposal for review, not an approved deployment. D51/D52 below adopt the recovery
objectives and scope; other unselected platform details remain proposals. Do not infer provider
capabilities from a target number.

### Environment and deployment boundaries

| Environment | Data and credentials | Permitted execution | Exit evidence |
|---|---|---|---|
| Laptop / CI | Synthetic or approved local feed data; simulated OCI/Vault/email | Local organization logic, disposable PostgreSQL, facade failure injection | Repeatable setup, schema/model parity, crash/race and UI checks |
| Integration | Isolated app/DB; approved disposable targets only | Runner/managed-PostgreSQL integration and explicitly authorized adapter probes | Same-transaction enqueue, actual service privileges, safe secret handling |
| Staging / pilot | Separate hosting configuration, DB and scoped secrets; restricted real children | Reviewed create/import/config/access/cost scenarios; approved email test recipients | Capability matrix, observed limits, rollback/restore drill and operator signoff |
| Production | Production DB, secrets and SSO entitlement; registered organization targets | Reviewed V1 operations behind all normal guards | Release evidence, monitoring, recovery ownership and runbooks |

Propose one repository, one modular Python service image, an API deployment and separate worker
process roles. Use the same immutable image digest for those roles; no per-feature microservices.
Serve the responsive frontend as a separately built immutable asset artifact. Kubernetes CronJobs
only trigger due work; occurrence uniqueness and database transactions remain authoritative even if
Kubernetes duplicates a trigger. Reserve worker capacity for due credential rotation/recovery so a
fleet scan cannot starve it. Exact runner queues, replicas, pod budgets and resource sizes require
qualification and load evidence; this proposal does not claim a runner feature is already tested.

Terraform defines hosting compartment resources, OKE, private PostgreSQL/networking, registry,
Vault references, ingress/DNS/TLS and telemetry access boundaries. Environment inputs distinguish
hosting, parent and child identity contexts. Do not put child resource reconciliation into Terraform
or child credentials into ordinary variables/state. Runtime secrets resolve through authorized
references. Protect remote state, state access and provider authentication independently. Disable
IMDSv1 on every node/VM definition. No real provisioning or cluster access is part of this checkpoint.

### Database roles and access

| Role | Intended authority | Explicit restriction / validation |
|---|---|---|
| Migration owner | Reviewed schema migration and grants | Used only by controlled deployment; never the API login or normal worker |
| API runtime | Authorized reads and domain commands/atomic acceptance | No DDL, owner/superuser rights, audit rewrite or arbitrary SQL endpoint |
| Worker runtime | Scoped operation claim/publication, managed projections, atomic continuation | No DDL or historical intent/audit rewrite; providers only through facade |
| Read/export | Bounded administrator export and inspection | Read only; sensitive tables/columns require separate views/entitlement |
| Independent recovery operator | Service restore/cutover and reviewed recovery controls | Not a normal application privilege or an automatic app recovery bypass |

The role rows describe capabilities; they do not require a separate DB login for every process.
Start with migration/runtime separation and add logins for actual permission differences.
Use separate migration ownership from table writers and explicitly test effective grants rather than
trusting role names. API/worker append audit rows via reviewed insert authority and cannot update/delete
them. Immutable version/evidence tables receive equivalent restrictions. Roles still need narrowly
scoped operational updates, not blanket write rights to every table. PostgreSQL privileges alone do
not enforce administrator action policy: service commands must apply current SSO/workspace/target
checks, and queries must use scoped keys/FKs. RLS is an optional defense to qualify, not an invented
requirement or assumed substitute for those checks. A privileged DBA remains outside the ordinary
immutability guarantee; provider security/audit controls govern that administrative path.

Private validated TLS connections, bound query parameters and secrets references are required.
Configure pool budgets across **all** API/worker replicas, runner connections, migrations and reserved
operator capacity against the qualified service connection limit. Add statement/lock/idle-transaction
timeouts per role after integration measurements. Keep network calls outside transactions. Prove the
chosen runner's enqueue participates in the same PostgreSQL transaction as operation/audit acceptance;
if it cannot, stop and review D2 integration rather than adding an unreviewed second queue.

### Physical schema and query acceptance

One integration owner controls migration ordering and generated application contracts. Start from
the existing 10 tables, then implement the reviewed 18 additions through incremental Alembic migrations.
Map model fields, safe JSON schemas, scoped FKs, uniqueness and deletion/retention rules before DDL.
The existing ER diagram labels remain proposed until those migrations and constraint tests exist.

| Read/write path | Candidate physical access path | Evidence required before acceptance |
|---|---|---|
| Current organization and hierarchy | Workspace/current-version plus stable person key; manager/LOB predicates | Representative feed/reorg plans; no repeated hierarchy reconstruction per dashboard row |
| Unified Tenancies list | Workspace/active registry, association counts, selected finance/config joins | Paginated stable sort plans; no N+1 OCI requests or per-row DB round trips |
| Independent Actual/Budget sort | Qualified selected observation's `actual_spend` or `observed_budget_amount`, stable tenancy-ID tie | Null last in either direction; pending desired amount never sorted as observed |
| Finance selection | Collection/tenancy scope, binding/context/policy/cycle and source/capture ordering | Late-read/partial/obsolete-source controls reproduced in SQL under concurrency |
| Jobs and rotation deadlines | Existing runner indexes, operation due/state and credential deadline predicates | Due-work EXPLAIN, fleet scan plus urgent rotation contention, replica pool limits |
| Registry/association correctness | Same-workspace FKs, active relationship uniqueness and FK-side indexes | Conflicting owner/member writes and cross-workspace failures roll back atomically |
| One initial incident/email intent | Audit command/source-event keys and outbox event/channel uniqueness | Concurrent detections, retry exhaustion and takeover cannot duplicate initial notice |
| Audit/export and evidence | Workspace/target/time keyset pagination, explicit JSON-path indexes only where queried | Bounded export memory, retained-history plans and no whole-table JSON indexing by default |

At roughly 250 tenancies, correct bounded queries and constraints matter more than partitioning.
Use representative retained-history volumes and operation bursts in addition to fleet size; a
250-row seed alone cannot qualify indefinite audit growth. Record EXPLAIN (ANALYZE, BUFFERS) results
and write/lock overhead in disposable environments. Track autovacuum/statistics and dead tuples,
and define index maintenance/retention ownership. Exact DDL/index names and numeric tuning settings
remain reviewed migration outputs, not claims that this table has measured production performance.

### Recovery acceptance and boundary with OCI

D51 accepts a **15-minute RPO** and **4-hour RTO** as initial production engineering targets.
D52 limits those targets to **recovery within the hosting OCI region** in V1; complete regional loss
is outside these targets and needs a separately reviewed future disaster-recovery design. These
are accepted objectives, not demonstrated OCI guarantees or executed restore evidence.

RPO bounds the age of the recoverable committed database state at the incident. RTO runs from
incident start until authorized administrators can use the recovered application and explicitly
released, eligible operations safely. Record read-only availability separately; it does not by itself
stop the RTO clock. Unknown scoped effects remain blocked rather than bypassed to meet a target.
The measurement/qualification contract below makes these boundaries explicit.

A database backup does not roll back OCI resources or Vault. D54 uses an ordinary deployment
maintenance/read-only setting with API mutations, password disclosure, workers, dispatchers and
scheduled triggers paused. Stop old processes before starting the restored application, hold
restored active work, manually inspect current OCI/Vault/mail state and explicitly resume safe work.
Normal passwords resolve stable secret OCID plus Vault CURRENT; uncertain rotations/deadlines stay
blocked for manual review. See [the short restore runbook](17-recovery-and-release.md#manual-database-restore-runbook).
No independent control object, distributed release protocol or per-effect external journal is required.

Keep the accepted targets, measure the manual procedure in a managed-service drill, and record
missing history or target misses honestly. Exact backup/PITR retention and service compatibility
remain implementation qualification; the target does not imply automatic replay or zero data loss.

### CI/CD gates and promotion

D53 requires protected `master` as the integration/default branch, with one migration/contract owner.
All required tests run on every CI build, with unit-only line coverage at least 95%. Require Playwright
UI integration and real database-operation tests against disposable Docker PostgreSQL; any failed
test or coverage below 95% blocks a PR merge. Missing/skipped required checks cannot pass, and direct/
force pushes, deletion and routine gate bypass are blocked. The [canonical test/merge policy](../engineering-test-plan.md#d53-required-test-and-merge-gates)
defines scope, candidate validation and enforcement probes. Actual hosted settings remain P0 work.

PR validation runs without
production credentials: locked install, lint/format/types, inline documentation, existing organization
regressions, generated schema/client parity, disposable PostgreSQL constraints/runner/transaction
tests, real/simulator contract parity and approved UI journeys at desktop/mobile widths. Keep static
C5 design checks as additional evidence; they cannot replace application workflow tests.

Build application/frontend artifacts once; record digest, dependency inventory and scan/signature
results. Validate Terraform and review a plan before infrastructure mutation. Promote the same tested
digests through integration/pilot/production. Deployment checks current schema/worker compatibility,
uses readiness and graceful drain, and prevents old workers from executing incompatible steps.
Use expand/contract database changes; removing data or replaying provider mutations is not an image
rollback strategy. Record release and migration revisions in operational evidence.

Production release requires smoke/read-only scope checks, monitored queues/deadlines, independent
operator alerting, restore evidence and an owned incident runbook. Test recipients/simulators remain
environment-enforced defaults outside approved live stages. The local prototype's Clean workspace
route is absent/disabled server-side in production, not merely hidden in the navigation.

### Development work packages, preliminary

| Package | Concrete output | Dependency / merge boundary |
|---|---|---|
| P0: repository and contracts | Shared repo with protected `master`, every-build tests/95% unit-coverage/Playwright/Docker-DB merge gates, reproducible toolchains, module ownership, generated model/API contracts and first migrations | One integration owner; preserve prototype fixtures/logic/tests |
| P1: durable vertical slice | Command acceptance → job/attempt → facade simulator → verified publication → Operations | Prove atomic enqueue, crash/restart/restore fences before multiplying workflows |
| P2: domain journeys | Create/import, shared ownership/member changes and offboarding to termination initiation | Build against P1; reuse accepted C1 screens and association rules |
| P3: configuration/access | Versioned managed objects, overrides/conflict gate, drift/repair and independent recovery password lifecycle | Shared binding/observation/credential contracts; dependency-ordered migration ownership |
| P4: consolidated visibility | Approved Tenancies dashboard, current-cycle budget collection, email routing/outbox | Exact C5 examples become model/query/provider tests; no V2 history or security findings |
| P5: platform and qualification | Terraform/OKE/PostgreSQL/SSO/mail, restore/load/security checks, live pilot | May prepare environments early; real pilot waits for safe P1–P4 boundaries |

These are reviewable output packages, not independent services or a calendar promise. One engineer
with Codex remains a valid default. Additional developers/Codex contexts can own frontend, adapter
qualification or platform work once P0/P1 boundaries are stable. Keep one schema/migration owner and
merge small vertical increments through shared contract tests; measure the first slice before
committing staffing or dates. The final dependency graph, detailed acceptance checklist and staffing
recommendation will be refined as C6 decisions and qualification findings settle.

### C6 narrative-to-model trace

| Operational information | Authority / storage plan |
|---|---|
| Recovery targets, schedules, pool/concurrency and timeout settings | `org_workspace.runtime_policy` plus revision; accepted recovery fragment has `rpo_seconds=900`, `rto_seconds=14400`, `disaster_scope=in_region`. Other numeric settings remain proposals |
| Backup/restore point, old/new DB system and endpoint references | Typed recovery operation intent and immutable `audit_event.data`, with surviving provider/deployment references; no password or connection secret |
| Restore pause and administrator review | Deployment maintenance setting and suspended processes; existing operation/audit review records, not an independent control store or workspace epoch mirror |
| Image digest, migration revision, compatibility, drill/test receipts | Release/deployment evidence and typed audit references; Terraform/registry/CI remain their own authorities |
| Role grants, indexes and service parameters | Versioned migrations/Terraform/provider configuration; effective permissions and EXPLAIN evidence checked in integration |
| Queue claims, due work, rotation deadlines and delivery backlog | Existing runner infrastructure, operation/step, credential/grant, collection and outbox state; no separate scheduling/incident application tables |

These mappings extend the existing [platform/recovery model](11-production-data-model.md#recurring-work-platform-recovery-and-database-operations)
without adding application tables or pretending operational evidence is already implemented. P0 must
version concrete payloads/constraints before implementation; C6 still owes provider-specific
qualification, the manual recovery drill and final work-package acceptance matrix.


## D51/D52 accepted: recovery objectives and in-region qualification

25 October 2026. D51 selects 15-minute RPO/4-hour RTO. D52 selects in-region recovery in V1.
No cross-region standby, automatic failover or full-region recovery guarantee is introduced.
The [nonsecret policy example](../contracts/platform-recovery-policy.example.json) is a **design-only
fragment**, not a complete deployable runtime policy. Future Python models must validate/version
its fields under the existing workspace `runtime_policy`/`runtime_policy_revision`; there is no new
table, relational column or tenancy baseline item.

### Candidate backup mechanism and documented limits

Use managed PostgreSQL point-in-time recovery as the candidate mechanism to qualify for the
15-minute objective. Daily backup alone cannot establish that objective. A region-specific pilot
must inspect the actual latest recoverable point, restore behavior, permissions, quotas, network
cutover, database/runner compatibility and reconciliation time.

Oracle documents that [PostgreSQL PITR](https://docs.oracle.com/en-us/iaas/Content/postgresql/point-time-recovery.htm)
uses retained WAL and periodic volume backups, exposes an active recovery window and creates a
**new** DB system while the original remains. Its documented retention maximum is 35 days. This
source does not establish a 15-minute maximum recovery-point lag or 4-hour end-to-end application
restoration guarantee. Retention length is a separate configuration decision, still to qualify.

Oracle's [backup documentation](https://docs.oracle.com/en-us/iaas/Content/postgresql/backups.htm)
describes daily/weekly/monthly automatic backups and regional copies, with data-placement constraints
on copying. Those capabilities do not establish continuous cross-region PITR or approval of a
regional standby. D52 does not depend on backup-copy capability. Service facts were checked on
25 October 2026; regional/service availability and Terraform/API support remain pilot checks.

### Measurement and evidence

| Evidence field | Meaning / acceptance |
|---|---|
| `incident_started_at` | Earliest established loss/corruption time from independent monitoring/operator evidence; record detection uncertainty, never restart the clock at restore initiation |
| `incident_detected_at`, `restore_started_at` | Diagnostic milestones; not substitutes for incident start |
| `latest_recoverable_at` | Verified service recovery-window endpoint at incident/restore selection, not the last backup's label |
| `selected_restore_at` | Actual selected recovery point; record why it differs from latest recoverable point |
| `recovered_contiguous_through_at`, `missing_commit_markers` | Committed-write prefix verified with ordered sentinel/test events and surviving independent receipts; a later isolated row cannot hide a gap |
| `read_only_ready_at` | Authorized sign-in, validated DB/schema and usable read views; intermediate recovery milestone |
| `safe_service_ready_at` | Old installation fenced, external effects reconciled or explicitly quarantined, credentials controlled, and administrator release permits eligible normal operations |
| `measured_rpo_seconds`, `measured_rto_seconds` | Proven recovery-point gap relative to incident and elapsed incident-to-safe-service time; compare against 900 and 14400 respectively |
| `affected_targets`, `blocked_effects`, `credential_obligations` | Explicit outstanding unknown scopes, original known disclosure deadlines and independent recovery ownership; never silently called healthy |
| `restore_review_event_id`, deployment revision and selected operations | Existing administrator audit evidence and deployment records; no independent release manifest or workspace epoch mirror |
| `objective_result`, `evidence_gaps`, `follow_up_references` | Measured met/missed/not-proven result, lost evidence and remediation owner; not an editable claim that rewrites history |

These fields are drill/review evidence under existing operation/audit and nonsecret provider/deployment
records. A disposable drill harness retains its own synthetic commit expectations for comparison.
V1 does not require a production external commit/dispatch journal. Available operational logs and
provider recovery information support manual review; irrecoverable history gaps are recorded.

Use a regular ordered commit marker in the disposable drill and independently retain its
acknowledgment. Record both recovery-point age and actual missing committed work. Quiet production
periods must not be interpreted as writes being lost merely because no application event occurred.
If the selected safe point is older than 15 minutes, or end-to-end recovery exceeds 4 hours, record
an objective miss; do not relabel the clock or waive normal guards. The accepted RPO permits a
bounded database evidence gap; it does not promise zero lost audit writes or allow fabricated
replacement history. Preserve and reconcile surviving evidence and report any irrecoverable gap.

A safe-service milestone requires usable authorized workflows for eligible targets plus explicit
quarantine of unresolved effects. It cannot count as full restoration if the entire application is
still read only. Record quarantined targets and their business impact in the drill result; achieving
RTO does not certify every external effect has been resolved or every historical record recovered.

### Credential deadline and independent recovery

The four-hour application RTO does not start or extend a four-hour password exposure window.
If a disclosed password becomes due during an outage, the independent recovery operator handles it
by its original deadline where possible, records any miss and verifies actual identity/Vault state.
Lost exposure anchors or uncertain rotated versions block disclosure; restoring an older credential
pointer is never proof it is safe. An urgent manual-recovery handoff must identify an authorized
person and evidence, rather than merely creating an in-app task while OTM is unavailable.

### Planned qualification cases

| Case | Required result |
|---|---|
| In-region DB loss with ordered committed markers | Restore state proves at most 15-minute recovery-point gap and safe service within 4 hours, or reports a measured miss |
| Corrupting migration/operator write | Select a demonstrated safe point; explicit loss/gap and any target miss, with no clock reset |
| Old DB and workers survive PITR | New system remains fenced until old installation's mutation/secret access is demonstrably fenced; in-flight calls reconciled |
| Create/delete completes after DB restore point | Recover provider identity/effect or quarantine; no duplicate create or repeated termination |
| Password disclosed/rotated after restore point | Reconcile live user and Vault versions; preserve deadline or record uncertainty; no stale-password release |
| Email accepted after restore point | Reconcile original delivery context; unknown is not unsent and cannot be blindly resent |
| Unusable DB endpoint/certificate or incompatible schema/runner | Readiness/release blocked; wall-clock recovery time still counts |
| DB restored quickly but all mutations still blocked | Read-only milestone recorded; RTO not yet met |
| One scoped external effect remains unknown | Quarantine that scope, report impact and explicitly release only independently eligible operations |
| Entire OCI region unavailable | Outside D52 V1 targets; do not claim either an in-region drill or copied backup qualifies regional disaster recovery |

All cases are planned, not executed. Gate production on a measured managed-service restore and the
D12 fence/reconciliation tests, with accepted objectives recorded in the release evidence. Exact
maintenance/runbook details, backup retention and drill ownership remain C6 work.


## D53 accepted: required CI and master protection

26 October 2026. The [required test/merge gates](../engineering-test-plan.md#d53-required-test-and-merge-gates)
are binding for P0: 95% or greater unit-only line coverage, Playwright UI integration, disposable
Docker PostgreSQL integration and all suites on every CI build. Every required result must pass
for the current merge candidate; protect `master` against direct/force pushes, deletion and routine
bypass. Capture actual configuration and negative enforcement probes as P0 acceptance evidence.
No CI workflow, remote settings, application dependency, schema or runtime test result is introduced
by this design adoption. Existing prototype tests are retained; their current coverage is not claimed.




## D54 accepted: keep recovery simple

26 October 2026. [The manual procedure](17-recovery-and-release.md) supersedes the unapproved external
control/journal proposal. Vault CURRENT is the ordinary recovery-password source; exact versions are
rotation/audit evidence. Deployment maintenance and stopped old processes prevent automatic replay,
with administrator reconciliation/resumption using existing operation state. No extra recovery
bucket, service, journal, distributed epoch mirror, release manifest or special CLI is V1 scope.

Review new and existing design for the simplest adequate approach. Introduce production tables and
indexes only as their feature slice requires them; ask before adding substantial rare-edge-case
machinery. Required authorization/target guards, durable jobs, secret handling and D53 gates remain.


## D56: independent slice security and supply-chain review

28 October2026. Each completed development slice requires the standing `security_review` subagent,
plus required automated secret/static/dependency checks and applicable image/IaC scans on every
build. [Security policy](../security-review-policy.md) defines threat boundaries, evidence, severity
disposition, exact artifact/lockfile review and no-real-PII publication. P0 must prove the gate before
feature merges; scans or hosted controls are not configured merely by documenting them.
