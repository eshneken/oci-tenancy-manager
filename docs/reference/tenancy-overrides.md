# Tenancy overrides and staged baseline reviews

Qualified local simulation · Both saved instances upgraded to 0016 · Real OCI remains unqualified

[Baseline authoring](baseline-authoring.md) · [Existing update engine](configuration-updates.md) ·
[Accepted configuration design](../engineering-design/03-templates-and-drift.md) ·
[Proposed full data model](../engineering-design/10-configuration-data-model.md) ·
[Implemented override ER](../architecture/diagrams/tenancy-overrides-implemented.mmd)

## Scope and invariants

A tenancy can independently inherit or override its complete authored policy list, complete quota
list and positive whole-unit monthly budget amount. An override is an explicit full replacement of
that category, not an appended statement, automatic merge or mutation of a published baseline.
Tags always inherit. Currency, period, namespace, parent, provider scope and required identity/access
are not editable override fields. The existing simulator remains explicit; no OCI call, credential
or real managed-object qualification is introduced.

One immutable accepted tenancy-configuration revision keeps baseline and all three nullable override
values together. Desired configuration and last fully verified configuration are separate heads,
even when both reference the same baseline version. Editing a budget on baseline v1 creates another
configuration revision on v1; it does not publish/choose v2. An older baseline remains eligible as
an already-assigned editor context, while a new baseline-update plan always targets latest.

This checkpoint adds three tables through 0016_tenancy_overrides: otm_tenancy_configuration,
otm_configuration_plan and otm_configuration_plan_target, for 18 application tables. It adds two nullable
heads to existing otm_tenancy; prior rows/heads/intents are not backfilled or rewritten. The broader
30-table model, required-policy manifest/rendering, real bindings, continuous drift and production
qualification remain separate. The qualified schema contains 18 tables after 0016; both saved runtimes are upgraded with existing
data preserved. The effective hash here proves exact simulated authored resolution,
not a complete production IAM grant profile or verified access.

## Single-tenancy editor

Configuration offers Create tenancy override, opening the existing paginated/searchable registry
chooser. It displays type/owner and disables inactive or currently reserved children. Selection
opens /tenancies/{UUID}?override=1; active tenancy detail also offers Manage overrides. This is an
entry shortcut, not a new provider target/permission source.

The editor reads the currently assigned published baseline, desired immutable configuration if
present and current values. Each category has an independent enable checkbox. Enabling policy or
quota starts from its existing override, otherwise the assigned baseline; disabling sends null to
inherit that category. It does not delete the underlying managed object. Budget shows fixed currency
and monthly context with a positive whole amount. Tags and required automation/recovery access are
explicitly outside the form. An unavailable/busy/invalid child has can_edit=false; commands recheck.

The form freezes assigned baseline UUID, tenancy revision and desired configuration UUID. A later
publication/background read does not silently upgrade the editor or replace typed inputs. Statement
blocks use 1–50 complete strings, each 1–2,000 characters, preserving order. Text that exactly
matches the joined original retains its original array boundaries, including embedded newlines;
explicitly changed blocks split LF/CRLF/CR into nonblank physical lines. Each block permits 105,000 raw
characters. New/modified lines preserve nonblank whitespace rather than trimming or merging text.
Budget accepts positive whole units, up to 16 digits in the UI; the API uses an exact Decimal with up to 20 digits and four decimal places and canonical strings. Empty replacement arrays, blank statements, NUL/obvious PEM material
and fractional/nonpositive amounts reject. Null means inherit, never a disguised empty list.

Preview changes is an explicit read-only POST. Alongside replacement counts, it shows expandable
exact effective policy/quota text, with each
block labeled as Override or Assigned baseline. Another disclosure lists the inherited tag defaults
or explicitly says none are defined; monthly amount/currency remain visible in the summary. These
read-only values resolve the frozen assigned baseline plus the reviewed values, while the server
independently recomputes and fences the same intent. No additional effective-content API field or
provider observation is invented. Back to editing keeps local values; Cancel discards only local edits. Apply overrides commits an asynchronous acceptance, not a verified
result. It freezes a new configuration revision and uses the existing four-category worker/progress.
Reload configuration is deliberate and replaces editor context only after a successful read. Unknown
acceptance can be retried with the same reviewed values/request UUID or inspected in Operations;
no reload-durable client transaction coordinator is claimed.

