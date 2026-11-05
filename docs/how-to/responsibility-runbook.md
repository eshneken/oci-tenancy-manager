# Manual review: administrator responsibility takeover

4 November 2026 · Qualified application capability and installed saved instances

[Runtime field and authority guide](../reference/responsibility.md) ·
[Guided onboarding](../reference/tenancy-onboarding.md)

## Review prerequisites

Use the prepared disposable synthetic PostgreSQL/browser fixture with at least two independently
authorized administrator sessions and a waiting guided create/import operation. The ordinary saved
main installation currently has only its protected local administrator: this feature does not create
another account, enable corporate SSO or justify editing grants to make a demo. Without another
already entitled principal, inspect the eligibility boundary and rely on the separate positive
fixture qualification. When that administrator is already responsible, the Take responsibility
button is correctly hidden; no temporary second-admin controls are present. Never share sign-in
factors or manually edit saved operation/audit rows.

No OCI tenancy is required for the application's responsibility change. Provider setup remains
local simulation; takeover cannot recover an unavailable original mailbox/MFA session. Preserve
saved main/lab data and stable frontend snapshots. No reset, temporary simulation UI, helper
command, cloud action or repository publication is authorized by this runbook.

## 1. Explicit claim and unchanged history

Open a synthetic guided operation as a different entitled administrator. The detail panel must show
Initiated by and Responsible administrator separately. Opening/refreshing it changes neither.
Take responsibility opens a confirmation naming the current responsible administrator, with no
Reason or other-assignee control. Cancel/Escape leaves state unchanged and returns usable focus.

Confirm. The notice says responsibility was recorded; it must not say a provider operation was
queued/completed. The operation remains waiting/needs_attention. Responsibility and revision/time
change with one immutable audit event and no queue job. Creator, activation contact, owner, original
provider intent/hash/revision, baseline pin, handoff IDs and verified steps remain unchanged. Audit
History and operation events show a readable previous → replacement administrator change.

## 2. Continue as the current responsible administrator

Reload the guided panel under both sessions. In both create and import, the setup subtitle must
still say Initiated by with the original creator; the separate responsibility panel names the
replacement. The activation contact stays original. Only the replacement can verify handoff/start setup;
the prior administrator may inspect but cannot submit stale setup commands. Use the fixture to
revoke the original creator, then let the replacement submit the appropriate next action. Dispatch
must use the captured replacement authority and current grant, with all original target/policy/
baseline guards retained. It must not rewrite provider intent to replace the creator.

Revoking or revoking/regranting the replacement before dispatch must block the captured authority.
This is an automated disposable-fixture case, not an instruction to revoke the protected saved
local administrator. External OCI activation remains bound to its original mailbox/MFA context.

## 3. Conflicts, uncertainty and cycles

Use separate test browser contexts to review the same operation revision, then claim it from two
different entitled administrators. Exactly one wins; the other gets a conflict and must refresh.
Polling must not silently replace the revision captured by an already-open confirmation.

An unchanged uncertain-response retry uses the same mounted request key and yields no second
claim event/revision/job. A changed body under that key conflicts. After another administrator
claims the operation, replaying the earlier request must not reclaim it. A fresh self-claim by the
current responsible administrator is ineligible; viewing never performs an implicit no-op claim.
Repeated legitimate takeovers use numeric operation revision ordering, not timestamp ordering.

Close/refresh after a stale conflict. A full browser reload does not promise to remember an
unconfirmed request key; inspect the recorded current responsibility before different work.

## 4. Negative and transaction matrix

The disposable test suite separately covers expired/revoked/wrong-workspace/foreign operations,
queued/running/terminal states, absent-version legacy work, non-create/import operations, paused/
changed policy, invalid body/oversize fields, malformed or mismatched authority proof, future proof
revision and original intent tampering. No denied path may change responsibility, audit or queue.

Actual PostgreSQL checks prove competing claims and audit-failure rollback. Unit fakes cover
business branches but are not evidence of database atomicity. Actual HTTPS/browser checks cover
keyboard confirmation/cancel/focus, separate labels, fresh panel after claim, conflict feedback and
responsive layouts. All source-unit gates, real transaction/native-worker/browser results, independent reviews and
both saved-instance preservation checks now pass. The positive multi-admin browser case uses
actual authenticated API/native-worker behavior in disposable synthetic fixtures, not a mocked
response or a new identity on the saved installation.

This implements application workload responsibility only. It does not transfer tenancy ownership,
permissions, credentials, activation access or notification delivery. Notifications/packaging and
real OCI qualification are separate future choices; no later slice is started here.


Final application qualification and saved-instance receipt (private historical evidence; not distributed).
