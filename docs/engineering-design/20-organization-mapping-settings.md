# Organization mapping settings

2 November 2026 | Approved implementation contract | Immediate preview/apply approach selected by user

## Problem and selected approach

Administrators must define and maintain top-level manager to industry-segment mappings in
Application Settings, alongside Administrators, without rebuilding or restarting OTM. The user
selected preview followed by immediate recalculation on Apply, rather than waiting for another
CSV. This document defines the approved behavior. The implemented settings screens, commands and field
map are described in the [runtime guide](../reference/organization-mapping.md).

## Scope and existing foundations

Use the existing `Configuration.lobs` model: stable segment `id`, display `label`, accountable
`leader_email` and optional `designee_emails`. Use the existing root in `Configuration.policy`.
UI terminology is **Industry segments**; internal LOB identifiers remain unchanged.
Use **Industry segment** consistently in the affected settings, Organization and Tenancies labels,
filters, previews and validation messages; existing internal/API `lob_*` fields retain their names.
Segment IDs are server-assigned, immutable across edits and never reused after removal from active
settings.
Historical configurations retain removed segments. No separate segment service or table is needed.

`org_workspace.configuration` remains the current settings authority; `org_version.configuration`
retains historical settings. Reuse existing audited configuration publication and reconciliation
patterns, extending their contracts where needed. `application.toml` remains operational settings.

## Initial setup and import gate

Application Settings → Organization Mapping contains a root-manager email and an editable list
of segments. Each segment requires a nonblank name and leader email; designees are optional.
Before any employee data exists, accept typed emails rather than require an employee picker.
After import, offer searchable employee selection while retaining explicit normalized emails.

Save initial settings only as a complete valid configuration: root plus at least one mapping.
The UI and CSV API reject first import until this configuration is saved. The Organization empty
state links to Organization Mapping and describes missing setup. Merely visiting a page performs
no writes. No deployment file silently initializes a new organization on first CSV upload.

Validate email syntax/normalization, unique segment IDs, unique labels after case-insensitive
trimmed comparison and unique leaders, and prohibit selecting the root as a segment leader.
Deduplicate designees. Reuse trusted source policy from application composition; this form cannot
grant census authority or change source/population/freshness policy. Initial setup sets only the
allowed root field and mappings. No wildcard or guessed reporting relationships are introduced.

Before a feed exists, clearly distinguish saved mappings from validated reporting relationships.
The first import verifies leader/designee coverage and root relationships using existing domain
rules and exposes unresolved mapping reviews; it must not claim that a valid email proves a
valid reporting position. Incomplete manager coverage retains the existing absence-inference gates.

## Editing, preview and Apply

Administrators can add a segment, change its name/leader/designees, or delete a mapping from the
active list. Editing retains its stable ID. Treat the form as one proposed configuration with
Preview changes, Apply changes and Cancel; no per-keystroke publication or autosave.
Any subsequent form edit invalidates its preview and disables Apply until a new server preview
succeeds. Apply binds the exact normalized candidate configuration to the expected revisions;
a matching old preview cannot authorize different edited values.

Preview is read-only and server-computed against the current applied organization and immutable
latest applied source. Show added/changed/removed mappings, affected employee counts, before/after
segment assignments and mapping/designee warnings, including employees becoming unassigned.
Paginate affected employees and avoid exposing whole raw feeds. No feed is needed to preview and
save initial setup; until the first feed, explain that employee impact cannot yet be calculated.

Apply rechecks live administrator authority, browser protections and expected configuration,
applied/proposed organization and registry revisions. Compute again under existing workspace
locking; never trust client-supplied preview results. Concurrent imports, registry/workflow changes
or edits invalidate the preview and return a refresh/review conflict while preserving entered edits.
Reject Apply while a genuinely unapplied organization proposal or pending organization lifecycle
operation exists; show its status and require it to be settled first. An already-applied proposal
pointer is not pending work. No extra preview table, coordinator or durable draft is required.

With an applied organization, publish a new configuration identity and recalculated organization
version atomically with the audit event. Retain source identity and capture time. Refresh employee
and tenancy segment displays from that version immediately after success. A label-only edit is
still a versioned change; historical pages continue using their pinned configuration.

Configuration-only recalculation must never infer a new absence, refresh presence/census clocks,
or generate return/onboarding episodes from reused evidence, even when that evidence remains
fresh. Preserve existing absence and lifecycle decisions. Existing `trusted_reapply` alone is not
proof of this invariant; explicitly test and enforce it in the implementation. Stale evidence can
support mapping recalculation without being presented as a new observation.

