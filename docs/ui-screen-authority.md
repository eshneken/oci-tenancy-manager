# UI screen authority and shared navigation

21 October 2026 | D34 accepted | Design source map, not a second application

The current React application and linked implementation references are authoritative for implemented
screen behavior. The retained prototype characterizes earlier approved business semantics; static
walkthroughs illustrate their declared design subset and must not override working application
contracts. Preserve the distinction between implementation, historical reference and future OCI
qualification when updating page bodies or navigation.

## Selected visual authority — D57

28 October 2026. The user chose **original A / Field Console (left)** after comparing rounded
A2. [DESIGN.md](../DESIGN.md) supplies the current navy/cobalt/cool-light visual system and crisp
3px geometry. The source table below continues to identify approved fields, behavior and flows;
older teal screens remain interaction references while their appearance is aligned. Keep the
retained prototype semantics as characterization evidence; current screen fields follow the implemented contracts.

## Screen authority

| Area | Authoritative reference | Treatment in engineering walkthroughs |
|---|---|---|
| Application sign-in/session | [Local application guide](reference/local-application.md), [React sign-in](../frontend/src/SignIn.tsx), [session shell](../frontend/src/App.tsx) | Implemented password/TOTP and session/logout flow in original-A styling; current validation is recorded separately, not inferred from static walkthroughs |
| Application administrators | [React directory](../frontend/src/Administrators.tsx), [administrator field map](reference/administrators.md), [actual HTTP projection](reference/local-application.md#implemented-http-and-model-boundary) | Implemented server search/sort/pagination, statistics and ordinary-grant revocation; protected recovery is operator-managed, add/regrant remain unavailable |
| Organization directory | [React directory](../frontend/src/Organization.tsx), [implemented screen contract](reference/organization-screens.md) | Authenticated CSV intake, mapped directory and stable-person actions; preserve source/profile/absence guards. The prototype is historical characterization. |
| Organization drift | [React review queue](../frontend/src/OrganizationReviews.tsx), [review/workflow guide](reference/organization-workflows.md) | Durable actionable reviews plus latest-feed information/optional full history; no fabricated successful empty state. |
| Tenancies dashboard | [React inventory/detail](../frontend/src/Tenancies.tsx), [workflow/model guide](reference/organization-workflows.md) | Registered simulated child inventory, clickable owner/member relationships, baseline/check status and scoped actions. Financial columns remain proposed until their source is qualified. |
| Configuration | [Baseline guide](reference/baseline-authoring.md), [overrides](reference/tenancy-overrides.md), [updates](reference/configuration-updates.md), [drift checks](reference/configuration-drift.md) | Implemented local authoring/publication, frozen assignments, staged updates and read-only check visibility; real OCI grammar/binding/access qualification remains separate. |
| Financial detail | [Selected-tenancy walkthrough](walkthroughs/financial-walkthrough.html#tenancy?tenancy=jordan), [chapter14](engineering-design/14-financial-journeys.md) | D41–D43 source/cadence/status remain binding; D44 removes the separate financial list. Detail and existing configuration flow remain; D46 approves the combined dashboard without declaring other layouts or real-provider behavior fully qualified |
| Human access | [Human access walkthrough](walkthroughs/human-access-walkthrough.html), [chapter13](engineering-design/13-local-support-and-emergency-access.md), D40 UI review (private historical evidence; not distributed) | D40 single Administrator access flow for the persistent recovery password; Required users is the other access tab. Temporary named support is deferred; no secret or provider qualification |
| Required access | [Access walkthrough](walkthroughs/access-walkthrough.html), [chapter12](engineering-design/12-access-health-and-repair.md) | Inert observation/repair examples; no MFA, provider or full permission qualification implied |
| Recorded Operations | [Implemented React list/detail](../frontend/src/Operations.tsx), [API/UI field guide](reference/operations.md) | Activity/history visibility; current-intent steps and recent50 events. A separate explicit simulator form accepts new reads; no generic retry or remediation inbox |
| Audit History | [React history directory](../frontend/src/AuditHistory.tsx), [field/actor/source guide](reference/audit-history.md) | Safe immutable events with categories/search/UTC dates/paging and filtered CSV export; worker/operator/unverified-attempt interpretation; no raw JSON or record editing |
| Onboarding and lifecycle actions | [React setup](../frontend/src/Onboarding.tsx), [guided onboarding](reference/tenancy-onboarding.md), [deletion](reference/tenancy-deletion.md) | Durable queued local simulation, manual handoff and guarded continuation; accepted work is distinct from verified effects. Static walkthroughs also preserve future provider design. |

Older wireframes, static captures and decks remain historical evidence. A new illustrative screen
must explicitly identify its scope and cannot silently replace an approved reference. The retained
prototype remains separate from the current application.

## Accepted tenancy information, consolidated by D44

The user explicitly retained **Assigned baseline** and **Configuration issues**. D44 places these
inside the combined dashboard’s Configuration column rather than requiring separate columns. Preserve its existing fields, owner/member counts and
search/filter/sort/pagination. The assigned version comes from that tenancy's stored assignment,
not the current-for-new default; pending application/verification must remain visibly distinct.
A configuration-issue indicator has accessible text/counts and opens the exact issue, or a
filtered issue list when several apply. Confirmed drift and unable-to-verify checks retain distinct
meanings. These additions belong in the production design; they do not imply that the local
prototype has acquired live OCI assignments or observations.

## One menu structure for current design walkthroughs

| Parent | Submenu | Destination/status |
|---|---|---|
| Tenancies | — | Single combined dashboard at financial-walkthrough.html#tenancies; legacy list links alias it |
| Organization | Organization drift | Production Organization directory/upload and current drift are enabled; static design menus remain non-clickable context |
| Configuration | [Baseline guide](reference/baseline-authoring.md), [overrides](reference/tenancy-overrides.md), [updates](reference/configuration-updates.md), [drift checks](reference/configuration-drift.md) | Implemented local authoring/publication, frozen assignments, staged updates and read-only check visibility; real OCI grammar/binding/access qualification remains separate. |
| Configuration | [Baseline guide](reference/baseline-authoring.md), [overrides](reference/tenancy-overrides.md), [updates](reference/configuration-updates.md), [drift checks](reference/configuration-drift.md) | Implemented local authoring/publication, frozen assignments, staged updates and read-only check visibility; real OCI grammar/binding/access qualification remains separate. |
| Activity & history | Operations | Recorded operation visibility/troubleshooting; existing static walkthrough destination, no inbox/action count |
| Activity & history | Audit History | Inert label until a static destination exists; no invented href/page |
| Application settings | Administrators | Inert static label; the real application has its separately implemented administrator screen |

The current engineering HTML walkthroughs share
[design-navigation.js](walkthroughs/design-navigation.js) and
[design-navigation.css](walkthroughs/design-navigation.css). These are the common
menu manifest/renderer and menu styling for this design package. Keep ordering, grouping, labels,
active context, target sizes, focus and responsive treatment consistent. Other reviewed workflow
controls retain their own page-specific behavior. This is a small design-shell component, not the
production React navigation implementation.

Organization and Organization drift are plain contextual labels, not anchors, buttons or focusable
pseudo-links. Do not navigate from configuration to an unapproved organization substitute. Old direct
organization-route aliases may display an explicit placeholder notice only; they must not imply live
data, zero pending work or approval of a new layout. Other menu links open existing design destinations.

## Consistency rules for further design

- Reuse the approved prototype's directory/review components and states when integrating them.
  Preserve actionable versus informational/history separation, sorting, filtering, paging,
  associations, review actions and truthful loading/error/empty states.
- Reuse the tokens and interaction patterns in [DESIGN.md](../DESIGN.md) across new pages. Keep
  control heights/alignment, typography, spacing, status language, focus and responsive rules aligned.
- Update the shared current navigation once rather than copying menu variants into separate mockups.
  Keep historical checkpoints unchanged. Archive shared assets with future snapshots so archived
  pages do not depend on later menu changes.
- Review shared-shell changes across all current walkthroughs and representative page states. Page-body
  approval requires comparison with its authority above, not just a successful navigation check.
- Distinguish confirmed configuration drift from failed checks, baseline conflict reviews and
  organizational review types. A common word in menu labels does not merge these workflows.

## Current validation evidence

The D34 review (private historical evidence; not distributed) and
browser receipt (private historical evidence; not distributed) cover
20 targeted navigation/workflow checks and20 representative shared-menu/viewport combinations.
Desktop, tablet and narrow mobile navigation preserve the agreed hierarchy and existing controls.
Same-document links preserve local draft/publication state; cross-document examples remain separate
in-memory demonstrations. No prototype, database or OCI state was changed.

## Field-coverage gate for every design slice

Apply this gate to narrative, current renders/walkthroughs, endpoint/facade contracts and data models
together before a design checkpoint is presented as reviewed:

1. Inventory each business input, displayed value, status, count, timestamp, link target and action
   consequence. Include validation/error/loading/unknown/partial states, not only the happy path.
2. Map each item to a named canonical field, a reproducible derived query, immutable intent/evidence,
   transient UI state or an authorized secret-only response. Name the typed properties inside JSON;
   “configuration document” or “metadata” alone is not a field contract.
3. Trace a worked record through acceptance, facade input, provider identity, observation and UI.
   Record every provider identifier needed for later verification; distinguish requested, desired,
   observed and verified values and their dates. Mark proposals and qualification limits explicitly.
4. Check the unit of each summary. A tenancy count is not an association count, and an aggregate
   view does not turn several scoped checks into one check or one passing result.
5. Reconcile prose, field guide and abbreviated ER names. Any new persisted field/table must have
   a lifetime, owner, types/nullability and query/guard purpose. Existing approved pages remain the
   authority; design placeholders do not replace them.
6. Use the standing documentation and UI/UX reviews, fix material findings, and recheck final source
   and browser states. Save bounded evidence and differentiate artifact checks from executed DB/OCI
   qualification. Carry open product decisions forward without silently choosing for the user.

This is the standing review process requested on 21 October 2026; it does not authorize a new
automation, independent chat or scheduled reviewer.

The first C4 [Required access walkthrough](walkthroughs/access-walkthrough.html#missing)
has a separate UI review (private historical evidence; not distributed) and
[field-by-field contract](engineering-design/12-access-health-and-repair.md#field-by-field-contract).
It is a proposed access page reached from its matching example tenancy, not a new organization
page or replacement inventory. Its 17 interaction and 16 layout checks validate inert UI behavior only.

## D35 protected-access policy review

D35 A keeps the single OTM policy and makes authored versus required statement sources visible in
the current configuration editor, overrides, conflict review, tenancy detail and drift comparisons.
The D35 review (private historical evidence; not distributed) records
interaction/layout evidence and limits; the [explicit field contract](engineering-design/10-configuration-data-model.md#d35-required-policy-manifest-and-rendered-evidence)
names manifest, renderer and final statement/provenance storage. A global baseline’s generated
section is an example, not persisted tenancy-specific content or a replacement baseline source.

Run `uv run python scripts/check_design_docs.py` before future checkpoints. It checks local design
links/anchors, explicit model/ER fields and table inventory, plus the product-spec header, numbered
sections and acceptance-criterion integrity. It complements the narrative/UI review; passing does
not prove that every semantic field is correct or qualify any provider behavior.


## D38: access flow presentation

The current human-access and required-access HTML now model product pages/dialogs. Their scenario
controls are collapsed demo aids. [Chapter13](engineering-design/13-local-support-and-emergency-access.md#d38-accepted-product-screens-and-separate-design-narrative)
contains the flow and field contracts; the current review (private historical evidence; not distributed)
covers this layout replacement. Earlier D36/D37 screenshots remain historical. This changes no
organization prototype authority, menu destination or OCI/credential state.

## D44: one authoritative Tenancies dashboard

24 October 2026. The five-column Tenancies design consolidates Tenancy, Owner/LOB, Configuration,
Actual/Budget and Forecast; do not create parallel Inventory/Costs lists. Canonical menu/list target
is `financial-walkthrough.html#tenancies`. Legacy financial `#costs` and configuration `#tenancies`
resolve to this same list. Existing prototype behavior remains the foundation and the actual app is
unchanged; D46 records final D45 dashboard acceptance, while historical receipts retain their recorded source/version scope.

Preserve owner-inclusive distinct association counts, identity links, filters, paging and exact issue/
override targets. OTM retrieval-time information must support hover, focus and tap; D45 excludes OCI computation time from this list tooltip while retaining internal qualification and technical detail. Important financial data
errors remain visible, while independent D45 per-value spend highlights retain separate meaning. All fields are existing
canonical/derived values; no model/schema expansion or historical-reporting feature is implied.

D44 validation: review and captures (private historical evidence; not distributed) record 29 journeys and 84 responsive/popup checks, plus independent source/screenshot review. No production or provider validation is claimed.

## D45: independent per-value status, without duplicate list badges

Accepted 25 October 2026. Retain the D44 five-column dashboard. Actual above qualified observed budget is red; forecast above that same observed budget is independently amber, even when actual is already red. Qualified below-budget values may be green; exact-at-budget and unqualified/unavailable values remain neutral. Number backgrounds replace redundant second-row spend badges and the dashboard overall-warning badge. Per-value screen-reader-only status and hover titles retain textual meaning. Detail may retain its highest-severity summary and independent values.

Keep important data degradation and pending-budget text visible. The hover/focus/tap information control shows OTM retrieval time, optionally status/cycle, without OCI calculation time. The latter remains an internal source/model and staleness field and may appear in technical detail. This refines D43 presentation only; no data qualification, schema or cost-automation/history scope changes. D45 final design/UI review (private historical evidence; not distributed) passes 38 browser journeys and 84 responsive/popup checks with independent source/screenshot review. D46 records user visual acceptance of the final D45 dashboard; real-provider qualification remains separate.

## D46: final combined dashboard approved — 25 October 2026

The user approved the final D45 unified five-column Tenancies dashboard, explicitly including separate Actual and Budget sort controls within their shared visual column. This closes user layout acceptance for this dashboard; it does not declare the entire engineering design complete or qualify real OCI behavior. D45 independent numeric highlights, retrieval-only list tooltip, visible degradation/pending labels and all D41–D42 source/cadence rules remain unchanged.

The shared Actual/Budget visual header has two independently operable sort controls: Actual uses `sort=actual` mapped to `actual_spend`; Budget uses `sort=budget` mapped to `observed_budget_amount`, never the desired/pending amount. One active `(sort, direction)` pair is retained, with `direction=asc|desc` (the walkthrough uses internal `1|-1`). Selecting a different key starts ascending; activating the same key toggles direction. Missing/unavailable values sort last in both directions, never as zero. A changed sort starts page1 while preserving search, LOB filter and page size; subsequent paging and detail/back navigation preserve the selected sort/direction and valid query/page context. Accessible control labels and the header sort state identify the active key and direction.

Per-value qualification remains independent: an available, qualified actual below observed budget may be green even when forecast is unavailable. Keep Forecast unavailable visible; green actual does not assert that projected spend or the whole tenancy's financial health is healthy. No schema, provider operation, historical cost reporting or automatic cost action is added.

## Accepted activity/history grouping and simulation copy

30 October 2026: daily navigation remains Tenancies, Organization → Organization drift and
Configuration → Baselines / Configuration drift. Separate **Activity & history** contains Operations
and Audit History, followed by **Application settings** → Administrators. The shared static renderer
propagates that grouping across current engineering pages; the style dashboard reflects the same
labels without an Operations task-count badge. Historical captures/reference images and prototype
business behavior remain unchanged.

Operations is visibility/troubleshooting. Contextual remediation belongs to the higher-level tenancy,
organization/configuration or access screen, with existing operation evidence linked as useful.
No generic Retry action is approved. Persisted `needs_attention` remains a state, not proof a user
has an assigned action. The current simulated result says **“Simulation ended with an issue. No action
is required.”** Apply that message only to the simulated issue outcome; future real create/access/
cleanup examples can still require safely scoped contextual remediation.

[Audit History's exact field/schema authority](reference/audit-history.md) now maps its eight
query, nine entry and five directory fields to existing immutable `audit_event` and derived public
values. Current scope, search/category and actor checks require no second history store, raw JSON
view or record editing. The later Audit History date/export slice adds UTC half-open date bounds
and an authenticated, audited CSV export of all matching rows within its explicit 10,000-event limit. Its static menu
label has no link because no static audit destination exists. The current future-lifecycle Operations
walkthrough remains inert design evidence and is not a live remediation inbox.


### Accepted manual-upload source time

30 October2026. The production upload screen will require the administrator to confirm an
**Organization data as of** date/time, defaulting to current server UTC. This is an explicit
administrator attestation, not a timestamp inferred from a filename, CSV cell, browser clock or
receipt time. It maps to `Envelope.captured_at`, `org_feed.captured_at` and the revision source
capture time. `received_at` remains the independent server receipt clock. Normal scope, freshness,
census authority/completeness, incoming-profile coverage and source-order checks still apply;
the field does not authorize automatic deletion or turn partial data into a complete census.
The four-column CSV format is unchanged. This design decision is captured now; the upload UI
remains the next implementation slice.


## Production Organization integration — 30 October 2026

The [implemented directory and drift](../frontend/src/Organization.tsx) now use production snapshots
and authenticated CSV/as-of upload. [The field/scope guide](reference/organization-screens.md)
records all public fields and limits. This is an incremental port of the approved prototype interaction:
tenancy associations/actions, permanent-ignore/closure and full informational history are not yet
connected. The current screen labels that boundary rather than reporting fake success. Preserve the
prototype as authority for those remaining interactions. Organization and Organization drift are active
in the application navigation; the tenancy/configuration entries remain unavailable.


The production Organization directory optionally shows a local-only **Reset test organization**
instructions dialog. It exposes the fixed operator command and a read-only Refresh action; it does
not add a destructive browser workflow or replace the prototype's separate workspace-reset behavior.

## In-progress production organization workflow parity

The [accepted parity checkpoint](history/organization-parity-checkpoint.md) is being implemented through
[the current field/source guide](reference/organization-workflows.md). Organization drift now
has durable Actionable/Informational & history tabs, with latest-feed scope by default and a Show all history checkbox; person dialogs show full registered associations and exact
context; Tenancies supplies a basic simulated inventory/detail entry point. Simulation labels and
operation links distinguish accepted from verified effects. No prototype synchronous-success/actor
bypass, generic Operations Retry or real provider completion is implied. Current runtime screens
implement a subset of the full approved configuration/finance dashboard, whose field authority is
unchanged. Independent whole-flow responsive/UI review and final test evidence are pending.

## Guided create/import runtime — 31 October2026

[The implemented setup panel](../frontend/src/Onboarding.tsx) is the interactive local authority for the guided simulated onboarding subset. It appears in pending tenancy detail and guided operation detail. Manual instructions, handoff fields, exact cleanup review and six compact checks are persisted and responsive; engineering narrative remains in [the field guide](reference/tenancy-onboarding.md). Approved static onboarding screens still describe later provider/baseline capabilities, not an alternative running UI.

## Tenancy detail deletion — 31 October2026

[DeleteTenancy](../frontend/src/DeleteTenancy.tsx) is the current local runtime action for whole-tenancy impact review on both individual and shared child detail. The wrapping person list shows other association counts/directory outcomes; one explicit confirmation follows manager/shared warnings. It reuses shared native dialog/checkbox controls and links accepted work to Operations. This does not change shared-member removal or introduce real OCI effects.

## Create request metadata and completion — 31 October2026

PersonActions Create now requires Requested tenancy name and Home region, with no guessed defaults. Region choices come from the server facade; the local list is explicitly simulated. Import does not ask for either. The successful Operation notice offers a direct Open tenancy link from its server-resolved registered UUID; its embedded onboarding panel suppresses a duplicate link. Existing accepted history is retained.

### OCI manual handoff guidance — 31 October 2026

The implemented setup panel and static activation sample now use documentation-backed OCI steps.
The checklist identifies the child Console, activation mailbox, three create/two import OCIDs,
bootstrap username, separate OCI group/domain-role grants and public-only key upload. Import links
created-child transfer approval separately from invited-child removal. [The operator procedure](reference/tenancy-onboarding.md#oci-console-handoff-instructions)
records Oracle sources and qualification limits. Simulation explicitly tells administrators to skip
real OCI actions and use the sample handoff. No new screen input or data-model field was added.

### Import target continuity — 2 November 2026

Import setup displays the OCID selected in the original modal read-only and asks only for bootstrap
user OCID. Create retains editable tenancy and activation-administrator inputs. The server still
rejects retargeting regardless of browser controls. Local registry name-conflict feedback retains
the create form/type/region and focuses the name field. OCI-wide rejection/correction is separately
specified future adapter work; it is not a behavior claimed by this simulator.

### Organization Mapping settings implementation — 2 November 2026

The application Organization Mapping page under Application Settings is authoritative for typed
initial setup, industry segment CRUD, independent role health and immediate preview/Apply.
Organization empty state/API require saved settings before first upload. Role drift links to the
matching segment; employee association actions remain independent. [The runtime field guide](reference/organization-mapping.md)
records the contract, data authorities and current validation boundary. Preview is invalidated on
edits, and uncertain Apply requires refreshing saved state while preserving the draft.


### Organization Mapping UI refinement — 2 November 2026

The production page places saved role health before the editor and uses shared form typography.
Preview is a modal review with summary counts, segment changes, proposed role health and paginated
employee impacts. Back to editing/Escape preserves the draft; Cancel edits restores saved values.
The leader field is a plain email input; designee suggestions remain an explicit lookup/add flow.
The modal's heading receives initial focus; Back to editing/Escape returns focus to Preview changes. This
refinement does not replace Organization or Organization drift layouts or change their behavior.

### Explicit organization leader replacement — 2 November 2026

Organization Mapping keeps the root read-only in ordinary post-import editing and adds the explicit
Change organization leader action. Its modal preview shows old/new root, warns when the replacement
has no row in the latest feed, reports all unresolved employees and exposes paginated before/after
ancestry and assignment changes. Review confirmation is required in the browser before Apply when
the saved root changes. Back to editing/Escape retains the draft; Cancel edits restores the saved root
and normal field lock. The API separately requires and binds change_root intent and current authority.

A missing new-root row can be deliberately applied before a corrected feed arrives; this never invents
reporting edges, a successor or tenancy reassignment. Updated source data resolves the displayed gaps.
The [runtime guide](reference/organization-mapping.md#replace-the-organization-leader) is the
current flow/field authority. This extension supersedes any earlier root-lock-only description; it
adds no table or OCI action. Root-replacement tests and independent documentation/security/UI reviews passed; see the manual
[runbook](how-to/organization-mapping-runbook.md) and
receipt (private historical evidence; not distributed).

### Audit History recorded change details — 2 November 2026

Audit History's Details column replaces the former outcome-only column. Organization events display
a readable summary; native View changes (N) disclosure shows selected recorded old/new root emails,
segment names, leader emails and designee lists. Added/removed mappings, unchanged Apply and legacy
unrecorded details are distinguished. The disclosure uses existing public row fields rather than a
raw JSON endpoint. Other categories retain closed outcome-code fallback or a dash.

The twelve-field UI/CSV projection derives these values from immutable typed evidence; it never
reconstructs old settings from today's configuration. Offboarding copy distinguishes requested work
from a completed decision using its receipt; missing proof remains neutral. Actor attribution and
current administrator labels remain separate. Search still covers actor/administrator names and
IDs, not the new change text or nomination emails. The CSV adds summary and a JSON-array changes
column while retaining scope/date filters, row limit, formula protection and audited preparation.

The [runtime guide](reference/audit-history.md#what-did-the-administrator-change)
is the current field/UI authority. This adds no audit mutation, table, permission or remediation
control. Selected nonsecret historical mapping values are visible to current workspace administrators;
full feeds/configuration/credentials remain private. Validation passed, including keyboard disclosure, narrow-screen Details visibility and historical
CSV parity; see the receipt (private historical evidence; not distributed).


### Mapping repair and provisioning eligibility — 2 November 2026

PersonWorkflow.mapping_required derives from the current stable identity, resolved branch and active
configured segment/leader, with the exact configured-root exemption. The dialog shows explicit repair
guidance and a link to Organization Mapping. Create/import/join are omitted until repair; offboarding,
delete/remove/transfer and other decisions retain their existing independent guards. Server admission
uses the same eligibility boundary. A corrected mapping review automatically moves to history rather
than requiring each downstream employee to be acknowledged individually. Counts/lists are invalidated
after Apply; source fixes also reconcile conditions. Unmapped exceptions and separate absence/setup
reviews remain. [The runtime guide](reference/organization-workflows.md#mapping-review-repair-and-targeted-provisioning-guard)
records the one new derived field and resolution semantics; there is no new table or reset requirement.

### Latest applied feed information — 2 November 2026

Organization drift presents Actionable and Informational & history. The latter defaults to change
records and still-open source warnings tied to the latest applied feed. Completed actionable work,
resolved source warnings and earlier-feed records stay out of that default scope. Show all history
exposes those retained records through the existing full-history API option. Audit History remains administrative audit,
not a replacement rendering of every organizational snapshot. Sorting/search/paging remain available;
the information badge counts its whole selection independently of search and overlaps full history.

The selection follows organization-version feed provenance, including all recalculations of the same
applied source. It is not a timestamp range, a latest-upload list or only the last mapping revision.
The metadata disclosure displays readable historical industry-segment labels resolved from the review
and base-version configurations, while stored lob_id and ID-based comparisons remain intact. Unknown
labels stay explicit; later mapping changes do not invent past names. Open nomination-warning labels
continue to reflect current-head context separately.

The [runtime contract/source map](reference/organization-workflows.md#latest-applied-feed-information-and-readable-segment-changes)
is the current screen authority. Organization-leader helper copy uses the existing mapping action-row
alignment. These read/display changes add no table, mutation, workflow action or raw JSON interface.
Final validation passed: 1,043 backend/database/browser tests, 177 frontend units, and a final focused HTTPS browser check. Separate unit coverage is 96.186% backend and 97.53% frontend.

### Show all organization history — 2 November 2026

Informational & history is the stable tab label. Its Show all history checkbox defaults unchecked,
selecting latest-applied-feed information; checked selects all retained changes, source warnings
(including resolved warnings) and completed/ignored actionable decisions across older feeds. The
badge follows the selection: informational_count or history_count. Actionable remains its separate
open-work queue, and the checkbox appears only inside the information tab.

Toggling scope resets page1 and preserves search, sort/direction and page size. The choice survives
switching between tabs until the page unmounts; it is not a saved preference across reload/navigation.
No raw JSON, mutation or new backend/schema/dependency is introduced. Existing historical segment
names and source-provenance rules still apply to latest-feed scope. See the [runtime flow](reference/organization-workflows.md#optional-full-history-in-the-information-tab).
Final validation passed: 178 frontend units at97.54% complete-source line coverage and 2 real HTTPS/browser tests against disposable PostgreSQL.

### Default landing and direct feature reload — 2 November 2026

Tenancies is the default after sign-in from `/` or `/login`, and those landing URLs also redirect
an already authenticated user to `/tenancies`. The application brand opens Tenancies. If sign-in
begins from an explicit valid feature path, successful sign-in preserves that path. This is URL
navigation, not a persistent last-tab preference.

The seven implemented feature entry paths support direct entry and full reload: `/tenancies`,
`/organization`, `/organization/drift`, `/organization-mapping`, `/administrators`, `/operations` and
`/audit-history`. Existing operation/tenancy detail routes remain. The missing Organization Mapping
shell/allowlist entry is added explicitly; no generic fallback route or public data endpoint is added.
Shell assets are public nonsecret presentation; all API data and writes retain their normal session,
authorization, scope and browser guards.

Full reload preserves the requested page and reads current protected data, but recreates in-memory
controls/cache. Filters, pagination, draft inputs and history-checkbox state reset unless specifically
encoded in the URL; no new durable page-state mechanism is introduced. The [runtime route map](reference/organization-workflows.md#direct-navigation-sign-in-and-full-reload)
records the precise entry points and limits. HTTP/React and seven-page browser validation passed: 866 backend units, 179 frontend units and
two real HTTPS/browser tests; unit coverage remains above95% for each application layer.

### Organization drift and Operations navigation counts — 2 November 2026

The authenticated navigation badges summarize existing scoped reads: Organization drift counts open
actionable reviews; Operations counts waiting/needs_attention organization workflows with a matching
pending person and a supported handoff, review, retry or safe cancellation. Read-only inspection
diagnostics and unsupported/orphaned work do not count. Counts remain workspace-wide, independently
of current search/page filters. Queued/running and terminal operations do not
contribute to the Operations badge. It remains visibility/troubleshooting, not assigned work or a new
retry inbox; read-only simulation issues keep their existing no-action-required guidance.

Known zero hides the visual badge. Loading or an unavailable first read never fabricates zero; after
a failed refresh, a retained value is described as last known. Link names remain Organization drift
and Operations, with count/status provided separately by aria-describedby and a visual-number tooltip.
The component shares existing authenticated cache keys and refreshes on every ordinary menu navigation
(including the same path) and browser Back/Forward, with a5-second fallback plus normal focus/invalidations.
It is cleared with other private data on logout/expiry. No persistent
notification service, configurable poll setting or delivery-timing guarantee is added.

OperationDirectory adds only read-derived attention_count (nonnegative, default0); no table/migration
or operation state changes. The [count and response source map](reference/organization-workflows.md#navigation-counts-for-organization-drift-and-operations)
is authoritative for this addition. Validation passed: 1,047 backend/database/browser tests and 184 frontend unit tests, with separate backend/frontend unit coverage of96.1896%/97.57%.

### Navigation refresh and shared native pickers — 2 November 2026

Navigation counts refetch on each same-app navigation revision, including reselecting a menu item and
Back/Forward, without remounting the sidebar. The5-second fallback supersedes the original30-second
badge interval; session checking retains its separate policy. Existing shared invalidations remain.
Observed onboarding state/phase transitions trigger Operations list/detail refresh, and successful
CSV upload uses the shared organization refresh for related review/mapping/inventory/history reads.
These are read requests, not new server mutations or a realtime notification guarantee; stale/failure
and current-authority behavior remain intact.

The shared Select remains a native control. Supported base-select pickers size to content with a
viewport maximum rather than the field's width as a cap; short state/category filter fields have a
shared13rem minimum. Short menu labels stay one line where tested, while long options remain bounded
and scrollable. Unsupported/forced-colors environments retain native fallback. This does not add a
custom JavaScript combobox or dependency.

The source inventory covers19 shared Select uses. Actual-picker regression checks visit visible
enabled controls on all seven feature pages and workflow modal states at1280/900/768/390/320px,
including option bounds/short-label height, mouse opening, Escape focus/value retention and keyboard
Space opening. This describes tested states rather than every conditional menu or OS-native renderer.
The [runtime refresh/picker scope](reference/organization-workflows.md#refresh-counts-on-navigation-and-observed-workflow-progress)
and [UI review policy](ui-ux-review-policy.md) remain authoritative. Final validation passed: 187 frontend units at97.58% coverage, 8 real HTTPS/database/worker integration cases and 30 isolated picker-position cases. Previous receipts retain their own scope. No backend, table,
contract, dependency or configurable polling setting is introduced.

## P3.1 Configuration draft screen — 2 November 2026

[React baseline editor](../frontend/src/Baselines.tsx) and the
[implemented field/behavior map](reference/baseline-authoring.md) define the current
`/configuration` screen. One editable draft appears in a table; New baseline/Open draft opens the
form. One multiline text box collects the policy block and another collects the quota block. Each
nonempty line is one statement; blank lines are ignored at explicit Save. LF, CRLF and CR separators
are accepted, preserving other text and statement order in the existing JSON arrays. The form also
edits a positive whole-unit monthly amount, proposed currency and static OTM tag defaults.
Integral stored values such as250.0000display as250; fractional legacy values are never silently
rounded and require explicit correction before Save. Read/history precision stays unchanged. Cancel discards local
edits; save records typed before/after audit. Stale revisions retain edits and require explicit reload;
controls lock during that reload. Opening/closing the editor preserves meaningful keyboard focus.

At the historical P3.1 checkpoint, the broader walkthrough described later publication, overrides and rollout. No Publish,
current-for-new, assignment, apply or drift button is exposed by this slice. Current tenancy and
organization screens retain their approved behavior. Source and browser validation are linked from
[development progress](history/development-progress.md).


Statement-count authoring bound, 2 November 2026: each policy block and quota block independently
accepts up to50complete statements (formerly20), with2,000characters per statement unchanged.
The UI remains one newline-separated editor per category. The browser allows105,000raw characters
per block; authenticated JSON saves remain stream-bounded at2MiB. Stored arrays, field shapes,
version/hash format and whole-unit budget behavior are unchanged; no SQL migration is required.


## P3.2a published baseline history — 2 November 2026

[Baseline history and read-only detail](../frontend/src/BaselineHistory.tsx), the existing editor and
[implemented field map](reference/baseline-authoring.md) now govern the implemented Configuration
subset. The table includes the sole draft and published versions; published history pages use
10/25/50 versions, with an independent **Latest published** label. Created/published UTC and frozen
publisher name are truthful to their stored clocks. Publish opens a bounded, scrollable native
confirmation dialog with initial heading focus; Cancel/Escape dismiss before dispatch. The exact
saved version/revision is published after local simulated structure and USD-profile checks.

Published detail is read-only, supports selectable statement blocks and a previous-version link,
and states that no OCI validation or application occurred. New baseline copies the latest published
recipe and records its parent, fenced by the server against concurrent publication. Narrow layouts
stack tag key/value pairs and keep compact status text on one line within table scrolling. Failures
preserve safe retry/refresh guidance; stale drafts require reload. No current-for-new pointer,
assignment counts, overrides, rollout or provider actions are exposed in this checkpoint.


## Latest-only baseline default — 3 November 2026

Latest published is automatically the default for every new create/import. Published history rows
have View version only; there is no Use for new or older-default choice. Publishing makes the saved
recipe immutable and automatically affects future admissions; drafts do not affect them. Older
versions remain view-only and may appear as frozen pins on operations already underway.

Create/import shows one read-only latest-version link; without a publication it links to Publish a
baseline and blocks only those actions. Onboarding and tenancy detail retain their original pin
through later publications, with explicit simulation guidance. No baseline application is claimed.
This supersedes the manual-default behavior introduced at the historical P3.2b checkpoint.

## Baseline update and return navigation — 3 November 2026

The live `ConfigurationRollout` component extends the approved Configuration and active-tenancy
screens. Configuration starts a complete eligible-fleet update; tenancy detail starts a single-child
update. Both obtain a fresh confirmation with the target version, ready count and complete blocker
list. No batch starts until every exception is cleared. Read-only recipe inspection stays inside the
same dialog. Individual confirmation returns focus to progress; fleet confirmation opens persistent
Configuration progress. Per-child results and supported retry controls live there; Operations links
back to that work rather than offering raw queue controls.

Selected baseline and last verified baseline are distinct exact-version links. Backlinks have at least
16px separation from the heading. Version detail returns to the actual tenancy, operation, audit or
baseline origin. Create/import recipe inspection preserves entered values and browser Back/Forward.
Return routes are allowlisted local pages; unknown/external destinations fall back to Baselines.
New configuration preview/progress caches clear on sign-out. The local simulation qualifier remains
visible throughout; queued acceptance never claims verified application. Later overrides and real OCI
qualification remain outside this baseline-only checkpoint.

## Baseline status and completed-work refinement — 3 November 2026

Use a separate description/action row below each baseline-update heading. Reset paragraph/heading
margins inside that row and verify actual text/control center geometry; centering a combined heading
and paragraph block does not satisfy alignment. The same rule applies to progress headers.

An individual tenancy shows baseline work only when it has an eligible update or unfinished work
for that child. Completed details remain in selected/verified fields and operation history, without
another completion panel. Successful bulk results remain visible until Acknowledge clears the
presentation and returns to Configuration. Acknowledgement never alters operation/audit records or
clears unresolved work. Refresh progress is absent after success. The idle fleet state is a compact
green oval; it must not substitute for failed/unavailable eligibility or unresolved updates.

Inventory Status groups the assigned exact baseline version, latest/update-available marker and
operation link. Completed operation links display only their UTC completion date. This adds no
separate configuration column, retaining room for the planned combined budget/actual/forecast cell.
Override markers will join this compact group when backed by actual override data; none are invented.
Audit targets retain the operation link and add friendly affected employee/tenancy names, with links
to registered tenancies and collapsed lists for large batches. All labels stay scoped to the workspace.


## Tenancy/shared-access refinement — 3 November 2026

Current UI qualified locally; both saved-instance installations pass. Tenancy detail separates Overrides from baseline-update
progress, listing configured categories or an explicit inherited empty state with existing verified
status and editor. The redundant top Manage owner & associations button is removed; clickable
owner/member names and contextual Transfer owner/Remove member remain. Inventory status exposes
registered created_at in UTC on pointer/keyboard tooltip, with Escape dismissal; this is not the OCI
tenancy's discovered creation date and adds no date column.

Add to shared tenancy explicitly chooses an existing discovered non-root compartment or a new name
under a discovered parent; never both. Member removal describes bound user/group retirement with
manual compartment/resource cleanup. New onboarding version 2 visibly includes frozen baseline
application/readback followed by access re-verification before temporary-account cleanup. Historical
operations display their accepted graph; no legacy completion is relabeled as applied.

These refinements do not change navigation, introduce a generic Operations action or qualify OCI.
[Manual review](how-to/tenancy-refinements-runbook.md) ·
[Field/step authority](reference/tenancy-onboarding.md).


## Configuration drift local production screen — 3 November 2026

Current React screen qualified and installed in both saved instances. Configuration → Configuration drift now has
Confirmed drift (default) and Checks views with server search/sort/pagination and tenancy counters.
Only current-context complete Missing/Different evidence enters confirmed drift; later failed reads
retain previous confirmed evidence and show unknown status/age. Checks also shows unchecked,
matching, unavailable and checking children. Empty confirmed drift never means all children healthy.
A newer publication or a pending review remains separate.

Check now / Check all tenancies explicitly queues read-only work. Refresh only fetches evidence;
active checks poll. Exact child/category detail shows assigned baseline, overrides, expected/observed
text, UTC timestamps and operation context with guarded Back routes. Queueing does not clear drift.
No Repair, fake acknowledgment/delete or navigation-action badge is introduced. Four local category
bundles do not imply real OCI grammar/binding/access qualification.

[Field/evidence authority](reference/configuration-drift.md) ·
[Manual review](how-to/configuration-drift-runbook.md). Historical static walkthroughs retain
the full accepted design; their repair controls are not claims of implemented production repair.


The current qualified drift implementation shares five computed tenancy read fields with the inventory/detail
(configuration_issue_count, configuration_confirmed_issue_count, configuration_check_state,
configuration_checked_at, configuration_check_stale); no SQL columns or duplicate health cache.
The inventory distinguishes confirmed category counts from independent check-health/status links
and opens the exact child's evidence. Unchanged-policy execution pause disables checks and preserves earlier
confirmed drift as unavailable, never green. Changed parent/policy invalidates old current context.
[Field source/default map](reference/configuration-drift.md#computed-tenancy-inventorydetail-fields).


## Qualified guided responsibility takeover UI — 4 November 2026

Local qualification and both saved-instance upgrades pass. Guided operation detail adds Administrator responsibility with separate
Initiated by and Responsible administrator labels. Eligible different administrators can explicitly
Take responsibility for waiting/needs_attention guided create/import. A native confirmation freezes
the reviewed current responsible name/revision; no Reason or other-assignee picker. Cancel/Escape/
GET/refetch never reassign. Conflict requires fresh review; accepted application change does not
queue a provider job or imply handoff completion.

Original activation mailbox/MFA and creator remain unchanged. Only current responsible has enabled
setup actions after refresh; takeover does not transfer tenancy ownership or credentials. Four
computed OperationSummary fields supply the labels, authority UUID, current revision and eligibility,
with no SQL columns. Exact [field/replay/authority mapping](reference/responsibility.md) and
[manual review](how-to/responsibility-runbook.md) define scope. No temporary simulation-control UI
or email delivery is introduced.


The create/import setup subtitle explicitly says Initiated by and keeps the original
OnboardingView.administrator_name after takeover. It is not a current-responsible label; the
separate Administrator responsibility panel reads OperationSummary's current responsible projection.
Original activation contact data also remains unchanged. This label refinement changes no field
source, provider intent or authority. Final slice qualification and both saved-instance upgrades pass.


## Lifecycle email/contact UI source candidate — 4 November 2026

Validation pending. An authenticated nonproduction banner describes NEW application delivery only;
canonical identities and old activation evidence remain unchanged. Create preview/setup uses
Activation / bootstrap email; import uses Bootstrap contact email, with Original contact separate.
The manual bootstrap checklist uses its frozen effective contact and distinct username. Owner
invitation contact is a provider-path preview, not an additional D50 SMTP recipient or a simulated
internet invitation. Legacy contacts=null retain existing instructions.

OperationDetail.notifications exposes up to 100 retained safe status rows with frozen effective/
original recipient, redirection, attempt/time and diagnostic. No HTML message body, SMTP credentials,
Send/Resend or recipient editor is added. Application notices may reach local capture while the
lifecycle facade sends no OCI activation email. [Field/state guide](reference/lifecycle-email.md).


## Separate audit delivery filter — 5 November 2026

Source/UI refinement, validation pending. Audit History adds Email delivery alongside its existing
category choices. It filters only email_delivery evidence; Operations excludes that evidence and
All categories includes it. Existing table/date/search/sort/pagination/export behavior remains.
Normal operation-detail notification panels are unchanged; a filter never sends, acknowledges or
rewrites mail/history. No navigation destination or database field is added.


## Consistent configuration-check freshness — 5 November 2026

Source refinement, validation pending. Inventory, tenancy detail, Configuration drift directory and
check detail share the status formatter: Configuration drift · N categories means only complete
current-context Missing/Different, while Check out of date, Unable to verify, Not checked and
Checking describe independent evidence health. Retained confirmed drift can appear with those age/
failure/progress labels. Inventory hides a fresh Matching-only label; detail can show Matching.
Check-status evidence links are allowed without inventing a confirmed-drift count or inbox badge.

The directory shows independent stale, unavailable, not-checked and checking counters, even when
Confirmed drift is empty. Not checked excludes overdue evidence. Stale is a filter alias over the
existing age flag; Matching is fresh only and Confirmed drift includes retained findings during
unavailable/checking. Counters can overlap. Recheck acceptance preserves previous findings/time;
actual observed completion refreshes the tenancy, directory and check-detail caches, including a
fast fleet result that leaves the confirmed list and externally started checks finishing while a
view is open. No new summary state, local scheduler or simulation-control UI is introduced.

[Current field/filter semantics](reference/configuration-drift.md#filter-and-counter-interpretation).
The drift CronJob is explicitly deferred until staging/Kubernetes deployment; a stale threshold is
not a schedule. Existing session-maintenance jobs are a separate feature.