Every accepted changed request gets a new revision through operation admission. A matching request
UUID/digest replay returns the existing operation/revision. Identical values with a different request
identity are not promised to be a content-deduplicated no-op; provenance is distinct from effective
provider text. Matching fake objects can skip mutation after fresh readback while the new accepted
revision still receives its own verification evidence.

## Baseline update with complete-list conflicts

Baseline updates retain the complete eligible single/fleet candidate set and all existing blockers.
Candidates compare desired and verified configuration IDs as well as baseline IDs. Same-baseline
unverified override changes cannot disappear merely because baseline v1 equals baseline v1.

A policy review is required only when a policy override exists and the old/new baseline policy
lists differ. Quota review follows the same independent rule. The view shows old baseline / new
baseline / current complete override for each affected category. There are exactly two choices:

- Use new baseline clears that category's override to null in the proposed accepted revision.
- Keep override retains the exact complete override list; no new baseline statement is merged in.

A budget override carries forward independently if target currency/period remain compatible. It
cannot silently convert to another currency. Changes to tags or budget alone do not manufacture a
policy/quota review. Unaffected override blocks carry forward. Editing an override remains a separate
single-tenancy action; it changes the source context and makes overlapping plan reviews stale.

Opening an update now explicitly creates a local draft plan. It stores the exact candidate proposal
snapshots/hashes, target baseline and owner/request identity, without changing desired pins,
reservations, effective objects or jobs. GET preview/read never creates a hidden plan. The resulting
?plan=<UUID> URL reloads the same owner-scoped plan. Closing a preview does not delete the plan or
apply its choices. Missing/other-owner plans share a safe not-found response.

Save review stages both required per-category choices with actor/time and increments the plan
revision. It records immutable configuration_review_staged audit, clearly saying no tenancy changed.
The review is content-bound to the original proposal hash, assigned/target baseline and source
configuration/revision. An unrelated boolean acknowledgment cannot satisfy it. The Reviewed · staged
section exposes saved decisions for rereading/editing before final acceptance.

A lost staged-save response is recovered by Reload saved review, not by assuming success or silently
creating another plan. SaveConfigurationReview uses an optimistic expected_revision, not a durable
request-key receipt: replaying a stale identical save can conflict after it already committed. Read
the saved choices/revision before retrying. Creating a plan does have actor/workspace/request-key
replay: the same key/scope returns its existing draft/stale/accepted view; another scope conflicts.

Any new baseline, altered registry/candidate membership, source configuration or reviewed context
invalidates the draft. Stale views retain their original publication/target evidence and cannot
Start; Reload preview explicitly creates a fresh plan rather than rebasing old choices. A plan
already accepted links its operation and cannot be accepted again as fresh work.

Every conflict and every other blocker in the batch must clear before Start update. Staging a choice
never changes one live tenancy or starts a ready subset. Final Start verifies plan owner/workspace,
source fingerprint, every proposal hash, latest target and complete membership under the workspace
lock. It then atomically inserts all immutable configuration revisions, one full operation intent,
all desired heads/reservations, accepted plan/target correlations and the native queued job. A failed
revision/target/audit/enqueue rolls the whole acceptance back. Child execution remains independent
only after that complete batch has been accepted.

## Immutable revisions, effective content and verification

New revisions retain previous_id plus revision_number+1 in the same tenancy/workspace. The baseline
publication and three override values resolve deterministically into BaselineContent; no separately
mutable baseline/override heads can drift apart. configuration_hash binds exact baseline ID/hash,
three explicit override values, simulated-config-1 and complete resolved authored content. It is
checked when loading a revision. Corrupt/missing nonnull heads fail closed; null heads are explicitly
legacy inheritance, not a fabricated accepted revision.

