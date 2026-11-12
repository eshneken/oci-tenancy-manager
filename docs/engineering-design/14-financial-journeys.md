# 14: financial screens and collection contract

25 October 2026 | C5 initial design | D41–D46 accepted: child Budget source, daily/manual, indicators and unified Tenancies direction; no new application behavior

[Design hub](README.md) · [Financial principles](05-cost-and-observability.md) ·
[Proposed financial model](11-production-data-model.md#financial-collection-and-observations) ·
[Usage SDK mapping](08-oci-sdk-call-design.md#actual-cost-and-native-forecast)

## Scope and decision sequence

The user approved D40's simplified access screens and requested proceeding. C5 develops the existing
V1 requirement for monthly budget, actual cost and OCI-native projected month-end cost. It does not
add security findings, shut down resources, impose quotas or provision OCI budget alerts. D7/D30 and
the accepted organization/configuration boundaries remain binding. This initial slice proposes the
screen/field contract and an [interactive walkthrough](../walkthroughs/financial-walkthrough.html#tenancies). D41–D46 choices are accepted; D46 approves the final D45 dashboard layout and independent monetary sort controls. Real-provider qualification remains separate.

Resolve these in order, with bounded interactive walkthroughs:

1. D41 accepted: exact managed child Budget snapshots for the current cycle; history post-V1.
2. D42 accepted: daily collection plus manual refresh. Qualified currency/cycle and freshness semantics remain provider/operational design work.
3. D43–D46 accepted: independent forecast/actual highlights, retrieval-only tooltip, one dashboard and separate Actual/Budget sort controls. Final dashboard layout approved.
4. Next: [collection/facade/decimal/interval contract](15-collection-and-operational-events.md), publication guards and simulator failure cases.
5. Operational alert/history integration and model/ER/screen audit, then checkpoint before C6.

The two existing proposed financial tables remain sufficient for this slice. No new table, migration,
SDK dependency, production job, implemented application dashboard or live OCI query is introduced. HTML is an inert design preview.

## D41: accepted current-cycle child-budget source

Accepted 24 October 2026. Use the existing child automation credential and exact bound OTM root Budget
OCID with `BudgetClient.get_budget`. Capture `amount`, `actual_spend`, `forecasted_spend` and
`time_spend_computed` from the same read. The forecast is the complete cycle-end estimate, not a
remaining amount to add to actual. No application estimate or parent Usage API fallback is V1.

Historical budget/cost reporting, backfill, past-month selection and trend analysis are post-V1.
Retained immutable snapshots support last-known display/audit/recovery, not a promise of a historical
reporting API. The earlier parent-first recommendation is superseded; parent-owned budgets are not
introduced. All source calls stay behind the existing facade and child context, with bounded per-child
jobs and independent failures. No new credential type or database table is needed.

Pin exact child, budget binding/generation/OCID, source profile, configured budget expectation,
observed amount, cycle and computation time. A missing object is a managed configuration/access issue
and unavailable financial source, never zero spend or permission to adopt another budget by name.
A valid GET may still return unavailable or stale spend values. Changing configuration does not
manufacture a new forecast. No automatic source substitution masks missing access.

The Budget model has no explicit currency field. Use qualified customer rate-card currency and
record its profile provenance; do not assume USD. Qualify monthly processing type/offset/boundaries,
no-alert budget computation and cycle rollover. OCI computation time and OTM retrieval time are
distinct; unknown computation time is not inferred from the GET. Prior-cycle evidence cannot be
relabeled as current-cycle figures after rollover. Actual and forecast availability remain separate.

D42 accepts daily automatic reads plus manual Refresh costs. Retain provider computation time and OTM retrieval time separately. Neither manual refresh nor a new daily job forces provider recalculation or extends source freshness. Exact scheduling time/jitter and qualified freshness cutoffs remain runtime policy, not a claim of a provider update SLA.

## Proposed screen journey

### Tenancies: one combined dashboard — D44

D44 accepts one Tenancies list; there are no Inventory/Costs tabs or competing tables. The common
Tenancies menu opens `financial-walkthrough.html#tenancies`. Legacy financial `#costs` and
configuration `#tenancies` links funnel to that same canonical dashboard. Selected tenancy detail
remains separate, with Back to Tenancies restoring valid search/filter/sort/page context. There is
no new top-level menu or alternative Organization screen. The actual working prototype is unchanged.

Consolidate inventory, configuration and finance into these five columns:

| Column | Primary and secondary values | Source / guard |
|---|---|---|
| Tenancy | Linked name; Individual/Shared; active people count including owner; cost-data information control | Registry + distinct active owner/member associations; an owned individual tenancy counts1, not0; never invent members or count one person twice |
| Owner / LOB | Linked current owner and configured LOB | Current owner association plus selected applied organization revision; direct manager stays searchable and available in detail |
| Configuration | Assigned baseline, Create/Edit override, clickable configuration issue indicator | Stored desired assignment with pending/verified context, existing override flow and exact/filtered issue links; current-for-new is not the assignment |
| Actual / Budget | Current-cycle actual and same-read observed budget in one paired cell; desired override secondary when pending | D41 coherent snapshot and independent availability; D43 red Actual over budget when qualified actual strictly exceeds observed budget |
| Forecast | Complete cycle-end estimate, independently highlighted amber when above observed budget | D41 forecast alone, never actual+forecast; D45 independent per-value presentation and qualification |

Use the cost-data information control for OTM retrieval time and optional data status/cycle only; do not expose OCI computation time in this list tooltip. It must open
on keyboard focus and touch/tap as well as hover, with accessible labels and a dismissal path; no
hover-only information. Unknown computation time remains explicitly unqualified through data status; a known retrieval timestamp cannot substitute for it. **Important missing/stale/prior-cycle/
unverified-currency or pending-data labels stay visible in the row**, not hidden in that tooltip.
Keep spend status distinct from data status. A timestamp tooltip cannot hide an unavailable forecast
or make old data look healthy. Exact source/cycle/currency remains available in tenancy detail.

Preserve tenancy/owner links, direct-manager search, LOB filtering, sort controls, numbered pagination,
row ranges, owner-inclusive counts and summary statistics. Counts/totals use the full filtered result,
not just the visible page. Unavailable amounts never sort as zero. The current cycle and qualified
currency remain explicit; no past-month selector, extra cost editor or history product is introduced.
The five-column direction is accepted. D44 source/layout validation (private historical evidence; not distributed) passes; D46 records final dashboard visual acceptance; provider qualification remains separate.

For incomplete or incomparable totals, show availability/coverage rather than a misleading fleet sum.
A known subtotal, if later included, must be labeled as a subtotal with its exact contributing count;
it cannot be the unqualified fleet total. Do not sum currency, billing basis, subscriptions or intervals
that the qualified source profile cannot compare. Preserve the selected organization revision for
LOB navigation; the V1 view uses labeled current management attribution. Historical financial attribution is deferred and would require a separately reviewed field contract; this slice does not promise a stored finance organization revision.

A collection-refresh action queues observation work and keeps prior values visible until qualifying
results publish. Loading a dashboard, sorting or paging performs no synchronous per-row SDK requests.
The current fleet action is [Refresh all data](../reference/fleet-refresh.md), including costs plus independent user/access/inventory and assigned-configuration reads across eligible registered children; tenancy detail Refresh costs targets only that child. Show the scope explicitly. Reuse matching active collection work under the same context/cycle, and preserve request idempotency; daily and manual request delivery cannot publish mixed responses or defeat capacity reserved for credential work. It cannot force OCI to recompute spending. Collection progress belongs in Operations.

### Selected tenancy: costs and configuration

The combined row opens the exact registered tenancy's detail, retaining current-cycle context and return
filters; Back to Tenancies returns to the single dashboard. Show budget, actual and projected month-end cost as separate facts, with currency, source,
collection timestamps and availability. A missing forecast does not hide independently available
actual cost. A monthly root budget is a soft comparison threshold, not a spending cap.

Budget changes use the existing single-tenancy Configuration override flow. Do not introduce a second
budget editor here. Show the recorded desired configuration and last verified budget context
separately during updates or drift. Do not present a newly saved override as an already deployed
budget. Compare against the same-read observed budget, not the desired override. A pending change does not hide a known overrun against the still-observed amount. Unqualified scope/currency/cycle/freshness blocks evaluation; pending/different configuration is a separate fact. A fresh cost snapshot does not close configuration issues.

### Required data states

| State | Proposed treatment |
|---|---|
| First collection not completed | Desired budget may be labeled as configuration; financial snapshot/costs show Not collected, not0 |
| Actual and forecast available/comparable | Separate values plus qualified month-end comparison |
| Actual available, forecast unavailable | Preserve actual; show Forecast unavailable with safe diagnostic |
| Prior value retained after failure | Show old value/time as stale plus latest collection failure; no silent zero replacement |
| One child fails or its budget is missing | Show that child unavailable and fleet coverage incomplete; other children continue |
| Mixed currency/basis/period | Keep facts visible in their own context; no combined percentage or total |
| Desired budget pending or observed drift | Show pending/review state and configuration link; no false effective budget |
| Collection in progress | Preserve last known result; show pending progress without claiming newer provider data |
| Budget forecast returned | Treat as complete cycle-end total; never add actual spend |
| Month rollover with only prior-cycle evidence | Current-cycle value unavailable until a qualified current-cycle read; no historical reporting/backfill in V1 |

D43 spend indicators are accepted. Exact freshness cutoffs remain operational/provider qualification; preview stale status is seeded evidence, not an adopted 48-hour cutoff.
No cost notification or resource action is authorized simply because a table row is highlighted.

## Initial field coverage: reuse proposed storage

| UI/business value | Canonical source or derivation |
|---|---|
| Tenancy name/OCID/home region/type/member count | Existing proposed registry and current owner/member associations; no new financial identity table |
| Owner/direct manager/LOB | Exact association/person and selected applied organization revision; shared member costs are not charged again to each member |
| Month, source context and billing scope | `otm_financial_collection.expected_period_start/expected_period_end/billing_timezone` and observation `spend_period_start/spend_period_end/period_state`, `source_access_context_id`, `source_tenancy_ocid`, `scope_hash` and source policy revision |
| Actual amount/currency | `otm_financial_observation.actual_spend`, qualified `currency/currency_policy_revision/currency_evidence_event_id` and spend-cycle evidence |
| Native forecast amount/semantics | `otm_financial_observation.forecasted_spend`, `forecast_semantics=complete_cycle_end` and qualified cycle; unavailable stays null |
| Projected monthly total | Provider Budget `forecasted_spend` directly; no actual-plus-forecast composition or extrapolation |
| Budget amount/context/change pending | `observed_budget_amount` from the same child-budget snapshot plus explicit assigned configuration; `budget_binding_id/budget_binding_generation/budget_ocid`, `budget_configuration_id` and optional `budget_observation_check_id` pin context |
| Availability/coverage/diagnostic | Observation `budget_availability/actual_availability/forecast_availability/diagnostic_code`, `period_state` and collection `coverage/state` for the exact child |
| Last collected / source as-of / stale | Observation `captured_at/time_spend_computed/fresh_until` and collection `completed_at`; source calculation time is not fetch time |
| Rollup attribution | Current associations and one labeled selected applied organization revision for V1; no financial observation organization-revision column or historical attribution is promised |
| Spend status/percent/summary | Derived only from comparable qualified facts and versioned tool-side display policy; no duplicate mutable financial truth |
| Refresh action/progress | Accepted C2 operation, collection and logical occurrence key; request idempotency and generation guards apply |
| Search/filter/sort/page/return link | UI/query state, not new database columns; stable page and source capture selection required |

Immutable evidence and source references already live in the financial/operation/configuration model.
If the later screen review needs an additional durable field, update chapter11 and the finance ER
alongside this map before calling the slice complete. Historical reporting and per-service/trend charts are post-V1; they require a separately reviewed source/granularity contract.

## Research and facade qualification: 24 October 2026

Oracle's [Budget model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/budget/models/oci.budget.models.Budget.html)
defines amount in the customer rate-card currency, actual spend for the current cycle, forecasted
spend by cycle end and the time spend was computed. [GetBudget](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/get-budget.htm)
retrieves that object by OCID. Qualify nullable spend/calculation fields, currency provenance, processing
period/offset and cycle rollover, root-wide scope, permissions/endpoint and decimal normalization.
Do not claim conversion of SDK floats recovers precision lost in transport; specify supported rounding
and observation precision in the adapter contract. No live OCI query or budget mutation occurred.

Verify that our no-alert-rule budgets populate spending and forecast. The documented 24-hour alert
evaluation is not a guaranteed recomputation contract for every budget. A Refresh action re-reads
provider state and cannot promise a newly computed forecast. Missing/unverified fields remain explicit.

The source inventory stays pinned to SDK 2.188.0/commit
`df5a803743d2560ec37ef5d1e437d5978ef7d33a`. The existing `get_budget` candidate now serves V1
configuration and financial observations. Usage API calls remain reference-only post-V1; the original
parent-first research was not accepted and cannot remain a V1 source requirement.

## D42 accepted: daily and manual collection

Accepted 24 October 2026. Schedule one logical read per eligible child per day. Duplicate delivery
reuses its occurrence; a deliberate manual refresh has a new command key but may join already-active
matching work. Dashboard reads remain database-only. Disabled/pending UI controls are convenience,
not server authorization or deduplication. Each child publishes or fails independently, preserving
last-known current-cycle values with explicit age/failure. Daily work and manual work preserve the
same target/context/generation/period guards. Source age always uses OCI computation evidence;
a successful re-read of old values does not make them newly calculated.

## D43 accepted: separate spend and data indicators

Accepted 24 October 2026, option A. For qualified comparable observations, actual spend strictly greater
than observed budget is red/Actual over budget. Under the D45 refinement, complete cycle-end forecast strictly greater
than observed budget is independently amber/Forecast over budget, including when actual is also red. No 80% early warning. Equal-to-budget values may
show neutral At budget; each qualified lower value may be highlighted green independently. A green actual value with a missing forecast does not imply healthy projected spend. Known actual overruns remain
visible even if forecast is unavailable. No percentage calculation substitutes zero for a missing field.

Data status is a separate field/badge: current, forecast unavailable, source out of date, budget missing,
not collected, previous cycle only, currency unverified or budget change pending. Unknown currency,
source age or cycle cannot produce green financial health. Pending desired budget is labeled separately;
comparison uses the actual observed budget until the provider object changes. These are view derivations,
not mutable status columns. The workspace’s versioned financial display policy captures this rule;
there is no OCI alert rule, cost-email dispatch, resource shutdown or other mutation.

## Walkthrough and exact UI field audit

D44 supersedes the earlier separate inventory/cost-list layout. One five-column Tenancies dashboard
combines the existing fields; the selected tenancy detail and Configuration override flow remain.
The common menu and legacy list aliases must lead to the same dashboard. Configuration detail may
retain View costs linking that same tenancy's detail; this is not a second inventory/list.

Search (including manager), LOB filter, page size, sort state, pages/range and return navigation are
transient query state. Name/type/owner-inclusive people count use registry/associations; Owner/LOB
uses current owner plus selected organization revision. Configuration uses recorded assignment,
override and issue records. Actual/Budget/Forecast use the same qualified immutable Budget snapshot.
D45 number backgrounds, accessible per-value status labels and hover titles derive independently from qualified actual/forecast comparisons against `observed_budget_amount`. List tooltip retrieval time derives from `captured_at`, with optional existing data status/cycle; it does not expose `time_spend_computed`. That computation timestamp remains stored and participates in internal stale-data qualification and technical detail. Visible degradation/pending labels derive from existing availability and collection evidence. No new status column/table is required.

Cost detail retains observed budget/actual/forecast, desired/pending amount, owner/direct manager/LOB,
type, source/capture times, cycle/currency provenance, root source, budget OCID and binding generation.
Refresh all data includes costs for eligible children across all filters/pages; detail Refresh costs targets one child. Its independent admissions and non-frozen retry boundary are documented in the [implemented fleet reference](../reference/fleet-refresh.md). Pending collection
is C2-derived in production, transient only in the fixture. Acceptance preserves displayed values/
timestamps and does not clear drift, force OCI recalculation, send mail or run a worker in this HTML.

Scenario controls are collapsed sample tools, not a product workflow: current, stale calculation,
missing budget, no collection, prior cycle, unknown currency and pending override. The normal screens
contain concise task copy. Fixtures use integer cents only for local rendering; production uses the
qualified decimal contract. No screenshot or JS transition qualifies provider behavior or a source
freshness SLA. Shared-menu links, mobile overflow/targets, filters/return navigation and source/model
coverage are part of the review evidence.

Historical D43 separate-list validation (not D44 source approval): review and captures (private historical evidence; not distributed)
record 99 passing browser checks plus retained model/doc/syntax/lint checks. Source-only verified
checkpoint: `.local-dev/checkpoints/d43-design-2026-10-24/`. No production database or provider state
changed; cost layouts remain ready for user review.

## D44 accepted: consolidated Tenancies list

24 October 2026. Replace separate Inventory/Costs lists with one five-column dashboard: Tenancy,
Owner/LOB, Configuration, Actual/Budget and Forecast. Reuse existing canonical records/derivations;
there are no new model columns, tables or API authoring sources. Timestamp details may move to an
accessible hover/focus/tap information control, while important data errors remain visible. D41
child-Budget source, D42 daily/manual collection, D43 spend/data semantics and post-V1 history scope
are unchanged. The existing D43 review describes the earlier layout; it is not validation of D44.

## D45 accepted: independent numeric highlights and retrieval-only list tooltip

25 October 2026. Keep the unified five-column dashboard. Replace redundant second-row spend badges with backgrounds on the actual and forecast numbers, evaluated independently against the same qualified observed budget: actual strictly above budget is red; forecast strictly above budget is amber. Grant at actual240 / budget200 / forecast320 therefore shows red actual and amber forecast simultaneously. Qualified below-budget values may be green; exact-at-budget and unqualified/unavailable values remain neutral. Use screen-reader-only per-value status and hover titles to preserve textual meaning without another visible spend-status row. The list has no overall warning badge; technical detail may retain a highest-severity summary alongside independently highlighted values.

Important missing/stale/prior-cycle/unverified-currency and pending-budget labels remain visible. The hover/focus/tap cost-data tooltip shows OTM retrieval time, optionally status/cycle, but no OCI calculation timestamp. Retain `time_spend_computed` in the immutable snapshot, internal freshness/cycle qualification and technical source detail; retrieval never makes old computation fresh. Desired budget remains secondary until observed. D45 supersedes only D43's exclusive overall-warning presentation, not D41 source/comparison rules, D42 cadence, data qualification or post-V1 history scope. No tables, model fields, cost automation or historical reporting are added. D45 final design/UI review (private historical evidence; not distributed) passes 38 browser journeys and 84 responsive/popup checks with independent source/screenshot review. D46 subsequently approves the final dashboard; provider qualification remains separate.

## D46 accepted: visual approval and separate Actual/Budget sort keys

25 October 2026. The final D45 dashboard is visually approved. The Actual/Budget header remains one
visual column with two independent controls: `sort=actual` maps to `actual_spend`, and `sort=budget`
maps to same-read `observed_budget_amount`, not configured/pending budget. One active `asc|desc`
selection is sufficient; selecting a different key starts ascending and selecting the same key
reverses it. Null/unavailable values stay last both ways. Sorting resets page1 while retaining
search/filter/page size, and detail return restores the valid table state. Deterministic ties use
stable tenancy ID, rather than unstable provider or database row order. Server-side query/DTO design
must retain these semantics; no extra model column is needed.

The D45 evidence (private historical evidence; not distributed) remains the
recorded browser/layout review. This acceptance update introduces no new runtime behavior. The
[next design contract](15-collection-and-operational-events.md) moves behind the approved screen.


## C5 typed-contract handoff — 25 October 2026

The approved D46 screen remains unchanged. [Chapter16](16-c5-contract-review.md) maps each normalized
collection/snapshot field to existing proposed storage, including same-response monthly facts in
`period_evidence` and profile-derived currency minor units. Its exact-decimal display rule expands
precision when ordinary rounding would hide a strict over/under comparison; it does not round the
comparison threshold. Production generated-client/query tests must carry these semantics forward.

## Implemented local milestone — 5 November 2026

The [runtime financial guide](../reference/cost-visibility.md) maps these journeys to real contracts,
HTTP/worker/UI and SQL. One five-column Tenancies dashboard includes inventory and independent
Actual/Budget/Forecast sorting. Retrieval-only tooltips, per-value unavailable labels, neutral retained
degraded data and async refresh preserve the approved screen. No separate cost dashboard is added.
