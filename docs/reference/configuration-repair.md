# Selected configuration repair

Configuration drift detail now supports an explicit preview and confirmation for selected confirmed
Missing/Different categories. The current capability is simulated, using the existing native
configuration worker. There is no live OCI call, scheduler, simulation-control UI or new table.
[Check semantics](configuration-drift.md) and [assigned baseline/overrides](tenancy-overrides.md)
remain authoritative; repair never chooses the latest publication or creates a desired revision.

## Screen flow

Open a tenancy's Configuration drift detail after a fresh complete check confirms a difference.
**Repair configuration** opens a modal with the confirmed categories selected. Deselect categories
that should remain unchanged, choose **Preview repair**, then **Repair selected objects**. The modal shows the fresh server-resolved assigned version and expected/observed values. The server
revalidates the exact selection before atomically recording and enqueuing the operation. Changes to
evidence, assignment, bindings or observed values invalidate the preview. Unknown/incomplete, stale,
unregistered, paused or busy contexts cannot authorize repair. The button is hidden when a fresh
complete check is required; the server independently enforces eligibility.

Acceptance keeps prior confirmed findings visible and reserves that tenancy. The durable worker
rechecks administrator authorization, runtime policy, assignment and all four exact retained
bindings before writing. Only the selected owned objects can be changed. The assigned baseline and
accepted statement-list/budget overrides are preserved, even if a newer baseline is published.
Owner-created objects and unrelated resources are outside scope.

All four categories are independently read after selected writes. Complete selected readback plus
complete overall observation permits completion; unselected differences remain confirmed drift.
Only an all-matching read advances the whole-configuration verification time. A failed/incomplete
read leaves the operation unverified and prior findings open, preserving partial local effects for
an explicit supported retry in Operations. It does not seal a misleading success check. A changed
assignment/binding is a blocked target, not authorization to adopt another object.

## Contracts and storage

| Boundary | Stored/request fields and behavior |
| --- | --- |
| POST `/api/configuration/repairs/preview` | `ConfigurationRepairRequest`: exact `tenancy_id`, 1–4 unique `categories` from policy/quota/budget/tags. Returns `ConfigurationPreview` with fresh `repair_expected` and `repair_observed` category/payload maps for confirmation; no client-authored content or credentials. |
| POST `/api/configuration/updates` | Existing `ConfigurationUpdate` gains optional `repair_categories`; a repair must be one tenancy, with no override editing or saved rollout plan. Exact `preview_hash` and request UUID retain normal replay rules. |
| Immutable `ConfigurationIntent` | Existing `configuration_update` kind gains `change_kind=repair`. Each target freezes `repair_categories`, `repair_bindings` (all four exact OCIDs), `repair_context_hash`, `repair_observation_hash`, `repair_check_id`. Other kinds cannot carry repair metadata. |
| `otm_operation` / `otm_operation_step` | Existing reservation, queue, scoped intent, per-target outcome and supported retry; no additional coordinator. Acceptance does not advance the tenancy revision or desired/verified heads, preserving the source finding context. |
| `otm_configuration_check` / immutable audit | Successful complete verification seals a check against the actual final released tenancy revision. Its operation FK points to the repair operation; no fabricated standalone check operation is introduced. Existing read-only check step records the acquisition evidence. |

Preview map keys are policy/quota/budget/tags; each payload is bounded to 700,000 characters.
`repair_observed` null means confirmed authorized absence, never a failed read. An uncertain
submission freezes its selection, preview and key across modal close/reopen; Retry same request
preserves them. A full browser reload requires reviewing Operations before new work.

The first dispatch requires the original observation fingerprint. A known partial local attempt may
retry after independently rereading the same retained bindings; its own partial effects do not
invalidate the original target. Workspace/administrator/operation/child locking serializes local
reads and writes. Completion advances the tenancy revision and seals current-context evidence in
that same transaction. Older queued checks become superseded and cannot green the repaired context.
Repeated native deliveries skip verified targets and cannot duplicate the sealed check.

No migration is required: new fields are typed immutable intent JSON. Existing accepted update
JSON remains readable, and request hashing omits empty new fields to retain replay compatibility.
The [configuration model](../engineering-design/10-configuration-data-model.md) still describes the
larger future OCI binding model. This local implementation does not qualify real OCI recreation,
SCIM access, permission probes or network-write ambiguity/reconciliation; live adapters require
separate qualification. No local scheduler or cloud drift-injection scaffolding is added.

## Regression coverage and manual review

Unit cases cover closed request scope, stale/unknown evidence, parent/policy/binding fences,
selected-only writes, readback failures, admission and worker boundaries. Disposable PostgreSQL cases
cover unchanged configuration revisions, preserved unselected findings, request replay, partial
failure/retry, later publication and older pending check supersession. Native HTTPS/worker Playwright
covers preview/confirm, completion, reload and widths 1280/390/320. Ordinary local users cannot
manufacture drift through a new simulator UI; interactive cloud-drift qualification remains pending
a controlled OCI tenancy. Existing [check runbook](../how-to/configuration-drift-runbook.md) still
covers nonmutating checks.
