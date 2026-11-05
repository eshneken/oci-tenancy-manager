# OCI Tenancy Manager UI baseline

## Selected visual direction — D57, 28 October 2026

The user chose **original A / Field Console (left)** after comparing it with rounded A2.
Use A's navy navigation, cobalt accents, cool light surfaces, crisp 3px corners and technical
sans/monospace typography. The 9px rounded A2 treatment is not selected; B/C/D remain references.

Selected treatment (private historical evidence; not distributed) ·
Selected capture (private historical evidence; not distributed) ·
Comparison record (private historical evidence; not distributed)

The token reference below is the visual authority for future application screens/components.
Preserve the organization prototype's approved usability, D44–D46 dashboard fields/behavior,
accessibility and security. Older walkthroughs retain their accepted interaction contracts until
visually aligned. This decision does not imply a completed application reskin or whole-package
Git/publication approval.

## Reference implementation

- [Current React frontend](frontend/README.md): application screens and shared controls.
- [Shared styles](frontend/src/styles.css): selected tokens, spacing and responsive behavior.
- [Screen authority](docs/ui-screen-authority.md): implemented versus future design scope.
- The retained prototype characterizes earlier business behavior; it is not current styling authority.

## Layout and visual language

A / Field Console uses a navy left navigation, white utility header, cool gray canvas, restrained
cobalt actions/links and a precise inventory table. Consolidated metrics use crisp dividing rules
rather than decorative card stacks. Keep one clear page title, concise task copy and aligned actions.
The table panel owns its search/filter/sort controls and numbered pagination; technical identifiers
and financial numerals use the selected monospace treatment.

| Token | Field Console value / treatment |
|---|---|
| Navigation | `#132035`; active navigation `#24416c` with visible cobalt/light-blue indicator |
| Canvas / surfaces | `#f3f5f7` / `#ffffff` |
| Text / secondary text | `#182536` / `#5b6877`; verify contrast on actual surfaces |
| Accent / soft accent | `#2459ed` / `#edf2ff` |
| Borders / ordinary corner radius | `#dce1e7` / `3px` |
| Over-budget actual | Foreground `#a72c36`, background `#fce7e9` |
| Over-budget forecast | Foreground `#8b5007`, background `#fff0ce` |
| Positive semantic state | Foreground `#376452`, background `#edf5ef`; never infer overall health from one passing value |
| Typography | Selected sans-serif stack with Arial fallback; local monospace stack for identifiers/numerals. No new external font/CDN is required |
| Desktop composition | Approximately222px navigation and38px content padding; adapt to viewport/content rather than hardcoding all widths |

Cobalt denotes navigation/actions, not a success condition. Preserve distinct semantic colors,
readable status text and accessible names; color alone cannot carry meaning. Keep the existing
44px primary/form-control rule, adequate compact desktop targets and44px touch targets. Maintain
clear focus contrast on both dark navigation and white content/preview chrome.

On narrow screens navigation moves above content, actions wrap to full-width rows, and metric
groups adapt to their meaningful count. Tables scroll inside their own panel. No global overflow,
clipped labels or hidden offscreen screen-reader text may expand the document. Anchor financial
screen-reader descriptions to their amount container, as in the reviewed selected treatment.
The selected preview's markup/CSS illustrates the treatment; implement reusable production
components rather than copying its demo dataset, limited sample states or style-comparison controls.

## Interaction patterns to carry into the app

- Daily work navigation: Tenancies; Organization → Organization drift; Configuration → Baselines / Configuration drift. A separate **Activity & history** group contains Operations and Audit History; **Application settings** contains Administrators. The [screen authority map](docs/ui-screen-authority.md) distinguishes implemented screens from inert static placeholders.
- A directory with the requested identity/reporting/LOB fields, sortable headers, search, LOB
  filter, selectable page size, numbered pages and a visible result range.
- Summary metrics with clear scope, plus a current applied-feed timestamp/coverage description.
- An informative empty state with the next useful action; a distinct no-search-results state.
- A focused review queue rather than a list flooded with automatically applied metadata changes.
- A native modal for upload, understandable source requirements, progress feedback and actionable
  validation errors. Success updates the directory and summary together without reloading the page.
- Clear confirmation for actions that discard the visible test context; Cancel is the initial
  focus, and the server checks that the confirmed context has not changed.
- Search/sort/filter responses cannot overwrite a newer request. Uploaded strings enter the DOM
  as text. Labels, keyboard controls, sort direction and focus behavior remain accessible.

