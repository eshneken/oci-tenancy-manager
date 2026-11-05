# 10: proposed configuration data model and screen contracts

21 October 2026 full-model proposal; 0018 local subset qualified and installed, 3 November 2026

[Design hub](README.md) · [Configuration behavior](03-templates-and-drift.md) ·
[Implemented prototype ER](../../prototype/docs/organization-er-diagram.md) · [Screen authority](../ui-screen-authority.md)

## Scope and authority

This document catches the storage design up with accepted D30–D34 screens and behavior. It does
not change the working prototype, its ten tables, UI, data, or OCI objects. Names, fields and
constraints below are a **review proposal**. Existing behavior remains binding; a proposed table
cannot weaken it. The [existing SQLAlchemy schema](../../prototype/backend/otm/organization/schema.py) is
the authority for the retained prototype only. Current production-source tables are defined in
[storage metadata](../../backend/src/otm/storage/tables.py); the exact implemented subset is mapped
below and in the runtime guides. Existing operation/step/queue storage is reused, never recreated
as another configuration engine.

This slice proposes **eight configuration tables**, extensions to existing workspace/registry/
audit/outbox tables, and readable dashboard projections. It introduces no second organization
model, table per policy statement/tag value/status, separate override-history table, separate
attempt table, new service, migration or queue engine. The same intent records serve UI, API and
CLI. The [unified production model](11-production-data-model.md) supplies registry, identity/Vault,
financial, notification, scheduling and recovery fields. Migration/provider qualification remains open.

## Current subset versus full target

| Model | Current implementation status |
| --- | --- |
| otm_baseline_version | Validated 20-column publication/authoring foundation; latest-only new admission and frozen pins retained. |
| otm_tenancy_configuration | New 14-column immutable authored baseline+override revision in0016 source, without the future full required-policy manifest/rendering fields. |
| otm_configuration_plan | New 11-column owner-scoped staging source; not every future plan/candidate-generation field below is implemented. |
| otm_configuration_plan_target | New 10-column closed proposal/hash/review/acceptance staging source. |
| otm_configuration_check | Qualified 13-column immutable local child-attempt table in 0018; both saved instances upgraded. |
| Managed-object binding, proposed otm_tenancy_check, separate object observation and tenancy issue | Full proposed/provider model; the new bundled local check is not full OCI binding/access qualification. |
| Existing operation/step/audit/native queue | Actual reused foundation extended with closed context/evidence; no second job or audit store. |

The qualified 0016 schema has 18 application tables,20 baseline columns,35 columns across the 3 new
tables and 2 nullable existing-tenancy heads. Both saved-runtime upgrades and complete local qualification pass. [The complete runtime field guide](../reference/tenancy-overrides.md) and
[implemented ER](../architecture/diagrams/tenancy-overrides-implemented.mmd) distinguish all actual
fields from the full eight-table configuration target below. Prior receipts remain historical.

## The model in plain language

A published baseline is a reusable recipe. A tenancy configuration revision says **which recipe, authored policy/quota/budget overrides,
and required-access manifest were accepted for this tenancy**. OCI bindings
say which real objects OTM owns. Observations say what a particular check actually saw. Issues are
persistent episodes requiring attention; operations are the work to apply or repair configuration.

```text
Published baseline + tenancy overrides
                 |
        Accepted tenancy configuration revision
                 |                     |
        Desired pointer                | last complete verification
                 |                     v
     Plan -> accepted operation -> bound OCI objects
                                      |
                          observations of exact intent
                                      |
                       current issues + verified pointer
```

**Keep baseline and overrides together in one immutable tenancy revision.** Editing just a budget
creates a new revision referencing the same baseline. Updating the baseline creates another
revision, carrying forward only the explicitly accepted overrides. This records the actual unit
being applied and avoids independently moving assignment and override heads. This grouping is now used by the local0016candidate; the full real-provider required-manifest/
rendered-binding design remains proposed/qualified separately. Accepted full-list/amount behavior
does not change.

## Historical existing-versus-proposed inventory

| Storage | Status and purpose |
|---|---|
| Ten existing organization/registry/audit/outbox tables | Implemented prototype; preserved as the foundation |
| `otm_operation`, `otm_operation_step` | Existing C2 production proposals; acceptance, progress, retries and waits |
| Eight `otm_*` tables below | New C3 production proposal; none exist in the local database |
| Runner-owned tables | Procrastinate implementation storage, separate from business progress |
| Credential/access and usage storage | Proposed in chapter11; not hidden inside baseline JSON |

The original proposal therefore described ten new application tables across C2+C3, in addition to
the ten prototype tables. It is not a claim that the complete production system stops at twenty
tables. Later additions must justify their lifecycle and queries; they must not silently duplicate
these concepts.

## Common keys, scope and types

Use UUID primary keys and the existing string `workspace_id`. Every proposed table carries
`workspace_id`; parent references use composite foreign keys including workspace and, where
applicable, tenancy. Add the corresponding composite unique keys to referenced tables. A globally
unique UUID alone does not establish scope. Provider OCIDs are strings, never substituted for
application IDs. All timestamps are UTC `timestamptz`; amounts use exact `numeric`, not float.

Use stable authenticated actor IDs plus a display-name/email snapshot in history. No passwords,
private keys, MFA material, activation URLs or usable tokens enter configuration, observations or
audit JSON. Handler identifiers and versions come from a registered typed backend contract, not
user-supplied code. JSONB is for bounded versioned documents, not unconstrained SDK responses.

## Explicit configuration values and created object identities

The authoring values are now named database columns. JSONB is used only for a **typed list** where
OCI accepts a list, not as an opaque all-purpose configuration field. Tag default rows in the list
explicitly specify the key and static string value; namespace is a separate fixed column.

| UI field | Baseline column | Tenancy override column | Expected value |
|---|---|---|---|
| Authored policy statement textarea block | `policy_statements` | `policy_override_statements` | `COALESCE(override, baseline)` authored list + captured generated required-access list in one policy |
| Quota statements textarea/list | `quota_statements` | `quota_override_statements` | `COALESCE(override, baseline)` complete list |
| Monthly budget | `monthly_budget_amount` | `monthly_budget_override_amount` | `COALESCE(override, baseline)` exact amount |
| Currency / monthly / no alerts | `budget_currency`, `budget_period`; no-alert invariant | None | Fixed qualified context; expected alert list is empty |
| OTM namespace | `tag_namespace` | None | `OTM` |
| Defined tag key/static value rows | `tag_defaults` | None | Create definition per key and root default with that value |

For example, one `otm_baseline_version` row stores the following values directly:

| Column | Example stored value |
|---|---|
| `version_number` | `2` |
| `policy_statements` | `["Allow group OTMOperators to read all-resources in tenancy"]` |
| `quota_statements` | `["set compute-core quota standard2-core-count to 8 in tenancy"]` |
| `monthly_budget_amount` | `200.0000` |
| `budget_currency`, `budget_period` | `USD`, `MONTHLY` |
| `tag_namespace` | `OTM` |
| `tag_defaults` | `[{"key":"Environment","value":"Engineering"},{"key":"ManagedBy","value":"OTM"}]` |

