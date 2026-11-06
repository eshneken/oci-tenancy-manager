# Organization reviews and tenancy workflows

3 November 2026 · Established local foundation; shared-access/onboarding qualified and installed locally · Real OCI remains unqualified

[Checkpoint](../history/organization-parity-checkpoint.md) · [Snapshot storage](organization-storage.md) ·
[Organization screens](organization-screens.md) · [Operations](operations.md) ·
[Implemented workflow ER](../architecture/diagrams/organization-workflows-implemented.mmd)

## Actual scope and qualification

This implementation connects durable organization review/history, managed-person decisions and a
registered tenancy/member directory to the existing native PostgreSQL queue. Application decisions
are real database changes. Provider-facing create/import/join/offboarding actions run only through
`SimulatedLifecycleFacade`; every resulting tenancy has `provider_mode=simulated`. Synthetic tenancy,
user and compartment identifiers are not OCI observations. No OCI credentials, activation/MFA web
flow, IAM/policy deployment, parent migration or real termination has been qualified by this slice.

The established foundation has its historical receipts. The shared-access/onboarding refinements
described below now pass local qualification; both saved-instance upgrades and preservation checks also pass.
Prior receipts retain their original scope.
This is not a full-MVP release or production deployment approval. The mandatory backend
and frontend 95% complete-source unit gates and separate PostgreSQL/Playwright/security reviews still
apply. Existing historical results in other guides do not validate this new milestone.

## Four separate authorities

| Authority | Meaning |
|---|---|
| `org_feed` / `org_version` / `org_member` | Immutable source and reporting evidence, including last-known roles and absence episodes. |
| `org_person` controls | Managed-directory inclusion, setup episode and pending operation, independent of whether a feed row exists. |
| `otm_tenancy` / `otm_tenancy_membership` | Registered simulated resources and owner/member obligations; owner is accountability, not a synonym for IAM privilege. |
| `otm_operation` / steps / `audit_event` | Accepted intent, queue handoff and verified local simulated outcome; acceptance is not completion. |

Production uses `otm_tenancy` and `otm_tenancy_membership`. The preserved prototype's separate
`org_tenancy` and `org_tenancy_association` tables are reference implementations, not another live
production registry. Future OCI fields extend this production authority; there must not be two
independently writable ownership trees. The initial organization census is a baseline, not an
assertion that every employee needs a new tenancy. No registry relationships are invented from old
source rows or prototype simulation history.

## Managed directory and review episodes

`included` and `outside` people appear in the normal directory; `exempt`, `offboarded` and `merged`
remain inspectable with the removed-person filter. Original person UUID/email anchors and reporting
snapshots survive these decisions. The person control is not a source-graph delete operation.

A later employee-row addition or reference-to-employee promotion opens setup. No tenancy required
requires zero current obligations, sets `exempt`, and survives ordinary feeds and absence/return.
This tenancy exemption also applies to the configured organization root: it does not offboard the
reporting boundary. Root offboarding and identity merge remain prohibited; see the root-specific
validation checkpoint below. An exempt root remains in the source graph and is visible through
Include excluded profiles, independently of its absence from the normal managed-person list.
Manual Re-onboard remains an explicit option for a source-present, unassociated exempt/offboarded
person. Automatic directory return is narrower: a newly **applied fresh feed** containing an already
offboarded person's actual employee row restores that stable identity to included. Full and partial
feeds can supply positive presence; no intervening absence cycle is required. If onboarding is
needed, one new setup episode is opened. Repeated later presence does not keep replacing that episode.
Actual employee rows are resolved through canonical aliases to stable person UUIDs before return matching. org_person.email remains the immutable original anchor across merges; comparing that old anchor directly with a current renamed-email row would miss a valid return and is not the matching rule. Existing relationships, users and tenancies are never resurrected. Exempt, merged or outside people
and people reserved by pending work are not silently restored; retained outside obligations still
require the existing explicit Mark returned decision.

The capture must be strictly newer than the predecessor's source capture (or publication time when
that source time is absent) and any recorded removed_capture_at. Legacy offboarded records with a
null removed_capture_at use that predecessor boundary; they do not need an invented omission.
Reference-only profiles, staged/rejected/stale/duplicate/replayed feeds and configuration-only
reclassification cannot trigger return, refresh census clocks or create onboarding episodes.
Partial omission still cannot prove anyone else's departure.

For a genuinely returning already-offboarded identity, qualified_return_history settles its handled
absence only on an evaluation copy before building a new immutable applied snapshot. The original
source, predecessor, absence evidence and decision/audit history remain unchanged. A person whose
absence decision is still unresolved and who was not offboarded does not gain this automatic
settlement. Return does not settle leader/designee/mapping defects merely by restoring directory
visibility; those conditions retain their independent actual-repair rules.

Only explicit Offboard employee may offboard a person, and current actual employee-row presence
makes that action unavailable/refused. Root offboarding remains forbidden. Standalone tenancy
termination, Remove shared member and Transfer owner preserve every affected person's managed
status and independent absence reviews even when no associations remain and even when the person is absent. This includes the underlying absence flags/working-reclassification decisions, not only keeping a review row open. For an included source-present person losing their final association, existing setup
flags may record a pending onboarding requirement/episode for the next organization reconciliation;
this is not offboarding and still honors independent absence/mapping eligibility guards.


The actionable inbox holds setup, absence, LOB mapping/leader, designee and override reviews.
The adjacent Informational & history tab defaults to change records and still-open source warnings
for the latest applied feed. Completed actionable decisions and resolved source warnings are excluded
in that default scope. Show all history switches the same tab to all retained nonactionable records
and completed actionable decisions through the existing category=history API selection. Nothing is
deleted or reclassified. Cases retain first/last/resolved dates.
Partial omission does not prove a missing-manager warning corrected. Unresolved absence/setup decisions do not close merely because another feed arrives; the handled-absence return of an already-offboarded identity described above is the explicit exception. A corrected LOB_MAPPING_REVIEW is different: once that
condition is no longer active and its stable person has valid current accountability, reconciliation
closes it automatically with resolution=mapping_corrected and a resolved timestamp. The historical
row remains; a later unsuppressed mapping defect opens a fresh episode. No second manual Resolve is
needed for an already corrected mapping. Leader/designee eligibility reviews retain their separate
actual-repair rules; mapping repair does not close unrelated absence or tenancy-setup work.

