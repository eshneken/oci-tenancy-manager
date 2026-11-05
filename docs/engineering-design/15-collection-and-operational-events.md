# 15: financial collection and operational events

25 October 2026 | C5 behavior contract with checked companion examples | Not runtime implementation

[Design hub](README.md) · [Approved financial screens](14-financial-journeys.md) ·
[Execution contract](09-execution-contracts.md) · [Production model](11-production-data-model.md)

## Scope and decision boundary

D46 approves the D45 Tenancies dashboard, including independent Actual/Budget sorting. This chapter
moves behind that screen: accepted daily/manual collection, the OCI facade read, publication,
current-snapshot queries and operational notification delivery. It elaborates D3/D4/D10/D12 and
D41–D50; it does not introduce a new scheduler, cost-history product or notification-driven repair.

The collection mechanics below are the engineering proposal for review. D47 accepts email as the
V1 operational-notification channel; Slack is deferred. Chapter16 supplies the bounded normalization/freshness design and typed examples; actual source precision/cycle/freshness settings still require provider/runtime qualification. D50 selects responsible-administrator-only lifecycle routing. D48 selects one administrator email after bounded automatic cost-read retries are exhausted. Existing immediate required-access/disclosure/rotation notices remain binding; the
channel or cost-read policy cannot suppress them.

No new table or relational column is proposed. Typed audit payload values are traced below to existing proposed storage:
`otm_financial_collection`, `otm_financial_observation`, C2 operation/step records, managed bindings,
versioned workspace runtime policy, `audit_event` and `notification_outbox`. These are production
design references, not a claim that the local prototype implements the worker or delivery system.

## One read per child; one coherent snapshot

```mermaid
sequenceDiagram
    participant T as CronJob or administrator
    participant A as OTM API/scheduler
    participant D as PostgreSQL
    participant W as Python worker
    participant F as OCI facade
    T->>A: Daily occurrence or manual refresh
    A->>D: Transaction: operation + collection + audit + job
    D-->>A: Commit; accepted operation ID
    W->>D: Claim bounded attempt; capture guards
    W->>F: Read exact child budget through its automation context
    F-->>W: One normalized response or typed read failure
    W->>D: Transaction: recheck guards; publish evidence + progress
    A->>D: Dashboard query; no synchronous SDK calls
    D-->>A: Coherent snapshot + latest attempt state
```

The transaction around acceptance includes the initial Procrastinate job under D3. OCI network
calls occur outside database transactions. Completion/audit/retry wake-up updates must be committed
together through the qualified runner integration; no long-held row lock spans a provider request.
A fleet trigger creates bounded per-child work, not one all-or-nothing 250-tenancy transaction.
One failed child cannot roll back another child's observations.

## Scheduling, joining and priority

| Input | Logical identity and action | Durable result |
|---|---|---|
| Daily CronJob | Workspace + child + source kind + configured daily slot; duplicate delivery uses the same occurrence key | One logical child collection; existing accepted occurrence is returned |
| Manual Refresh costs | New actor command key for a deliberate request; re-delivery retains that key | Join compatible active work or accept a new child collection; return operation ID after commit |
| Refresh all costs | Freeze eligible registered child IDs; one bounded child acceptance per target | Report accepted/joined/skipped targets honestly; new children wait for their next trigger |
| Retry | Original collection/occurrence with a new attempt ID and bounded backoff | Does not masquerade as a new user request or a new provider calculation |
| Recovery after restore | D12/D54 deployment maintenance, stopped old processes, held work and reconciled current bindings | Normal dispatch stays paused until release; restored queue does not self-authorize work |

Active-work joining requires the same child, budget binding/generation, source context/policy and
expected current cycle. A changed scope cannot join an older read. Store each manual command
receipt/audit even when several requests return the same active operation; request replay must
return its original accepted result. CronJob concurrency settings are convenience, not deduplication.

Exact daily time, deterministic jitter, timeout/backoff and collection concurrency are versioned
runtime settings to size in C6. They are not child baseline values. Reserve capacity for credential
rotation and preserve per-tenancy mutation coordination. A read may overlap an allowed mutation
with captured context; it cannot promote a stale generation or certify that mutation's completion.
No worker sleeps for a daily schedule or holds a tenancy lock while waiting for a retry.

## Proposed facade port

`read_managed_budget(request) -> BudgetReadResult` is an application-facing read capability.
Production Python DTOs will generate the wire/OpenAPI contracts under D11; this document is not a
second hand-maintained production schema. The real adapter owns `BudgetClient.get_budget`; the
simulator implements the same input/result semantics without importing OCI SDK models into domain code.