Each policy/quota array element is **one complete statement**. Each tag element is one defined-tag
key plus its static root-default value. There is no separate row per policy statement and no free-form
configuration blob to interpret. The sample statements are illustrative, not OCI grammar or permission
qualification. Amounts shown here are decimal database values, not binary floating-point values.

A shared tenancy assigned this baseline can have one `otm_tenancy_configuration` row containing:

| Column | Example stored value / meaning |
|---|---|
| `tenancy_id` | The shared tenancy's local registry UUID |
| `baseline_version_id` | FK to the baseline row above |
| `policy_override_statements` | SQL `NULL`: inherit the baseline list |
| `quota_override_statements` | SQL `NULL`: inherit the baseline list |
| `monthly_budget_override_amount` | `500.0000`: replace the baseline amount |

Its effective policy and quota inherit, its monthly budget is 500, and both tags inherit. For a policy
override, the column instead contains the entire replacement statement array. No statement-by-statement
merge is performed. Applying those values creates or updates separately bound OCI objects as shown below.

[Existing JSON fixtures](../contracts/configuration-examples/baseline-v2.json) remain a useful
facade/authoring envelope: `policy.statements`, `quota.statements`, `budget.monthly_amount` and
`tags.defaults` are assembled from the explicit columns. There is no competing persisted `document`
or `overrides` source to update. Schema/resolution versions define decimal encoding and canonical
hashing; the provider adapter receives the reviewed versioned envelope.

**Object OCIDs live in `otm_managed_object_binding`, not in the reusable baseline.** For one tenancy:

| Logical key | Binding identifier | Query/compare |
|---|---|---|
| `policy/main` | Policy `provider_ocid` | Read this exact policy, compare complete expected statements and root scope |
| `quota/main` | Quota `provider_ocid` | Read this exact quota policy, compare statements/root |
| `budget/main` | Budget `provider_ocid` | Read amount, period, root owner/target and complete alert-rule state |
| `tags/namespace` | Namespace `provider_ocid` | Read namespace name/state/root |
| `tags/key/environment` | Tag definition `provider_ocid` | Read definition under bound namespace |
| `tags/default/environment` | Tag default `provider_ocid` | Read root default, referenced definition and static value |

Every binding has a tenancy FK, logical key, provider kind and generation; definition/default rows
retain parent binding FKs. A policy override updates the same policy OCID. A verified missing object
may require explicitly reviewed recreation, recording a new binding generation and preserving the
old ID/history. A failed read never proves the object is missing. Names cannot substitute for OCIDs.
See [Oracle policy](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/models/oci.identity.models.Policy.html),
[quota](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/limits/models/oci.limits.models.Quota.html) and
[budget](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/budget/models/oci.budget.models.Budget.html) models.

## 1. `otm_baseline_version`: the reusable recipe

| Field | Type / rule |
|---|---|
| `id`, `workspace_id` | UUID PK; scoped workspace FK |
| `version_number` | Positive integer; unique within workspace; allocated transactionally |
| `based_on_id` | Nullable same-workspace FK to a published baseline copied into this draft |
| `schema_version` | Registered authoring/resolution format version |
| `policy_statements` | Required JSONB array of complete administrator-authored IAM statements; required access is separate; nonempty |
| `quota_statements` | Required JSONB array of complete quota statement strings; nonempty |
| `monthly_budget_amount` | Required positive `numeric(20,4)`; qualified currency precision validated |
| `budget_currency` | Required qualified currency code; not guessed from deployment region |
| `budget_period` | Required string constrained to `MONTHLY` in V1 |
| `tag_namespace` | Required string constrained to `OTM` in V1 |
| `tag_defaults` | Required typed JSONB array of `{key: string, value: string}`; key uniqueness case-insensitive |
| `content_hash` | Digest of canonical envelope derived from these explicit fields; never authorization |
| `edit_revision` | Positive optimistic-concurrency counter for the editable draft |
| `created_by`, `created_at` | Required author and time |
| `published_by`, `published_at` | Both null for draft, both required once published |

Drafts are editable through expected-revision checks; published rows are immutable, including
nested statement/tag arrays. Permit at most one editable draft per workspace for V1. Unique version numbers may
have gaps after abandoned drafts; deleting/reusing published numbers is forbidden. No separate
baseline-family table is needed for the accepted single lineage. The latest published version is derived by workspace and descending version number. The retained
`org_workspace.current_baseline_id` is deprecated historical metadata and has no selection authority.
The organization LOB/designee `configuration_id` retains its separate meaning.

These baseline columns contain one complete authored policy statement array and one complete quota statement array,
one root monthly budget amount and qualified currency context with no alert rules, and OTM defined
tag keys/static values/default intent. No tag override, arbitrary handlers or user/group editor.
Definitions/defaults are distinct provider objects even though the authoring document groups them.
Structural schema/decimal validation is not proof of OCI grammar, permissions or access safety.

## 2. `otm_tenancy_configuration`: one accepted tenancy revision

| Field | Type / rule |
|---|---|
| `id`, `workspace_id`, `tenancy_id` | UUID PK; scoped registry FK |
| `revision_number` | Positive integer; unique per tenancy |
| `previous_id` | Nullable same-tenancy FK; immutable chain of accepted configurations |
| `baseline_version_id` | Required FK to an immutable published same-workspace baseline |
| `policy_override_statements` | Nullable JSONB authored IAM statement list; null inherits; present list replaces authored block only |
| `quota_override_statements` | Nullable JSONB array of complete quota statements; null inherits; present list replaces whole block |
| `monthly_budget_override_amount` | Nullable positive `numeric(20,4)`; null inherits |
| `required_policy_manifest` | Required closed JSONB generated-entry list with immutable assignment/profile/template/binding provenance; never editable in the baseline/override form |
| `required_policy_manifest_hash` | Canonical digest of exact manifest and contributors, checked at preview/acceptance/dispatch |
| `policy_render_contract_version` | Required pinned registered renderer version; missing version blocks rather than substituting latest |
| `resolution_contract_version`, `effective_hash` | Required resolution contract and complete desired-content digest, including authored values + required manifest/render version |
| `operation_id` | Required scoped C2 operation FK that accepted this revision |
| `created_by`, `created_at` | Required actor/time; immutable |

These are concrete database columns, not keys hidden in an untyped `overrides` blob. SQL NULL
means inherit; present policy arrays replace the authored category; quota arrays replace the whole quota category. JSON null, empty or malformed
arrays are rejected, not interpreted as delete. Budget is positive exact money; no currency/period/scope
redirect. Tags always inherit. Keep source provenance for copied lists in the accepted operation/
plan evidence; do not infer their history from current strings. Do not mutate this row on retry.

Resolve the immutable baseline plus the three override columns deterministically. Provider normalization and
late OCI group/target binding are versioned separate steps; `effective_hash` describes complete desired
intent, including the required manifest, not proof of successfully rendered OCI policy or live access. Bound rendered
payload/evidence belongs to the immutable operation step and subsequent observation. D35 fixes the authored/generated composition model below; exact registered profiles, grammar and
provider permission behavior remain qualification gates.

