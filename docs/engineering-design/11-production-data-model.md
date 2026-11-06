# 11: unified proposed production data model and UI field guide

21 October 2026 | Full data-model catch-up | Review proposal, not a database migration

[Design hub](README.md) · [Configuration field guide](10-configuration-data-model.md) ·
[Implemented ten-table model](../../prototype/docs/organization-er-diagram.md) · [Approved UI authority](../ui-screen-authority.md)

## Read this first

This is the full application data inventory: organization, tenancy identity, associations, durable
operations, configuration, managed objects, access/credentials, financial observations, notification,
audit, recurring work and recovery. It describes where a field lives, which values are derived,
and what cannot yet be treated as verified OCI state. The working prototype remains unchanged.
Recovery-only MFA-exemption enforcement, provider permissions, financial attribution, managed PostgreSQL qualification and final migration
DDL remain explicitly open; missing qualification is represented by state/evidence, not invented data.

The current proposal reuses ten existing domain tables, adds the two C2 operation tables, eight C3
configuration/shared-observation tables, six C4 access/session tables, two financial tables,
and two D58 application-administrator tables:
**30 proposed total application tables**, before runner-owned/framework infrastructure. This is a
model inventory, not a claim that 30 tables have been created. Each added table has a separate
lifetime/query purpose; no new people/reporting tree, policy-statement-per-row, attempt-per-row,
role-lookup-per-enum or per-screen cache tables are introduced.

