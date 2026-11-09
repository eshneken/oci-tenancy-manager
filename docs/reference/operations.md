# Read-only Operations list and detail

2 November 2026 · Recorded Operations visibility; actionable-only badge validated locally

[Local application](local-application.md) · [Durable worker](worker.md)
· [Admission and intent](admission.md) · [Session authority](authentication.md)
· [Production model](../engineering-design/11-production-data-model.md)
· [Explicit responsibility takeover](responsibility.md)

## Implemented boundary

Operations now shows real persisted inspection work in a searchable list and linked detail page.
It reads the existing `otm_operation`, `otm_operation_step` and `audit_event` tables through
`SqlOperationDirectory`, using closed public models in `otm.operations.views`. No table, migration,
new operation kind or provider call was added by the original read-only milestone. An installation without accepted operations shows
an honest empty state; the page does not seed examples or generate an activity feed.

This guide covers the read-only list/detail projections. The subsequent [simulation form/API](simulation.md)
now accepts explicitly selected virtual inspections and executes them in a separate foreground
worker. Generic retry/resume/cancel and real tenancy/OCI writes remain absent. Neither the initial
read milestone nor that bounded simulation path completes the full tenancy lifecycle/MVP. The
original underlying worker executed only simulated `inspect_import` reads; the parity candidate adds the separate `organization_action` path described below. `provider_mode="simulated"` is the public model's fixed scope for that
supported kind/current worker, not a freshly observed OCI provider fact or independent per-row
provider qualification. A real adapter or another operation kind requires an explicit contract/UI
change before its records can be presented here.

A `succeeded` inspection means its bounded target read was verified. It does not mean the tenancy
was adopted, configured or created. Native runner job completion also remains distinct from business
operation state. The interface explains this scope in both list and detail.

## API and authority

The default `create_app()` remains health-only. Explicitly injecting the directory alongside the
session/browser boundary adds two GET routes; the local application composes those dependencies.
The public `/operations` and `/operations/{id}` HTML shell contains no embedded operation data.
HTTPS/Host guards still apply, and the underlying API requires current administrator authority.

| Route | Behavior |
| --- | --- |
| `GET /api/operations` | Bounded filtered/sorted page in the verified session workspace. |
| `GET /api/operations/{id}` | Recorded operation, current-intent steps and recent operation events in that same workspace. |

Each API read runs through request authentication and a fresh `SessionService.require_admin`
command-boundary check. Callers cannot choose another workspace through the query or URL.
A missing or foreign valid operation UUID produces the same 404 `OPERATION_NOT_FOUND`.
Recognized query values that violate the closed model produce 400 `INVALID_OPERATION_QUERY`;
framework path/numeric parsing errors remain validation failures. Unexpected storage/evidence
failures become 503 `OPERATION_SERVICE_UNAVAILABLE`, without SQL, raw intent or provider diagnostics.
Current session denial and verification-outage diagnostics retain their existing authentication rules.

| Query field | Accepted values and effect |
| --- | --- |
| `page` | Integer 1–100000; default 1. The result clamps it to the final available page. |
| `page_size` | 10, 25, 50 or 100; default 10. |
| `sort` | `accepted_at`, `updated_at`, `state` or `stage`; default `accepted_at`. |
| `direction` | `asc` or `desc`; default `desc`. A UUID tie-break gives stable ordering. |
| `state` | Empty for all, or `queued`, `running`, `waiting`, `needs_attention`, `succeeded`, `cancelled`, `failed`. |
| `query` | At most 128 characters; literal case-insensitive containment over operation UUID text or current-intent target tenancy OCID. `%`/`_` are escaped rather than becoming SQL wildcards. |

SQL sort columns come from an allowlist; no caller-supplied identifier is interpolated. The filtered
count and page share one snapshot. `total` is the filtered operation count, and `pages` is at least
one even for zero results. These read controls do not expand the implemented worker state machine;
the operation contract retains states used by the broader design.

## Snapshot and evidence checks