Extend `org_tenancy` with nullable **desired_configuration_id** and **last_verified_configuration_id**
FKs to this same tenancy, plus `configuration_generation` and `current_configuration_check_id`.
The desired pointer changes only on accepted configuration intent. Increment
`configuration_generation` when desired intent changes, binding identity/retirement changes, and
before/after any relevant mutation attempt, including repair that keeps the same config/OCID.
A failed/unknown mutation retains its C2 exclusion/reconciliation obligation; checks overlapping it
cannot publish healthy coverage. This observation-generation token is distinct from C2 worker
ownership/execution generation and does not freeze a credential version. The verified pointer records
last complete verification, not a permanent statement of current health. Fresh drift may exist
against that same version; the dashboard reads observations/issues as well as pointers.

Create/import acceptance can register a pending tenancy and pin its configuration **before its real
OCID exists**. Production registry lifecycle must therefore include pending setup. Provider OCID is
null until discovery/verification; never invent an OCID/name to satisfy an FK. Assigned configuration
is not active ownership or proof of completed onboarding. Existing simulated `active/deleted`
registry status is not reused as a production lifecycle state machine without migration design.

## D35 required-policy manifest and rendered evidence

D35 A keeps all authored/required statements in one bound root policy. The new immutable
configuration fields above pin generated intent without an independently writable policy head or
new table. For example, a tenancy on baseline v2 with a 500 budget override can have a later local
configuration revision on the same v2 after adding a shared-member root-policy requirement.

`required_policy_manifest` is a bounded array. Each entry has the following explicit fields:

| Entry field | Type and source |
|---|---|
| `entry_key` | Stable logical required-grant key, unique in the manifest |
| `profile_reference`, `profile_version` | Pinned registered access profile, not an uploaded program |
| `statement_template_key`, `template_version`, `statement_template` | Registered immutable template identity/version and captured statement text; all must agree with its qualified contract |
| `bindings` | Closed named parameter map to same-tenancy/domain logical keys and optional already-known binding IDs; no fabricated provider IDs |
| `contributor_assignment_ids` | Nonempty stable source access-assignment UUID list, validated same workspace/tenancy; retain all contributing obligations |

Accepted planned assignments use stable logical subjects/purposes while provider identities are
not yet created. Optional known binding snapshots stay immutable; the operation later resolves
logical references. Do not mutate an accepted assignment/configuration to fill in new OCI IDs.
The manifest is generated by the backend from the accepted access workflow. Public authoring
commands accept authored values only and reject caller-supplied generated manifest/render fields.
The manifest includes reviewed pending/retiring obligations necessary for safe transition; it is
not an arbitrary browser document or a query of current feed names. Empty generated intent is valid
only when the qualified profile contract proves no statements are required; it cannot drop mandatory
owner/automation/recovery requirements by omission.

Once dependencies are resolved, append a typed immutable `audit_event` of kind `policy_rendering`
with `configuration_id`, operation/intent/step references, exact tenancy/policy binding context and:

| Rendering field | Meaning |
|---|---|
| `authored_policy_statements` | Baseline/override-resolved complete authored strings |
| `required_policy_statements` | Complete generated strings, stable entry order |
| `effective_policy_statements` | Authored then required, exact duplicate strings emitted once |
| `required_policy_manifest_hash`, `policy_render_contract_version` | Exact captured source/renderer |
| `resolved_binding_inventory`, `binding_set_hash` | Verified actual domain/group/compartment IDs and binding generations used in rendering |
| `statement_provenance` | Each emitted string’s authored/required origin plus entry/contributor references; duplicate output retains every source |
| `rendered_policy_hash` | Digest of exact provider payload; not a permission proof |

The event is scoped to the configuration and resolved binding context; a matching retry returns
the same rendering, a conflicting result fails closed. SDK dispatch consumes this reproducible
payload/evidence. Immutable step inputs reference logical intent; append rendering evidence rather
than rewriting those inputs with late provider facts. Observations name `policy_rendering_event_id`
in their typed expected-source evidence, and compare the full policy against the captured list. If
no current render can be established, report pending/unable to verify rather than green or missing.

A manifest change creates a new tenancy configuration revision atomically with the accepted access
operation, preserving authored baseline/overrides. Thus the same desired-configuration pointer and
observation generation cover access-driven root-policy changes; no second policy-composition head
is introduced. If output strings are unchanged, skip the SDK write while preserving new provenance.
Relevant manifest/profile/binding changes invalidate stale plans; full batch reviews remain required
before any target starts. An owner transition retains overlap until replacement access verifies.
Removing one contributor never removes a statement still required by another. Unknown prior writes
retain the normal C2 exclusion. Registered profile changes do not auto-update existing intent.

No new baseline field is added for generated access and no second managed policy is created.
Existing D30 fixture resolution is the **authored phase**; D35 composition adds the manifest/render
phase. Older example `effective_hash` values are authored-only fixture hashes, not current production
complete-intent hashes or proof of granted authority.

## 3. `otm_configuration_plan`: editable review before work

| Field | Type / rule |
|---|---|
| `id`, `workspace_id` | UUID PK; workspace FK |
| `kind` | `baseline_update`, `override_change`, or `repair` |
| `target_baseline_version_id` | Required published baseline FK; repair/override uses the current assigned baseline |
| `state` | `preparing`, `review_required`, `ready`, `accepted`, `cancelled`, `stale` |
| `revision`, `candidate_set_hash`, `candidate_epoch` | Optimistic edit counter, complete sorted candidate/context digest, and workspace candidate generation captured at preview |
| `created_by`, `created_at`, `updated_at` | Required draft ownership/history context |
| `accepted_by`, `accepted_at`, `operation_id` | Null before acceptance; atomically recorded with accepted root operation |

Plan state is a cached summary, never the only acceptance guard. A baseline batch captures the
complete eligible older-version candidate set; no skip/deselect path. Single override/repair plans
have exactly one target. A zero-candidate baseline plan shows No tenancies need updating and cannot
start an operation; empty scope is not a successful rollout. Saving a draft/review writes staged plan data and audit only, not accepted
configuration, job or OCI state. Pure GET/preview calculation remains read-only; explicit Create
plan / Save decision are local draft commands, distinct from C2 operation acceptance.

Publication and current-for-new selection are separate from plan acceptance. A draft editor cannot
alter a published target. Changing the target or any relevant candidate/review context invalidates
the plan and regenerates its preview; queued operations keep their accepted inputs.

## 4. `otm_configuration_plan_target`: one candidate, bounded review data

| Field | Type / rule |
|---|---|
| `workspace_id`, `plan_id`, `tenancy_id` | Composite PK `(plan_id, tenancy_id)` plus scoped plan/tenancy FKs |
| `source_configuration_id` | Required same-tenancy revision seen at preview |
| `expected_generation`, `binding_set_hash`, `eligibility_hash` | Required context for stale-preview checks |
| `proposed_policy_override_statements` | Nullable replacement list; null proposes inheritance |
| `proposed_quota_override_statements` | Nullable replacement list; null proposes inheritance |
| `proposed_monthly_budget_override_amount` | Nullable exact money; null proposes inheritance |
| `review_decisions` | Bounded JSONB map for policy/quota only; exact old/new/override digests, choice, actor/time |
| `repair_selection` | Versioned closed JSONB array required for repair only: logical key, source check/observation key, expected binding ID/generation and exact intended change/preconditions; nonempty, no duplicates/cross-tenancy references; null otherwise |
| `proposal_hash` | Digest of exact target content and review context, including repair selection |
| `accepted_configuration_id` | Nullable same-tenancy FK populated for accepted update/override; repair creates no new revision |
| `operation_id` | Nullable same-tenancy child/target operation FK after acceptance |