| Request component | Source / constraint |
|---|---|
| C2 attempt context | Workspace, operation, step, attempt, intent/execution generation and access binding from committed work |
| Exact child target | `source_tenancy_ocid` and the verified expected child-root scope; never parent/hosting identity substitution |
| Exact budget | `budget_ocid` from frozen `budget_binding_id` / `budget_binding_generation`; no display-name lookup |
| Policy reference | Captured source/currency/cycle/normalization policy revision; not arbitrary endpoint or SDK kwargs |

| Result component | Meaning |
|---|---|
| Read outcome | Observed, unobservable, rejected/unsupported, with typed safe diagnostic and provider correlation |
| Object facts | Returned budget OCID, owning compartment, target type/OCIDs and relevant monthly-cycle facts from that exact response |
| Amounts | Observed budget, actual and complete-cycle forecast, independently nullable and normalized as decimal strings |
| Source time | Nullable provider `time_spend_computed`, distinct from OTM `captured_at` |
| Evidence | Safe response/attempt identity and coverage; no secrets, raw SDK objects or guessed currency |

A successful HTTP response establishes neither correct target scope nor fully usable money values.
Validate exact identity, child-root ownership/targets, monthly scope and policy before publication.
Budget responses have no currency property; qualified rate-card policy supplies that provenance.
Authorization/not-found ambiguity is Unobservable, not proof that the managed budget was deleted.
Only separately authoritative scoped evidence may establish Missing. No automatic object replacement,
credential fallback or budget adoption is permitted on a read failure.

### Decimal and cycle qualification

The existing storage contract uses `numeric(20,4)` and nullable values. Provider SDK floats are not
proof of exact transport precision. The adapter must reject non-finite/out-of-range values and record
its qualified conversion/rounding policy. Presentation uses the qualified currency's minor units;
comparison and rounded display must not produce an unexplained equal-looking overrun. Exact excess-
precision treatment is a remaining engineering/provider qualification item, not silently settled here.
Negative actual adjustments remain valid if the qualified source supports them; do not clamp to zero.

A response is not assigned to the current cycle from retrieval time alone. Use qualified source-cycle
and computation evidence. Unknown computation/cycle remains unverified; old-cycle money is not a
current-cycle fallback. Source and retrieval freshness are separate internal tests even though D45's
list tooltip exposes retrieval only. Exact freshness cutoffs need provider qualification; no 48-hour
cutoff or guaranteed OCI recomputation interval is adopted by this chapter.

## Publication and current-view selection

1. Accept immutable target/context/configuration/source-policy expectations and record the operation.
2. Before dispatch, verify current child eligibility, exact budget binding and authorized access context.
   Resolve the current permitted signer version on that same context; record the version in attempt
   evidence. Ordinary credential rotation cannot retarget the read or rewrite the operation's intent.
3. Read outside the transaction. Normalize one response; never combine optional fields across retries.
4. Publish with current execution/recovery, source-context, binding, policy and relevant configuration
   guards. A result for a replaced budget, obsolete cycle/context or lost worker generation is retained
   as safe attempt evidence/obsolete work, not the current selected snapshot. Schedule a fresh read.
5. Insert at most one immutable observation per collection, using the existing uniqueness constraint.
   Commit observation, operation outcome and audit together. Data can be partial without fabricated
   zeroes. A retry after commit discovers the existing completion rather than inserting another fact.

Dashboard selection reads one compatible observation for each child plus the latest collection outcome.
All amounts, source time and observed budget in a row come from that selected observation. A newer
partial response with unavailable forecast never borrows an older forecast. A failed attempt does not
overwrite money with zero or make retained data fresh. Show retained values with their original age
and the latest failure/unverified condition; a newly confirmed missing object blocks healthy display.

Late completions cannot regress the selected qualified source calculation within the same cycle.
Retain older-response evidence without replacing a newer compatible calculation. Equal source
calculation times may use later capture evidence; unknown/future/invalid timestamps cannot win as
fresh calculations. Month rollover and binding/policy changes are separate selection domains. Final
query/transaction tests must prove this ordering; do not use collection commit order as source age.

A complete Budget observation may also feed a compatible C3 check, but only the normal C3 scope/
coverage/generation predicates can close that configuration issue. Financial success alone cannot
clear Configuration drift, certify required users or advance a fully verified baseline pointer.

## Query and field coverage

| Screen/worker concept | Canonical proposed storage or derivation |
|---|---|
| Source/cycle/target identity | Collection `source_*`, `budget_binding_*`, `budget_ocid`, `expected_period_*`, `scope_hash` |
| One coherent row | Observation `collection_id`, observed budget, actual, forecast, computation/capture times and independent availability |
| Latest attempt/failure/pending | Collection state/times plus C2 operation and attempt evidence, not inferred from old amounts |
| Actual sort | Qualified current-view `actual_spend`, asc/desc, null/unavailable last, stable tenancy-ID ties |
| Budget sort | Same selected observation's `observed_budget_amount`, never desired override; independent key in shared header |
| Forecast sort | Selected `forecasted_spend`, not actual+forecast; unknown last in either direction |
| Desired budget pending | Existing assigned configuration versus observed snapshot; no second budget editor |
| Red/amber/green/neutral | D45 independent comparisons, qualification and versioned display policy; no stored health column |
| Retrieval tooltip | Observation `captured_at` only, optionally existing status/cycle; computed time remains internal/technical detail |
| Filters, page, return state | Client/request state; organization attribution uses selected applied revision; no database sort settings |
| Operational notice | Committed audit/source event and existing outbox intent plus immutable routing evidence |

