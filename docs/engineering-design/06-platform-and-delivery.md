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

## Shared inbound source allowlist — 13 November 2026

Use one protected GitHub Environment Secret, **`OTM_ALLOWED_SOURCE_CIDRS`**, for both
hosted app ingress and each child tenancy's recovery-console perimeter. Values are a comma-separated
list of canonical CIDRs, with multiple network ranges and individual addresses represented as IPv4
`/32` or IPv6 `/128`. Reuse the [existing strict parser and bounds](22-credential-security-lifecycles.md#configuration-contract-and-github-actions):
reject the whole candidate on missing/empty/malformed entries, host bits, or an unrestricted union;
never default to public access. Operational values stay in environment variables/private deployment
inputs, not source, examples, plan artifacts or logs. The approved initial three-entry list is retained
privately; the saved laptop runtime is not changed by this hosted deployment decision.

The same validated list supplies the Terraform `app_ingress_allowed_cidrs` input and
`recovery_console.allowed_cidrs` in rendered application settings. The
[network source foundation](../how-to/network-foundation.md) now implements this input and its private
renderer; it is not an input to bucket bootstrap. OKE attachment and the optional [held Caddy ingress](../how-to/caddy-ingress.md) backend/health rules now exist as source. Deployment and live filtering remain unqualified.
Keep these two consumers consistent during reviewed network/settings releases; changing a GitHub
variable alone does not mutate either control. A widening must review both consequences; a removal
must account for administrator lockout. Do not create separate independently editable lists.

Restrict the app's internet-facing load balancer to TCP 443 from this union, covering both SPA and
API traffic. Private nodes/pods/database must not expose a bypass through public IPs, alternate
load balancers, NodePorts or management endpoints. Health checks use separately scoped internal
rules, not a public health-check exception. SSO/session authorization and MFA remain required.
Network admission uses the actual connection source, never a client-supplied forwarded-IP header.
No public IPv6 listener is enabled until its allowlist enforcement is qualified. The owner subsequently approved reusing the human list for Kubernetes API TCP6443 only; it does not grant SSH, database or Kubernetes authorization. Runner admission stays separate.

Inspect the **effective union** of load-balancer NSGs, subnet security lists and any controller-created
rules: adding a restrictive NSG does not compensate for another permissive rule. Ensure Kubernetes
load-balancer manifests explicitly set the supported source restriction rather than allowing an
omitted value to create internet-wide access. See [Oracle's OKE load-balancer security guidance](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengconfiguringloadbalancersnetworkloadbalancers-subtopic.htm)
and [listener ingress rules](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managinglisteners_topic-Enabling_Listeners_to_Accept_Traffic.htm).

Staging/production environment variables are configured with the approved list and restricted to
protected-branch deployments. Deployment workflows, production approval controls and actual network
enforcement remain to be implemented and qualified; variable creation is not proof of protection.

## Paid-tenancy platform direction and candidate sizing — 13 November 2026

The [Enhanced OKE source follow-up](../how-to/oke-foundation.md) implements cluster/pool pins,
private node/pod attachments and the [explicit traffic matrix](../how-to/oke-network-traffic.md).
The owner approved a source-restricted **public** Kubernetes API for Lens/kubectl and hosted CI,
superseding the private-endpoint/private-runner proposal. Human TCP6443 uses the existing shared
allowlist; job-specific `/32` admission remains a separate deployment control. Node cloud-init is
required from per-environment GitHub Actions secret `OTM_WORKER_CLOUD_INIT`, never a published script.
Terraform state/plans and node metadata retain its base64 content; use restricted private custody.
Falcon ARM64 compatibility is unknown and is a staging/go-live prerequisite. No live resources have
been created or qualified by this source checkpoint.

The owner confirmed a fully paid OCI tenancy, managed PostgreSQL, an Enhanced OKE cluster and
multiple Kubernetes nodes. The family-grocery-list project is a reference for delivery patterns,
not an Always Free capacity, networking or availability template. Prefer appropriately sized A1 ARM
managed nodes, subject to region capacity and compatibility. The hosting compartment can remain in
a tenancy separate from the managed parent. No cloud resource creation is authorized by this note.

The accepted hosting target is `us-ashburn-1` (13 November 2026). Keep the region an explicit
environment input with that default, not a baked-in provider constant. This does not select the
managed parent's home region or restrict administrators' child-tenancy home-region choices.

Use the newest generally available, region-supported OKE Kubernetes release compatible with the
selected ARM node image and required add-ons. Pin the exact version through protected Actions inputs.
The [image resolver](../how-to/platform-versions.md) selects a unique newest compatible version/ARM/OS
image during a reviewed infrastructure plan; apply that saved plan and promote the exact staging
selection. Replanning can change the image and requires renewed qualification; no floating Kubernetes
version is accepted. Preview releases require a separate explicit decision. Disable IMDSv1 on every node.
Validate ARM application images, native dependencies and add-ons, including native crypto, TLS and
Psycopg smoke tests; an amd64 image or an emulated build alone does not qualify the ARM deployment.

The following numbers are **engineering proposals for qualification, not accepted capacity or
performance guarantees**:

| Production component | Candidate starting point | Qualification condition |
| --- | --- | --- |
| Shared managed node pool | Three `VM.Standard.A1.Flex` nodes, each 2 OCPUs / 8 GB RAM | Spread across availability domains where available, otherwise fault domains; demonstrate remaining-node capacity during one-node loss and rolling updates, including system/add-on reservations |
| API | Two small replicas, spread across nodes | Measure dashboard/feed latency, requests/limits, connection use and graceful drain; no dedicated API node pool initially |
| Durable workers | Existing accepted target: two pods, one execution slot each | Shared native Procrastinate queue, per-tenancy exclusion, duplicate delivery and interrupted-write controls remain mandatory; extra nodes do not imply extra execution slots |
| Managed PostgreSQL | Two `PostgreSQL.VM.Standard.E5.Flex` database nodes, each 1 OCPU / 16 GB RAM | Primary plus HA replica; validate target-region shape/configuration support, realistic history/query/queue load and failover; consider 2 OCPUs per node only if measurements justify it |
| PostgreSQL storage performance | Lowest supported suitable performance tier | Measure query/write latency, storage growth, WAL and temporary spill before increasing the tier; no speculative premium tier |

Prefer regional database placement in a multi-AD region. Initially use the primary endpoint for
application reads and writes; the second node is for availability, not a new read-replica routing
feature. Database HA and backup/PITR recovery are separate; retain the accepted in-region RPO/RTO
targets and qualify restore independently. The database CPU architecture need not match ARM clients.

OCI PostgreSQL automatically scales shared data/WAL storage independently of compute. Do not model
it as a manually reserved application PVC or invent a large fixed data-disk allocation. Temporary
storage is separate and shape-dependent. Budget and monitor data, indexes, retained immutable
history, WAL, temporary/log usage and backups. Do not shorten approved history retention merely to
meet a storage estimate. Production sizing must include future feed/audit/job history, not just the
approximately 250 current employee rows.

The owner requires staging to mirror production: both use two API pods and two worker pods with
one slot each, matching node/database sizing, HA topology, versions and deployment behavior. The
saved local worker remains unchanged. Qualify multi-worker and database-failover acceptance in
this same staging topology. Bound total SQL pools across API, workers, native queue consumers, scheduled
jobs, migrations and reserved operator capacity, including rollout surge. Start with one shared node
pool; split or scale it only for measured resource contention or required isolation. Track queue age,
credential deadlines, provider throttling, CPU/memory pressure, database lock/connection waits and
dashboard query latency. Raise worker parallelism based on measured service limits and queue latency,
not solely on spare CPU. No runtime settings, pool counts or deployment resources are implemented here.

Platform qualification sources:
[OKE supported versions](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengaboutk8sversions.htm),
[OKE workload identity](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm),
[PostgreSQL shapes](https://docs.oracle.com/en-us/iaas/Content/postgresql/supported-shapes.htm),
[PostgreSQL HA](https://docs.oracle.com/en-us/iaas/Content/postgresql/high-availability.htm),
[PostgreSQL storage](https://docs.oracle.com/en-us/iaas/Content/postgresql/storage-best-practices.htm),
[PostgreSQL performance tiers](https://docs.oracle.com/en-us/iaas/Content/postgresql/performance-tiers.htm).
Recheck live region/service capabilities before selecting or provisioning the pinned environment.

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

### Ashburn V1 backup policy proposal — 13 November 2026

The owner confirms `us-ashburn-1` as the hosting region and excludes a second-region DR site from
V1. The following retention, monitoring and drill settings are engineering proposals to qualify in
that region; they are not deployed policies, measured storage usage or service guarantees.

| Control | Proposed V1 setting / acceptance |
| --- | --- |
| Point-in-time recovery | Enable with a 35-day window; verify the actual earliest/latest recoverable timestamps. Daily backup alone cannot meet the accepted 15-minute RPO |
| Scheduled backups | Daily managed-service backups in a configured UTC window, retained for 35 days; qualify coexistence and accounting with the PITR policy, without implementing another backup engine |
| Pre-change checkpoints | On-demand backup before destructive/high-risk schema, database or platform changes, with explicit seven-day expiry unless an incident requires an approved extension; never delete the last verified usable recovery source as routine cleanup |
| Availability | Existing proposed two-node DB system with regional placement; HA/failover does not replace backup or protect against logical mistakes |
| Restore exercises | Full isolated restore before go-live, at least quarterly afterward, and after material backup/restore/platform changes; include a recent restore point and an older retained point across the drill program |
| Recovery objective | Retain D51/D52: at most 15 minutes of committed-data loss and application recovery within four hours, in-region only; measure usable application recovery, not just database creation |
| Monitoring | Independently monitor backup failure/age, PITR being disabled or inactive, recovery-window freshness approaching/exceeding the RPO, retention-policy drift, storage growth and restore-drill age; alerts must work while Atlas/its DB is down |
| Custody | Provider-managed encrypted backups; qualify chosen encryption-key access, backup retention/deletion permissions and restore permissions. API/worker and ordinary application-deployment identities receive no backup-delete authority |
| Deletion/restore guard | Reviewed destructive Terraform plans and database lifecycle protections; retain backup/key access and capacity for a replacement DB system. A removed Terraform resource definition or privileged operator can bypass a lifecycle guard, so it is not the only control |

Backup storage is a measured, automatically managed service cost rather than a preallocated PVC or
fixed disk size. Oracle documents a first full backup followed by incremental backups; do not budget
35 independent full copies by default, assume a compression/deduplication ratio, or multiply the
logical backup chain by the number of HA compute nodes. Include changing blocks, retained WAL/PITR
volume history, retained manual checkpoints and actual service billing categories. Keep growth of
source snapshots, operation/audit history, queue churn, indexes and maintenance writes in the model;
new-row size alone does not predict changed-block or WAL volume.

Use `baseline backup bytes + retained incremental bytes + separately accounted PITR/WAL bytes +
manual-checkpoint bytes + headroom` as a planning worksheet, reconciling it with service reporting
so shared or already-accounted bytes are not charged twice in the estimate. For illustration only:
a 10 GiB baseline plus 1 GiB/day of combined additional retained backup/PITR bytes for 35 days is
about 45 GiB before checkpoints/headroom. Two additional hypothetical 10 GiB checkpoints plus 25%
headroom bring that to about 81 GiB; a rounded 100 GiB cost-planning allowance is a provisional
scenario, not a forecast, allocation or hard retention cap. Confirm actual backup/WAL footprint and
growth during a representative pilot (including maintenance and a baseline rollout), replace the
assumptions with measured data and review cost regularly. Do not silently shorten recovery windows
or immutable audit retention to meet that allowance. Budget transient restore-drill compute and
service quota capacity separately; no idle duplicate database is required outside a drill.

Restore into a separate private system with outbound application effects, workers, schedulers and
mail delivery fenced. Exercise [the existing simple manual restore procedure](17-recovery-and-release.md#manual-database-restore-runbook):
prove old-process fencing, endpoint/TLS/role/migration compatibility, historical integrity, fresh
authentication, restored pending-work holds and reconciliation with current OCI/Vault state before
an administrator resumes mutations. A drill must not act against real child tenancies or send real
notifications. Exercise process fencing on the owned test installation, without stopping the healthy
production deployment; the real incident procedure still requires fencing the original installation.
Keep restored data, credentials and detailed drill logs restricted, outside source and CI artifacts.
Record timestamps, actual recovery gap, end-to-end recovery duration and results;
remove only the explicitly owned drill system after review. Backups do not restore Vault or reverse
OCI effects, and there is no new coordinator, external effect journal or automatic queue replay.

Future DR is a separate design/qualification milestone. Oracle currently documents that backups
of PostgreSQL systems with regional data placement cannot be copied to another region. Therefore
do not promise to add cross-region DR by simply toggling backup-copy configuration on this regional
HA design. Reassess supported replication/copy/export mechanisms, placement, key/network custody,
cost and separate regional-loss RPO/RTO then. V1 retains no standby region and makes no regional-loss
recovery promise. Independent indefinite application audit retention is not indefinite backup retention.

Service facts checked 13 November 2026:
[backup mechanics, retention and copy limits](https://docs.oracle.com/en-us/iaas/Content/postgresql/backups.htm),
[PITR and replacement DB systems](https://docs.oracle.com/en-us/iaas/Content/postgresql/point-time-recovery.htm),
[backup billing](https://docs.oracle.com/en-us/iaas/Content/postgresql/billing.htm),
[manual backup expiry](https://docs.oracle.com/en-us/iaas/Content/postgresql/create-backup.htm),
[backup survival after DB deletion](https://docs.oracle.com/en-us/iaas/Content/postgresql/delete-db.htm).
Reconfirm retention/deletion semantics, policy coexistence, recoverability, encryption and monitoring
API fields in the Ashburn pilot rather than inferring them from backup labels or a successful plan.

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
| Staging / pilot | Separate OCI parent/children and isolated hosting tenancy/resources, DB, state, secrets and deployment identities; restricted real children | Reviewed create/import/config/access/cost scenarios; approved email test recipients | Candidate-bound acceptance, capability matrix, observed limits, rollback/restore drill and operator signoff |
| Production | Its own OCI parent/children and isolated hosting tenancy/resources, DB, state, secrets and entitlement; no staging authority | Reviewed V1 operations behind all normal guards, using only staging-qualified release artifacts | Exact digest promotion, release evidence, monitoring, recovery ownership and runbooks |

Propose one repository, one modular Python service image, an API deployment and separate worker
process roles. Use the same immutable image digest for those roles; no per-feature microservices.
The installed image contains the compiled responsive frontend and migration assets; no separate
frontend rebuild occurs during promotion. Kubernetes CronJobs
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

The [two-environment deployment contract](24-environments-and-promotion.md) requires staging's own
OCI parent tenancy, separate production tenancy/resources/identities/state and build-once promotion.
Separate GitHub entry points build the app, plan/apply each environment's infrastructure, deploy to
staging and promote the exact qualified release to production. Settings retain their separate path.

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


## Accepted initial worker sizing — 10 November 2026

Superseded on 13 November 2026: staging must mirror production. Both target two worker pods with
one execution slot each and two API pods, with identical node/database capacity, software versions,
security/deployment controls and resource budgets. Measure OCI request duration, queue wait,
credential-closure timeliness, contention and node-loss/surge headroom in that staging topology
before promoting the exact tested release. Environment identities, credentials/endpoints and the
staging email redirection stay isolated. The local saved worker remains one process/one slot; no
pods are deployed by this decision.

Workers share the existing PostgreSQL/Procrastinate queue; no separate queue service or scheduler
is added. Native operation locks and application claim/revision checks remain required. The
per-tenancy signing-key pause still serializes protected work for that child across all pods.
Additional workers do not make uncertain external writes safe to retry or automatically recover
an operation left running after a crash. Owned manual reconciliation remains the V1 boundary.

Before production qualification, exercise two independent processes against the same queue,
per-tenancy exclusion, unrelated-child progress, duplicate delivery and worker death. Include
recovery-password closure while signing-key work drains. Record real-OCI timings and bound the
PostgreSQL connection budget for API and worker replicas; replica count alone is not a latency SLA.

## Installed image packaging — 12 November 2026

The first container checkpoint packages one installed nonroot image for existing explicit commands,
with a built frontend and wheel migration assets. See the [container guide](../how-to/container-development.md)
for exact smoke coverage and boundaries. It neither deploys to OKE nor changes the saved demo. Hosted
composition and verified remote database/secret/worker behavior remain separately qualified work.

Runtime selection uses a digest-pinned official Python3.12 Alpine3.24 base for both Python build and
runtime stages. The Debian candidate's remaining OS findings are not blanket-exempted; the alternate
base must pass native crypto/TLS/database/job compatibility and strict OS/Python image scanning.
The existing security CI lane owns that image gate; base updates require a fresh uncached build
and reviewed dependency changes. No arbitrary shared-library removal or hand-maintained distro.

### Managed PostgreSQL source follow-up — 13 November 2026

The [managed database source guide](../how-to/managed-postgresql.md) records the implemented private two-node resource, service configuration/shape discovery, Vault-reference provisioning, backup/PITR intent and upgrade safeguards. These source checks do not qualify the proposed capacity, backup freshness, restore targets or live version transitions. Runtime roles, Vault/IAM wiring and hosted monitoring remain separate slices.

### Vault custody source follow-up — 13 November 2026

The [Vault/IAM foundation](../how-to/vault-foundation.md) creates separate database-provisioning/application Vaults and HSM AES256 keys in one existing hosting compartment in separate environment security roots. Initial secret ingestion remains outside Terraform; an approved existing provisioning group gains only exact-Vault-conditioned database-secret/Vault reads. Runtime workloads, federation, effective IAM, key rotation and service recovery still require their own qualification.


## V1 network simplification — 14 November 2026

[Approved NSG-only source](../how-to/nsg-only-networking.md): no pod policy engine and no generated NetworkPolicy. Existing NSG matrix remains; optional explicit SMTP CIDRs/port465 or587 add only relay rules. No claim of per-pod network isolation or link-local metadata filtering. IMDSv1 stays disabled, workload IAM stays separate from node authority, and actual rule unions/routing/metadata/SMTP behavior require staging qualification.

## Caddy HTTP-01 source checkpoint — 15 November 2026

[Accepted ingress design](25-https-ingress-and-certificates.md) and [review procedure](../how-to/caddy-ingress.md): external DNS remains operator-managed; public port 80 serves active ACME challenges only, ordinary HTTP 404, HTTPS 443 remains source-restricted. Separate pinned Caddy image, held single-writer ingress/PVC and exact NLB/NSG handoff are implemented as source. StorageClass bootstrap needs infrastructure authority, not app CI cluster-admin. Native Pebble issuance/renewal/restart/header tests pass. On 15 November the owner accepted two exact official-image DoS findings under the [scoped continuous-update policy](../reference/caddy-security-exceptions.md); targeted policy/native checks pass with two accepted and zero blocked findings, while full milestone/hosted/live gates remain separate. Real OCI/Let's Encrypt and persistent-volume recovery remain unqualified.

## Immutable ARM64 build source — 16 November 2026

[Candidate fields and trust boundary](../reference/artifact-releases.md) and [operator review](../how-to/application-releases.md):
exact successful master-push Checkpoint source, native ARM64 app/Caddy build-once source, actual-image
scans and SBOMs, standard GitHub attestations and four allowlisted public files. Git archive plus
Docker filtering excludes local private build inputs. Hosted publication/attestation, 90-day versus
long-term evidence custody, OCI pulls and staging/production acceptance remain unqualified. No OCI
deployment, app/table/UI change or saved 8443 update occurs in this source checkpoint.