A block decision is exactly `use_new_baseline` or `keep_override`. Missing decision is unresolved.
Use-new sets that proposed override column to SQL NULL; keep preserves its complete list.
Several block decisions count as one tenancy exception. No per-statement or per-choice table is
needed; at most two current block decisions per target, with append-only change evidence in audit.
Changing an override separately invalidates pending target evidence, even if the plan still says
Ready. Repair freezes selected logical object keys and current binding context in the persisted `repair_selection` field;
copy that exact selection into accepted C2 operation intent. It cannot be reconstructed from current drift at dispatch, become an override, or authorize replacing unrelated objects.

At D31 acceptance, lock/recheck the authoritative plan and **all** targets, source revisions,
candidate membership and eligibility. All reviews must be resolved. Refuse stale, omitted,
duplicate or incomplete scope before any accepted revision/job write. Commit the complete batch's
accepted target configuration revisions, desired pointers, operation intent, audit/outbox intents
and initial durable job atomically. Child execution may be scheduled through the committed root
operation; no job runs before commit. Exact Procrastinate transaction integration remains a pilot
qualification, not something this proposed schema proves.

## 5. `otm_managed_object_binding`: which OCI objects belong to OTM

| Field | Type / rule |
|---|---|
| `id`, `workspace_id`, `tenancy_id` | UUID PK; scoped registry FK |
| `logical_key` | Stable managed identity such as `policy/main`, `quota/main`, `budget/main`, `tags/namespace`, `tags/key/environment`, `tags/default/environment` |
| `kind`, `handler_contract_version` | Registered object kind and version |
| `generation`, `replaces_id` | Positive per-logical-key generation; nullable prior binding FK |
| `parent_binding_id` | Nullable same-tenancy parent; namespace → definition → default dependency |
| `provider_ocid`, `owning_scope_ocid`, `target_scope_ocid` | OCID required for policy/quota/budget/tag/compartment kinds; explicit owner/target scopes |
| `identity_domain_binding_id`, `scim_resource_id` | Separate domain FK / SCIM ID for identity kinds; never store a SCIM ID as an OCID |
| `subject_binding_id`, `target_binding_id`, `provider_resource_type` | Typed endpoints/resource type for group/role membership; qualified tuple may identify relationships without an OCID |
| `ownership_mode` | `managed` or `observed_reference`; observed built-in/domain objects are never eligible for destructive managed retirement |
| `state` | `provisional`, `active`, `retired`, `replaced`; a typed authoritative provider identity is required; OCID remains mandatory for configuration objects |
| `created_operation_id`, `retired_operation_id`, timestamps | Provenance and retirement evidence |

One live (`provisional/active`) binding per tenancy/logical key; generations are unique. One
canonical policy, quota, budget and namespace, with separate definition/default bindings. Key
identity is case-insensitive while values preserve case. Scope/dependency rules are typed handler
checks; identity/access fields and per-kind nullability are expanded in chapter11; use scoped FKs to prevent another tenancy's key/default attachment.

Known provider creation identity may be recorded provisionally before independent verification.
An unknown write with no correlated OCID remains in Operations, not a guessed binding. A same-name
unbound object is a collision requiring review, never automatic adoption. Updating statements or
budget changes the same bound object; replacement is exceptional and retains the old binding.
Removing a default does not delete its definition/namespace or historical resource tags. Retired
or retained objects are classified explicitly rather than rediscovered as fresh missing work.

## 6. `otm_tenancy_check`: one bounded configuration/access observation run

| Field | Type / rule |
|---|---|
| `id`, `workspace_id`, `tenancy_id` | UUID PK; scoped registry FK |
| `check_kind` | `configuration` or `access` |
| `configuration_id`, `access_assignment_id` | Exactly one non-null: current desired configuration or immutable access-assignment intent |
| `coverage_subject_kind`, `coverage_subject_key` | Stable backend-derived configuration tenancy / association / operational identity-purpose scope; disclosure grants are not access owners (D40); validated scoped references, never arbitrary browser keys |
| `configuration_generation`, `access_generation`, `binding_set_hash` | Required generation for selected kind and exact binding context |
| `schedule_occurrence_key` | Required logical acquisition identity; unique per workspace/tenancy/coverage-subject/kind/occurrence; manual acquisitions use fresh UUIDs, retries retain one |
| `sequence_number` | Monotonically allocated per tenancy, not based on clock ordering |
| `started_at`, `completed_at`, `state` | `running`, `complete`, `partial`, `failed`, `obsolete`; completion timestamp null only while running |
| `coverage`, `contract_versions` | Closed JSONB expected-key inventory, authorization/completeness and versioned normalization evidence |
| `operation_id` | Nullable linked verification/repair operation |

Configuration checks require a configuration revision; access checks require an access assignment and verified target/context, not a fabricated baseline dependency. The common records are named for both uses; configuration-only views retain their filter.

A complete configuration check includes every required object/property and eligible planned retirement, including
budget alert-rule absence and individual tag defaults. A permission failure cannot become an empty
successful inventory. Whole-tenancy inspection failure is one check issue, not invented missing
policies/defaults. Collect reads outside a DB transaction; publish evidence in a short transaction.

Advance the registry's current-check pointer only if configuration/generation/binding context is
still current, the run is newer than the published sequence, and concurrent mutations did not
invalidate coverage. Old runs remain historical. Partial/failed fresh checks are visible as such;
do not keep an old green result looking current. Running/obsolete observations cannot establish
absence, close issues or advance full verification.

## 7. `otm_object_observation`: expected versus observed per object

| Field | Type / rule |
|---|---|
| `workspace_id`, `check_id`, `tenancy_id`, `logical_key` | PK `(check_id, logical_key)`; scoped same-tenancy check FK |
| `binding_id` | Nullable same-tenancy FK; null only when no verified binding exists or a bounded collision inspection is being reported |
| `result` | `matching`, `missing`, `different`, `unable_to_verify`, `conflict`, `pending` |
| `expected`, `observed`, `diagnostics` | Closed sanitized JSONB facts; unknown actual data is null, never fabricated empty |
| `captured_at`, `coverage` | Object-level time and complete/authorized/concurrent-change evidence |

Expected values derive from the captured accepted configuration and bindings, not the newly
published fleet baseline or a mutable draft. Missing requires complete authorized absence. Pending
expected mutations are work progress, not new drift noise. Conflict is a distinct binding/adoption
issue, not automatic permission to repair. Matching can mean verified intended absence for an
explicitly reviewed retirement. Preserve per-object evidence; do not overwrite historical scans.