Queries are database-only, page bounded, whitelist sort keys/directions and retain workspace scope.
Resolve one coherent snapshot before sorting/filtering/aggregation; do not paginate the registry first
and then sort only that page's costs. Counts/totals span the filtered scope. Unknown amounts are not
zero; mixed currency/cycle/basis blocks unqualified totals. Joining members cannot multiply shared
costs. Current organization metadata can change display attribution without rewriting money evidence.

Candidate indexes remain the chapter11 collection-occurrence uniqueness, collection/tenancy/cycle/
capture lookups, operation due-work and scoped-FK indexes. C6 must choose exact covering/partial indexes
from query plans and realistic retained history, not add an index for every sortable column.

## Operational events and delivery boundary

Security findings and cost threshold notifications remain out of scope for V1. A colored spend
amount is not an email trigger. Existing required operational intents remain automatic; manually
composed notices require explicit Send. Sending a notice cannot repair, delete or mutate a tenancy.

| Trigger family | Existing obligation / remaining policy |
|---|---|
| Organization exception or source-quality incident | Durable review/incident and required admin intent; ordinary valid metadata changes do not email every person |
| Confirmed required access/configuration loss | Required scoped alert and existing owner/manager/designee/admin routing; unable-to-inspect is not confirmed missing |
| Recovery password disclosure | Every authorized request commits audit plus notice to other admins and owner/manager before release; shared window does not suppress distinct retrieval notices |
| Failed/overdue/uncertain rotation | Urgent admin incident and independent recovery path; no credential material in notice |
| Lifecycle needs human input/fails | D49 emails for durable administrator action or terminal failure; routine progress/success stays in Operations; D50 recipient is the responsible administrator only |
| Financial acquisition failure / check failure | Failures remain visible; D48 sends one admin email after financial-read retry exhaustion, with no recovery/reminder email. D49/D50 lifecycle and required access/configuration notices retain their separate rules; no additional check-failure escalation is selected |

One continuing incident has one initial source event; repeated identical checks do not create repeated
initial alerts. Verified resolution followed by relapse creates a new episode. Reminders or deliberate
resends need separate committed events; no new reminder product is silently added here.

Source event and notification intent commit with the triggering local transition. Freeze recipients,
manager/LOB/designee routing revision, safe payload and template version. Unresolved contacts route to
admins with visible routing evidence except D50 lifecycle notices, which remain Blocked without
automatic recipient expansion. Channel delivery uses existing outbox records; attempt outcomes
are appended to audit, and delivery heads alone may change. Retry the captured intent, not a newly
looked-up owner list. Partial/unknown delivery requires provider-aware reconciliation; restore is not
proof a message was unsent. Credential secrets, activation links and unrestricted provider logs never
enter email payloads or any future delivery channel. Current recipient entitlement must be checked before sensitive disclosure;
notice delivery itself contains no credential and cannot authorize that disclosure.

D47 is accepted: V1 dispatches email only. Preserve a channel-neutral application port, but do not
implement Slack adapters, setup screens, tokens or delivery in V1. Unsupported channel requests fail
validation rather than silently switching destination. The existing outbox `channel` field is `email`
for V1; keeping an extensible field does not authorize Slack sends. Exact approved email provider,
sender domain/identity, credentials/network endpoint and delivery semantics remain C6 qualification.

## D47 delivery contract: email in V1

Accepted 25 October 2026. Application workflows create channel-neutral notification intents; the V1
worker resolves only the email adapter. The domain boundary is `send_email(intent, attempt_context)`
with an immutable accepted intent reference and bounded safe content, not arbitrary provider commands.
The real email client stays behind a delivery facade alongside the OCI facade boundary. Local and
CI simulation records effects without contacting an email service. This contract adds no runtime code.

### Intent, routing and persistence

| Contract value | Existing proposed source |
|---|---|
| Notification identity and trigger | `notification_outbox.id/workspace_id/source_event_id` and typed issue/operation/grant reference |
| V1 delivery channel | `notification_outbox.channel=email`; server rejects Slack/unknown dispatch channels |
| Frozen recipient set | `recipients/routing_revision/routing_evidence`; addresses plus role/person/administrator provenance, deduplicated by normalized address |
| Immutable message | `template_version/safe_payload` plus recorded source event; sanitize data and escape HTML/header content |
| Sender/adapter reference | Approved email service/sender from versioned workspace `runtime_policy`; resolve and freeze `delivery_context` in attempt audit before dispatch, never reuse a child signer |
| Delivery progress | Existing outbox `state/attempt_count/next_attempt_at/last_outcome/last_attempt_at` |
| Provider correlation | `provider_delivery_reference/delivered_at/uncertain_at`, with attempt and per-recipient evidence in append-only audit |

