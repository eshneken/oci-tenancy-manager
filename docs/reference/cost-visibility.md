# Current-month cost visibility

Status: implementation candidate; final validation and saved-instance installation are pending.

This milestone adds stored current-month financial visibility to the existing Tenancies list and
detail. It uses a read-only Budget facade and the native durable worker. Local reads are explicitly
simulated: the managed observed Budget supplies the budget; actual and forecast are synthetic zero.
There is no OCI connection, daily scheduler, simulator-control screen or historical reporting product.

## Administrator flow

1. Create/import a tenancy and finish its simulated onboarding, including the managed baseline.
   An active registered child needs its retained managed Budget OCID before a read is eligible.
2. On **Tenancies**, choose **Refresh costs** for the eligible fleet, or open a tenancy and choose
   **Refresh costs** in **Current month costs**. Refreshing the view alone never calls the provider.
3. Admission returns promptly. Compatible pending work is joined. Polling shows stored results
   without a page reload; the acceptance message clears once its operations finish.
4. Use **Actual**, **Budget** and **Forecast** sort controls. The list has five visual columns:
   Tenancy, Owner, Status, Actual/Budget and Forecast. Type/member count, industry segment and compact
   baseline/override/configuration indicators retain their existing contexts.
5. Open the retrieval info control by keyboard, hover or touch. It shows only **OTM retrieved**.
   Detail's optional **Source details** retains OCI computation time and the derived source interval.

Red marks actual above the **observed** budget; amber independently marks month-end forecast above
that budget; qualified values below budget use green. Equal or unqualified values remain neutral.
Screen-reader descriptions carry the same meanings. Missing values stay unavailable, never zero.
Normal currency display uses two places, expanding to four when rounding would hide an overrun.
A desired budget override can appear separately in detail, but never substitutes for the read budget.

## Data states

| State | Meaning / display |
| --- | --- |
| `not_collected` | No compatible facts; read not yet completed or no eligible managed Budget |
| `current` | Coherent current-cycle qualified response, both ages within configured limits |
| `partial` | Current qualified response lacks budget, actual or forecast; show each missing value |
| `stale` | OTM retrieval or provider computation age exceeded its own threshold |
| `prior_cycle` | Provider computation belongs to another monthly cycle; retain the original interval |
| `unavailable` | Acquisition failed; retain compatible facts with their original timestamp, neutral colors |
| `unqualified` | Scope-valid facts have unverified currency/cycle, or validation failed |

`pending` is independent of data state. Retried or newly queued reads do not hide continuing failures
or recolor old retained facts green. A coherent newer partial response replaces the old full response;
OTM never borrows the old forecast. Provider computation time orders observations; retrieval breaks
ties. A late older computation cannot displace newer facts. Changed configuration/target/access/profile
invalidates compatibility; no HTTP GET performs per-row cloud calls or repairs configuration drift.

## Read contract and safety

`POST /api/costs/refresh` accepts only a UUID `client_request_key` and optional registered `tenancy_id`.
It uses existing administrator/session, Origin and command-header guards, a 4096-byte body limit and
closed fields. No client-supplied workspace, OCI endpoint, credentials, currency or Budget OCID is
accepted. Fleet scope means all eligible active registered children, independent of page/filter.

Acceptance, immutable intent/audit, collection heads, native reference-only enqueue and replay receipt
commit together under the existing workspace lock. A replay returns its original receipt even after
completion. A deliberately new compatible command joins active work. Concurrent commands cannot
create duplicate active context reads. The worker claims a bounded attempt, commits, performs its
read **outside** database transactions, then rechecks authority and exact current context before
publishing. Attempt identity fences duplicate/late results. Configuration/credential mutations do not
occur. Operation results remain read-only history; failed cost reads do not create action badges.

The facade returns one exact managed Budget response: amount, actual, forecast, computation time,
retrieval time, root-compartment target and cycle facts. Money is a canonical finite decimal string
with four places, at most 16 integer digits. Signed spend adjustments and nullable amounts are valid;
negative budget, NaN/Infinity, exponent strings, floats, excess scale and overflow are rejected.
Currency is **not** a Budget response field. Only the explicit local `simulated-usd-utc-1` profile
qualifies USD and a UTC monthly day-one cycle here. Unknown/one-time/mismatched cycles are not guessed.
Live SDK, billing currency, timeout, permissions and calculation-clock behavior still need OCI qualification.

