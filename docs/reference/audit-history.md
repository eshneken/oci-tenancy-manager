# Audit History read directory

2 November 2026 · Recorded-change details validated locally

[Local application](local-application.md) · [Operations](operations.md)
· [Administrator evidence](administrators.md) · [Authentication](authentication.md)
· [Production data model](../engineering-design/11-production-data-model.md)

## Scope and navigation

Audit History reads existing immutable `public.audit_event` rows under current administrator and
workspace authority. It is grouped with Operations under **Activity & history**, separate from
Tenancies, Organization/Organization drift and Configuration daily management. Administrators stays
under **Application settings**. History records what happened; it is not an assigned-action inbox.

The implemented page provides searchable, categorized, sorted and paginated safe history plus
UTC date filters, readable recorded-change details and a bounded complete-filter CSV export.
No raw JSON view, event edit, audit deletion or new history table is added. The export adds forward-only migration0007 to extend the
closed event-kind constraint and index workspace/time/event paging. This history is
application/operation evidence, not the deferred security-findings/audit-user capability.

The explicitly configured application serves the public nonsecret `/audit-history` shell and the
protected `GET /api/audit-history` data route. Default `create_app()` remains health-only. Static
design menus show Audit History as an inert label because no static audit page exists; they do not
link to an invented destination or imply live data.

## API controls and authorization

Request authentication plus `SessionService.require_admin` recheck live session/current grant.
Workspace is taken from that verified session, never a caller filter. Unsafe browser operations
retain their existing Origin/custom-header boundary; this GET does not create an audit event.
The shared `read_snapshot` helper opens a PostgreSQL `REPEATABLE READ`, `READ ONLY` transaction so
filtered counts and page rows are coherent within one response. Operations uses the same helper
without changing its snapshot meaning.

| `AuditQuery` field | Accepted values and effect |
| --- | --- |
| `page` | Integer 1–100000; default 1; clamped to the final result page. |
| `page_size` | 10, 25, 50 or 100; default 10. |
| `sort` | `at`, `kind` or `actor_name`; default `at`. Event sorting uses the stored kind token. |
| `direction` | `asc`/`desc`; default `desc`. Nulls are last in both directions; event UUID breaks ties. |
| `category` | Empty for all, or `authentication`, `administration`, `operations`, `organization`, `email_delivery`. |
| `query` | At most 128 characters, literal case-insensitive actor/target-administrator display name or event/operation/administrator UUID substring. SQL `%`/`_` are escaped. |
| `from_at` | Optional aware UTC instant; inclusive lower bound. |
| `to_at` | Optional aware UTC instant; exclusive upper bound. If both are supplied, end must be strictly after start. |

Search does not inspect raw payloads, attempted usernames, issuer/subject identifiers, session IDs or
outcome text, readable summaries or before/after mapping values. Adding details does not expand
search to root/leader/designee emails in that evidence. “Unverified attempt” is UI guidance, not a known actor name to search. Sort expressions
and category predicates are allowlisted; input cannot become a SQL identifier or select a workspace.

Recognized parsed controls outside the closed query contract produce 400 `INVALID_AUDIT_QUERY`;
framework numeric parsing remains validation. Selected invalid evidence/storage failures produce
503 `AUDIT_SERVICE_UNAVAILABLE`, not a partial row dump or raw SQL exception. Session denial/outage
uses the existing authentication diagnostics. Pagination affects display only and does not change
retention, mutate history or create a new authority.

## Public fields and source map

`AuditEntry` has twelve fields, including nullable `summary` and the `changes` list. The reader
validates each returned row's canonical data hash and its appropriate actor representation before
exposing the entry. Typed organization evidence supplies allowlisted descriptions; closed inspection,
organization-action and onboarding evidence supplies outcome codes. Other payload JSON remains private.
The digest is an integrity/correlation check, not an authenticity signature against a privileged
DBA. Existing append-only UPDATE/DELETE/TRUNCATE guards and their owner/DDL boundary are unchanged.