Resolve recipients from one current applied organization/configuration revision when accepting the
intent; later delivery retries retain that exact set. If a person serves several roles, send one copy
to that address while retaining each routing reason. Missing owner/manager/designee contacts in notice families that require those recipients create
an administrator fallback and visible routing issue. D50 lifecycle notices are the explicit exception:
unresolved responsible-admin routing is Blocked, without an all-admin fallback. Missing all valid administrator destinations for an admin-team notice is
Blocked, not successful empty delivery. Recovery-grant notices remain per authorized request, not
one notice per shared four-hour window. Source secrets never enter message content or exports.

Acceptance commits the source event and intent atomically. Delivery claims a bounded attempt under
C2, sends outside the transaction, and appends its safe outcome with a guarded delivery-head update.
The email provider is not part of the database transaction. A worker crash after submission therefore
requires reconciliation of the original attempt, not an automatic new send.
Before each first submission, commit typed `delivery_context` in `audit_event.data`: runtime-policy
revision, approved service/account reference, sender identity reference, adapter contract version,
credential reference/version used for this attempt, and stable submission key where supported.
These are nonsecret identities, not passwords/tokens or arbitrary callback URLs. A changed current
workspace policy cannot redirect reconciliation to a different mail provider/account or sender.
Subsequent attempt evidence may resolve a newly authorized credential version for that same approved
service context; it must preserve original submission correlation and recipient/message intent.
A corrected sender or different service needs an explicit audited replacement intent after the old
outcome is safely resolved. Unknown old submission cannot be bypassed by silently sending through
the new service. Provider-specific lookup/reconciliation exists only where separately qualified.
The provider's qualified idempotency support may be used; OTM does not assume every email transport deduplicates a message key.

### Result meanings

| Outcome | Required handling |
|---|---|
| Known provider acceptance | Record its reference and accepted recipient scope. Accepted means handed to the service, not proof it reached an inbox |
| Confirmed delivery | Record `delivered_at` only when qualified provider evidence establishes delivery; no fabricated delivered state from an accepted submission |
| Known rejection with no acceptance | Record safe diagnostic; bounded automatic retry only for a classified transient failure |
| Partial recipient outcome | Preserve accepted/rejected/unknown subsets in immutable audit; never blindly resend to the already accepted subset |
| Unknown submission outcome | Set uncertainty, preserve original correlation and reconcile. Timeout is not proof that no email was sent |
| Missing/invalid sender or transport configuration | Block delivery with visible administrative issue; no implicit Slack or alternate-sender fallback |

If delivery-confirmation events are unavailable, show Accepted/Delivery unconfirmed. Do not keep
sending merely to obtain confirmation. Bounces or later rejection append new evidence and update
only the delivery projection. Exact return/status schema and event handling depend on the approved
email service and remain a C6 qualification task, not an assumed OCI Email Delivery feature.

An email service outage cannot reliably report itself through that same service. Keep the dashboard
and delivery backlog/health visible and define independent operator monitoring/runbook checks in C6.
This is not permission to add Slack to V1. Database restore must fence old dispatchers and reconcile
accepted/uncertain submissions before any normal resend under D12.

## D48 accepted: alert after automatic cost-read retries are exhausted

Accepted 25 October 2026. Failed acquisition attempts become visible immediately and follow bounded
C2 automatic retry policy. Once that policy is exhausted, commit one email intent to administrators
for the continuing failed-read episode. Do not email on the first transient attempt or wait another
24 hours. Exact retry count, timeout/backoff and scheduling remain versioned runtime/C6 settings;
D48 chooses the exhaustion trigger, not arbitrary numeric retry defaults.

This policy covers financial acquisition failure only. Null optional forecast, normal provider
calculation lag, unqualified currency/cycle data and over-budget values are not failed-read email
triggers. A valid read that returns incomplete financial data remains visibly incomplete. Confirmed
access loss and urgent credential events retain their own immediate notices and recipients; a cost
read failure alone does not notify owners/managers/designees or imply an account is missing.

### Durable episode and publication contract

| Transition | Persistent evidence and consequence |
|---|---|
| Initial failure with retries remaining | Attempt evidence and next due work; dashboard shows failure/retry state, no failed-read email yet |
| First current retry exhaustion | One committed `financial_read_failure_opened` source event and one D47 email outbox intent to the configured admin set |
| More retries, manual refreshes or daily collections fail | Append observation/outcome evidence against the same open episode; do not create another initial email |
| Verified same-source read recovers | Append `financial_read_failure_recovered` referencing the open episode; no recovery email is introduced |
| Failure recurs after verified recovery | A new episode and new initial email when its automatic retry policy is exhausted |
| Source replaced/retired or work becomes obsolete | Record superseded/obsolete outcome, not verified recovery or an old-source alert against the new target |