## 8. `otm_tenancy_issue`: one persistent attention episode

| Field | Type / rule |
|---|---|
| `id`, `workspace_id`, `tenancy_id`, `logical_key` | UUID PK and scoped target; reserved `inspection/access` key for a tenancy-wide failed check |
| `coverage_subject_kind`, `coverage_subject_key` | Stable coverage owner matching referenced checks; required in open-episode uniqueness and resolution guard |
| `issue_class`, `condition_code` | `configuration_drift`, `access_health` or `check_issue`; stable typed condition |
| `first_check_id`, `last_check_id`, `last_confirmed_check_id` | Same-tenancy evidence; confirmed reference nullable for check-only issues |
| `opened_at`, `last_seen_at`, `resolved_at` | Open when resolved timestamp is null |
| `resolution_check_id`, `resolution_code` | Nullable; required qualified evidence when resolving |
| `repair_operation_id` | Nullable linked accepted operation; progress comes from Operations, not duplicated issue states |

At most one open episode per tenancy/coverage-subject/logical-key/issue-class/condition.
All evidence and resolving checks must match that subject; a passing recovery-user check cannot
resolve a failed automation-user check even when both use `inspection/access`. Repeated unchanged scans
refresh evidence without opening another issue or initial notification. Verified resolution followed
by relapse creates a new episode. Keep immutable original/confirmation checks; append transition
audit. Only a current qualifying follow-up can resolve the condition. Check failures never prove
that prior confirmed drift was fixed. Keep prior unresolved confirmed drift visible with its last
confirmation time and current unknown/stale status; a separate check issue may explain lost access.

For changing missing/different details on the same object, continue the same drift episode with
updated evidence instead of generating noise. Reserve a stable `managed_configuration_mismatch`
condition code for these differences. A concrete current matching observation, or verified intended
retirement against current intent, resolves that episode. A resolved unrelated property cannot
close it. If check coverage changes, do not silently close prior issues because they were omitted.
No generic dismiss button. Repair queued/failed/unknown keeps the episode open until verification.

## Existing-table extensions and audit/notification reuse

| Existing storage | Proposed extension; not present today |
|---|---|
| `org_workspace` | Deprecated historical `current_baseline_id`, ignored by runtime; `configuration_candidate_epoch` for complete-set acceptance; keep organizational mapping config separate |
| `org_tenancy` | Real child/parent/domain/origin evidence, pending lifecycle; desired/last-verified/current-check pointers, config generation and observation sequence |
| `org_tenancy_association` | Existing C1/C2 pending/active/retiring transition and operation references; do not create a second owner/member model |
| `audit_event` | Scoped operation, plan, configuration and issue references; actor subject/display; command key/digest/result receipt; structured immutable before/after/outcome evidence |
| `notification_outbox` | Workspace and unique source-event reference; nullable organization recommendation/version plus typed configuration-issue/operation sources, routing snapshot, delivery attempts/outcome |

Today's outbox requires a unique non-null organization recommendation and non-null org version.
It **cannot be reused unchanged** for configuration alerts. Extend its source contract explicitly;
do not manufacture organization recommendations to satisfy it. Each committed alert-worthy event
produces one deduplicated intent with captured routing; missing routing falls back to administrators.
Preserve old recommendation linkage during migration. Audit/source events and outbox delivery are
separate records; their exact required-trigger checks must be fixed in the production migration.

Audit history remains append-only with indefinite retention, exportable by entitled administrators.
Database/runtime roles deny updates/deletes to published configuration and immutable history;
controlled migrations use separate credentials. A superuser-proof tamper-evident archive is not
implicitly provided by a PostgreSQL permission grant. Notification delivery does not authorize
repairs/lifecycle effects and must not replay blindly after restore.

## Screen and API mapping

Routes below are **proposed production contracts**, not endpoints implemented in the local app.
Persisted list projections avoid live OCI calls per row. Use stable IDs and optimistic revision or
If-Match evidence; derive final OpenAPI/client models from Python under D11.

| Screen / action | Read/write model | Proposed API boundary / result |
|---|---|---|
| Baseline history, view version | Baseline rows + workspace pointer + clearly labeled assignment counts | GET baseline versions / version; viewing changes no pointer/plan |
| New/edit draft | Copy published immutable document; edit one draft by expected revision | POST baseline drafts; PATCH draft; validation errors preserve input |
| Publish | Seal baseline, advance current-for-new, audit atomically | POST publish with draft revision; no existing assignment/job change |
| Tenancies: Assigned baseline | Desired config → published baseline; separate verified pointer/current check | GET tenancy inventory includes assigned version, pending/verified context |
| Tenancies: Configuration issues | Open issue projection with class and freshness; no live scan | Count distinct issue IDs; one opens detail, several open tenancy-filtered list |
| Override editor / preview | Current immutable config plus staged plan-target overrides | POST single-target override plan; PATCH proposal; GET preview; explicit Accept |
| Update existing tenancies | Plan + complete target set and content-bound decisions | POST baseline-update plan; GET ready count/exception list |
| Old/new/override comparison | Source config, target published baseline, proposed override/reviews | GET target; PATCH decision using plan/target context; no desired change |
| Start bulk update | Revalidated whole plan + every target | POST accept; one committed operation/initial job/audit; blocked before all reviews |
| Default Configuration drift | Open confirmed drift episodes with evidence and current visibility | GET issues filtered configuration_drift; exclude check-only, age and plan reviews |
| Tenancy issue detail | Exact episode + expected/observed check + binding + capability evidence | GET tenancy/issue; unknown ID never falls back to another target |
| Repair preview/start | Current assigned config + selected owned bindings + fresh permission guards | POST repair plan; GET preview; POST accept → operation, issue stays open |
| Operations progress | C2 operation/step plus accepted plan/config references | GET operation; qualified resume/reconcile; never restart a whole create blindly |
| Organization / Organization drift | Existing organization prototype model and review semantics | Approved UI remains authority; no configuration issue rows in org recommendations |

The registry projection must distinguish **Assigned baseline**, **last fully verified baseline**,
**Update available**, **configuration check freshness** and **open issue count**. Do not collapse
them into a single lifecycle/status flag. Version age alone creates no drift incident. Stale or
unverifiable observations do not mean everything is good.

## Idempotency for draft commands as well as accepted operations

Extend append-only `audit_event` with nullable `client_command_key`, `command_digest` and closed
`command_result` (IDs, resulting revisions and safe response facts). Receipt rows require a stable
actor subject and those three fields together. Add a partial unique key on
`(workspace_id, actor_subject, client_command_key)` for receipt rows; legacy events need no invented
actor identity. The digest includes command kind, target, payload and expected revision. Reuse this
receipt for Create draft/plan, Save draft/decision and Publish, not a new workflow/receipt table.
Accepted operation commands retain the C2 operation uniqueness guard as well.

Look up a successful matching receipt **before** rejecting its now-old optimistic revision. A lost
response replay returns the original ID/revision/result without another draft, plan, version or
audit event. A reused key with a different digest is a conflict. Concurrent identical requests race
on the unique receipt in the same transaction as the state change; the loser rolls back its whole
transaction and reads the winner's committed receipt. Failed/rolled-back commands leave no success
receipt. Returning an old result still checks current authorization and does not expose secrets.
This is a local database transaction; retrying it cannot send OCI or duplicate notifications.

