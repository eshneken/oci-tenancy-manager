# 05: usage, financial visibility, operational notifications and history

28 October 2026 | C5 design review candidate; implementation/provider qualification separate | D41–D50 source, cadence, dashboard and operational delivery decisions accepted

[Design hub](README.md) · [Financial specification](../product/oci-tenancy-manager-spec.md#monthly-cost-and-forecast-source) ·
[Financial journeys](14-financial-journeys.md)

## Accepted V1 financial source: D41

Read each child's exact OTM-managed root budget using its existing child automation context and
`BudgetClient.get_budget(budget_id)`, behind the OCI facade. One read supplies `amount`, `actual_spend`,
`forecasted_spend` and `time_spend_computed`. Persist the snapshot for the current monthly budget
cycle and serve dashboard data from the database. No per-row synchronous OCI calls from a dashboard.

The forecast is the provider's estimate of total spend at cycle end. Display it directly; never add
actual spend to it. D7's OCI-native-only requirement remains satisfied, without application forecasting
or automatic parent Usage API fallback. Parent-owned budgets are not substitutes for the child-owned
managed object selected by D30. Use its stored OCID/binding, not a search by display name.

Historical budget/cost reporting, prior-month selectors, trends, parent Usage API reporting and
historical backfill are post-V1. Retaining immutable collection evidence and a last-known value for
correctness/audit does not introduce a historical reporting feature. Administrative and organizational
history requirements are unchanged.

## Period, currency, freshness and configuration

Use the qualified monthly processing cycle of the bound budget, not the browser's time zone. The
baseline's monthly root budget and overrides remain configuration truth. The observed amount is the
actual object value at collection time, not a separate authoring source. Pending overrides and confirmed
budget drift remain visibly distinct; saving an override is not proof OCI applied it.

The Budget model expresses money in the customer's rate-card currency but has no explicit currency
property. Capture verified currency/billing-context provenance in the versioned source profile and
snapshot. Never assume USD, copy the hosting tenancy's currency or aggregate unqualified currencies.
Qualified comparable scope, cycle, currency and cost basis are required for totals/percentages.

Keep OTM collection time and OCI `time_spend_computed` separately internally. The approved dashboard tooltip shows OTM retrieval time only; technical detail may expose computation time. A recent GET is not a forced provider
recalculation. Optional/missing actual, forecast or computation time remains explicitly unknown; it
never becomes0. Keep source age separate from collection failures. A prior cycle's cached values
cannot become current-month figures merely because a retry or page load occurs after month rollover.
Historical-cycle evidence stays retained but is not a current-cycle reporting fallback.

Each child has independent collection success/retry state. Use C2 bounded jobs, logical occurrence
keys and backoff. Reuse a bound-budget read for configuration observation only under its qualified
coverage/generation contract; financial success does not certify the entire configuration or clear
an unrelated drift issue. Keep credential rotation capacity reserved. D42 accepts daily collection plus manual refresh. D45 independently highlights amber forecast over budget and red actual over budget, including simultaneous overruns, with separate data availability/freshness. No 80% early warning or cost notifications. Exact operational/source-freshness policy still requires qualification; retrieval cannot force provider recalculation.

## Proposed data and interface

[Chapter11](11-production-data-model.md#financial-collection-and-observations) specifies the two
proposed financial tables and [chapter14](14-financial-journeys.md) maps screen fields to storage.
Budget/actual/forecast from one provider read retain exact child, binding generation, source budget,
cycle, observed amount, configured expectation and computation timestamp. Decimal normalization,
nullability, source profile and row selection must be qualified before production use.

The single combined Tenancies dashboard and selected-tenancy cost detail show current-cycle budget/actual/forecast,
LOB/owner, explicit source and freshness, pending collection and unavailable/error states. No historical
month picker or trend chart is V1. Budget edits reuse the existing Configuration override flow.
The [financial walkthrough](../walkthroughs/financial-walkthrough.html#tenancies) is visually approved under D46, including the separate Actual and Budget sort controls. It remains an inert sample, with no new production application page or database migration.

## Operational observation and notification design

Keep access/configuration observations, incidents, administrative history and financial evidence distinct.
Required operational alerts follow committed triggers; manually composed notices require Send.
Deduplicate continuing incidents, preserve routing/retry evidence and handle unresolved recipients.
D47 selects email only in V1; Slack is deferred behind an extensible delivery interface. Credentials never enter notifications. Delivery uncertainty is not permission to resend blindly after
an unknown outcome or restore. Security-findings CSVs and security auditing remain V2.

Remaining C5 outputs: reviewed financial prototype/data/freshness/status policy and page states, exact snapshot
facade/schema and failure fixtures, collection scheduling/query plan, and operational notification/
incident/history contracts. Display thresholds are separate from D30's no-OCI-alert budget; a cost
highlight does not authorize resource mutation or notification by itself. Retention and database
operations remain C6 work; no historical cost product is implied.

## Provider evidence and remaining qualification

Oracle's [Budget model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/budget/models/oci.budget.models.Budget.html)
documents current-cycle actual spend, cycle-end forecast, amount and spend-computation time.
The [GetBudget guide](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/get-budget.htm)
confirms retrieval by budget OCID. Qualify real permissions/endpoint, root-wide target scope, monthly
cycle/rollover, rate-card currency, optional values and decimal handling. Verify spend/forecast
population for our budgets with no alert rules; do not infer a guaranteed recomputation interval
from the documented alert-evaluation interval. No live OCI test has been performed.

Parent cost/Usage API research remains reference evidence for post-V1 reporting only. D41 supersedes
the earlier parent-first recommendation and Usage API-specific financial collection design.

## Next C5 slice

[Chapter15](15-collection-and-operational-events.md) makes the collection/publication path and
operational-notification boundaries concrete. Its implementation mechanics elaborate accepted
invariants; pending routing/failure-notification decisions remain proposals. C5 stays open until the
remaining contracts, field coverage and failure fixtures have been reviewed. C6 follows; the
prototype, production schema and OCI environment are not modified by this documentation pass.

## D47 accepted: email delivery only in V1

25 October 2026. Required operational notices use email. No Slack adapter, setup, token or dispatch
is included in V1. The channel-neutral intent/outbox interface remains extensible. Existing automatic
trigger/recipient/urgency, manual Send, frozen routing, uncertainty and recovery safeguards remain.
Provider acceptance is not confirmed inbox delivery. [Chapter15](15-collection-and-operational-events.md#d47-delivery-contract-email-in-v1)
records the delivery port and field mapping; provider/sender/network qualification stays in C6.
D48 selects one administrator email after bounded failed financial-read retries are exhausted; cost-overrun emails and security-findings workflows remain outside this V1 decision.

## D48 accepted: exhausted acquisition retries

25 October 2026. Financial read failures are immediately visible and retry under bounded runtime
policy. Retry exhaustion opens one admin email incident; continuing daily/manual/retry failures reuse
that episode. Verified same-source read recovery closes it internally and relapse opens a new one.
No 24-hour delay, first-transient email, recovery/reminder email, owner-chain expansion or cost-overrun
email is added. Optional unavailable forecast and normal provider calculation lag are separate data
states. Exact retry/backoff remains C6 configuration. [The episode contract](15-collection-and-operational-events.md#d48-accepted-alert-after-automatic-cost-read-retries-are-exhausted)
uses existing audit/collection/operation/outbox records and source/publication guards; urgent access
and rotation requirements remain unchanged.

## D49 accepted: lifecycle attention, not routine progress

25 October 2026. Accepted create/import/delete, transfer, membership and offboarding workflows email
when an administrator must act or when the operation reaches known terminal failure. Provider/retry
waits and routine progress/success remain in Operations. Unchanged attention deduplicates by exact
operation/intent/action episode; unknown effect is not terminal failure. [The lifecycle contract](15-collection-and-operational-events.md#d49-accepted-lifecycle-email-only-for-action-or-terminal-failure)
uses existing state/audit/outbox fields and retains partial-resource context. D50 selects the responsible administrator only, with no all-admin or owner-chain routing fallback. D47, D48 and urgent access/credential notices stay binding.

## D50 accepted: responsible-admin-only lifecycle routing

25 October 2026. Lifecycle action/failure emails go only to the current responsible administrator,
initially the initiating admin and changeable through explicit audited takeover. No automatic
all-admin fallback or copies to owner/manager/designee are selected. Unresolvable, unauthorized or
confirmed-undeliverable routing stays visible in Operations until explicitly corrected or taken over.
Existing D48 and access/recovery/rotation recipient sets remain. [The routing contract](15-collection-and-operational-events.md#d50-accepted-responsible-administrator-only)
uses existing operation/audit/outbox fields and preserves immutable recipients and unknown-send
reconciliation through reassignment. No new UI/runtime integration or database table is introduced.


## C5 contract checkpoint — 25 October 2026

[Chapter16](16-c5-contract-review.md) records closed request/result shapes, coherent snapshot and
selection cases, exact decimal/profile boundaries, email intent/result/routing examples and model
mapping. It checks49 valid and 43 invalid cases without application/DB/provider execution. Exact
MONTH/day1/UTC processing is an illustrative qualified profile, not an adopted fleet default;
12h/24h freshness limits are fixture inputs. Unsupported source precision/currency/cycle stays
unqualified. Other qualified profiles and runtime concurrency remain implementation/pilot gates.
