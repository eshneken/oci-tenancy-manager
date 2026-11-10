# Automation signing-key inventory and observed age

9 November 2026 · Targeted local UI checkpoint qualified and installed; real OCI and rotation enforcement pending

[Selected 30-day policy](../engineering-design/22-credential-security-lifecycles.md#thirty-day-otm-api-key-policy) ·
[Required-user reads](user-presence-checks.md) · [Live qualification](../how-to/real-oci-test-manifest.md#automation-signing-key-inventory-qualification)

## Observation-only scope

Current UI source follows the approved separate compact **signing-key panel below Required users**. Refresh
reuses the existing authenticated required-user operation rather than a second scheduler or per-row
provider call. It observes only the exact registered automation user’s public key metadata. It does
not select/test a signer, retrieve a PEM or secret, establish custody, rotate/delete keys, send alerts,
block other work or certify compliance. Recovery/password access remains independent.

Chapter22’s 30-day retirement obligation remains accepted **future enforcement work**. Observed age
labels do not mean OCI automatically expires a key or that OTM currently enforces deletion. Unknown
keys are not adopted as managed credentials, and no unrelated key may be removed to free a slot.
There is no new table, migration or operational setting for this inventory slice.

## Independent source and read boundaries

Only explicitly opted-in NEW create/import operations carry optional
`OrganizationIntent.automation_key_inventory_contract="automation-key-inventory-1"`; this requires
existing opted-in permanent-user capture. During simulated `configure_required`, the producer creates
bounded public metadata once, using its original server/provider clock. Retained fixture creation
uses exclusive creation so retries/restarts preserve that timestamp. Capture and refresh read retained
producer facts; neither creates/backfills a missing key record. Older accepted operations and saved
children lacking metadata stay unavailable rather than receiving fabricated keys.

`OnboardingUsers.automation_keys` and `PresenceCheckEvidence.automation_keys` omit absent optional
fields to preserve historical hashes. The check targets the exact automation identity/domain/SCIM/OCI
references and existing attempt/connection context. Actual returned subject facts are independently
validated; wrong scope, unsupported/denied/partial reads, clock errors, duplicate key IDs/fingerprints
or bound overflow cannot establish a complete inventory. Provider calls run outside transactions.
The worker seals evidence only under current attempt, authorization, lifecycle and binding guards.

A complete authorized **empty** list is known zero inventory. A missing legacy capture or failed
read is unavailable, never zero. A known key with missing/invalid-age creation evidence remains a
known inventory row with **Unknown age**. These are separate facts. Original creation time is never
inferred from user creation, connection/feed/observation time, activation or process restart.

## Field dictionary and existing persistence

| Contract / field | Meaning |
| --- | --- |
| `ObservedAutomationKey` | `provider_key_id`, normalized lowercase colon-separated 16-byte `fingerprint`, nullable UTC `created_at`, provider `state` active/inactive/unknown. Resource ID is opaque; identity-domain SCIM/composite key IDs are not necessarily OCI OCIDs. No PEM data. |
| `AutomationKeyFacts` | Independently returned `user`, `authorized`, `complete`, `supported`, bounded `keys` (max 16). Complete pagination is required; bounds are not a claim of service quota. |
| `AutomationKeyCapture` | `facts`, retained in private immutable onboarding evidence; expected identity does not manufacture observed metadata |
| `InspectAutomationKeys` | Exact existing read `context` and automation `target`; browsers do not select user/key IDs or authority |
| `AutomationKeyObservation` | Actual `context`, `target`, `captured_at`, `facts`; 30-second read window and exact subject/coverage guards |
| `AutomationKeyCheck` | `context`, `target`, `checked_at`, state known/unavailable and bounded safe keys. Unavailable results contain no partial rows. |
| `AutomationKeyView` | `provider_key_id`, `fingerprint`, `created_at`, `key_state`, derived `age_state`, optional whole-day `age_days` and `retirement_due_at` |
| `AutomationKeysView` | state not_checked/known/unavailable/stale; optional `checked_at`, `age_as_of`, `operation_id`; bounded derived `keys` |

The current detail API adds `RequiredUsersDirectory.automation_keys`. Existing immutable check
outcome JSON owns the evidence and operation reference. No API-key credential/version row, selected
fingerprint head, association or new foreign key is created. Invalidated identity/connection/context
does not borrow another subject’s history; compatible harmless registry changes retain dated facts.
A stale result stays dated, never renewed by opening the page.

Age is observational: active known creation time yields within_limit before day 29, due_soon at day 29
and overdue at day 30 (exact 2592000 seconds). Inactive key rows have inactive age status; unknown
provider state or unavailable creation evidence has Unknown age. Creation timestamps future-dated at their own key check remain Unknown age at later display
times until a new qualified read, never a fresh 30-day lease. No age result grants signer usability or triggers enforcement.
Current tenancy projection uses server read time as `age_as_of`; the planned historical Operations
projection uses the recorded observation time. Both preserve original UTC creation/observation facts.
Historical `OperationEventView.automation_keys` now carries the optional derived `AutomationKeysView`
on required-user outcome events. Operations renders the same panel in historical mode; its age basis
must be the recorded key-check time. The source uses the key check’s own `checked_at`, not aggregate peer-check completion, for
historical age. The [checkpoint receipt](../history/automation-signing-key-inventory-checkpoint-2026-11-09.md)
records targeted local qualification/publication separately from full milestone/PR qualification.

## Checkpoint review and tests

After this checkpoint is actually qualified and installed in the sole main 8443 app, use a NEW normal
opted-in simulated create/import child. Complete setup, Refresh user data and review the separate
key panel. Existing children are not silently upgraded. Dates/age basis and the source operation
should remain explicit after navigation/reload. No other local instance or artificial main drift is
needed; missing/aged/denied scenarios belong in disposable automated fixtures, not a product fault UI.

Required regressions cover complete empty versus unavailable, per-row Unknown age, unknown/inactive
state, exact day 29/day 30 boundaries, UTC/clock behavior, stable creation over repeated setup/refresh/
restart, malformed/duplicate/overflow metadata, denied/partial pages, cross-subject/context capture,
stale/late/superseded publication, immutable legacy omission and absence of PEM/secret data. Test
current versus historical age clocks separately and ensure inventory never gates password/lifecycle
work, creates credentials, rotates/deletes, emits alerts or claims compliance.

Live API identity/timestamp/pagination/permission behavior remains Pending. Actual SDK key identifiers
must be normalized without assuming OCID shape. The public inventory is not a live adapter or
proof of the broader 30-day rotation/capacity/retirement workflow.


## Panel values and links — source checkpoint

`AutomationKeys.tsx` shows **Automation signing keys** with an explicit Simulated inventory label.
Known rows display fingerprint, Created (UTC), Key age and 30-day date (UTC); the opaque provider key
ID appears only as fingerprint title metadata. Ages map to Under 30 days, Due within 1 day, 30 days or
older, Age unknown or Inactive. The label describes observed age, never enforced expiry/compliance.
Known-empty, unavailable, stale and not-checked states have distinct text.

Inventory checked links to its exact operation’s `#automation-keys` section; current age shows
**Age assessed**, while Operations shows **Recorded check** and **Age at observation** without
recomputing historical age from today. Compact UTC dates retain full instants in title/time metadata.
The source fields are `checked_at`, `age_as_of`, `operation_id` and the row dictionary above; labels,
layouts and displayed day counts add no storage. This exact new fragment is included in the bounded operation-return helper and focus logic,
alongside the original five user-check targets.

The [checkpoint receipt](../history/automation-signing-key-inventory-checkpoint-2026-11-09.md) records
passing targeted validation and preserved main publication, with exact native versus later accessibility
edit scope. It is not new full-suite/milestone/PR qualification. Key rotation/enforcement remains Pending.


## Independence and setup-polling corrections — source checkpoint

Current inventory age metadata is excluded from the password dialog’s readiness revision signal.
A read-time/age-only inventory change must preserve existing consent and a displayed transient
password; this observation-only feature adds no password gate. Exact user/policy/readiness changes
continue to invalidate access normally. A composed UI regression covers both preserved consent
and value, rather than only the isolated signing-key component.

Onboarding keeps polling queued/running work and the `waiting`/`configuring` machine phase while
background password setup completes. Human-action waits and terminal phases stop polling. This
prevents an obsolete Setting up access display after the durable operation succeeds; it does not
authorize extra provider actions or change stored state. Targeted local qualification/publication pass in the receipt; live-only cases remain Pending.


## Manual review on the installed main application

1. Reload **https://localhost:8443**. Use only this existing instance; 8444 remains retired.
2. Normally create or import a NEW simulated tenancy and complete its ordinary setup. Do not reset
   the organization, rewrite an older setup or supply real keys; the inventory metadata is synthetic.
3. Open the new tenancy’s Required users and select **Refresh user data**. After acquisition finishes,
   inspect **Automation signing keys**, the separate panel immediately below Required users.
4. Review fingerprint, original creation date, observed age/30-day date and the distinct Inventory
   checked/Age assessed dates. No row is selected as an active signer and no key action is offered.
5. Follow the inventory date to its exact historical operation section. Recorded check/Age at
   observation use the original key check time; navigate back and reload to verify dated persistence.
6. Older tenancies without the new metadata may remain unavailable. This is expected and is not
   zero-key evidence or permission to backfill. Never alter main clocks/files to create aged rows;
   age/negative scenarios are covered by disposable tests and pending real-provider qualification.