## Workspace candidate fence for D31

Use the existing workspace row as the short-lived candidate-set lock; add the explicit epoch above.
Every transaction that changes active managed eligibility, desired configuration, relevant ownership/
parentage or binding facts takes the workspace row lock **first** and advances its epoch. Capture
the epoch with the preview; include it in the plan hash/revision. Acceptance locks workspace, then
plan, then target tenancy rows in deterministic order, checks the captured epoch and recomputes
the complete candidate set under that fence. Any changed context returns Stale and requires a new
preview/review; no job or desired pointer is committed from that stale plan.

Newly eligible onboarding/import completion uses the same protocol. It either commits before
acceptance and invalidates the preview, or commits afterward and is an explicit later update
candidate. The set is complete at acceptance's serialization point, not an expanding promise to
include future arrivals. Acceptance advances the epoch with its own desired changes; it does not
invalidate the already accepted operation. Later previews use the new epoch.

Never hold this workspace lock during OCI reads/writes, activation waits or worker execution.
Ordinary draft edits don't change the candidate epoch. This conservative protocol is appropriate
to a250-tenancy, low-change admin tool; it still needs DB concurrency tests across **every** write
path. Row locks on existing targets plus a hash are insufficient to prevent phantom candidates.
No new distributed lock service or speculative serializable-only dependency is introduced.

## Worked example: shared tenancy stays at a500 budget

These are readable labels for UUID-backed records, not new ID formats or executed results.

| Administrator/provider event | Desired / last fully verified revision | What the dashboard means |
|---|---|---|
| Baseline v1 has200; shared tenancy accepts budget override500 | CFG-1 / CFG-1 after complete verification | Assigned v1; effective budget500; check freshness still matters |
| Publish v2 with budget300 and a new root tag default | CFG-1 / CFG-1 | Update available; no assignment change or drift merely because v2 exists |
| Preview/review a bulk update | CFG-1 / CFG-1 | Saved decisions belong to the plan only; no queued effect |
| Accept the complete reviewed plan | CFG-2 / CFG-1 | Assigned v2, budget override500 preserved; application pending |
| Some objects applied, new default still unverified | CFG-2 / CFG-1 | Partial progress in Operations; do not claim v2 completely applied |
| All required objects/defaults/retirements verify | CFG-2 / CFG-2 | Last full verification is v2; existing resource tags are not retroactively rewritten |
| Owner later removes the quota | CFG-2 / CFG-2 | Same desired/last-verified IDs, but a new confirmed drift episode makes health unhealthy |
| Administrator starts Repair for quota only | CFG-2 / CFG-2 | Same assignment; exact persisted selection goes to Operations; issue remains open |
| Current authorized check verifies repair | CFG-2 / CFG-2 | Drift episode resolves with evidence; repeated failures would not resolve it |

A policy/quota full-list override has the additional D31 content-bound decision when its baseline
block changes. Keeping that list never appends new baseline statements. Selecting Use new baseline
removes that block override only in the proposed/new accepted revision, not the historical one.

## Critical transaction boundaries

1. **Publish:** validate expected draft revision, seal immutable baseline, change current-for-new
   pointer and append audit together. No update plan/jobs/desired pointers are implied.
2. **Stage review:** lock/check draft plan revision; save exact local decision and audit. No live
   configuration revision, desired pointer, worker job or OCI mutation changes.
3. **Accept:** lock workspace candidate fence, plan and target tenancies in deterministic order; reread complete membership,
   permissions, source generation/overrides/bindings and exact reviews. Atomically create root/child
   operation intent, configuration revisions as needed, desired pointers, audit/outbox intents and
   initial runnable job. Reject stale/incomplete scope without partial accepted target changes.
4. **Dispatch:** recheck current ownership generation and eligibility; resolve currently authorized
   credentials under C2. Superseded intent cannot overwrite newer desired state. OCI runs outside
   DB transactions. Unknown effects reconcile before another conflicting write.
5. **Observe:** store immutable run/object evidence; publish only context-current/newer evidence;
   reconcile issue episodes and notification intents in the same transaction. Advance full verified
   pointer only after complete current coverage and required retirements verify. Selected-object
   repair success alone cannot mark the entire configuration verified.
6. **Restore:** a database restore does not undo OCI/Vault/mail. C2 restore fencing and reconciliation
   apply to plans, generations, pointers, bindings, observations and notification replay before release.

Only one accepted tenancy mutation proceeds under the existing C2 guard; configuration is not a
second independent mutation runner. A superseding accepted override/upgrade requires explicit
conflict handling; this proposal does not authorize overlapping writes or silent cancellation.
If an older intent has unknown external effects, block acceptance/dispatch of conflicting intent
until reconciliation establishes a safe boundary. A later baseline publication alone changes no job.

## Keys, indexes and readable query projections

| Query / invariant | Candidate constraint/index |
|---|---|
| Baseline list and draft uniqueness | UNIQUE(workspace, version_number); partial UNIQUE(workspace) WHERE unpublished; B-tree(workspace, published_at DESC, id) |
| Config history and scoped pointers | UNIQUE(workspace, tenancy, revision_number); scoped UNIQUE(workspace, tenancy, id); index(tenancy, created_at DESC, id) |
| Complete plan and target lookup | UNIQUE(plan, tenancy); index(workspace, state, updated_at, id); FK indexes for source/accepted config and operation |
| Canonical live binding | Partial UNIQUE(workspace, tenancy, logical_key) WHERE state IN provisional/active; UNIQUE(tenancy, logical_key, generation); bound provider-identity uniqueness in its service/tenancy scope |
| Latest completed check/history | UNIQUE(tenancy, sequence_number); index(workspace, tenancy, completed_at DESC, id); scoped current-check FK |
| Check objects | PK(check, logical_key); scoped FKs and index(binding_id, check_id) |
| Open issues and exact detail | Partial UNIQUE(workspace, tenancy, coverage_subject_kind, coverage_subject_key, logical_key, issue_class, condition_code) WHERE resolved_at IS NULL; index(workspace, issue_class, opened_at, id) WHERE open; index(tenancy, opened_at DESC, id) |
| Initial notification deduplication | UNIQUE(source_event_id) or typed source-event/channel key, fixed with delivery contract; preserve existing legacy-source uniqueness during migration |

Composite FK targets require full non-partial unique keys; partial unique indexes enforce live-only
rules but are not FK targets. Cross-row published-state and complete-plan checks need guarded
transactions/permissions, not a CHECK expression pretending to read another row. Candidate-set
phantoms are handled by the explicit workspace epoch/lock protocol above; locking only existing
targets cannot prevent a newly eligible target from being omitted. SQL serialization/deadlock errors
still retry the complete local transaction with the same command identity. No OCI calls run inside that retriable transaction. These built-in PostgreSQL
mechanisms are design choices to qualify against the selected managed service, rather than a custom
locking service. [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) and
[transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html) document the
underlying behavior; the service's actual PostgreSQL version must be pinned before implementation.