| Question / area | Read |
|---|---|
| Where are tenancy name, OCID and home region? | [Registry fields](#tenancy-registry-org_tenancy) |
| Where are policy/quota statements, budget and tags? | [Explicit configuration fields](10-configuration-data-model.md#explicit-configuration-values-and-created-object-identities) |
| Where are created policy/quota/budget/tag OCIDs? | [Object identity map](#created-oci-object-identity-and-drift-path) |
| How do operations, access and secrets fit? | [Operations](#operations-and-immutable-intent), [access model](#identity-access-and-credential-model) |
| How is usage/forecast stored? | [Financial model](#financial-collection-and-observations) |
| How do UI fields map to storage? | [Field coverage](#ui-and-prose-field-coverage) |
| Which ER should I use? | [Diagram set](#diagram-set-and-authority) |

## Current model decision: D40 — 24 October 2026

V1 has one human administrator-access flow: retrieve the unique Vault-held password for the
persistent child-local recovery account. D39 selects an MFA exemption for that recovery identity
only; owner/member humans retain MFA and OTM retains corporate SSO/administrator entitlement.
Each authorized retrieval is audited/notified. The first authorized disclosure attempt opens a
four-hour rotation window; further retrievals cannot extend it. Unknown password/Vault state blocks
release. Loss of automation requires the independent manual recovery procedure, not self-repair.

Temporary named support is deferred. D40 supersedes the earlier D19/D37 two-flow proposal for V1.
`otm_human_access_grant` now records credential disclosure requests and their shared exposure window,
not temporary-user provisioning or access-assignment ownership. The credential head and existing C2
operations remain the single rotation authority. The D40 count stayed **28 proposed application tables**
(the later D58 administrator extension brings the full inventory to 30);
this is a proposed-model change only, not a migration or change to the running ten-table prototype.

## Current implemented organization storage — validated local checkpoint, 30 October 2026

The validated organization/tenancy foundation through0010_guided_onboarding has fourteen physical
application tables: five snapshot, six foundation and three review/registry tables. The existing
[workflow field dictionary](../reference/organization-workflows.md) and
[workflow ER](../architecture/diagrams/organization-workflows-implemented.mmd) cover that foundation. Its
[local checkpoint](../history/organization-parity-checkpoint.md) receipts retain their original source scope.

P3.1 added the fifteenth application table, otm_baseline_version, through forward migration 0011.
P3.2a extends it through 0012 with published_by_name and publication_mode, for 20 columns and still 15 tables.
The [separate baseline ER](../architecture/diagrams/baseline-authoring-implemented.mmd) and
[complete twenty-column/content field map](../reference/baseline-authoring.md#the-fifteenth-application-table-otm_baseline_version)
show workspace/optional published-parent relationships, simulated publication and immutable history.
P3.2a, original P3.2b and the user's latest-only 0014 correction are validated locally. New admission
derives latest published version_number in the workspace, ignoring preserved deprecated
org_workspace.current_baseline_id metadata. Existing pins/intents are preserved and older versions
cannot be selected for new starts. The 0015 baseline-only update foundation and presentation refinements
are also validated locally. The qualified local 0016 implementation adds immutable authored configurations and
staged override reviews:3 tables/35 columns and 2 nullable tenancy heads, for 18 application tables while
the baseline remains 20 columns. Complete local qualification and both saved-runtime upgrades for 0016 pass.
Real OCI bindings/application, full required-policy rendering and production verification remain
unimplemented. See the [current override field dictionary](../reference/tenancy-overrides.md),
[0016 implemented ER](../architecture/diagrams/tenancy-overrides-implemented.mmd) and prior
[baseline-only field guide](../reference/configuration-updates.md).
The full30-table logical proposal and preserved prototype remain separate authorities.

The added tables are `org_recommendation`, `otm_tenancy`, `otm_tenancy_membership`. They are the
production equivalents of the preserved prototype's review/tenancy/association model, not a duplicate
live production registry. New `org_person` managed controls do not rewrite immutable source/person
anchors; `org_workspace.registry_revision` fences stale registry decisions. The workflow field guide
lists every new column and public/frozen contract field. Existing source tables still use the
[snapshot dictionary](../reference/organization-storage.md).

Accepted work closes its organization handoff atomically with intent/audit/native queue admission.
Verified local simulation governs association activation/retirement and final managed-directory
changes. Source warnings/history have durable episodes; existing snapshots become a baseline without
invented tenancy ownerships. No OCI credentials/activation/real IAM or termination is qualified by
these authored local flows. Broader fields/constraints below remain future design unless explicitly
mapped to an actual migrated column in the current guide.

The following P0.9 paragraphs are historical foundation checkpoints.

## Local production implementation checkpoint — P0.9

[Admission field map](../reference/admission.md) and [worker ER/field map](../reference/worker.md)
[session field map/ER](../reference/authentication.md) and
[administrator field map/ER](../reference/administrators.md) document the six actual production
application tables: `public.otm_operation`, `public.audit_event`, `public.otm_operation_step`,
`public.otm_admin_session`, `public.otm_administrator` and `public.otm_local_credential`. Every implemented column, closed JSON field, scoped constraint
and queue reference is listed there. OCI execution is still internal simulated `inspect_import` only; local grant/session/authentication
and administrator directory/revocation behavior are implemented independently of OCI execution;
remaining fields/tables below are still design, not an assertion the whole 30-table schema exists.
Native runner/Alembic tables are infrastructure; the ten-table prototype remains separate.

Forward migration 0002 keeps non-null positive revisions for intent events and null revisions for
worker dispatch/outcomes, whose typed JSON carries attempt/intent context. This retains the exact
current-intent FK and allows multiple evidence events under ordinary NULLS DISTINCT uniqueness,
without an added kind column, coordinator or partial index. All append-only protection remains.
The logical step stores one current read generation; full normalized observations persist in audit.
The original six migrations are frozen/hash-checked; forward migration0007 adds only the
closed export event family and a workspace/time/event index. All seven ship in the wheel. Actual local DDL is compared
against all six SQLAlchemy application tables, with real negative constraint tests. Business HTTP routes,
corporate authority composition, real credentials/provider writes and managed deployment are not yet
implemented or qualified by this local slice.

The session subset implements hashed-handle verification, current injected entitlement, scoped
revocation and optional protected session context. It does not implement SSO/session issuance or
fulfill the maintained SSO/session-library qualification. No raw tokens or claims enter the 16-column
session table; no production local-login bypass is introduced. D58 adds a separate administrator
access list and local credential model below, not a second organization directory.


## D58 application-administrator extension — 29 October 2026

[Chapter19's detailed checkpoint](19-administrator-provisioning.md#detailed-checkpoint-two-new-tables-existing-sessions-and-audit)
is the field and flow authority for two proposed additions: `otm_administrator` and
`otm_local_credential`. The previous domain proposal had 28 tables; this extension makes **30 total**
(10 retained domain tables plus 20 proposed additions). The focused
[administrator ER source](../architecture/diagrams/application-administrators-proposed.mmd) and rendered
Mermaid in chapter19 add those tables without duplicating the existing session or audit table.
Older 28-table core/configuration/finance diagram subsets remain valid for their domain scope;
the administrator extension is required when reading the full proposed inventory.

The grant holds workspace, exact issuer/subject, local/corporate kind, display/contact data,
active/revoked status, authorization revision and lifecycle timestamps. The local credential holds
its scoped grant FK, Argon2id verifier, external TOTP secret reference, last consumed time step,
enrollment/password timestamps and bounded failure-window/cooldown fields. The chapter19 field
tables enumerate every column. No seed/password plaintext, per-screen cache, extra employee identity,
role lookup or MFA challenge table is introduced.

Explicit column index (types, nullability and constraints are in the chapter19 field tables):

- `otm_administrator`: `id`, `workspace_id`, `identity_kind`, `issuer`, `subject`, `display_name`,
  `email`, `status`, `authorization_revision`, `created_at`, `updated_at`, `revoked_at`.
- `otm_local_credential`: `workspace_id`, `administrator_id`, `password_hash`, `totp_secret_reference`,
  `last_totp_step`, `mfa_enrolled_at`, `password_changed_at`, `failed_attempts`,
  `failure_window_started_at`, `retry_after`.

Existing sessions retain 16 fields: exact issuer/subject/workspace identify the grant;
`entitlement_reference` identifies its UUID and `entitlement_revision` must equal its current
revision. Revocation/regrant/reset cannot revive an old session. The same-workspace grant identity
FK is added by migration0005, after discarding pre-grant operational sessions. Cleanup
never deletes grant/credential/history rows. Existing `audit_event` gains nullable scoped
`administrator_id` and supports closed authentication event kinds without requiring a fictitious
OCI operation. Existing operation kinds still require their operation/intent references.

A1 now implements these two tables through frozen forward migration0005, plus exact grant checks
and atomic ordinary-grant revocation/audit; the actual production subset is six tables. See the
[implementation guide](../reference/administrators.md) for the implemented subset. [The local authentication slice](../reference/local-authentication.md) now uses the credential
shape for real operator enrollment/reset, password/TOTP verification and atomic session issuance/
audit. The [local React application and HTTP field map](../reference/local-application.md#implemented-http-and-model-boundary)
now project directory rows/statistics from the same grant table and reuse atomic revocation.
There are 23 exported structural schemas, including Operations, simulation and Audit History projections; no UI/session cache table is added. Ordinary grant
creation/regrant, corporate identity qualification and production secret/provider deployment remain future slices. The existing prototype remains unchanged.

## Common types and ownership rules

Unless stated otherwise, IDs are UUIDs, workspace IDs reuse the existing string key, timestamps are
UTC `timestamptz`, counters are positive bigint/int, foreign keys are scoped by workspace and tenancy,
and amounts are exact `numeric(20,4)` with qualified currency precision. Null means unavailable/not
yet known only where specified, not zero/false/success. Named type codes are candidate constrained
strings, not new lookup tables. JSONB fields have closed versioned schemas; JSON references still
need explicit same-scope validation when SQL cannot enforce an array element FK.

Stable application identity, OCI OCID, SCIM resource ID, public display name and an authenticated
SSO subject are different facts. Never match authoritatively by display name or substitute one ID
format for another. Published versions and evidence are immutable; mutable heads point to them.
Every current/head reference is same-owner/same-workspace. Rows retained for history do not imply
current entitlement, ownership, successful provider effects or live health.

## Organization model: preserve the implemented foundation

| Existing table / view | Fields and continuing meaning |
|---|---|
| `org_person` | Stable person UUID and original identity email. Current display/contact is revision data; a name/email merge preserves stable relationships and history |
| `org_workspace` | Organization mapping configuration ID/document, applied/proposed version pointers; production control fields below are separate |
| `org_feed` | Acquisition/source IDs, capture time, digest, immutable canonical JSON and diagnostics/status. Every deliberate upload/pull gets a new acquisition; delivery retry reuses its identity |
| `org_version` | Immutable applied/proposed organization/configuration evidence, source and base revision |
| `org_member` | Full name/current email, direct manager UUID/email, profile/presence evidence, LOB, accountable leader, designees, ancestry and absence-review status for one revision |
| `org_recommendation` | Actionable/informational kind, target, before/after, episode/status and decision evidence; remains organization-specific |
| `current_organization`, `proposed_organization` | Existing selected-head projections, not new independently writable organization tables |

Root/LOB labels and designees derive from the pinned organization configuration. Missing-manager
references and incomplete ancestry remain explicit. Ordinary valid metadata auto-applies. Email/name
remap is explicit/audited; no stable employee ID is assumed. None of the OCI baseline/credential
changes rewrites organizational identity or fabricates feed presence. Detailed existing fields and
reconciliation cases remain in the [implemented field reference](../../prototype/docs/organization-field-reference.md).

## Workspace control fields: `org_workspace`, proposed extensions

| Field | Type / source / constraint |
|---|---|
| `hosting_tenancy_ocid`, `hosting_compartment_ocid` | Verified/configured deployment targets; never infer parent tenancy from these |
| `organization_parent_tenancy_ocid` | Explicit configured control parent; independent of hosting location |
| `hosting_access_context_id`, `parent_access_context_id` | Scoped FK to the corresponding machine contexts; no fake managed child rows |
| `deployment_configuration_revision` | Immutable external configuration/Terraform reference used by the deployment; changes audited |
| `protected_tenancy_ocids` | Closed bounded list including host/control/parent protections; enforced alongside real target checks |
| `current_baseline_id` | FK to a published managed-OCI baseline; not the existing organization `configuration_id` |
| `configuration_candidate_epoch` | Workspace-first short-transaction fence from chapter10 |
| `runtime_policy_revision`, `runtime_policy` | Audited nonsecret operational settings: schedule/freshness/limits, qualified financial source profile, notification channel and entitlement references, plus D51/D52 `recovery` objectives (`rpo_seconds=900`, `rto_seconds=14400`, `disaster_scope=in_region`, `objectives_revision`); closed schema, separate from org and child baselines |

Deployment/entitlement configuration may be supplied externally. The database stores its nonsecret
version/provenance and accepted context; it is not a competing source of passwords or deployment
credentials. Hosting equals parent and hosting differs from parent both remain supported.

## Tenancy registry: `org_tenancy`

The current parity migration ports the separate prototype registry to physical `otm_tenancy` and
its associations to `otm_tenancy_membership`; it does not create another writable production registry.
`name` already existed in the prototype. The wider OCI-qualified field contracts below are target
extensions; the current simulated subset and actual column spellings are in the workflow guide.

| Field | Type / source / constraint |
|---|---|
| `id`, `workspace_id` | Existing local UUID/workspace; stable even before OCI creation |
| `name` | Actual observed tenancy name; nullable only before discovery in production. Existing simulation names remain local-only evidence |
| `tenancy_ocid` | Nullable until real discovery; known value unique across this controller, preventing concurrent management through another workspace |
| `home_region_key` | Raw OCI `home_region_key`, retained as returned |
| `home_region_identifier` | Qualified mapping to SDK region identifier; never assume the key is already an SDK identifier |
| `parent_tenancy_ocid`, `parentage_verified_at` | Observed parentage with authorized organization evidence; GetTenancy alone does not prove it |
| `metadata_observed_at`, `metadata_observation_state` | Time and complete/unavailable/conflicting metadata evidence; failed read never erases last known facts |
| `kind`, `origin`, `legacy` | Existing individual/shared kind; created/imported origin and historical simulation provenance |
| `management_state` | Proposed pending_setup, managed, termination_pending, termination_initiated, retired states; one authoritative production lifecycle, not a parallel mutable copy of legacy status |
| `provider_lifecycle_state`, `provider_lifecycle_observed_at` | Separately observed provider state; unknown is not app lifecycle failure/success |
| `lifecycle_generation`, `lifecycle_operation_id` | Current mutation/eligibility context and scoped operation |
| `termination_initiated_at`, `termination_evidence_event_id` | D26 verified initiation and audit; no final deletion/30-day finality monitor |
| `bootstrap_access_context_id`, `automation_access_context_id` | Scoped child contexts; real target must match this row before dispatch |
| `desired_configuration_id`, `last_verified_configuration_id` | FK to this tenancy's immutable config revisions; desired and fully verified are separate |
| `configuration_generation`, `observation_sequence`, `current_configuration_check_id` | Stale-check fencing, ordering and scoped current configuration check |
| `financial_source_context_id`, `financial_attribution_revision` | D41 source is this child's existing automation context plus pinned Budget/currency/cycle policy; source context must match `automation_access_context_id`, never hosting/parent authority or a fallback |
| `created_at`, `updated_at` | Existing row lifecycle times; old provider metadata/requests remain in immutable evidence |

Requested tenancy name/home region and initiating activation email live in immutable operation intent,
not a second writable registry name. Display actual name when verified; before discovery, show
explicit **Requested / awaiting activation** with the captured request. Name conflicts/amendments
append intent/attempt evidence. A different name on the same verified OCID is observed metadata;
a different supplied OCID requires explicit reconciliation, never silent registry retargeting.
Raw/final names and regions survive in operation/audit history. Failed inspection cannot clear them.
Oracle's [Tenancy model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/models/oci.identity.models.Tenancy.html)
returns `id`, `name` and `home_region_key`; parentage is separately verified.

Do not store a single owner/manager/LOB copy on tenancy as another authority. Resolve current owner
through association, then selected organization revision. One person may own multiple tenancies.
Groups/members may span scopes; compartment IDs belong to bound scope/access intent, not one
misleading tenancy-wide employee compartment field.

## Associations: `org_tenancy_association`, proposed transition extensions

| Field | Meaning |
|---|---|
| Existing `id/workspace_id/tenancy_id/person_id/role` | Stable owner/member relation; scoped tenancy and real stable person, not email-only linkage |
| `state`, `revision`, `access_generation` | pending, active, retiring, retired; expected revision and access-observation/dispatch guard |
| `initiating_operation_id`, `transition_operation_id`, `supersedes_association_id` | Accepted change and retained predecessor evidence |
| `accepted_at`, `activated_at`, `accountability_ended_at`, `retired_at` | Accountability can end before residual IAM cleanup verifies |
| `desired_access_assignment_id`, `last_verified_access_assignment_id`, `current_access_check_id` | This relation's immutable desired/verified access intent and scoped latest check |

Keep one active owner per tenancy and one active person/tenancy association. Pending replacement
owner is not a second current owner. Publish replacement accountability only after verified grants;
retiring old-owner cleanup remains an obligation after the current owner changes. Promotion/member
retention atomically supersedes conflicting active roles. Offboarding examines pending/active/
retiring obligations and explicit Keep actions, not just current owners. Member removal deletes
only safely bound personal identity/access; resources/compartments remain for manual owner cleanup.
Migration replaces legacy status semantics explicitly; it does not keep two writable state columns.

## Operations and immutable intent

The same two proposed C2 tables serve all lifecycle/configuration/access/financial jobs. No new
worker engine, attempt table or operation-per-UI-screen entity is introduced.

### `otm_operation`

Fields: UUID `id`; scoped `workspace_id`; optional `parent_operation_id`, `tenancy_id`, `person_id`;
`kind`; `initiating_actor_subject`, immutable `initiating_actor_snapshot` including verified activation
email, `responsible_actor_subject`; `client_request_key`, `request_digest`, `consumed_preview_id`;
`current_intent_revision`, `current_intent_event_id`; `state`, `stage`, `wait_reason`, `effect_knowledge`;
`revision`, `stop_requested_at/by`; `due_at`, `deadline_at`; `prior_operation_id`, `recovery_release_event_id`;
`accepted_at`, `created_at`, `updated_at`, `completed_at`.

Unique(workspace, actor, request key) rejects conflicting reuse. Unique(workspace, consumed preview)
prevents accepting one preview twice with different keys. Batch parents may have no tenancy; target
children are scoped to their exact tenancy. Parent totals derive from children. Initiating actor
and activation mailbox are not rewritten when responsibility changes.

**Canonical intent history is typed append-only `audit_event`**, with event kind `operation_intent`,
operation ID, intent revision, contract version, full sanitized bounded intent and digest. Enforce
unique(workspace, operation, intent revision). The operation's current pointer references that exact
event/revision. A name/amendment appends a new snapshot; no unbounded JSON history array or rewriting
of old requests. All step inputs bind one exact revision; compatible reused evidence names its origin.

### Create-only activation administrator binding (D55)

The accepted create handoff appends a closed typed operation-intent snapshot containing
`tenancy_ocid`, `bootstrap_user_ocid` and **`activation_administrator_user_ocid`**, plus the
verified activation-administrator binding reference once inspection succeeds. The UI and API
require all three OCIDs for net-new create; import does not accept or infer this cleanup target.
These are immutable intent fields, not additional columns or a new table.

Read-only identity-domain discovery resolves the supplied activation OCID to its exact returned
OCI user OCID, SCIM resource ID and verified same-child/domain binding. The admin explicitly
confirms the displayed retirement target; a matching email/name alone cannot establish it.
Record the confirmation, original initiating identity/email, operation and inspection evidence.
Use the existing operation-scoped managed-user binding for this expressly authorized cleanup;
its creation provenance records binding registration, not a claim that OTM created the human in OCI.
Other observed humans remain references and cannot become deletion candidates by name matching.

Reject a target equal to the bootstrap user, permanent automation, recovery identity or intended
owner, another tenancy/domain, an ambiguous lookup or a changed binding. Before retirement,
recheck exact binding/operation provenance and all existing replacement/last-administrator guards.
A changed submitted OCID requires a fresh preview and audited intent revision; it cannot silently
retarget an accepted cleanup step. Unknown/failed verification leaves cleanup blocked in Operations.
No initial-admin password, MFA seed or token is collected.

### `otm_operation_step`

Key: `(operation_id, intent_revision, step_key)` scoped to workspace. Fields: `command_kind`,
`contract_version`, immutable `inputs`, typed target/access-context references, `dependency_keys`,
`required_completion_predicate`, nullable `reused_evidence_step_reference`; mutable `state`,
`execution_generation`, `attempt_number`, `current_attempt_id`, qualified lease owner/expiry,
`next_due_at`, `wait_condition`, `retry_policy_version`, `attempt_budget`, `last_outcome`,
`effect_knowledge`, `verified_at`, `evidence_event_id`, `cleanup_obligation`; `provider_submission_id`,
`provider_retry_token`, provider request/work-request/object correlation and original attempt reference.

Attempt IDs differ from provider submission identity. Re-delivery/transport retry keeps the original
qualified submission identity; amendment may change it only after a known no-effect boundary. Exact
credential version/generation and dispatch/outcome snapshots append to audit; business intent does
not freeze an obsolete secret forever. Unknown effects retain a durable exclusion independent of
lease expiry. A late worker may record possible effects but cannot publish over newer generation.
No secret values or SDK clients enter these records.

### Preview and command receipts without another table

A pure preview calculation is read-only. An explicit **capture preview** command writes an immutable
`audit_event` of kind `action_preview`, with actor, validated input, context revisions, intended
IDs/actions, valid-until and digest, but no accepted operation/job/provider change. Its event ID is
the consumed preview FK. GET of captured preview is read-only. This makes pre-accept create/import/
offboard/transfer plans recoverable without adding a second planning table. Configuration-specific
multi-target reviews still use the two chapter10 plan tables.

The explicit capture/save/publish commands use chapter10's audited idempotency receipt. A matching
lost-response retry returns the stored result before stale-revision rejection; changed payload reuse
conflicts. Capture is not action authorization: current entitlement/guard checks still run at accept.
Offboarding freezes one action per association in the preview/intent, preserving exact scope and
resource-cleanup guidance. Source metadata changes do not rewrite accepted provider targets.

## Created OCI object identity and drift path

Reusable baselines contain values, **not per-tenancy OCIDs**. Each instance's actual object identities
live in `otm_managed_object_binding`. The registry stores the tenancy OCID separately.

| Record | Example logical key / fields | Meaning |
|---|---|---|
| Tenancy | `org_tenancy.tenancy_ocid`, `name`, home-region fields | Which real OCI child to inspect |
| Accepted configuration | Baseline FK + authored policy/quota/budget overrides + pinned required-policy manifest/renderer | Complete desired intent for this tenancy |
| Root policy binding | `policy/main`, `provider_ocid`, root owner scope, generation | Actual single policy object; compare its statement array |
| Root quota binding | `quota/main`, `provider_ocid`, root scope | Actual single quota object; compare statement array |
| Budget binding | `budget/main`, `provider_ocid`, owner/target scopes | Actual monthly root budget; compare amount/context/no-alert rule state |
| Tag namespace/key/default bindings | Separate `provider_ocid` and parent binding links | Namespace, each definition and each root default are different real objects |
| Observation | Check ID + logical key + binding ID/generation, expected and observed values | What an authorized bounded check actually saw |
| Issue | Exact evidence and persistent episode | Confirmed drift/access loss/check failure, with appropriate UI and repair path |

```text
registry.tenancy_ocid + qualified target context
    -> desired_configuration_id
    -> baseline explicit values + nullable override columns
    -> managed binding for policy/main (its policy OCID)
    -> facade reads that OCID in that tenancy/root/region
    -> compare returned statement list with resolved expected list
    -> immutable observation + issue episode / verified state
```

No name-based rediscovery/adoption shortcut. Known object updates retain their OCID; explicit verified
recreation records a new binding generation and replacement link. Unknown writes remain in Operations.
API denials/timeouts are not Missing. Expected and actual JSON in observations are typed snapshots of
these values; they are not another authoring source.

### Binding extensions for identity and compartments

Retain child `tenancy_id` and scoped logical key/generation. Add `kind`, `provider_resource_type`,
`ownership_mode` (managed/observed_reference), nullable `provider_ocid`, `scim_resource_id`,
`identity_domain_binding_id`, `domain_endpoint`, `endpoint_verified_at`, closed typed `domain_metadata`, `subject_binding_id`,
`target_binding_id`, `desired_access_assignment_id`, `last_verified_access_assignment_id`, `current_access_check_id`,
`access_generation`,
`metadata_observed_at`, typed `provider_relationship_reference`.

Configuration objects and compartments require a real OCID. Domain users/groups may have both SCIM
and OCI IDs; store them separately after verified mapping. Memberships/app-role grants without an
OCID use the qualified exact subject/target/domain/provider relationship identity. Unique live
binding/relationship keys use those typed identities, never fabricated OCIDs. Both endpoints must
be same verified tenancy/domain where the adapter requires it. Domain/built-in observed references
are not OTM-owned deletion candidates. All identity endpoints must come from verified allowed realm/
domain metadata, not arbitrary browser input. Hosting/parent principals use external context references;
they are not invented managed-child bindings.

Identity-domain bindings use a closed nonsecret `domain_metadata` JSONB schema with
`display_name`, nullable `console_sign_in_url`, `console_sign_in_verified_at`,
`source_evidence_event_id` and `verification_method`. `display_name` is an observed provider label,
not a domain identifier. The console URL is a separately qualified HTTPS sign-in destination with
an approved identity host/realm and same-domain/tenancy evidence. Never derive it by guessing from
`domain_endpoint`: that field addresses the API/SCIM service. No activation tokens, query credentials
or caller-supplied URLs are accepted. Until qualification, the console URL is null and the UI offers
instructions/unavailable status rather than a clickable guessed destination. Attempts pin this
verified metadata revision; this adds no second editable domain registry.

## Identity, access and credential model

### 1. `otm_access_context`: machine request authority

Fields:

- `id`, `workspace_id`, `purpose`: hosting, organization_parent, child_bootstrap, child_automation.
- `tenancy_id` nullable scoped registry FK; required for child contexts (including pending registry),
  null permitted for hosting/parent without pretending they are managed children.
- `operation_id` nullable scoped FK; required for operation-specific bootstrap context.
- `target_tenancy_ocid` nullable until qualified handoff; `expected_parent_ocid`, `region`, `realm`,
  `identity_domain_binding_id` for child contexts. The referenced domain binding is the canonical
  child domain OCID/endpoint/verification revision; do not keep an independently writable endpoint here.
  External hosting/parent contexts instead use qualified `external_identity_domain_ocid`,
  `external_domain_endpoint`, `external_endpoint_verified_at` when needed.
- `authentication_method`: qualified workload_identity or api_key. `principal_binding_id` for a bound
  child user; `external_principal_reference` closed nonsecret reference for configured hosting/parent
  workload/API principal. These are alternatives, not two editable identity sources.
- `credential_id` nullable FK; required for API-key use, absent for workload identity.
- `generation`, `state` (pending, verified, unavailable, retiring, retired),
  `verification_operation_id`, `verified_at`, `capability_evidence` and `created_at`.

Constraints: current identity/credential/target binding is checked together before signing. Context
verified does not certify all future calls; evidence declares exact service/profile, time and coverage.
For child contexts, target_tenancy_ocid must match the scoped registry when known; prefer a
same-target composite FK and reject dispatch while unknown. Child domain endpoint/ID resolve from
the verified domain binding; configured hosting/parent contexts hold their separately verified external
principal/domain facts. Attempts capture immutable endpoint/domain-revision snapshots; dispatch
requires that revision still to match the canonical binding. These are not independently editable
alternative child targets.
Domain endpoint must come from verified OCI metadata/realm validation, never arbitrary browser URL.
Pre-OCID bootstrap can hold staged material/context but cannot dispatch child writes until target,
domain and signer mapping are verified. Initial activating human, bootstrap API user, permanent signer
and intended owner remain distinct identities. Parent/hosting scope never follows the app deployment
location implicitly. Child credentials cannot substitute for parent/hosting permissions.

Do not weaken The configuration model's required child binding FK to fabricate parent/hosting registry records. The closed
external-principal reference is intentionally a configured signer fact, not a new organization or
managed-identity lifecycle. If later managing parent/hosting identities is required, review that scope
explicitly. Workload principal claim/subject identity is not a user OCID and has no private-key version.

### 2. `otm_credential`: durable credential head and exposure obligation

Fields:

- `id`, `workspace_id`, `tenancy_id` nullable for hosting/parent, `principal_binding_id` nullable,
  `access_context_id` nullable. Require a qualified principal subject via child binding or external
  context; enforce one canonical ownership scope and kind, not orphan reusable secret references.
- `kind`: api_signing_key or recovery_password; `purpose` (bootstrap, automation, parent, hosting,
  independent_recovery); `generation` and `state` (staging, usable, rotating, unknown, unavailable,
  retired). An emergency password does not become a background-job signer.
- `current_version_id`, `staged_version_id`: nullable same-credential FK pointers; distinct when set. For recovery passwords, current is last-reconciled version evidence, not a normal retrieval selector: resolve its stable `vault_secret_ocid` and request Vault `stage="CURRENT"` (D54). Staged identifies the exact in-progress candidate. API signing-key verification/selection is unchanged.
- `exposure_generation`, `first_disclosure_at`, `rotation_due_at`, `active_window_grant_id` nullable;
  `rotation_operation_id`, `rotation_status`, `restore_reconciliation_required`.
- `created_at`, `updated_at`; actor/provenance in audit.

Conditional rules: API keys do not inherit the password's four-hour disclosure policy. For a recovery
password, the first authorized disclosure attempt opens one exposure window, due exactly four hours
later. Serialize opening/joining that window on this head; overlapping requests inherit its earliest
unchanged deadline. A retry/second admin cannot move it forward. Retain window/deadline history in
grant/audit records when advancing to a new verified credential generation. No fresh disclosure after
the deadline while rotation is pending/unknown/unverified; no stale current-version fallback.

The recorded current pointer reflects a reconciled usable version. D54 makes Vault CURRENT the
normal recovery-password source; the DB pointer is audit/cache evidence. An unknown external change
makes the head unavailable/unknown even if a previous pointer remains for history. A staged secret is not current.
Promotion and retirement require per-kind provider evidence and C2 generation checks; a successful
Vault write alone does not prove the child password changed or new key works. Retirement of usable
bootstrap material follows verified permanent signer + safe replacement/last-admin checks.

### 3. `otm_credential_version`: immutable nonsecret version metadata

Fields: `id`, `workspace_id`, `credential_id`, positive `version_number` unique per credential;
`vault_secret_ocid`, exact `vault_version_number`/qualified immutable version identifier,
`public_key_fingerprint` for API keys, public-key hash/algorithm where needed;
`created_operation_id`, `created_step_key`, `created_at`; immutable provider/principal binding snapshot.
Use mutable lifecycle/verification summaries on the head/operation and append audit evidence rather
than rewriting immutable secret-version history. A Vault stage such as CURRENT is not an immutable version identifier: D54 uses it for normal
password resolution and records the actual returned version for audit. The stable secret OCID is
reused across that password credential's version rows; do not select normal passwords using the
DB's historical `vault_version_number`. Exact versions remain for in-flight rotation and API keys. No passwords, PEM private keys, OAuth access/refresh tokens, MFA seeds or activation
links appear here, in jobs, logs, exported tables or notifications.

Staged known password exists recoverably in Vault before requesting its application in the domain.
Unknown password change preserves both candidate/prior references and exact step correlation until
qualified reconciliation; it does not label either as proven current. New API public key is verified
through an independent new signer before promotion/old-key retirement, respecting capacity and grace
rules still to qualify. App-secret retrieval is restricted to resolver/disclosure paths; UI returns
public PEM only for bootstrap. An emergency password disclosure is the explicit exceptional response.

### 4. `otm_access_assignment`: access intent, distinct from association and signer

Fields: `id`, `workspace_id`, `tenancy_id`; nullable `association_id` to existing owner/member
relationship, nullable `operational_subject_binding_id` plus typed operational `purpose` for
automation/recovery. Exactly one ownership variant (association or operational purpose) is allowed,
with scoped FK checks; `previous_id`, immutable
`revision_number`; `profile_reference`, `profile_version`, `profile_contract_version`;
`subject_logical_key`, optional `existing_subject_binding_id`, `scope_logical_keys`, and closed
nonsecret `parameters` (profile mode, selected parent/existing compartment bindings, new compartment
name, granted role/group references and required policy-context/hash); `accepted_operation_id`, `created_by`, `created_at`.

Association head extensions: `desired_access_assignment_id`, `last_verified_access_assignment_id`,
`access_generation`, `current_access_check_id`. Operational purpose heads, including
`access_generation`, live on their canonical bound user only. Disclosure requests do not own access
assignments or check heads. Do not also keep an independently writable context head.
Never infer app admin entitlement from this record.

Each head advances its access generation before and after relevant mutations, including same-OCID
grant repair, credential/context changes and root-policy changes affecting that coverage. Checks
capture access generation plus credential/context generations and publish only while all remain
current. This counter is distinct from object replacement and worker execution generations; unknown
effects block verified publication. Operational automation/recovery assignments need no employee
association; their accepted intent and same-owner heads are committed under the C2 boundary.
Store immutable accepted revisions; current publication/retirement remains existing association/C2
state. Registered versioned profile references are sufficient until an actual editable profile
catalog is designed; do not invent a profile-authoring table/API here.

Accepted access intent can precede user/compartment creation. Preserve immutable logical keys and
known selected-scope binding references; do not invent provider IDs or mutate the assignment later
to fill them in. Verified operation-step/binding evidence resolves those logical keys after creation.
The new binding head can then reference this already accepted assignment. Every JSON-held binding
reference is explicitly validated in the same tenancy/domain at acceptance and dispatch.

One current assignment per association or canonical operational purpose; verified and desired are
distinct. Owner remains full admin; member selects accepted scoped/full-admin profile explicitly.
Use current generation and still-active intended relationship at dispatch to prevent stale repair
resurrecting offboarded access. Preserve stable person/association mapping through email/name merge.
Replacement owner access verifies before old-owner cleanup; old cleanup obligation survives current
owner switch without creating two current owners. Deleting a member's bound personal child identity
requires safe-use/ownership checks and preserves upstream SSO, shared groups and workload compartments.
Required user/group/capability observations reuse typed managed-object observations/issues with explicit
access-assignment context; the shared check discriminator and intent FK below carry access context rather than falsely tying
every identity observation to an OCI baseline revision. Final migration/adapter qualification remains open.

### 5. `otm_human_access_grant`: credential disclosure request and exposure window

The retained table name does not represent a new OCI user or independent grant/rotation engine.
Every row records one authorized request for the persistent recovery credential. Proposed fields:

- `id`, `workspace_id`, `tenancy_id`; `requesting_subject`, immutable `requester_snapshot`
  (issuer/subject/display_name/verified_email/profile provenance); optional `person_id` only when
  unambiguously linked; `request_key`, `payload_digest`, `accepted_operation_id`.
- Required same-tenancy `credential_id` and exact same-credential `disclosed_version_id`;
  `window_root_grant_id`, `exposure_generation` identify the shared exposure window.
- `lifetime_policy_version`, `duration_seconds=14400`,
  `deadline_anchor=first_authorized_disclosure`; `accepted_at`, `first_disclosure_attempt_at`, `due_at`.
- `state` as a projection of disclosure/rotation evidence, `verified_rotation_at`,
  `resolution_evidence_event_id`, `resolved_at`. Resolution requires the credential head's verified
  rotation outcome and corresponding C2 evidence, not a timer or editable success flag.

No named-support kind, desired/verified access-assignment pointers, access-check head, access generation,
cleanup operation or user-revocation timestamp belongs here in V1. The canonical recovery binding owns
its operational access assignment. The credential head owns `rotation_operation_id` and rotation state;
requests derive progress through it and retain immutable window/verification evidence.

Unique workspace/authenticated subject/command request key plus digest handles lost responses without
opening duplicate requests. Root request anchors the exposure window. Joining requests must reference
the same credential/version/generation and original deadline; no one-open-request-per-administrator
restriction prevents separately audited retrievals. Root may reference itself or use null with an
explicit root constraint; exact deferred FK ordering belongs to migration design.

Before returning secret content, commit request/disclosure-attempt audit, notifications and durable
rotation obligation atomically. The credential head and root request agree on the earliest deadline.
A network loss cannot prove the response was unseen and cannot reset that deadline. Each subsequent
authorized retrieval has its own request/audit/notification evidence and joins the same window.
At/after due time, or while rotation/current credential state is unknown, deny release until verified
reconciliation/rotation. Do not offer a prior Vault version as fallback. Avoid unbounded disclosure
arrays and do not claim requester identity proves subsequent shared-account usage.

The recovery password is unique per tenancy; only its authorized non-cacheable response exposes its
value. D39's exemption applies only to this bound recovery identity, with verified policy scope;
it does not exempt owners/members or weaken OTM SSO entitlement. Stage the candidate password in Vault,
apply it to the child, reconcile/verify and promote the correct Vault version through existing C2
steps. Neither a Vault write nor elapsed four hours proves usable rotation or universal session logout.
If automation authority is lost, surface independent manual recovery and keep the obligation visible.

### UI, audit and recovery mapping

- Onboarding: context states, distinct identity bindings, public bootstrap PEM, verified permanent
  signer and required owner/recovery assignment facts. Owner first-login is a separate observed fact;
  it is not inferred from invitation or required for setup under D20. Add observed enrollment/login
  evidence to typed identity observations, not a newly invented MFA method.
- Required access/repair: bound user exists, signer authenticates, profile privileges verified,
  MFA policy/enrollment facts and observation freshness remain separate. Check failure is not absence.
  A human may have access even when the automation context cannot authenticate; neither fact is app
  SSO entitlement. No Repair without adequate independently verified machine authority.
- Recovery retrieval: request + authenticated requester, exact disclosed version, original deadline,
  canonical credential rotation operation, overdue/unknown state and separately qualified session outcome.
  Never label four hours a universal token/session cutoff. Retrieval response is authenticated and
  non-cacheable; historical versions are not retrievable through old grant links.
- Restore: restored DB grants/current pointers do not prove OCI/Vault state or later disclosures.
  D12 external restore fence blocks ordinary disclosure/dispatch until reconciliation/release. Recover
  earliest trustworthy deadlines/exposure; unknown lost history is an urgent recovery incident, not
  a renewed window. Reserve urgent rotation capacity while preserving required safe access checks.
- Custodial recovery: only nonsecret custodian/runbook/version references belong in accepted operational
  profile metadata. D39 selects recovery-only MFA exemption; qualify its exact identity/policy scope
  without changing owner/member MFA. Out-of-band recovery must work without OTM/SSO/automation;
  independent custody and manual rotation procedures remain explicit operational qualification.


### 6. `otm_admin_session`: application local/SSO session, not engineer access

[Implemented settings/cleanup](../reference/application-settings.md) add the sixteenth session
field, `idle_timeout_seconds`, pinning issued idle policy while `expires_at` pins absolute lifetime.
The central TOML defaults are 30-minute idle/eight-hour absolute; daily bounded cleanup removes invalid
rows without touching administrator identity or audit. Real activity updates last_seen_at conditionally;
polling never refreshes it. This adds no table. Local/SSO issuance and D58 grant design remain separate.


Proposed fields: `id`, `workspace_id`, unique `session_token_hash`, `issuer`, `subject`, verified
nonsecret `display_snapshot`, `entitlement_reference/revision`, `entitlement_checked_at`,
`auth_time`, `created_at`, `expires_at`, `idle_timeout_seconds`, `last_seen_at`, `revoked_at`, `provider_session_reference_hash`.
Use a maintained SSO/session library and opaque secure cookies; no raw session token, identity token,
access/refresh token or password in these rows. A refresh credential, if actually required, needs a
separately protected secret reference, not an exception to this rule. Exact library/provider remains
implementation qualification, not a custom authentication design.

An SSO subject is not inferred from employee email and does not confer admin rights through tenancy
ownership. Session expiry/revocation and current entitlement are checked before sensitive actions;
a cached old group claim is not proof an employee still has access. Corporate disable/logout latency
and revocation integration remain qualified behavior, not a promise of instantaneous logout.
Break-glass disclosure additionally requires current entitlement and non-cacheable response handling.
This table is the sixth C4 table; it does not create a second employee/user directory. D54 restore
procedure revokes all restored sessions through existing `revoked_at` state and requires fresh SSO/
current entitlement before administrative use; no external session-cutoff service is needed.

Context/credential heads form scoped insertion cycles. Create a pending context without a credential,
create its credential head and immutable staged version, then attach same-owner pointers in one
transaction using explicit deferred constraints/checked ordering. A context is not dispatchable until
all identity/target/current-credential checks pass. A credential with an unresolved password/key
outcome is not usable merely because a prior current-version pointer still exists. Grant root/window
pointers similarly require atomic creation and cannot point to another credential/version/tenancy.

## Financial collection and observations

### Current source: D41, 24 October 2026

V1 reads each child's exact OTM-managed root Budget through its existing child automation context
and `BudgetClient.get_budget(budget_id)`. Capture `amount`, optional `actual_spend`, optional
`forecasted_spend` and optional `time_spend_computed` from **one immutable provider response**.
`forecasted_spend` is the provider's complete cycle-end estimate: never add actual spend to it,
extrapolate a replacement or compose it with a remaining-period forecast. No Usage API/parent
reporting or fallback is selected in V1. Historical cost reports, backfill, trends and historical
financial APIs are post-V1. Retained observations are operational/audit evidence, not approval of
historical product reporting. D42 accepts daily collection plus manual refresh. Schedule occurrence and request idempotency keep retries separate from deliberate new reads; neither trigger forces OCI recalculation.

The same two proposed financial tables are sufficient. There is no new budget-authoring table,
credential type, source identity, migration or runner. Baseline/override fields still own desired
budget amount. Financial observations record what this exact Budget response returned, separately
from desired configuration and full C3 verification.

### `otm_financial_collection`

| Field | Type / meaning |
|---|---|
| `id`, `workspace_id`, `operation_id`, `tenancy_id` | UUID/scoped collection operation and exactly one registered child target |
| `source_access_context_id`, `source_context_generation`, `source_tenancy_ocid` | This child's existing automation context and recorded generation/verified OCI target; no parent or host signer substitution |
| `budget_binding_id`, `budget_binding_generation`, `budget_ocid` | Exact live same-child `budget/main` binding and immutable target snapshot; no name-based selection |
| `configuration_id`, `configuration_generation` | Desired configuration context captured for comparisons/stale publication; financial success is not verification of this configuration |
| `source_policy_revision`, `scope_hash` | Pinned typed source policy: Budget read, qualified cycle/timezone and rate-card currency provenance, child-root owner/target scope |
| `source_kind`, `request_schema_version`, `request_parameters` | `child_managed_budget`; closed request `{budget_id}` and supported request correlation, not arbitrary Usage API filters |
| `expected_period_start`, `expected_period_end`, `billing_timezone` | Expected current monthly budget cycle, inclusive/exclusive, from qualified source policy; these do not assign old spend to a new cycle |
| `schedule_occurrence_key` | Logical acquisition identity; deliberate manual read uses a fresh UUID, delivery retry retains it |
| `state`, `coverage`, `provider_request_reference` | running/complete/partial/failed/obsolete and exact-object/authority/scope coverage; not fleet pagination completeness |
| `started_at`, `completed_at`, `next_due_at` | Acquisition and scheduling times; D42 daily schedule determines due time; exact time/jitter remains runtime policy; never a fake provider calculation timestamp |

One collection targets one child Budget. Freeze scoped context, object OCID/binding generation and
policy at acceptance; recheck live child/root identity and authority before reading. Record signer
credential version/generation in existing C2 attempt evidence. Credential rotation does not license
retargeting the request; stale identity/context changes require refreshed acquisition under current
C2 guards. Reads run outside DB transactions; publish under matching scope/generation fences.

Unique(workspace, source kind, tenancy, scheduling occurrence) prevents duplicate logical reads
from duplicate trigger delivery. A retried request cannot combine values from separate provider
responses. Unknown/failed reads retain safe attempt evidence and cannot manufacture zero values.

### `otm_financial_observation`

| Field | Type / meaning |
|---|---|
| `id`, `workspace_id`, `collection_id`, `tenancy_id` | UUID PK; same-workspace/same-tenancy FKs; one immutable snapshot per successful/qualified partial collection |
| `provider_tenancy_ocid`, `budget_binding_id`, `budget_binding_generation`, `budget_ocid` | Verified frozen target facts matching the collection; not independently editable attribution |
| `observed_owning_compartment_ocid`, `observed_target_type`, `observed_target_ocids` | Same-response root ownership/COMPARTMENT target facts; require this child root and reject conflicting/unverified scope before publishing usable finance facts |
| `observed_budget_amount` | Nullable exact `numeric(20,4)` from returned Budget `amount`; observed fact, not a second budget-authoring source |
| `actual_spend` | Nullable exact decimal from the same response; absence is unavailable, not zero |
| `forecasted_spend`, `forecast_semantics` | Nullable exact decimal; semantics fixed `complete_cycle_end`; projected total is this value alone |
| `time_spend_computed` | Nullable UTC provider calculation time copied from the response; not replaced with fetch/completion time |
| `captured_at`, `fresh_until` | Read time and versioned policy freshness boundary; both stay distinct from provider calculation time |
| `spend_period_start`, `spend_period_end`, `period_evidence`, `period_state` | Qualified cycle associated with returned spend, or null/unknown; typed evidence contains exact-response reset/processing/offset/one-time-date facts, qualified profile/evidence references and derivation. State current/prior/unknown never comes from acquisition timestamp alone |
| `currency`, `currency_policy_revision`, `currency_evidence_event_id` | Nullable qualified rate-card currency and provenance; Budget does not return a currency field. Never infer USD from a label or silently convert |
| `budget_availability`, `actual_availability`, `forecast_availability`, `diagnostic_code` | Independent available/unavailable/stale/unverified results with typed explanation; valid zero remains zero, unknown remains null/unverified |
| `budget_configuration_id`, `budget_observation_check_id` | Optional same-child comparison references; a complete same-read C3 observation may be reused without making financial success full configuration success |

Unique(collection_id) preserves one coherent read. Frozen target facts are checked against the source
header; they are provenance, not another canonical binding. Keep exact values, including negative
adjustments if the qualified source returns them. No selecting actual from one response, forecast
from another and budget from today's authoring draft while calling them one snapshot. A failed
collection leaves prior facts visible with their actual age/status; it cannot overwrite them with0.

The provider calculation timestamp and cycle must be qualified. If spend is still last cycle's data
at month rollover, retain it explicitly as prior/stale and show current-cycle spend unavailable.
Do not relabel it current because a read completed today. Missing `time_spend_computed` stays null;
unknown cycle or insufficient source freshness evidence stays unverified, even if numeric fields exist.
A subsequent read with genuinely qualified current-cycle calculations can replace the current view.
Record provider and capture dates so repeated reads cannot hide source age. Exact cycle attribution
rules require provider qualification; this model invents no extra Budget response field.

Current budget, actual and projected columns use this one authoritative same-read snapshot for
comparable display. Desired baseline/override budget remains separately labeled pending/different
when appropriate. Currency/basis/cycle/freshness uncertainty blocks misleading percentages, highlights
or cross-tenancy sums; comparable totals use a labeled org revision and qualified currency/scope.
Tool-side warning policy is versioned runtime configuration, not an OCI alert-rule definition. D45 independently derives red for qualified actual>observed budget and amber for complete forecast>observed budget; both may appear simultaneously. Qualified below-budget values may be green per value, including available actual with unavailable forecast; this is not a whole-row health claim. Equal values remain neutral and there is no 80% warning. Data status is separate. Pending desired budget does not replace observed budget for comparison. No additional financial-status table/column or cost-notification trigger is introduced.
No budget alerts, cost-history selector or backfill/reporting job is introduced by this proposal.

D46 approves independent Actual and Budget sort controls within one visual table column. Query key
`actual` selects `actual_spend`; key `budget` selects `observed_budget_amount`. Both use asc/desc,
null/unavailable last, and stable tenancy-ID ties; desired/pending values are never the budget sort
source. Sort/filter/page state belongs to the request/client, not new storage columns. D45 tooltip
retrieval maps to `captured_at`; internal `time_spend_computed` remains a qualification input.
[Chapter15](15-collection-and-operational-events.md) develops publication and selection using these
same two financial tables; it adds no third financial-truth store. The [C5 field map](16-c5-contract-review.md#field-to-model-map) distinguishes typed `period_evidence`/event payloads and profile-derived projections from physical columns; its test-only live/prior/authorization inputs are not persisted truth or client authority.


C3 may share this provider acquisition for Budget amount/scope verification. Publishing finance facts
alone cannot resolve a configuration issue, advance the full verified-configuration pointer, prove
absence of alert rules, or certify all required objects. Those effects require the complete current
C3 check/observation predicates and their normal generation/coverage transaction. Conversely, a budget
configuration check is not a fabricated spend calculation or native forecast result.

## Notifications, administrative history and command evidence

### Existing `audit_event`, production extensions

Retain existing `id/workspace_id/feed_id/version_id/actor/kind/at/data`. Add nullable scoped references:
`operation_id`, `intent_revision`, `step_key`, `attempt_id`, `plan_id`, `configuration_id`, `issue_id`,
`credential_id`, `credential_version_id`, `grant_id`, `financial_collection_id`; stable `actor_subject`
and display snapshot; `contract_version`, `data_hash`. Typed event data contains immutable intent,
provider correlation, safe outcomes or review decisions, not secrets or unbounded retry arrays.

Command receipts additionally have `client_command_key`, `command_digest`, `command_result` together,
unique(workspace, actor subject, command key) when present. Operation-intent events have unique
(workspace, operation, intent revision). Captured-preview events are immutable referenced receipts.
Request digests include command kind, target, payload and expected revision. A successful replay is
looked up before stale-revision rejection; mismatched reuse conflicts. No successful receipt survives
a rolled-back state change. Scoped references and kind-specific required fields are validated and
indexed; legacy actor text need not become a fabricated SSO subject.

Administrative history is append-only, indefinitely retained and exportable by entitled admins;
ordinary roles cannot rewrite it. Full-name/email metadata changes do not rewrite actor snapshots.
No raw provider logs, private PEMs, MFA seeds, passwords, activation URLs or bearer tokens in event data.

### Existing `notification_outbox`, explicit extension

| Field | Proposed meaning |
|---|---|
| Existing `id`, optional legacy recommendation/version links | Preserve organization notification provenance; old NOT NULL/unique constraints need explicit migration |
| `workspace_id`, `source_event_id`, `channel` | Required scoped event FK; V1 channel is `email` under D47, Slack is future-only; unique(event, channel) for one captured channel intent |
| `issue_id`, `operation_id`, `grant_id` | Nullable typed source references; source-event contract establishes exactly which trigger applies |
| `routing_revision`, `recipients`, `routing_evidence` | Frozen trigger-specific contacts at acceptance; D50 lifecycle selects responsible admin only with no fallback, other notice families retain required owner/manager/designee/admin routing |
| `template_version`, `safe_payload` | Closed versioned content, not an arbitrary executable template or secret |
| `state`, `attempt_count`, `next_attempt_at`, `provider_delivery_reference` | Delivery projection and due-work/correlation |
| `last_outcome`, `last_attempt_at`, `delivered_at`, `uncertain_at` | Known/partial/unknown delivery; append attempt evidence in audit |

One unchanged continuing issue generates one initial alert event; relapse after verified resolution
gets a new episode/event. Reminders/manual sends use distinct committed source events. V1 dispatches
email only under D47; later multi-channel delivery would use separate outbox intents. Retries retain the captured recipients/body and original
idempotency identity, not current mutable routing. Delivery uncertainty/partial recipient success
requires provider-aware reconciliation and bounded per-recipient outcome evidence; it is not blind
resend. No notification command can authorize tenancy mutation. The existing prototype's immutable outbox trigger cannot be reused unchanged: production migration
must permit only delivery-head updates while protecting source event, channel, recipients and content.
Append delivery outcomes to audit; never rewrite captured intent. New automatic events and outbox
intent commit atomically with their triggering state. Security-findings workflows remain V2.

D47 requires no new table or column. Email sender/service references belong to closed versioned
workspace runtime policy; secrets remain external references. `provider_delivery_reference` proves
only the qualified outcome attached to it: provider acceptance is not inbox delivery. Populate
`delivered_at` only with confirmed delivery evidence; otherwise retain Accepted/Delivery unconfirmed.
Before provider dispatch, typed `audit_event.data.delivery_context` captures runtime-policy revision,
approved service/account and sender references, adapter contract version, credential reference/version
and supported submission key. Retry/reconciliation uses that original service namespace; changing
current runtime configuration cannot redirect unknown mail outcomes or silently change sender. These
are nonsecret immutable attempt fields, not new table columns. Authorized credential rotation on the
same context is separately recorded; explicit service/sender replacement cannot bypass uncertainty.
The existing state/outcome/audit fields support rejection, partial and unknown submission. Full DTOs
and managed-service behavior remain qualification work. [Chapter15](15-collection-and-operational-events.md#d47-delivery-contract-email-in-v1)
traces every proposed delivery value to these existing fields. No V1 Slack setup/credentials or
dispatch can be enabled merely because a generic channel field exists.


### D48 financial-read incident evidence

After bounded acquisition retries are exhausted, one current failed-read episode produces one admin
email source event/outbox intent. Continuing retries, daily/manual requests and month rollover do not
create a new initial notice. Verified same-source acquisition recovery closes the episode internally;
relapse is a new episode. This is not a cost-overrun, missing-forecast or provider-lag email policy.

No new incident table/column is added. Typed `audit_event.data` records `failure_key`, `episode_key`,
`recovery_anchor_event_id`, `first_exhausted_collection_id`, retry-policy revision, safe failure code
and transition kind. Existing scoped `financial_collection_id/operation_id`, service-actor command
receipt uniqueness and outbox unique(source event, email) retain correlation/deduplication. Open,
recover and supersede decisions coordinate on the existing child registry row with current C2
source/generation guards, so concurrent/late outcomes cannot duplicate or regress the episode.
Audit events append; delivery heads alone remain mutable. [Chapter15](15-collection-and-operational-events.md#d48-accepted-alert-after-automatic-cost-read-retries-are-exhausted)
contains the transaction, source-identity, recovery and restore rules. Query/index/runner integration
and concurrency behavior remain implementation qualifications, not a claim that this prototype
already sends email. No automatic recovery/reminder emails or new retry-count default is introduced.

### D49 lifecycle attention evidence

D49 lifecycle email derives from committed operation state/stage/wait facts: `waiting` only when an
administrator action is required, actionable `needs_attention`, or known terminal `failed`. Routine
queued/running/provider/retry waits, success and cancellation send no lifecycle email. Required
access/credential notices and D48 remain separate. D50 routes lifecycle email only to existing `responsible_actor_subject`; no all-admin fallback applies.

Existing scoped audit references `operation_id/intent_revision/step_key` and typed
`audit_event.data.lifecycle_notice` carry `notice_kind`, `attention_episode_key`, affected child/step
references and routing-policy version. Existing outbox source-event/operation/template/payload fields
capture the notice. One unchanged attention episode or exact terminal transition has one initial
intent, with the existing command-receipt/outbox uniqueness and C2 publication guards. Parent-managed
attention retains child references rather than duplicating the same notice at both levels. A stale
worker or unsuccessful Resume cannot create a fresh initial event. [Chapter15](15-collection-and-operational-events.md#d49-accepted-lifecycle-email-only-for-action-or-terminal-failure)
records identity, trigger and content rules. No new state, table/column or success-email feature is
introduced. D50 routing is accepted; implementation concurrency/delivery qualification remains open.

### D50 responsibility and routing evidence

Initialize `otm_operation.responsible_actor_subject` to the initiating authorized admin; explicit
audited takeover changes that field and the operation revision while preserving immutable creator/
activation facts. Viewing an operation changes nothing. D50 lifecycle notices have exactly that
current responsible administrator as recipient; missing/unauthorized/unreachable recipients produce
visible blocked/failed routing, never an automatic all-admin email. Other alert families keep their
required recipients and fallback semantics.

Typed `audit_event.data.lifecycle_notice` records `responsible_actor_subject`,
`responsible_operation_revision`, `recipient_snapshot`, `routing_policy_revision` and optional
`responsibility_event_id/supersedes_notification_id`. These JSON fields join existing operation and
outbox references; no new column/table or separate assignment head is added. Notice acceptance and
pre-dispatch checks guard the current assignment/entitlement. Existing frozen outbox recipients are
not mutated: only a known unsent intent may be superseded with an audited corrected intent; accepted/
uncertain sends retain original correlation and D47 reconciliation. An in-flight email cannot be
atomically recalled by reassigning the operation. [Chapter15](15-collection-and-operational-events.md#d50-accepted-responsible-administrator-only)
records parent/child scope, delivery races, takeover and source-event rules. Concrete constraint/
transaction/entitlement tests remain implementation qualification.

## Shared observation model: configuration and access

The [typed access field contract](12-access-health-and-repair.md#typed-access-observation-envelope)
names identity presence, API authentication, qualified privilege coverage, observed console/MFA
facts and recovery-readiness evidence inside the existing typed observation fields. The
[screen field inventory](12-access-health-and-repair.md#field-by-field-contract) maps every new
Required access display/control to these records, immutable intent or transient state.


Chapter10's proposed shared records are named `otm_tenancy_check`, `otm_object_observation`,
`otm_tenancy_issue`; these replace the earlier configuration-only **proposed** names, not runtime
tables. A check has exactly one `configuration_id` or `access_assignment_id` according to `check_kind`.
Its target/generation/binding coverage are scoped to that intent. Checks and issues also carry
`coverage_subject_kind` and `coverage_subject_key`: backend-derived configuration tenancy, association
UUID or canonical operational identity/purpose. Disclosure request IDs are not access coverage owners. Scoped subject FKs and
a closed operational-purpose enum validate the key; arbitrary browser strings cannot select coverage.
The stable subject survives assignment revisions and is part of acquisition uniqueness, open-issue
uniqueness and resolution guards. Evidence from recovery inspection cannot close automation loss,
and one member inspection cannot close another member’s issue. Access checks cannot claim health
from an unrelated baseline or compare SCIM IDs as OCIDs. Add the exact verified `access_context_id`
used, its generation, and source operation where applicable.

Per-association and canonical operational-user heads each point to their own scoped check. Overall tenancy access health aggregates every required current assignment; a recent passing owner check cannot replace a failed automation/recovery result.

Required access is a projection of observed identity existence, key/signing health, privilege/profile
checks and available MFA/enrollment/first-login evidence. These facts stay distinct. An existing user
is not proof the SDK signer works; successful signing is not proof every required domain role works.
Repair is only actionable with independently verified sufficient automation. A full-admin owner may
remove access; report/notify rather than assume parent-child membership bypasses that loss.

Configuration drift queue selects only confirmed configuration episodes. Access-health queue selects
access episodes. A tenancy's issue icon can link all counted types without making check failures into
confirmed drift. Repeated observations reuse one open condition; failed checks never close prior
confirmed loss. Permission recovery requires current qualifying observation, not clicking Dismiss.
Observation sequence and logical acquisition identity are different: sequence orders runs, occurrence
key deduplicates delivery, generation rejects stale context. Partial/failed fresh results are explicit.

## Recurring work, platform recovery and database operations

No extra application tables are proposed for a second scheduler, restore workflow, metrics store or
Kubernetes desired state. Use C2 steps/jobs, typed audit receipts, workspace recovery fields, and
Terraform/deployment state in their proper authorities.

- **Recurring work:** persist stable occurrence key `(kind, target, coverage_subject, nominal_due)` or manual UUID,
  policy revision, next due time/wake condition and wake generation. Unique scheduling receipts on
  audit or run headers prevent repeated triggers from allocating duplicate logical work. Queue IDs
  and attempt numbers are not occurrence IDs. Continuation enqueue commits with progress/audit.
- **Organization feed:** source acquisition IDs remain org_feed observations; equal file content
  creates a new observation when deliberately acquired, while delivery retry keeps one ID.
- **Credential deadlines:** authoritative credential head/grant rows retain the original earliest
  exposure deadline and due rotation operation. Scheduler delay raises an urgent condition; it cannot
  extend access or release a stale password. Reserve worker capacity under C2.
- **Restore (D54):** stop old processes and start the replacement in deployment maintenance/read-only
  mode with workers/dispatcher/triggers suspended. Use existing operation state/audit for manual
  reconciliation and selected resumption. No external control object, epoch mirror or receipt journal.
  Resolve passwords from stable Vault secret OCID plus CURRENT, and manually review uncertain
  rotations/deadlines and queued messages before leaving maintenance.
- **Backups:** backup IDs, provider DB system/endpoint, restore point and drill results are nonsecret
  external-provider references in audited recovery operation intent. Terraform/configuration owns
  infrastructure definitions. OCI managed PostgreSQL PITR creates a new DB system; endpoint/network
  cutover, compatibility and measured RPO/RTO remain C6 qualification. D51 accepts 15-minute RPO/4-hour RTO objectives and D52 in-region scope; these are existing versioned runtime-policy values, not new columns. The [recovery evidence contract](06-platform-and-delivery.md#measurement-and-evidence) maps incident/restore/commit/readiness timestamps, measured gaps and unresolved effects to typed operation/audit data, with available provider/deployment logs and documented manual evidence; D54 does not require an external receipt journal.
- **Runtime settings:** nonsecret schedule/freshness/threshold/concurrency/retention policy lives in
  the versioned workspace runtime policy, not a child baseline or arbitrary operator SQL.
- **Platform alerts:** failed/late jobs derive from operation/check/collection/deadline records;
  DB/network outages use external monitoring. Do not manufacture a child tenancy to store global
  incidents. Audit/outbox source events retain relevant correlation without another incident database.

Use least-privilege API/worker/migration/export roles, private authenticated TLS connections,
parameterized queries, scope guards and immutable-history protections. Mutating operational heads
are distinct from immutable version/evidence rows. Managed-service privileges and runner enqueue in
the same DB transaction need qualification; schemas and diagrams do not prove them. No production
reset/truncate endpoint. Read/export bounds, autovacuum and historical growth require measurements.
[Provider restore reference](https://docs.oracle.com/en-us/iaas/Content/postgresql/point-time-recovery.htm).

## UI and prose field coverage

Each visible/input field is one of: persisted canonical data, derived projection, immutable snapshot,
transient form/query state, or secret material obtained only through an authorized non-cacheable path.
There is no requirement to persist a redundant database column for a count, page number or derived name.

| Screen / fields | Canonical source or persistence boundary |
|---|---|
| Organization name/email/manager/leader/LOB/designees | org_member + pinned org_version configuration/person edges; manager/leader names joined in that same revision |
| Organization ancestry/presence/absence and evidence | Existing member/recommendation/source revision facts, not OCI scan results |
| Organization tenancy count / person associations | Active registry associations; cleanup obligations shown separately; count includes ownership |
| Upload CSV / feed capture/diagnostics/current revision | org_feed + version heads; raw upload is acquisition input, converted canonical JSON immutable evidence |
| Actionable/informational tabs, dates, before/after | Existing organization recommendation episodes/events; metadata history not copied into config issues |
| Create/import/add/remove/merge/offboard action controls | Explicit capture-preview + accepted operation; stable person/association IDs, not editable email identity guesses |
| Tenancy name/OCID/type/home region/parent | Registry actual provider fields; requested pre-discovery values labeled from operation intent |
| Tenancy owner/direct manager/LOB/member count | Active owner association + pinned org projection and owner-inclusive active member count |
| Assigned baseline / Update available | Desired config baseline versus workspace current-for-new; last fully verified and pending context separate |
| Configuration issues icon / exact detail | Distinct open shared issues and observed freshness; direct issue or tenancy-filtered list, not count per join row |
| Total/individual/shared/unassigned cards | Query-derived active inventory statistics using the same scope as the table |
| Baseline history version/published actor/date/current/count | Baseline explicit columns, publication audit, workspace head, labeled desired/verified assignment aggregates |
| Baseline authored policy text | `otm_baseline_version.policy_statements`; complete editable authored strings only |
| Required policy readonly block / provenance | `otm_tenancy_configuration.required_policy_manifest`, hash and render-contract version; immutable `policy_rendering` audit receipt supplies resolved strings and all contributors |
| Final policy preview / drift expectation | Authored list + generated list, exact-text dedup; rendering event’s `effective_policy_statements`, `statement_provenance`, `rendered_policy_hash`; same bound policy OCID |
| Baseline quota text | `otm_baseline_version.quota_statements` array of complete strings |
| Baseline monthly budget / currency / no alerts | `monthly_budget_amount`, `budget_currency`, `budget_period`; current Save/editor require positive whole units, while exact NUMERIC(20,4) read/history storage and V1 no-alert invariant remain |
| Baseline namespace / key/value rows | `tag_namespace`, `tag_defaults` typed array; definition/default bindings are separate provider objects |
| Override checkbox and statement/value fields | Nullable accepted override columns; drafts mirrored in plan_target proposed columns; NULL means inherit |
| Old baseline / new baseline / current override comparison | Source config baseline FK, target baseline FK, source override columns; no three editable copies |
| Keep override / Use new baseline / ready/review count | Content-bound per-block plan-target review data; all-target server gate; counts derived once per tenancy |
| Publish / update-existing / Start | Separate baseline publish and whole-plan operation acceptance; queueing is not verified application |
| Drift expected/observed/object/time/status | Exact config/access intent, binding OCID/SCIM identity, immutable observation coverage/time/result |
| Repair control / recovery guidance | Verified access capability plus persisted repair selection; unavailable automation exposes no false automated action |
| Onboarding owner/type/parent/requested name/home region | Accepted immutable operation intent plus pending registry/person references; final provider values separately verified |
| Activation administrator/name/email/status | Immutable initiating actor and operation stage/wait; no corporate password/token delegated |
| Activation administrator user OCID / confirmed retirement identity | Create-only `activation_administrator_user_ocid` in immutable operation intent; verified managed-user binding stores same-child domain FK, OCI OCID, SCIM ID and operation/confirmation provenance; import leaves absent |
| Bootstrap public PEM / temporary username / supplied user OCID | Public key derived from staged secret; identity display and user mapping bound in intent/access context; private PEM stays Vault |
| Import OCID / identity-domain / parent check / actual name | Verified registry/domain bindings and scoped inspection operation evidence; supplied fields never overwrite without checks |
| Shared member existing/new parent/path/profile/scope | Versioned access assignment parameters + compartment/domain/identity bindings, immutable step inputs |
| Transfer replacement owner / previous-owner disposition | Parent operation intent per association, desired access assignments; one current accountable owner |
| Offboard all associations / per-target results | Immutable person-plan intent + child operations + retained/retiring associations; zero-link final directory state derived |
| Operations list state/stage/wait/correlation/updated | C2 operation/step heads and immutable intent/attempt events; parent progress derived, no SDK calls per row |
| Recovery requester/deadline/rotation/result | Disclosure request + exact credential version + head exposure window + canonical C2 rotation operation; no secret in history |
| Actual/monthly budget/projected/currency/freshness | One D41 Budget snapshot: observed_budget_amount, actual_spend, complete-cycle forecasted_spend, time_spend_computed, qualified currency/cycle and visible source age; never actual+forecast |
| Audit actor/action/target/time/result/export | Typed immutable events, scoped filtered export operation and redacted artifact reference |
| Search/filter/sort/page size/page selection | Transient URL/query/browser state; deterministic scoped server queries, not new tables |
| Sign-in display/admin ability | Current validated SSO session/entitlement, not tenancy ownership or a feed role |
| Clean workspace / sample-simulation notices | Existing lab-only behavior, not production delete/reset capability or stored cloud state |

A complete statement can wrap visually without becoming multiple array entries. The approved current
editor uses one policy block and one quota block, one complete nonblank physical line per statement;
on explicit Save it converts those lines to ordered array entries. This is an editor contract, not
a database limitation: direct API/legacy items may still contain embedded newlines. Reads/reopening
never rewrite stored values; saving through the revised editor normalizes visible newline boundaries.
Validate list item grammar/length/permission references under the qualified OCI adapter before future
dispatch. No policy, quota or tag input is executable application code.

## Keys, indexes and transactional obligations

In addition to chapter10's constraints, propose scoped FK indexes for every access context,
credential/version, principal/subject/target binding, grant, operation/parent and collection relation.
One live canonical context per purpose/child or configured parent/host, with bootstrap additionally
scoped to operation. Exact version pointers are same-credential, not arbitrary Vault stage labels.
Session token hashes are unique; expiry/revocation lookups are indexed. Grant/credential due times
and operation/step next_due support bounded workers. Access assignments are unique per owner/revision,
with validated same-owner pointers (association or operational identity). Financial per-child occurrence and one-snapshot-per-collection keys
are unique; add tenancy/spend-period/captured-time indexes for selected current-snapshot reads. Outbox unique
source-event/channel and due-work indexes support retry without a second delivery engine.

FK indexes follow actual query plans; arrays/JSON references are not claimed to be relational FKs.
Avoid blanket JSON indexing, unbounded embedded histories and premature partitioning. At 250 tenancies,
start with one source of truth and measured queries. Scope predicates, stable tie-breakers and
preaggregated association/issue counts prevent pagination/count errors. Indefinite audit is retained;
financial/observation archival and backup growth remain explicit operational policies, not truncation.

## Validation scenarios and remaining qualification

The following are **planned implementation tests**, not executed DB/provider behavior:

- Registry pending → verified OCID/name/home region without fake IDs; wrong parent, realm, region,
  duplicate OCID, renamed same OCID, blocked cross-workspace targeting and failed reads preserving facts.
- Complete policy/quota lists, exact budget decimal and namespace/key/value rows round-trip through
  baseline columns → resolved payload → bound provider IDs → observation → UI detail.
- Statement/tag duplicates/null/malformed values reject; override NULL inherits and full list replaces;
  policy/quota/budget OCIDs stay stable for content updates; recreation preserves binding generations.
- Domain SCIM/user OCID mapping cannot swap; membership endpoints cannot cross child/domain; observed
  built-in principals cannot be destroyed as owned resources; loss of automation yields manual guidance.
- Stable identity merge preserves ownership/shared membership/access intent; pending/retiring old-owner
  cleanup remains visible with one current accountable owner and no compartment/workload deletion.
- Create/import/offboard preview consumed once; name amendment preserves all intent revisions; repeated
  acquisition vs delivery retry and wake occurrence vs execution attempt remain distinct.
- Credential stage/apply/promote/retire and unknown outcomes preserve recoverable references; key/password
  checks are independent; repeated disclosures cannot extend the original window or expose historical keys.
- SSO disable/revocation/expired session, unauthorized read/export/disclosure and unavailable provider
  fail with correct access boundaries; exact upstream revocation latency remains qualified behavior.
- D41 exact child-budget source, binding/context generation and one-response values cannot mix; null/stale
  actual/forecast never become zero. Complete-cycle forecast never adds actual; currency provenance and
  month rollover prevent false current/comparable totals. Parent Usage API/history/backfill remain post-V1.
- Notification trigger/state/outbox atomicity, uncertain/partial delivery and restore do not blindly
  replay; current routing cannot rewrite accepted recipients; no secrets leak into prototype/data/logs/results.
- D54 manual restore stops old processes, holds restored work and rejects stale disclosure; recovered deadlines cannot
  restart access windows; normal process restart remains automatic and distinct from restoration.

Recovery-only MFA-exemption enforcement, independent custody, full session revocation, policy-access composition, provider grammar/permissions,
late binding, Budget cycle/currency/freshness qualification, D42 daily/manual collection, queue transaction integration, all-path DB
concurrency and measured restore/query behavior remain explicit production gates. The data model
now names the fields/state/evidence to represent them rather than assuming successful qualification.

## Diagram set and authority

The production proposal is deliberately split to remain readable:

- [Existing organization ER](../../prototype/docs/organization-er-diagram.md): ten **implemented** tables.
- [Configuration ER](../architecture/diagrams/configuration-data-model-proposed.svg): explicit statement/budget/tag fields, overrides, object bindings and shared observations.
- [Application-administrator ER source](../architecture/diagrams/application-administrators-proposed.mmd), rendered in [chapter19](19-administrator-provisioning.md#detailed-checkpoint-two-new-tables-existing-sessions-and-audit): grants, local credential, existing sessions and audit extension.
- [Core/access ER](../architecture/diagrams/production-core-access-proposed.svg): tenancy identity, associations, operations, contexts, credentials, assignments, grants and sessions.
- [Financial/delivery ER](../architecture/diagrams/production-finance-proposed.svg): collections/facts and reused audit/outbox/workspace controls.

Each production diagram has adjacent Mermaid source, PNG and Excalidraw exports. ER Excalidraw files
contain an image that can be moved/annotated, not independently editable table boxes; edit the .mmd
source to change structure. Figures omit repetitive workspace edges and selected fields for space;
these explicit field contracts govern. No omitted box label removes the fields defined here.

## Catch-up review evidence

The documentation reviewer checked the actual prototype and all three current walkthroughs against
chapters10/11. No displayed/input business field remained without named storage, immutable intent/
evidence, a documented derivation, or an explicitly transient/secret-only boundary. The coverage
matrix above records those design mappings; it does not claim that the full proposed application
is implemented. The current local subset and its six real tables/UI projections are documented above.

Historical pre-D40 review: the independent engineering review identified four design gaps, including named-support assignment ownership,
access-check/issue coverage identity, canonical domain endpoint ownership, and access-generation
fencing for operational/grant heads. Those contracts are now explicit. A bounded recheck of these
four changes reported no new material findings; provider and database behavior remain unqualified.

Validation on 21 October 2026: all 249 local links/anchors across 14 design/reference documents passed;
all 10 explicit baseline/override field names matched the configuration ER source; diagram inventory
contained 18 proposed additions plus the existing ten tables. Three SVG/PNG diagram sets were
regenerated and visually inspected. Excalidraw conversion uses an image fallback, as disclosed above.
The inline-documentation checker passed 33 Python files and Ruff passed. No runtime code, migration,
prototype database or OCI resources changed, and the application test suite was not rerun for this
documentation-only update. The planned scenarios above are not reported as executed tests.

## Development handoff

Use this chapter and chapter10 as the unified proposed schema input; reviewers resolve field/state
contracts before freezing Python-generated OpenAPI, Alembic migrations and facade fixtures together.
Implement shared core/schema/resolution/operations serially first. Then UI, typed adapters and platform
lanes can build against the same fixtures without independently inventing tables or states. Retain all
organization prototype logic/tests and its approved UI. No new functional screens or DB changes are
introduced by this catch-up pass.

## D35 field-contract clarification

D35 A is accepted. [Chapter10](10-configuration-data-model.md#d35-required-policy-manifest-and-rendered-evidence)
adds the three explicit immutable configuration fields and typed rendering audit event described
above. A root-policy requirement change creates a same-baseline tenancy revision; ordinary role/
membership changes without manifest changes require no artificial policy write. This adds no table
and no independently editable generated-policy authority. Required role/identity/MFA verification
remains separate from policy matching. Earlier authored-only examples are historical resolution
inputs, not a full production payload.

## Historical D36–D38 human-access design, superseded by D40

D36 local child sign-in remains valid. D37's temporary named-support lifetime and the two-flow D38
screens are historical proposals for a feature now deferred from V1. They do not authorize named
user creation, named access-assignment owners, per-grant access heads or temporary-account cleanup
in this current model. D40's single persistent-recovery-account retrieval flow is authoritative.

The current app-style Access page uses existing disclosure-request, credential/version, binding,
check/observation, C2 operation and notification records. Ready requires scoped recovery-policy and
credential evidence; route fixtures cannot supply production proof. Dialog/tab/busy/scenario state
is transient. The field/flow contract remains in [chapter13](13-local-support-and-emergency-access.md).
No new table, runtime endpoint, database migration or actual credential is introduced by D40.





## D54 accepted model simplification — 26 October 2026

[The simple V1 contract](17-recovery-and-release.md) supersedes the withdrawn C6-A control/journal
proposal. Normal recovery-password resolution uses the stable existing secret OCID plus Vault CURRENT;
version rows/current pointers record observed history and exact staged work, not a stale password
selection rule. No new secret-locator column/table is necessary. API-key selection is unchanged.

Remove the unused workspace `recovery_epoch/recovery_state/recovery_release_event_id` mirrors from
the current proposed model/ER. Deployment maintenance and suspended processes enforce manual restore
pause; existing operation/audit state records held work and administrator review. Per-operation
`recovery_release_event_id` remains a review reference, not an external manifest. No independent
control/journal/installation/manifest tables or JSON envelopes are required. The table inventory
was 28 (10 existing plus 18 proposed); the later D58 administrator extension brings the current
full proposal to 30.


## Local application authentication implementation checkpoint

[The actual local-authentication guide](../reference/local-authentication.md) maps the existing
six-table model to operator bootstrap/reset, password-plus-TOTP proof, shared cooldown, last consumed
TOTP step and committed sessions/security events. Migration0006 expands only closed event kinds;
no MFA seed/password plaintext enters the DB. The opaque laptop reference includes a random UUID
and SHA-256 content digest; the future production Vault adapter must pin an exact immutable version.
`session_logged_out` records first revocation and audit in one transaction without IdP availability.
Ordinary administrator grants/regrants and corporate enabled-status checks remain separate work.

## Operations read projection implementation

The [complete UI/DTO source matrix](../reference/operations.md#public-dto-and-ui-field-map)
records every field now shown in the local Operations list/detail. Existing `otm_operation` owns
identity, state/stage and accepted/updated/completed timestamps. Its exact current `audit_event`
intent supplies the target OCID and allowlisted initiating display name. Current-intent
`otm_operation_step` rows supply attempt/state/verified time and validated outcome code; operation-wide
`audit_event` rows supply recent event time/kind/code. Pagination/count and `events_limited` are
snapshot derivations, not stored fields or new tables.

The public simulated-mode value reflects the current supported inspection kind/worker. No registry
adoption, verified real OCI permission or new provider observation is inferred. One read-only
repeatable snapshot keeps each response coherent; newest-50 display preserves older immutable rows.
Production remains six application tables/six migrations; the subsequent simulation slice brings
current exports to 21 schemas and runtime Python modules to 41. Its separate worker and typed
[configuration/catalog/submission field dictionary](../reference/simulation.md#simulation-configuration-and-field-map)
reuse these authorities without adding a table. Full proposed tenancy execution and other tables remain design.

## Durable simulation model extension without new tables

[The simulation field dictionary](../reference/simulation.md#simulation-configuration-and-field-map)
maps `SandboxConfig`/policy/targets, public catalog, submission and existing acceptance/result fields.
Private local state adds nullable `worker_password`; existing owner/API values and user data remain
preserved during explicit setup. Application TOML remains 14 keys; separate JSON config owns pause,
virtual targets and policy, never a real signer. The new HTTP/native-worker path writes only the
existing operation/intent/job/step/event authorities. Production remains six application tables,
six migrations/17 assets; 21 schemas and 41 runtime modules now describe the implemented local subset.

## Audit History projection without a new history store

The [Audit History source/actor matrix](../reference/audit-history.md#public-fields-and-source-map)
maps `id/at/kind`, nullable operation/administrator targets and private validated evidence to nine
public entry fields. Category and actor label are derived; the six query controls/five directory
fields are bounded inputs or read-snapshot calculations, not new columns. Worker actor shape is the
existing closed `{kind: worker, subject: inspection}` record, distinct from issuer-qualified human
snapshots. Failed sign-in public actor is null and is not a verified recovery-user action.

The nullable `administrator_name` projection joins the current administrator display name by both
workspace and administrator ID, including revoked grants. It is searchable directory context, not a
rewrite of immutable historical evidence; the target UUID remains visible if a name is unavailable.
No new column or table is required.

The shared read-snapshot helper keeps Audit and Operations consistent without DML. Raw payloads,
claims, credential/session identifiers and hashes are not public fields. Append-only retention and
existing operation/administrator scoped FKs remain unchanged; no second audit table exists. At the original Audit History checkpoint the shape was23 schemas/45 runtime modules, six
application tables/six migrations/17 assets and14 TOML keys. Instance branding adds one public
schema and three settings: at that branding checkpoint the shape was24 schemas/45 runtime modules and17 TOML keys, with
the same six tables/six migrations/17 migration assets. Audit rows remain read-only. The later CSV export adds immutable preparation evidence without
a second history store.


## Instance branding outside the domain model

`branding.display_name`, `branding.logo_url` and `branding.icon_url` are nonsecret process-loaded
application TOML settings, not organization or tenancy-baseline fields. A closed public projection
serves them for sign-in/navigation/browser identity. They add no table, column or migration; all
`otm_` identifiers remain unchanged when a deployment displays **Atlas**.


## Audit export and date-filter implementation

Forward migration0007 expands `ck_audit_event_revision` to allow the administrator-linked
`audit_export` kind with null operation/intent references, retaining all existing event constraints
and append-only protections. Its closed `data` contains `contract_version=audit-export-1`,
`row_count`(0–10,000), and `query_digest`(SHA-256), with the usual canonical `data_hash`, verified
actor snapshot, workspace, timestamp and scoped administrator FK. No plaintext query or CSV file
is stored. The existing `audit_event` table receives index
`ix_audit_workspace_at_id(workspace_id,at,id)` for scoped chronological/range reads.
`from_at`/`to_at` are query controls rather than new stored columns. No new application table or
role grant is introduced by this slice.

The production organization port currently implements canonical in-memory contracts and pure
CSV/reconciliation logic only. It does not migrate the prototype's ten domain tables or publish
organization revisions into the running app. Those production persistence/authorization bindings
remain the next organization slice. Existing/proposed model distinctions above still apply.


## Organization snapshot implementation sources

Forward migration0008 implements the five approved organization tables as specified in the
[storage dictionary](../reference/organization-storage.md#tables-and-field-sources). Its
[implemented ER source](../architecture/diagrams/organization-snapshots-implemented.mmd) separates two optional
head relationships from version ownership. Original emails are workspace-scoped identity anchors;
full PersonState evidence is stored once per `org_member` with readable matching columns. The
Revision header is in `org_version.data` without a duplicate people collection, and configuration
is frozen on each version. Delivery/source-byte digests and server receipt/source capture clocks
remain distinct. Terminal source evidence, sealed graphs and original identities cannot be rewritten
through ordinary DML; prototype and production data are not merged by this migration.

The existing shared `audit_event` CHECK now admits only the four reviewed organization kinds with
null operation/admin targets. `OrganizationEvidence` stores source/population/configuration and
nullable feed/proposed/applied correlation IDs plus counts; `data_hash` protects canonical integrity.
Publication computation has an explicit service actor after authorized administrator acceptance.
History/CSV expose only safe category/actor labels and the workspace-organization target, not raw
configuration, employee rows or source evidence. The schema adds no second audit table, outbox or
per-screen projection store.


### Local development organization reset

[The explicit operator reset](../reference/organization-screens.md#local-test-reset) clears only
the reviewed eight source/review/registry tables in a verified owned laptop installation. It introduces no
table/column/migration, changes no API-role privileges and preserves administrative audit and all
non-organization tables. Historical audit references to removed test snapshot UUIDs are intentionally
retained. Production organization history remains immutable; no reset HTTP route is introduced.

## Implemented guided onboarding subset — 31 October2026

Migration0010 adds allowed step/audit kinds to the existing14-table runtime, not the full proposed access schema. [The exact UI/field dictionary](../reference/tenancy-onboarding.md#existing-storage-no-new-tables) defines handoff OCIDs, create-only activation-account bindings, discovered metadata, cleanup confirmation and immutable attempt payloads. These are typed operation/step JSON and audit evidence; no new credential table or raw secret is introduced. Synthetic reservations are not real provider identity observations.

## Whole-tenancy deletion runtime — 31 October2026

[The deletion field dictionary](../reference/tenancy-deletion.md#complete-public-contract-dictionary) covers all19public fields. Existing operation intent JSON adds a server-owned whole_tenancy_deletion flag and per-association person_id/person_was_manager. Existing tenancy/membership/person pending/status fields and review/audit records handle all affected people; no table/column migration is required. Historical intents default to their original person-scoped behavior.

## Requested metadata and completed-record link — 31 October2026

Create uses existing OrganizationAction.name/home_region and immutable intent fields; home_region defaults null for noncreation commands and is required at create admission. Import ignores creation inputs and awaits discovery. CreationRegion.identifier/name and PersonWorkflow.creation_regions are parent-facade read models. OperationSummary.result_tenancy_id is derived by workspace+frozen-OCID registry join for successful organization actions. No new storage columns/tables/migration; requested and observed values remain separate. [Current field mapping](../reference/tenancy-onboarding.md).

The current OnboardingView also projects nullable requested_name/requested_home_region from frozen
create intent, independently of discovered metadata; the corrected guide enumerates all21view fields.
These and the result link/region choices are read models, not new storage columns.

### Implemented organization mapping settings — 2 November 2026

Organization mapping uses existing org workspace/version JSON authorities and recommendation
episodes, with no new table or column. The editor's segment statement is Configuration.lobs
(id,label,leader_email,designee_emails), while root is the single permitted policy field. Apply
pins a new immutable configuration in both recalculated versions without changing source identity
or observation clocks. Audit JSON adds root-before/root-after and small typed mapping changes.
[Complete61-field public DTO map and storage relationships](../reference/organization-mapping.md#public-contracts-and-fields).

### Explicit root replacement in existing configuration JSON — 2 November 2026

MappingRequest adds change_root (false by default); MappingApply inherits it. The canonical preview
binding includes that intent alongside exact candidate and context. Only explicit configuration-only
Apply may replace Configuration.policy.root_email; every other trusted policy field must remain
identical. org_workspace stores the new configuration, and immutable proposed/applied org_version
snapshots pin the corresponding root. Existing mapping_root_before/mapping_root_after audit fields
retain the change; no new table, column or audit-field addition is needed for this extension.

MappingPreview adds nullable root_before, root_present (row supplied by the latest applied feed) and
unresolved_count (all projected employee profiles with incomplete ancestry). MappingImpact adds
before_ancestry/after_ancestry. These read models, not stored columns, bring the ten mapping DTOs to
61 effective fields. MappingSettings.root_editable continues to describe ordinary editor locking;
the deliberate replacement command is available after import. Changing the root does not rewrite
feed data, source clocks, membership/owner records, managed status or accepted operation intents.
A missing successor row is allowed with explicit warnings; a later feed supplies actual reporting
relationships. Root-replacement validation and independent reviews passed. See the [complete field map](../reference/organization-mapping.md#public-contracts-and-fields).

### Recorded audit changes in the existing history projection — 2 November 2026

AuditEntry adds nullable summary (at most512characters) and changes (default empty, at most512strings,
each at most18000characters). With the existing ten fields this is a twelve-field DTO, mirrored by
the twelve-column audit CSV; changes is a JSON array in the CSV. These are derived values, not new
stored columns. The [complete field/source map](../reference/audit-history.md#public-fields-and-source-map)
also distinguishes current administrator labels from historical organization subject/change evidence.

The existing immutable OrganizationEvidence mapping_root_before/mapping_root_after/mapping_changes
payload supplies selected old/new root, segment-name, leader and designee values. The reader validates
evidence hashes/typed shapes and derives allowlisted summaries; it never looks up today's mappings
to fill missing history. Older events without change evidence stay explicitly unrecorded; no-change
mapping Apply is labeled unchanged. Offboarding receipt metadata distinguishes a requested queued
workflow from a completed local decision, while missing receipt evidence remains neutral. Feed
receipt does not invent a row count; published profile counts include retained/reference identities.

AuditHistory's Details column shows the description and native View changes disclosure; outcome codes
remain the fallback for other events. Search remains limited to actor/current-administrator names
and correlation IDs, excluding the new text. CSV keeps existing date/scope/limit/formula/preparation
semantics. Full configuration, feeds and credentials are not serialized. No table, column, migration,
audit mutation or additional permission is needed. Final validation for this projection extension passed;
the scoped receipt (private historical evidence; not distributed) records its evidence
separately from historical checkpoints.

### Corrected mapping review state and derived provisioning guard — 2 November 2026

The existing org_recommendation row resolves a repaired LOB_MAPPING_REVIEW with status=resolved,
resolved_at and resolution=mapping_corrected; its person_id is matched to the current stable person,
not a mutable display name. The condition must no longer be active and valid current accountability
must be established. The old row remains in history; later unsuppressed recurrence inserts a fresh
episode. No new review table, column or audit-event kind is added. Other absence/setup/nomination
conditions are not implicitly settled by this repair.

PersonWorkflow adds mapping_required (false compatibility default, explicitly derived for current
previews), bringing that DTO to fifteen fields. It is the inverse of the shared accountability
predicate: exact configured root email with ancestry=root, or ancestry=resolved with active lob_id
and accountable_leader_email equal to that segment's configured leader. These use existing pinned
configuration and member evidence; no boolean column is stored. Mapping editor DTOs remain ten
models/61 effective fields.

The derived actions omit create_tenancy/import_tenancy/join_shared while invalid; current command
admission independently rejects them. Cleanup and other available decisions retain their own guards.
Ignore/hidden profiles do not create valid mapping evidence. The [field map](../reference/organization-workflows.md#personworkflow)
and [repair lifecycle](../reference/organization-workflows.md#mapping-review-repair-and-targeted-provisioning-guard)
are the source/UI authority. Final aggregate/browser validation passed; see the scoped mapping-review validation receipt.


### P3.1 baseline recipe: historical draft-only addition

This subsection records the validated0011 checkpoint. The current0012 publication extension is
described in [P3.2a below](#p32a-simulated-publication-and-history); its updated field map/ER supersede
the18-column/draft-only scope without changing those earlier receipts.

The new table stores eighteen explicit columns: id, workspace_id, version_number, based_on_id,
schema_version, policy_statements, quota_statements, monthly_budget_amount, budget_currency,
budget_period, tag_namespace, tag_defaults, content_hash, edit_revision, created_by, created_at,
published_by and published_at. The [new implemented ER](../architecture/diagrams/baseline-authoring-implemented.mmd)
and [runtime field guide](../reference/baseline-authoring.md#complete-model-and-source-map)
map every type, nullability, constraint and DTO source; they supplement rather than replace the
fourteen-table organization/workflow ER. No prototype table or proposed30-table inventory is renamed.

workspace_id references the existing org_workspace. Optional based_on_id is scoped to the same
workspace and can reference only a published parent; the current new-draft command sets it null.
A partial unique index admits one unpublished draft. Guarded edits preserve original ID/version/
creation provenance and increment edit_revision. Exact NUMERIC(20,4) and canonical Decimal JSON keep
money/hash handling independent of binary floats. A three-letter draft currency is structural input,
not an OCI-qualified billing configuration. Fixed MONTHLY/OTM and static tags remain explicit fields.

Existing draft content is revalidated against explicit columns and its canonical hash before a read,
edit or no-op response; inconsistent evidence is refused. Same-content save is a no-op; changed draft
and immutable baseline_draft_saved before/after evidence commit together under existing authority/
workspace locks. AuditEntry.baseline_id derives from typed
event JSON, not a new audit column/FK. Published provenance is reserved and API-role edits cannot
publish. No current-baseline pointer, rollout/effective overlay, object binding, drift observation or
provider call is implemented by this checkpoint.

The guarded local test reset explicitly includes this FK table, making nine reset tables, and deletes
test drafts without CASCADE while retaining auth/Operations/audit. It remains an opt-in owner command
for the selected local installation. Required unit, real-database and browser checks and independent
reviews have passed for P3.1; both saved local installations are upgraded with user data preserved.


P3.1 local qualification, 2 November 2026: migration0011 and draft authoring are now validated and
installed in both saved local instances with all14previous application tables preserved. The
checkpoint receipt (private historical evidence; not distributed) records the final
1,083-case combined backend/PostgreSQL/browser run, separate95%unit gates and independent reviews. The one new table makes
15actual application tables; no publication, baseline assignment or OCI application is implemented.

### Policy/quota blocks retain ordered array storage

The user-selected statement editor uses one policy block and one quota block rather than one widget
per array item. On explicit Save, LF/CRLF/CR split the text; blank lines are ignored while nonblank
line order and whitespace remain exact. policy_statements/quota_statements remain the existing JSONB
arrays and API tuple/list fields, now with1–50 complete strings of at most2000characters each. No TEXT
replacement, statement-row table, migration or additional contract field is introduced.

The backend still permits legacy/direct API entries containing embedded newlines. Opening the UI
joins stored items with newlines without writing. Only explicit Save applies the new line boundaries,
which can split a legacy item and therefore legitimately change the hash/edit revision and audited
before/after content. Cancel/read does not normalize data. Existing limits/concurrency/no-op rules
remain; original P3.1 receipt counts describe the previous UI. The refinement passed201frontend
units at97.48%and2actual HTTPS/PostgreSQL browser cases, with independent reviews complete.
The [current editor contract](../reference/baseline-authoring.md#statement-block-editor-decision)
and [implemented ER](../architecture/diagrams/baseline-authoring-implemented.mmd) distinguish display from storage.

### Whole-unit authoring without changing money storage

New baseline authoring accepts positive whole currency units only. SaveBaselineDraft.content enforces
the additional semantic rule; the UI validates digits-only whole-unit entry and displays250.0000 as250
by removing only a zero-only fractional suffix. API whole-value representations remain canonicalized
to four places. A nonzero fractional suffix is never rounded or silently discarded.

BaselineContent, NUMERIC(20,4), canonical content hashes and typed audit before/after content remain
unchanged to preserve existing exact values. Legacy fractional drafts remain readable; a later Save
requires the administrator to choose a whole value explicitly, even when the original content would
otherwise match a no-op digest. Read/open/cancel/upgrade does not rewrite those rows. This is a
baseline Save constraint, not a retyping of cost observations or historical financial data.

No table, field, migration or archival-format change is introduced. Existing26authoring/model fields
and18physical columns remain. Previous foundation/statement-block receipt counts retain their source
scope. Whole-unit validation passed904backend units,203frontend units and1,090combined
backend/PostgreSQL/browser tests, with independent reviews complete. See the [authoring boundary](../reference/baseline-authoring.md#whole-unit-budget-authoring).

### Fifty policy and fifty quota statements without a storage change

Each BaselineContent policy_statements/quota_statements list now permits1–50entries;51rejects and
the2000-character per-item limit is unchanged. These remain ordered JSONB arrays in the existing
columns. UI raw blocks increase to105000characters each; the streamed Save body bound increases to
2MiB to accommodate large UTF8lists and the existing100static tags. Value bounds/generated maxItems
change, not the26model fields,18columns, hash encoding or migration history.

Whole-unit authoring and precise archived money remain separate as before. Stored content/audit
hashes are not rewritten and no publication/application capability is added. Previous receipts keep
their counts and earlier20-item scope. New bounds passed906backend units,205frontend units and1,092combined backend/PostgreSQL/
browser tests, with independent reviews complete. [Current limits](../reference/baseline-authoring.md#fifty-statements-per-policyquota-list).


Actionable Operations navigation count, 2 November 2026: raw needs_attention alone is not actionable
work. attention_count remains a read-only projection over waiting/needs_attention organization
workflows with a matching current intent and stable person's pending-operation pointer, and a
supported guided handoff/review/retry or the current simulator's safe no-effect cancellation.
Read-only inspection diagnostics and unsupported/orphaned work remain in history at count0. Do not
delete, dismiss, force-success or rewrite records merely to clear a badge. The counter is a workspace
action hint, not command authorization or a guarantee a retry succeeds. Existing live authority/
context guards still apply. No new table, state, acknowledgment, migration or generic retry control
is introduced. See the [Operations guide](../reference/operations.md) for capabilities.


### P3.2a simulated publication and history

This records the validated publication-only0012 checkpoint. The current0013 selection/pinning
extension is [P3.2b below](#p32b-current-for-new-and-onboarding-pins); earlier55-field/no-pointer
statements describe that original source scope.

The current baseline source extends the existing fifteenth table to20columns through forward0012:
nullable published_by_name snapshots the publisher display name and publication_mode admits only
simulated publication. Together with published_by/published_at they distinguish an editable draft
from a frozen locally qualified version. Migration0012 refuses pre-existing manual publications for
explicit review rather than fabricating metadata. No table or existing recipe/hash/Decimal format
is replaced. The [current ER](../architecture/diagrams/baseline-authoring-implemented.mmd) and
[complete field/source map](../reference/baseline-authoring.md#complete-model-and-source-map)
cover all20columns and10DTOs with55effective fields, including inherited projections.

SaveBaselineDraft adds nullable based_on_id; existing draft audit evidence adds the same optional
parent while retaining old-event parsing. First draft has no parent. Subsequent new drafts must
reference the exact latest publication under the workspace lock; existing draft parentage is fixed.
The UI starts from latest content while the server validates the deliberately edited submitted recipe.
Version allocation, one-editable-draft constraint, precise archival money, whole-unit new authoring,
50-statement arrays, body limit and immutable before/after save evidence remain in force.

PublishBaseline requires exact saved UUID/revision and current authority. The explicit injected
qualifier is absent by default; local composition supplies structural whole-unit USD checks only.
It cannot establish OCI policy/quota grammar, real billing currency or deployed state. Publication
advances edit_revision and commits the full typed BaselineVersion snapshot/qualification version in
baseline_published audit together with captured publisher identity/name/time and simulated mode.
Published rows cannot be updated/deleted by ordinary runtime commands. Exact original-revision
replay is a no-op only after current authorization and dependency availability; failed validation or
audit rolls back publication. Local runtime API receives narrow publication-column UPDATE, not DELETE/
TRUNCATE; the explicit owner-only nine-table test reset may remove test publications and retain audit.

The directory reads sole draft, latest publication, optional exact UUID selection and SQL-paged
published history in one read snapshot. Page sizes10/25/50 count publications separately from draft;
latest is independent of page. Published detail is read-only with historical publisher metadata.
The label Latest published does not imply current-for-new, tenancy assignment or adoption. No pointer,
create/import pinning, effective overlay, provider binding, rollout or OCI call is added. Existing
workflow ER and30-table proposed inventory retain their distinct scope.

P3.2a passes920backend units96.3838%,216frontend units97.67% and1,114combined PostgreSQL/
backend/browser cases, with independent reviews complete. Both saved instances are upgraded with
all15application tables' pre-migration column fingerprints unchanged. See the
publication receipt (private historical evidence; not distributed).
Earlier P3.1 receipts qualify their original draft-only sources.


### P3.2b current-for-new and onboarding pins

This subsection records the validated0013 implementation. The user subsequently rejected choosing
older defaults. [The0014 correction below](#latest-publication-only-default-correction) supersedes
the pointer/SelectBaseline parts; earlier receipts and immutable audit retain their original scope.

Forward0013_baseline_pinning adds two nullable columns to existing tables, retaining15application
tables and20columns in otm_baseline_version. org_workspace.current_baseline_id uses a scoped
(id,current_baseline_id) FK to baseline(workspace_id,id); a trigger requires a published simulated
version. otm_tenancy.baseline_version_id uses (workspace_id,baseline_version_id) to the same scoped
key and records desired selection, not application. Migration leaves both columns null on every
old row: no old workspace default, tenancy assignment or accepted-operation pin is inferred. The
[current baseline ER](../architecture/diagrams/baseline-authoring-implemented.mmd) abbreviates the two existing
tables and the [field map](../reference/baseline-authoring.md#the-fifteenth-application-table-otm_baseline_version)
documents both new columns separately from the unchanged20-column recipe.

Publishing now sets the current pointer and increments registry_revision atomically with the row
and baseline_published audit, whose optional default_for_new defaults false for old events and is
true for new publication. An exact original publish replay returns before moving the pointer, so
old publication retries cannot roll back a newer selection. Existing publications can be selected
explicitly through SelectBaseline(baseline_id,expected_current_id); selecting an already-current
version is a no-op, otherwise the prior pointer is fenced. A changed selection, registry revision
and baseline_default_changed event commit together. Its typed BaselineSelectionEvidence records
previous_baseline_id and a complete BaselineVersion. No configuration_id or organizational head
changes meaning. Selecting an older publication changes future starts only, not an existing tenancy.

The configuration dictionary now covers12DTOs/61effective fields: BaselineDirectory adds nullable
current, BaselinePublicationEvidence adds default_for_new, and the selection command/evidence add
two fields each. latest remains a separate highest-published history projection; new draft lineage
continues to derive from latest, not an older explicitly selected current default. Both current and
latest are independent of history pagination; viewing exact detail never selects it.

New create/import acceptance requires a current published simulated recipe under the same workspace
lock as registry reservation. The full BaselineVersion is frozen in optional OrganizationIntent.baseline;
otm_tenancy.baseline_version_id records its UUID. Public OrganizationAction fields/digest shape stay
unchanged, preserving historical request-key replay. A matching accepted replay occurs after live
authorization but before new preview/default checks. Current publication/selection advances registry
revision so stale previews refresh instead of silently accepting a changed default. No-default
new acceptance fails before operation/reservation/audit/job writes; other workflows retain their guards.

Worker attempts compare the exact scoped published snapshot/hash/mode with the immutable pin and
never consult latest/current to replace it. Manual activation waits, later publication, retries and
restarts keep the original recipe. Existing target, parent, runtime policy and administrator checks
remain live. Old intent JSON and hashes are not rewritten; missing pin defaults null. Legacy tenancy
rows stay unassigned and older operations keep their previous behavior.

Read-only PersonWorkflow.current_baseline displays admission context. OnboardingView.baseline adds
one field, making22fields and52across its six onboarding DTOs; BaselineVersion is separately mapped.
TenancyView.baseline_version_id exposes the registry pin. This historical 0013 checkpoint did not
apply or verify baseline policies/quotas/budget/tags; required-access setup checks remain separate.
The later qualified 0015/0016 slices implement local simulated updates, immutable authored override
revisions and desired/last-verified configuration heads, as documented below. Real OCI bindings,
full required-policy rendering and production verification remain future qualifications.
P3.2b passes934backend units at96.4141%,222frontend units at97.38% and1,135combined
backend/PostgreSQL/HTTPS-browser cases. Independent reviews pass; both saved instances are0013
with all15tables' old-column fingerprints unchanged and no selection/pin backfill.
Pinning receipt (private historical evidence; not distributed).


### Latest-publication-only default correction

The only default for new create/import is the highest published version_number in the authenticated
workspace. It is derived from immutable baseline rows, not an independently editable choice. Forward
0014 preserves deprecated org_workspace.current_baseline_id and its scoped FK/default guard as
unused historical metadata; runtime publication does not write it and admission does not select from
it. The application remains15tables with20baseline columns. No SelectBaseline command/endpoint, Use for new UI or older
version selector remains. Existing publications automatically qualify for the latest lookup without
another publish/adoption command; no old recipe or publication evidence is rewritten.

Publishing still commits registry_revision+1 with publication/audit to fence stale create/import
previews, without updating stored historical default metadata. The correction migration changes no
schema or recorded selection values; it only increments registry_revision once, invalidating previews from
the old selectable-default model. The remaining otm_tenancy.baseline_version_id scoped FK and every
accepted OrganizationIntent.baseline snapshot stay unchanged. New admissions freeze latest once;
manual waits/retries keep the original pin even after a newer publication. Worker checks exact
published snapshot and matching registry pin, never substitutes latest on resume. Existing legacy
null pins remain null; no tenancy backfill, reassignment or baseline application is implied.

Historical baseline_default_changed evidence and its typed reader remain for immutable audit only;
it cannot choose a future default. Current model fields and source mappings are maintained in the
[baseline guide](../reference/baseline-authoring.md#complete-model-and-source-map) and the
[updated ER](../architecture/diagrams/baseline-authoring-implemented.mmd), which labels the retained workspace/
reference edge deprecated while retaining workspace ownership, published parentage and tenancy pins.
The current configuration contracts total11DTOs/58effective fields: SelectBaseline and redundant
BaselineDirectory.current are removed; BaselineSelectionEvidence remains for historical audit. Current correction
validation and both saved-instance upgrades pass:929backend/219frontend units and1,130combined
backend/PostgreSQL/browser cases. Metadata/pins remain unchanged; only registry_revision advances
once. Correction receipt (private historical evidence; not distributed).


### Baseline-only configuration updates

The implemented baseline-only slice adds no table. Forward0015_configuration_updates extends otm_tenancy
with nullable verified_baseline_version_id (same-workspace baseline FK), configuration_verified_at
(UTC timestamp paired with that ID by CHECK), and configuration_observation (JSONB object-or-null).
All old rows start with null verification/fake state; desired baseline_version_id remains separate.
The [complete new field guide](../reference/configuration-updates.md) maps11closed DTOs/57fields,
all three new columns, reused workflow storage, UI projections and narrow simulation limits. The
[abridged ER](../architecture/diagrams/configuration-updates-implemented.mmd) shows existing tables/relationships;
it does not replace the full organization/workflow/baseline dictionaries or30-table proposed model.

A read-only single/fleet preview binds latest published BaselineVersion, workspace/scope/registry
revision, every eligible target's original pin/revision/parent and all blockers into a hash. Active
unverified or outdated rows remain candidates; busy/invalid/provider-unavailable candidates remain
explicit blockers rather than disappearing from the set. Pending onboarding is counted separately
and retains its accepted pin. All blockers must clear before acceptance; the browser cannot submit
a different baseline, arbitrary target list or ready subset. No persisted plan/override-review table
is introduced in this transitional baseline-only checkpoint.

Atomic acceptance reuses otm_operation(kind=configuration_update), immutable operation_intent audit
and transactional native enqueue. It freezes the complete baseline and1–500target snapshots, moves
each target's desired pin/reservation under revision guards and increments registry revision. Any
failure rolls back all acceptance writes/jobs. Existing request UUID/digest semantics recover a
matching accepted operation before a newly changed preview is evaluated. No fleet-wide provider
transaction is implied by this acceptance boundary.

One native delivery processes children in separate local transactions. Fresh administrator/policy/
target checks and exact accepted baseline apply per child; later latest publication cannot retarget
it. Four fake managed categories—policy, quota, budget and tags—retain typed synthetic IDs/payloads/
canonical hashes inside configuration_observation. Partial state survives expected local failure;
last complete verified baseline/time advance only after all four simulated readbacks match. The
previous verified pointer/time is historical evidence if a later partial update changed objects,
not fresh healthy status. This timestamp is distinct from onboarding tenancy.verified_at.

One current target step uses configuration:<tenancy-UUID>, intent_revision1 and typed
ConfigurationOutcome; immutable configuration_outcome events retain each attempt with fixed worker
identity. configuration_retry records the responsible administrator's accepted retry of the unchanged
operation/baseline/targets. Verified children are skipped; matching stored categories in incomplete children are freshly read
and skip writes only on exact desired-object equality. Other categories still require successful
readback. Incomplete targets retain reservations and support only currently authorized recovery. Operations remains history; tenancy/configuration
progress owns contextual retry. No generic dismiss/delete/force-success mechanism is introduced.

Read projections distinguish TenancyView.baseline_version_number from
verified_baseline_version_number through separate scoped joins; verified_baseline_version_id and
configuration_verified_at expose the new stored evidence. TenancyDetail.configuration_operation_id
links the current/latest configuration operation. Exact version links carry allowlisted return
context or stay inside the confirmation. Full source/projection mapping is in the guide; no new
baseline override, effective configuration revision, real provider binding/drift episode or secret
custody is hidden in JSON. This checkpoint is now validated and installed on both saved instances
at0015; the earlier0014 receipt remains historical. New evidence covers960backend units96.4005%,
229frontend units97.26%,1,171combined backend/PostgreSQL/HTTPS-browser cases and a separate
time-advanced PostgreSQL preservation test. Independent reviews pass; backups and full old-column
fingerprints prove existing data unchanged. See the receipt (private historical evidence; not distributed).


Validated source refinement: managed fake-object payloads allow700000characters
and encode Unicode without unnecessary ASCII expansion, preserving maximum valid baseline inputs
and JSON escaping. New DTO count stays11/57; no new column/type is added. The runtime Operations badge
adds only retryable needs_attention configuration batches owned by the current responsible admin,
not every failure or every failed child. Operations links Open baseline update to the frozen progress
context. Start/Retry advertise HTTP202queued and200existing-state receipts. The linked receipt establishes local PostgreSQL/browser and installed-runtime qualification;
it does not qualify live OCI application or substitute for the remaining real-provider milestones.


### Inventory and audit context projections after baseline updates

This validated refinement adds no SQL column/table/migration and changes no accepted intent. The
current baseline-only operation model remains11DTOs/57fields. TenancyDirectory adds nullable derived
latest_baseline_id and latest_baseline_version_number from the same workspace's highest published
version, independently of inventory filters/page. TenancyView adds nullable operation_completed_at
from existing current-or-last otm_operation.completed_at. Public inventory models now have12and27fields,
respectively. The compact Status cell exposes selected version, Latest or newer-version link; Latest
is a desired-version comparison, never full verification/drift health. A completed operation link
formats the full stored UTC timestamp as a date without changing the source event/time.

AuditEntry adds resources=(), a derived tuple of at most501AuditResource(kind,id,name) records; the
entry now has14fields and the reusable resource model3. The paged resource_context query batches
original intent_revision1 evidence by operation ID, verifies original canonical hash/workspace and
uses same-workspace registry ID/name/OCID mappings. Configuration outcomes identify their child,
batch events identify their frozen accepted targets, and person-scoped lifecycle work can add the
original employee display name. Whole-tenancy deletion does not invent an employee label. Current
registry tenancy names are contextual labels, not rewritten historical names or evidence of an
old name. Foreign/missing resources never cause a name-based/cross-workspace fallback. No resource
list is persisted; unchanged CSV remains12safe columns and does not include these display resources.
The [complete projection dictionary](../reference/configuration-updates.md#new-derived-read-fields)
records every new field and its exact storage/read source.

Completed individual panels hide when current selected/verified fields already show the result;
completed fleet receipts have a presentation-only Acknowledge that returns to Configuration. It
calls no command and writes no state/audit/acknowledgment field, clears no unresolved work badge and
leaves operation history reopenable. Successful terminal progress drops redundant refresh/polling;
needs-attention work retains supported recovery. The default no-work state is a green status pill.
These presentation changes do not add financial observations or drift semantics.

Concurrent same/different-key admission and duplicate-worker PostgreSQL regression cases are added
alongside projection/privacy/UI checks. Qualification passes:964backend units96.4268%,232frontend
units97.21%,1,178combined backend/PostgreSQL/HTTPS-browser cases, independent reviews and scoped
scans. Both saved runtimes remain0015 with private backups and full existing-data fingerprints
unchanged. Prior receipts retain their historical source scope.
Current receipt (private historical evidence; not distributed).


### Authored override and staged-plan local qualification through 0016

The qualified local schema now defines 18 application tables, retaining the full 30-table target as a separate
proposal. New otm_tenancy_configuration has 14 explicit columns, otm_configuration_plan11, and
otm_configuration_plan_target10. Existing otm_tenancy adds nullable desired_configuration_id and
last_verified_configuration_id, both scoped to that exact workspace/tenancy revision. No legacy row,
intent or verified history is synthesized/backfilled. The [complete runtime dictionary](../reference/tenancy-overrides.md#complete-physical-model)
and [implemented ER](../architecture/diagrams/tenancy-overrides-implemented.mmd) list every type, constraint,
relationship and effective UI field, rather than silently treating all proposed C3 fields as implemented.

Each immutable accepted revision contains assigned published baseline plus nullable policy/quota
full-list overrides and an independent positive whole-unit monthly amount. Null inherits; no tags,
currency, period, parent or required-access override exists. New resolution_contract_version is
simulated-config-1; effective_hash binds exact baseline/content, explicit overrides and authored
resolved envelope. It does not claim the future required-policy manifest or OCI rendering. The
source model/SQL applies published-parent/predecessor guards and immutable UPDATE/DELETE/TRUNCATE;
its operation FK is scoped and deferred so revisions/intent/heads/jobs accept atomically.

Plans are owner-scoped explicit staging with unique request identity, fixed candidate_set_hash and
closed ConfigurationTarget proposal/hash rows. A staged per-category Use new baseline/Keep override
choice carries reviewer/time and immutable configuration_review_staged evidence, while changing no
live head or job. All conflicts/blockers must clear; accepted_plan recomputes source membership and
context under lock, then seals each accepted configuration correlation and operation with desired
heads/audit/native job. New plans must be drafts and accepted plan/target content is guarded against
later mutation. Real disposable-database permission, rollback and immutability tests pass; this does not qualify OCI.

Overrides bind their assigned publication and required OverrideContext (baseline UUID, tenancy
revision, nullable desired configuration UUID); publication cannot silently rebase the editor. UI
uses one policy and one quota textarea with up to 50 complete nonblank physical lines, no per-item
widgets, plus independent whole budget. Existing exactly matching block text preserves original
array boundaries; changed blocks split hard line endings without semantic parsing/merge. Cleared
categories inherit and do not delete objects. Configured tags/required access remain separate.

Current public maps comprise 10 override DTOs / 55 effective fields and 12 rollout DTOs / 76 fields, with
59 generated schema artifacts across the qualified local application. At that 0016 checkpoint, TenancyView had 31 fields including scoped
desired/last-verified heads, derived override_categories and has_pending_operation. Busy eligibility
uses current stored reservation only, not the history fallback operation link. Same-baseline new
revisions remain verification-pending until all local effective category readbacks succeed; previous
verified revision/time survive failure. Existing original 3-field start digests and raw stored intent
hashes remain compatible, with optional accepted revision/defaults absent on legacy operations.

Full source-unit/database/native-worker/browser, independent reviews and both saved-instance upgrade
qualification pass. The local test-reset set grows to 12 tables under existing owner-only guards;
this is not authorization to reset saved data. Prior 0015 receipts retain their original scope. The
[manual review steps](../reference/tenancy-overrides.md#manual-review-after-qualification) are
for an isolated qualified runtime, not claims of already-executed live OCI/production behavior.


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


## Qualified local membership/onboarding refinement — 3 November 2026

Local simulation qualified and installed in both saved instances. Forward migration 0017_membership_onboarding expands
existing operation-step allowed keys/evidence only: the current inventory remains 18 application
tables with no new column or assignment backfill. The
[workflow ER](../architecture/diagrams/organization-workflows-implemented.mmd) annotates reused JSON/steps;
[configuration ER](../architecture/diagrams/tenancy-overrides-implemented.mmd) retains the 0016 tables/heads.

| Changed contract/evidence | Existing persistence and meaning |
| --- | --- |
| OrganizationAction.existing_compartment_ocid | Optional selected existing child compartment, omitted when null to preserve legacy request serialization; exclusive with parent_compartment_ocid + compartment_name. |
| OrganizationIntent.existing_compartment_ocid | Same server-validated exact target frozen in immutable intent; membership's existing compartment fields retain its readback binding. |
| MemberRemoval (5 fields) | association_id, tenancy_ocid, user_ocid, group_memberships_removed=true, user_deleted=true; exact typed identity receipt, no resource claim. |
| OrganizationActionOutcome.removals | Tuple of receipts, empty by default for historical results; same immutable operation_outcome data, not a new audit store. |
| Two member-removal steps | remove_member_groups:{association_uuid} and delete_member_user:{association_uuid}, existing operation_step.inputs contains the receipt; verified timestamp/evidence_event_id link immutable outcome. Receipt validation precedes retirement; all writes commit together. |
| OrganizationIntent.onboarding_version | Newly accepted 3 captures permanent user IDs before cleanup; original 1/2 and absent-version intents retain their original step graph and hashes. |
| OnboardingEvidence.step / safe_code | Adds configure_baseline and verify_configured_access keys plus BASELINE_UNVERIFIED; public field shape is unchanged. |
| Verified baseline state | Existing configuration_observation retains partial four-category state; verified_baseline_version_id/time advance only after all category readbacks. Access readiness is independently checked afterward. |
| Existing UI read fields | Dedicated Overrides uses override_categories/desired and verified configuration IDs; creation tooltip reads created_at, the registered row's immutable timestamp, not OCI creation discovery. |

See [onboarding](../reference/tenancy-onboarding.md),
[registry contracts](../reference/organization-workflows.md) and
[the manual runbook](../how-to/tenancy-refinements-runbook.md). No live OCI, resource cleanup,
secret custody, full proposed model or deployment qualification is implied.


Local qualification and saved-instance receipt (private historical evidence; not distributed).


## Qualified local on-demand configuration checks — 3 November 2026

Local qualification and both saved-instance upgrades pass. The new immutable otm_configuration_check table adds 13 columns and takes the
qualified local schema from 18 to 19 application tables. It reuses accepted operation/native queue,
step and audit infrastructure; there is no second worker engine or audit store.

[Complete 13-column map and all DTO fields](../reference/configuration-drift.md) ·
[Implemented check ER](../architecture/diagrams/configuration-drift-implemented.mmd).

Scoped child and operation/evidence references, one record per operation/child, closed context/hash,
exactly four category results and an immutable database acquisition ordinal retain current-context
proof without a mutable issue table. Existing configuration_observation can read legacy raw fake
objects or explicit ManagedObservation envelopes; read checks never mutate that state or desired/
verified heads. Four complete authorized categories are needed to confirm/resolve drift. A later
failed/partial scan preserves earlier same-context confirmation and its age. Superseded/stale checks
cannot establish current matching state.

Current source maps nine drift DTOs / 82 fields plus the five-field ManagedObservation envelope.
Directory omits expected/observed payloads; detail reads bounded typed evidence. This is four local
bundles, not the full proposed required-policy, domain-access, namespace/key/default or budget-alert
model. Daily scheduling, repair/email and real OCI qualification remain future work.

The qualified local owned-test reset set adds otm_configuration_check (13 tables total), preserving
existing operator-only opt-in/ownership/transaction guards and retained audit. This does not weaken
ordinary immutable DML or authorize a saved-data reset. Native task otm.configuration_check carries
only its operation UUID; each child record uses existing immutable outcome/step evidence.


### Current inventory/detail check projection

The qualified on-demand drift implementation adds five derived TenancyView fields, bringing that DTO to 36 fields:
configuration_issue_count, configuration_confirmed_issue_count, configuration_check_state,
configuration_checked_at and configuration_check_stale. They map directly to the shared
ConfigurationCheckSummary issue_count, confirmed_issue_count, state, checked_at and stale,
respectively. No physical tenancy column is added. Current issue_count equals the confirmed
Missing/Different category count; unavailable/conflicting/stale checks remain separate status, not
additional issues. Zero/default not_checked is not healthy proof.
[Exact field/default/source map](../reference/configuration-drift.md#computed-tenancy-inventorydetail-fields).

Execution pause with unchanged trusted parent/policy preserves confirmed same-context differences
with unavailable capability and no new green status; check commands are disabled. A changed parent/
policy invalidates the old evidence context entirely for current projection. Historical immutable
rows remain. Qualification and both saved-instance installations of this drift slice pass.


Final local qualification and installation receipt (private historical evidence; not distributed).


## Qualified local guided operation responsibility — 4 November 2026

Local qualification and both saved-instance upgrades pass. Forward migration 0019_operation_responsibility extends only the closed
audit-event kind constraint. There remain 19 application tables and 20 baseline columns; no table,
column, provider intent revision or stored-data backfill is added.

Existing otm_operation.responsible_actor_subject, revision and updated_at change in one transaction
with immutable audit_event kind operation_responsibility_changed. The 12-field ResponsibilityEvidence
captures previous subject/name, new actor/grant/revision, original intent event/typed-envelope hash,
reviewed/new operation revision and replay identity/hash. The
[complete field dictionary](../reference/responsibility.md#complete-field-and-storage-map)
covers both command fields and every evidence field.

OperationSummary adds four computed detail fields: responsible_administrator_name,
responsible_administrator_id, responsibility_revision and can_take_responsibility, bringing it to
18 fields. Existing detail derives the current authority from original intent or the latest valid
claim; compatibility defaults elsewhere remain null/false. These are not physical columns or a
second responsibility table. The [existing workflow ER](../architecture/diagrams/organization-workflows-implemented.mmd)
annotates this use of operation/audit.

Creator, original activation mailbox, tenancy owner, request/provider intent, pin and steps remain
unchanged. Numeric revision and original typed context bind replacement authority; a worker rechecks
the exact captured live grant, including revoke/regrant protection. Full D50 email routing/transport,
corporate identity issuance and real OCI permission/activation qualification remain future work.


Final application qualification and saved-instance receipt (private historical evidence; not distributed).


## Lifecycle email/outbound contact source candidate — 4 November 2026

Qualification/install pending. Migration 0020_email_delivery adds one 15-column
otm_notification_outbox table to the 19-table application, for 20 tables; baseline remains 20 columns.
Original immutable notice route/context/hash and bounded mutable delivery knowledge share this
one table, reusing native queue and email_delivery audit events. No employee/SSO key is rewritten.

[All 15 columns and complete contract fields](../reference/lifecycle-email.md) ·
[Source/rendered outbox ER](../architecture/diagrams/lifecycle-email-implemented.mmd) ·
[Accepted environment policy](21-environment-email-policy.md).

EmailRoute has 5 fields, EmailContacts 3, MailPolicy 2, EmailPolicyView 3 and IdentityContactRequest 4.
NotificationIntent has 19 fields (including frozen application_origin), Envelope 4, DeliveryResult 2,
NotificationSummary 11 and NotificationEvidence 6. Existing OrganizationIntent now has 26 fields,
PersonWorkflow 17, OnboardingView 23 and OperationDetail 5; the additive contacts field is excluded
when null on persisted intent to preserve legacy typed takeover hashes. These JSON/derived fields
are not extra SQL columns.

The full proposed notification/outbox design above remains broader; this concrete local table is
the current subset, not a second writable recipient authority. SMTP accepted is not inbox delivery;
unknown submissions are retained without blind resend. Local organization reset preserves outbox
with operations/audit and refuses pending/sending mail. Staging/production secret/SMTP/OCI behavior
and hosted CI are not qualified by this source checkpoint.


## Email delivery audit read category — 5 November 2026

Source refinement, validation pending. AuditCategory and directory/export query enums add
email_delivery, displayed as Email delivery. Existing email_delivery kinds leave the Operations
audit filter while All categories keeps them. Category is computed, with no field/table count
change, stored audit mutation or migration. Operation-detail notifications are unchanged.
[Projection and CSV semantics](../reference/audit-history.md#separate-email-delivery-category-5-november-2026).


## Drift freshness/read-counter refinement — 5 November 2026

Locally qualified read-projection change. ConfigurationCheckSummary.issue_count and the existing computed
TenancyView.configuration_issue_count now expose only the confirmed_issue_count value. Earlier
complete same-context Missing/Different remains counted through stale/unavailable/checking status;
unknown or overdue evidence alone does not create confirmed drift. Existing state/stale/time fields
retain the check-health distinction.

ConfigurationDriftDirectory adds one computed stale_count field (default 0), for 11 fields total.
It counts stale flags independently; unchecked_count now excludes stale records. No SQL column,
table, check/summary-state enum, migration or persisted evidence rewrite is required. Summary/TenancyView field counts
are unchanged; the nine drift DTOs now have 83 effective fields. No ER change is required for this
read-projection-only refinement.

Daily drift acquisition stays deferred until staging/Kubernetes: a future authorized scheduled
admission will use the existing read-only worker, with no local CronJob/demo controls now.
[Field semantics](../reference/configuration-drift.md#confirmed-drift-versus-freshness-5-november-2026).


The query state permits stale as a read-filter alias only: it selects the existing stale flag.
Matching and Not checked filters exclude stale rows; Confirmed drift selects a positive retained
confirmed_issue_count even when the latest attempt is unavailable/checking. Unavailable/Checking
select their projected attempt state. These independent counters can overlap and are not a
partition of inventory. The query still has eight fields, summary 14 and TenancyView 36; the new
Directory counter alone accounts for the 83-field total. No physical ER update is needed.


The freshness validation record (private historical evidence; not distributed) records the passing unit/database/browser gates, completed reviews and both saved-instance updates with all existing rows preserved. No SQL migration was required.

## Current implemented financial subset — 5 November 2026

Migration 0021 adds 15-column otm_financial_collection and 17-column otm_financial_observation, for
22 application tables. The [complete actual field dictionary](../reference/cost-visibility.md#storage-field-dictionary)
and [implemented ER](../architecture/diagrams/financial-implemented.mmd) supersede generic proposed
financial names for the local implementation. Exact context/source/child composite references, immutable
observations, stable failure scope and current stored projections are implemented; live provider and
daily scheduled collection remain unqualified.


### Root manager display metadata — 5 November 2026

`Configuration.root_name` is an optional trimmed 1–256-character display name stored in existing
`org_workspace.configuration` and pinned `org_version.configuration` JSON. `MappingCandidate.root_name`
is the editable input, and `MappingPreview.root_name_before` retains the saved value. The existing
Change organization leader action unlocks both email and name; `MappingRequest.change_root` binds
post-import changes of either field. A name-only edit does not need the email-boundary confirmation.

Reconciliation copies a configured root name into the existing effective root person's `full_name`,
so Organization derives direct-report manager names through its normal lookup. The configured name
wins over feed names but does not create an employee profile or source observation, advance absence
clocks, change email identity or touch tenancy associations. Historical null/omitted names retain
feed/reference fallback. `OrganizationEvidence.mapping_root_name_before` and
`mapping_root_name_after` record immutable display-name changes alongside the existing email fields.
No table or column is added. See the [implemented root-name guide](../reference/organization-mapping.md#root-manager-display-name).


## Selected repair intent fields — 6 November 2026

The [implemented repair field map](../reference/configuration-repair.md#contracts-and-storage) uses
existing operation/step/check/audit tables. `ConfigurationRepairRequest` carries `tenancy_id` and
unique selected `categories`; `ConfigurationUpdate.repair_categories` binds acceptance. Immutable
`ConfigurationTarget` freezes `repair_categories`, all-four `repair_bindings`,
`repair_context_hash`, `repair_observation_hash` and `repair_check_id`. The intent/progress
`change_kind` adds `repair`. These are typed JSON fields, not new table columns. Repair creates no
configuration revision, advances no baseline assignment and seals complete post-repair evidence
against the released registry generation. Existing check/ER relationships remain unchanged; larger
proposed live binding tables above remain separately qualified work.


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
