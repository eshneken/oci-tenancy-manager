# Managed automation signing-key rotation

10 November 2026 · Implemented source subset; **targeted local qualification and saved installation PASS**.

[Execution accounting](../engineering-design/23-signing-key-rotation.md) ·
[Editable ER source](../architecture/diagrams/signing-credentials-implemented.mmd) ·
[Observed inventory](automation-signing-keys.md) ·
[Live qualification](../how-to/real-oci-test-manifest.md#credential-security-lifecycles)

This reference describes candidate source/migration 0028, not a completed full milestone.
[Targeted evidence and installation status](../history/signing-key-rotation-checkpoint-2026-11-10.md)
remain separate from live qualification. Saved 8443 now runs this preserved targeted-qualified
installation; no second local instance is authorized. Targeted unit, restricted-role, native worker, notification and browser checks have passed;
complete-integration/PR/live qualification remains Pending. No live
OCI, RSA/PEM signing or Vault SDK capability is claimed. The selected simulator stores deliberately
nonusable material markers privately; exact metadata references never contain private material.

## Enrollment, schedule and execution

Fresh opted-in create/import intent adds `prepare_automation_signer` after canonical identity capture
and before recovery-password preparation/temporary cleanup. Its own asynchronous setup operation
verifies the exact source principal before publishing custody and resuming onboarding. A new opted
profile starts with empty public inventory; prior captured keys/children are never adopted/backfilled.
Setup publication checks credential ID, creating operation, exact target, expected next generation,
and original `material_created_at <= uploaded_at <= now < retire_at`.

One managed head owns the setup or scheduled successor operation. Successful preparation/rotation
pre-creates the next immutable rotation intent and native ETA at day 29. Its FK is scheduling
ownership, not an active pause. The bounded `queue-signing-rotations` rescue selects at most 100
usable heads joined to `waiting/signing_rotation_due` operations due within one day of retirement,
ordered by `(retire_at,id)`, and requeues the same operations transactionally. No hourly OKE CronJob
is deployed. See the execution chapter for complete query, lock and drain accounting.

Rotation first blocks new child provider admissions/windows, drains accepted work and active recovery
windows, then reserves the child. Short administrator/workspace/operation/child/head transactions
end before provider/custody I/O. Every phase authenticates current source evidence, principal/domain,
connection, policy, operation and attempt. Candidate stage/upload/reconcile/probe/activation/retirement
checkpoints use existing operation-step and immutable audit records. Upload dispatch is durable before
the call; absence after an uncertain upload does not authorize a resend. Activation preserves the old
original deadline until exact old ID/fingerprint absence and continuing replacement proof.

A completed nonterminal phase commits `queued` plus its next native job; priority 100 password jobs
can run between phases. Initial future admission alone sets `scheduled_rotation=True` (priority -1);
immediate/manual/resume/phase/drain jobs use priority 0. This avoids an earlier scheduled job on the
same operation lock blocking a manual run, without adding a queue or changing lock identity. Automatic delivery cannot take over `running` or resume `needs_attention`.
Guarded Resume is explicit. A hard-crashed running operation requires owned paused-worker/manual
recovery, not timed takeover or simply clearing its state. Cached views and other children continue.

## Physical field dictionary

Migration 0028 adds **one** `otm_signing_credential` table, with 17 columns; it extends existing
operation/audit/step constraint branches. Installed totals are 29 OTM tables / 33 public tables including runner tables. The checkpoint
preserved all 32 preexisting public tables and added only this managed signing head.
No signing-version, attempt, schedule or notification table is added.

| Column | Meaning and constraint |
| --- | --- |
| `id` | Stable managed credential UUID, primary key |
| `workspace_id` | Workspace scope in composite unique/FK identities |
| `tenancy_id` | Exact registered child; partial unique active head per workspace/child |
| `principal_binding_id` | Exact canonical automation user binding; unique per workspace |
| `connection_id` | Existing immutable active presence connection for this child |
| `source_operation_id` | Fresh owned create/import onboarding operation |
| `source_evidence_event_id` | Exact onboarding outcome; composite workspace/operation/event FK |
| `target` | Closed `RequiredUserTarget` JSON, never a name-based lookup |
| `target_hash` | Canonical metadata hash verified before use |
| `current_key` | Nullable typed `ManagedSigningKey` JSON; null during generation-zero preparation |
| `current_hash` | Canonical current-key hash, null iff no current key |
| `generation` | Zero for staging, then positive current managed generation; unchanged or +1 on SQL update |
| `state` | `staging`, `usable`, `rotating`, `attention`, `retired` |
| `retire_at` | Original earliest unresolved retirement deadline; null only before initial publication |
| `rotation_operation_id` | Required scoped setup/current/scheduled operation FK, deferrable during atomic admission |
| `created_at` | Immutable initial allocation timestamp |
| `updated_at` | Monotone head transition timestamp; also invalidates older cached public inventory |

Insertion is limited by fresh simulated create/import, selected rotation contract and exact source
bindings. Trigger guards protect anchors, prohibit deletion/truncation and prohibit updates to retired
heads. Scoped FKs join the existing tenancy, managed binding, presence connection, operations and
audit evidence. Typed service validation additionally authenticates JSON/hash/clock/intent coherence;
SQL JSON shape checks alone are not provider authority. Partial index `ix_signing_credential_due`
uses `(workspace_id,retire_at,id) WHERE state='usable'`.

## JSON, request and derived-view field dictionary

These are typed existing-column payloads or transient projections, **not new SQL columns**.

| Contract | Named fields and persistence |
| --- | --- |
| `RequiredUserTarget` | `workspace_id`, `tenancy_id`, `purpose=automation`, `subject_binding_id`, `binding_generation`, `identity_domain_binding_id`, `domain_ocid`, `scim_resource_id`, `provider_ocid`, `user_name`, `organization_id`, `parent_tenancy_ocid`, `tenancy_ocid`; stored in head and frozen intent |
| `SigningKeyVersion` | `credential_id`, `created_operation_id`, `generation`, `target`, `secret_reference`, `secret_version`, `fingerprint`, `material_created_at`; nonsecret exact-version metadata in head/step/audit, not normal public API |
| `ManagedSigningKey` | `version`, `provider_key_id`, `uploaded_at`; retirement derives from the earlier material/upload timestamp +30 days, never a refreshed read/activation clock |
| `SigningKeyIntent` | `contract_version`, `kind`, `phase`, `workspace_id`, `credential_id`, `subject`, `connection_id`, `connection_revision`, `policy_hash`, `expected_generation`, `source_operation_id`, `source_evidence_event_id`, `target`, optional `old`/`due_at`; existing immutable `operation_intent` audit JSON |
| `SigningRotationState` | `old`, `phase`, `candidate`, `uploaded`, `upload_dispatched`, `retire_dispatched`; existing sealed step outcome/audit preserves candidate and old history through pointer changes |
| `SigningKeyEvidence` | `contract_version`, `operation_id`, `credential_id`, `tenancy_id`, `phase`, `state`, `safe_code`, optional `checkpoint`/`current`, `checked_at`; `signing_key_outcome` audit and authenticated step outcome |
| `SigningKeyRequest` | `client_request_key`, `preview_hash`, `acknowledged`, `action=rotate/resume`; transient command, with actor-derived authorization |
| `SigningKeyRequestEvidence` | `contract_version`, `operation_id`, `tenancy_id`, `client_request_key`, `request_digest`, `action`, `acknowledged`, `safe_code`; `signing_key_requested` audit, unique workspace/actor/request key |
| `SigningKeyView` | `tenancy_id`, `tenancy_name`, `provider_mode=simulated`, `state`, `generation`, `available`, `preview_hash`, `operation_id`, `starts_at`, `retire_at`, `safe_code`, `last_rotation_operation_id`, `last_rotated_at`; derived metadata GET, no custody/provider read |

Public states are `not_prepared`, `preparing`, `scheduled`, `rotating`, `attention`, `overdue`,
`inactive`, `unavailable`. Availability also depends on active child/approved parent/current trusted
policy and supported operation state. Preview hashes bind actor, child revision, credential generation,
head state/current hash and operation ID/revision. Current and historical private version locators
never appear in this public view. Current inventory is marked stale when the active head's
`updated_at` is newer than its sealed check; changing custody never invents a new provider observation.
Historical inventory retains its original captured age/provenance. A rotating head that reaches
its original deadline displays `overdue`, including while accepted recovery access is draining.

## Failure email and permission boundary

Written WIP `stage_failure` adds one existing outbox intent per original operation/active administrator,
with transition hash over operation ID, administrator ID and `signing_key_attention`. Repeated holds
of that operation do not repeat notices or silently change recipients. Delivery rechecks the active
administrator authorization revision/email, exact head/current operation/generation/deadline, current
unresolved attention state or exact-operation queued/running/waiting resume/drain state, child status and frozen
route/application/transport. Predeadline queued/running/waiting resume and generation+1 activation do not discard a notice while that same
operation and original retirement obligation remain unresolved. Obsolete context supersedes a
known unsent notice; blocked routing remains visible. There is no new notification table. The drain worker also stages this same deduplicated incident at/after the original deadline.
This does **not** establish a separate overdue scheduler or qualified live mail-service behavior. Local SMTP coverage is recorded in the targeted checkpoint.

`SigningKeyFailureNotice` fields in existing outbox `intent` JSON are `contract_version`,
`operation_id`, `tenancy_id`, `credential_id`, `generation`, `administrator_id`,
`authorization_revision`, `original_recipient`, `delivery_recipient`, `route`, `application_origin`,
`delivery_profile_hash`, `event=signing_key_attention`, nullable `retire_at`, `created_at`.
Existing outbox status, attempts, transition key and audit evidence retain delivery history.

Local role setup grants both API and worker SELECT. The API gets only head UPDATE of `state` and
`updated_at`; the trusted worker gets INSERT plus UPDATE of `current_key`, `current_hash`,
`generation`, `state`, `retire_at`, `rotation_operation_id`, `updated_at`. Neither gets head DELETE,
anchor UPDATE or implicit owner fallback. These are SQL table/column grants plus typed application/
trigger guards, not SQL row-kind permission filters. Targeted installed-role checks pass; hosted-role qualification remains Pending.

## Confirmed termination

The worker defers a child still `terminating`, preserving the signer while its outcome is uncertain.
The existing lifecycle retirement hook tombstones a head only for the scoped `terminated` child and
cancels its waiting/queued/attention future key operation. Custody and immutable history remain;
pending/failed termination is not confirmation. No OCI final-termination monitoring is added.

## Remaining boundaries

No actual keypair, OCI upload/delete/signing, Vault integration, current dynamic privilege-loss proof,
OKE schedule or live restore drill is qualified. The simulator currently derives capability flags from
retained onboarding grants/static root fixture, so dynamic current-grant/configuration failure cases
remain work. Password CURRENT selection and original four-hour rotation remain separate; API keys
always require exact immutable version references. The checkpoint receipt records targeted unit/integration/review/preserved-publication results;
no complete-suite/PR/live qualification is claimed here.

## Current key versus future operation — source follow-up

Combined clarity targeted gates, final UX and preserved saved republication PASS; earlier targeted
feature evidence remains separate. The tenancy panel now says **Current key: generation N** alongside **Next rotation scheduled**.
The generation describes the active key, not a generation waiting to be created. Labels are Next
automatic rotation (UTC) and Last completed rotation (UTC). Rotate key opens an unchecked confirmation;
Rotate now starts the SAME scheduled operation early. Resume and lost-response retry describe their
original unresolved operation/request, not a new keypair. Completion alone creates a new successor.

Operations uses optional `OperationSummary.scheduled_for` from frozen intent `due_at` only while
`waiting/signing_rotation_due`; Accepted remains admission time. The date is earliest execution
eligibility, may be delayed by prior work/recovery access and is omitted for expedite/running/drain/
terminal states. A future waiting operation does not pause provider work. This is derived read-only
metadata; no SQL column, migration, setting or custody/provider behavior changes.

### Fixed signing event descriptions — source follow-up

The installed combined clarity patch adds optional omitted-null `OperationEventView.summary` from
validated immutable `SigningKeyEvidence`, using shared `signing_event_summary` in Operations/Audit.
Labels distinguish staged, upload authorized/verification pending, public key observed, signer verified,
activated/old retirement pending, removal authorized/verification pending, old absent/access verified,
completed and attention. A dispatch fence never implies provider success. Existing records gain
friendly display labels on refresh without history rewrite; no SQL field/migration is added. The UI
uses this heading and suppresses only redundant `SIGNING_KEY_PROGRESS`, preserving failure/final codes.
Combined clarity targeted gates, final history-visual UX and preserved saved republication PASS; earlier two-case schedule
receipts remain separate and do not qualify these later labels.