Use ordinary views/queries such as `tenancy_configuration_summary`, `configuration_drift_queue` and
`configuration_plan_summary`, not additional tables with independent truth. Aggregate open issue
counts before joining the inventory, so owner/member joins do not multiply them. Page/filter/sort
with deterministic ID tie-breakers; totals, pages and filters use the same scope. Counts show active
managed tenancies, not historical assignment rows or one row per affected block.

No blanket JSONB GIN indexes, partitioning, read replica or custom job engine is proposed. At250
managed tenancies and roughly4+2k bound objects per tenancy for k tag keys, measure realistic daily
checks, history and operation bursts before tuning. Even k=10 means roughly2.2million object
observations/year; indefinite history requires storage/autovacuum/backup planning, not truncation.
Use query plans and representative production-like test data before freezing indexes, pool sizes
or retention. Audit retention remains indefinite; observation archival/retention remains a separate
operational decision and cannot delete unresolved evidence or change incident truth.

## ER view and visual guide

[Open zoomable proposed ER](../architecture/diagrams/configuration-data-model-proposed.svg) ·
[PNG](../architecture/diagrams/configuration-data-model-proposed.png) ·
[Mermaid source](../architecture/diagrams/configuration-data-model-proposed.mmd) ·
[Excalidraw](../architecture/diagrams/configuration-data-model-proposed.excalidraw)

The figure labels proposed C3 tables; existing registry/workspace and C2 operation references are
context. It omits repetitive workspace FK edges and detailed composite columns for readability;
field/constraint sections above govern scope. Excalidraw contains the ER render as an image that
can be moved/annotated; edit Mermaid to change table boxes/relationships.

## Validation and failure scenarios to implement

These are acceptance scenarios, **not executed runtime tests** or a claim that proposed SQL exists.
Existing D30 resolution and D31 gate design checks are reusable; the existing134 prototype tests
remain unchanged and do not prove these production transactions.

```text
Draft -> publish -> pinned recipe                 immutable/version concurrency checks
                     |
Plan -> stage decisions -> accept all targets      stale/omitted/review/job failure checks
                              |
                         operation / facade         retry/unknown/restore fencing
                              |
                          observation run           generation/coverage/order checks
                              |
                      issues + verified pointer     dedup/unverified/relapse/repair checks
```

| Scenario | Required result and test level |
|---|---|
| Budget-only override | New same-baseline revision; policy/quota/tags inherited; unit + PostgreSQL transaction |
| Full-list override | Exact replacement, no append/merge; immutable baseline remains intact; resolver unit |
| New baseline while onboarding waits | In-flight config remains pinned; new start gets new default; operation/simulator integration |
| Review one of several conflicts | Counts by tenancy; no assignments/jobs accepted; plan unit + API |
| Direct/bypassed Start with pending review | Server rejects whole batch; zero target/job changes; API + transaction |
| Concurrent override/parentage/binding change | Stale plan rejected before writes; DB concurrency + facade guard |
| Job/audit/outbox insertion failure | Accepted intent/pointers/config revisions all roll back; DB failure injection |
| Response lost after commit | Same request returns same operation; no second configuration revision or job; API/DB |
| Lost response to Create draft/plan, Save decision, Publish | Matching receipt returns original result before stale-revision rejection; different digest conflicts; concurrent retries create one result/audit; API/DB |
| Newly eligible tenancy during bulk acceptance | Workspace fence orders completion vs acceptance; changed epoch forces re-preview; no omitted conflicting target; DB concurrency |
| Repair without new config or binding ID | Generation changes invalidate overlapping scans; exact persisted repair scope is executed; simulator/DB |
| Old/partial scan or concurrent write | Historical evidence retained; no new-green pointer/false resolution; DB concurrency |
| Missing vs permission denial | Complete authorized absence only is Missing; denial is check issue; facade contract |
| Drift repeats / recovery / relapse | Same open episode and one initial alert; verified close; new episode on relapse; DB |
| Prior drift followed by failed check | Drift stays open with stale/unknown annotation; no false repair success; integration |
| Repair selected object | Keeps issue open until current verification; no unrelated/owner-created mutation; facade contract |
| Tag-default retirement | Verify intended absence; keep namespace/definitions/resource history; handler/simulator |
| Cross-workspace/tenancy FK or malicious ID | DB/API reject; no fallback/wrong-target dispatch; DB/security contract |
| Post-restore newer OCI effects | Fenced until reconciliation; no stale config/notification replay; restore simulator + later real drill |
| Inventory / drift / detail | Assigned version, freshness and exact issue links agree across routes and pagination; UI/API |

## Review checkpoint and current evidence

The documentation reviewer and independent engineering reviewer found the overall grouping
consistent with C2 and D30–D34. Initial review found missing durable repair scope, draft-command
idempotency and a candidate-set phantom race. This revision makes those fields/protocols explicit,
including observation generation for repair. The independent bounded recheck found no new material issues in those changes. These are addressed
**design findings**, not fixed runtime bugs or executed database tests. The rendered ER and document-link checks validate the
artifact; PostgreSQL/runner/provider transaction and failure scenarios above remain to implement.

## Catch-up milestones and development handoff

1. Review this model's grouping, state boundaries and full screen/API mapping. Decide the combined
   immutable tenancy-revision proposal; resolve any review findings before calling it accepted.
2. Qualify the selected D35 C3/C4 required-access composition and permission profiles of the explicit identity/Vault
   fields in chapter11 without hiding secrets in configuration JSON. Qualify budget root scope.
3. Review chapter11 usage/freshness fields and qualify C6 production roles, backup/restore, runner integration and
   query/retention evidence; update the unified production ER. Keep implemented ER separate until migrated.
4. Freeze Python models/generated API, Alembic migrations, facade contracts and test fixtures together;
   implement the first vertical slice before dividing feature work. One engineer/Codex flow remains
   a reasonable default; later frontend/adapters/platform lanes consume these shared contracts.

Do not split parallel developers into independently inventing baseline/override/assignment schemas.
The configuration domain owner supplies immutable resolution, plan/acceptance and observation
contracts first. Handler-specific work and UI integration can then proceed against common fixtures.

The catch-up pass does not mark C1–C6 complete. Still open: exact migration DDL and managed PostgreSQL
qualification; required-access profile/provider qualification; provider grammar/normalization and late binding;
MFA/credential lifecycle; financial source qualification; notification retry/reconciliation; observation
retention and measured SLO/restore targets. These are explicit next work, not missing silent defaults.

## D35 current validation and screen sources

The D35 UI review (private historical evidence; not distributed)
checks authored editing, visible readonly profiles, full-policy previews, authored-only batch
comparisons and captured queued arrays, plus complete expected/observed policy drift. The required
manifest, profile provenance, final policy preview and repair-authority display map to the fields
above and chapter11; transient expansion and client simulation state are not database columns.
The bulk review’s required-context signature is the illustrative equivalent of persisted plan
configuration/manifest/generation guards. It cannot silently acquire new grants at Start.

## P3.1 implemented authoring boundary — 2 November 2026