## Semantic boundaries

Retain the distinction between reported top manager and derived accountable leader. An employee
missing from a feed is retained for investigation; a new profile indicates tenancy association
review, not proof that a new tenancy is needed. Required human decisions stay explicit.

The plain-JavaScript frontend and local FastAPI server are prototype implementation choices.
Preserve their approved usability when moving to the production stack. The **Clean workspace**
control is a local testing convenience that archives runs; do not carry it into production as a
general reset/delete capability. OCI operations, SSO and workflow completion still require the
production design and its authorization boundaries.

## Exception workflow refinement — 16 October

Keep actionable administrator decisions separate from informational warning/change history, using
tabs with independent filtering/paging and an actionable-only navigation count. Review actions
open a focused modal showing affected identity, explicit operation and consequences, with a factual action description recorded automatically.
Organization review state and tenancy workflow state are separate. One-way identity merges preview the survivor and
new metadata; show the local registry accurately without implying that simulated tenancies exist in OCI. Preserve dates and
expandable per-employee before/after changes in the informational tab.

## Reusable interface and review policy — 19 October 2026

Interface guidance, status messages, errors and empty states must describe the configured
organization generically. Keep real people and LOB labels in records/configuration; do not embed
organization-specific examples in instructional text. Retain an honest local-environment label
and explicit simulated-operation notices until the corresponding capabilities are implemented.

For LOB mapping reviews, label the condition-scoped `resolve` operation **Dismiss current
condition** and the person/type-wide `ignore` operation **Always exempt from LOB mapping**.
Explain recurrence before confirmation: changed relevant facts may reopen a dismissed condition;
an exemption suppresses only that employee's LOB mapping reviews across future changes. Neither
operation assigns an LOB, removes the employee or suppresses absence and other review types.
Both retain an audited server-generated action description; neither requires a free-text Reason field. Stored operation names and lifecycle semantics remain unchanged.

Action buttons share a minimum 44px control height, centered label/icon alignment and explicit
line height. Decorative icons must not change button height. Scope sidebar selectors to sidebar
navigation so category links and count badges cannot inherit their typography. Wrap long labels
and action groups on small screens. Dialogs scroll within the viewport, keyboard focus remains
visible, and selected review operations expose `aria-pressed`. Apply the standing
[UI/UX review policy](docs/ui-ux-review-policy.md) to future changes.

Historical prototype token: `--muted: #586d65` corrected its earlier contrast failure. D57 uses
Field Console secondary text `#5b6877`; verify at least4.5:1 on actual normal-text backgrounds,
including tinted notes. Keep the historical fix when maintaining the unchanged local lab.

## Association-aware tenancy actions — 19 October 2026

The person panel shows owned individual/shared tenancies and shared membership as separate
relationships, with explicit local simulated-state labels. Create/import/shared choices persist
local registry associations and close onboarding; No tenancy required is permitted only without
active associations and hides the person from the managed directory. Initial baseline/pending
profiles with zero tracked associations remain visible until an explicit decision.

Use **Offboard person**, not an ambiguous Delete/Resolve/Remove-person sequence. Preview every
association and require a disposition for each. Shared membership removal never deletes a shared
tenancy. A shared owner must transfer ownership or keep that association. Warn about other members
and prevent individual-tenancy deletion from silently removing their access. Show the resulting
outcome before confirmation: zero remaining associations removes the person from the managed
directory; retained associations keep the person visible for further cleanup. An empty registry
requires explicit confirmation because the prototype cannot prove external OCI absence.

Retain source/reporting records and history even when someone is unmanaged. Provide access to
unmanaged profiles. After qualified absence, a qualified full-feed return automatically opens
onboarding for completed zero-association offboarding; do not restore old tenancies. No tenancy
required stays an explicit exemption until manual Re-onboard. Mere unchanged-present uploads
without absence cannot create return work. Persist pending onboarding across later feeds. A retained outside employee with existing associations uses Mark returned to organization
only after source presence returns; repeated feeds alone never clear that explicit status.
Ownerless legacy shared tenancies show Assign owner and block new memberships until accountability
is restored. Keep the source employee count distinct from the managed-directory count.

The prototype simulates immediate successful completion and logs it honestly. Production review
closure happens at durable workflow acceptance, with the person Offboarding until required
operations succeed. Failures/retries remain in the linked tenancy operations workflow. There is
no separate Resolve action after successful association cleanup. Follow the
[association design](prototype/docs/tenancy-associations.md) for local persistence and ownership guards.