The scoped failure key is financial acquisition for one registered child and the exact managed-budget/
authorized source identity. It excludes retry ID, daily occurrence, month rollover and ordinary key
rotation, so those do not create a new incident. Replacing the bound budget or actual source identity
is an explicit new scope; supersede the old scope rather than silently move its incident. Capture
source identity with the event, not a later mutable lookup.

Existing `audit_event.data` carries closed episode evidence: `failure_key`, `episode_key`,
`recovery_anchor_event_id`, `first_exhausted_collection_id`, the relevant retry-policy revision,
safe failure code and transition kind. `financial_collection_id`/`operation_id` are existing scoped
correlation fields. Record later failures/recovery as new immutable events; do not rewrite the
original source event or use volatile process memory as the episode head.

Serialize open/recover/supersede decisions with short database coordination on the existing child
registry row and current C2 publication guards. Atomically discover the current open episode, create
it only if none exists, and insert the source event/outbox intent. Use the existing service-actor
command-receipt uniqueness namespace with an internal key derived from the stable source/recovery
anchor; daily/manual request keys are not incident identities. Closed typed event data, command digest
and result must accompany this internal receipt as required by the audit model. The outbox's existing
unique(source event, channel) protects the one email intent. Retry known delivery failures through
that intent, preserving frozen recipients and original delivery context.

Success/failure publication and episode transitions share the same short coordination boundary.
Recheck current source/operation ownership before opening an incident; a late obsolete failure cannot
reopen an episode after a newer current read recovered it. Likewise an obsolete or wrong-source
success cannot close current acquisition failure. Compatible active collection joining and C2
intent/generation guards remain necessary; the notification dedup key alone is not an ordering fence.
Exact lock/query/index mechanics must be demonstrated in transaction tests during implementation.

Verified acquisition recovery means an authorized, target/scope-valid current-source Budget read,
not merely a worker restart, submitted refresh or configuration edit. It does not assert current
forecast availability, full configuration health or a fresh provider computation. D48 adds neither
recovery/reminder emails nor daily summaries. Restore recovery reconstructs episode evidence under
D12 and reconciles prior delivery; missing history is uncertainty, not permission to send a fresh
initial email. These are new typed audit payload contracts, not new tables or columns.

## D49 accepted: lifecycle email only for action or terminal failure

Accepted 25 October 2026. Create/import/delete, ownership transfer, membership and offboarding
workflows emit email when accepted work requires administrator action or reaches terminal failure.
Routine progress and successful completion stay in Operations. D47 email-only delivery, D48 failed
cost-read policy and mandatory access/disclosure/credential notices remain independently binding.

### Exact C2 transitions

| Persisted operation condition | Lifecycle email consequence |
|---|---|
| Draft form/preview before acceptance | None; no accepted operation exists yet |
| `queued` or `running` | None for routine progress |
| `waiting` on an administrator action | One attention notice when that durable action requirement first opens |
| `waiting` on provider completion, scheduled retry or automatic reconciliation | None unless a separate committed transition now requires administrator intervention |
| `needs_attention` | One attention notice for the current actionable condition; preserve exact step, safe cause and partial-effect context |
| `failed` | One terminal-failure notice after C2's known scoped failure predicate is satisfied |
| `succeeded` | No automatic success email; goal/verification evidence remains in Operations |
| `cancelled` | No routine cancellation email; cancellation still requires C2 no-effect/dispatch-exclusion guards |

An unknown provider outcome is not terminal failure. Continue bounded safe reconciliation or move
to actionable attention when administrator input is needed; never relabel uncertainty as `failed`
just to send an email. A deletion operation's success remains confirmed termination initiation under
D26; D49 adds no monitoring or notification of final OCI deletion after its retention period.
Owner first-login status is not an administrator wait for setup completion under D20. D23 manual
resource-cleanup guidance does not become a tracked resource-cleanup operation or a success email.

### Notice identity and content

Publish the operation transition, its immutable source event and notification intent in one local
transaction. The notice references existing `operation_id`, `intent_revision`, `step_key` when
applicable, safe wait/attention cause and the triggering transition event. Typed
`audit_event.data.lifecycle_notice` records the `notice_kind` (`action_required` or `terminal_failure`),
`attention_episode_key` when applicable, affected operation/child references and routing-policy version.
Existing outbox `source_event_id/operation_id/template_version/safe_payload` retain accepted content.
No new table, operation state, notification engine or independently writable lifecycle status is added.

