# UI/UX review policy

Established 19 October 2026 by user request. The dedicated `ui_ux_review` subagent is a standing
review partner, like the code-documentation agent. Reuse the same agent while it remains
available. Recreate this role from this policy after a new session when necessary; no background
scheduler or independently running process is implied.

## Review scope

Review every UI change against DESIGN.md, the working prototype and the whole affected flow.
Check shared effects on the employee directory, both exception categories and every affected
dialog. Review the whole existing UI when first assigned and revisit it when shared styles or
interaction patterns change. Keep production findings and verification evidence under ignored `docs/design-evidence/` or
`frontend/.local-dev/`; reserve `prototype/evidence/` for the retained lab. Describe limitations accurately.

## What the reviewer checks

- Consistent component size, spacing, typography, color, borders and primary/secondary emphasis.
  Adjacent buttons must have matching heights and vertically centered labels/icons. Count badges
  must align with their labels and must not inherit unrelated navigation styles.
- Generic reusable guidance, validation errors, status messages, empty states and action names.
  Actual employee identities and configured organizational labels remain real data. Avoid
  named-organization examples in interface instructions. Keep prototype limitations honest.
- Clear action consequences, selection, confirmation, loading, success, failure and retry states.
  Do not conflate acknowledgment with completed infrastructure operations or review resolution.
  Prevent ambiguous/double submissions and preserve entered input after recoverable errors.
- Keyboard operation, visible focus, labels, semantic controls, screen-reader selection/state,
  readable contrast, meaningful status text and usable target sizes. Never rely only on color.
- Responsive behavior at desktop, tablet and narrow mobile widths, including 320px and 390px.
  Long names, emails, labels and changing count lengths must wrap or scroll appropriately.
  Tables may scroll inside their own panel; the page must not overflow horizontally. Dialogs
  must fit the viewport and allow access to all actions. Check zoom when shared layout changes.
- Consistency between pages: navigation, filters, sort indicators, pagination, dates, notifications,
  count meanings, action wording and loading/empty/error feedback.

## Review workflow

1. Read the affected source and the approved baseline; report concrete findings with severity,
   file/line references and the user-visible effect. Coordinate file ownership with the parent.
2. Review real browser behavior after changes. Navigation and opening/canceling dialogs in the
   live workspace are read-only. Use an isolated workspace for any upload, decision or reset.
   Do not change the user's live data to manufacture a screenshot. Clearly identify DOM-only
   fixtures when used to inspect otherwise unavailable states.
3. Fix material findings within the requested scope, then recheck the affected state and shared
   screens at relevant widths. Capture screenshots and geometry/console evidence when useful.
   Use meaningful existing tests for behavior changes; do not add tests that merely mirror CSS.
4. Return a concise pass/fail review with remaining limitations. Record reusable lessons in the
   design baseline or policy so future work does not depend on an agent retaining conversation
   memory. The parent remains responsible for final verification and user communication.

## Approved-source and global consistency check — D34

Use [the screen authority map](ui-screen-authority.md) before accepting a page-body change. The
working organization prototype is authoritative for Organization and Organization drift; placeholder
pages in an engineering walkthrough cannot replace it. Check the shared menu across onboarding,
operations, configuration and required access when its structure/styles change. Organization context labels remain
non-interactive in design-only navigation until the approved pages are integrated. Preserve current
workflow behavior and historical snapshots; do not treat navigation approval as layout approval.

## Narrative, screenshot and model agreement