## Fresh organization observations — 19 October 2026

Every deliberate upload is a new snapshot, even for unchanged file bytes. Future API/object
storage pulls have the same semantics per acquisition. Content hashes identify content only;
a persisted observation ID distinguishes a new acquisition from retries of the same delivery.
The upload dialog explains this behavior and reports a processed new snapshot. Do not show a
CSV duplicate-success message or ask the operator to change whitespace to force reevaluation.
An intentionally uploaded older file is evaluated as current evidence, retaining all validation,
coverage, authority and human-decision guards. Existing source history remains immutable.

## Tenancies inventory — 19 October 2026

Tenancies is the first main-menu destination at `/tenancies`, not a secondary modal-only inventory.
Reuse the Employees table's search/filter bar, sortable header affordances, numbered pagination,
page-size/result range, loading/error/empty/no-match states and responsive panel scrolling. Show
active tenancy name, type, owner name/email, owner-derived LOB and member count including the owner. Name and
owner links open existing detail dialogs with consistent focus/return behavior. Unknown ownership
and LOB have explicit empty labels; zero member count is meaningful and distinct from an unknown
owner. Do not mix deleted rows into this active inventory or imply a live OCI discovery result.
Changing the owner-derived LOB is a reporting update, not an ownership transfer.

## Summary scope and audit input refinement — 19 October 2026

Tenancies owns total-active, individual, shared and unassigned-owner summary cards; employee or
exception metrics must not be relabeled as tenancy inventory. Its Member count includes the owner.
Employees has a sortable Tenancies column for each person's active association count. Keep the
internal member-only registry count for backend ownership guards; do not expose it as total people.

Do not ask for free-text Reason on UI action dialogs. Show operation-specific consequences and
explicit confirmations instead. Automatically retain a factual server-generated action description,
actor, target/context and outcome. Optional API/CLI notes do not require a UI textbox. This current
policy supersedes earlier dialog guidance requiring a manually supplied reason. Return notices
must distinguish automatic zero-association re-onboarding from manual retained-association return
and explicit no-tenancy exemptions.

## Organization navigation terminology — 21 October 2026

The production design/walkthrough names the people directory **Organization**, with **Organization
drift** as its review submenu, consistent with **Configuration drift**. Keep headings, breadcrumbs,
empty states and back links consistent. This rename preserves actionable/informational organization
review semantics. References above to Employees/Exceptions describe the implemented local prototype;
that application's menu has not been renamed by this design-only checkpoint.

## Approved page bodies and shared menu — D34, 21 October 2026

The working prototype remains authoritative for the Organization directory and Organization drift
review pages, including actionable/informational tabs, table controls and dialogs. Configuration
walkthrough organization screens are placeholders and do not approve alternative layouts. Keep
Organization and Organization drift non-clickable in the design menu until approved content is
integrated. Their legacy direct URLs show a placeholder notice only, without fake rows/counts.

All three current engineering walkthroughs use the shared design navigation assets specified in
[the screen authority map](docs/ui-screen-authority.md). Back-propagate current menu changes there;
preserve historical screenshots/checkpoints. Cross-page review checks both the common shell and
each page's approved source, so a convenient mockup cannot silently replace established UX.

The tenancy table retains the explicitly accepted **Assigned baseline** and clickable
**Configuration issues** additions. Extend the prototype inventory rather than dropping its owner,
LOB, type, member-count or table controls. Show the recorded assignment and distinguish pending
application; issue links preserve exact tenancy context and do not call an unknown check healthy.


## App-style walkthroughs — D38, 24 October 2026

Walkthrough HTML models the intended product screens and user interactions. Use normal page titles,
short statuses, essential fields, focused confirmations and meaningful transitions. An administrator
should be able to follow the ordinary task without a scenario dropdown. Move implementation flow,
API/transaction details, invariants and qualification rationale to the design Markdown. Detailed
observed diagnostic data can be behind Check details; it is not a reason to show a specification essay.

Keep local-only simulation honest with a quiet, always-visible preview label and collapsed scenario
controls. Do not call real services, display actual credentials or imply simulated checks qualify OCI.
Preserve app-quality keyboard/modal behavior, stable deadlines, blocked actions and responsive layouts.
D40 uses one Administrator access flow for the persistent recovery password; temporary named support is deferred. Keep Required users and Administrator access as the two access tabs. Independent outside-app recovery remains available. Apply this treatment to new work;
older approved walkthroughs retain their functional meaning until intentionally aligned. The two access
pages are the first updated reference, without replacing the approved organization prototype.