An unchanged open manual-action/attention condition produces one initial notice. Page visits,
worker redelivery, restart, repeated check and a Resume attempt that does not satisfy the condition
cannot create new initial emails. A distinct later required action after verified progress is a new
attention episode. A subsequent genuinely terminal failure is its own terminal transition/notice;
its key is the exact operation and terminal intent revision, not every failed step attempt.
Only current C2 guards may publish these transitions. Obsolete workers cannot create new notices.

For a parent-managed offboarding workflow, notification ownership follows the existing parent/child
operation graph: summarize an actionable child condition under the responsible parent attention
transition rather than sending both a parent copy and an identical child notice. Preserve affected
child/step references so the action remains discoverable. Separate consequential action requirements
must remain distinguishable; this is not an indefinite digest or reminder feature.

Content includes operation kind/ID, verified target label when available, a short factual reason,
required administrator action or scoped failure, and an authenticated OTM operation-detail link.
Do not include bootstrap keys, passwords, activation links or unbounded provider errors. Before a
child is verified, identify the pending operation rather than invent an OCI tenancy identity. Email
is informational: opening its link is a read and cannot resume, repair or delete anything. A terminal
failure notice must preserve partial-resource context and cannot claim partial resources were cleaned.

### D50 accepted: responsible administrator only

Accepted 25 October 2026. Lifecycle action/terminal-failure emails go only to the operation's currently
responsible administrator. The user explicitly selected "only"; the earlier proposed all-admin
fallback is not adopted. Do not copy other admins, the tenancy owner, managers or designees into
these notices. D48 financial-read failure emails and required access/recovery/rotation notices keep
their existing recipient sets; D50 is not a global restriction on all OTM notifications.

#### Responsibility and reassignment

Initialize `otm_operation.responsible_actor_subject` to the initiating authorized administrator at
acceptance. The initiating actor and activation mailbox remain immutable history. An entitled admin
can explicitly take responsibility through an audited reassignment; merely opening, refreshing or
troubleshooting an operation does not reassign it. Reassignment updates the existing responsible
subject and operation revision, appending before/after subject evidence. It does not change the
provider intent, tenancy owner, initial activation mailbox/MFA or grant another person's credentials.

For parent-managed lifecycle work, the parent that owns the attention notice supplies its responsible
administrator. Child work inherits responsibility when created; child-step execution by an automation
worker does not make the service account the email recipient. Standalone operations use their own
responsible subject. Resolve the exact stable subject through current administrator entitlement and
verified contact data, not a tenancy owner's or historical initiating email.

#### Routing and delivery guards

| Condition | Required treatment |
|---|---|
| Required lifecycle notice opens | Capture one authorized responsible subject/email with operation revision, routing policy and immutable source event |
| Responsibility/contact cannot be resolved or administrator is no longer authorized | Keep the operation/attention visible and routing Blocked; no automatic email to other administrators |
| Known invalid address or confirmed nondelivery | Record failed/blocked delivery for the captured recipient; explicit authorized correction/takeover is required, with no recipient-list expansion |
| Responsibility changes before an unsent notice is submitted | Recheck current subject/revision; supersede the stale unsent intent and capture an audited corrected intent for the newly responsible admin if the notice still applies |
| Original submission is accepted or uncertain | Preserve original recipients/context and reconcile; reassignment cannot retract an accepted email or justify a blind duplicate send |

Current responsibility and entitlement are checked when accepting the notice and immediately before
provider dispatch. External email delivery is not atomic with reassignment: retain the actual routing
and attempt evidence rather than promise that an in-flight email can be recalled. A known accepted
submission stops automatic repeat submission; unknown outcomes remain subject to D47 reconciliation.

The existing outbox's recipients are never edited in place. A corrected intent has its own audited
source event linked to the prior notice and responsibility/contact correction; freeze only the newly
responsible admin, never all admins. Superseding a known unsent intent changes only its delivery head
and appends audit evidence. It does not reopen a lifecycle attention episode or fabricate progress.
If the prior submission is uncertain, do not use the new recipient as a workaround for reconciliation.
An admin can still inspect/take over the workflow in Operations while email routing is blocked.

Typed `audit_event.data.lifecycle_notice` retains `responsible_actor_subject`,
`responsible_operation_revision`, `recipient_snapshot`, `routing_policy_revision` and optional
`responsibility_event_id` / `supersedes_notification_id`. Existing operation subject/revision fields,
audit correlation and outbox routing fields carry this contract; no new table or column is required.
Notify once for unchanged attention, preserving D49 event/episode identity and D47 delivery context.

The earlier generic unresolved-recipient admin fallback applies to other notice families only.
D50 is its explicit lifecycle exception. The design adds no automatic reassignment, no all-admin
fallback email and no routine reassignment-progress/success email. Actual entitlement, takeover,
concurrent delivery/reassignment and transport behavior remain implementation qualifications.

## Simulator and contract-test plan