A worker validates exact frozen baseline, accepted immutable revision, current desired head and
previous verified context before provider work. It resolves an effective content envelope for the
existing fake-object facade without changing/publishing the original baseline row/hash. Policy,
quota, budget and tags retain their deterministic synthetic identities. Successful categories are
read before skipping writes; partial state and old full-verification evidence survive failures.
Only after all four local readbacks match do last_verified_configuration_id, verified baseline and
verification time advance. The same baseline ID with a newer desired revision is verification pending.
A successful child step stays skipped on retry; later publication cannot retarget its accepted content.

This resolution intentionally covers simulated authored values only. It does not implement the full
production required-policy manifest, renderer provenance, exact OCI identities, permission probes,
uncertain network outcomes or bound-object drift model. A real adapter cannot inherit the local
transaction/fake readback guarantees without separate qualification.

## New public and evidence contracts

The 10 override-specific DTOs contain 55 effective fields, counting inherited OverrideValues in
TenancyConfiguration and the standalone values model separately. Scope is always server/session-
owned; workspace_id is a SQL column, not a browser authoring field. Reused BaselineVersion and
existing receipt models are mapped in their own guides.

| Model | Every field | Meaning/defaults/bounds |
| --- | --- | --- |
| OverrideValues (3) | policy_override_statements, quota_override_statements, monthly_budget_override_amount | Each defaults null/inherit. Present lists 1–50 complete strings, 1–2,000 characters each; present budget positive whole Decimal 20/4 with canonical scale. No tag/currency/scope fields. |
| TenancyConfiguration (13) | Three OverrideValues fields; id, tenancy_id, baseline_version_id, revision_number, previous_id, operation_id, created_by, created_at, resolution_contract_version, effective_hash | Immutable accepted snapshot. Positive revision; required nullable previous UUID. Registered resolution simulated-config-1; 64 hex hash; server-generated ID, operation, actor/time. |
| OverrideEditor (7) | tenancy_id, tenancy_name, tenancy_revision, baseline, configuration, values, can_edit | Assigned published baseline, nullable desired revision and inherited/override values, with current registry revision and live edit affordance. Never a latest-version substitution. |
| OverrideContext (3) | baseline_version_id, tenancy_revision, configuration_id | Exact assigned baseline and positive tenancy revision; required nullable desired configuration ID. Binds editor intent, not permission. |
| OverridePreviewRequest (3) | context, tenancy_id, values | Closed read-only preview input; no request/operation identity, arbitrary batch or chosen baseline. |
| OverrideConflict (8) | tenancy_id, tenancy_name, old_baseline, overrides, policy_review, quota_review, policy_choice, quota_choice | Exact prior baseline (nullable type), current override values and required-review flags. Choices default null; only use_new_baseline/keep_override. |
| CreateConfigurationPlan (2) | client_request_key, tenancy_id | Required UUID and optional single child scope default null for fleet. Same owner/workspace/key replays same scope. |
| SaveConfigurationReview (4) | expected_revision, tenancy_id, policy_choice, quota_choice | Positive optimistic plan revision and exact target. Both choices default null; service requires choices exactly for required categories, neither missing nor unrelated extras. |
| OverrideReviewEvidence (5) | policy_choice, quota_choice, reviewed_by, reviewed_at, plan_id | Choices default null; required verified reviewer key/UTC time and durable plan UUID frozen into accepted target context. |
| ConfigurationReviewEvidence (7) | contract_version, plan_id, tenancy_id, baseline_id, proposal_hash, policy_choice, quota_choice | Fixed configuration-review-1 plus exact context/hash and nullable choices in immutable staged-save audit. Actor/time remain enclosing event facts. |

### Updated rollout models

The rollout module now has 12 DTOs with 76 effective fields, superseding the earlier 11-model, 57-field baseline-only map.
Old optional fields default compatibly. Every current field is listed here; unchanged private actor/
receipt models are not duplicated as new storage.