## Storage field dictionary

Migration **0021_financial_collection** adds two tables (22 application tables total). Existing
operation, step, audit and notification-outbox tables are reused. This is actual application storage,
not prototype-only data. See the [implemented financial ER](../architecture/diagrams/financial-implemented.mmd).

| Table | Fields / responsibility |
| --- | --- |
| `otm_financial_collection` (15 columns) | `id`, `workspace_id`, `tenancy_id`, `operation_id`; immutable `context`/`context_hash` capturing child/name/OCID, parent/org, configuration generation/versions/bindings, source access binding, CostPolicy and expected cycle; strict `source_hash`; stable `failure_scope_hash`; mutable `state`, `attempts`, `attempt_id`, `next_attempt_at`, `safe_code`, `updated_at`; immutable `created_at` |
| `otm_financial_observation` (17 columns) | `id`, `workspace_id`, `tenancy_id`, `collection_id`, `context_hash`, `source_hash`, `budget_ocid`; `observed_budget_amount`, `actual_spend`, `forecasted_spend` as nullable numeric(20,4); nullable `currency`, `time_spend_computed`, `period_start`, `period_end`; `captured_at`; complete immutable `snapshot` and `snapshot_hash` |

Observation's composite FK includes workspace, collection, child, strict context hash and source
hash. Readers validate its exact collection target and profile, JSON hashes and query columns.
Collection context/creation identity cannot change; attempts are monotonic and terminal heads immutable.
Observations cannot update/delete/truncate. Application runtime grants continue to prohibit DDL and
immutable-history rewriting. Existing explicit local reset includes both tables and blocks pending work.

Collection states are `queued → reading → retry → reading` (bounded), then `succeeded`, `failed` or
`superseded`. A normalized response with missing optional values or unknown cycle is a completed read,
not acquisition failure. A malformed response with no observation never proves recovery. Due retries
use native queue scheduling on the same operation; workers do not sleep. The default has two delays,
30 then 120 seconds, so at most three provider attempts occur.

Strict source identity fences configuration generation and the full cost policy; failure-episode
identity instead contains child/OCID, parent/org, managed Budget OCID, access binding and provider
profile. Baseline/override edits, month rollover and retry/age setting changes alone do not reopen a
continuing incident. A normalized observation from that stable source resets it.

## Failure emails and settings

D48 acquisition emails use the existing outbox and **Email delivery** audit category. After bounded
retries exhaust, freeze one notice per stable continuing child/source episode and active administrator.
D50 lifecycle responsibility is independent. Before delivery, recheck current grant, stable source,
recovery, environment contact policy, origin and transport. A changed budget/access source supersedes
old notices; unrelated baseline/timing changes do not suppress an unresolved incident's only email.

No email is sent for over-budget values, absent optional forecast, stale calculation, cycle/currency
qualification or discarded obsolete work. Local/staging capture and production release guards remain
in force; no employee contact is delivered during tests.

`[costs]` in application.toml defines the explicit profile, independent retrieval/source maximum ages
(default 86400 seconds each, range 1–604800), and 0–2 read retry delays (each 1–3600 seconds).
Configuration changes use the existing coordinated config rollout/restart; they require no image
rebuild and cannot silently retarget admitted jobs.

## Qualification boundary

Unit-only complete-source coverage remains at least 95% independently in backend/frontend. Disposable
PostgreSQL tests cover constraints, immutable contexts, joining/concurrency, retry failure isolation,
late/partial facts and source/authority changes. Real HTTPS/Playwright tests cover fleet/detail refresh,
independent sorting, automatic result refresh, retrieval accessibility and 1280/390/320 layouts.
Independent documentation, UI/UX and security review are required before milestone completion.

Daily cost collection is deferred with drift scheduling to staging/Kubernetes: qualify noninteractive
machine authority and occurrence idempotency, then enqueue the same durable read path. No browser
session bypass, local timer or temporary production-only scaffolding is added here. Historical budget
reporting and over-budget emails remain outside V1.


## Public and internal contract field map

These ten financial models contain 77 fields, not additional database tables. Python validators
are authoritative; generated structural contracts live in backend/contracts. Their internal nested
context snapshots preserve exact immutable request/source evidence; view-only fields are derived.