Mapping defects remain visible through existing domain review rules. Reject fatal graph or
configuration violations; nonfatal mapping gaps may be applied after the preview clearly shows
them. A formerly mapped employee may become unassigned. Applying such a gap remains permitted,
but new create/import/shared-join provisioning for that person is blocked until valid accountability
is restored; existing cleanup and other administrator decisions remain available under their guards.
No automatic reassignment to an unrelated
segment is allowed. Keep at least one validly configured segment; deleting the last mapping is
rejected. The approved root-replacement extension supersedes the original post-import root lock.
Ordinary editing keeps that field read-only; Change organization leader explicitly unlocks it.
Preview shows old/new root, latest-feed row presence, unresolved employee paths and before/after
ancestry/classification. A missing replacement row is allowed with a warning, not an invented reporting
edge or automatic successor. Deliberate Apply is followed by an updated feed to resolve reporting gaps.
Bind change_root intent into the preview and recheck it at Apply; only root_email may change within
trusted source policy. Existing source/population/authority/freshness/census settings stay fixed.

## Leader and designee departures

Departure review covers both tenancy associations and organization responsibilities. Detect affected
roles from all configured mappings, including people with no tenancy and people already excluded
from the managed directory. A person can be a leader and a designee, or a designee for several
segments; show each affected segment and role without creating duplicate reviews on repeated feeds.
Evaluate designee health even when its segment leader is also invalid. Reuse existing reviews and
versioned settings; no new departure coordinator or automatic replacement is required.

A confirmed absent leader leaves the segment and its stable ID intact, with the configured leader
retained as evidence and a **Leader needs attention** state. Exclude invalid leadership from current
accountability/routing and show affected/unassigned employees. Do not guess a successor, promote a
designee or remove the segment. An administrator selects a replacement using preview/apply; its
reporting chain must meet the same root/branch eligibility rules. Changing a mapping does not move
employees in the source reporting graph; show remaining reporting gaps rather than invent edges.

A confirmed absent designee remains in saved settings as an invalid nomination until explicitly
removed or replaced. Show **Designee needs attention** with a link to that segment's settings and
exclude the person from new effective designee routing. Retain other eligible designees. Designees
are optional: removing the last designee is valid, distinct from deleting the last segment. If
required routing is incomplete, follow the existing notification-family policy, not a new generic
fallback. Retain frozen accepted notification evidence and existing correction/delivery guards.

Employees leaving a branch, a leader no longer reporting directly to the root, incomplete ancestry,
and unknown configured identities also require role validation even without confirmed absence.
Settings health distinguishes a confirmed departure from incomplete feed/profile evidence. A row
missing from a partial/stale/unqualified feed is not proof of departure. A missing manager row still
referenced by incoming employees raises profile/coverage review and keeps absence inference gated;
the reference does not by itself establish a healthy current leadership profile. A missing configured
root row alone is permitted when the source policy explicitly exempts that boundary profile.

Tenancy offboarding, removing associations, acknowledging an absence or hiding an employee must
not silently clear outstanding leader/designee defects. Mapping repair likewise does not settle
tenancy cleanup. Link the related work and derive completion from current role eligibility and
saved settings; an acknowledgment never makes an ineligible person a valid recipient. Preserve
existing valid per-condition decisions without allowing suppression to restore invalid routing.
If a person returns while an absence decision remains unresolved, retain that decision requirement
and reevaluate all configured roles. Preserve the existing qualified-return renewal semantics after
completed offboarding; that path can clear the old absence episode and reopen onboarding. In either
case, validate every role against current reporting evidence and saved nominations; return alone
does not prove a leader/designee is eligible or settle an outstanding mapping defect.

## Effects and security boundaries

A mapping change updates organizational classification and derived accountability/designee
routing only. It does not alter tenancy ownership, memberships, administrator grants, OCI access,
resources or accepted operations, and does not offboard/delete employees. Reuse dispatch-time
authority/configuration checks for operations that rely on organization state; never reinterpret
an already accepted destructive target from newly edited mappings.
Accepted operation intent and notification recipient/routing snapshots remain frozen; new mappings
affect future routing only, not the recipients attached to already accepted work.