These cases are planned, not executed by writing this document. Reuse them against the simulator and
real-adapter response fixtures, with separate real OCI/service qualification later.

| Case | Required assertion |
|---|---|
| Duplicate CronJob/manual delivery; lost accepted response | One occurrence/command result; commit/rollback preserves operation/audit/job atomicity |
| Compatible simultaneous manual refresh | Joins active exact-scope work; distinct actor request audit retained |
| One unavailable child in fleet read | Other children publish; failed child stays explicit, totals coverage incomplete |
| Actual zero; forecast null; negative credit; non-finite/overflow | Valid values retained; unknown remains unknown; invalid money never becomes a healthy zero |
| Changed budget amount during desired override | Coherent observed amount remains comparison/sort source until a qualified new response |
| Missing computation/currency; previous cycle; future timestamp | No false current/green/summed result, no use of retrieval time to invent source freshness |
| Bound budget replaced; child retired; wrong signer/target | No current publication or fallback; stale attempt evidence retained |
| Worker dies before/after publication; late older response | No duplicate snapshot, stranded completion or regression to an older source calculation |
| New partial forecast versus older complete response | One selected snapshot; no mixing actual/budget/forecast across observations |
| Configuration/shared-member changes during read | Correct current guards and one financial contribution per child |
| Retry exhaustion versus first transient failure | Email admins once only at current exhaustion; no 24-hour delay or owner/manager/designee expansion |
| Continuing failure across retries/manual reads/daily slots/month rollover | Same failure scope/episode, one initial email intent; key rotation cannot reset the episode |
| Concurrent exhaustion, verified recovery and late obsolete result | Scoped coordination yields one open event and cannot reopen/close through stale source/work evidence |
| Verified read recovery then relapse; missing contacts | Close episode without recovery email; new exhausted relapse creates a new event and explicit admin fallback |
| Email-only validation; repeated recipient roles | Reject Slack/unknown dispatch, deduplicate addresses without losing role evidence; no live send in simulation |
| Provider acceptance without delivery evidence | Show Accepted/Delivery unconfirmed, not Delivered; do not resend to obtain confirmation |
| Sender/service policy changes after submission | Reconcile using captured delivery context; current configuration cannot redirect unknown-outcome lookup or silently resend through another service |
| Durable human wait versus provider/retry/reconcile wait | Email only when administrator action is required; never create a false terminal failure |
| Repeated same attention, unsuccessful Resume, later distinct action | One initial episode notice; only verified progress/new action can open a distinct episode |
| Success/cancelled/queued/running and terminal scoped failure | No routine lifecycle email; one terminal-failure intent without hiding partial resources |
| Parent/child offboarding attention | One owned attention transition with affected children; no identical parent-and-child double send |
| Responsible admin differs from initiating admin/owner | Route lifecycle attention only to current responsible subject; preserve creator/activation history |
| Unavailable responsible admin; ordinary viewer opens operation | Block routing without all-admin fallback; viewing does not transfer responsibility |
| Reassignment/contact change races email dispatch | Recheck current revision, preserve immutable recipients/attempt context and supersede only known unsent intent; no unknown-outcome bypass |
| Notification timeout/partial delivery; DB restore | No blind duplicate send, mutable recipient rerouting or secret exposure |

## Remaining C5 review items

| Item | State / next evidence |
|---|---|
| Financial dashboard and controls | Approved D46; retain recorded D45 browser evidence, no new UI required for this policy adoption |
| Daily/manual collection and coherent publication | Companion [typed examples and negative controls](16-c5-contract-review.md) checked locally; live ordering/transaction tests remain implementation gates |
| V1 delivery channel | Email accepted D47; approved sender/service/transport and acceptance/delivery behavior qualify in C6/pilot |
| Failed financial acquisition notice | D48 accepted; episode/transaction contract recorded; prove concurrency/recovery in the implementation test plan |
| Lifecycle email trigger policy | D49 accepted: administrator action or terminal failure only; routine progress/success stays in Operations |
| Lifecycle recipient and per-transition identity | D50 accepted responsible-admin only, no fallback; existing operation/intent/episode and audited reassignment evidence support routing |
| Money/cycle/freshness normalization | Bounded decimal, response-cycle and freshness examples checked in chapter16; real source behavior remains separately qualified |
| Schema/model/query trace | Existing fields cover this slice; exact physical constraints/index plans and delivery adapter setup belong to C6 |

D49 triggers and D50 responsible-admin-only routing are accepted. D47 email-only delivery and required
access, disclosure, rotation and D48 cost-read notices remain binding. A lifecycle progress update
cannot resolve an organization exception or certify provider effects. No automatic lifecycle success
email is selected. This design artifact sends no notifications.

## C5 exit and next stage