| Model | Every field | Change/authority |
| --- | --- | --- |
| ConfigurationOperationTarget (2) | tenancy_ocid, display_name | Existing exact single-child or null batch OCID plus display label. |
| ConfigurationTarget (13) | source_configuration_id, source_verified_configuration_id, configuration, overrides, review, tenancy_id, name, tenancy_ocid, parent_tenancy_ocid, organization_id, revision, source_baseline_id, source_verified_id | New IDs/configuration/review default null; overrides defaults all-inherit. Accepted configuration is the immutable new revision; source heads fence stale context. Existing exact target/scope/revision and nullable prior baseline IDs remain. |
| ConfigurationIntent (12) | change_kind, contract_version, kind, workspace_id, policy_revision, organization_id, parent_tenancy_ocid, administrator_id, authorization_revision, baseline, targets, target | change_kind defaults baseline_update, otherwise override_change. Existing configuration-update-1/kind defaults remain.1–500 unique scoped targets; any accepted revision must match its tenancy/baseline. |
| ConfigurationBlocker (4) | tenancy_id, name, code, operation_id | Fixed codes extend with OVERRIDE_REVIEW_REQUIRED/OVERRIDE_CONTEXT_UNAVAILABLE alongside existing busy/registration/provider codes. Optional conflicting operation defaults null. Context corruption can also fail the entire preview safely. |
| ConfigurationPreview (7) | conflicts, baseline, tenancy_id, ready_count, pending_count, blockers, preview_hash | conflicts defaults empty; existing latest/assigned baseline, full candidate counts/blockers/hash. Assigned baseline is used for override mode, latest for baseline-update mode. |
| ConfigurationUpdate (7) | plan_id, override_context, override_mode, overrides, client_request_key, tenancy_id, preview_hash | New plan/context/values default null and mode false. Override mode requires one child, values and context, and forbids a plan. Existing start route rejects authored override mode; dedicated route applies it. |
| ConfigurationPlanView (5) | id, revision, state, preview, operation_id | Derived draft/accepted/stale state, current staged preview/digest, optional accepted operation default null. Not a second execution state machine. |
| ConfigurationOutcome (7) | contract_version, tenancy_id, baseline_id, configuration_id, safe_code, category, verified_at | New nullable accepted revision UUID defaults null for old evidence. Existing closed safe codes/category/time continue. |
| ManagedConfigurationObject (4) | category, object_ocid, payload, payload_hash | Existing four synthetic category records; 700,000 character JSON bound and canonical hash, no real OCI binding proof. |
| ConfigurationTargetProgress (5) | tenancy_id, name, state, safe_code, verified_at | Existing per-child projection from immutable target/current step. |
| ConfigurationProgress (6) | change_kind, operation_id, state, baseline, targets, can_retry | New mode defaults baseline_update. Accepted recipe/targets and current supported-retry checks remain separate from latest. |
| ConfigurationRetryEvidence (4) | contract_version, baseline_id, configuration_id, safe_code | New optional revision correlation defaults null, preserving old payload parsing; existing fixed retry code/version. |

## Complete physical model

Migration 0016 adds 35 explicit columns across three new tables plus two nullable registry heads. There
are 18 application tables, not the full 30-table target. The [implemented ER](../architecture/diagrams/tenancy-overrides-implemented.mmd)
shows scoped FK relationships; old baseline and operation diagrams retain all other foundation fields.

### otm_tenancy_configuration — 14 columns

| Field | Type/meaning |
| --- | --- |
| id | UUID primary key; generated per accepted revision. |
| workspace_id | Required VARCHAR(256); part of scoped tenancy/baseline/operation references. |
| tenancy_id | Required UUID; composite FK to the exact registered child. |
| revision_number | Required positive integer, unique within workspace/tenancy. |
| previous_id | Nullable same-workspace/same-tenancy predecessor FK; insert guard requires immediately previous revision number, or 1 for null. |
| baseline_version_id | Required scoped published-baseline UUID; insert guard rejects unpublished parents. |
| policy_override_statements | Nullable JSONB; SQL NULL inherits, present bounded nonblank string array replaces authored policy. JSON null/empty arrays do not stand for inheritance. |
| quota_override_statements | Nullable JSONB with the same full-list/null distinction for quotas. |
| monthly_budget_override_amount | Nullable NUMERIC(20,4); positive mathematically whole when present. No currency/period override. |
| resolution_contract_version | Required VARCHAR(32), fixed simulated-config-1. |
| effective_hash | Required 64 hex VARCHAR(64); hash of registered authored resolution envelope, not provider authority. |
| operation_id | Required same-workspace operation UUID; FK is DEFERRABLE INITIALLY DEFERRED so new revision and operation/intent can commit in one transaction. |
| created_by | Required VARCHAR(256), accepting verified actor key. |
| created_at | Required UTC timestamp of acceptance, not eventual completion. |