Require current authenticated administrator authority for reads, previews and writes; scope all
queries to the verified workspace. Apply uses the existing same-origin/CSRF protections and
bounded, closed request models. Audit actor, configuration revision and meaningful changes using
existing immutable audit facilities; never log whole HR feeds or credentials. A failed transaction
leaves settings, versions and audit unchanged. After an uncertain response, refresh current state
before offering another Apply; never automatically retry a write as a new command.

Existing installations retain their database mappings. The private `organization.json` profile
becomes a legacy/bootstrap input, not ongoing authority: starting/restarting or importing must
not overwrite saved settings. Expose existing database values in the form. Do not change the
user's live installation as part of tests or migration demonstrations.

## UI and verification

Follow Field Console in DESIGN.md: existing settings navigation, navy/cobalt palette, crisp 3px
corners and shared forms/dialogs. Include empty/loading/error/dirty/saving/conflict/success states,
keyboard labels and focus return, readable long emails and responsive 320/390px layouts. Scope
controls to the authenticated workspace and use organization-independent guidance. Shared
navigation and both Organization and Tenancies must reflect applied changes consistently.

Acceptance requires meaningful unit tests at the existing 95% complete-source gate, disposable
PostgreSQL integration and Playwright flows. Cover first-import API/UI gating, initial typed-email
setup, CRUD/last-mapping guard, stable IDs/history, designee changes, immediate derived displays,
nonfatal orphan warnings, fatal rejection, fresh- and stale-source reapply without new absence/return,
pending work guards, concurrent stale previews, unauthorized/cross-workspace requests, rollback and
uncertain-response recovery. Keep provider work simulated and all fixtures synthetic.

### Required leader/designee regression matrix

These tests are part of the implementation acceptance gate, written alongside implementation and
passing before completion. This is a requirement list, not a claim that these tests already exist.

| Scenario | Required outcome |
| --- | --- |
| Qualified leader departure | Stable segment retained; leader review and affected assignments visible; no automatic successor or tenancy/access mutation. |
| Leader still referenced but missing its row | Profile/coverage warning rather than false absence; unresolved leadership evidence remains visible. |
| Leader moves below another manager or outside the root | Eligibility/routing review without falsely calling the person absent; source graph remains authoritative. |
| Leader replacement, rename or segment dissolution | Preview/apply recalculates immediately; stable IDs/history preserved for edits; explicit deletion shows affected employees. |
| Root row absent or root replacement attempted | Respect the configured root-profile exemption; reject unmarked post-import root edits. Explicit preview/Apply may replace the root, including a missing-row successor, with visible gaps and no new source observation or tenancy mutation. Updated feeds resolve reporting edges. |
| Qualified designee departure with and without tenancies | Both association work when applicable and every affected mapping exposed; invalid nominee excluded from future routing. |
| Several designees, or last designee removed | Preserve eligible peers; permit an empty optional designee list; never promote a replacement automatically. |
| Designee changes branch or no longer has rooted ancestry | Flag role eligibility separately from person absence; preview shows recipient changes. |
| Same person has several roles; leader and designee depart together | Detect all affected nominations even under invalid leadership; no hidden defect or duplicate episode. |
| Offboarding, directory exclusion or review acknowledgment precedes repair | Outstanding mapping defects persist; repairing mappings does not settle tenancy cleanup and vice versa. |
| Partial, stale, incomplete and repeated feeds; later return | No unsupported departure inference; stable episodes; unresolved absence stays open; qualified return after completed offboarding retains renewal behavior and rechecks every role. |
| Reapply/role repair, concurrent imports and accepted operations | No fresh absence/return/clocks from config-only work; stale previews rejected; frozen accepted intent/routing/history preserved. |

Use pure reconciliation/settings unit tests for eligibility and episodes; disposable PostgreSQL
tests for version/audit consistency, independent resolution and concurrent Apply; and Playwright
tests for linked departure/settings work, replacement/removal preview and resulting Organization
and Tenancies displays. Verify long identities and multi-role warnings at desktop and narrow
widths with keyboard access. D53's coverage and required-suite gates continue to apply.

## Handoff and review status

The user approved immediate preview/Apply and requested implementation of the departure extension
and required regression matrix. Pre-implementation documentation, security and UI/spec reviews
shaped this contract. Their planning notes are superseded by the implementation checkpoint below.
Existing qualified-return renewal remains intact; no alternate departure coordinator was introduced.

## Implementation checkpoint — 2 November 2026