| UI / `AuditEntry` field | Existing source and derivation |
| --- | --- |
| Event identifier: `id` | `audit_event.id`; shown as the recorded technical event UUID. |
| Time · UTC: `at` | `audit_event.at`, normalized/rendered in UTC; recorded event time, not a provider observation clock. |
| Event label: `kind` | Closed `audit_event.kind`, mapped to readable labels without creating a new outcome. |
| Category: `category` | Derived from the closed kind groups below; no category column/table added. |
| Actor: `actor_name` | Validated allowlisted `actor_snapshot.display_name` or explicit worker/operator/unverified interpretation below; nullable. |
| Operation target: `operation_id` | Nullable `audit_event.operation_id`; links to the existing recorded operation detail, not a retry control. |
| Baseline target: `baseline_id` | Nullable ID derived from validated baseline draft/publication evidence; links to `/configuration?baseline=…`. A removed draft may be unavailable after local reset; immutable evidence remains. |
| Administrator target: `administrator_id` | Nullable `audit_event.administrator_id`; displayed below the current administrator name for correlation; no administrator-detail route is invented. |
| Administrator target name: `administrator_name` | Nullable current `otm_administrator.display_name`, joined by both workspace and administrator ID, including revoked grants. This is current directory context, not a historical snapshot. Missing records show **Name unavailable** while retaining the UUID. |
| Outcome code: `safe_code` | Closed code from validated inspection, organization-action or onboarding evidence; null where absent. No arbitrary provider/security message is returned. |
| Organization subject: `organization_subject_name` | Nullable bounded display snapshot from typed organization decision evidence; no claim that the display text establishes identity. |
| Details summary: `summary` | Nullable string, at most512characters, derived from typed recorded organization or baseline draft/publication evidence; null where unsupported. Not a new stored column or arbitrary action/provider message. |
| Selected changes: `changes` | Tuple/list defaulting to empty, at most512strings of at most18000characters each. Describes recorded old/new root, segment names, leaders and designee lists, including mapping additions/removals. Baseline draft events describe per-statement, exact budget/currency and static-tag old/new values. Derived from immutable event evidence, never today's settings. |

`AuditDirectory` contains five fields:

| Field | Derivation |
| --- | --- |
| `items` | Ordered, validated `AuditEntry` projections from existing rows. |
| `total` | Count with the same workspace/category/search predicates as the page. |
| `page` | Requested page clamped to the last available page. |
| `page_size` | Accepted allowlisted page size. |
| `pages` | `max(1, ceil(total/page_size))`; zero results still have page 1. |

No payload data/hash, raw claims, actor issuer/subject, password/OTP/seed, credential binding or
session identifier is exposed. SQL loads private evidence for validation, then serializes the closed
DTO; it does not return a whole database row. Selected mapping names and nomination emails are
intentional administrator-visible history, not a full configuration or employee feed. No raw-data
endpoint is provided; the expandable UI uses these same public fields without a separate detail
request. Export uses the identical projection.

## Categories and factual actor interpretation

| Category | Existing allowed kinds |
| --- | --- |
| `authentication` | `local_sign_in_succeeded`, `local_sign_in_failed`, `session_logged_out` |
| `administration` | `administrator_revoked`, `administrator_bootstrapped`, `local_credentials_reset`, `audit_export`, `configuration_review_staged`, `baseline_draft_saved`, `baseline_published`, `baseline_default_changed` |
| `operations` | `operation_intent`, `inspection_dispatch`, `inspection_outcome`, `organization_action_outcome`, `onboarding_action`, `onboarding_outcome`, `configuration_outcome`, `configuration_retry`, `configuration_check_outcome`, `operation_responsibility_changed` |
| `email_delivery` (Email delivery) | `email_delivery` only; independent of the Operations category. |
| `organization` | `organization_configured`, `organization_feed_received`, `organization_feed_rejected`, `organization_published`, `organization_review_decided` |

These categories derive from existing kinds. A future kind requires reviewed contract/source support;
it cannot silently appear as a trustworthy arbitrary event. The historical actor cases differ:

- `operation_intent` identifies the initiating human/application principal through its existing
  `ActorIdentity` snapshot and issuer-qualified key. Display text does not establish employee identity.
- Dispatch/outcome use the existing closed worker snapshot `{kind: "worker", subject: "inspection"}`
  and `actor_subject="otm-worker:inspection"`. The projection validates that representation and shows
  **Inspection worker**. It must not claim the initiating administrator executed a background read.