Conditional decisions bind relevant facts/absence episodes. Permanent Ignore is restricted to LOB
mapping for that person and does not assign a fictitious segment or bypass provisioning guards. An
unmapped review can still be explicitly ignored, but its person remains blocked from new tenancy
provisioning until accountability is valid. Other conditional review types retain their fact/episode-
scoped closure.
Name-only changes do not reopen unrelated reviews. Change rows compare stable IDs and retain
before/after name, email, manager, LOB, accountable leader and designees; no-op feeds add no fake
changes. Existing snapshots can be adopted as a baseline by explicit local setup without generating
new-employee reviews for the entire organization. The first migration itself seeds no employees.

## Preview, acceptance and verified simulation

General employee/review dialogs start at **Choose an action**, with action fields hidden and Continue
disabled until the administrator selects an option. No action is inferred from list ordering, even
when only one is available. Explicit task buttons such as Transfer owner may preselect their named
action after fresh eligibility validation; an unavailable task falls back to the placeholder, never
another operation. An unchanged retry preview may retain the administrator's explicit choice.

A person preview resolves allowed actions, every pending/active/removing association, eligible
transfer recipients, current shared children and merge partners. A command freezes both org heads,
configuration ID and registry revision. Current session/grant checks and the protected administrator
anchor precede workspace/operation locks. Changed previews require refresh. The browser cannot
supply an actor, workspace, arbitrary SDK arguments or a publishable candidate.

The request UUID is scoped to workspace and verified actor. Exact committed replay returns its
receipt before stale-preview checks; changed input under that key conflicts. Application-only
receipts live in immutable decision evidence; simulated lifecycle receipts use the existing operation
request uniqueness. New destructive admissions additionally require explicit consent, while authenticated exact historical replay is checked before that new guard. The UI retains uncertain-request identity only for its current dialog attempt;
this does not promise reload-durable recovery memory. Check the recorded result before starting a
new action after uncertainty.

| Choice | Admission and completion boundary |
|---|---|
| Create / Import | Reserve a pending simulated tenancy and owner link, append intent/audit, close linked review and enqueue atomically. Import accepts an exact synthetic child OCID; it does not discover/adopt a real tenancy. |
| Add to shared tenancy | Choose a registered active shared child and either an existing non-root compartment or a new compartment name under a discovered parent. These choices are exclusive. Freeze the exact selected target; verified simulator bindings publish the local user/compartment association. |
| Offboard / direct delete, transfer, remove | Freeze exact registered associations, roles, revisions, OCIDs and personal-user/compartment bindings. Keep is explicit. Pending/failed work remains an obligation. |
| No tenancy / Ignore / Resolve / Re-onboard / Mark returned / Merge | Guarded real application decisions with immutable audit; no fictitious provider success or native job required. |

One offboarding plan must include each current association exactly once. Individual owners may
Delete/Transfer/Keep; shared owners Transfer/Keep; shared members Remove/Keep. An individual tenancy
with other associations cannot be deleted through this flow. Transfer needs a current eligible
source-present managed recipient. Manager/shared confirmations are explicit; root/parent,
unregistered/wrong-parent and unsupported targets are refused. Empty registry is not proof of no
real OCI assets: zero-association offboarding requires its explicit confirmation as well as universal destructive consent. Offboard employee is hidden/refused while an actual current employee row is present.

The queue receives only the immutable operation UUID. `otm.organization_action` uses the same scoped
native queue and foreground worker as inspection, with no automatic task retry. Dispatch validates
the exact intent/hash/actor, current administrator revision, policy/pause, person state, original
registration/parent/organization/revision and recipients again. Feed/merge/return cannot silently
retarget accepted work. The local facade and registry publication run in one database unit of work;
this atomic local simulation must not be copied into a real OCI network transaction or described as
exactly-once OCI execution. An exception rolls back that local unit and attempts a separate fixed
failure publication. A native task returning is not proof of business success.

Verified simulation activates pending bindings, retires selected links and records the simulated
outcome. Standalone deletion/member removal/ownership transfer never offboard the person or settle independent absence work. Only explicit offboarding changes directory status: completed zero-obligation work may become offboarded; retained obligations remain outside and tracked. Shared user/member cleanup preserves resources and compartments, records known
scope/owner guidance and does not gate completion on manual resource cleanup. Unknown scope remains
unknown. A simulated terminated registry row is excluded from current inventory but retained in
history. Real V1 deletion, once separately qualified, completes at verified termination initiation
(D26), never permanent deletion or a 30-day polling/finality promise.

## Cancellation and identity merge

Cancel local simulation is available only for its original person's pending simulated operation in
queued/waiting/needs-attention/failed state with no known effect. It serializes with execution,
verifies frozen intent, releases pending reservations and affected-person locks, preserves verified
links, cancels never-verified pending tenancies, and reopens relevant handed-off reviews. It does not
undo verified simulator effects, cancel an arbitrary operation or establish a real OCI compensation
contract. Operations remains visibility/troubleshooting; recovery begins in the person/tenancy context.

Merge requires an explicit same-workspace unresolved absence/new-setup pair, old email absent and
new email present, no pending work and neither root. The absent UUID/original anchor survives;
current source metadata and verified aliases rebase reporting/LOB/designee/override references.
Duplicate provisional associations are reconciled, historical records retained and both reviews
closed atomically. Retired source employee rows reject; stale manager references can canonicalize.
This application identity decision is not proof of corporate/OCI identity or IAM changes.

## Routes and current screens

| Route | Meaning |
|---|---|
| `GET /api/organization/reviews` | Bounded `ReviewQuery` to actionable inbox, latest-feed information or retained full-history `ReviewDirectory`. |
| `GET /api/organization/people/{id}/workflow` | Fresh `PersonWorkflow`; optional `review_id` binds the selected open case. |
| `POST /api/organization/actions` | Bounded 32 KiB closed JSON `OrganizationAction`, normal session/Origin/custom-header guards; `ActionReceipt`,202for durably queued work and200for immediate/replayed terminal receipts. |
| `GET /api/tenancies` | Literal search, allowed sorting, clamped paging and registry summary `TenancyDirectory`. |
| `GET /api/tenancies/{id}` | `TenancyDetail`, historical memberships and manual cleanup context; foreign/unknown IDs are indistinguishable. |

Organization rows expose current/pending association counts and managed status; the removed-person
filter supports deliberate return/re-onboarding. Organization drift has independent searchable,
sortable, paginated Actionable/Informational & history tabs and review dialogs. The second tab defaults to latest-feed information and exposes full history through its checkbox. Tenancies is a basic registered
inventory/detail entry point with visible simulation status and operation links. It is not the full
approved configuration/finance dashboard. Counts include owner relationships; operational current
obligations include pending/active/removing, while directory tenancy_count counts active/removing
and pending_tenancy_count separately. Inventory omits terminated/cancelled rows, includes pending
and issue states, and never represents an empty filtered page as zero total registered children.