## Combined Tenancies dashboard — D44, 24 October 2026

Use one Tenancies list, with no Inventory/Costs tabs. Five columns consolidate existing information:
Tenancy (linked name, type, owner-inclusive people count); Owner/LOB; Configuration (assigned baseline,
override action and linked issues); Actual/Budget; Forecast. An individual tenancy with an active owner
counts that owner as1; shared people counts include the owner plus distinct active members. Never
fabricate a minimum count for an unassigned record. Direct manager remains searchable/in detail.

The common Tenancies destination is `financial-walkthrough.html#tenancies`; old list routes are aliases
to it. Preserve filters, sorting, numbered paging/ranges, linked identities and scoped summary counts.
Tenancy detail and existing Configuration actions remain available without creating another list.
The working organization prototype and its database are not changed by this design direction.

Consolidated cells retain accessible actions and textual status alternatives; color is supplementary. The list cost-data information control shows OTM retrieval time, optionally status/cycle, and works on hover, keyboard
focus and touch/tap. Do not show OCI computation time in that tooltip; retain it internally for stale-data qualification and in technical source detail. Missing/stale/prior-cycle/unverified-currency and other important data warnings
remain visible in the row. Tooltip availability cannot become a substitute for error/status text.

D41 same-read observed budget/actual/full-cycle forecast, D42 daily/manual acquisition and D43
red-actual/amber-forecast comparisons remain binding. Desired budget remains secondary while pending;
forecast never adds actual. Unqualified data cannot appear healthy. Historical financial reporting
is post-V1. D46 records user acceptance of the final D45 consolidated dashboard; source/layout evidence remains version-specific and provider qualification remains separate.

## D45 numeric presentation — 25 October 2026

Keep the same five columns. Highlight actual and forecast numbers independently against the same qualified observed budget: actual over budget red, forecast over budget amber, qualified below-budget values green, exact-at-budget or unqualified/unavailable values neutral. Grant actual240/budget200 and forecast320 must show both red actual and amber forecast. Replace redundant second-row spend badges with these number backgrounds plus screen-reader-only status and hover titles; the list has no overall warning badge. Detail may retain a highest-severity summary alongside independent values.

Keep missing/stale/prior-cycle/unverified-currency and pending-budget messages visible. The accessible cost-data tooltip exposes OTM retrieval time only as its timestamp, optionally status/cycle. Preserve OCI computation time in storage, internal freshness checks and technical detail. D45 refines D43 presentation only; D41–D42 and existing comparison/qualification remain. D46 records user acceptance of this dashboard; no application/model/schema change or real-provider qualification is implied.

## D46: final combined dashboard approved — 25 October 2026

The user approved the final D45 unified five-column Tenancies dashboard, explicitly including separate Actual and Budget sort controls within their shared visual column. This closes user layout acceptance for this dashboard; it does not declare the entire engineering design complete or qualify real OCI behavior. D45 independent numeric highlights, retrieval-only list tooltip, visible degradation/pending labels and all D41–D42 source/cadence rules remain unchanged.

The shared Actual/Budget visual header has two independently operable sort controls: Actual uses `sort=actual` mapped to `actual_spend`; Budget uses `sort=budget` mapped to `observed_budget_amount`, never the desired/pending amount. One active `(sort, direction)` pair is retained, with `direction=asc|desc` (the walkthrough uses internal `1|-1`). Selecting a different key starts ascending; activating the same key toggles direction. Missing/unavailable values sort last in both directions, never as zero. A changed sort starts page1 while preserving search, LOB filter and page size; subsequent paging and detail/back navigation preserve the selected sort/direction and valid query/page context. Accessible control labels and the header sort state identify the active key and direction.

Per-value qualification remains independent: an available, qualified actual below observed budget may be green even when forecast is unavailable. Keep Forecast unavailable visible; green actual does not assert that projected spend or the whole tenancy's financial health is healthy. No schema, provider operation, historical cost reporting or automatic cost action is added.

## Accepted activity/history navigation — 30 October 2026