Every directory/detail call opens one PostgreSQL `REPEATABLE READ` transaction and explicitly sets
it `READ ONLY`. Thus a worker publishing concurrently cannot mix an older operation with newer steps
or a count from another view of the same call. This is a per-read snapshot, not a live event stream
or permanent cache; a later refresh may observe newer committed state. Existing browser session
activity/logout writes remain separate from the Operations read transaction.

The operation joins its exact current intent by workspace, operation UUID, intent event UUID,
positive intent revision and kind `operation_intent`. Before exposing summary fields, the reader
validates closed `IntentEventData`, its canonical stored hash, exact workspace and the frozen actor's
issuer-qualified key against the initiating actor column. Malformed selected evidence fails closed.
The digest is an integrity/correlation check, not a cryptographic authenticity signature or a defense
against a privileged database owner changing schema/protections.

Detail reads step rows only for `current_intent_revision`, ordered by logical step key. An absent
step means none has been recorded for that intent; the UI does not invent a queued/verified step.
The current worker uses `inspect_target`. Its outcome JSON is validated as `InspectionOutcome`
before selecting the safe code; a missing outcome remains null.

Recent events cover the operation across its intent/attempt history. The query orders by descending
`at` and event UUID and fetches up to 51 rows, returns the newest 50 and sets `events_limited` if the
extra row exists. Every returned event's stored digest is checked; `inspection_outcome` JSON is also
validated before selecting its allowlisted safe code. Acceptance/dispatch events expose no code.
Older rows remain immutable history in `audit_event`; the 50-event view limit does not delete or
rewrite them. This slice has no older-event pagination or raw audit export endpoint.

## Public DTO and UI field map

Only the following public projections cross the HTTP boundary. Raw intent/outcome JSON, access
bindings, credential generations, actor issuer/subject and SDK exceptions remain private. Recorded
instants are normalized to UTC; null completion/verification or display name is shown as not recorded.
Processing/event timestamps are not relabeled as provider observation/capture times.