## Storage field reference

Historical migration 0009 added three tables to the eleven-table foundation (14 application tables).
Subsequent baseline/configuration work brings the current inventory to 18 tables through 0016. The
0017 refinement expands allowed step/evidence values without adding a table or column. The field
reference here covers registry/review storage; the baseline and override guides cover later columns.
There is no second audit store, worker engine or per-screen database cache. Local qualification of 0017, its UI changes and both saved-instance upgrades pass.

### org_workspace

| Field | Meaning/source |
|---|---|
| `registry_revision` | Positive workspace-wide registry/decision preview fence; commands increment after changes. |

### org_person

| Field | Meaning/source |
|---|---|
| `directory_status` | included/exempt/offboarded/outside/merged; managed status independent of immutable source history. |
| `setup_required` | Durable pending onboarding requirement, not proof of zero OCI resources. |
| `setup_episode_id` | UUID identifying a particular setup requirement across repeated feeds. |
| `removed_capture_at` | Capture boundary retained by explicit offboarding; nullable for legacy controls. Fresh actual-row return compares this and the prior source/publication boundary. It is not an absence-cycle prerequisite or changed by standalone association cleanup. |
| `pending_operation_id` | Same-workspace accepted lifecycle operation reserving the person; nullable. |

### org_recommendation

| Field | Meaning/source |
|---|---|
| `id` | Stable UUID primary key; never reused as an employee email or OCI identifier. |
| `workspace_id` | Authenticated application authority scope; part of scoped uniqueness/FKs. |
| `person_id` | Same-workspace stable person; nullable for organization-wide history. |
| `kind` | Closed review/event kind for recommendation; individual/shared classification for tenancy. |
| `category` | actionable/informational/change; separate work from source warnings/history. |
| `target` | Exact person/email or branch/field-qualified review target. |
| `basis` | Relevant-facts or setup/absence-episode fingerprint, preserving conditional closure scope. |
| `status` | Review open/resolved/ignored; tenancy pending/active/terminating/terminated/failed/cancelled; membership pending/active/removing/removed/failed. |
| `first_seen_at` | UTC first observation/publication of this episode or history item. |
| `last_seen_at` | UTC last supporting observation for the episode; does not replace first-seen time. |
| `resolved_at` | Nullable UTC explicit or adequate source-correction closure time. |
| `version_id` | Same-workspace organization version supporting the review/history record. |
| `resolution` | Nullable factual decision/source-correction token, not proof of OCI completion. |
| `operation_id` | Nullable same-workspace current accepted operation/handoff; retained on completed review as correlation. |
| `data` | Stored name/email, bounded before/after metadata or factual history projection; not a raw feed/SDK dump. |

### otm_tenancy

| Field | Meaning/source |
|---|---|
| `id` | Stable UUID primary key; never reused as an employee email or OCI identifier. |
| `workspace_id` | Authenticated application authority scope; part of scoped uniqueness/FKs. |
| `name` | Requested/local registered display name; current scope is explicitly simulated. |
| `tenancy_ocid` | Synthetic or explicitly supplied simulated child identifier, unique inside workspace. |
| `parent_tenancy_ocid` | Trusted frozen control-parent scope, distinct from child. |
| `organization_id` | Trusted simulated parent-organization binding. |
| `home_region` | Requested simulator SDK-style region identifier; not an observed OCI home_region_key. |
| `kind` | Closed review/event kind for recommendation; individual/shared classification for tenancy. |
| `status` | Review open/resolved/ignored; tenancy pending/active/terminating/terminated/failed/cancelled; membership pending/active/removing/removed/failed. |
| `provider_mode` | Exactly simulated in this milestone; no real adapter qualification. |
| `origin` | create/import requested origin; both have equivalent registered-child guards. |
| `revision` | Positive optimistic/stale-target fence, advanced on local registry transitions. |
| `operation_id` | Nullable same-workspace current accepted operation/handoff; retained on completed review as correlation. |
| `last_operation_id` | Retains most recent operation after current reservation is released. |
| `created_at` | Immutable UTC row creation time. |
| `updated_at` | UTC current processing/association transition time. |
| `verified_at` | Nullable verified local simulated milestone time, not OCI permanent deletion. |

### otm_tenancy_membership

| Field | Meaning/source |
|---|---|
| `id` | Stable UUID primary key; never reused as an employee email or OCI identifier. |
| `workspace_id` | Authenticated application authority scope; part of scoped uniqueness/FKs. |
| `tenancy_id` | Same-workspace registered tenancy UUID; never an arbitrary external target. |
| `person_id` | Same-workspace stable person; nullable for organization-wide history. |
| `role` | owner/member accountability role; not an IAM permission profile. |
| `status` | Review open/resolved/ignored; tenancy pending/active/terminating/terminated/failed/cancelled; membership pending/active/removing/removed/failed. |
| `user_ocid` | Nullable exact simulated personal user binding retained for scoped removal. |
| `compartment_ocid` | Nullable bound personal simulated compartment; retained for manual cleanup context. |
| `compartment_name` | Nullable requested/readable personal compartment label. |
| `parent_compartment_ocid` | Nullable selected existing simulated parent compartment binding. |
| `cleanup_required` | Retained manual resource/compartment cleanup guidance; does not delay verified membership retirement. |
| `operation_id` | Nullable same-workspace current accepted operation/handoff; retained on completed review as correlation. |
| `revision` | Positive optimistic/stale-target fence, advanced on local registry transitions. |
| `created_at` | Immutable UTC row creation time. |
| `updated_at` | UTC current processing/association transition time. |

One open review per workspace/kind/target is enforced. All new person/version/operation/tenancy
references are scoped. Review and registry DELETE/TRUNCATE are blocked for ordinary DML. Original
registry UUID/workspace/created_at and original person identity are protected while processing
fields can transition. Partial unique indexes prevent duplicate current person/tenancy links and
multiple pending/active/removing owners; deferred triggers require exactly one active owner for an
active tenancy. Database owners can change DDL: these are not protection against a privileged DBA.

`current_organization` additionally joins live managed controls and active/removing association
counts; source member evidence remains immutable. It filters included/outside people. The proposed
source view remains a frozen reporting preview, not a prediction that future associations are done.

## Complete contract field map

The lists below enumerate current authored fields. Closed models/types/generated schemas remain
authoritative for nullability, enums and bounds. Shared identifiers are UUIDs unless named OCID;
public actors/workspace derive from the authenticated service, never command fields.

### OrganizationContext

Exact org applied/proposed heads, trusted configuration and registry fence from one preview.

`applied_version_id`, `proposed_version_id`, `configuration_id`, `registry_revision`.

