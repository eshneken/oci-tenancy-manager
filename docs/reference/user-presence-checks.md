# Manual required-user presence checks

Local simulation qualified; main preview upgraded with existing data preserved; parallel test preview unchanged. [Final local receipt](../history/manual-presence-checkpoint-2026-11-06.md). Real OCI remains unqualified.

Tenancies → a registered child → **Required users** now supports **Refresh user data**. The worker reads
both exact bound subjects independently through an explicitly selected simulator. Present means
existence in that simulator's qualified fixture, not live OCI existence, usable signing credentials,
administrative privileges, console access, MFA or recovery readiness. The [assignment extension](administrator-assignments.md) now
checks both users’ exact group and domain-role assignments separately. The original presence-only checkpoint added no email. The
[new confirmed-Missing alert slice](required-user-alerts.md) adds scoped notices; daily scheduling,
repair and password actions remain deferred.

## Recovery-policy extension — 7 November 2026

[Recovery console checks](recovery-console-verification.md#current-ui-checkpoint) now accompany
manual refresh as independent controls. Presence semantics and Missing episodes remain unchanged.
New setup can retain private exact policy facts; refresh compares them with current desired policy
without treating desired settings as observed state. Separate MFA/network results, dated policy links
and inventory drift indicators do not certify credentials, privileges or live provider qualification.
The [qualified UI checkpoint receipt](../history/recovery-policy-ui-checkpoint-2026-11-07.md) now records
complete gates and main-only preservation. Daily CronJob installation and real provider qualification remain deferred.

## API, admission and replay

`GET /api/tenancies/{UUID}/required-users` remains a noncacheable read-only snapshot. It returns
stored identities, current check eligibility, pending progress and validated dated results; GET
never dispatches a provider read or creates missing historical bindings/connections.

`POST /api/tenancies/{UUID}/required-users/check` accepts one closed
`PresenceCheckRequest.client_request_key` UUID, with a 4,096-byte body limit. Existing session,
current administrator entitlement, HTTPS/Host/Origin and unsafe-request protections apply. A browser
cannot choose workspace, subject IDs, credentials, provider facts or a connection revision. The
response is an `ActionReceipt` with operation_id, state, simulated provider_mode and accepted_at;
202 records accepted or already-recorded work, not completed presence verification.

Admission uses the existing administrator-anchor/workspace locks and then locks the registered
child. Same-actor/workspace request replay is checked before reloading the target context; a changed
request under the same key conflicts. New requests require an active, idle, registered child under
the configured parent, all three canonical identity bindings, an active accepted simulated
connection, and the currently selected unpaused provider policy. Distinct explicit request UUIDs
remain independent, even for the same child/context; they are not coalesced. The exact same request
UUID always replays its own operation, including after completion. Operation,
immutable intent, check row and native queue deferral commit atomically. Foreign and unknown child
IDs share the usual not-found behavior. Missing configuration is unavailable, never Missing users.

## Worker, authority and source facts

The UUID-only native task is `otm.required_user_check`, on the existing workspace queue; it has no
automatic provider fallback or repair behavior. The operation kind and step command_kind are
`required_user_check`, with step_key `required_users:{tenancy UUID}` and effect_knowledge=none.
The worker uses short claim/publication transactions, releasing all locks before provider work.
It locks the protected local-administrator anchor, workspace, operation and child in that order,
then the check. A fresh attempt UUID and incremented attempt number fence interrupted/redelivered
workers; only the current attempt can seal a result. A terminal result cannot be overwritten.

Before acquisition and again before publication, the worker verifies the initiating administrator's
active grant and exact authorization revision/actor, current child lifecycle/revision and absence of
conflicting lifecycle work, canonical identities/generations/domain, active connection/revision and
unchanged unpaused provider policy. A changed context yields superseded evidence containing only
Unknown observations; it cannot certify current presence. The reader also requires the original
stored hash and exact current identity/connection context before presenting per-user results.
Read-only compatibility excludes only the tenancy display name and registry revision; execution
checks still require the full captured snapshot. Membership changes cannot erase an otherwise
compatible dated result.

The local adapter authenticates the producer's immutable onboarding capture hash, scope and typed
verified outcome, then restores independent domain/user fixtures from those retained producer facts.
Expected current binding rows select targets; they are not used to fabricate observed users. This
is a simulation of known producer facts, not an independent live cloud read. A future OCI adapter
must qualify exact-domain absence, credentials, permissions and propagation separately. No real
credentials or parent/recovery fallback are composed by this checkpoint.

A 30-second total attempt window rejects results returned too late; backward clock movement
detected at publication also produces unavailable results. This is a publication freshness bound, **not an SDK/network
timeout**: it does not cancel a blocked external request. Real adapters still need bounded I/O and
reconciliation qualification. Each observation retains its own captured_at; no aggregate timestamp
is copied over older account observations. Complete authorized absence alone means Missing;
denial, malformed/partial results, unqualified domain, timeout or unavailable source means Unknown,
rendered **Unable to verify**. A partially available pair may retain one confirmed subject and one
Unknown. The operation still succeeds once both bounded outcomes are durably recorded; success
means acquisition bookkeeping completed, not that both users exist or access is healthy.

## Physical storage: all 14 check columns

Migration **0025_user_presence_checks** adds `otm_user_presence_check`; actual application metadata
now contains 25 tables. Earlier migrations and stored results are preserved. The existing operation,
step and audit tables gain allowed kinds; there is no second queue, audit store or access profile.

| Column | Source and rule |
| --- | --- |
| operation_id | UUID primary key and same-workspace operation FK; exactly one child check per operation. |
| workspace_id | Authenticated workspace scope for every reference/read. |
| tenancy_id | Same-workspace registered child FK. |
| acquisition_sequence | Database-generated unique monotonic bigint allocated at admission. Latest means greatest sequence for this child, not latest finishing worker or greatest wall-clock time. |
| context | Immutable closed PresenceSnapshot JSON from the accepted intent. |
| context_hash | SHA-256 of canonical context; must agree with immutable intent and sealed evidence. |
| state | queued, reading, complete, unavailable or superseded. Sealed terminal states are immutable. |
| attempt_id | Null at admission; fresh UUID on each claim/reclaim. Late callbacks must match the current UUID. |
| attempt_number | Zero while queued; positive, incrementing execution generation after claim. |
| started_at | Null while queued; UTC start of the current attempt, not a provider-read timestamp. |
| checked_at | Null until sealed; UTC publication time, no earlier than started_at. |
| results | Null before sealing; exactly two closed RequiredUserObservation JSON values in automation/recovery order. Each has independent captured_at, scope, authorization, completeness and facts. |
| evidence_event_id | Nullable until sealed; same-workspace/operation FK to immutable required_user_check_outcome. |
| created_at | UTC operation accepted_at; fixed at admission. |

Initial context/identity are immutable; only attempt and terminal publication fields advance. Database
guards validate admission source, child/connection scope, attempt transitions, immutable outcome
agreement and result target/attempt/connection references. Application decoding additionally checks
canonical hashes and typed invariants. Delete/truncate are denied. The installed API role can read
and insert the bounded admission columns/use the sequence; the worker can read and update only
attempt/result columns. The reviewed owner-only local reset explicitly includes check rows; normal
reads and workflows cannot reset them. Historical operation/audit/admin records remain retained.

[Implemented ER source](../architecture/diagrams/user-presence-checks-implemented.mmd).

## Closed contract field dictionary

These are JSON/model fields, not additional SQL columns. Existing required-user provider contracts
remain `required-user-presence-2`; the new operation/evidence envelope is `user-presence-check-1`.
The public schema inventory is now 75 exported snapshots. Complete Python validators remain authoritative beyond what generated schemas express; a structural schema does not prove transaction/authority guards.

| Model | Every field and source |
| --- | --- |
| PresenceCheckRequest (1) | client_request_key: caller's UUID for one logical submission/retry; no other input accepted. |
| PresenceSnapshot (8) | tenancy_id/name/revision from registry; connection_id/revision from selected active connection; policy_hash from canonical trusted provider policy; subjects: exactly two RequiredUserTarget values from canonical bindings, automation then recovery, same child/domain and distinct subject/SCIM identities; recovery_console_fingerprint: optional current desired network-policy fingerprint, not raw CIDRs. |
| PresenceCheckIntent (9) | contract_version=user-presence-check-1; kind=required_user_check; workspace_id and administrator_id/authorization_revision from authenticated current grant; snapshot; context_hash; target: existing ConfigurationOperationTarget carrying the exact child OCID and display label. Immutable operation_intent stores it with the initiating actor. |
| PresenceCheckEvidence (13) | contract_version; tenancy_id; operation_id; context_hash; state=complete/unavailable/superseded; safe_code=USER_PRESENCE_CHECK_COMPLETE/USER_PRESENCE_UNAVAILABLE/USER_PRESENCE_SUPERSEDED respectively; started_at; checked_at; results: two provider observations tied to the admitted attempt/scope and capture window; optional administrator_access (automation), recovery_administrator_access (recovery), recovery_console and notice_episodes retain independently scoped assignment/policy and missing-user incident evidence. Optional absent fields preserve historical hashes. |
| UserPresenceView (4) | state=not_checked/present/missing/unknown; checked_at from that subject's captured_at, nullable when no current matching result; stale from server UTC age/window test; operation_id for the exact retained check, nullable when not checked. Defaults are not_checked/null/false/null. |

The existing RequiredUserTarget (13), RequiredUserReadContext (8), InspectRequiredUser (3),
ObservedRequiredUser (4) and RequiredUserObservation (12) are fully mapped in the
[presence boundary reference](required-user-presence.md). No assignment/profile/credential IDs are
invented. Public directory/identity/record fields are mapped in the
[Required users screen reference](required-users-screen.md).

Sealing adds `required_user_check_outcome`, actor_subject `otm-worker:user-presence`, and exact
actor_snapshot {kind: worker, subject: user-presence}. Audit History/CSV render **User presence worker**
with the closed state/code and scoped resources. Operation detail links back to Required users via
its tenancy context. Neither audit nor Operations is an actionable repair inbox for these reads.

## Current display, freshness and qualification

Results come from the greatest admitted terminal acquisition_sequence, not the last callback to
finish. A newer unavailable check does not silently reuse an older positive result; within a partial
new result, each subject retains its own actual outcome. A newer pending check keeps the previous
terminal results dated while polling progress. A result whose context no longer matches is not
shown as current. No automatic background provider refresh is implied.

Each account becomes stale at exactly 24 hours after its own captured_at, or if its timestamp lies
in the future relative to server UTC. The UI replaces its primary label with **Check out of date**
and displays the last result separately. Only a fresh check can restore a current Present/Missing
label. This freshness threshold is currently code-owned, not a new application setting. The UI polls
GET once per second only while pending_operation_id exists; the single Refresh user data action starts acquisition, while page-level Refresh only reloads stored results.
An uncertain Refresh user data response retains its request key while this component is mounted. Retrying
uses that key; navigation/reload may discard this local memory, so inspect pending Operations first.
Server-side committed replay remains durable when a known key is reused.

Both complete unit/coverage gates and all 351 PostgreSQL/native-worker/HTTPS-browser cases pass. The main preview is upgraded with all 28 preexisting public tables preserved; the parallel test preview remains unchanged. No live OCI result is claimed. Daily scheduling is deferred to staging/Kubernetes with a separately qualified machine
admission/authorization path. Those counts describe the original presence-only checkpoint;
[current confirmed-Missing email](required-user-alerts.md) is a separate implemented extension.
Identity repair remains deferred. All real-provider cases remain
Pending in the [manual manifest](../how-to/real-oci-test-manifest.md); the
[runbook](../how-to/required-users-runbook.md) provides the intended local simulated review steps.

### Complete local verification

The required lanes pass separately: 1,556 backend units at 9,228/9,597 covered lines, all 351 postgres
marked database/native-worker/Playwright cases, and 446 frontend units at 1,770/1,816 lines. The two
backend selections are disjoint and cover 1,907 tests in total; frontend coverage remains separate.
The complete integration run took 429.457 seconds, with valid JUnit and zero failures/errors/skips,
within the user-approved 600-second aggregate limit. Earlier 420-second deadline-expired runs are
incomplete evidence, not passes. Individual bounds, assertions, both 95% coverage gates and all
required jobs remain unchanged. See the [test-lane policy](../engineering-test-plan.md#complementary-backend-test-lanes)
and [dated validation/preservation receipt](../history/manual-presence-checkpoint-2026-11-06.md). The main preview was deliberately
upgraded; no historical records were backfilled and the parallel preview was not changed.

### Inventory summary follow-up — source checkpoint

A later [derived Tenancies Status summary](required-users-summary.md) reuses the same exact context,
immutable-evidence decoding and per-user age logic. Its original four-field RequiredUsersSummary (now seven after the independent policy/assignment extensions) and single
additive TenancyView.required_users field are read projections, not new check columns or operations.
Active page IDs bound four additional workspace-scoped queries. Fresh confirmed Missing with its own date/check reference takes precedence; other unsupported positive labels are unavailable before stale/unknown/two-present/default evaluation. DTO and frontend guards prevent coarse label-only positives. Configured corrupt canonical records become an unavailable summary/closed detail 503; genuinely unconfigured or validly changed contexts remain Not checked. Stale facts cannot stay green, and pending checks retain dated results. No Refresh user data
admission/execution behavior, table, daily schedule, email or live OCI adapter changes. Local qualification and the main-preview update for this follow-up pass; the parallel preview is unchanged. [Final summary receipt](../history/required-users-summary-checkpoint-2026-11-06.md). The completed pipeline receipt above retains its original scope.


## Retained results after membership changes — 7 November 2026

Results are durable database observations, not browser-session state. Navigation and page reloads
read the latest sealed check; they never invoke the provider. Adding/removing a member or changing
ownership updates registry revisions without discarding observations for unchanged required users.
Read compatibility ignores only `PresenceSnapshot.tenancy_name` and `tenancy_revision`. Exact
workspace/child/parent/organization, user/domain/SCIM bindings and generations, connection ID/revision
and policy hash still match. The original stored context/hash and audit evidence remain immutable
and validated; admission and worker publication retain full revision fences. Inactive/unbound/busy
contexts remain unavailable to this projection. Original capture timestamps determine staleness;
viewing a page cannot renew them. A newer unavailable result never borrows an older positive result.


New alert-enabled checks now carry optional incident state and may stage confirmed-Missing notices;
see the [complete alert contract](required-user-alerts.md). This supersedes earlier no-email scope
only for qualified Missing notifications. Daily scheduling, broader effective-privilege checks and repairs remain deferred; the scoped automation assignment extension is implemented.

## Compact checked-date presentation — 9 November 2026

Current cards collect their checked dates after all status facts. Date-only UTC links replace the
separate full timestamp plus View check text; accessible names identify each check and full UTC
instants remain in hover detail/metadata. This changes no API fields, freshness, polling, history,
operation IDs or read authority. See the [current screen guide](required-users-screen.md#compact-check-dates--9-november-2026).