The database blocks UPDATE/DELETE and ordinary TRUNCATE of immutable revisions. Scoped uniqueness
covers(workspace,tenancy,id) and(workspace,tenancy,revision). Application reads revalidate typed values,
baseline scope/content and effective_hash; an FK or stored digest alone does not prove semantic
integrity or successful application. No secret or raw provider document is stored in these columns.

### otm_configuration_plan — 11 columns

| Field | Type/meaning |
| --- | --- |
| id | UUID primary key for explicit local staging. |
| workspace_id | Required VARCHAR(256), FK to existing workspace; owner/session selects scope. |
| scope_tenancy_id | Nullable scoped tenancy FK; null means full eligible workspace candidate set. |
| target_baseline_version_id | Nullable scoped baseline FK; captures publication at draft creation, even if no publish exists yet. Such a plan cannot accept until rebuilt with valid target. |
| candidate_set_hash | Required 64 hex VARCHAR(64), exact source preview fingerprint. |
| client_request_key | Required UUID; unique with workspace and created_by for creation replay. |
| revision | Required positive optimistic staging revision; increments when a review saves. |
| created_by | Required VARCHAR(256), verified plan owner key; another administrator cannot read/review this draft by UUID. |
| created_at | Required server UTC creation timestamp. |
| updated_at | Required server UTC last staged save/acceptance time. |
| operation_id | Nullable scoped accepted operation FK; absent means not yet accepted. Accepted state is derived from this field, not a duplicate state column. |

### otm_configuration_plan_target — 10 columns

| Field | Type/meaning |
| --- | --- |
| workspace_id | Part of composite primary key and every scoped relation. |
| plan_id | UUID, part of primary key and composite FK to owning plan. |
| tenancy_id | UUID, part of primary key and composite FK to registered target. |
| proposal | Required JSONB object, a closed serialized ConfigurationTarget snapshot, not a free-form provider/override program. |
| proposal_hash | Required 64 hex digest of original proposal; checked on every staged read/review/acceptance, with target UUID correspondence. |
| policy_choice | Nullable use_new_baseline/keep_override staged choice. |
| quota_choice | Nullable independent choice with same enum. |
| reviewed_by | Nullable VARCHAR(256), last verified reviewer; paired with reviewed_at. |
| reviewed_at | Nullable UTC review timestamp; required when reviewed_by present. |
| accepted_configuration_id | Nullable scoped same-tenancy configuration FK; filled during whole-plan acceptance before the plan is sealed with operation_id. |

Draft updates can change only allowed staged choices/revision/acceptance correlations through runtime
privileges. New plans must start without an accepted operation; accepted plans reject UPDATE/DELETE,
and accepted targets reject later INSERT/UPDATE/DELETE. Installed-role, transaction and accepted-plan guard qualification passes in disposable PostgreSQL,
with the reviewed installer applied to both saved runtimes. No draft Delete/Discard
route is introduced. Ordinary TRUNCATE guards remain; exceptional local-reset authority is separate.

### Existing registry heads and compatibility

| Field | Meaning |
| --- | --- |
| otm_tenancy.desired_configuration_id | New nullable scoped(workspace,id,head) FK to configuration(workspace,tenancy,id). Moves with accepted baseline_version_id, reservation and operation intent in the same commit. |
| otm_tenancy.last_verified_configuration_id | New nullable equivalent FK. Advances only after full simulated verification; retains the prior accepted revision on failed/partial later updates. |

Existing baseline_version_id/verified_baseline_version_id remain compatibility/read projections and
must agree with their accepted configuration context. New reads reject mismatching nonnull heads;
they do not infer fresh overrides from fake-cloud state. Existing legacy rows receive no synthetic
revision or verified head. Two null heads retain prior baseline-only inheritance/verification rules;
a new accepted update creates the first revision chain explicitly.