- Organization lifecycle/onboarding outcomes use the independently validated worker snapshot
  `{kind: "worker", subject: "organization"}` and `actor_subject="otm-worker:organization"`; the
  display is **Organization worker**, separate from the initiating administrator and source
  synchronization actor.
- Bootstrap/reset record the verified database-operator principal. The public label is **Database
  operator**, not a claimed named human; independent operator evidence remains necessary for attribution.
- Failed local sign-in exposes `actor_name=null`; the UI says **Unverified attempt**. This does not
  authenticate `recovery-admin`, identify an attempted username or claim a real administrator acted.
- Other supported principal events use the validated display name, or **Not recorded** if absent.
  Password possession/session audit identifies the shared recovery principal, not every human use.

Malformed actor structure/key or hash fails the returned page unavailable rather than inventing
attribution. Search/sort use the same worker/operator/null display interpretation. Raw attempted
usernames and authentication material are not retained for this feature.

## UI behavior and remaining verification

The page supplies search, category selection, sortable Time/Event/Actor headings, row count, page
buttons, refresh, clear filters and truthful loading/error/empty states. Category and result counts
are history filters, not task counts. Operation links preserve normal navigation into existing
Operations evidence; administrator names and UUIDs remain text, with current names searchable. There is no generic Retry, event edit or delete action. CSV export is a separately audited
preparation request, described below. Inspection-read simulated `needs_attention` guidance remains **“Simulation ended with an issue. No action is required.”** Lifecycle handoff failures require their person/tenancy context; real future remediation remains under its own guards.

At the original read checkpoint, two added top-level schemas (`AuditQuery`, `AuditDirectory`, with
nested `AuditEntry`) brought backend structural schemas to23 and the runtime Python inventory to45;
The original read checkpoint retained six application tables, six migrations/17 migration assets;
the later export checkpoint adds one forward-only revision/two packaged assets, with no new table.
At that checkpoint runtime settings had17scalar keys after instance branding. Current settings
have18keys; simulator JSON/private state remains separate.

