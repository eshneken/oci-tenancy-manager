# Accepted engineering decisions D1–D17

These are the accepted foundation decisions, retained from the 12 October review.
Later decisions in [the current design hub](../engineering-design/README.md) supersede earlier
alternatives: D30/D35 govern configuration, D40 human access, D41–D50 finance/email,
D51/D52 recovery objectives, D53 quality gates and D54 simple manual restore.
The dated review record (private historical evidence; not distributed) is historical evidence,
not a second pending design or an implementation completion claim.

## D1: accepted rollout contract

Publication makes a version selectable. It does not mutate existing assignments or enqueue OCI application. Creation/import select a published version. Existing checks use the assigned version; a new publication alone is not drift.

Explicit rollout records the administrator, idempotency identifier, immutable version, exact targets and resolved parameters from the preview. Changed assignment/eligibility preconditions require a refreshed preview; execution rechecks authorization and automation permissions. Record desired assignment, last verified version and per-item/per-tenancy progress separately. Partial failure remains visible; retries reconcile prior outcomes rather than restart blindly. Queue/concurrency mechanics are still under review.

Acceptance cases: publication creates no OCI jobs; explicit start preserves the selected version despite later publications; repeated start returns the recorded operation; stale previews cannot overwrite intervening assignment changes; partial success is represented accurately; worker restart/retry preserves progress; lost automation access blocks dispatch. These are planned tests, not executed results. See specification AC35.


## D2: accepted runner direction and qualification

Use Procrastinate for PostgreSQL-backed Python task dispatch. Keep tenancy workflow state in application operation records; the task runner is responsible for dispatch, not the authoritative meaning of a completed create/import/delete/rollout. Waiting for manual activation persists a stage rather than holding a worker indefinitely. CronJobs remain the recurring-trigger mechanism.

Before adopting pinned versions, prototype the chosen SQLAlchemy/psycopg integration, task locking/retry behavior, duplicate dispatch, graceful shutdown and abrupt worker termination. Verify stalled jobs are detected and recovered through an explicitly configured mechanism; do not assume crashed jobs resume automatically. Recovery of an OCI side effect must still inspect recorded provider outcomes before repeating it. The original qualification targets now have bounded local execution evidence in the runner checkpoint below. Production integration and operation-specific concurrency/recovery guards remain separate implementation work.

