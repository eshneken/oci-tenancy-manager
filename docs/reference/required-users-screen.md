# Required users: identity records and manual presence checks

Tenancies → select a tenancy → **Required users**, below Accountability & registration.
The section has two independent cards, **Automation user** and **Recovery user**. Identity records
and presence are separate. Recorded/Not recorded/Retired record describe stored mappings; they do
not establish cloud existence or credentials. Retired record does not assert OCI account deletion.

**Refresh user data** now admits an asynchronous presence-only operation when a qualified current simulated
connection and both exact bound users exist. It does not check administrative permissions, console
access, MFA or recovery readiness. **Permissions: Not checked** remains on both cards. The banner
explicitly identifies local simulated fixture data; Present must never be described as live OCI
verification. No new primary menu, daily scheduler, repair, email or password action is added.
Local qualification and the main-preview upgrade pass; the parallel test preview is unchanged. See the [final receipt](../history/manual-presence-checkpoint-2026-11-06.md).

## API and all 22 public display fields

`GET /api/tenancies/{UUID}/required-users` uses current administrator/session authorization and a
single noncacheable read-only repeatable snapshot. Workspace comes from the principal. Foreign and
unknown UUIDs share a 404; malformed UUIDs fail validation. No provider or queue is invoked by GET.
Broken stored relations/evidence return unavailable rather than an invented empty inventory.

`POST /api/tenancies/{UUID}/required-users/check` accepts only PresenceCheckRequest.client_request_key,
under existing unsafe-request/Origin protections. A 202 ActionReceipt records admission/replay; the
separate native worker acquires results. The [check reference](user-presence-checks.md) maps the
request, authority, immutable evidence, attempt fencing, SQL columns and failure semantics.

| DTO / field | Source and interpretation |
| --- | --- |
| RequiredUsersDirectory.tenancy_id | Same-workspace otm_tenancy.id. |
| tenancy_status | Registry pending/active/terminating/terminated/failed/cancelled; not independent OCI lifecycle proof. |
| provider_mode | Registry context, currently simulated. |
| check_available | Derived from active idle registered child, current provider availability and all exact bindings/selected connection. False for historical unqualified children; no guessed backfill. |
| check_unavailable_reason | Null when eligible; otherwise tenancy_inactive, tenancy_busy, provider_unavailable or not_configured, with explanatory UI text. |
| pending_operation_id | Matching-current-context queued/running check UUID, nullable. Drives progress/polling, not a positive observation. |
| users | Exactly two ordered RequiredUserRecord values, automation then recovery. |
| RequiredUserRecord.purpose | automation/recovery from canonical logical keys. |
| identity_state | recorded for active mapping, not_recorded for none, retired for retained retired mapping. |
| identity | Null exactly when not_recorded; otherwise the following seven-field model. |
| presence | Independent four-field UserPresenceView below, defaulting to not_checked. |
| RequiredUserIdentity.user_name | User binding.user_name; escaped observed display metadata, never an adoption key. |
| user_ocid | User binding.provider_ocid, separate from SCIM ID. |
| scim_resource_id | User binding.scim_resource_id. |
| domain_ocid | Referenced same-child domain binding.provider_ocid. |
| recorded_at | User binding.created_at, displayed UTC; not a later provider-read timestamp. |
| retired_at | User binding.updated_at only when retired, otherwise null. |
| source_operation_id | Binding.created_operation_id; internal View setup operation link. |
| UserPresenceView.state | not_checked, present, missing or unknown; rendered Not checked, Present, Missing or Unable to verify. |
| checked_at | This subject observation's captured_at; null if no current-context result. Unknown is labeled Last attempt (UTC); confirmed results use Checked (UTC). |
| stale | Server UTC is outside [captured_at, captured_at+24 hours); out-of-date label supersedes fresh-result styling and preserves last result text. |
| operation_id | Exact check operation UUID, nullable; View check opens its retained Operations detail. |