The departure extension and required matrix are implemented and verified.
[The runtime guide and complete field/storage map](../reference/organization-mapping.md)
cover the initial CSV gate, exact preview/Apply fence, independent role health and no-observation
recalculation. All1,006backend/database/browser tests and172frontend units pass; separate unit-only
coverage is96.13% backend and97.46% frontend. Documentation, security and UI/UX reviews are clear.
The dated validation receipt (private historical evidence; not distributed)
records source scope, installed-role qualification and desktop/mobile captures. No new database
tables or privileges were needed. The local app was refreshed after backup without changing
existing rows or mappings; testing used disposable installations and synthetic data. No Git
publication or live OCI action occurred.


## Mapping editor UI refinement — 2 November 2026

Saved organization role health precedes the editor. Segment fieldsets have consistent application
form typography and space between identification fields, designee lookup and nomination lists.
Leader email is a normal email input without a dropdown indicator; after a feed, designee lookup
continues to offer employee suggestions with an explicit Add designee action.

Preview changes opens a modal with affected/unassigned counts, segment changes, proposed role
health and paginated employee impacts. Back to editing or Escape retains the draft and discards
the preview. Cancel edits on the editor separately restores saved values. Closing is disabled while
preview paging or Apply runs. Initial focus goes to the review heading; Back to editing/Escape returns focus to
the Preview changes control. Exact candidate/context binding, blockers, error handling and all
independent departure/return behavior are unchanged. No API, data model or authorization change.

## Explicit organization leader replacement — approved extension, 2 November 2026

The user approved replacing the saved organization root without SQL, redeployment or automatic
successor selection. Change organization leader unlocks the ordinary read-only field. Preview and
Apply include change_root; the browser confirms review of the replacement and reporting gaps before
Apply. The server binds that intent to the exact candidate/context, reauthorizes and recomputes under
lock. Existing pending-work and replacement segment-leader guards remain. Only the root field may
differ from source policy; all source trust, population, census and freshness settings are preserved.

The new root can be absent from the latest feed. Preview explicitly shows that absence, old/new root,
total unresolved employees and paginated ancestry/assignment/routing deltas. Apply retains the real
source graph and all associations, clocks and lifecycle evidence. The former root's manager-less row
in previously validated evidence remains a nonfatal mapping-only diagnostic; a fresh feed still
requires managers for every non-root employee. The subsequent corrected feed supplies the new root
and reporting relationships. The former root is retained as an ordinary identity and may require
its own qualified absence/association review; replacement does not perform cleanup.