Old intent JSON is hash-checked in its original stored form before optional model defaults parse it.
Existing baseline-only targets lack configuration/review and keep their original behavior; no old
operation/audit payload or hash is rewritten. Legacy start request digests use exactly the original
client_request_key,tenancy_id,preview_hash fields when new modes/plan are absent. New plan/mode values
enter the digest only when actually supplied/enabled. An old accepted key therefore recovers its
original receipt before a newly stale preview or changed current context is evaluated.

## HTTP and authority

| Route | Model/result and limit |
| --- | --- |
| GET /api/configuration/overrides/{tenancy-UUID} | OverrideEditor for assigned publication/current desired values; no implicit upgrade. |
| POST /api/configuration/overrides/preview | OverridePreviewRequest, application/json bounded 2 MiB before parse; read-only ConfigurationPreview. |
| POST /api/configuration/overrides | ConfigurationUpdate with override_mode=true, one child/context/values, no plan; 2 MiB. Queued ActionReceipt 202, nonqueued existing replay 200. |
| POST /api/configuration/plans | CreateConfigurationPlan, 4,096 bytes; ConfigurationPlanView 200; persists only local staging. |
| GET /api/configuration/plans/{plan-UUID} | Owner-scoped read/reload, including explicit stale/accepted state. |
| POST /api/configuration/plans/{plan-UUID}/reviews | SaveConfigurationReview, 4,096 bytes; updated staged ConfigurationPlanView 200. |
| POST /api/configuration/updates | Existing baseline/plan start; 4,096 bytes, rejects override mode. Accepts plan_id with exact preview_hash/scope; 202 queued/200 existing replay. |

Existing progress/retry endpoints and one native operation UUID job are reused. All commands run
under current HTTPS/Host/Origin/header, session/grant and workspace transaction checks. Missing/foreign
context, stale preview/revision, busy/invalid children and unresolved reviews fail before accepted
live work; errors are fixed 400/404/409/413/415/503 diagnostics, not reflected authored text or SQL.
Current can_edit/can_retry/read labels are affordances rather than reusable permissions. Private
configuration-plan and tenancy-override caches join normal logout/expiry clearing.

Staged reviews are Administration events with operation_id=null, typed proposal/plan/tenancy/baseline
context, human actor/time and configuration-review-1. Accepted operations freeze choices plus
reviewed_by/reviewed_at/plan_id in OverrideReviewEvidence; later retry never mutates them. Outcome
and retry evidence can carry nullable configuration_id. Existing friendly resource/audit projection
and safe CSV remain separate from raw immutable JSON; no general audit editor is introduced.

## Local reset and validation boundaries

The explicit owner-only local test reset adds the three new FK tables, increasing its organization/
registry/configuration set from 9 to 12. It may destroy test revisions/plans while preserving auth,
Operations and immutable audit; retained audit snapshots can outlive reset rows. Its owned-target,
opt-in, unsettled-work and transaction guards remain mandatory, without CASCADE. This is not a
production cleanup endpoint or authority to reset either saved installation.

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

These checks qualify the local simulator, immutable revisions, staged plans and application flow.
They do not qualify real OCI required-policy rendering, exact provider objects/permissions,
uncertain network effects, continuous drift or the remaining full V1/P3 scope. The proposed
30-table model remains a separate target.

## Inventory and editor field sources

TenancyView has 31 fields in the current source. These four additions expose the new heads and editor
eligibility without adding another mutable UI state or confusing historical completed operations
with current reservations. TenancyDirectory keeps its existing 12 fields and latest-only default.

| Read field | Source/meaning |
| --- | --- |
| desired_configuration_id | Nullable same-tenancy accepted revision head on otm_tenancy; current desired baseline/overrides must agree with its validated snapshot. |
| last_verified_configuration_id | Nullable same-tenancy last complete simulated revision head; can differ from desired while the baseline UUID is unchanged. |
| override_categories | Derived policy/quota/budget tuple for nonnull override columns joined from the exact desired configuration in this workspace/tenancy. Empty for inherited/legacy values. It is not provider drift evidence. |
| has_pending_operation | Current stored tenancy.operation_id is nonnull. This excludes current reservations in the chooser; the separate public operation_id can fall back to last_operation_id for history and is not the busy test. |