### AssociationChoice

One selected existing obligation/action and explicit transfer recipient.

`association_id`, `action`, `recipient_person_id`.

### OrganizationAction

Request identity + exact context/person/review/tenancy/operation IDs; bounded new/import/shared-compartment inputs; complete association plan and explicit warnings. No actor/workspace/SDK fields.

`client_request_key`, `context`, `action`, `person_id`, `review_id`, `tenancy_id`, `operation_id`, `name`, `tenancy_kind`, `home_region`, `import_ocid`, `parent_compartment_ocid`, `compartment_name`, `existing_compartment_ocid`, `recipient_person_id`, `partner_person_id`, `plan`, `confirm_destructive`, `confirm_no_associations`, `confirm_manager`, `confirm_shared`.

OrganizationAction has 21 fields. confirm_destructive defaults false and is omitted when false to preserve historical hashes; new admissions for the five destructive actions require true. It is an acknowledgment, not a provider privilege or new stored column.

### FrozenAssociation

Server-captured registered target/role/revision, personal user/compartment and transfer bindings; immutable intent, not browser authority.

`person_id`, `person_was_manager`, `id`, `tenancy_id`, `tenancy_revision`, `role`, `action`, `tenancy_ocid`, `parent_tenancy_ocid`, `recipient_person_id`, `new_association_id`, `recipient_user_ocid`, `recipient_compartment_ocid`, `recipient_compartment_name`, `recipient_parent_compartment_ocid`, `user_ocid`, `compartment_ocid`.

### LifecycleTarget

Frozen stable person/display context and optional exact child; person-wide plans do not invent an OCID.

`tenancy_ocid`, `person_id`, `display_name`.

### OrganizationIntent

Server-owned scope/policy/admin authorization plus frozen action/person facts, pending reservation IDs and association plan; no secrets.

`contract_version`, `kind`, `workspace_id`, `policy_revision`, `organization_id`, `parent_tenancy_ocid`, `administrator_id`, `authorization_revision`, `action`, `whole_tenancy_deletion`, `target`, `person_was_absent`, `person_was_manager`, `pending_tenancy_id`, `pending_association_id`, `onboarding_version`, `baseline`, `activation_email`, `email_contacts`, `name`, `tenancy_kind`, `home_region`, `parent_compartment_ocid`, `compartment_name`, `existing_compartment_ocid`, `associations`.

### ActionReceipt

Actual application decision or accepted simulated operation identity/state/mode/time; queued does not mean verified.

`operation_id`, `state`, `provider_mode`, `accepted_at`.

### OrganizationActionOutcome

Closed simulated result/code and nullable verification time; no raw provider error.

`contract_version`, `provider_mode`, `action`, `removals`, `safe_code`, `verified_at`.

### MemberRemoval

Five nonsecret fields describe one exact simulated identity-removal receipt: `association_id`,
`tenancy_ocid`, `user_ocid`, `group_memberships_removed`, `user_deleted`. The last two are required literal true
values in a verified receipt: neither has a default, and omitting either cannot imply success. They
are independent provider-readback evidence, not administrator checkbox assertions. Outcome `removals` defaults to
an empty tuple for historical evidence. Compartments/resources are deliberately absent from this
receipt; it cannot be used as proof that they were inspected or deleted.

### ReviewQuery

Six independent category/search/sort/direction/page controls; search at most128characters and page
size10/25/50. category accepts actionable (default), informational or history. Informational is a
query selection spanning stored change records and open informational warnings, not a new persisted
category or synonym for all history. The Actionable tab uses actionable; Informational & history uses
informational by default and history when Show all history is checked. History includes all retained
nonactionable records and completed actionable decisions, independent of their source feed.

`category`, `query`, `sort`, `direction`, `page`, `page_size`.

### ReviewView

Thirteen persisted episode/display fields plus bounded factual data; operation link is a handoff,
not a success guarantee. For data.before/data.after metadata, the read projection supplements the
stored lob_id with nullable lob_name. Before uses the review version's base_version_id configuration;
after uses the review version's own configuration. Known IDs display their pinned historical label;
an unknown nonempty ID displays Unknown industry segment, and no ID has a null label. The nested
read-derived label does not replace the stored ID or rewrite historical payloads. Open leader/designee
review headings separately use current pinned-head segment labels; do not confuse that live role
context with the historical before/after metadata values.

`id`, `kind`, `category`, `status`, `person_id`, `name`, `email`, `first_seen_at`, `last_seen_at`, `resolved_at`, `resolution`, `operation_id`, `data`.

### ReviewDirectory

Eight fields: filtered page plus independent whole-selection counts, computed before search/paging.

`items`, `total`, `page`, `pages`, `page_size`, `actionable_count`, `history_count`, `informational_count`.

informational_count (compatibility default0, computed by current readers) counts the latest applied
feed's information selection. It is a subset of history_count, not a third disjoint population to
add to actionable_count/history_count. total remains the searched category's count. Existing
history_count semantics and all historical rows remain unchanged. The Informational & history badge
uses informational_count while unchecked and history_count while checked; it reflects the chosen
scope, not merely the number of rows matching the current search/page.

### PersonOption

Stable person identity with current version name/email or historical original-anchor fallback.

`id`, `name`, `email`.

### AssociationView

Existing membership/tenancy fields, pending operation, cleanup context and server-calculated allowed choices.

`id`, `person_id`, `tenancy_id`, `tenancy_name`, `tenancy_kind`, `tenancy_status`, `role`, `status`, `compartment_ocid`, `compartment_name`, `cleanup_required`, `operation_id`, `actions`.

### TenancyView

Thirty-six fields combine registry identity/scope/region/kind/status/origin/mode/times, explicit
owner/accountability labels, current/last operation, membership counts, desired/verified baseline
and configuration state, plus the shared read-only configuration-check projection.

`configuration_issue_count`, `configuration_confirmed_issue_count`, `configuration_check_state`,
`configuration_checked_at`, `configuration_check_stale`, `has_pending_operation`,
`desired_configuration_id`, `last_verified_configuration_id`, `override_categories`,
`operation_completed_at`, `baseline_version_id`, `baseline_version_number`,
`verified_baseline_version_id`, `verified_baseline_version_number`, `configuration_verified_at`,
`id`, `name`, `tenancy_ocid`, `parent_tenancy_ocid`, `home_region`, `kind`, `status`, `origin`,
`provider_mode`, `owner_person_id`, `owner_name`, `owner_email`, `manager_name`, `leader_name`,
`lob_name`, `member_count`, `operation_id`, `operation_state`, `verified_at`, `created_at`,
`cleanup_count`.