For every new design slice, apply the [field-coverage gate](ui-screen-authority.md#field-coverage-gate-for-every-design-slice).
Check that controls/statuses/counts are supported by the named model or a documented derivation, and
that narrative matches the final rendered behavior. Do not infer full privileges from generic reads
or whole-tenancy health from one passing scoped check. Coordinate field gaps with the documentation
reviewer and root; preserve pending decisions rather than inventing successful provider evidence.


## Product-shaped interaction review — D38

Review walkthroughs as proposed app flows: normal entry point, short task copy, essential status and
fields, confirmation, pending result, success/attention, cancel/back and return focus. Scenario controls
are optional collapsed demo tools, not required navigation. Engineering explanations belong in Markdown.
Keep production gates in the contract even when concise UI omits their internal names. Verify seeded
check transitions do not claim real provider qualification and an unknown outcome cannot become success
through a page visit. Compare both access pages and the current shared shell.

## D40 human-access consistency

Review one Administrator access journey alongside Required users. No temporary user creation,
enrollment, cleanup or separate Recovery tab belongs in V1. Use the exact persistent recovery
identity and preserve the first-attempt four-hour deadline on repeat retrievals. Available, rotating,
unverified and verified-rotated states require different allowed actions. Unknown rotation cannot
show a usable password or old-version fallback. Keep audit/notification and independent recovery
instructions concise; screen acceptance never qualifies provider behavior. Historical support links
may normalize to the current flow without inventing a provisioning action.


## Shared control review — 30 October2026

Review controls in both their resting and interactive states. A closed dropdown screenshot is not
sufficient evidence for its menu: open it by pointer and keyboard, choose an option, cancel with
Escape, and verify focus returns to the field. Check popups inside scrolling dialogs, near viewport
edges and with long names/OCIDs. Menus should align to the field, reserve inset space for a clear
chevron, distinguish selection from focus/hover, and remain scrollable within the viewport. Retain
native keyboard/form semantics; qualify OS/browser fallback differences explicitly. Check disabled
and forced-colors states. Do not replace semantic native controls with bespoke interaction code
when progressive browser styling meets the requirement.


### Dropdown sizing and regression coverage — 2 November 2026

A shared dropdown change requires an inventory of every select use, not approval from one screen.
Review each distinct content class: short state/category filters, numeric page sizes, workflow
choices, regions, employee names/emails, tenancy names/OCIDs and compartment paths. Mapping email
suggestions use a separate native datalist; qualify those separately rather than assuming select
coverage also tests autocomplete.

The open menu may be wider than its closed field. Size it to readable option content, at least the
field width, and cap it to the viewport. Short labels such as All states, Needs attention,
Succeeded and the audit categories must fit on one line without splitting words. Numeric menus
should remain compact. Long descriptive options may wrap at word boundaries; long unbroken names
or identifiers may wrap when the viewport cap requires it. Preserve room for both text and the
selection checkmark. Closed labels may use ellipsis while retaining a visible inset chevron.

Open the actual Operations state and Audit category menus together after any sizing change; a
screen-specific width fix cannot substitute for shared-control regression coverage. Inspect the
widest selected and nonselected labels at 1280, 900, 768, 390 and 320px, including a scrolling dialog
and controls near viewport edges. Confirm the popup itself stays inside the viewport, its options
remain readable, and the selected checkmark is visible. Measure the text/checkmark content area
and short-option line heights, not only the closed field width or document overflow. Short options
must have equal heights of at least 44px; longer options may be taller. Check pointer selection,
keyboard selection and Escape/focus return. Capture open-state screenshots at desktop and phone
widths and visually inspect them before reporting success. State which browser, native fallback,
forced-colors and zoom behaviors were actually exercised; CSS zoom is not browser zoom.

### Checkbox alignment

Checkboxes need explicit dimensions, zero text-input padding and a reliable relationship to their
label. Inspect single-line labels and the first line of wrapped labels at100%/200% zoom, on desktop
and320/390px screens. Check the actual checkbox glyph against text, not just the surrounding element
boxes. The label provides the44px pointer/touch target; do not inflate the checkbox itself to achieve
that target. Review every shared checkbox use, including filters, census attestation and impact
confirmations. Never infer that two elements align merely because both have44px minimum height.

## Actionable navigation badges

Navigation counts signal work with a supported way for an administrator to resolve it. A raw error,
blocked state or historical simulation result is insufficient. Check the actual handoff, review,
retry, verification or safe cancellation path; unsupported recovery and orphaned history must not
light a work badge. Cover both a positive actionable case and a diagnostic-with-no-action case, and
confirm the count clears after a supported transition. Preserve operation/audit history; do not add
Delete, Dismiss, acknowledgment or forced-success behavior merely to clear a number.


## Backlinks and contextual detail views — 3 November 2026

Backlinks require intentional separation from the detail heading. Inspect the actual gap on desktop
and narrow screens; a link immediately touching a heading is a defect even when neither overflows.
Use the shared spacing rhythm (normally at least 16px between the backlink and heading), preserve a
visible focus state and keep heading hierarchy clear. Review the backlink together with the heading,
metadata and first content section; do not approve each item in isolation.

A detail opened from a workflow must offer a return to that workflow rather than a generic list.
Exercise entry from the baseline directory, create/import form, operation and tenancy detail, plus a
direct URL without origin context. Verify Back/Forward and the explicit return link. Returning from
an in-progress form must preserve its entered values and action context; merely returning to the
same page while discarding the form is insufficient. Origin hints must use validated application
routes, not arbitrary external return URLs. Links to versioned records should identify the version
(e.g. Version 2), and distinguish selected/target versions from verified application. Queue acceptance
is not completed configuration work; individual and bulk updates must retain that distinction.


## Horizontal action-row alignment — 3 November 2026

Inspect visible text and controls together. `align-items: center` on a container and equal minimum
button heights do not prove that a paragraph's text, heading or button label is visually centered.
Default paragraph/heading margins and a combined title/description box can shift the actual text
away from adjacent controls. Put section headings on their own row when the action belongs beside
supporting text; use a dedicated action row with explicit margins, spacing and wrapping.

Review the actual line box/text baseline against the button's visible vertical center, not only the
outer paragraph or flex-container bounds. Check single-line and wrapped descriptions with one and
multiple buttons at desktop, tablet and 390/320px. Add geometry assertions for the intended visible
text/control relationship and inspect fresh screenshots; a no-overflow check is insufficient.
When rows stack, keep the reading order and spacing intentional. Recheck other uses of shared row
styles so a local alignment fix does not shift unrelated labels, headings or footer actions.

## Optional operator instructions — 7 November 2026

Lengthy procedural help belongs in a native details/summary disclosure, closed by default. Use
the shared operator-instructions styling: clear topic label, visible native marker, keyboard
focus, at least 44px summary and bounded/wrapping content. Opening help is transient local UI
state, not a saved preference or administrator acknowledgment. Keep instructions and links
complete inside; do not remove useful guidance merely to reduce page height.

Keep actual fields, action buttons, current failures, prerequisites, simulation/safety notices,
destructive consequences, exact account-removal targets, consent and pending manual work visible.
Do not collapse an obligation or a required warning as optional help. Apply the pattern to future
long operator procedures and audit existing pages; brief field/CSV constraints can remain inline.
Create/import share the collapsed OCI administrator checklist; existing first-time sign-in help,
identity/source details and nested transfer references already use default-closed disclosures.

## Button color consistency — 7 November 2026

Audit every screen against [the action emphasis rules](../DESIGN.md#action-emphasis--7-november-2026).
Routine refresh/check and section-level view/edit/manage/add-member launchers are white secondary.
Main page create workflows and form/dialog submit/save/confirm/continue actions use cobalt primary.
Destructive actions stay danger-styled; active tabs/navigation retain their selected-state treatment.
Compare related controls together, including cost/user refresh and overrides/member management on
tenancy details. Check enabled, busy, disabled and narrow-screen states; report role drift before
a slice is complete. A queued background read does not justify stronger emphasis than another read.

## Whole-page section rhythm — 9 November 2026

Cropped panel screenshots do not qualify a layout change by themselves. Inspect a full-page
capture showing the changed panels and their preceding/following sections. Compare vertical
section gaps with the shared spacing rhythm and horizontal panel gutters at laptop and mobile
widths. In tenancy detail, the costs/overrides group has 24px before and after it and 24px between
its panels, including when stacked. Check Current members even when optional baseline-update
content is absent. Include measured boundary assertions in the affected browser flow; checking
only containment and internal alignment misses touching adjacent sections.

## Compact checked-date provenance — 9 November 2026

Keep status badges uninterrupted; group check dates beneath them, before optional identity details.
Use labelled, date-only UTC links in a two-column laptop footer, stacking on small screens.
Accessible link names must identify the check kind and date; preserve exact operation destinations
and full UTC timestamps in metadata/hover detail. Check unknown/last-attempt labels, coincident
dates, absent operation references, keyboard navigation and whole-page section gaps.

Date values in a shared footer row must align even when one caption wraps. Measure the actual
date/link line boxes, not merely the tops of the surrounding grid cells.

For paired panel headers, compare actual action centers and right insets, not just heading or
container bounds. Test compact laptop wrapping as well as wide screens. A three-fact overview row
must preserve the wider policy pairs below it and stack before phone-width text becomes cramped.

A no-overflow assertion is insufficient for short status values: inspect actual text-line ranges
for word fragmentation. Required-user cards stack at900px to preserve readable overview values;
their inner facts/footer fields still stack at700px.
