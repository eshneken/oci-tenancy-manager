# Baseline updates for existing tenancies

Validated0015 foundation and inventory/audit/completion refinements installed · Local simulation only

[Baseline authoring/pins](baseline-authoring.md) · [Onboarding](tenancy-onboarding.md) ·
[Operations](operations.md) · [Audit History](audit-history.md) ·
[Implemented update ER](../architecture/diagrams/configuration-updates-implemented.mmd) ·
[Build order](../engineering-design/18-database-ci-and-build-order.md#baseline-only-configuration-updates)

This guide records the qualified 0015 baseline-only foundation and its presentation refinements.
The current 0016 application also includes [tenancy overrides and staged reviews](tenancy-overrides.md),
with 18 tables, immutable configuration revisions and updated rollout contracts. Its exact field
dictionary supersedes the older baseline-only counts below; legacy contracts/history remain readable.

## Actual checkpoint boundary

Administrators can preview an individual registered tenancy or the complete eligible fleet and
start an asynchronous update to the latest published baseline. The server freezes that version and
the entire accepted candidate set. All blockers must be cleared before acceptance; after acceptance,
children commit independently, so one blocked child does not undo successful children.

This is a transitional baseline-only simulator, reusing existing operation, step, audit and native
queue storage. No override editor, persisted preview/bulk-plan table, conflict-resolution plan,
configuration-revision table or real OCI adapter is introduced. There remain15application tables;
forward0015_configuration_updates adds three columns to existing otm_tenancy and expands closed
operation/step/audit kinds. Existing desired pins, onboarding, historical audits and legacy nulls are
preserved. No column/value is removed from the prior latest-only model.

The four managed categories are policy, quota, budget and tags. They are explicit local fake-object
records, not qualified real OCI bindings. In particular the tags record bundles namespace/default
intent rather than proving creation of every OCI namespace/key/default object. Policy holds the
authored statement list only; protected required-access composition, grammar, permissions and live
identity safety remain separate qualification gates. No credentials or OCI requests are involved.

## Operator flow and context

1. Configuration offers Update existing tenancies for latest-baseline work. An active tenancy detail
   offers Apply baseline when its selected version is already latest but unverified, or Update to
   baseline for a newer desired version. Opening old history never selects an older rollout target.
2. Open the confirmation to obtain a fresh coherent preview. It shows the exact target baseline,
   ready count, all exceptions and a pending-tenancy count. Pending onboarding tenancies keep their
   original setup pins and are not batch targets; return after they become active.
3. The target baseline can be inspected read-only inside the confirmation, with Back to baseline
   update returning to the same reviewed context. Cancel changes no desired pin or queue record.
   The confirmation initially focuses its heading. A blocked batch cannot start its ready subset.
4. Start update sends only a request UUID, optional single-tenancy scope and the reviewed hash.
   The server recomputes the complete preview under a workspace lock, then atomically writes all
   desired pins/reservations, immutable intent/audit and the native queued job. A receipt is acceptance,
   not verified completion. A stale preview requires explicit reload/review rather than a silent rebase.
5. Progress shows each frozen child and safe result, a verified count and View operation history.
   While queued/running it polls; a terminal issue exposes Retry incomplete updates only where the
   current server checks support that action. This retry keeps the same operation/baseline/targets.

A single-tenancy scope uses the same candidate and all-blocker checks as fleet scope. No published
baseline means no work can be accepted. An already-selected but never fully verified baseline is
still a candidate for simulated application. A tenancy with both selected and verified IDs equal
to latest is excluded from this update flow; that exclusion is not a current drift scan.

### Version links and return navigation

Selected/last-verified versions use exact published UUID links and show version numbers from scoped
baseline joins, not a fallback to latest. Tenancy detail keeps the two links distinct. The onboarding
panel links its immutable accepted pin, including an older pin after later publication. Audit baseline
targets open their exact recorded recipe. Parent-version links retain the permitted original context.

baselineHref/baselineReturn carry a validated returnTo path. Allowed return destinations are exact
local tenancy/operation UUID detail paths, Organization, Organization drift and Audit History; other
values fall back to Configuration. No external origin or arbitrary path becomes a return redirect.
The ordinary published-detail backlink names the initiating context. These are destination links,
not a promise to restore every prior filter/page/form value. Default configuration links return to
baselines. Inline workflow recipe views return to the containing confirmation without accepting work.

Configuration progress can be reopened at /configuration?update=<operation-UUID>; tenancy detail
also projects its current/latest configuration operation. Historical baseline query parameters remain
read-only. No generic retry action is added to the Operations list: contextual progress owns the
supported retry, while Operations retains immutable execution history. Its Open baseline update link returns to
/configuration?update=<operation-UUID>, including a frozen older baseline after later publication.
Both configuration-preview and
configuration-update caches join the private query inventory cleared on sign-out/session expiry.

## Candidate set and preview fingerprint

The read snapshot loads all registered rows in the authenticated workspace, optionally restricted
to the exact requested tenancy UUID. Unknown explicit scope fails instead of becoming fleet scope.
Candidates are active rows where selected baseline or last fully verified baseline differs from
latest, including null legacy pins. Pending rows are counted separately. Other inactive states are
not candidates. Rows are ordered by stable tenancy UUID before fingerprinting.

Every candidate is kept in the preview even if blocked. Fixed blocker codes identify unavailable
execution, invalid registered-child/provider/parent/organization scope, or another reserved operation.
The preview hash binds workspace, single/all scope, registry_revision, full latest BaselineVersion,
complete target snapshots and all blockers. Ready count equals candidates minus blockers; the hash
covers both, not only the ready subset. At most500targets can enter the closed accepted intent.
This is not a paginated or persisted plan and cannot be edited into a browser-selected subset.

Start checks live administrator/session authority and locks the workspace before exact request-key
replay and fresh preview comparison. A replay with the same actor/workspace/key and digest returns
the original receipt even after later publication; changed digest/kind conflicts. A new request with
changed hash, missing baseline, any blocker, empty targets or unavailable execution writes no accepted
batch. It freezes current administrator grant/revision, parent/organization/policy revision, full
published baseline and every target's IDs/scope/revision/prior selected/verified IDs.

All candidate desired pins move to the accepted baseline and reserve the same operation in one
transaction, incrementing each tenancy revision and the workspace registry revision. The previous
last-verified fields stay intact. Failure of any guarded target update, audit insert or transactional
enqueue rolls the entire acceptance back. This is atomic local acceptance, not an atomic fleet-wide
provider transaction. Later publications cannot change the accepted recipe or target membership.

## Simulated execution and partial recovery

One native delivery runs the batch, committing/releasing locks between children. The worker rechecks
immutable intent hash/actor/workspace, current initiating administrator grant and authorization
revision, trusted pause/parent/policy context and exact registered target on every child. The pending
tenancy must still be active simulated scope, reserved by this operation, at the expected accepted
revision and selected baseline. The exact published recipe must equal the frozen snapshot; latest
is never substituted at dispatch. A verified child step is skipped on retry, even if a later separate
operation has legitimately changed that child's registry pin.

For an incomplete child, the facade has separate apply and read methods over explicit fake-object
state. Deterministic synthetic IDs bind one logical object per category to the exact target tenancy.
Unexpected previous object IDs cannot be adopted by name. Canonical payload hashes and closed object
records are revalidated. The read path reconstructs the passed fake-object state separately from the
desired recipe and compares exact objects. State persists between attempts in configuration_observation;
this is not evidence of an independent live OCI service or a real database/provider round trip.

Local payload JSON uses ensure_ascii=false, preserving Unicode without unnecessary ASCII escape
expansion; the closed record allows at most700000characters, not a700000-byte network body. The
envelope accommodates valid maximum-size authored statement/tag values, including JSON-required
escaping. It does not loosen the baseline's50-item/2000-character and tag key/value/count limits.

Category order is policy → quota → budget → tags. Expected category failures preserve returned partial
fake state and record the failing category without advancing last complete verification. Successful
children clear their own reservation and advance verified_baseline_version_id/configuration_verified_at
only after all four comparisons succeed. The previous verified version/time on an incomplete child
is historical full-verification evidence; partial objects may now differ. It must not be presented
as fresh current health. configuration_verified_at is separate from onboarding tenancy.verified_at.

Fully verified children are not reapplied by retry. Incomplete children reuse their stored partial
object records. Each existing category is validated and read before mutation; if that observation
exactly matches the accepted desired object, the worker skips its write. This preserves already
matching categories, including a successful prefix, without trusting a prior success flag alone.
A failed read blocks that category rather than establishing absence or permission to recreate it.
The remaining categories still need successful readback before full verification advances.
Expected blocked outcomes do not stop processing the other accepted
children. An unexpected transaction failure rolls back that child's local changes, preserves earlier
committed children/reservations and puts the operation in needs_attention for supported recovery.
The simulator has no external effect to roll back. A real network adapter cannot be dropped into
these database transactions; split dispatch/reconciliation, provider IDs, read completeness and
uncertain effects must be qualified first.

Batch success requires a verified target step for every frozen child. Otherwise the batch records
needs_attention. Retry is restricted to the responsible administrator, valid current grant, matching
policy/scope and supported incomplete outcomes. AUTHORIZATION_CHANGED, TARGET_CHANGED and
LIFECYCLE_UNAVAILABLE require operator review rather than an invented automatic recovery. Repeated
retry while queued/running/succeeded returns the current receipt without another enqueue. A supported
retry atomically requeues the same operation and adds immutable configuration_retry evidence; it does
not freeze a newer baseline, expand targets, erase old attempts or roll back verified children.

### Actionable Operations badge

The runtime adds one count per configuration_update batch in needs_attention only when the currently
signed-in administrator is responsible and the same current policy/grant/outcome checks support its
retry. It does not count failed children separately or count an unsupported error merely because its
state needs attention. Other administrators can read history without inheriting a false retry task.
Read-only inspections and unsupported historical failures remain excluded. The existing lifecycle
contribution is separate; this configuration contribution is computed through its scoped retryability
service. A badge is a supported-action hint, never a permission token or guarantee of success. Do not
add deletion, acknowledgment, dismissal or forced completion to clear it.

## Complete contract dictionary

The11new closed DTOs contain57fields. Reused BaselineVersion, ActorIdentity, ActionReceipt and the
existing operation projections are mapped in their own guides. Nullable/derived progress fields
are views, not additional durable authorities. No command accepts provider credentials, raw SDK
options, arbitrary policies, actor claims or an editable batch target list.

| Contract | Every field | Source/defaults/bounds |
| --- | --- | --- |
| ConfigurationOperationTarget (2) | tenancy_ocid, display_name | Display/operation-directory envelope. OCID is exact for a single child and null for a multi-child batch; label is frozen child name or batch count. It does not choose scope. |
| ConfigurationTarget (8) | tenancy_id, name, tenancy_ocid, parent_tenancy_ocid, organization_id, revision, source_baseline_id, source_verified_id | Frozen same-workspace registry row. Positive preacceptance revision; previous desired/verified IDs are required nullable values. Exact OCIDs/parent/org remain dispatch guards. |
| ConfigurationIntent (11) | contract_version, kind, workspace_id, policy_revision, organization_id, parent_tenancy_ocid, administrator_id, authorization_revision, baseline, targets, target | Fixed configuration-update-1/configuration_update defaults. Full published BaselineVersion,1–500unique target tenancy IDs, closed trusted parent/org. Server-only accepted intent in existing audit, not a public authoring command. |
| ConfigurationBlocker (4) | tenancy_id, name, code, operation_id | Fixed TENANCY_BUSY/REGISTERED_CHILD_REQUIRED/PROVIDER_UNAVAILABLE. Optional conflicting operation UUID defaults null; no raw provider error string. |
| ConfigurationPreview (6) | baseline, tenancy_id, ready_count, pending_count, blockers, preview_hash | Nullable latest baseline and single scope; counts derived from the complete read snapshot, blockers include all exceptions. SHA256 fingerprint is64lowercase hex; no stored preview ID. |
| ConfigurationUpdate (3) | client_request_key, tenancy_id, preview_hash | Request UUID, optional exact tenancy scope default null for fleet, required reviewed hash. No browser baseline choice or omitted target list. |
| ConfigurationOutcome (6) | contract_version, tenancy_id, baseline_id, safe_code, category, verified_at | Fixed configuration-update-1; codes CONFIGURATION_VERIFIED/CONFIGURATION_UNVERIFIED/AUTHORIZATION_CHANGED/TARGET_CHANGED/LIFECYCLE_UNAVAILABLE. category defaults null and otherwise one of policy/quota/budget/tags; verified_at defaults null and is populated only for full local success. |
| ManagedConfigurationObject (4) | category, object_ocid, payload, payload_hash | Category enum; synthetic ocid1.<lowercase-kind>.oc1..otmsim... ID; payload JSON string2–700000characters, required object form and matching canonical SHA256. Never a qualified OCI object ID. |
| ConfigurationTargetProgress (5) | tenancy_id, name, state, safe_code, verified_at | Frozen target ID/name; pending without step, otherwise verified/needs_attention. Nullable safe code/time default null and derive from closed target outcome. |
| ConfigurationProgress (5) | operation_id, state, baseline, targets, can_retry | Operation row state, full frozen baseline and progress for accepted target list; can_retry is recomputed from current responsibility/authority/policy/safe recovery. It is an affordance, not authorization. |
| ConfigurationRetryEvidence (3) | contract_version, baseline_id, safe_code | Fixed configuration-update-1 and CONFIGURATION_RETRY_ACCEPTED; same baseline/operation identity, without rewritten target membership. |

## Database and field mapping

Historical migration 0015 added only these three fields to otm_tenancy, all nullable for legacy rows,
without backfilling verification or fabricated fake objects. That checkpoint retained 15 tables and
20 baseline columns. The current [0016 override model](tenancy-overrides.md#complete-physical-model)
adds three tables for 18 total; baseline columns remain 20. The earlier [abridged implemented ER](../architecture/diagrams/configuration-updates-implemented.mmd)
shows the reused identities and JSON evidence rather than creating another plan/step store.

| Stored field | Meaning/constraint |
| --- | --- |
| otm_tenancy.baseline_version_id | Existing desired/pinned published recipe UUID. Admission changes it for each accepted update; it is not completed verification. Same-workspace baseline FK. |
| otm_tenancy.verified_baseline_version_id | New nullable UUID, same-workspace baseline FK. Advances only after four successful simulated readbacks; historical last-complete baseline, not a permanent health verdict. |
| otm_tenancy.configuration_verified_at | New nullable UTC timestamptz paired with verified_baseline_version_id by CHECK. Last complete local configuration verification time, independent of onboarding verified_at. |
| otm_tenancy.configuration_observation | New nullable JSONB object. Explicit fake-provider category records, preserving partial state across attempts. Database checks object-or-null shape; closed per-record/hash validation is application-side. Not a full real-observation history store. |
| otm_tenancy.operation_id, last_operation_id, revision, updated_at | Existing reservation/current/latest-operation and stale-target fences. Success clears only its matching current reservation and advances revision. |
| org_workspace.registry_revision | Existing coherent-preview fence; advances at atomic acceptance and per-child publication. Deprecated current_baseline_id remains ignored metadata. |
| otm_operation | Existing kind gains configuration_update. One batch row stores actor/request digest, current immutable intent pointer, queued/running/needs_attention/succeeded state, stage, effect knowledge, revision and timestamps. |
| audit_event.data for operation_intent | Existing versioned IntentEventData holds ConfigurationIntent plus initiating ActorIdentity. Original stored JSON hash is checked before typed parsing; IDs/scope/actor must match operation. |
| otm_operation_step | One current target step keyed configuration:<tenancy-UUID>, intent_revision1, command_kind configuration_update. Inputs are empty; last_outcome is ConfigurationOutcome; state/evidence UUID/verified_at/attempt counter update while immutable events retain all attempts. |
| audit_event for configuration_outcome | Append-only ConfigurationOutcome with fixed worker identity otm-worker:configuration and snapshot kind=worker/subject=configuration. Carries operation and baseline/tenancy correlations, no private provider payload. |
| audit_event for configuration_retry | Append-only ConfigurationRetryEvidence with the responsible human actor, accepted retry time and same operation/baseline. No original outcome is edited. |
| Native queue record | Existing transactional enqueuer uses the accepted operation UUID. Runner job completion is separate from all-target business success. |

### Four local managed-object records

| Category | Exact payload derived from frozen baseline | Local identity |
| --- | --- | --- |
| policy | statements=ordered authored policy_statements | Deterministic synthetic policy ID from exact child OCID/category. Protected required-access composition is not included/proven. |
| quota | statements=ordered complete quota_statements | Deterministic synthetic quota ID from child/category. No real quota grammar/service-limit proof. |
| budget | monthly_amount=canonical decimal string, currency, period=MONTHLY | Synthetic budget ID. No actual budget API, billing eligibility, alert-list verification or cost observation. |
| tags | namespace=OTM, defaults=ordered static key/value entries | One synthetic tags bundle. Real namespace, key and root-default objects/bindings remain unqualified. |

### Screen/read projection sources

| UI fact | Model/authority |
| --- | --- |
| Selected baseline ID and version link | TenancyView.baseline_version_id from tenancy; baseline_version_number from scoped desired-baseline join. Exact UUID, never inferred latest. |
| Last verified baseline ID/version/time | TenancyView.verified_baseline_version_id/configuration_verified_at from the new columns; verified_baseline_version_number from a separate scoped join. Explicit simulation label. |
| Existing update progress on tenancy | TenancyDetail.configuration_operation_id from current operation_id or last_operation_id, only when that operation kind is configuration_update. |
| Latest recipe/ready/pending/blocker counts and target link | ConfigurationPreview frozen at confirmation open; full BaselineVersion read-only view. |
| Batch/child progress and Retry button | ConfigurationProgress, ConfigurationTargetProgress and current can_retry; accepted snapshot, not a new latest selection. |
| Operation history | Existing scoped Operations directory/detail, new kind/title and configuration:<UUID> steps with safe typed outcomes. Individual success may link the exact registered target; multi-child operation has no guessed single result tenancy. |
| Audit title/actor/baseline/resource context | AuditEntry validates ConfigurationOutcome/RetryEvidence. Configuration worker label is fixed; baseline_id links exact published recipe. New resources is a scoped derived display tuple alongside operation links, with no new audit-table column or CSV field. |
| Back to initiating context | Validated returnTo destination via baselineHref/baselineReturn, or inline recipe-preview close callback; no database field or action authority. |

## HTTP, retries and failure boundaries

| Route | Result/bounds |
| --- | --- |
| GET /api/configuration/updates/preview | ConfigurationPreview; optional exact tenancy_id UUID, otherwise full eligible workspace. Read-only coherent snapshot. |
| POST /api/configuration/updates | Closed ConfigurationUpdate; application/json,4096-byte streaming limit. HTTP202 when ActionReceipt.state is queued; HTTP200 for replay returning another existing state. No arbitrary recipe/target payload. |
| GET /api/configuration/updates/{operation-UUID} | ConfigurationProgress for same-workspace accepted configuration_update. |
| POST /api/configuration/updates/{operation-UUID}/retry | Empty request body only; ActionReceipt for the unchanged batch. HTTP202 for queued receipt, HTTP200 for another existing state; no new baseline/targets. |

Start/Retry OpenAPI declarations advertise both202queued and200existing-state receipt models.
All routes require explicitly composed services and current session/admin scope; unsafe requests use
existing HTTPS/Host/Origin/custom-header guards. There is no anonymous simulator fallback. Commands
and SQL work run through the existing service transaction boundary. Fixed diagnostics distinguish
404CONFIGURATION_TARGET_NOT_FOUND,409preview-changed/blocked/request-key reuse/unconfigured-workspace,
400INVALID_CONFIGURATION_UPDATE,415CONFIGURATION_JSON_REQUIRED,413CONFIGURATION_COMMAND_TOO_LARGE
and503CONFIGURATION_SERVICE_UNAVAILABLE. No raw SQL/provider exception, credential or authored recipe
is reflected into an error string. Authentication failures keep ordinary session semantics.

The backend request key is durable for a known unchanged start command. The current browser keeps
that key for retries of its open preview; it is not a reload-durable mutation coordinator. Closing/
reopening obtains a fresh preview/key. After uncertainty, inspect existing progress/Operations before
starting again. Reservations and full preview validation remain server-side gates. A real OCI writer
requires separately qualified durable recovery UX and uncertain-effect reconciliation. Neither HTTP202
nor a native job receipt means that every child, or even the first child, has completed verification.

## Validated foundation and remaining work

The original0015baseline-only checkpoint is implemented, validated and installed on both saved local instances.
Unit, PostgreSQL, HTTP/browser, restricted-role migration, native execution, attempt/replay/rollback,
matching-category recovery and independent reviews pass. Private backups and old-column fingerprints
verify preservation of all existing data. Real OCI operations, overrides and full P3 completion remain
separate qualification milestones. No reset, seed or Git publication occurred.


### Input envelope and navigation count

Managed-object payloads are canonical-hash-checked JSON strings bounded at700,000characters.
UTF-8 Unicode is serialized without ASCII expansion; the bound also covers worst-case escaped
non-NUL controls in all accepted50x2000statement and100tag inputs. This internal object format does
not enlarge the4096-byte admission command, which never accepts authored configuration text.
Operations counts only a current responsible administrator's supported configuration retries;
progress and repair remain linked from tenancy/Configuration. Individual acceptance focuses its
progress heading once rather than stealing focus on every polling result.


## Historical0015 foundation validation and operator exercise

960backend unit tests pass at96.4005%line coverage;229frontend unit tests pass at97.26%.
The full1,171-case backend/PostgreSQL/HTTPS-browser run passes with no failures/errors/skips.
A separate disposable PostgreSQL run advances time before a failed later update and confirms that
both the previous verified baseline and its timestamp remain intact. Source/contracts/purpose/docs
checks and independent documentation/security/UI reviews pass; scoped source and dependency scans
report no findings. Both saved local instances were backed up privately and upgraded to0015; all
existing columns/rows across15application tables have unchanged fingerprints.

Validation receipt (private historical evidence; not distributed) ·
[Manual test guide](../how-to/baseline-update-runbook.md).


## Inventory, completed receipts and friendly audit resources

This follow-up changes presentation and derived read models, not the database schema or accepted
baseline-update intent. The existing11rollout DTOs/57fields remain unchanged. New inventory fields
are nullable/default-null projections, and friendly audit resources supplement the same immutable
operation/audit rows. Validation and both saved-runtime refreshes pass; the refinement receipt below
records current evidence. The foundation receipt above retains its original source scope.

### Completion and inventory behavior

Individual update progress no longer stays as a completed task after that child verifies. When its
selected/verified fields already represent completed work and there is no current new eligibility
or visible error, the redundant update/progress block hides. A later publication can expose a new
update opportunity. In a multi-child batch, a verified child's detail need not retain another child's
unresolved work panel; the batch remains accessible through Configuration/Operations history.
Successful receipts stop polling and have no redundant Refresh progress button. Needs-attention work
retains current Refresh/retry/error guidance; it is not treated as successful terminal work.

A completed fleet receipt offers Acknowledge. This clears only the local receipt view and removes
its update query by navigating to /configuration. It sends no command, mutates no operation/audit,
changes no badge or permission, and does not acknowledge an unresolved issue. When no active tenancy
needs an update and no receipt is being shown, the default view uses a compact green status pill.
Acknowledgment is not a new durable field or an entry in administrative history; the original
completed operation remains reopenable by its URL.

The inventory Status cell now groups the selected baseline version link, Latest indication or a
compact upward link to the latest-version update workflow. It leaves future financial display space
available without inventing cost data or adding another configuration column. Latest means selected
baseline ID equals the newest published ID in this workspace; it does not mean fully verified,
healthy or free of drift. A different-version upward link opens the tenancy workflow; it neither
starts an update nor allows an older target choice. A null desired pin says No baseline assigned.

The operation link remains alongside the row's state/configuration context. When the resolved
current-or-last operation has completed_at, its visible label is the UTC calendar date only, without
a clock time. Otherwise it retains View operation/Review operation guidance. The read model still
carries the complete UTC timestamp, and the operation/audit time is unchanged; this is formatting,
not a loss of stored timing evidence or a new completion event.

### New derived read fields

| Public field | Source and meaning |
| --- | --- |
| TenancyDirectory.latest_baseline_id | Nullable UUID, default null; one scoped latest published row selected by version_number descending while loading registry state. Independent of inventory search/page. No workspace pointer read or new column. |
| TenancyDirectory.latest_baseline_version_number | Nullable integer, default null, from that same latest row; used with its ID to label Latest/update affordances, never a fully verified status. |
| TenancyView.operation_completed_at | Nullable UtcInstant, default null; existing otm_operation.completed_at for the same resolved row.operation_id or fallback last_operation_id already exposed by operation_id/state. Visible table label formats date-only in UTC. |
| AuditEntry.resources | New tuple, default empty, at most501 AuditResource values; derived for the current authorized page. No database audit-column, saved resource list, new CSV column or resource-name search predicate. |
| AuditResource.kind | Closed tenancy/person enum; controls a tenancy link versus an employee display label. |
| AuditResource.id | Required UUID from the validated original operation target/association or same-workspace registered tenancy match. It is context, not an action permission token. |
| AuditResource.name | Required1–320character label. Tenancy names come from current same-workspace registry rows; employee labels come from the accepted original intent display_name. These sources remain distinct. |

TenancyDirectory now has12fields and TenancyView27; unchanged inventory fields retain their existing
[registry mapping](organization-workflows.md). AuditEntry now has14fields, including resources, and
AuditResource adds3separately mapped fields. The existing [audit guide](audit-history.md) remains the
source for the other entry fields and unchanged12-column CSV contract. These counts describe public
DTOs, not new SQL columns or tables.

### Batched resource context and evidence limits

resource_context gathers operation IDs from the requested audit page, reads each original
operation_intent at intent_revision1 in the same workspace, checks its original canonical data_hash
and parses the closed intent with matching workspace. It loads registry ID/name/OCID mappings in
one same-workspace batch rather than one query per event. Current labels supplement the stored
historical event; this does not rewrite the immutable intent, original operation actor or audit JSON.

Configuration-update events include the frozen accepted target set; configuration_outcome narrows
context to its child. Lifecycle context includes frozen association tenancies and any pending
registered tenancy, plus the original employee target when the operation is person-scoped. Whole-
tenancy deletion does not mislabel the tenancy's display name as an employee. An exact target OCID
can resolve another registered tenancy context only inside the authorized workspace. Inspection-only
results may link their matching registered tenancy without adopting or changing it. Missing registry
rows do not trigger cross-workspace/name fallback or fabricate a new resource.

Audit targets keep their operation link and add friendly tenancy links/employee names alongside it.
More than three resources collapse under an affected-resources disclosure; smaller sets remain
visible. Employee labels are text, not an invented person-detail route. Current tenancy names are
explicit display context rather than proof of what a resource was called at the historical event's
time. Historical selected before/after facts remain in the existing immutable summary/changes.

CSV export is unchanged. It uses the existing safe12-column projection rather than adding resources
or current registry labels to the historical file. Resource context is constructed for the paged
read response only; no new export target record, outbox, audit event, scan or mutation is introduced.
Session/workspace checks still govern reads and action commands independently of clickable labels.

### Refinement qualification

Qualification passes:964backend unit tests at96.4268%line coverage,232frontend unit tests at97.21%,
and1,178combined backend/PostgreSQL/HTTPS-browser tests without failures/errors/skips. Direct
PostgreSQL races prove distinct-key contention admits one operation, same-key replay returns one
receipt, exactly one native job is queued and concurrent duplicate worker invocations emit one
verification per child. Projection/privacy checks, loaded responsive captures, independent reviews,
source/contracts and dependency/secret scans pass. Both saved runtimes retain0015 with private
backups and unchanged full fingerprints for all existing data across15tables. No schema migration,
reset, seed, baseline reassignment, audit mutation, real OCI call or Git publication occurred.
Refinement receipt (private historical evidence; not distributed).


## Separate observation path — 3 November 2026

The authored [on-demand drift check](configuration-drift.md), now qualified and installed locally, reads the
assigned baseline/overrides without invoking this update engine. Confirmation and current unknown
status remain separate; four complete reads are needed before confirmation/resolution. A check
does not advance this workflow's desired/verified pointers or mutate fake-cloud observations.
[Explicit selected-object repair](configuration-repair.md) is now implemented separately;
daily scheduling remains deferred until staging/Kubernetes.


### Explicit repair follow-up — 6 November 2026

Earlier read-only checkpoint statements excluding Repair describe the check foundation. The current
[explicit selected-object repair flow](../reference/configuration-repair.md) now adds a guarded modal
preview/confirmation and native worker verification. Checks remain read-only. No daily scheduler,
live OCI repair or local drift-injection control is enabled.
