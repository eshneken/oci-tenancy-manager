# Guided onboarding responsibility takeover

4 November 2026 · Qualified application capability; both saved instances upgraded to 0019

[Accepted onboarding journey](../engineering-design/07-onboarding-journeys.md) ·
[D50 responsibility contract](../engineering-design/15-collection-and-operational-events.md#d50-accepted-responsible-administrator-only) ·
[Operations](operations.md) · [Onboarding](tenancy-onboarding.md) ·
[Existing workflow ER](../architecture/diagrams/organization-workflows-implemented.mmd) ·
[Manual review](../how-to/responsibility-runbook.md)

## Scope

An already entitled administrator can explicitly take responsibility for an existing waiting or
needs_attention guided create/import operation. This is a permanent application workflow, not a
temporary simulator control. The change records real database responsibility and immutable audit;
provider execution remains the current local simulation. No OCI tenancy access, credentials or new
permission-handoff flow is introduced.

The claimant takes responsibility for themself; there is no other-admin picker, Reason field,
automatic assignment on view or grant-creation shortcut. Only organization_action create_tenancy /
import_tenancy with accepted onboarding_version 1 or 2 is eligible. Queued, running, terminal,
inspection, configuration-check/update, member/offboarding and absent-version legacy operations
are excluded. Already being responsible is not a new claim. In the current saved main installation there is
only one local administrator; when that administrator already owns the work, Take responsibility
is correctly hidden. No temporary second-admin control is added. Positive multi-admin cases use
prepared disposable authorized test sessions, not fabricated saved accounts.

Creator, initiating actor snapshot, original activation mailbox/MFA custody, provider intent/hash/
revision, tenancy owner, baseline pin, handoff target and verified steps remain unchanged. The
existing responsible_actor_subject, operation revision and updated_at change together with one
immutable claim event. Takeover does not enqueue work, finish a provider step, activate ownership,
change a password or grant access to another person's mailbox. External activation recovery stays
manual when the original account is unavailable.

## Screen and request flow

Guided operation detail shows Administrator responsibility with separate Initiated by and
Responsible administrator labels. The create/import setup subtitle also explicitly says Initiated by:
its OnboardingView.administrator_name is the immutable creator, not the current responsible admin.
The activation contact remains original as well. An eligible different administrator can choose
Take responsibility.
The native confirmation dialog captures the displayed operation revision and current administrator
name; background polling cannot silently replace that reviewed revision. Cancel/Escape makes no
change. Confirmation changes only workload responsibility, with a recorded notice and fresh
operation/onboarding reads afterward.

If another claim or state transition wins, the stale command returns conflict; close, refresh and
review again. An unknown response can retry the same mounted request identity. Closing/reopening
starts a new reviewed attempt; there is no promise of reload-durable browser request memory. Merely
opening/refetching the operation never claims it. Only the currently responsible administrator can
submit handoff/start-setup actions, even if another active administrator can inspect the record.

POST /api/operations/{operation_uuid}/responsibility accepts at most 4,096 bytes of closed JSON
ResponsibilityCommand under the existing current-session, entitlement, HTTPS/Host, Origin and
custom-header guards. It returns HTTP 200 ActionReceipt with the operation's current state,
simulated provider mode and acceptance time; a claim is not a queued provider action. The browser
supplies neither actor/workspace nor an arbitrary assignee. Missing/foreign operation IDs stay
scoped. The server repeats state, revision, current authority and provider-policy/pause checks; an
enabled affordance is not permission to bypass fresh admission.

## Concurrency and replay

The existing protected-administrator/session/workspace/operation lock ordering serializes claims
with authority changes and workflow transitions. expected_revision must equal the locked current
operation revision; successful claims increment it exactly once. Competing commands with the same
reviewed revision cannot silently overwrite each other. The responsible subject, revision/time and
audit event commit together; an audit failure rolls back the change.

Replay is scoped to workspace, operation, verified claimant and request UUID. An exact committed
retry returns the original acceptance time with the operation's current state before stale-state/
revision eligibility checks. It creates no second event, revision or job and does not reclaim work
if another administrator has since taken it. A changed body under the same key conflicts. Replay
still requires a current authorized session; historical evidence is not login permission.

## Continuation after creator departure

The worker always validates the original stored intent bytes/hash and original creator binding.
Without a takeover proof, original frozen administrator/grant-revision checks remain. A guided
operation with a claim additionally resolves its latest valid immutable responsibility event by
numeric operation_revision, never a tied wall-clock timestamp. That event must match the current
responsible subject, exact intent-event pointer and canonical typed original intent envelope hash,
and cannot claim a future operation revision.

The event captures the replacement administrator UUID, issuer-qualified actor and authorization
revision. Dispatch rechecks that exact live grant, active status/revision and actor pairing. Thus
a departed/revoked creator need not block an explicitly authorized replacement, while revoking or
revoking/regranting the replacement cannot silently revive stale captured execution authority.
A later explicit eligible claim is needed for a new authority snapshot. Existing policy/parent,
source-person, baseline, target, effect and cleanup guards still apply. No provider intent rewrite
or general execute-as-any-active-admin fallback is used.

The proof's intent_hash is the canonical typed original IntentEventData envelope, including the
original actor; it is distinct from the original stored event's raw data_hash. Both checks have
their own purpose. Stored provider intent/history is not normalized or overwritten by a claim.

## Complete field and storage map

| Contract/field | Meaning and source |
| --- | --- |
| ResponsibilityCommand.client_request_key | UUID for this explicit claimant's request on this operation. |
| ResponsibilityCommand.expected_revision | Positive reviewed operation revision; caller cannot select another actor. |
| ResponsibilityEvidence.contract_version | Fixed operation-responsibility-1. |
| ResponsibilityEvidence.client_request_key | Original request UUID in immutable claim audit. |
| ResponsibilityEvidence.request_hash | Canonical SHA-256 of the closed two-field command. |
| ResponsibilityEvidence.before_name | Nullable prior authority actor display-name snapshot; never reconstructed as historical truth from a future mutable label. |
| ResponsibilityEvidence.before_subject | Previous issuer-qualified actor key from the locked responsible head. |
| ResponsibilityEvidence.after_actor | Three-field ActorIdentity: issuer, subject, optional display_name; key is derived from issuer/subject. |
| ResponsibilityEvidence.administrator_id | Current same-workspace claimant grant UUID, obtained server-side. |
| ResponsibilityEvidence.authorization_revision | Exact captured grant revision rechecked at execution. |
| ResponsibilityEvidence.intent_event_id | Original current intent-event pointer; not a new/amended provider intent. |
| ResponsibilityEvidence.intent_hash | Hash of canonical typed original IntentEventData envelope; raw stored event hash is independently verified. |
| ResponsibilityEvidence.expected_revision | Previous operation revision reviewed by the claimant. |
| ResponsibilityEvidence.operation_revision | expected_revision + 1 exactly; orders claim history and cannot exceed current revision at authority resolution. |
| OperationSummary.responsible_administrator_name | Nullable computed current grant display name, with recorded authority actor fallback; separate from initiated_by. |
| OperationSummary.responsible_administrator_id | Nullable computed grant UUID resolved through original/claim authority for guided detail. |
| OperationSummary.responsibility_revision | Nullable computed current operation.revision used for confirmation fencing. |
| OperationSummary.can_take_responsibility | Default false; guided detail enables only an eligible different viewer. Server admission still repeats all current guards. |

ResponsibilityCommand has 2 fields; ResponsibilityEvidence has 12, including nested after_actor.
OperationSummary now has 18 fields; the four additions are computed on guided operation detail,
with null/false compatibility defaults elsewhere. None is a new SQL column.

Existing physical storage is reused:

- otm_operation.responsible_actor_subject, revision and updated_at hold the changed head/time.
  initiating_actor_subject/snapshot, current_intent_event_id/revision and lifecycle/provider state
  remain unchanged by the claim.
- audit_event appends operation_responsibility_changed for the same workspace/operation, with
  claimant actor/subject/snapshot, contract version, timestamp, closed data and data_hash. The top-
  level administrator_id/intent_revision remain null; claimant grant identity is in typed data.
- Existing administrator data supplies current entitlement; no new grant is created. No native
  job, operation step, owner/membership/configuration row or separate responsibility table is added.

Forward migration 0019_operation_responsibility only extends the closed audit-kind constraint.
There are still 19 application tables and 20 baseline columns; no column, backfill or new intent
revision is introduced. Audit History and operation events expose the responsibility change with
readable before/after administrator labels. Audit is not editable and a claim is not a provider
success or ownership transfer.

## Qualification and remaining boundaries

All final source-unit/PostgreSQL/native-worker/browser gates, independent reviews and both
saved-instance preservation checks pass. The user agreed to continue useful
OCI-independent application work without access to a parent tenancy; this accepted D50 capability
is the selected slice. No temporary simulation-control UI or operator observation-editing helper is
added. Full OCI activation/identity/Vault qualification and lifecycle email delivery are separate.
D50 responsible-admin-only routing remains the future notification contract; this claim does not
send an email or change other notice recipient rules. Later work such as notifications/packaging
requires its own next-step selection; it is not started by this checkpoint.


### Final qualification and preserved-data installation — 4 November 2026

All 1,330 combined backend/PostgreSQL/native-worker/HTTPS-browser cases pass with no failures,
errors or skips, in disposable synthetic databases. The 1,077 backend unit tests cover 7,062 of
7,362 executable lines (95.925%) across all 100 runtime modules. The 338 frontend unit tests cover
1,600 of 1,642 lines (97.4421%) across 29 files. Unit-only coverage is measured separately from
transaction/browser proof. The final focused actual native-browser case also passes after rebuilding
the corrected Initiated by subtitle; create/import component checks preserve the original contact.
Final independent UI review approves all six synthetic screen captures.

All 64 generated schemas, 260 Python purpose-comment files, Ruff/format and document links pass.
Fresh audits report zero known vulnerabilities across 75 locked Python packages with zero skips,
zero npm vulnerabilities, and zero Bandit/scoped Gitleaks findings. Independent security, migration/
installer, documentation and final actual-screen UI reviews pass.

Both saved instances are upgraded from 0018_configuration_drift to 0019_operation_responsibility
with private 0600 backups. Every old column/row across all 19 existing application tables retains
identical fingerprints; there are still 19 tables, no new table/column and 20 baseline columns.
Baselines, accepted pins, overrides, administrator accounts and history are preserved. Both API/
worker pairs serve matching private qualified frontend snapshots. Liveness and Operations HTML
return HTTP 200; unauthenticated takeover POST returns HTTP 401. No saved-data reset, backfill,
extra saved administrator, real OCI call or Git publication occurred.

The current main installation has one local administrator, so already-responsible work correctly
hides Take responsibility. Review the positive multi-admin capability through its disposable
qualification rather than expecting a second-account simulator control. This completes the selected
OCI-independent application feature; notification transport, corporate identity issuance and live
OCI qualification remain future work requiring their own review. No next workstream is started.


Final application qualification and saved-instance receipt (private historical evidence; not distributed).