Primary references: [Procrastinate documentation](https://procrastinate.readthedocs.io/en/stable/), [external database connections](https://procrastinate.readthedocs.io/en/stable/howto/production/external_connection.html), and [stalled-job recovery](https://procrastinate.readthedocs.io/en/stable/howto/production/retry_stalled_jobs.html). The documented SQLAlchemy connector example uses psycopg2; compatibility with the accepted psycopg stack must be demonstrated rather than inferred from that example. An incompatible prototype returns the issue to review rather than silently changing the stack or choosing a different dispatch design.


### Local runner qualification checkpoint

The [isolated native-runner experiment](../../prototype/experiments/runner/README.md) now passes
29 cases: 17 real PostgreSQL/owned-process scenarios plus 12 target/process-cleanup controls.
Candidate Procrastinate 3.10.0, SQLAlchemy 2.0.54 and psycopg 3.3.6 work through the supported native
external-connection hook. The acceptance call receives SQLAlchemy's exact active psycopg connection;
no custom connector or psycopg2 bridge was needed. Long-lived workers use the native async connector.

The tests cover local transaction/visibility/commit failure, request conflict/concurrency, caller
and worker crashes, retries, locks, graceful shutdown and explicit stalled recovery. The three toy
tables are not production entities, and SQL idempotency does not establish exactly-once OCI effects.
Managed-service permissions and production immutable intent/authorization/dispatch/migrations remain
unqualified. Production dependencies are unchanged; the candidate pin is isolated until integration.

## D3: accepted transactional enqueue contract

The API commits an accepted operation, its initial append-only audit event and the initial Procrastinate job together through one PostgreSQL transaction. The job payload references the durable operation; credentials are not queue arguments. Commit failure rolls back all three records and returns no acceptance. Workers cannot dispatch OCI work from uncommitted intent. The API returns the operation ID only after commit; a lost response after a successful commit is recovered by resubmitting the same request identifier. Enforce request uniqueness and reject reuse with conflicting intent, including concurrent submissions.

Qualification must demonstrate that job insertion joins the exact application transaction through supported connection handling, rather than committing independently. Test transaction rollback, job-insertion failure, process termination immediately before/after commit, worker visibility only after commit, lost-response retries and simultaneous duplicate submissions. The runner checkpoint above exercises these local transaction/process scenarios using toy records. It does not qualify the production command model. A database commit does not make subsequent OCI calls atomic or guarantee a single external execution; provider reconciliation remains required. This decision covers initial job dispatch, not notification delivery or the still-open concurrency/recovery contracts. See specification AC36.


## D4: accepted mutation coordination contract

Allow one mutation step at a time for a managed tenancy; distinct tenancies can progress concurrently. Apply the coordination rule across task types and workers, not only within each task function. Lifecycle admission remains separate: a delete cannot slip between steps of an active import/rollout and invalidate its prerequisites. Conflicting requests return a visible conflict or wait with an explicit reason, rechecking eligibility before dispatch. Exact admission/wait error schemas remain engineering details.

Manual activation and future credential deadlines persist state without occupying a worker or reserving a task execution lock during the wait. Due rotations receive priority at safe boundaries between steps and retain the original deadline. They cannot preempt an OCI call already in progress; blocked/overdue rotation is visible and alerted. Do not introduce a long-running database transaction covering network calls or a human wait. Read-only collection can continue, but observations identify their capture time and any concurrent mutation rather than certifying a stable state prematurely.

Use owning scope and object identity to coordinate a shared parent-side object as well as the affected child. A global parent lock for unrelated objects is not the default. A lost worker/timeout does not prove that its OCI request stopped; ambiguous outcomes block conflicting mutations until reconciled. Queue locks alone do not establish provider completion or recovery safety. Qualify the mechanism with multiple workers, process termination and provider calls that outlive a task attempt.

Planned tests: concurrent repair/rollout/delete requests; parallel mutations across different tenancies; activation waits releasing workers; future rotation scheduling without reserving execution locks; due rotation priority and blocked/overdue alerts; shared-parent object conflicts; read observations during changes; crash/timeout recovery without overlapping uncertain provider writes. See specification AC37.

Primary references: [Procrastinate task locks and priority](https://procrastinate.readthedocs.io/en/stable/howto/advanced/locks.html) and [PostgreSQL lock lifetimes](https://www.postgresql.org/docs/current/explicit-locking.html). The runner documents that a high-priority job cannot preempt a running job and warns about locks on future-scheduled tasks; qualification must account for both.


## D5: accepted organization publication contract

Retain source snapshots and validation diagnostics independently from the currently applied organization. Normalize and construct a candidate effective hierarchy from the last trusted revision plus eligible source changes before opening the publication transaction. Preserve source scope, capture time, completeness and employee-row/reference evidence. Existing email matching, identity exceptions and supplemental-edge conflict rules continue to apply; staging does not bypass those rules.

Publish eligible person metadata, reporting relationships, derived LOB/routing state, qualified absence review items, change history, initial notification intent where needed and the new applied revision together. Preserve internal person IDs, tenancy ownership and shared memberships. Parse and validate outside the short publication transaction. Recheck the starting organization revision and relevant configuration revisions before commit; an intervening change requires rebuilding/revalidating the candidate, not overwriting it. Reject stale source snapshots and prevent concurrent duplicate application. Each hierarchy/routing read uses a consistent applied revision; cache entries and multi-query responses must not mix revisions.

Structurally invalid snapshots leave trusted state intact, with visible diagnostics. Eligible partial-feed updates can publish atomically without absence conclusions; unresolved ancestry remains visible. Only a qualified complete authoritative snapshot for the same population can generate absence review. Publication is automatic for valid metadata and performs no OCI lifecycle or access mutation.

Repeated delivery of the same source snapshot creates no duplicate changes or notifications. Equal normalized content captured on a later day is still new presence evidence; content equality alone cannot suppress refreshed observation times or replace source ordering/completeness checks. An ingestion crash before commit leaves the previous revision authoritative; a crash after commit resumes from the recorded applied revision and queued work.

Planned tests: valid reorg and unchanged ownership; stable person identity through reference enrichment; malformed, partial and stale snapshots; complete-census absence versus referenced-only managers; failure before/at/after publication; duplicate delivery and later captures with unchanged content; competing ingestions and intervening administrator configuration; consistently versioned hierarchy/routing reads. See specification AC38. The missing production feed metadata remains an external qualification gate.


## D6: accepted managed-object ownership contract

Create dedicated tool-managed IAM policies, quota policies and budgets rather than inserting managed fragments into owner-maintained objects. A stable logical managed item has an explicit binding to its owning scope, target scope and actual OCI object OCID. Keep binding/replacement history and the applied/verified item version. Display names and ownership markers assist discovery but do not by themselves authorize taking over an existing object. An imported tenancy's conflicting object or name collision requires review, without silently overwriting the existing object.

Owners retain full administration and may create their own users, policies, quota policies and budgets. Compare the declared managed settings through typed handlers, excluding irrelevant provider-generated fields. An owner edit to those settings is drift; unrelated owner-managed objects remain outside repair. Observe by the recorded binding and distinguish confirmed removal/modification from unavailable inspection. Administrator repair previews the intended changes, requires sufficient verified automation access and verifies the outcome. The baseline's desired configuration is authoritative for the managed settings, not for every object in the tenancy.

Record request/object identifiers before progressing to subsequent steps. Reconcile ambiguous creation/update responses to avoid duplicate objects; discovery conflicts require review rather than guessed adoption. Recheck observations before a repair and use OCI conditional updates where supported. A concurrent-edit conflict requires refreshed inspection/preview, not unconditional overwrite. Apply the D4 owning-object coordination rules for parent-side budgets that target a child. Exact per-type fields, limits, overrides, comparison rules and any adoption/removal workflow remain separate engineering details.

Planned tests: removed/modified managed objects; unavailable inspection; owner-managed objects untouched; import/name collisions; parent/child owning-versus-target scope; lost responses and duplicate dispatch; concurrent owner edits; repair access checks and post-write verification. See specification AC39. This is baseline configuration management, not the deferred security auditing capability.


## D7: accepted forecast source contract

Use OCI-native forecasts through the financial provider adapter; V1 introduces no linear extrapolation or other application-calculated fallback. Retain explicit source/method, target tenancy OCID, period boundaries, currency, collection time and available coverage/as-of information for actuals and forecasts. Compose a period-end total from provider actual/forecast segments without overlap or double counting, qualifying the exact response semantics with fixtures and real OCI data.

If OCI cannot provide a usable forecast, show Forecast unavailable with a reason such as insufficient history, unsupported query, access failure or collection failure. Preserve separately available actual cost and budget observations. A retained prior forecast remains visibly stale when current collection fails; it must not masquerade as current. Missing forecast data is not zero and cannot produce a healthy projected-spend indicator. Budget comparisons require matching scope, period, currency and cost basis; mismatch/unknown states stay visible rather than being silently converted or prorated. Exact financial basis, budget selection, cadence, freshness and warning thresholds remain engineering decisions.

OCI Cost Analysis documents history requirements and source delay; the Python usage request model exposes a forecast parameter. Neither establishes that every child-tenancy query will work under our eventual permissions/subscription setup. Qualify parent-side collection, per-child attribution, forecast availability and response coverage before release. The simulator must exercise both available and unavailable projections.

Planned tests: insufficient history/new tenancy; unsupported or failed collection; stale retained values; available actuals/budgets with unavailable forecast; no double counting of overlapping actual/forecast data; period/currency/scope mismatch; visible estimate provenance and no custom fallback. See specification AC40.

Primary references: [Oracle Cost Analysis and forecasting](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm) and [Python usage API forecast request](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/usage_api/models/oci.usage_api.models.RequestSummarizedUsagesDetails.html).


## D8: accepted hosting and access-context contract

Deploy into a dedicated compartment of a configured hosting tenancy. Its tenancy/compartment identifiers are independent from the organization parent and managed child identifiers. Terraform/deployment configuration must support H=P and H!=P without application business-logic changes. The actual hosting tenancy remains an organizational deployment decision; architecture review does not select or provision one.

```text
Hosting tenancy H / dedicated compartment C
  Application API and worker
    |-- hosting access --> Vault and hosting resources
    |-- parent access  --> organization parent P
    |-- child access   --> registered child T1..Tn

H may equal P or differ. Each access context selects its own target and identity.
```

Use distinct access contexts for hosting resources, parent-side organization/financial operations and each child's supported operations. A context identifies its target tenancy, region/endpoint, credential method and non-secret identity/secret references. Parent access supports workload identity where the service and deployment arrangement are qualified, or a dedicated parent API identity with its private PEM in Vault, using the same secure credential-resolution mechanism as child keys. Parent and child credentials remain separate, with permissions appropriate to their operations; being a child administrator is not parent authority. Do not infer parent credential selection from the hosting tenancy or substitute a child's signer.

The hosting identity must be able to retrieve necessary secrets independently of parent API credentials; this avoids using the parent key to fetch itself. Parent key loss becomes an explicit parent-access failure and blocks affected operations rather than prompting an implicit credential fallback. Keep private keys out of queue payloads, logs, exports and routine UI. Persist credential references and operation/provider identifiers so retries use the correct target context. Exact parent permissions, API-key rotation and out-of-band recovery runbooks remain qualification work.

Protect hosting, organization parent and control resources from tool-driven deletion in either placement. Keep the accepted Terraform/OKE/managed PostgreSQL approach and IMDSv1-disabled hosting VMs. Test H=P and H!=P in simulation, including wrong-target credential rejection, parent access revoked while hosting/child contexts remain usable, Vault access failure and secret redaction. Qualify actual parent service calls and child operations separately with real OCI; workload identity is not assumed to work for every cross-tenancy service. See specification AC41.

Primary references: [OKE workload identity](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm), [API signing identities and keys](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm) and [Vault secrets](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm).


## D9: accepted configuration override contract

**21 October2026 refinement:** D30 supersedes the D29 numeric-only approach. V1 uses one root
OTM policy and one quota object with administrator-authored complete statement lists; full-list
policy/quota overrides and a budget-amount override are allowed. Changed overridden baseline blocks
require explicit content-bound review. One root monthly budget has no alert rules; one root OTM
namespace contains baseline-only keys/static defaults. See the current
[configuration design](../engineering-design/03-templates-and-drift.md). New operations capture the
current published version; existing assignments change only through confirmed updates.

An assignment selects an immutable published baseline plus explicit per-tenancy overrides. Each supported configuration type declares the fields eligible for override and validates their types, ranges and applicable service constraints. The fully resolved configuration must also pass validation; a valid individual field does not establish a valid combination. Reject unknown/disallowed fields rather than silently dropping them. No arbitrary executable expressions or code plugins are introduced. Mandatory emergency/automation access expectations cannot be disabled through overrides.

Resolve published defaults and explicit overrides deterministically, preserving their provenance and the requesting administrator's history. Reuse the same validation/resolution logic in API preview and worker execution. Preview shows effective values and which values differ from baseline defaults. Capture baseline version, override revision and effective values for the started rollout under D1; later edits or new publications do not alter queued work. Checks and repairs compare against the recorded assignment, not a live overlay that changes during a task. A change to an override remains an explicit configuration/rollout action; organization metadata synchronization alone does not push changed budgets or quotas into OCI.

Keep tenant identity, credential selection and OCI object bindings separate from generic field overrides so a budget/quota edit cannot redirect work to another tenancy or signer. Exact allowable fields and safe policy parameter binding are part of each handler's schema; acceptance of override support is not permission to make every field overridable. Avoid additional implicit LOB inheritance layers in the initial resolution contract; shared baselines can be assigned to chosen branches through explicit rollout targets.

Planned tests: permitted budget/quota variations; unknown/disallowed fields and wrong types; invalid resolved combinations; attempts to disable required access or change target/credential bindings; baseline updates preserving existing assignments; stale preview/override revisions; identical API/worker resolution; retry after override editing using the original captured values; audit/provenance. See specification AC42. These tests are planned, not executed.


## D10: accepted provider result and error contract

Both stateful simulator and real adapters implement the same application-facing request/result contracts. Keep OCI SDK models and exception interpretation inside the real adapter boundary. Observations distinguish confirmed presence, confirmed absence and inability to verify, with capture/coverage metadata. Mutation results distinguish accepted/pending, verified completion, known failure/rejection and unknown outcome; accepting a provider request is not verified completion. Exact DTO names and capability-specific payloads follow interface design, without introducing one generic untyped result dictionary.

Preserve target/access context, application correlation, known OCI request/work-request/object identifiers and safe diagnostic status/code. Exclude credentials, signatures and raw secret-bearing payloads. Unknown or unmapped provider errors remain explicit uncertainty/failure rather than successful empty results. OCI NotAuthorizedOrNotFound and similar ambiguous errors cannot establish absence; a type/service-specific authoritative inspection must support that conclusion. Incomplete listing or unavailable scope is also insufficient evidence of absence.

Workflows use these contracts to update application state and decide whether to wait, fail or reconcile. An ambiguous write requires reconciliation under D3/D4 before repeating side effects. A transient error annotation alone does not authorize retrying a mutation. Qualify SDK retry settings and supported idempotency mechanisms per operation; do not let an adapter's default retries bypass the operation ledger or invent provider guarantees. Include partial item outcomes without claiming overall verified completion.

Shared contract tests exercise simulator behavior and real-adapter fixtures: confirmed/ambiguous absence, unavailable inspection, accepted asynchronous requests, delayed completion, known rejection, unknown writes, partial outcomes, request correlation and redaction. Adapter fixtures remain distinct from live OCI qualification. See specification AC43. Operation-specific permission/absence/retry evidence must be established during the real-provider milestone.

Primary references: [OCI API errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm) and [Python SDK retry behavior](https://docs.oracle.com/en-us/iaas/tools/python/latest/sdk_behaviors/retries.html).


## D11: accepted application API client contract

Backend request/response models define the application API and export OpenAPI. Generate typed client bindings for UI and CLI from that contract, using pinned compatible tooling. Exact generator selection remains a qualification task; support for the chosen OpenAPI/schema features must be demonstrated. Keep authentication/session acquisition, screen behavior, command prompts and display formatting in handwritten wrappers; do not maintain duplicate handwritten wire models or hand-edit generated code.

CI exports the schema deterministically, regenerates bindings and fails on unexpected differences. Stable operation identifiers and explicitly documented error/operation-state responses support predictable clients. Qualify timestamps, nullable fields, enums, configuration-type schemas and financial values so generation cannot silently change their meaning. Client typing does not replace server validation, authorization, deletion guardrails, warning acknowledgment or idempotency. Retry wrappers retain the original request identifier and never interpret acceptance as completed OCI work.

Planned tests: schema/client consistency; authenticated and unauthorized requests; documented validation/conflict/error responses; queued/waiting/failed/uncertain/verified states; required confirmation fields and request identifiers; retries after a lost response; supported schema constructs. See specification AC44. API/CLI authentication details and exact endpoint names remain integration design, not inferred from generator output.

Primary reference: [FastAPI OpenAPI client generation](https://fastapi.tiangolo.com/advanced/generate-clients/).


## D12: accepted database-restore recovery contract

A database restore is an explicit operational recovery event, distinct from an ordinary API/worker restart or deployment. Fence old workers/dispatchers and block normal external mutations before activating the restored application. The restore runbook/deployment controls must establish recovery mode independently of rows rewound by the restore; a restored queue cannot authorize its own release. Read-only discovery and reconciliation can compare restored intent/bindings with current parent/child OCI state and current Vault secret versions.

An authorized administrator reviews reconciled operations and explicitly releases eligible normal mutations. Release records actor, reason, recovery point, inspected evidence and selected operation IDs; it cannot waive current registration, parentage, protected-target, entitlement, access, version or manager/shared warning checks. Ambiguous outcomes remain blocked, not automatically replayed. Already completed creates/deletes/rotations cannot repeat merely because old queue entries survive. Reconcile notification outcomes before considering queued delivery; unknown delivery status remains visible rather than being treated as unsent.

Due/overdue credential rotation receives an urgent controlled recovery path and alerts, not silent suspension behind normal mutation release. Inspect the live identity/Vault state before changing credentials; insufficient evidence/access requires manual recovery. Keep the original deadline when known and record uncertainty when it cannot be recovered. Do not reveal stale credentials as though they were current. A recovery-mode bypass cannot silently restart ordinary fleet work. The exact runbook/interface and audit-history recovery mechanism remain engineering qualification work, including any evidence gap after the recovery point.

Planned tests: restore an older application/queue snapshot while simulated OCI/Vault retain later completed creation, deletion and password rotation; notification delivery after the recovery point; fencing the original workers; blocked dispatch before administrator release; current guardrails on released work; unknown external outcomes; urgent overdue rotation without stale disclosure; preserved independent hosting/parent/child contexts. Rehearse the managed PostgreSQL restore procedure separately in M5. Ordinary worker/API restart still resumes under D2–D4 without a restore approval gate. See specification AC45.

Primary reference: [OCI PostgreSQL point-in-time recovery](https://docs.oracle.com/en-us/iaas/Content/postgresql/point-time-recovery.htm). Restore affects database state, not the state of external OCI resources or Vault secrets.


## D13: accepted fleet-scan scheduling contract

Recurring coordinators enqueue per-tenancy checks for eligible managed targets through the durable runner. Use stable scheduling keys to deduplicate repeated triggers, record scan/target progress and retry independently. Configure concurrency, request timeouts and bounded backoff/retry limits; a slow or inaccessible child must not block healthy children. Track last successful verification separately from last attempted check and expose overdue work. Scheduler catch-up/deduplication must work even if a CronJob fires twice or misses a trigger.

Reserve worker/provider capacity for deadline-sensitive credential work, rather than relying only on priority after all slots are occupied by slow scans. D4's mutation coordination still applies; priority cannot preempt an uncertain OCI call. Failed checks report unavailable/unverified or overdue states under D10, not healthy zero/empty results. Exact concurrency, provider/service throttles, cadence and timeouts are qualified in the simulator and actual OCI environment rather than assumed universal limits. Parent-wide financial collection can use provider-supported batch queries; per-tenancy access checks do not require duplicating parent cost queries.

Dashboard requests read persisted observations with source/check freshness instead of synchronously calling OCI per visible row. Keep pagination/sort/filter deterministic, bulk-load related owner/manager/LOB/status data and inspect query counts during prototype validation. The bounded organization can be validated/recomputed in memory; no additional cache service or graph database is required by the reviewed scope. Concrete query plans, indexes, export streaming and memory bounds are measured with the eventual schema; indefinite history must not be loaded wholesale for routine fleet views.

Planned tests: the target fleet with injected latency/throttling and a failed child; repeated/missed triggers and recovery; independent retries and overdue status; preserved observed versus attempted times; credential rotation during a scan backlog; worker restart with no duplicate effects; dashboard reads without live provider calls; pagination/query count and history-export behavior. See specification AC46. These are planned scenarios, not measured performance results.

Primary references: [Procrastinate concurrency](https://procrastinate.readthedocs.io/en/stable/howto/production/concurrency.html) and [Kubernetes CronJob limitations](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/).


## D14: accepted notification-trigger contract

The user accepted Astra's proposed clarification. Required organization exceptions, access/configuration loss, accepted break-glass grants and unresolved rotation failures create durable operational notification intents automatically; manually composed notices require explicit preview/Send. Ordinary valid metadata changes do not each require an email. An alert never authorizes OCI creation, deletion, repair or rollout.

Resolve recipients against one applied organization/configuration revision and persist the selected identities/addresses/channels with intent. Retries retain that routing evidence; corrected sends create separately audited intents. Unresolved routing for these D14 notice families falls back to administrators; D50 lifecycle routing explicitly has no automatic fallback. Repeated unchanged incident observations do not duplicate initial alerts; recovery followed by a new loss creates a new incident. Grants remain individually notified. Known transient delivery failures use bounded retry; uncertain delivery remains visible and requires channel-specific reconciliation. Database-restore restrictions remain in force. D47 now selects email only for V1; exact approved email provider, sender/endpoints and integration behavior remain qualification gates. Slack is deferred.

Planned tests: unattended detection and rotation-failure alerts, grant intent before disclosure, event/intent rollback, no implicit repair/deletion, ordinary metadata changes, incident deduplication/recovery, frozen recipients after reorg, manual preview/Send authorization, routing fallback and uncertain delivery/restore. See specification AC47 and the D14 test cases.


## D15: accepted effective-organization storage contract

Store stable person identities separately from complete immutable effective organization revisions. Each successful publication contains retained and newly observed people, effective reporting edges and accountability facts with exact immutable input configuration. Atomically advance one current-head reference under D5. Historical reads select stored revision facts directly; they cannot join current mutable LOB/designee configuration into a past revision. Ordinary reorgs do not alter person IDs, tenancy ownership or shared memberships.

Corrections and accountability-configuration changes publish new coherent revisions rather than edit old ones. Duplicate source delivery points to the prior application; later capture with identical metadata still refreshes presence evidence. Live exception/delivery/operation state remains separately versioned evidence, not an implied frozen part of historical organization state. Exact schema fields, constraints, source-state DTOs and permission enforcement remain detailed implementation design and qualification.

Planned tests: old/new revision reads after reorg and designee edits; retained absent/reference-only people in complete effective state; same-revision edge references; atomic head/content publication under crashes/concurrent configuration changes; immutable published-content interfaces; duplicate versus later identical captures; stable tenancy-owner references. See specification AC48 and the organization design/test drafts.


## D16: accepted organization browsing contract

Select the latest applied organization revision when opening a current workspace and retain its ID through related branch/person navigation and pagination. New publication updates a banner offering explicit Refresh; it cannot silently swap records or turn a valid selected revision into a conflict. Refresh reloads the current head coherently, preserving valid controls and resetting page position as appropriate. Unknown/unavailable requested revisions produce diagnostics, never implicit fallback.

This read context freezes organization facts only. Current tenancy inventory, operation progress, check observations, incident resolution and delivery carry separate version/freshness evidence. Historical names/contacts cannot become current notification recipients simply because they are displayed. Actions obtain current previews and recheck server authorization/eligibility/guardrails at acceptance/dispatch; changed relevant facts require refreshed review/confirmation under existing workflow rules. Cache keys and read queries carry the selected organization revision. Exact routes/error codes and head-detection interval/transport remain design details, with no new websocket service required.

Planned tests: publish R2 while paging/navigating R1; banner without row replacement; explicit Refresh; back/deep-link context; historical contacts; separate live operation/incident evidence; unknown revision without fallback; current previews and guards after reorg/entitlement changes; revision-aware caching. See specification AC49 and page/data contracts.


## D17: accepted incomplete-manager-coverage contract

Retain a configured source's complete claim separately from assessed coverage. If required manager employee rows are missing, assess the census as incomplete, publish eligible unambiguous supplied metadata under D5 partial rules after effective-graph validation, preserve trusted missing facts/reference-only profiles and block census absence conclusions. Persist source-quality evidence/incident plus required administrator notification intent with publication. Missing input rows cannot be filled by previously stored profiles to establish complete census evidence. Later qualified complete capture is evaluated independently; the incomplete historical capture remains incomplete.

This is a coverage fallback, not an override of source trust/freshness, identity ambiguity, invalid graph or malformed-row rules. Explicit source-boundary coverage exceptions require the configured/qualified source contract. Successful metadata publication and population completeness are distinct dashboard facts. No organization metadata approval, autonomous cleanup or deletion is introduced.

Planned tests: missing new versus previously known manager profiles, valid name/manager updates with retained facts, old profiles resolving paths without authorizing absence, mixed identity/graph/stale failures, declared/assessed UI status, atomic incident/alert persistence and duplicate initial-alert suppression, later complete capture with independently qualified absence. See AC50 and detailed organization/feed/page/test contracts.