| Model | Fields and their meaning |
| --- | --- |
| `CostPolicy` | `profile`: qualified adapter/currency/calendar identity; `retrieval_max_age_seconds` and `source_max_age_seconds`: independent freshness thresholds; `retry_delays_seconds`: bounded acquisition retry schedule |
| `CostRefreshRequest` | `client_request_key`: replay identity; nullable `tenancy_id`: one registered child, otherwise the eligible fleet |
| `CostRefreshReceipt` | `operation_ids`: exact accepted/joined work; `accepted_count`, `joined_count`, `skipped_count`: candidate disposition; `accepted_at`: command time; `provider_mode`: explicit simulation |
| `CostTarget` | `configuration`: existing CheckTarget containing exact registered child/parent/org/configuration/binding identities and hashes; `budget_ocid`: exact retained managed object; `source_access_binding_id`: trusted provider access source; `profile`: frozen CostPolicy; `period_start`, `period_end`: expected read-cycle boundaries |
| `CostIntent` | `contract_version`, `kind`: fixed capability/version; `workspace_id`: server-derived scope; `administrator_id`, `authorization_revision`: current authorizing grant; `targets`: immutable unique children; `target`: human display label and optional single-child OCID for Operations |
| `BudgetCycleFacts` | `reset_period`, `processing_period_type`, `budget_processing_period_start_offset`: actual provider calendar facts; optional `start_date`, `end_date`: one-time/explicit date qualification |
| `BudgetReadResult` | `budget_ocid`, `compartment_ocid`, `target_type`, `targets`: returned exact root/child scope; `cycle_facts`: returned calendar facts; nullable `amount`, `actual_spend`, `forecasted_spend`: same-response monetary facts; nullable `time_spend_computed`: source calculation time; `captured_at`: adapter retrieval time |
| `CostSnapshot` | `budget_ocid`: source object; nullable `budget`, `actual`, `forecast`: one coherent response; `computed_at`, `retrieved_at`: independent source/retrieval clocks; nullable `period_start`, `period_end`: derived source interval; nullable `currency`, `minor_units`: qualified billing-profile display facts; `profile_hash`: frozen profile; `source_state`: qualified/unqualified; `cycle_facts`: raw calendar provenance |
| `CostEvidence` | `contract_version`, `collection_id`, `tenancy_id`: exact read identity; `state`, `attempts`, `safe_code`: bounded outcome for read-only Operations/Audit; no money or credentials |
| `CostView` | `computed_at`, `cycle_facts`: detail-only provenance; `state`: visible data qualification; nullable `budget`, `actual`, `forecast`, `currency`, `minor_units`: retained coherent facts; `retrieved_at`, `period_start`, `period_end`: original retrieval/source interval; `pending`: queued/reading/retry independent of health; `latest_failure`: continuing safe read failure; `can_refresh`: current eligibility; `operation_id`: latest work link; `desired_budget`: separately labeled pending authored override; `actual_over_budget`, `forecast_over_budget`: independent qualified same-response comparisons |

The separate **CostFailureNotice** model has 15 fields and is frozen in the existing outbox intent:
`contract_version` identifies cost-failure-email-1; `operation_id`, `collection_id`, `tenancy_id`,
`source_hash` retain the failed strict context; `failure_scope_hash` groups the stable incident;
`administrator_id`, `authorization_revision` retain recipient authority; `original_recipient`,
`delivery_recipient`, `route` freeze the environment-safe contact decision; `application_origin`,
`delivery_profile_hash` pin allowed links and transport; `event` is cost_read_failed; `created_at`
anchors the notice/recovery episode. This does not store a mailbox password or provider credentials.

| Existing screen contract extension | Source / behavior |
| --- | --- |
| `TenancyView.costs` | Derived CostView from compatible financial collection/observation rows; both list and detail use the same service |
| `TenancyDirectory.costs_pending_count` | Count pending cost sources across the eligible registry, independent of displayed page/filter |
| `TenancyDirectory.can_refresh_costs` | At least one active registered Budget source is currently eligible; never grants authority by itself |
| `TenancyQuery.sort` values `actual`, `budget`, `forecast` | Allowlisted Decimal sort over qualified current/partial observed values; missing or unusable last in both directions, stable child-ID ties |

No amount, failure state, sorting projection or navigation affordance is a second source of truth.
