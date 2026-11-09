# Organization Mapping implementation and operator guide

2 November 2026 · Mappings/root replacement and mapping-review correction validated locally · Provider work remains simulated

[Approved contract](../engineering-design/20-organization-mapping-settings.md) ·
[Required regression matrix](../engineering-design/20-organization-mapping-settings.md#required-leaderdesignee-regression-matrix) ·
[Test plan](../engineering-test-plan.md) · [Implemented ER](../architecture/diagrams/organization-workflows-implemented.mmd)

[Manual test runbook and six synthetic CSVs](../how-to/organization-mapping-runbook.md).

## Set up and maintain mappings

Application Settings → Organization Mapping is the current settings editor. Save a root manager and
at least one industry segment before uploading the first CSV. Names are trimmed, leader/root emails
normalized, and designee emails deduplicated. Segment names and leaders must be unique; the root
cannot also be a segment leader. Typed emails work before employee data exists. Saved nominations
are not proof of reporting eligibility: the first feed establishes that evidence.

After import, Find designee offers employee suggestions and Add designee appends the chosen email.
Leader email is a plain typed email field, not a dropdown. After import, the root is read-only during
ordinary editing; use the explicit Change organization leader action for a replacement. Add, rename,
replace segment leaders, edit optional designees or remove segments in one
draft. Removing the last segment is rejected; removing the last designee is allowed. A segment's ID
survives edits. Only the server assigns new IDs, and requests cannot reuse IDs of removed mappings.

Preview changes calculates mapping additions/changes/removals, classification and recipient deltas,
unassigned employees, and role health in a modal dialog. Saved organization role health appears
above the editor, so outstanding nominations are visible before editing. The dialog separates summary
counts, segment changes and paginated employee impacts (ten per page). Preview is read-only.
Back to editing or Escape closes the preview and retains the draft; another preview is required
before Apply. Closing is disabled while a request runs. Keyboard focus starts at the dialog heading
and Back to editing/Escape returns focus to Preview changes. Every form edit invalidates the preview,
including an in-flight response. Apply recomputes
under the workspace lock and checks the exact normalized candidate and configuration, applied,
proposed and registry revisions. Pending lifecycle work, genuinely unapplied source proposals or
ineligible replacement leaders block Apply; an already-applied proposed pointer is not pending work.
No durable draft, preview table or extra workflow coordinator is introduced.

Apply publishes the configuration and derived organization version immediately and refreshes the
Organization and Tenancies displays. It does not change source reporting relationships, ownership,
association records, administrator grants, OCI accounts or resources. Repeated/uncertain writes are
not retried as fresh commands: refresh saved state, compare retained edits, and preview again. Cancel edits
explicitly restores saved values. Visiting the page never initializes settings.

Nonfatal gaps can be previewed and applied without preventing existing-tenancy cleanup. They do block
new provisioning for affected people: create/import/shared-join require valid accountability. The
employee action dialog explains the missing mapping and links back to settings rather than offering
those three actions. Ignore acknowledges a review only; it never supplies a segment or overrides
this guard. Other otherwise-available cleanup and non-infrastructure decisions remain independent.

## Replace the organization leader

Change organization leader unlocks the saved root email deliberately. Enter the replacement, keep or
edit the segment mappings, then Preview changes. The preview shows the old/new root, whether the new
root has an employee row in the latest applied feed, the total employees with unresolved reporting
chains, and paginated before/after ancestry, assignment and recipient changes. The browser requires
I reviewed this leader replacement and its reporting gaps before Apply when the root actually changes.
Back to editing/Escape retains the draft; Cancel edits restores saved settings and the ordinary root lock.

A missing new-root row does not block a deliberate replacement. This permits settings to be updated
before the revised organizational feed arrives. The preview warns that reporting paths may become
incomplete and employees unassigned; applying never moves source reporting edges or guesses a
successor. An unchanged segment leader may remain nominated with a visible role defect; a newly
selected segment leader must still satisfy the existing eligibility guard. Upload an updated feed
containing the intended reporting relationships afterward to resolve those gaps. Presence alone is
not a healthy-role or complete-graph guarantee.

The API requires change_root=true for a post-import root email or display-name change. That flag, candidate and revision
context are part of the preview digest; changing any of them invalidates the reviewed request. The
checkbox is a browser review affordance, not a separate server authorization field. Apply rechecks
current administrator authority, blockers and exact context, and permits only root_email to differ
from the trusted source policy. Source/population identifiers, authority, census and freshness policy
remain unchanged. No tenancy associations, grants, source observations or absence decisions change.

## Departures are two independent responsibilities

Every configured leader and designee is evaluated per segment, even if a segment leader is invalid,
there are no tenancies, or a profile is hidden/excluded. A single person may have several affected
roles. Current role issues use the existing `LOB_LEADER_REVIEW` and `DESIGNEE_INVALID` kinds with
`segment-id:email` targets. Repeated feeds keep each open episode rather than adding duplicates.
Role reviews link to their segment's settings. Employee association actions remain separate.

A missing required current employee profile is not healthy leadership merely because a retained
reporting path still exists. A reference can prevent a false absence without qualifying a role.
Unknown identity, incomplete ancestry, changed reporting branch, explicit exclusion and confirmed
absence have distinct health messages. The configured root-profile exemption still applies only
to that boundary. Stale/partial/unqualified inputs cannot establish a new departure.

Absent leaders stay nominated in their stable segment as evidence, but cannot supply current
accountability. No successor or designee promotion is guessed. Absent/invalid designees stay visible
until replaced/removed, are excluded from effective future routing, and do not remove healthy peers.
Role eligibility is computed independently of review suppressions. An acknowledgment or tenancy
cleanup cannot make an invalid nomination eligible. Actual mapping/source repair closes the relevant
role condition. Fixing mappings does not close tenancy cleanup/absence decisions.

Unresolved absence remains a decision even after a person reappears. Completed offboarding followed
by a newly applied fresh actual employee row restores the stable directory identity, settling only its already-handled absence and opening one onboarding episode when needed. Full and partial feeds qualify for this positive presence; no intervening absence cycle is required. Validate each role independently against actual reporting evidence.
The return does not make an ineligible nomination healthy by itself. Accepted operation targets and
existing notification evidence stay frozen; future eligible routing comes from the new head only.

## Recalculation is not a new observation

`prepare(..., configuration_only=True)` preserves existing identity and row/reference/source/census
clocks, absence flags and continuous-absence keys. Reused fresh evidence cannot create absence; stale
evidence can recalculate classification without pretending to be fresh. Reviews skip directory
return/onboarding transitions in this mode. Explicit administrator absence decisions are applied to
a working baseline, independently of source inference; original source and predecessor remain immutable.
The first genuine newly applied feed still follows freshness/actual-row return guards. Full census qualification remains necessary for departure inference; a fresh partial employee row can establish that person's presence.
During replacement, the immutable previously accepted feed can contain the former root without a
manager. Mapping-only recalculation retains a nonfatal MANAGER_REQUIRED diagnostic and shows that
unresolved path; it does not invent the missing edge. Fresh uploads remain strict: every non-root
employee requires a manager. The original source, source capture and historical configuration remain
available, and the old root becomes an ordinary retained identity rather than being silently deleted.

## Public contracts and fields

Ten mapping DTOs expose 61 effective fields, including inherited Apply fields. They are exported to
JSON Schema and generated TypeScript. Public mapping endpoints are authenticated, workspace-scoped,
and use existing same-origin protections. JSON commands are bounded to 64 KiB and reject unknown fields.
Neither source trust nor actor/workspace can be submitted through this form.

| Contract | Fields and authority |
| --- | --- |
| `MappingSegment` (4) | `id` (null for new, existing active server ID for edits), `label`, `leader_email`, `designee_emails`. Persist as `Configuration.lobs` (`id`, `label`, `leader_email`, `designee_emails`). |
| `MappingCandidate` (3) | `root_email` → allowed `Configuration.policy.root_email`; optional `root_name` → `Configuration.root_name` (trimmed 1–256 characters); `segments` → complete active `lobs`. All other policy/configuration fields remain server-owned and unchanged. |
| `MappingContext` (4) | `configuration_id`, `applied_version_id`, `proposed_version_id`, `registry_revision`, from `org_workspace`; null heads/configuration and revision0 represent an unconfigured workspace. |
| `MappingRequest` (3) | `context`, `candidate`, `change_root` (false by default). The flag explicitly permits a post-import root email or name edit and is included in the candidate/context digest; no computed employee impacts are accepted. |
| `MappingApply` (4) | Inherited `context`, `candidate`, `change_root`; `preview_token` is the canonical request digest including replacement intent. It is a consistency binding, not administrator authorization. Apply independently reauthorizes and recomputes. |
| `MappingChange` (3) | `segment_id`, `before`, `after`: small old/new mapping records; null side denotes addition/removal. Also stored as administrative audit evidence. |
| `MappingRole` (5) | `segment_id`, `segment_name`, `role` (`leader`/`designee`), `email`, `status`. Derived from saved nominations and latest applied evidence; never a new identity or tenancy grant. |
| `MappingImpact` (11) | `person_id`, `name`, `email`, `before_ancestry`, `after_ancestry`, `before_segment`, `after_segment`, `before_leader`, `after_leader`, `before_designees`, `after_designees`. Derived, paginated preview only; ancestry is root/resolved/incomplete from the old and recalculated graphs. |
| `MappingSettings` (8) | `configured`, `available`, `context`, `candidate`, `root_editable`, `has_feed`, `roles`, `blockers`. `available` depends on existing settings or explicitly composed trusted source policy. `root_editable` describes ordinary editing before a feed; false requires the explicit replacement flow rather than permanently prohibiting replacement. |
| `MappingPreview` (16) | `root_before`, `root_name_before`, `root_present`, `unresolved_count`, `context`, `candidate`, `preview_token`, `changes`, `roles`, `affected_count`, `unassigned_count`, `items`, `page`, `pages`, `blockers`, `has_feed`. `root_before` is the nullable saved root; `root_present` means an actual row in the latest applied source (false before a feed), not inferred presence or eligibility. `unresolved_count` covers all projected employee profiles with incomplete ancestry, not just the impact page. No persistence or authority is inferred from rendering the preview. |

Role statuses: `healthy`, `departed`, `excluded`, `profile_missing`, `ancestry_incomplete`,
`branch_changed`, `not_verified`. The last is a neutral pre-feed nomination state. A healthy designee's
own evidence does not restore routing through an invalid leader. Blockers: `PENDING_LIFECYCLE`,
`UNAPPLIED_ORGANIZATION`, `INELIGIBLE_REPLACEMENT_LEADER`. The server enforces recomputed blockers.

Routes: `GET /api/organization/mapping`, `POST /api/organization/mapping/preview?page=N`,
`POST /api/organization/mapping/apply`. Closed errors distinguish changed preview, root/segment
fences, invalid graph/input, pending work and unavailable policy. Private parser/database details
are not returned. Inputs remain in the body, never URL fields except page number.

## Storage and audit

No new table, column or database migration is needed. Current configuration remains the JSON in
`org_workspace.configuration`, keyed by `configuration_id`. Each applied/proposed version pins
its configuration in `org_version.configuration`. Employee assignment, leader and effective
designee fields remain in the existing `org_member` projection/data. Existing `org_person`
lifecycle controls are not changed by mapping-only Apply. Existing recommendations hold role episodes.

`OrganizationEvidence` records `mapping_root_before`, `mapping_root_after`,
`mapping_root_name_before`, `mapping_root_name_after` and `mapping_changes`.
The existing immutable `organization_configured` audit event records the verified actor and new
configuration identity with these small changes; it does not log a whole HR feed. Failed transactions
roll back configuration, head pointers, versions, recommendations and audit together. Initial/pre-feed
configuration changes retain their before/after mapping evidence in audit even without source versions.

The private deployment `organization.json` remains a trusted legacy/bootstrap policy input. Its LOB
values no longer silently initialize settings during CSV upload, and cannot overwrite saved DB values
on restart. `application.toml` continues to hold operational settings, not this mutable mapping list.
Validation uses synthetic fixtures and disposable PostgreSQL, never the user's saved mappings.

## Required regression matrix trace

The design matrix is exercised by the following named cases. Final run status belongs in the dated
validation receipt; a source listing alone is not proof that the gate passed.

| Design scenario | Unit / PostgreSQL / browser evidence |
| --- | --- |
| Qualified leader departure | `test_leader_eligibility_matrix[departed]`; `test_departed_multirole_no_tenancy_and_independent_repair` with/without tenancies; `departedMapping` browser flow. |
| Referenced leader missing its own row | `test_leader_eligibility_matrix[missing]`; existing profile-coverage invariants continue to gate absence inference. |
| Leader below another manager/outside root | `test_leader_eligibility_matrix[moved/outside]`; `test_replacement_follows_source_graph_and_keeps_segment_identity`. |
| Replacement, rename, segment dissolution | Server-ID and preview-impact units; immediate-version and retired-ID PostgreSQL cases; `departedMapping` replacement and `mappingInventory` rename/dissolution-preview browser flows. |
| Root omission or replacement | Root-profile-exemption unit; unmarked changes remain fenced. Added `test_explicit_root_replacement_previews_reporting_gaps_without_new_observation` variants cover present/missing successors; `test_root_replacement_audit_graph_repair_and_old_root_cleanup` covers real storage, unchanged associations/clocks, audit, stale replay and a later corrective feed. Frontend root-replacement case covers unlock, warning/confirmation and restored lock. All added cases pass in the final root-replacement validation. |
| Designee departure, with/without tenancy | Multi-role pure case; multirole PostgreSQL variants give leader and designee their own child when enabled; exempt no-tenancy designee case; browser shows independent role repairs after no-tenancy offboarding. |
| Healthy peers/optional empty list | `test_designee_peers_partial_stale_and_acknowledged_departures`; root/optional-designee unit; PostgreSQL removal of final optional designee; browser replacement removes invalid nominations explicitly. |
| Designee changes branch/rooted ancestry | Independent role-health evaluation, leader outside-root unit graph, nominee peer cases and qualified-return PostgreSQL variants with eligible/ineligible returned roles. |
| Multiple roles, invalid leaders, repeated feeds | Pure multirole departure and unresolved-return case; PostgreSQL verifies all four segment/role targets keep their original review IDs across repeated feeds. |
| Offboarding, exclusion or acknowledgment before repair | Excluded-alias invariants and nomination-suppression unit; exempt-designee and independent-offboarding PostgreSQL cases; `departedMapping` browser offboards first then repairs roles. |
| Partial/stale/incomplete inputs and return | Coverage/absence invariants plus peer cases; fresh/stale mapping reapply tests; four qualified-role-return PostgreSQL variants retain renewal and recheck eligibility. |
| Reapply/concurrency/frozen accepted work | No-observation units, including unchanged historical suppressions; PostgreSQL exact controls/association/history comparisons, audit-failure rollback, concurrent Apply, source/registry fences, pending lifecycle and accepted-intent pointer checks. |

Transport tests require real session and same-origin middleware, reject caller source-policy/workspace
fields, bound request sizes before buffering, close private errors and verify scope comes from the
session. `test_mapping_apply_with_installed_api_role` uses actual installer permissions and updates
an existing role episode without broadening grants or rewriting descriptive history. Browser fixtures
use the same configuration-update column permissions already granted by the real API installer.

Playwright exercises the actual built frontend, HTTPS, restricted API, PostgreSQL and native worker.
It verifies initial import gating, preview invalidation, employee selection, keyboard Apply/Add,
linked role repair and independent cleanup, and immediate Organization/Tenancies projections.
Desktop/390/320px captures include long synthetic nomination emails in an **unapplied** initial preview
and real multi-role warnings in the disposable installation. Production OCI and notification delivery
remain outside this slice's qualification; no test sends email or calls OCI.

## Validation checkpoint

The following receipt covers the base mapping/departure implementation before root replacement.
Its results remain historical; the later root-replacement validation below covers the extension
and its independent final reviews.

The2November2026receipt (private historical evidence; not distributed)
records1,006passing backend/database/browser tests,833separate backend units at96.13% line coverage
and172frontend units at97.46%. Both complete-source unit gates exceed95%. All three independent
reviews passed; no material findings remain. Source formatting, generated contracts, package source
checks and static security checks also pass. Current deployment has14application tables at
0010_guided_onboarding, unchanged by this slice.


## Root replacement validation — 2 November 2026

All1,014backend/database/HTTPS-browser tests and175frontend units pass with no failures/skips.
Separate unit-only coverage is96.14% backend and97.51% frontend. Independent documentation,
security and UI reviews passed. Actual browser tests cover root unlock/cancel, confirmation-gated
Apply, missing-successor warnings, narrow screens, updated feed repair and former-root absence.
The six manual CSVs are validated as a qualified census sequence by a dedicated unit test.
Validation receipt (private historical evidence; not distributed).


## Compact designee editing — 2 November 2026

On wide screens, Find designee/Add designee and the editable two-row designee email list share one
horizontal row. At1100px and below the two fields stack; on phones at480px and below Add designee
moves below the search input to preserve a usable typing area. Pre-feed setup still permits typed
nomination emails without employee lookup. Search/Add, email editing and preview invalidation retain
the same behavior and contracts; this refinement changes no stored fields or permissions.

## Corrected mapping reviews and onboarding eligibility — 2 November 2026

When mapping or reporting repair makes a person's current accountability valid, their no-longer-active
LOB_MAPPING_REVIEW closes automatically as mapping_corrected. The existing row stays in history;
an unignored later regression opens a fresh episode. Validation uses the current stable person UUID,
resolved ancestry, active segment ID and its configured accountable leader. The exact configured root
with ancestry=root is explicitly exempt from needing a segment. A stale ID, permanent Ignore, hidden
profile or disappearance of a diagnostic is not evidence of repair.

This correction closes only the repaired mapping condition. Unrelated branch gaps, absence decisions,
tenancy-setup reviews and leader/designee nomination work remain governed by their own conditions.
It does not invent reporting relationships, change ownership/membership, recreate onboarding episodes
or alter observation clocks. Existing cleanup remains available under its usual guards even when
new create/import/shared-join provisioning is blocked.

PersonWorkflow adds derived mapping_required (false by compatibility default, explicitly computed by
the server); its fifteen-field preview and current command checks share the same accountability rule.
This is separate from the ten mapping DTOs (61 effective fields in total), which include root display metadata. The UI warning/repair link
is an affordance; the server independently removes/rejects blocked actions and repeats a defensive
admission check. No new table, column, migration or audit-event kind is introduced.

The correction passed 1,041 backend/database/browser tests and 177 frontend unit tests. Separate
unit coverage is 96.18% backend and 97.52% frontend; earlier receipts retain their original scope. See the [workflow field map](organization-workflows.md#personworkflow).


## Root manager display name

Root manager email and Root manager name share one responsive row and the existing **Change
organization leader** button. The same Preview/Apply transaction saves both. Name-only editing
requires no boundary-replacement confirmation; email replacement retains its existing confirmation.
The preview shows the saved and proposed name; audit details retain those values at the time of Apply.

`Configuration.root_name` is optional for existing records; missing values preserve existing
feed/reference-name fallback. A supplied name is administrator-owned display metadata and wins over
root names in subsequent feeds. It is copied into the effective root person so direct reports show
the same friendly manager name as other employees. It does not change email identity, source rows,
profile type, observation/census timestamps, absence eligibility or tenancy associations. A configured
root name never proves that the leader is present in a feed. Storage uses the existing configuration
JSON and effective member name; no new table or migration is required.

Manual check: unlock the root fields, enter a name without changing email, Preview and Apply.
Refresh Organization and confirm direct reports display the configured manager name. Reload settings
to confirm persistence. Load another feed and confirm the name persists and role-health checks still
reflect actual feed presence. A replacement should update both fields before Preview.

## Fresh presence versus offboarding — source checkpoint

Already-offboarded identities may return on fresh applied full/partial actual employee rows;
reference-only, staged, replayed, stale and configuration-only inputs cannot do so. Exempt/merged/
pending people are not resurrected, no infrastructure is restored and unrelated leader/designee
conditions are not closed by directory restoration. Standalone deletion/member removal/transfer
never offboards or settles an independent absence. Explicit Offboard employee requires actual
current-row absence and destructive consent. No mapping or source-history rewrite is added.
Qualification and saved-preview update for this correction are pending; see the
[workflow contract](organization-workflows.md#destructive-consent-and-directory-return-correction--source-checkpoint).