Keep day-to-day management in Tenancies, Organization/Organization drift and Configuration/Baselines/
Configuration drift. Place Operations and Audit History together under a separate **Activity & history**
heading; keep Administrators under **Application settings**. History is not a global remediation inbox:
no badge or copy should turn an operation-state count into a count of tasks assigned to the user.

Operations explains recorded progress, outcomes and troubleshooting evidence. When a real workflow
needs remediation, start from the affected tenancy, organization, configuration or access context,
with links back to its operation evidence. Do not introduce a generic Retry button or invent a
context destination that does not exist. Existing authorization, target and uncertain-effect guards
remain mandatory when a later contextual action is implemented.

The stored `needs_attention` state remains unchanged. Current simulated detail explicitly says
**“Simulation ended with an issue. No action is required.”** This is virtual inspection guidance,
not a change to the meaning of a future real lifecycle/security issue. Submission uncertainty still
requires checking recorded Operations before starting another request; the new wording does not
claim an unconfirmed submission failed or completed.

Audit History is an application-administration/operation evidence view over existing immutable audit
rows, separate from deferred security findings. Its first read slice uses safe search/category
filtering and public projections; it has no raw JSON display or record editing. The later
Audit History slice adds UTC date bounds and complete-filter CSV export with an explicit size
limit and a recorded preparation event. Exact DTO/field
mapping follows the authoritative implementation contracts. Static Audit History/Administrators
labels remain inert where no static destination exists; do not fabricate an audit page link.


## Instance branding — Atlas, 30 October 2026

OCI Tenancy Manager remains the internal product name; Python packages, database tables, API/header
names and technical documentation retain OTM identifiers. Deployments may choose their public
identity using `application.toml` `[branding]`: `display_name`, `logo_url`, and `icon_url`. This
installation uses **Atlas**. The original Field Console layout and semantic colors are unchanged.

Use the transparent horizontal wordmark on navy surfaces in sign-in and navigation. The compact
cloud mark is the browser icon. Preserve natural aspect ratio; do not stretch/crop the artwork to
fill a box. Display-name text is the accessible identity and the fallback if an image is missing;
never rely on the raster wordmark alone. Browser titles use the configured name. Custom names
remain text, never markup. Branding is deployment configuration, not an administrator/profile edit.
The preserved organization prototype and historical walkthrough captures are reference artifacts,
not another runtime instance requiring renaming.

[Branding configuration and asset guidance](docs/reference/application-settings.md#instance-branding)
records validation, deployment and local update steps.


## Audit date filtering and CSV export

Audit History remains retrospective. **From (UTC)** is inclusive and **Before (UTC)** is exclusive;
clear filters resets search, category and both dates. Invalid ranges show an inline message, retain
the last valid results and disable export. Keep date controls aligned and responsive alongside
search/category/refresh. **Export CSV** applies all current filters and ordering across pages, not
just the visible page. State the 10,000-event limit; oversized results require narrowing filters
and never produce a silently truncated file. Loading, preparation/error/success and expired-session
states remain visible without new dialogs. The export is recorded as **Audit export prepared**:
this proves preparation, not that a person received or opened the download.


## Shared checkbox and select treatment — 30 October2026

Checkboxes use18px visual controls without text-input padding, aligned to the label's first line;
labels retain44px click targets. Directory one-line toggles center their checkbox/text pair. Selects
retain native form/keyboard behavior with normal-weight values, a clearly visible inset chevron and
reserved end padding. Supporting browsers use the CSS customizable native picker, anchored to the
field with bounded scrolling options, cobalt selection/focus and Field Console3px corners. Unsupported
browsers retain their native picker behavior; the enhanced closed-field arrow still applies. Forced
colors restore browser-drawn appearance. A thin native `Select` wrapper bounds selected text; the browser owns selection, focus and keyboard
state. Its display-only selected-value button is hidden from assistive technology so the native
combobox remains the single accessible control. No bespoke interaction widget or dependency is introduced.

### Dropdown sizing guard — 2 November 2026

All application selects share the native Select wrapper and popup rules. Menus size to their option
content, at least the field width, with a viewport maximum. Short state/category labels stay on one
line; long identifiers may wrap when constrained by the viewport. Reserve checkmark/chevron space.
Prefer field-aligned placement; when neither inline edge fits, use a viewport-centered safe fallback
below or above the field. State/category filters share a13rem minimum. Numeric controls remain compact.
Validate open menus, not only the closed field, using the [cross-screen review gate](docs/ui-ux-review-policy.md).