The reader selects the latest canonical generation per logical identity key, checking domain/user
kind, ownership, exact same-child reference, shared capture provenance and compatible record state.
[Bindings](managed-object-bindings.md) and [connections](user-presence-connections.md) remain their
own storage. Migration 0025 adds a [14-column check record](user-presence-checks.md#physical-storage-all-14-check-columns),
not access-assignment, credential or privilege heads. No read backfills historical mappings.

## Behavior, progress and error boundaries

- Refresh user data is disabled with an explanation for pending/inactive/busy/unqualified tenancies or an
  unavailable selected provider. A historical identity alone cannot enable acquisition.
- A pending receipt shows Refreshing user data… and polls records once per second. Previous results remain
  dated; an accepted operation is not completion. On completion the per-account outcomes and times
  refresh, with View check linking to the actual operation. Operations success means bounded
  outcomes were recorded, even when an outcome is Missing or Unable to verify.
- There is one normal refresh action in this section: Refresh user data requests acquisition.
  Page-level Refresh reloads stored records without creating a job. Failed background reads
  explicitly label retained data and offer Retry loading users; initial
  loading/failure is distinct from a successful Not recorded result. 401/403 hides retained facts
  immediately while the app expires the session.
- A failed/uncertain Refresh user data request retains its UUID while this component is mounted, allowing
  Retry user refresh with the same logical request. After navigation/reload, inspect Operations
  before issuing another request; no reload-durable browser key cache is claimed.
- The private query key includes the child UUID. Switching children cannot borrow another child's
  data; logout clears private cache. No navigation attention badge is added for diagnostic reads.
- Presence and identity remain separate. Independent observations can be Present/Missing/Unable
  to verify. At 24 hours, Check out of date and last-result text replace a current success claim.
  A changed binding/connection/policy/child context cannot make old evidence current.
- Identity details uses native keyboard disclosure with domain/user OCIDs, SCIM ID, UTC record/
  retirement times and the setup link. Long IDs wrap. Cards share a row on desktop/tablet and
  stack below 700px; disclosure expansion remains independent. Refresh/check controls stay reachable.

## Qualification boundary

The complete unit/coverage and all-postgres/native-browser lanes pass, with independent security/UI review. Main-preview preservation is verified; the parallel preview remains unchanged. Unit/API, disposable PostgreSQL and native browser scenarios distinguish exact presence from scope/permission failure, exercise replay/attempt/context/ordering/freshness guards and retain the auth/error/cache/responsive cases. The local adapter reconstructs fixtures
from authenticated onboarding producer evidence rather than current expected IDs. This is not
real account discovery and cannot qualify SDK/network failures or actual authorization.

See the [manual local runbook](../how-to/required-users-runbook.md) and
[pending real OCI manifest](../how-to/real-oci-test-manifest.md). Privilege, credential custody,
readiness and repair remain separate future work; presence-only reads do not require fabricated
assignment/profile tables.

## Inventory summary — source checkpoint

The new [Required users summary field map](required-users-summary.md) adds a derived
TenancyView.required_users value to directory/detail responses and a compact link in the existing
Tenancies Status cell. RequiredUsersSummary has four fields; its automation/recovery values reuse
the four-field UserPresenceView. The 22-field directory above is unchanged. Shared context/evidence/
freshness helpers keep summary and cards aligned; the title/accessible description retains each
account's own result and UTC time, simulation and Permissions not checked. Deep linking focuses the
Required users heading after terminal success or a nonauthorization read error such as 503; 401/403 does not focus or expose data. Current source adds no table, filter, provider call or job.
Summary qualification and the main-preview update now pass; the parallel preview is unchanged. [Final summary receipt](../history/required-users-summary-checkpoint-2026-11-06.md). Earlier Refresh user data qualification retains its original pipeline scope.

The summary's positive-label guards require per-account timestamp/check references; a configured
broken canonical connection is Unable to verify in inventory and a closed 503 in the expanded view,
while genuinely unconfigured or validly changed contexts stay Not checked. Inventory configuration
badges use Config: and account summaries use Users:; detail configuration labels retain section
context. The final summary qualification and preserved-data main update pass.


## Unavailable Refresh user data

Refresh user data requires both recorded exact identities and a qualified automation connection from the
current create/import setup flow. Older registered tenancies are not enrolled automatically; merely
having a tenancy record or reloading it cannot create that authority. The disabled button describes
its visible prerequisite notice for assistive technology. Local testing can use a newly created or
imported simulated tenancy after setup completes. Do not backfill or reinterpret older audit events.

There is no second saved-record refresh button in Required users. Initial display and pending
polling read stored facts automatically; page-level Refresh also reloads them. A record-loading
error offers **Retry loading users**, a read retry rather than a second normal acquisition action.

## Consistent provider refresh terminology — 7 November 2026

**Refresh user data** (formerly Check now) starts the existing asynchronous presence-only read,
just as **Refresh costs** requests a fresh budget read. Local development still uses the simulator.
**Refreshing user data…** indicates work in progress; **Retry user refresh** retains the same
request key after an uncertain response. No API, operation, eligibility or identity guard changes.
The sole normal action mirrors Refresh costs. Automatic pending polling updates the display;
there is no separate saved-record refresh button. No user repair, enrollment or privilege
verification is implied. Inventory's compact Checking… indicator remains a status, not an action.