At the historical P3.1 checkpoint, the production application implemented the first recipe table, `otm_baseline_version`, with
18 explicit columns. See the [implemented draft field map and ER](../reference/baseline-authoring.md)
and [ER source](../architecture/diagrams/baseline-authoring-implemented.mmd). Policy and quota statement arrays,
exact monthly amount/currency and static OTM tag defaults have dedicated columns. Existing audit
storage records typed before/after content in the same transaction; no extra history table is needed.

This is draft authoring only. The other proposed configuration tables, publication/current-for-new
selection, tenancy assignments, override review/rollout, OCI object bindings, application and drift
observations remain design targets. Existing create/import operations do not yet capture or apply
this draft. Earlier “not implemented” descriptions in this chapter describe the original proposal;
use the implemented field map for this bounded production slice and chapter11 for actual table counts.


P3.1 authoring clarification, 2 November 2026: the UI collects one newline-separated policy block
and one quota block. Each nonempty line maps to an entry in the existing ordered JSONB array; there
are no individual statement rows or new TEXT columns. Loading joins entries for editing; only
explicit Save performs the line-to-array conversion. Blank lines are skipped; remaining text/order
are preserved. This supersedes the initial per-statement authoring controls, without changing the
physical model or automatically rewriting existing draft content.


Whole-unit budget authoring, 2 November 2026: administrator-entered monthly budget amounts use
positive whole currency units (whole dollars forUSD), including future per-tenancy budget overrides.
This is an authoring rule, not a conversion of actual/forecast cost observations. Keep exact decimal
storage and historical content; display integral budget values without decimal padding. Existing
fractional recipes remain readable but require an explicit whole amount before a later save; never
round or rewrite them automatically. The implemented SaveBaselineDraft command enforces this rule.


Statement-count authoring bound, 2 November 2026: each policy block and quota block independently
accepts up to50complete statements (formerly20), with2,000characters per statement unchanged.
The UI remains one newline-separated editor per category. The browser allows105,000raw characters
per block; authenticated JSON saves remain stream-bounded at2MiB. Stored arrays, field shapes,
version/hash format and whole-unit budget behavior are unchanged; no SQL migration is required.


## P3.2a implemented publication boundary — 2 November 2026

`otm_baseline_version` now has20explicit columns: migration0012 adds nullable
`published_by_name` and `publication_mode` to preserve human attribution and explicit simulated
qualification. Published metadata is all present and the mode is exactly `simulated`; draft metadata
is absent. Existing immutable-row guards and draft-revision fences remain. Typed publication audit
uses the existing audit table in the same transaction. The implemented field map and ER linked above
cover all20columns and10DTOs/55effective fields. No additional application table was introduced.

History, exact read-only version lookup, local publication and cloning the latest publication are
implemented; existing data is not rewritten. Earlier publishing/current-for-new/assignment/OCI
flows in this chapter remain the full design target, not this checkpoint's capabilities. There is
no current-for-new pointer, assignment or OCI application yet. Create/import pinning follows next
and must not mistake a simulated publication for real-provider qualification.


## Implemented latest-only default and onboarding pin — 3 November 2026

Latest published is always the default for new operations. BaselineDirectory.latest and
PersonWorkflow.current_baseline derive the same scoped maximum published version; there is no
separate current DTO, selection command or endpoint. New drafts also derive from latest.

The retained org_workspace.current_baseline_id column/FK/guard is deprecated historical metadata;
runtime never consults it for selection and its UPDATE grant is revoked. Migration0014 preserves
that metadata and all existing pins, incrementing registry_revision once to invalidate old previews.
The application stays15tables and the baseline table20columns. The current configuration dictionary
has11DTOs/58effectivefields, retaining old BaselineSelectionEvidence only to decode immutable history.

OrganizationIntent.baseline and otm_tenancy.baseline_version_id still freeze the recipe accepted for
an operation. Workers verify that exact snapshot and registry pin, never substitute latest during
waits/retries. Old unpinned operations stay unpinned. Selected recipe is not applied/verified OCI
configuration; full configuration revisions, overrides, bindings and drift remain later work.


## Exact 0016 field mapping and staging boundary

Use the [current runtime dictionary](../reference/tenancy-overrides.md#complete-physical-model)
for the actual 14-, 11- and 10-column tables and desired_configuration_id/last_verified_configuration_id
heads; the full proposed tables above include additional future fields and do not constitute an
executed migration. Source UI maps each input/display to 10 override DTOs / 55 effective fields and
12 updated rollout DTOs / 76 fields. Statement editing uses one bounded textarea per category, maximum
50 complete nonblank lines and 2,000 characters per item; null inheritance and explicit whole-budget
replacement retain exact fixed-scale storage. No per-statement table, append/merge, tags override
or implicit latest upgrade is introduced.

Draft plans capture typed ConfigurationTarget proposals/hash and owner/request identity. Staged
Save review is optimistic and audited but changes no desired/provider state. Final whole-plan Start
rechecks complete candidate source/choices and writes accepted revisions/heads/intent/job/seal in one
transaction. Nonnull configuration heads/hash are independently validated; two null legacy heads
retain inheritance, not fabricated revision history. Full required-policy manifest/renderer and real
OCI payload/binding/observation qualification remain future work. Whole-slice local verification and both saved-runtime upgrades pass. The 59 schema artifacts match
the qualified models, while separate database/browser/authority checks establish runtime behavior.


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


## Existing-model onboarding reuse — 3 November 2026

The qualified, installed version 2 onboarding refinement reuses otm_tenancy.baseline_version_id,
verified_baseline_version_id, configuration_verified_at and configuration_observation. The accepted
intent already stores the full published baseline. No new table, override revision or column is
needed; new create/import applies the frozen recipe, independently reads all four simulated
categories, then reprobes access. Old operations and stored hashes remain intact. The broader
required-manifest/live-OCI object model remains future work. See
[the runtime field map](../reference/tenancy-onboarding.md).


## Local on-demand check subset — 3 November 2026

Local implementation qualified and installed in both saved instances. One new table, otm_configuration_check, records 13 fields for
each immutable child attempt: id, workspace_id, tenancy_id, operation_id, acquisition_sequence,
contract_version, started_at, checked_at, context, context_hash, state, results and evidence_event_id.
The qualified local schema has 19 application tables; the previously qualified 0017 subset had 18. No
desired/verified head column or backfill is added. The
[field-complete runtime guide](../reference/configuration-drift.md) and
[implemented ER](../architecture/diagrams/configuration-drift-implemented.mmd) are the actual subset authority.

The proposed otm_tenancy_check/object-observation/issue tables above remain the full future model,
not three more tables already implemented. This slice keeps four closed category results and the
frozen assigned context in one immutable check row, joined to existing operation/step/audit records.
Future qualification must extend/migrate that check authority rather than create independently
writable competing histories. Acquisition ordinals are database-generated under serialized local
read locks. A failed/latest attempt and earlier same-context complete confirmation are separate
projection inputs; partial/unknown cannot resolve confirmed drift or leave old Matching green.
The 24-hour freshness threshold adds no daily scheduler. No repair, notification or OCI binding/
required-manifest qualification is claimed.