The inventory Override indicator and active-tenancy detail link open the assigned-version editor.
Latest baseline selection and full configuration verification remain separate; baseline equality
alone cannot show the current override revision as verified. The two configuration heads and
existing last-verification time provide that context. Editor checkboxes/text/amount come from
OverrideEditor.values or its assigned baseline, not from observed fake/provider objects.

## Manual review after qualification

Both saved runtimes are qualified on 0016. For this manual exercise, use an isolated synthetic
installation, preferably the separate 8444 runbook instance with its normal private enrollment. Keep the current organization; no reset or direct
SQL modification is needed. For the all-conflicts exercise, prepare two active synthetic children on
the same published baseline and use the normal local worker. These are optional operator review instructions after the completed qualification;
they do not authorize replacing saved data or running real OCI operations.

1. Open Manage overrides from an active tenancy. Confirm the displayed assigned baseline and current
   configuration. Preview a budget-only whole amount, then Cancel: assignments stay unchanged. Repeat
   and Apply; receipt is queued, with verification only after worker readback. Policy/quota inherit.
2. Enable a complete policy block and quota block (at most 50 nonblank statement lines each), keeping
   budget independent. Inspect Preview changes, use Back to editing and verify inputs remain. Apply
   and inspect selected versus last fully verified configuration in the resulting local progress.
3. Clear one category checkbox and preview/apply. That category inherits the assigned baseline;
   other overrides remain. No managed object is deleted and the assigned baseline is not upgraded.
4. Give two children statement overrides, then publish a new baseline changing the overridden blocks.
   Open Update existing tenancies. Review old/new/override full lists for one child and Save review.
   Its live assignment stays unchanged; the second unresolved child still prevents Start. A required
   unanswered category cannot be saved or bypassed through the API.
5. Reload the ?plan URL and inspect Reviewed · staged. Resolve the remaining exceptions using the
   two explicit choices. Start only after the whole batch is ready. Inspect one operation containing
   all accepted targets; verify Keep override retains its exact list and Use new baseline inherits.
6. Separately stage a new preview, then alter source configuration or publish another baseline in a
   second tab. The old plan must become stale and require a fresh preview, never silently rebase or
   start a subset. Inspect audit's staged-review and accepted-operation records with exact identities.
7. Leave failure injection, audit/enqueue rollback, revocation, SQL guards and concurrent deliveries
   to disposable automated fixtures. Do not change saved runtime permissions/database rows to mimic
   failures. No step performs live OCI actions or gives blanket approval to reset or publish Git.

The complete local unit/PostgreSQL/browser/review/installation gates pass as recorded above. The
59 generated schema artifacts match the qualified wire models; generated typing still does not
replace server authorization, transaction checks or separate real-provider qualification.


### Additional recovery and concurrency coverage

The new PostgreSQL cases race same-key and different-key override acceptance against the same
reviewed context. Same-key retries must share one operation/revision/job; competing different keys
allow one acceptance and reject the stale command. A forced enqueue failure must roll back the
new configuration revision, desired head, operation and audit together. These are real transaction
regressions, not a claim that unit stubs prove rollback. Browser coverage includes Back/Forward
restoration of the staged flow and focus after acceptance. These cases are included in the completed
local qualification; no real OCI behavior is inferred.

Local qualification receipt (private historical evidence; not distributed) · Independent review (private historical evidence; not distributed).


## Dedicated tenancy-detail section — 3 November 2026

UI refinement qualified and installed in both saved instances. Active tenancy detail now places Overrides in its own section, with
configured category names, an explicit all-inherited empty state, existing desired-versus-verified
status and the same Manage overrides entry. This separates override editing from baseline-update
progress; it adds no read/write fields, tables or alternative effective-content calculation. A
category list does not establish that OCI is healthy. Actual baseline/configuration IDs and verified
readback heads retain the authority described above.


## Observe accepted overrides without applying them again

The [configuration drift screen](configuration-drift.md), qualified and installed locally, resolves the same
assigned baseline plus immutable accepted overrides for expected read evidence. New publication,
budget inheritance or a draft edit does not change what that assignment means. Checks never save
an override, create a configuration revision or repair an object. Full four-category authorized
coverage is required before drift confirmation/resolution.