C5 closes only after review of this contract, normalization/cycle/freshness qualification boundaries,
source/query failure fixtures and operational trigger/routing rules. D47 settles email-only V1 delivery and D48 settles failed-read email timing. D49 settles lifecycle action/failure triggers; D50 settles responsible-admin-only routing. The [checked companion pack](16-c5-contract-review.md) supplies bounded source/fixture review evidence; real-runtime qualification remains explicit. Update the
model/ER only if a reviewed missing durable field is found; none is proposed here. Real-provider
permissions, budget computation and channel behavior remain pilot gates rather than fabricated local
success. The approved UI does not need redesign while these contracts are settled.

C6 then defines Terraform/OKE environments, SSO/network/database privileges, migration/index/query
plans, CI/CD and signed/reproducible artifacts, backups/PITR/restore fencing and recovery rehearsals,
SLOs/runbooks and a dependency-ordered implementation backlog. Preserve one shared schema/contract
owner; decide concrete parallel development packages only after these boundaries are stable.


## Bounded D50 application implementation — 4 November 2026

Application capability qualified locally and installed in both saved instances. The [responsibility capability](../reference/responsibility.md)
implements explicit audited self-claim for waiting/attention guided create/import. Original creator,
provider intent, owner and activation mailbox/MFA remain immutable. Existing operation responsible
subject/revision/time and typed before/after audit are reused; no new table or automatic assignment
is added. Continuation uses a validated replacement authority snapshot and fresh grant checks.

This implements application responsibility only. D49/D50 email acquisition, recipient/contact
resolution, unsent-intent supersession and accepted/uncertain delivery handling above remain future
transport qualification. Claiming neither sends mail nor changes any other notification's recipient
rules. No fallback to all administrators, owners, managers or designees is introduced.


## Accepted environment email override policy — 4 November 2026

The user requires one operator-configured test destination in local/staging, applied to all actual
OTM-controlled email delivery/contact inputs, including OCI-generated child activation, invitation
and recovery messages. This is not limited to SMTP To. Canonical employee/manager email identifiers,
SSO/login keys and stable relationships remain unchanged. Missing test routing blocks email-capable
external operations without employee fallback; production rejects test overrides/bypasses.

Freeze original/effective contact and policy fingerprint at acceptance. The local recovery admin's
original contact remains null; an explicit test route can supply effective delivery without changing
that identity. Production unresolved responsible contact remains blocked with no all-admin fallback.
Dispatch revalidates trusted environment/profile/destination; policy changes block old queued work
instead of retargeting it. Prior activation and accepted/uncertain delivery evidence remain immutable.

[Full accepted boundary and qualification matrix](21-environment-email-policy.md). Initial SMTP
notices remain D49/D50 create/import action/failure to the responsible admin only. No temporary
recipient-editing UI, security-findings workflow or other notice-family expansion is approved here.
Runtime fields/transport/OCI behavior and release checks are still in progress, not qualified by
this decision text. OTM cannot intercept arbitrary spontaneous/manual OCI mail; imported contacts
and uncontrolled email triggers must be checked before email-capable mutations.


## D49/D50 email source contract — 4 November 2026

Local qualification passed; see the final validation checkpoint below. [Lifecycle email](../reference/lifecycle-email.md) now
stages create/import action/failure notices with frozen current-responsible contact, explicit test
route, SMTP profile and application origin. Its one outbox table has immutable intent and guarded
bounded delivery head. SMTP runs outside transactions after durable sending/preflight; known reject
retries up to 3 at 30 seconds, accepted/uncertain outcomes never blindly resubmit. Ordinary progress/
success/view does not send. Known-unsent context can supersede, without editing old recipient intent.

Operation detail exposes safe retained notification metadata, not message content or credentials.
Original-null local recovery contact can use an explicit override; production unresolved contact
blocks. Guarded OCI activation/bootstrap/owner/people contacts stay distinct from D50 SMTP recipient
selection. Application-origin operation links are frozen and rechecked. Vault/hosted transport and
actual OCI-generated contact behavior remain unqualified; current capture is local only.


### Lifecycle email final local qualification — 4 November 2026

The final validation record (private historical evidence; not distributed) supersedes this feature's source-only pending checkpoints: 1,421 full-suite tests pass, both unit-only coverage gates exceed 95%, reviews are complete, and both saved local instances were upgraded with all existing rows preserved. The release-check command covers both application and configuration paths. Hosted CI/OKE deployment, production Vault/SMTP and live OCI contacts remain separately unqualified; the feature is not a claim of complete V1 delivery.


## Email delivery audit category — 5 November 2026

Source refinement, validation pending. Existing email_delivery evidence projects to the separate
Email delivery audit category rather than Operations. Directory/export use the same predicate;
retained kinds/hashes/history remain immutable. Normal operation-detail delivery evidence is
unchanged. This is visibility only, with no new routing, send/retry policy, notification family or
database migration. [Current audit guide](../reference/audit-history.md).