At the original read checkpoint, local gates passed: **501 backend unit tests**, **2188/2203 executable lines (99.3191%) across
all 45 modules**; **74 frontend unit tests**, **357/357 lines (100%) across all 11 source files**;
**612 combined backend/PostgreSQL/browser tests**, zero failures/errors/skips. Backend/frontend unit
coverage is independent of database/browser execution. [Development progress](../history/development-progress.md#activity--history-navigation-and-audit-history)
and its validation receipt record scope, source hashes, captures and independent-review disposition.

Unit actor/hash fixtures do not prove database locking or production custody. All fixtures are
synthetic/isolated and separate from the human's persistent local administrator/database and the
organization prototype. No production OCI/SSO/Vault/operator-pod deployment, Git/publication clearance
or full-MVP completion is implied.


## UTC filtering and complete filtered CSV exports

The directory and export share the exact same category/search/sort/direction predicates and
workspace-bound join. The UI labels both date/time inputs **UTC**; `from_at` is inclusive and
`to_at` exclusive. JSON/query timestamps must be explicitly UTC; naive, non-UTC and contradictory
ranges return400 `INVALID_AUDIT_QUERY`. No date filter means all retained history. These filters
change visibility only; they never truncate or delete authoritative events.

`AuditExportQuery` has exactly six fields: `sort`, `direction`, `category`, `query`, `from_at`,
`to_at`, with the same meanings as the directory. Paging is deliberately absent and forbidden.
`POST /api/audit-history/export` accepts bounded JSON (4096bytes) with normal HTTPS/Host,
same-origin/custom-header and fresh current-administrator guards. Its request scope comes only
from the verified session. It returns `text/csv` with attachment name `audit-history.csv` and
`Cache-Control: no-store`. Failed validation/storage/commit returns a fixed diagnostic rather
than partial CSV or a private exception. This is a read/export of the safe projection, not raw
provider/security payload export.

The export reads every matching row from one `REPEATABLE READ` transaction, independent of the
current displayed page. It bounds allocation to10001rows: up to10000 may be exported; reaching
the sentinel returns413 `AUDIT_EXPORT_TOO_LARGE`. The UI asks the administrator to narrow the
date range/search; it never silently returns only the first page or first10000rows. A zero-match
export contains headers only. The cap bounds this V1 synchronous operation; background large
exports are not implemented. Export failures leave the existing history filters intact.

| CSV column | Meaning |
| --- | --- |
| `id` | Recorded event UUID. |
| `at` | Event time as explicit UTC ISO8601. |
| `kind` | Closed event kind, including `audit_export`. |
| `category` | Derived authentication/administration/operations/organization/email_delivery category; the latter displays as Email delivery. |
| `actor_name` | Same validated actor interpretation as the UI; null is an empty cell. |
| `operation_id` | Recorded operation UUID when present. |
| `administrator_id` | Recorded target administrator UUID when present. |
| `administrator_name` | Current workspace-scoped directory label, not a historical snapshot. |
| `safe_code` | Closed inspection/organization-action/onboarding code when present. |
| `organization_subject_name` | Nullable recorded organization decision subject display. |
| `summary` | The same nullable human-readable action summary displayed under Details. |
| `changes` | JSON array of the same selected historical change strings displayed by View changes; an empty array when no selected details exist. |

The export has exactly twelve columns in the order above. Array values use JSON rather than raw
configuration serialization. Every cell is CSV-quoted. Formula-leading text (including leading whitespace/BOM) and text with
C0control characters are prefixed with an apostrophe so spreadsheet software treats them as text.
Ordinary commas/quotes remain losslessly quoted. UTF8BOM supports common spreadsheet importers.
No raw evidence, claims, session hash/ID, password, factor, key or Vault binding is exported.

### Preparation evidence and authority

Before returning any bytes, OTM commits an immutable `audit_export` event attributed to the
verified administrator. Its label is **Audit export prepared**: server preparation is evidence,
not proof the browser saved or opened the file. The current export does not include its own
subsequent preparation event. A later read/export can see that event under Administration.

`AuditExportEvidence` contains only `contract_version="audit-export-1"`, bounded `row_count`, and
`query_digest` (canonical SHA256 of the six validated filters). The raw search/name/email and CSV
contents are not copied into event data. The event row separately stores the ordinary verified
actor snapshot, administrator target and server preparation time. Hash and closed evidence shape
are validated before displaying a preparation event.

Export acceptance locks the same protected recovery-administrator anchor used by revoke/reset,
then locks the exact stored session. It samples server time **after** waiting for these locks and
checks revocation, idle/absolute expiry and exact issuer/subject/current-grant revision. The locks
serialize accepted export preparation with revocation/logout/reset; a previously valid browser
principal cannot substitute for current authority. Serialization/commit failure discloses no CSV.
Normal directory reads remain short read-only snapshots. Existing runtime role privileges suffice;
no audit UPDATE/DELETE/TRUNCATE, extra grant or ownership privilege is introduced.

Migration0007 preserves all earlier immutable rows/guards, adds only the closed preparation kind
and the `(workspace_id, at, id)` index. It is forward-only and packaged alongside its checksum;
prior migration bytes remain unchanged. No fake export activity is seeded by migration/setup.


At the historical export/organization-extraction checkpoint the inventory was25structural schemas,
51runtime modules, six application tables, seven frozen migrations/19migration assets and17
application TOML scalar keys. These are not current inventory claims. Current complete-source
unit/database/browser results are recorded
in [development progress](../history/development-progress.md), rather than the historical read-only
checkpoint counts above.


## Organization event family

The [organization snapshot store](organization-storage.md) adds four closed kinds under
**Organization**. Configuration/receipt have the verified administrator actor; publication/rejection
use the exact closed **Organization synchronization** service actor after the same authenticated
command boundary. The shared reader validates `OrganizationEvidence` and the actor/body hash.
The target label is **Workspace organization**, derived from that category; it creates no fake
organization detail link. Raw feeds, complete employee profiles and full configuration remain private;
selected recorded mapping values are intentionally visible through summary/changes. At the original
store checkpoint CSV kept nine safe columns; the later subject display and current summary/changes
extensions bring the projection to twelve columns.

At that store-only checkpoint the inventory was27generated models,54runtime modules,11application
tables and8migrations/21migration assets, with17TOML keys. Those counts are historical. The current
organization/tenancy runtime has14application tables at0010_guided_onboarding and18TOML keys; this
details extension adds no table, column or migration.
The source-specific field/transaction map is separate from the original read checkpoint counts above.

## Organization workflow history

[Organization workflow evidence](organization-workflows.md) adds `organization_review_decided` and
`organization_action_outcome` plus typed `organization_action` intent under existing `operation_intent`.
Decision evidence retains permanent request key/digest/receipt and bounded person/review/action/name
facts. The organization worker uses the closed worker subject `organization`, distinct from the
initiating human and source synchronization actor. The nullable `organization_subject_name` is a
recorded display label, not a raw employee/profile/intent object. With summary/changes, the current
UI/CSV projection has twelve fields. Existing cap/formula protection/UTC filtering/preparation
semantics remain; prior checkpoint receipts are historical and do not establish the latest detail
projection's final validation result.

## What did the administrator change?

The table's Details column replaces the former outcome-only heading. Organization events show an
allowlisted readable summary. When changes exist, native View changes (N) disclosure expands the
recorded values; opening it does not fetch private JSON, mutate audit history or initiate remediation.
Other events retain their closed outcome-code fallback, or a dash when neither description nor code
exists. React renders these values as text, not HTML.

For mapping Apply, the typed immutable event already records mapping_root_before, mapping_root_after
and mapping_changes. The description shows changed root emails, added/removed segments, renamed
segments, changed leader emails and old/new designee lists. Initial setup uses Not configured for an
absent former root; an empty nomination list is None. An Apply recording no mapping difference says
Applied unchanged organization mappings. Older configuration events without recorded change details
say those details were not recorded; the app does not reconstruct them from current settings.

Organization decisions use readable allowlisted actions. Offboarding with an accepted operation
receipt says Requested employee offboarding; a receipt with no queued operation says Offboarded
employee. Missing receipt evidence uses neutral Recorded employee offboarding decision rather than
claiming completed work. Requested creation/import/transfer/removal is not provider verification.
Feed receipt says Received organization feed without fabricating a zero employee count; publication
reports organization profiles, which can include retained or reference identities, not just incoming
employee rows. Rejection reports the recorded diagnostic count.

Descriptions preserve recorded event intent and outcomes while current administrator_name remains
separately labeled live directory context. They do not change actor attribution, target binding,
authorization, search predicates, indefinite retention or append-only protections. The allowlist
exposes selected nonsecret mapping values to current workspace administrators; it excludes complete
configuration, HR feeds, credentials, factors, key material, raw SDK errors and arbitrary unknown action
strings. CSV uses the same projection and existing formula/control-character protection. No new
audit data, history store, schema column, permission grant or mutation route is introduced.

This details slice passed1,025backend/database/HTTPS-browser tests and176frontend units.
Separate unit-only coverage is96.17% backend and97.51% frontend; the existing runtime authority
and audit immutability are unchanged. Independent documentation, security and UI/UX reviews passed.
Validation receipt (private historical evidence; not distributed).
The dated progress/receipt will record results; earlier receipts remain evidence only for their own
source checkpoints. See [development progress](../history/development-progress.md).


The Category filter reserves a13rem minimum width (195px at the application's base font size)
so its full labels and indicators fit. Its toolbar still wraps, and the filter expands to full width
on narrow screens. This audit-only sizing rule does not change category/filter behavior.


## P3.1 baseline authoring audit extension

`AuditEntry` now has13fields, including nullable `baseline_id`. The CSV remains12columns; its
summary/changes carry version/revision and selected recorded recipe deltas without a new ID column.
`baseline_draft_saved` uses `baseline-draft-1` typed before/after evidence and is inserted in the same
transaction as the recipe. Unchanged retries create no duplicate event. Authored statements and tag
values are intentionally administrator-visible configuration, never a channel for credentials.
See the [implemented baseline field map](baseline-authoring.md).


## Baseline publication evidence — P3.2a

Publishing a saved baseline records `baseline_published` atomically with the immutable version.
The closed evidence captures the exact version ID/number, parent, content/hash, publisher key and
display-name snapshot, UTC publication time, `publication_mode=simulated` and the fixed
`baseline-structure-simulated-1` qualifier. The projection checks content hash and correspondence
with the event's actor/name/time, labels the event **Baseline published**, and links to its read-only
published version. Details explicitly state that local structure/USD checks do not qualify or apply
OCI configuration. Retrying the exact original publish command creates no second event. Existing draft
save history and old payloads remain readable. No credential or provider response is captured.


Historical baseline_default_changed events from the withdrawn P3.2b manual-selection feature remain
readable through BaselineSelectionEvidence. No route emits new selection events. Latest publication
now determines the new-operation default automatically; history retains what actually happened.

### Baseline application evidence

Baseline-update acceptance records the complete immutable recipe and exact child targets under an
operation intent. `configuration_outcome` records one child/category-safe result and complete
verification time where successful; repeated attempts remain separate immutable events.
`configuration_retry` records the responsible administrator's retry of the unchanged accepted batch.
Audit renders friendly result summaries and exact baseline-version links with Back to audit history.
No provider credential, password, PEM key or raw SQL diagnostic enters these event payloads. The
stored fake-object observations are local simulation state rather than proof of real OCI configuration.
See [configuration updates](configuration-updates.md) for all fields and relationships.

### Friendly lifecycle targets

Directory entries now supplement the operation link with typed `AuditEntry.resources` entries
(`AuditResource.kind`, `id`, `name`). The original revision-1 intent is parsed after hash/workspace
validation. Employee labels use that frozen display name; registered tenancy labels use the current
same-workspace registry. Configuration child outcomes narrow context to that accepted child. This
is derived display context, not a rewrite of immutable historical names. No cross-workspace target
can supply a label. Large batches collapse under an affected-resource count. Registered tenancy
names link to their detail; employee names remain readable beside the operation link. Existing CSV
columns/export semantics are unchanged by this directory-only enrichment.


## Qualified local read-only configuration-check outcomes

Local qualification and both saved-instance upgrades pass. Existing operation_intent records the verified administrator's explicit check
request. Each sealed child attempt appends closed configuration_check_outcome evidence and a
same-scope check-row reference/hash; actor snapshot must match the Configuration check worker.
Audit summary says Read-only configuration check plus its state. This is an observation, not a
configuration change or successful repair. No raw SDK response, credential or fake user simulator
command is exposed. [Evidence field map](configuration-drift.md).


## Qualified local guided responsibility audit

Local qualification and both saved-instance upgrades pass. operation_responsibility_changed is an append-only operation event with a
closed twelve-field ResponsibilityEvidence payload, claimant actor snapshot and original intent
context. Audit History displays Administrator responsibility changed with previous → replacement
name evidence; it does not present the claim as provider success, ownership transfer or email
delivery. Historical creator and activation mailbox are never overwritten.
[Full field map](responsibility.md#complete-field-and-storage-map).


## Lifecycle delivery evidence — source candidate

Validation pending. email_delivery uses closed six-field NotificationEvidence (version, notice ID,
intent hash, state, bounded attempts, nullable safe code) with a validated Email worker actor. It
records head transitions without copying mailbox/message content into that evidence. Outbox intent
retains exact immutable routing separately. Sent is acceptance, not inbox delivery; unknown is not
proof of failure/unsent. [Field and state map](lifecycle-email.md).


## Separate Email delivery category: 5 November 2026

Locally qualified. Audit History now offers Email delivery (category=email_delivery)
as a separate filter for the existing email_delivery kind. The Operations audit category excludes
those delivery-state records. All categories still includes them, and existing retained rows are
classified by their kind at read time; no audit record, hash or delivery history is rewritten.

Directory and CSV export share the same new category predicate/projection, with existing date,
search, sort, paging, authorization and export limits unchanged. CSV column layout stays the same;
new exports label these rows email_delivery, while previously downloaded files are not modified.
This does not remove delivery events or the notification panel from normal operation detail. No
SQL column/migration, send/retry behavior, recipient, outbox state or user data changes are required.


5 November category refinement validation (private historical evidence; not distributed): both unit coverage gates and focused PostgreSQL/SMTP/Playwright tests pass; documentation, security and responsive UI reviews pass. Both saved applications were updated without schema changes or rewriting any existing rows.

## Cost collection worker events

Cost outcomes validate the exact worker identity: actor_subject otm-worker:costs with
actor_snapshot {kind: worker, subject: costs}. They display and search as **Cost collection worker**;
the outcome code comes from validated CostEvidence. The directory and CSV export use the same
projection. Human-shaped or mismatched worker identities remain invalid. Existing immutable events
are read correctly without deleting, rewriting or skipping history. Regression coverage includes
real worker-written records through PostgreSQL search/export and browser navigation after a refresh.