| UI/API field | Persisted source or explicit derivation |
| --- | --- |
| Operation link/ID: `operation.id` | `otm_operation.id`; used for the list-to-detail link and recorded identifier. |
| Operation label/kind: `operation.kind` | `otm_operation.kind`, closed to `inspect_import` / `organization_action` / `configuration_update` / `configuration_check`; allowlisted title derives from verified intent. |
| State badge: `operation.state` | `otm_operation.state`, independent of native job success. Inspection-read issues use no-action guidance; lifecycle attention remains linked to person/tenancy context. Stored states/filters are unchanged. |
| Stage: `operation.stage` | `otm_operation.stage`; UI replaces underscores for display without adding progress percentages. |
| Accepted: `operation.accepted_at` | `otm_operation.accepted_at`, rendered in UTC. |
| Updated: `operation.updated_at` | `otm_operation.updated_at`, rendered in UTC. |
| Completed: `operation.completed_at` | Nullable `otm_operation.completed_at`; no completion time is synthesized. |
| Initiated by: `operation.initiated_by` | Exact current intent event `audit_event.data.actor.display_name`, after actor-key validation; nullable, with no raw-subject fallback. |
| Target tenancy: `operation.target_tenancy_ocid` | Nullable exact current-intent child; a person-wide operation does not invent an OCID. |
| Title/target label: `operation.title`, `operation.target_label` | Allowlisted action title and recorded target display from validated intent; not browser-supplied ownership authority. |
| Simulated badge/provider: `operation.provider_mode` | Fixed `simulated` for the currently supported kind/worker. It does not assert a real OCI call. |
| Step label: `steps[].step_key` | Current-intent `otm_operation_step.step_key`, closed to `inspect_target`, `apply_lifecycle` and the accepted-version onboarding/member/configuration/check keys in [the guided field reference](tenancy-onboarding.md#existing-storage-no-new-tables); labels distinguish inspection, accepted handoff and simulated setup checks. |
| Step state: `steps[].state` | `otm_operation_step.state`: `running`, `verified` or `needs_attention`. |
| Attempt: `steps[].attempt_number` | Positive `otm_operation_step.attempt_number` for that logical step/intent. |
| Verified: `steps[].verified_at` | Nullable `otm_operation_step.verified_at`, set by committed worker verification, except `handoff`, where it records accepted administrator input; not a provider capture timestamp. |
| Step outcome code: `steps[].safe_code` | Validated `otm_operation_step.last_outcome.safe_code`, or null when no outcome exists. |
| Event heading/kind: `events[].kind` | `audit_event.kind`: `operation_intent`, `inspection_dispatch`, `inspection_outcome`, `organization_action_outcome`, `onboarding_action` or `onboarding_outcome`, mapped to recorded event labels. |
| Event date: `events[].at` | `audit_event.at`, rendered in UTC. |
| Event code: `events[].safe_code` | Validated outcome event `audit_event.data.safe_code`; null for acceptance/dispatch. |
| Event-limit message: `events_limited` | True when the operation snapshot has an event beyond the newest 50 returned. |
| List rows: `items` | Ordered `OperationSummary` projections from the exact-intent join. |
| Navigation count: `attention_count` | Workspace-wide count of current organization workflows in `waiting` or `needs_attention` with a supported action: guided handoff/review/blocked recovery, or safe no-effect local cancellation. Requires matching current intent/person pending-operation binding; excludes inspection-only simulations, orphaned/unsupported records and known effects without supported recovery. Independent of list filters/page; nonnegative, compatibility default0. Derived in the read snapshot, not stored. |
| Filtered count: `total` | `COUNT(*)` under the same workspace/state/search predicates as list rows. |
| Pagination: `page`, `page_size`, `pages` | Requested allowlisted size, clamped page and `max(1, ceil(total/page_size))`; no stored page/cache table. |
| Detail groups: `operation`, `steps`, `events` | One `OperationSummary`, current-intent `OperationStepView` rows and bounded `OperationEventView` rows from one detail snapshot. |

`OperationDirectory` has `items`, `total`, `page`, `page_size`, `pages`, `attention_count`. `OperationDetail` has
`operation`, `steps`, `events`, `events_limited`. The three added exported schemas cover
`OperationQuery`, `OperationDirectory` and `OperationDetail`, including their nested definitions.
The original read-history checkpoint had23generated backend schemas and45runtime files.  Generated frontend
types retain this source authority; TypeScript types alone are not response runtime validation.

## Screen behavior and verification limits

Operations is working navigation under Activity & history. Organization and the parity candidate Tenancies entry point are integrated; full Configuration/finance features remain outstanding. The list provides search, state filter, sortable headings, page size, page
buttons and refresh; [Run simulated inspection](simulation.md) is a separately guarded admission action. It distinguishes “no operations yet” from no filter matches. The detail has
back navigation, recorded status/facts, current steps and recent events with the explicit history
limit notice. Browser Back/Forward and normal/new-tab links preserve expected navigation, and list
controls survive detail/back navigation in the scoped in-memory query cache. Session loss clears
privileged query data. Read denial returns to sign-in; service outages keep a retryable error state.

The initial read-only checkpoint passed 449 backend unit tests over 1868/1878 executable lines (99.4675%) across
39 runtime files; 45 frontend unit tests cover 240/240 lines (100%) across nine source files.
That checkpoint's combined backend/PostgreSQL/browser run passed 555 tests with no failures, errors or skips.
Unit and integration coverage remain separate. [Development progress](../history/development-progress.md#operations-read-visibility)
and its validation receipt record exact scope and evidence.

Unit fixtures check malformed evidence, public projections and the newest-50 flag; they do not prove
SQL locking or physical history retention. Real PostgreSQL checks verify literal query controls,
foreign/absent scope, actual accepted/worker-completed reads, read-only repeatable transactions and
coherence when a worker commits between reads. HTTPS/Chromium scenarios use the real restricted API
role and exercise recorded queued/verified data, keyboard/filter/detail/back/deep-link reload and
320/390/1280px geometry. Existing audit protections and retained rows are not changed by these reads.
All factors/records belong to isolated synthetic test fixtures; the human's persistent local database
and the organization prototype are separate. No OCI, cloud operator pod, production role/Vault/SSO
deployment or Git/publication clearance follows from this local read slice.

## Subsequent submission and polling

The read-only checkpoint's field meanings/retention guarantees remain unchanged. Operations now
also offers the configured simulator catalog/confirmation form and 202 submission flow described
in [simulation.md](simulation.md). The list polls recorded state, and active detail polls until a
recorded outcome; these read polls do not refresh session idle time. Request uncertainty is retained
only while the Operations-list form remains mounted, including modal close/reopen. Backend replay
is durable for a known key, but navigation/reload clears that form's key memory. Check Operations
before starting another request after uncertainty. No generic mutation-recovery coordinator is added.

## Activity/history role and contextual remediation

The accepted navigation now groups Operations with Audit History under **Activity & history**,
separate from daily Tenancies, Organization/Organization drift and Configuration management.
Administrators belongs to **Application settings**. Recorded operations provide visibility and
troubleshooting rather than a user inbox. The navigation badge counts only current supported
workflow actions, not every stored attention state or assigned security-remediation task; see
the current capability rules below.

The stored `needs_attention` value is unchanged. Current simulated detail displays
**“Simulation ended with an issue. No action is required.”** This applies to a simulated inspection
issue, not future real resource/lifecycle remediation. An unconfirmed submission still requires
checking Operations before new work. Later corrective actions begin in the affected tenancy,
organization/configuration or access context and may link back to this evidence; no generic Retry
button or guessed context route is added here.

[Audit History](audit-history.md) now reads the existing immutable audit table through scoped safe
search/category projections. Its source map documents each query/entry/directory field and distinguishes
worker/operator/verified-principal display from an unverified failed attempt. Raw JSON/edit/export
were not enabled in that original read checkpoint; the later guarded audit CSV export is implemented. Static Audit History remains an inert menu label
because no static audit destination is available.

## In-progress organization lifecycle visibility

The [organization parity candidate](organization-workflows.md) adds recorded `organization_action`
operations alongside bounded `inspect_import`. Their immutable target may be a stable person plus an
association plan, not a single invented child OCID. Operations projects both kinds and their closed
simulated outcomes; native job success remains distinct from verified business completion. The
current inspection-only no-action guidance applies to inspection reads, not an unsuccessful lifecycle
handoff. Lifecycle attention/cleanup is reached from its person/tenancy context; there is no generic
Operations Retry or real-provider cancellation contract. Authored local cancellation is described
in the workflow guide. No historical read-milestone pass qualifies this new implementation.

## Guided onboarding current action — 31 October2026

Guided operation detail may now embed the same [setup panel](tenancy-onboarding.md) shown on a pending tenancy. This is a scoped action in its tenancy workflow context, not a generic retry facility on the Operations list. New step/evidence projections validate `OnboardingEvidence`; historical inspection/lifecycle contracts remain supported.

## Direct successful tenancy link — 31 October2026

OperationSummary.result_tenancy_id is nullable and read-only. Selection left-joins otm_tenancy on exact workspace and frozen target OCID, using its unique scope/OCID key. Only succeeded organization actions expose a matched UUID; inspections and person-wide/no-target operations do not infer one. The completion notice links that UUID to the normal authorized tenancy detail, including older nonguided operations. It is a derived field, not a new database column.


## Actionable badge versus recorded operation state

The user selected a clearable-work badge: if the tool has no supported action to advance or settle a
current operation, that record does not contribute. attention_count is no longer a count of all rows
whose state text happens to be waiting or needs_attention. It is a workspace-wide read projection,
not a new lifecycle state, per-user acknowledgment or retention rule. The list/detail and existing
state filters still expose all authorized recorded operations, including excluded simulation issues.

A candidate must be an organization_action in waiting/needs_attention, joined to its exact current
intent and the same workspace's person whose pending_operation_id still points to that operation;
the intent must identify that person. It then needs either a supported guided onboarding continuation
or safe local cancellation with effect_knowledge=none. The guided branch requires immutable intent
onboarding_version in {1,2,3} and either needs_attention (the blocked recovery phase) or wait_reason equal to
onboarding_handoff/onboarding_review. A different wait can still count when no-effect cancellation
is supported. Unsupported/orphaned work and known-effect work with no supported continuation do not become badge
items merely because a status says attention. Current actor/responsibility, scope, policy/revision,
exact-target and effect checks still apply when the actual command is submitted.

| Recorded kind/state and current binding | Supported action context | Badge contribution |
| --- | --- | --- |
| inspect_import simulation, including needs_attention | Read-only result/history. No correction, acknowledgment, delete or cancel action is added. Detail retains Simulation ended with an issue. No action is required. | None. |
| Current organization_action waiting for guided handoff/review | Responsible administrator verifies the exact handoff or reviews/continues setup through the existing guided panel. | Counts while a supported continuation remains current. |
| Current guided organization_action needs_attention with blocked recovery | Existing handoff/setup continuation follows persisted progress and verified prerequisites; not a generic Retry button. | Counts while that supported recovery exists. |
| Current organization_action waiting/needs_attention with no known effect and safe local cancellation | Existing person/workflow cancellation guard can settle the local simulation. Cancellation is not provider rollback or deletion of historical evidence. | Counts when current safe cancellation is supported. |
| Orphaned pending binding, a wait without guided recovery or safe cancellation, or known effect without supported recovery | No invented continuation/cancel/dismiss action. Keep the recorded state and troubleshooting evidence visible. | None. |
| Queued/running or terminal records outside the waiting/needs_attention selection | Normal processing or recorded outcome; this badge does not measure all work or every possible contextual action. | None. |

The existing needs_attention state remains useful machine/business evidence: an inspection can be
denied, unsupported or unobservable; a lifecycle phase can be blocked; an outcome can require later
qualified recovery. Badge exclusion does not mean healthy, repaired or erased. Inspection simulations
remain immutable recorded results; there is no delete, acknowledgment, dismissal or cleanup endpoint
to make their number disappear. No existing row/state/history is rewritten by this badge change.

The count describes workspace capability, not an authorization grant to every viewer or a guarantee
that the next attempt succeeds. Only supported current commands can advance/settle the workflow;
failed recovery can leave it waiting again. A stale badge cannot bypass responsible-administrator or
other command guards. The server derives the count in the existing list read snapshot, independently
of search, state filters and pagination. No table, migration, response field or dependency is added;
the six-field OperationDirectory shape and default0 compatibility value remain.

The narrowed predicate passed906backend units at96.3301%and205frontend units at97.49%, plus
1,094combined backend/PostgreSQL/browser tests without failures/errors/skips. Cases cover diagnostic
history at count0, handoff/review, bootstrap and partial-known-effect retries, safe cancellation,
unsupported/orphaned work, workspace/filter independence and actual completion clearing the badge.
Independent documentation/security/UI reviews pass. Both local instances were restarted with all
15application tables unchanged. Prior state-only receipts retain their original source scope.
See the actionable-badge receipt (private historical evidence; not distributed).


## Selected baseline on guided operations

P3.2b create/import details use the onboarding panel to show the immutable selected BaselineVersion
and its exact published-version link. Publication during activation never replaces that snapshot.
The worker also requires the pending registry baseline_version_id to match the frozen intent before
provider work. Older operations explicitly show that no baseline was recorded; they do not inherit
the current default. This is selection evidence, not verification that OCI configuration was applied.
See [the onboarding field guide](tenancy-onboarding.md#p32b-baseline-retained-across-manual-waits).

### Configuration update operations

The `configuration_update` kind records one frozen baseline and one or many exact registered children.
Each `configuration:<tenancy UUID>` step retains its safe outcome and attempt count. The original
intent remains immutable; retries add `configuration_retry` evidence and reuse the same operation.
A batch can finish with successful and incomplete children; its progress/retry controls live under
Configuration or tenancy detail. Operations offers **Open baseline update**. Its navigation count
includes supported retries owned by the currently authorized responsible administrator, excluding
unsupported historical failures and inspection-only simulation issues. See
[the field/transaction reference](configuration-updates.md).


## Versioned onboarding and member-removal evidence — 3 November 2026

Local simulation qualified and installed in both saved instances. Existing operation detail reads the accepted onboarding version: new
version 2 includes configure_baseline and verify_configured_access before retire_temporary;
a 6 November source follow-up added version 3 with capture_required_users before retirement. At that
earlier source checkpoint qualification was in progress and saved instances were not upgraded; the
later [manual-presence receipt](../history/manual-presence-checkpoint-2026-11-06.md) records the
qualified main-preview upgrade and unchanged parallel preview. Version 1
keeps the old graph. Shared-member outcomes may include exact MemberRemoval receipts, with durable
remove_member_groups:{association_uuid} and delete_member_user:{association_uuid} steps. Both share
the closed immutable lifecycle outcome, and commit atomically with membership retirement. These
are local simulated identity milestones, not resource-cleanup verification or generic Operations
actions. Continue from the existing contextual tenancy/person panel.


## Qualified local read-only configuration checks — 3 November 2026

Local qualification and both saved-instance upgrades pass. New configuration_check operations retain UUID-only queued acquisition, one
immutable child outcome/step and native task otm.configuration_check. The operation can finish
succeeded when every attempt is recorded even if a child is drifted/unavailable; inspect the typed
category outcomes. The contextual [drift screen](configuration-drift.md) distinguishes confirmed
findings from unknown reads and retained evidence. No apply, generic retry/acknowledgment or action-
inbox badge is introduced by diagnostic results. Start a fresh explicit check in Configuration.


## Qualified explicit guided responsibility

4 November 2026 · Local qualification and both saved-instance upgrades pass. The read-only directory still cannot assign work on view.
A scoped guided-detail panel now permits the explicit application-only
[Take responsibility decision](responsibility.md); it is separate from generic provider Retry/Resume.
POST /api/operations/{uuid}/responsibility accepts only a request UUID and expected operation
revision, returns HTTP 200 ActionReceipt and queues no job. Original creator, activation mailbox,
provider intent and tenancy owner stay unchanged.

OperationSummary now has 18 fields: responsible_administrator_name, responsible_administrator_id,
responsibility_revision, can_take_responsibility, id, kind, state, stage, accepted_at, updated_at,
completed_at, initiated_by, target_tenancy_ocid, title, target_label, provider_mode, guided_onboarding
and result_tenancy_id. The first four are computed for guided detail, with nullable/false defaults
elsewhere. The [complete new-field/source map](responsibility.md#complete-field-and-storage-map)
distinguishes the current responsible grant from immutable initiated_by.

operation_responsibility_changed appears in retained operation events with a human label, not a
provider safe outcome code. Claim/replay/conflict behavior and captured execution authority are
documented in the runtime guide. Only current responsible may continue actual setup after the
claim; no responsibility/notification auto-assignment is implied.


Final application qualification and saved-instance receipt (private historical evidence; not distributed).


## Retained lifecycle email metadata — source candidate

Validation pending. OperationDetail now has five fields: notifications, operation, steps, events,
events_limited. notifications defaults empty and returns up to 100 exact-workspace/operation
NotificationSummary rows, retaining full history beyond that display limit. It exposes original/
effective contact, delivery knowledge, redirection and bounded attempts/times/diagnostics, never
message body or credentials. Sent is SMTP acceptance; unknown has no blind resend action. Existing
operation events also read immutable email_delivery evidence.
[Every summary and outbox field](lifecycle-email.md). No generic Send/Resend/recipient editing or
notification-driven ownership change is added.

## Manual required-user check operations — 6 November 2026

Local qualification and the main-preview upgrade pass; the parallel preview is unchanged. The required_user_check kind, step
required_users:{tenancy UUID}, and immutable required_user_check_outcome use existing operation/
step/audit records. View check from either account opens its exact operation. Succeeded means both
bounded outcomes were recorded, including Missing or Unable to verify; it does not establish access
health. No retry/repair or actionable navigation count is added for these diagnostics. Return to the
child's Required users context for a new explicit Check now. See the
[full source/storage map](user-presence-checks.md).
