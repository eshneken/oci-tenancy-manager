# 23: managed automation signing-key rotation execution plan

10 November 2026 · Implemented candidate accounting; targeted local qualification and saved installation PASS

**Availability correction:** targeted source/unit/PG/native-browser checks PASS; saved republication
PASS for recovery-window waiting. Prior passing receipts retain their original scope.

[Binding 30-day policy](22-credential-security-lifecycles.md#thirty-day-otm-api-key-policy) ·
[Current read-only inventory](../reference/automation-signing-keys.md) ·
[WIP source fields and ER](../reference/signing-key-rotation.md) ·
[Existing executor](02-operations-and-provider.md) · [Manual restore](17-recovery-and-release.md)

## Accepted scope and explicit limits

The user approved a brief **per-tenancy provider-work pause** for replacement, after existing
recovery access closes; ordinary reads continue during that earlier wait. Cached views and other
children remain available. The intended implementation applies the existing 30-day maximum through exact managed
credentials and the existing native executor, not a new daemon or identity model. Candidate source
and migration 0028 now exist; targeted checks and preserved installation in sole saved main 8443 have passed.
The [checkpoint receipt](../history/signing-key-rotation-checkpoint-2026-11-10.md) records exact scope;
complete-integration/PR/live qualification remains Pending. The
previous observation-only inventory checkpoint does not establish this new rotation capability.

Sections marked **current WIP** describe written source and remaining integration scope; the
targeted checkpoint is qualified locally, not a complete-integration/PR/live qualification.
The durable phase and failure requirements remain normative acceptance criteria. Current custody
and provider composition is an explicit simulator with deliberately nonusable material markers:
no real RSA generation, PEM signing, Vault SDK or OCI mutation is established. Real exact-version
signer composition and dynamic current-grant probes remain unfinished. Failure-email staging is
now written through the existing outbox but covered by targeted local tests; drain-at-deadline notices are written in the same source subset. No separate overdue scheduler is installed.

Automation signing keys use exact immutable private-version references; **never Vault CURRENT or
LATEST**, and never recovery-password custody tables. Existing immutable presence-connection guards
remain intact. Recovery is not an alternate machine signer. Private/public PEM material stays within
explicit custody/provider boundaries, not SQL, audit, job arguments, API metadata or notifications.
The new version clocks never restart at activation, retry, observation, app restart or old-key cleanup.

## Current WIP: one head; immutable history stays in existing records

Candidate migration 0028 adds one `otm_signing_credential` table (Python `signing_credential`),
with scoped references to existing workspace/child, canonical automation binding, immutable presence
connection and enrollment operation. The preserved saved installation has 33 public tables (29 OTM), after retaining all 32 prior
public tables and adding only this head. The written field responsibilities are:

| Head value | Responsibility |
| --- | --- |
| ID and exact scoped child/principal/connection FKs | One eligible managed head for that exact child automation identity; cannot mix another child/domain/user/connection |
| `current_key`, canonical hash | Typed `ManagedSigningKey`: exact credential/generation/target, nonsecret secret locator and immutable version, fingerprint, material creation, provider key ID and upload evidence |
| `generation`, bounded state | CAS admission/publication and usable versus rotating/attention/retired; detailed phase/effect belongs to the existing operation/steps |
| `retire_at` | Earliest original unresolved retirement deadline; retain old deadline during retirement even after the new current key publishes |
| `rotation_operation_id` | Single setup or pre-created scheduled successor operation; its presence alone does not pause provider work. During rotation it remains attached through verified old-key absence |
| Created/updated and enrollment provenance | Explicit owned setup and lifecycle history, never enrollment inferred from an inventory row |

The head contains **nonsecret current version locators** because its typed current key requires
them. Exact staged candidates and old historical references remain in existing immutable operation/
step/audit evidence; no separate signing-key-version table is added. Hashes check typed metadata
integrity; they neither contain PEM nor confer provider authority.

The current key’s next deadline derives from its own original material/upload times. During retiring,
`retire_at` preserves the old obligation frozen in the rotation intent; after verified completion it
advances to the replacement’s independently derived deadline. No creation timestamp is rewritten.
Enforce scoped uniqueness, positive generations, exact typed/hash checks and legal state/operation
combinations. Candidate SQL constraints/permissions must be tested against the reviewed typed service contract.

## Fresh explicit enrollment only

A new immutable onboarding opt-in adds `prepare_automation_signer` **after canonical identity capture**
and before recovery-password preparation/temporary cleanup. It admits a reference-only native setup
continuation in the same transaction as its accepted intent. Simulated initial custody/upload/probe
evidence must independently verify the exact permanent automation signer before the head is usable
and the parent resumes. Failure leaves setup waiting/attention; no temporary last-admin cleanup.

Earlier inventory-only configure/capture may contain synthetic rows without private custody. Those
rows are discovery facts, never proof of a managed signer. The new explicit profile must produce
coherent owned material/upload evidence and account for existing slots; no name/fingerprint match
silently upgrades an old row. Existing accepted profiles, inventory-only children and legacy accounts
are not backfilled or adopted. Actual OCI enrollment remains separately qualified.

## Current WIP: schedule, query and deduplication

Day 29 preparation/day 30 retirement are elapsed-time policies, not calendar-month reset rules.
The primary written schedule is a **pre-created successor operation and reference-only native job**.
Successful initial enrollment, and each fully verified rotation, transactionally create the next
operation with immutable old key/generation and `due_at = retire_at - 1 day`, update the head's
operation pointer and enqueue that operation for its future ETA. A scheduled successor is not an
active provider pause: its head remains `usable` while waiting for existing recovery access, even after an administrator
expedites the same operation. The short provider pause begins only after that window closes. Browser polling does not create jobs.

The CLI `queue-signing-rotations` supplies a bounded rescue of already scheduled due work:

- Select the chosen workspace's `usable` heads joined to their existing operation where state is
  `waiting`, wait reason is `signing_rotation_due`, and `retire_at <= now + 1 day`.
- Order by `(retire_at, id)`, limit to 100 (or a validated smaller limit), and lock selected rows with
  `SKIP LOCKED` within the short transaction. Index `ix_signing_credential_due` covers
  `(workspace_id, retire_at, id)` for usable heads.
- Change each selected operation to `queued` and enqueue its SAME UUID transactionally. The changed
  state removes it from the next rescue batch; this is bounded state-changing selection, **not**
  keyset pagination or allocation of a new business operation. Additional batches must be invoked
  explicitly; there is no hidden unbounded loop or permanent scan cursor.

This rescue query does not independently establish current parent/organization/binding eligibility.
The worker rechecks the frozen target, current child lifecycle/parent, active canonical user/domain,
immutable connection, trusted policy and owning head before provider work. Parent/arbitrary/legacy
identities cannot enroll through this schedule. Attention, retiring and unverified heads require their
own original operation/recovery, not a newly allocated rotation. An hourly OKE maintenance fan-out
using this capability remains a future deployment step; no CronJob is installed by this checkpoint.

One head and its operation pointer own generation deduplication. Manual Rotate expedites the existing
successor; Resume explicitly requeues an eligible attention operation. Preview binds actor, child,
head generation/hash/state and operation revision. Audited request keys return the original receipt
on exact replay, including after completion; an obsolete preview cannot rotate a later generation.
Neither rescue, restart nor repeated requests create another pair or reset original clocks.

## Current WIP: lock and asynchronous-worker accounting

The worker uses short **administrator → workspace → operation → child → signing-head** row locks.
It authenticates immutable intent/evidence hashes, exact original onboarding source proof and current
principal/connection/policy scope under those locks, then commits
before any custody/provider I/O. Callback transactions reacquire the same scope and current attempt;
stale callbacks cannot publish a new key or release the pause. No transaction is held while waiting
for a password deadline, provider response or the next rotation phase. Existing serialized workspace
admission and the partial unique active-head index prevent competing managed heads.

`begin` accepts only `queued` or the recognized `waiting` reasons `signing_rotation_due` and
`signing_drain` or `signing_recovery`; a future due wait does not execute early. It refuses `running`, `needs_attention`,
terminal states and other wait reasons. Native redelivery therefore neither steals in-flight I/O nor
silently resumes a human-held operation. Each successful nonterminal phase commits its checkpoint,
changes the operation back to `queued` and enqueues the same UUID together. This deliberate yield
lets higher-priority recovery-password closure jobs run between phases on the shared native worker;
password jobs have priority 100. Only the initial future successor enqueue uses
`scheduled_rotation=True` and priority -1; immediate/manual/resume/drain/phase jobs use priority 0.
This keeps an earlier future job on the same operation lock from blocking an immediate manual run.
The sole queue and same-operation lock are retained; there is no second scheduler or retry daemon.

A hard process death can leave an operation `running`. There is **no timed takeover or automatic
lease expiry** in this slice. An operator must stop/verify ownership of the old worker, use the
existing paused-worker/manual-recovery procedure, inspect the persisted phase and actual candidate
inventory, and explicitly admit safe continuation of that original operation. Do not merely reset
`running` to `queued` while the original worker or an uncertain provider effect may still exist.
Normal attention uses the explicit guarded Resume path; it never clears the upload-dispatch fence.

## Current WIP: logical pause, drain and child reservation

An eligible start/manual expedite first checks existing recovery access. An open recovery-password
window records `waiting/signing_recovery` with a usable key head and no child reservation; ordinary
provider reads remain available before the hard retirement deadline. Block NEW recovery windows
while rotation is requested/due. Same-window redisclosures preserve the original first-attempt/due
time and cannot postpone closure. Cached views and other children remain available.

After the window closes, mark the head `rotating` to prevent new provider admissions, drain existing
child ownership and short `reading` cost/presence/configuration work, then reserve
`tenancy.operation_id`. Short I/O drain uses `waiting/signing_drain`; both waits requeue after
15 seconds without holding a transaction. A wait is not an exemption from the original retirement
deadline: ordinary dispatch through expired material still blocks, with scoped password closure/
reconciliation preserving their separate required safety rules.

The worker can normalize an OLD untouched rotating `waiting/signing_drain` head only when its
original key/current context match, there is no logical step and no child reservation. It then waits
under `signing_recovery`. This excludes queued resume, attention/running and effectful work; it is
not timed takeover, a live SQL repair or a general pause-release action. Targeted qualification for this approved availability correction PASS; saved republication PASS; prior receipts are not rewritten.

Already dispatched calls cannot be recalled by a generation change. Drain/reconcile their original
attempts before retiring old material; do not reissue ambiguous destructive calls using a new key.
Recheck child lifecycle/parent, bindings, immutable connection, generation and pause ownership before
each dispatch/publication. Do not mutate immutable connection evidence merely to represent a new key.
The required live adapter must select the exact head version for each new attempt; cached SDK
clients must not keep using an obsolete key. That real private-signer composition is not implemented
by the current nonusable-marker simulation. Other children and their cached/provider work remain independent.

This brief-pause intent is not a promise that an uncertain failure has a bounded duration. Failure
keeps the affected provider boundary visibly paused/attention when safe release cannot be proven.
It must not silently strand password closure or pause the whole organization.

## Current WIP: termination boundary

A child in `terminating` causes a recognized drain wait/requeue, not premature signer retirement.
The existing `retire_terminated_credentials` lifecycle hook now tombstones the signing head only
for the scoped child whose termination initiation is confirmed (`status=terminated`). It cancels
that head's pending/waiting/attention future key operation and retains immutable custody/history.
Failed or merely pending termination must not remove a still-needed signer. This is source behavior
covered by targeted candidate checks, not a new independent termination monitor or 30-day finality wait.

## Required durable phases and effect knowledge

| Phase | Durable evidence before/after I/O and completion boundary |
| --- | --- |
| Admitted/recovery wait/short drain | Frozen original key/generation/deadline and operation FK; usable-head `signing_recovery` permits reads until recovery closure, then rotating-head short I/O drain precedes child reservation. New recovery windows cannot extend the wait. |
| Stage | Same stable operation UUID+old generation resolves the same recoverable candidate; persist exact nonsecret version/fingerprint/material clock before upload. Attempt IDs are not a new candidate identity. |
| Capacity/authority read | Independently complete exact-user inventory and qualified old authority; never delete the sole working or unowned key to make space. Full/unknown slots require attention. |
| Upload dispatch | Persist `upload_dispatched`/candidate/context and possible-effect state BEFORE provider upload; send public half only. A crash/lost response first reconciles that SAME fingerprint. |
| Reconcile upload | Complete found candidate must match exact resource/fingerprint/principal evidence. A still-absent candidate after uncertain dispatch is not proof of no effect/propagation: hold for qualified no-effect evidence and explicit supported resumption; no blind reupload/new pair. |
| New signer probe | Build an independent signer from the exact staged private version only. Fresh bounded proof covers OCI identity, identity-domain administration and root configuration; no old signer/client fallback. Persist source/version/context/probe evidence. |
| Activation CAS | Only after the fresh exact probe, atomically publish current candidate/generation and retiring phase. Keep active operation, old key reference and ORIGINAL old deadline; activation is not completed rotation. |
| Drain/retire | Use verified replacement authority. Delete only the frozen old provider ID when actual ID/fingerprint pair matches; never an unknown slot. Persist possible retirement effect before send. |
| Final verification | Independently complete inventory proves old ID AND fingerprint absent, candidate active/exact and replacement capabilities still qualified. Only then release the pause, complete this operation and replace its head pointer with the scheduled successor using the candidate’s original next deadline. |

All custody/upload/probe/delete/readback I/O occurs outside DB transactions. Existing operation/step
attempt IDs, immutable audit and exact version references provide recovery; no second journal, queue
or rotation engine is introduced. Local simulation cannot qualify real SDK permissions/slot capacity/
propagation, Vault staging or conditional deletion behavior.

## Failure, retry and rollback accounting

- **Before effects:** stale target/preview/authority, unsupported capacity or known no-effect failure
  blocks safely. An old signer may resume ordinary use only if independently verified and still
  within its original deadline, with no unresolved competing effect/cleanup obligation.
- **Stage reply lost:** resolve the same operation-owned candidate from custody. Never generate a
  different pair because a response/worker was lost; missing unreconstructable custody needs attention.
- **Upload uncertain:** preserve possible-effect evidence and reconcile same fingerprint first. No
  automatic write resend on complete absence unless qualified no-effect evidence permits it.
- **Probe fails:** do not activate or claim rotation. Retain old authority only while safe/within age;
  cleanup a known owned candidate only through its exact qualified plan, never an unknown key.
- **CAS loses:** retain candidate/old evidence and reread current scope. No stale head overwrite or
  secret pointer rollback; another generation does not authorize deletion of its key.
- **After activation:** retirement failure remains an open obligation. Do not revert to old credential
  merely because its private version is retained; pointer rollback cannot undo external effects.
- **Retire reply lost/crash:** read the frozen old ID/fingerprint under the exact replacement. Known
  absence can close only with continuing replacement proof; uncertain absence/permission stays held.
- **Lifecycle/restore changes:** no intentionally retired/deleted principal is resurrected. Follow D54
  paused manual restore and inspect actual inventory/custody/accepted attempts before resumption.

Known persisted provider results skip duplicate effects; automatic native redelivery is not automatic
permission to repeat a write. UI Retry/Resume is offered only for an explicitly safe supported state.
Rare unresolved edges use owned manual recovery, not a new coordinator or forced bypass.

## Overdue runtime guards, notices and visible status

At/after the original unresolved 30-day deadline, ordinary NEW provider use of overdue/unverified
material is blocked at dispatch, not only when the hourly scan notices it. Narrow audited rotation/
reconciliation and independent recovery must remain possible so guards do not prevent repair.
A recorded deadline cannot make an OCI key expire; show externally usable overdue keys honestly.

Written admission/dispatch guards block ordinary new work on rotating/attention/unusable heads and
ordinary dispatch at the unresolved retirement deadline; accepted work may drain before expiry.
These source guards have targeted local coverage; full milestone/live qualification remains Pending. Failure attention now stages existing outbox
notices, deduplicated by original operation and active administrator; delivery revalidates the exact
recipient grant, unresolved head/generation/deadline, child and frozen routing/transport. This source
has targeted local qualification; complete-suite/PR/live qualification remains Pending. If draining reaches the original retirement deadline, the worker stages
the same deduplicated operation/admin incident; the view reports overdue even while rotation drains.
An original pending notice remains eligible through predeadline queued/running/waiting resume
and generation+1 activation while that SAME operation and
original retirement obligation remain unresolved; completion/context change supersedes it. A separate
overdue scheduler is not established. See the
[field reference](../reference/signing-key-rotation.md#failure-email-and-permission-boundary) for
all notice fields and restricted SQL grants. Do not infer that alerts or enforcement
already exist from the read-only inventory badge. Preserve urgent password obligations, no fallback
signers, and the existing separation of lifecycle versus operational recipients.

Current targeted-qualified UI accounting (full-suite/live qualification separate): selected managed authority/fingerprint, original deadline, pending/draining/
paused/retiring/attention/completed operation, owned/unmanaged inventory distinctions and exact
Operations link. Cached views stay available and must explain pause/unknown status without green
compliance claims. No private PEM or secret locator belongs in ordinary public responses.

## Current simulator limits and required qualification

The simulator persists a stable operation-owned nonusable private/public marker, exact nonsecret
version metadata and independently stored public inventory. It cannot authenticate against OCI.
Its current three capability flags consult retained onboarding administrator evidence and a static
root-configuration fixture. They do not yet detect subsequent current grant/policy removal. Dynamic
independent grant/configuration fixtures and corresponding negative probes remain unfinished;
current success must not be described as live or dynamic privilege proof. Current public inventory becomes stale when the active head `updated_at` is newer than its
sealed observation; it does not manufacture a new check or alter historical capture time. Setup
publication now verifies exact version/creating operation/generation and original material/upload
times before publishing usable custody. Provider-upload age in the public inventory is distinct from managed retirement at the earlier material/upload timestamp.

## Required checkpoint and live evidence

Write tests with the slices: duplicate admission/scans, query/page bounds, deterministic ordering,
role permissions, exact context/version/probe, original deadlines, stage/upload crashes, absent-after-
unknown upload, candidate identity mismatch, full/unowned slots, CAS races, post-activation retirement
failure, old in-flight work, open password windows/due closure, lifecycle/restore and no unrelated-key
delete. Verify cached/other-child availability and absence of raw secret material.

Use the approved targeted local cadence for internal/UI slices, separate full-source unit-only 95%
gates and meaningful disposable DB/native/SMTP/browser cases. Complete integration is required at
full milestone/PR/merge gates; report targeted versus full evidence exactly. Native ETA/rescue is installed in the explicit local simulator; no hosted OKE schedule is qualified.
The checkpoint records preserved saved installation, not completed full milestone/PR qualification. Live enrollment, key IDs/timestamps, permission probes, signer
interoperability, capacity/propagation, custody and restore remain Pending in the
[manual manifest](../how-to/real-oci-test-manifest.md#credential-security-lifecycles).

## Schedule/current-key UI clarification — source follow-up

Combined clarity targeted gates, final UX and preserved saved republication PASS; prior feature
qualification remains a separate receipt scope. `OperationSummary.scheduled_for` derives from immutable rotation `due_at` only in
`waiting/signing_rotation_due`. The list/detail distinguish Accepted from Scheduled start (UTC);
the latter is earliest eligibility, not guaranteed execution, and future waiting does not pause work.
Expedited queued/running/drain/terminal operations omit it. No persistent field or migration is added.

The tenancy panel separates Current key: generation N from Next rotation scheduled, with Next
automatic rotation/Last completed rotation date labels. Rotate key opens confirmation and Rotate now
expedites the same operation. Resume/retry preserve the original unresolved operation/request. Only
verified completion allocates the successor; the active key generation is not a future key promise.

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

Current public state adds derived `waiting` (Waiting to rotate); the operation wait reason is `signing_recovery`, with no SQL migration. The [current field reference](../reference/signing-key-rotation.md#recovery-window-waiting) records the guarded normalization, targeted qualification and preserved saved republication PASS.