The five configuration-check fields are computed from the same current evidence used by
Configuration drift, not database columns. The
[complete source/meaning table](configuration-drift.md#computed-tenancy-inventorydetail-fields)
distinguishes affected categories, confirmed differences, latest check state/time and stale age.
Compatibility zero/not_checked defaults do not imply healthy state; application verified_at and
configuration_verified_at are separate historical milestones.

### PersonWorkflow

One exact preview: person/review/current presence/manager/managed state, pending operation, qualified mode, allowed actions and explicit candidates.

`email_contacts`, `current_baseline`, `mapping_required`, `creation_regions`, `context`, `person`, `review`, `source_present`, `is_manager`, `directory_status`, `pending_operation_id`, `provider_mode`, `actions`, `associations`, `shared_tenancies`, `transfer_recipients`, `merge_partners`.

The seventeen-field projection derives mapping_required from current person/configuration evidence;
its compatibility default is false, but the server explicitly computes it for every current preview.
The configured root is exempt only when its exact root email and ancestry=root agree. Everyone else
requires ancestry=resolved, a lob_id in the active configuration and accountable_leader_email matching
that segment's configured leader. A nonempty stale ID alone is insufficient. This boolean is a public
read model, not a stored column or browser-granted permission.

When true, only create_tenancy/import_tenancy/join_shared are removed from allowed actions. The dialog
shows mapping guidance and Repair Organization Mapping before the action selector; cleanup and other
otherwise-available decisions stay independent. The command path rechecks its current server preview
and denies unavailable actions; the internal admission path also rejects invalid accountability with
ACCOUNTABILITY_MAPPING_REQUIRED. Neither Ignore nor a forged client can authorize new provisioning.
Existing authentication, context, owner/manager warnings and cleanup guards continue to apply.

### CreationRegion

`identifier`, `name`: parent-facade subscription choices used by the create-only home-region selector.
The local adapter supplies explicit simulated fixtures. Admission rechecks membership in the server's
current list; browser-supplied option lists are never trusted. No selected/default region is invented.

### TenancyQuery

Literal directory search/sort/direction/paging, at most128characters and page size10/25/50.
The visible Shared tenancies only checkbox maps to `shared_only` (defaultfalse), applied to registered
`kind=shared` before paging and combined with search/sort. Toggling restarts page one, preserving
search/sort. Inventory cards still count all current tenancies, independent of this shortcut.

`shared_only`, `page`, `page_size`, `query`, `sort`, `direction`.

### TenancyDirectory

Filtered page plus whole-current-inventory total/individual/shared/pending/issue cards.

`items`, `total`, `page`, `pages`, `page_size`, `total_tenancies`, `individual_count`, `shared_count`, `pending_count`, `issue_count`.

### CompartmentOption

Facade-discovered existing simulated parent, not an arbitrary user-supplied SDK target.

`ocid`, `name`.

### TenancyDetail

Registry projection plus historical person/membership/cleanup evidence and current simulated parent options.

`tenancy`, `people`, `memberships`, `compartment_parents`.

### OrganizationQuery

Adds include_removed and tenancy_count sorting to existing literal directory controls.

`page`, `page_size`, `sort`, `direction`, `query`, `include_removed`.

### EmployeeView

Current member labels plus live managed status, active/removing count, separate pending count and operation correlation.

`id`, `full_name`, `email`, `manager_name`, `leader_name`, `lob_name`, `absence_review`, `tenancy_count`, `pending_tenancy_count`, `directory_status`, `pending_operation_id`.

### OrganizationFinding

Compatibility current-finding shape; the workflow-enabled directory returns findings=(), using durable reviews instead.

`category`, `code`, `employee_name`, `email`, `detail`, `at`.

### OrganizationDirectory

Directory/snapshot/config/reset context plus pending workflow, workflow mode and durable inbox/history counts.
This DTO is unchanged: its history_count remains the legacy total of retained nonactionable and
completed actionable records, not the latest-feed information count. The current drift tabs use
ReviewDirectory counts instead; do not repurpose OrganizationDirectory.history_count as the new badge.

`test_reset_enabled`, `pending_workflows`, `workflows_enabled`, `provider_mode`, `actionable_count`, `history_count`, `configured`, `upload_enabled`, `server_time`, `items`, `total`, `employee_count`, `absence_count`, `page`, `pages`, `page_size`, `applied_at`, `source_as_of`, `absence_eligible`, `latest`, `findings`.

### OrganizationOutcome

Existing feed-state receipt; revision_id means applied version, independent of proposal identity.

`snapshot_id`, `state`, `proposed_version_id`, `revision_id`, `original_state`, `diagnostics`.

### OrganizationEvidence

Existing source/config/feed/version counts plus bounded review/person/action/subject display and permanent request digest/receipt. No raw configuration/feed.

`contract_version`, `request_key`, `request_digest`, `receipt`, `review_id`, `person_id`, `action`, `subject_name`, `source_id`, `population_id`, `configuration_id`, `feed_id`, `proposed_version_id`, `applied_version_id`, `person_count`, `diagnostic_count`.

## Audit, reset and remaining qualification

Decision evidence `organization_review_decided` is attributed to the verified administrator and
stores the request key/digest/receipt; automatic source publication retains its synchronization
actor. Worker `organization_action_outcome` has the closed `{kind:worker,subject:organization}`
actor and validates its typed simulated outcome. `operation_intent` still binds the initiating
human to the exact immutable command. Safe public history adds nullable `organization_subject_name`;
CSV now has ten columns (the original nine plus that display field). Raw intent/source/claims and
credentials remain private. CSV formula neutralization, UTC filters,10,000-row cap, preparation audit
and commit-before-disclosure remain unchanged. Export preparation is not proof of file receipt.

The explicit owned-laptop reset now reviews a fixed eight-table set: five source tables plus
`org_recommendation`, `otm_tenancy`, `otm_tenancy_membership`. It refuses unsettled organization-action
operations and any non-simulated registry row, unexpected organization tables or outside dependents.
The disabled-by-default opt-in, Docker label/loopback/database/scope checks, active READ COMMITTED
transaction, fixed locks/timeouts and no-CASCADE rule remain. Only corresponding truncate guards are
temporarily disabled and restored before commit. This physically removes test registry/review/source
rows, not an archive; original login/session/operations/audit survive and may retain correlation IDs
whose test targets were removed. The UI shows instructions only; no destructive reset endpoint or
runtime API owner credential is added. A retained private profile may initialize the next upload.

Remaining real-provider work includes creation/activation/bootstrap, actual parentage/region/access
qualification, IAM assignment/removal, termination initiation reconciliation, partial/unknown external
effects and recovery. No deterministic local ID or transaction proves those capabilities. Final
validation metrics, independent reviews and the local source checkpoint are recorded in the
[completed checkpoint](../history/organization-parity-checkpoint.md). Real OCI effects remain unqualified.

## Provider facade value fields

`MemberBinding` has `association_id`, `tenancy_ocid`, `person_id`, `user_ocid`, `compartment_ocid`,
`parent_compartment_ocid`. These exact simulated read-back bindings must match the frozen expected
association/person/child; nullable compartment fields do not authorize arbitrary resource cleanup.
`LifecycleCompletion.bindings` is the tuple of those bindings. `LifecycleFacade.apply` takes the closed
OrganizationIntent, while `compartments` returns existing simulated `CompartmentOption` choices.
The real adapter is absent. The server policy is the existing typed sandbox `InspectionPolicy` and
pause configuration, not a new browser-authorizable lifecycle settings document.

## Guided create/import extension — 31 October2026

[The current onboarding guide](tenancy-onboarding.md) supersedes one-step completion for newly accepted create/import work. It adds persisted handoff, verification and cleanup review in existing operation/step/audit records. Migration0010 extends allowed values only; the14-table registry remains unchanged. Earlier accepted intents retain compatibility.

## Whole-tenancy termination — 31 October2026

[Delete tenancy](tenancy-deletion.md) is now a separate tenancy-detail action for individual and shared children, retiring every target owner/member association after verified simulated initiation. The earlier shared-owner Transfer/Keep restriction applies to person offboarding, not this explicit whole-tenancy action. Other tenancy associations and unresolved absence work remain. No new tables are added.

## Mapping review repair and targeted provisioning guard

The shared has_valid_accountability predicate drives review completion and person previews/admission.
Automatic mapping closure uses the current stable person UUID, never a display label or merely the
absence of a suppressed diagnostic. Missing/excluded people and still-unassigned or unresolved
branches are not repaired by hiding their review. Promotion to the exact configured root qualifies
under its explicit exemption; an arbitrary person carrying a root-like label does not.

Corrected cases retain immutable source history and the existing recommendation row's dates and
mapping_corrected outcome. Unrelated unmapped assistants, sticky absences and legitimate tenancy
setup episodes remain open. Recurrence after a corrected case creates a new open episode, preserving
the old resolved row. This introduces no table, migration or new audit-event kind. Other accepted
workflow targets and completed historical decisions are not reinterpreted.

Added unit and real disposable PostgreSQL regressions cover the formerly stale reviews, guarded
create/import/shared admission, Ignore without fictitious accountability, retained cleanup actions,
independent absence/setup work and recurrence. Final validation passed 1,041 backend/database/browser tests and 177 frontend unit tests, with
96.18% backend and 97.52% frontend unit coverage. Earlier receipts retain their original scope.

## Latest applied feed information and readable segment changes

The UI's stable Informational & history tab defaults to latest applied feed information and offers
Show all history within that tab. Actionable remains the durable open-work queue, oldest first by
default. The information tab defaults to newest first and, while unchecked, includes stored
category=change records (baseline, additions, metadata and applicable recorded lifecycle changes)
plus still-open category=informational source warnings. Completed/ignored actionable reviews and
resolved source warnings are excluded in this latest-feed scope even when created during that feed.
Checking Show all history instead includes all retained change/source-warning records and completed
or ignored actionable decisions, including earlier feeds and resolved warnings. Search, sorting and
pagination operate after the chosen selection; independent counts are not reduced by search.

Source provenance determines membership: gather organization versions in the verified workspace
whose org_version.feed_id equals the latest applied head's snapshot_id, then include recommendation
rows referencing those versions. Mapping/configuration reapplies of that feed remain in the same
information selection. A later applied feed changes the selection; the latest rejected or staged
upload does not replace the applied source. Event timestamps, upload-clock ties and a last-row-only
heuristic do not define membership. No row is deleted, reclassified or mutated by opening either tab.

Before/after metadata displays readable industry-segment names alongside the unchanged ID-based
comparison. Review-version/base-version configurations supply historical labels, so a later rename
or removal does not relabel earlier evidence. Missing labels stay explicitly unknown instead of
inventing a name. The UI renders selected text fields through the normal change disclosure, without
raw JSON or a complete HR-feed view. Actionable review resolution, provisioning/cleanup guards,
source-time/census semantics and Audit History are unaffected.

The mapping editor's existing organization-leader helper paragraph is aligned with its action row;
that spacing adjustment changes no fields or behavior. Unit/database/browser verification of this
information-tab and display-label refinement passed (1,043 backend/database/browser tests and
177 frontend units); see the validation receipt (private historical evidence; not distributed). Earlier checkpoint receipts remain
historical evidence for their own source scope; no new table or history store is introduced.

## Organization root without a tenancy

The configured organization root may choose No tenancy required when there are no current tenancy
associations or other blocking work. The same ordinary exemption rules apply: directory_status becomes
exempt, setup_required clears and related setup review closes. Repeated source feeds do not recreate
that onboarding requirement. No tenancy is provisioned, source reporting edge removed or replacement
root selected. Current root email, segment mappings, descendants' rooted ancestry and existing tenancy
relationships remain intact; this is a real application decision, not a simulated provider operation.

The normal directory hides exempt profiles. Use Include excluded profiles to inspect the root's
retained stable identity and explicit Re-onboard action when source-present and unassociated. That
action can reopen setup deliberately. This application-local tenancy exemption is separate from
application-administrator grants or login authority.

Offboard employee and identity merge remain unavailable for the actual configured root. The server
continues to refuse direct root offboarding with ORGANIZATION_ROOT_PROTECTED; review/UI actions do
not bypass that guard. Other source/configuration/association protections remain unchanged. The
root-only fix removes a conflation between declining tenancy provisioning and removing the hierarchy
boundary; it adds no field, table, migration or permission.

Unit and disposable PostgreSQL regressions cover the exemption, repeat feeds, retained graph and
root protection. Validation passed across the full run's 1,044 successful cases and the corrected affected-browser
rerun (2 tests). Separate unit gates passed: 866 backend units at96.1874%, 177 frontend units
at97.53%. Earlier receipts retain their original scope; failed browser harness attempts and their
corrections are recorded in the validation receipt (private historical evidence; not distributed).

## Optional full history in the information tab

Informational & history keeps a stable tab label in both scopes. Show all history is visible only
inside that tab and starts unchecked for a newly mounted page. Checking it selects the existing
ReviewQuery.category=history; clearing it selects informational and restores latest-applied-feed
scope. The badge uses history_count or informational_count respectively. This does not redefine
those server counts or add a backend filter/field.

Toggling resets page1 while preserving the current search, sort field/direction and page size. The
checkbox choice is remembered when switching to Actionable and back while the page remains mounted;
it is not persisted across page unmount/reload. Actionable selection itself remains unchanged. The
scope helper explains latest applied evidence versus all retained warnings, metadata and completed
decisions; full history is visible without turning completed work back into open actions.

Existing source provenance, historical segment-label projection, indefinite retention, authorization
and cleanup/provisioning guards are unchanged. No backend, schema, dependency or history mutation is
introduced. Final validation passed: 178 frontend units at97.54% complete-source line coverage and 2 real HTTPS/browser tests against disposable PostgreSQL. Earlier receipts remain evidence only for their own source scope.

### Refresh mapping context after decisions

After a real application decision or durable operation acceptance, the shared organization refresh
also invalidates and refetches existing Organization Mapping queries even while that settings page
is closed. The decision flow awaits these refresh attempts so a later settings visit can use the
updated configuration/organization context instead of an inactive cached preview context. In the
employee-action dialog, Decision saved/Operation accepted and Done appear only after these
refresh attempts settle and only if the request was not abandoned. This does not assert that
accepted background work has finished. Other related reads retain active-query refresh behavior;
person-workflow remains invalidated without
automatic refetch. Read failures do not waive server-side context, preview or authority guards;
refresh/review is still required when saved state cannot be confirmed. A QueryClient regression
exercises the inactive-cache case; Final validation passed: 178 frontend units at97.54% complete-source line coverage and 2 real HTTPS/browser tests against disposable PostgreSQL.

## Direct navigation, sign-in and full reload

Tenancies is the landing page for `/` and `/login` after a valid session is established, including
an already authenticated visit. The application brand links to `/tenancies`. Signing in from an
explicit valid feature URL preserves that feature path instead of redirecting every login to the
landing page. This does not restore a previously selected tab from persistent browser storage.

The configured UI explicitly serves these feature shells, including direct address entry and reload:

| Feature | Path |
| --- | --- |
| Tenancies | `/tenancies` |
| Organization | `/organization` |
| Organization drift | `/organization/drift` |
| Organization Mapping | `/organization-mapping` |
| Administrators | `/administrators` |
| Operations | `/operations` |
| Audit History | `/audit-history` |

Existing Operations/Tenancies detail paths retain their identifier routes and normal protected data
reads. Organization Mapping is added explicitly both to the shell route and the public-shell path
allowlist; there is no generic SPA catch-all or new public API permission. The shell/assets contain
no private organization data. API requests still require the existing live session, current grant,
workspace and browser protections; default health-only application composition remains unchanged.

A full reload keeps the requested valid feature path, constructs a fresh frontend state/cache and
requests current authorized data. Search, sorting, pagination, draft inputs and the Show all history
choice that exist only in memory reset; only values explicitly represented in the URL can survive
as navigation state. This correction adds no saved tab/filter preference or session-independent
organization cache. Merely opening/reloading a shell does not submit a workflow or apply settings.
Validation passed: 866 backend units at96.1881%, 179 frontend units at97.55%, six focused shell
tests and two real HTTPS/browser tests covering all seven feature reloads. Earlier receipts retain
their original scope.

## Navigation counts for organization drift and Operations

The authenticated navigation shows two independent workspace counts. Organization drift uses the
existing ReviewDirectory.actionable_count: open actionable reviews across the workspace, not just
the displayed review page or latest-feed information. Operations uses the new read-derived
OperationDirectory.attention_count: waiting/needs_attention organization workflows with a supported
current handoff/review/retry or safe no-effect local cancellation. The matching workspace/person/
pending-operation and exact current intent are required. Read-only inspection diagnostics and
unsupported/orphaned work are excluded; all remain in history. Queued/running/terminal states are
excluded. These workspace hints do not assign work or grant command authority.

### Operations directory addition used by navigation

OperationDirectory has six fields: attention_count, items, total, page, page_size and pages. The new
attention_count is an integer with minimum0 and compatibility default0. The current server computes
it from the authenticated workspace's exact current-intent join and supported-action/pending-person
predicate, in the same read-only snapshot as list counts and rows. It is independent of
list search/state filters and pagination; total still counts the requested filtered directory.
This is a response projection, not a new stored column, table, migration, queue or operation state.
Other operation fields and their [existing source map](operations.md) retain their prior meanings.

NavigationCount reuses the private operations/list and organization-reviews query keys. Existing
feed/decision/workflow invalidations therefore refresh badges with related directories, and logout
or session expiry clears the same private cache. Every ordinary same-app menu navigation requests
count refresh, even when the selected path is unchanged; browser Back/Forward does the same. A
navigation revision triggers those reads without requiring the sidebar to remount. A5-second query
interval is the fallback, alongside existing query focus/invalidation behavior; it replaces the
original30-second badge interval, not the separate session-check interval. This is not a separately
configurable application schedule, background service or delivery SLA. API reads retain live administrator/session/workspace protection.

A known zero hides the visual numeric badge. While no count is available, loading/read failure does
not invent a zero. If a refresh fails after an earlier successful read, that previous value can remain
visible with a last-known-count description; it is not presented as a fresh successful observation.
The links retain stable Organization drift/Operations accessible names; aria-describedby supplies the
separate count or unavailable description, while the visual number is hidden from the accessible
link name. No backend writes, generic Retry control or remediation inbox is introduced.

Validation passed: 1,047 backend/database/browser tests and 184 frontend unit tests, with separate backend/frontend unit coverage of96.1896%/97.57%. Earlier receipts
retain their own source scope; this addition introduces no configurable setting or dependency.

## Refresh counts on navigation and observed workflow progress

The shared navigation hook increments a revision on each navigate call and browser popstate, including
reselecting the current menu link. Both NavigationCount components refetch when that revision changes.
Normal modified-click/new-tab browser behavior remains native; a new document performs its own initial
protected reads. Count definitions, private cache keys, stale/unavailable descriptions and logout
clearing remain unchanged. The fallback interval is5seconds, not a promise of push delivery or an
upper bound on observed delay when a browser/network/read is unavailable.

When the onboarding panel observes a new operation state or phase, it invalidates the operation detail
and Operations list immediately rather than waiting for the badge interval. Repeated polls of the
same state/phase do not repeatedly fan out those invalidations. Completed onboarding uses the shared
organization refresh; successful CSV upload now uses that same helper so reviews, mapping, inventory,
Operations and audit reads are refreshed under their existing active/inactive cache policies. Read
failure still does not waive current-context, preview or authorization checks.

### Shared picker sizing and verification scope

Shared Select controls retain native select semantics. In browsers supporting base-select, the open
picker is content-sized with the closed control as its minimum width and a viewport-bounded maximum;
it is not capped to a narrow closed-field width. State/category filter fields reserve a shared13rem
minimum. Short options should remain one line; long choices can wrap within the bounded scrollable
picker. If ordinary field-aligned placements cannot fit, CSS viewport-spanning safe-center
fallbacks place it below or above the field. Unsupported browsers and forced-colors mode retain
their native picker fallback.

The19-use Select inventory is paired with actual-picker browser checks on the seven feature pages
and relevant workflow modal states at1280/900/768/390/320px. The helper opens visible enabled controls,
checks option bounds and short-label height, then verifies Escape focus/value preservation and
Space-key reopening. That targeted browser coverage is not a claim that every OS-native fallback or
all possible conditional option states have been exercised. The [standing UI review policy](../ui-ux-review-policy.md)
retains the broader visual/interaction requirements. Named helper and critical refresh comments explain
the native/control and cache boundaries. No backend, database, schema or dependency changes are added.
Final validation passed: 187 frontend units at97.58% coverage, 8 real HTTPS/database/worker integration cases and 30 isolated picker-position cases. Earlier receipts
retain their original source scope.


## Shared access and onboarding refinement — 3 November 2026

Local simulation qualified and installed in both saved instances. This section supersedes the earlier new-compartment-only join
flow and registry-only simulated removal milestone; it does not qualify real OCI. See the
[isolated manual review runbook](../how-to/tenancy-refinements-runbook.md).

### Select an existing compartment or create one

OrganizationAction and the frozen OrganizationIntent add nullable `existing_compartment_ocid`,
bounded to 1–256 characters when present. When null it is omitted from serialization, preserving historical request digests and stored intent
shapes. A non-null value is allowed only for join_shared and cannot be combined with
parent_compartment_ocid or compartment_name. The server discovers the selected registered child's
compartments and rejects the root, foreign/unknown or changed scope. A new compartment instead uses
a discovered parent and a new name. Neither choice lets browser-provided names/OCIDs become target
authority. Existing assignment creates no replacement compartment; its returned exact binding must
match the selected OCID before membership becomes active. Stored membership compartment/user fields
retain the choice without another database column.

### Remove identity access, keep resource cleanup manual

A shared member's Remove member action targets the frozen registered association, child and personal
user. Simulated completion now requires a closed MemberRemoval receipt for that exact triple, with
group memberships removed and personal user deleted. The receipt is checked before local membership retirement; the two durable identity steps,
immutable outcome and registry retirement commit in the same transaction. Missing, duplicate, foreign or mismatched receipts
cannot publish a successful removal. Existing clickable owner/member names and Transfer owner remain available. The redundant top-level
Manage owner & associations button is removed; this is not a change to owner-row permissions.
Whole-tenancy deletion remains a separate guarded workflow.

The compartment binding is retained as manual cleanup guidance. No resource inventory, purge,
delete_compartment or resource-cleanliness verifier is introduced. cleanup_required means the owner
still has a manual obligation to review only the departing user's resources, independently of
completed identity retirement. Preserve the shared compartment and other members' resources.
Current status may say access removed only after the simulator's identity readback receipt; it must
not say the employee's resources were removed. Retries retain the frozen account/association target.

### Detail presentation

Active tenancy detail groups current override categories, inheritance/verification state and the
existing editor in an Overrides section. It does not introduce another override API or source of
configuration authority. Inventory status exposes the existing immutable created_at as a UTC
creation-date tooltip, available by pointer and keyboard focus with Escape dismissal. This is local
registration time, including imported rows, not a newly discovered OCI creation timestamp. No
created-date column or storage migration is added.

New create/import work uses guided onboarding version 2, applying the exact baseline frozen at
admission before post-baseline access checks and temporary-account retirement. Previously accepted
version 1 and absent-version intents retain their original semantics; see the
[onboarding field and step guide](tenancy-onboarding.md).


Local qualification and saved-instance receipt (private historical evidence; not distributed).


## Frozen environment contacts — source candidate

Validation pending. OrganizationIntent now has 26 fields, with optional email_contacts omitted when
null so legacy raw/typed takeover hashes remain unchanged. PersonWorkflow has 17 fields, adding
nullable preview contacts; OnboardingView has 23, returning the accepted snapshot. Employee email
remains the canonical organization key. Environment routing does not merge people, rename logins or
change owner/manager links. [Complete route/notification map](lifecycle-email.md) ·
[Settings and release gate](application-settings.md). No actual OCI activation/invitation contact
behavior is qualified by local contact preview or SMTP capture.

## Destructive consent and directory-return correction — source checkpoint

Local qualification, all independent reviews and the preserved-data main-preview update pass.
The parallel preview remains unchanged; see the [final receipt](../history/employee-restoration-consent-checkpoint-2026-11-06.md).
There is no table/column migration and no automatic infrastructure restoration.

New POST /api/organization/actions admissions require confirm_destructive=true for exactly:
offboard_person, delete_tenancy, remove_member, transfer_owner and merge. False is the default and
is excluded from canonical serialization, preserving pre-consent request hashes. An authenticated
exact committed replay returns its original receipt before the new consent guard; this does not
permit a new unconfirmed operation or bypass current session/grant authority. Missing consent on a
new destructive request yields DESTRUCTIVE_CONFIRMATION_REQUIRED before mutation or enqueue.

The native employee dialog presents the exact person, selected tenancy/recipient/merge partner and
full association plan, with a required consequence acknowledgment. Consent resets on action,
target/recipient/partner, plan or preview-context changes and is unavailable during preview refresh.
Manager/shared warnings and zero-association offboard confirmation are additional requirements,
not substitutes. Whole-tenancy DELETE admission keeps its existing explicit confirm_deletion
contract and impact review; it is not a reason to add an unrecognized field to that separate API.
Only an actually absent employee can be explicitly offboarded. These rules do not relax root,
parentage, pending-work, association or identity-merge guards.

Fixed confirmation failures return safe HTTP409 codes DESTRUCTIVE_CONFIRMATION_REQUIRED or
PERSON_NOT_ABSENT as applicable; unknown error text remains hidden by the existing allowlist.

Verified association cleanup can mark a source-present zero-link person as needing onboarding.
The restricted worker therefore receives UPDATE only on the existing setup_required and
setup_episode_id columns in addition to its prior directory-control grants. It receives no
new identity-key/email, table-wide UPDATE, administrator, credential or history-rewrite grant.
The role installer applies these grants idempotently; no data migration/backfill is performed.