The [runtime guide](../reference/organization-mapping.md#replace-the-organization-leader)
contains the59-field DTO map and named regression trace. Added unit, disposable PostgreSQL and
frontend cases cover present/missing successors, stale context, evidence/association preservation,
root-only policy permission, audit, confirmation/cancel behavior and subsequent graph repair.
Final root-replacement checks passed:1,014backend/database/browser tests,175frontend units;
independent unit-only coverage96.14%/97.51%. Documentation, security and UI/UX reviews passed.
[Manual runbook](../how-to/organization-mapping-runbook.md) and
validation receipt (private historical evidence; not distributed) record the handoff.
The earlier base-mapping receipt remains historical evidence for its own source scope. No new table,
column or production OCI mutation was introduced.

## Corrected mapping review lifecycle and provisioning guard — 2 November 2026

The approved targeted guard blocks new tenancy creation/import and joining a shared tenancy only
for a person without valid accountability. Valid means resolved ancestry plus an active segment ID
and that segment's configured accountable leader, or the exact configured root with ancestry=root.
This rule is shared by the public preview and server admission. PersonWorkflow.mapping_required
explains the omitted actions and the UI links to Repair Organization Mapping. It is not a blanket
ban on managing existing resources: cleanup, offboarding, transfer/removal and non-infrastructure
decisions retain their existing independent guards. Permanent Ignore never authorizes provisioning.

A no-longer-active LOB_MAPPING_REVIEW closes automatically only when the current stable person meets
the same rule, with resolution=mapping_corrected and retained history. Merely suppressing a diagnostic,
hiding an employee or seeing another feed is insufficient. Promotion to the actual root uses its
explicit exemption. Unrelated unmapped employees, absences and setup decisions stay open. A later
unsuppressed mapping regression creates a new episode rather than reopening or deleting old history.
Leader/designee repairs remain independent and no source edge, association or observation is invented.

Regression source covers corrected-versus-unmapped neighbors, direct API guard attempts, Ignore,
root identity/ancestry, active-ID/leader matching, cleanup availability, independent sticky absence
and setup work, and recurrence. Final aggregate/browser qualification passed: 1,041 backend/database/browser tests and 177 frontend
units, with 96.18%/97.52% separate unit-only coverage. No table/migration/audit-family change is required; the mapping DTOs stay at59 fields.
The [runtime workflow guide](../reference/organization-workflows.md#mapping-review-repair-and-targeted-provisioning-guard)
records the field and resolution mapping without treating earlier receipt results as this fix's final evidence.

## Latest-feed information and historical segment labels — 2 November 2026

Organization drift keeps its durable Actionable queue and presents Informational & history beside
it. By default this tab includes the latest applied feed's change records and still-open source
warnings, including mapping/reapply changes tied to that feed. Completed/ignored actionable reviews,
resolved source warnings and earlier-feed changes are excluded in that default scope. Show all history
switches to the existing full-history API selection and exposes all those retained records. The independent
informational count is computed before search/paging and overlaps full history; it is not an extra
set of outstanding tasks.

Link information to org_version.feed_id matching the applied head's source snapshot, not to event
clock cutoffs or only the latest recalculated version. A later failed/staged import does not displace
the applied feed. Historical metadata retains lob_id, with read-derived lob_name from the review's
own configuration for after values and its base-version configuration for before values. Later mapping
renames/removal do not rewrite those labels or source evidence. Current role-warning labels remain
separate current-head context. The UI shows selected readable changes, not raw configuration JSON.

This read refinement adds the informational query choice and informational_count to the existing
review contracts; it introduces no table, new stored category or separate history service. Mapping
Apply, review lifecycle, targeted onboarding guard and independent cleanup remain unchanged. Existing
organization-leader helper text is aligned with the mapping action row without changing its meaning.
Final validation passed: 1,043 backend/database/browser tests and 177 frontend unit tests; backend/frontend unit coverage is 96.186%/97.53%. [Exact query/count/label authority](../reference/organization-workflows.md#latest-applied-feed-information-and-readable-segment-changes).

## Root tenancy exemption is separate from root offboarding — 2 November 2026

The configured root may legitimately require no tenancy. With no associations or pending work,
No tenancy required records the same managed-directory exemption as for other employees: setup
closes and repeated feeds do not reopen it. The source graph, root configuration, segment mappings
and descendants remain unchanged. Exemption does not nominate a successor, delete the root identity,
change OCI access or remove the reporting boundary.

Include excluded profiles makes the retained exempt root inspectable; a source-present unassociated
root can be explicitly Re-onboarded later. Actual root offboarding and identity merge remain blocked
in both available choices and server guards. Root identity and app-administrator login are different
roles; this organization decision changes no application grants.

This correction adds no contract/storage field, table, migration or authority. The manual successor
exercise now checks No tenancy required after the corrected feed, continued reporting health and
no repeated-feed onboarding. Validation qualified the full run’s 1,044 passing cases plus a passing affected HTTPS browser rerun (2 tests) after correcting test-only navigation/locator mistakes. Separate unit gates passed: 866 backend units at96.1874% and177 frontend units at97.53%. The initial browser failures are retained as investigation evidence, not reported as passing full-run receipts. The earlier root-replacement evidence is not this fix's final result.
[Current workflow boundary](../reference/organization-workflows.md#organization-root-without-a-tenancy).

## Optional full-history scope in the information tab — 2 November 2026

The user requested access to earlier organization history without changing the latest-feed default.
Keep Informational & history as the tab's stable label and offer Show all history only within it.
Unchecked maps to the existing informational query category; checked maps to history, including older
changes, resolved source warnings and completed/ignored actionable decisions. Match the badge to the
selected informational_count/history_count; neither count becomes a task-assignment metric.

Reset paging to1 when the checkbox changes while retaining search and sort/direction/page size. Keep
its choice across tab switches only while the page remains mounted; no durable preference is added.
Actionable reviews, historical label provenance, source scope, indefinite retention and all command
guards remain unchanged. This is a frontend use of existing APIs, not a new backend contract/table,
permission or dependency. Unit/browser validation passed: 178 frontend units at97.54% coverage and 2 real HTTPS/browser tests. The [runtime guide](../reference/organization-workflows.md#optional-full-history-in-the-information-tab)
records the exact current flow and count semantics.
