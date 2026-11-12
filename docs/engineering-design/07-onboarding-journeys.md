# 07: create, import and onboarding operations

20 October 2026 | C1/C2 working detail | D18–D20 accepted; provider contracts still require qualification

[Design hub](README.md) · [Domain model](01-domain-and-journeys.md) ·
[Execution/facade](02-operations-and-provider.md) · [Identity constraints](04-identity-and-access.md)

[Interactive screen walkthrough](../walkthroughs/onboarding-walkthrough.html)
uses inert sample records, including supplied Platform Engineering identities. It is a design artifact,
not a second running application. Buttons only navigate sample states; nothing creates accounts,
sends invitations or contacts OCI. The screen contracts below distinguish accepted behavior from
proposed details. Candidate state labels are not approved database enums or API routes.

The walkthrough also includes [shared-member setup](../walkthroughs/onboarding-walkthrough.html#member),
whose authoritative profile/parent-picker contracts are in [chapter01](01-domain-and-journeys.md#member-compartment-setup-d24-accepted).

## Concrete SDK trace

[Chapter08's ordered map](08-oci-sdk-call-design.md#create-and-import-ordered-call-map) binds the
stages below to exact SDK candidates and access contexts. Create/termination responses have no
tenancy object in their body; persist qualified response/correlation evidence separately. Domain
handoff translates the supplied bootstrap user OCID to a verified SCIM resource ID before domain
calls. D27 confirms identity-domain-only user management for existing and new tenancies; import
still discovers the actual domain/configuration. No legacy identity fallback is implemented.
The static source receipt does not establish live permission, activation or readiness.

## Shared boundaries

An administrator explicitly starts create/import. New-person reviews close only when operation,
initial audit/job and review closure commit together. The returned operation link replaces that
review as the place to monitor work. No association is active merely because a request was accepted.
Maintain pending ownership separately; normal inventory shows verified managed tenancies, with
pending setup visible through Operations and a linked summary indicator rather than disguised as
an active tenancy. Do not lose an employee whose onboarding is pending or failed.

Create, import and Add to shared tenancy remain different intents. Multiple tenancies per person
are allowed. A unique person constraint must not prevent a deliberate second tenancy. Prevent
concurrent onboarding of the same OCI tenancy using verified OCID binding and operation coordination.
Names identify neither provider resources nor people. Person UUID, organization revision and
observed OCI IDs retain separate identities and provenance.

The initiating actor, current responsible administrator, intended owner, initial child administrator,
bootstrap API identity, permanent automation identity and recovery custodian are distinct roles.
An authorized replacement administrator can take responsibility through an audited reassignment;
it does not change the recorded creator or silently transfer the initial administrator's mailbox/MFA.
External activation recovery remains manual when those credentials cannot be recovered.

D49 sends a lifecycle attention email only after accepted work durably requires administrator action
or reaches known terminal failure. Draft/preview typing, ordinary provider waits and successful
completion do not email. The notice links the operation and carries no activation URL/key/password.
D50 routes these lifecycle notices only to the current responsible administrator, initially the initiating admin; explicit audited takeover may change responsibility without changing the owner or immutable activation mailbox. There is no all-admin email fallback; unresolved routing remains visible for takeover. [Chapter15](15-collection-and-operational-events.md#d49-accepted-lifecycle-email-only-for-action-or-terminal-failure)
records state/episode and content boundaries; D20 owner sign-in and D23 manual resource guidance do
not create additional lifecycle email workflows.

## Journey C: create individual or shared tenancy

| Stage | Screen/input and administrator action | Durable effect and verification |
|---|---|---|
| C1 Details | Choose eligible owner, individual/shared, requested name and home region; show parent and initiating verified email; no Reason input | Draft only; no OCI calls. Name/region required by create API, not proof of availability or eventual identity |
| C2 Preview | Show organization/accountability, intended owner rights, parent, requested identity, configuration version/overlays and manual activation requirement | Refresh entitlement, owner/context and effective configuration; later stale preview requires a fresh preview |
| C3 Start | Start creation; disable repeated submission while recovering the same request ID | Commit operation, pending intent, review closure, initial audit and runner job together; return operation ID after commit |
| C4 Provider request | Operation progress shows provider request/pending state, not a falsely active tenancy | Parent facade creates/reconciles the child. Persist attempts and known correlation/OCID; uncertain outcomes do not cause blind duplicate creation |
| C5 Activation | Manual checklist: administrator activates in OCI, sets password/MFA and creates temporary API user with displayed public key | Persist waiting condition without occupying worker or holding a long database transaction. Private key stays in Vault; no password/MFA/activation-link collection |
| C6 Handoff | Supply/confirm tenancy OCID, bootstrap user OCID and create-only activation administrator user OCID; name is discovered. Request additional nonsecret region/domain context only if needed | Fresh entitlement and context checks; verify key/identity, actual parent, actual metadata, existing operation binding and required grants. A wrong/different target does not resume automatically |
| C7 Configure | Read-only progress for permanent automation, recovery, owner and remaining baseline | Create permanent automation and verify using its own signer; apply dependency-ordered managed objects, preserving unrelated objects. Each item has verification/evidence |
| C8 Verify and retire | Show mandatory checks and any remaining human enrollment/recovery steps | Confirm alternative administration and recovery, then permanent automation retires initial child-local admin and temporary API key/user; verify cleanup. No self-deletion or last-admin violation |
| C9 Complete | Managed tenancy detail and operation history; owner sign-in status follows D20 | Atomic local publication after verified outcomes; record active association and verified configuration. A failed/unknown mandatory check cannot become success |

Freeze the chosen baseline version, overlay revision and effective intent at acceptance (D1/D9).
If a required onboarding configuration must change later, stop at a safe boundary, show a revised
preview and record an explicit amendment/superseding operation. Do not silently resolve a newer
published template midway through setup. Exact amendment/cancellation API is a C2 contract gap.

### Activation administrator cleanup target (D55)

For create only, collect the activation administrator’s user OCID alongside the child and bootstrap
user OCIDs. After read-only discovery, show the exact account that will be removed and require
confirmation. Persist the verified domain/OCI/SCIM binding and operation provenance in the existing
intent/binding records; [chapter11](11-production-data-model.md#create-only-activation-administrator-binding-d55)
defines the field mapping and protected-identity checks. Import preserves unrelated humans.
Cleanup waits for verified permanent replacement access and recovery readiness. An unresolved or
changed human identity blocks cleanup; neither email matching nor a name is a destructive target.

### Naming and handoff

Store requested and observed names separately. Local validation checks syntax, not global
availability. A definitive OCI name rejection enables corrected-name submission with an appended
attempt record. A timeout after creation enters reconciliation before another create call.
At handoff, retrieve actual name/home region through the facade, and prove parent membership through
the parent context. Preserve both original request and final facts. Show a changed name as discovered
metadata, not as a tenancy replacement. Changing the supplied OCID requires explicit reconciliation
and verification before configuration writes. The exact activation-time name-change behavior is
reported by the user and remains a provider qualification case.

### Activation screen

- Header: operation type/ID, current owner, requested name until actual name is verified, responsible
  administrator, started/last-updated dates and explicit human-wait status.
- Read-only initiating verified email, requested home region and known provider request details.
- Numbered instructions: finish OCI activation/password/MFA; create temporary API identity with
  specified grants; upload the public key; return with both OCIDs. No browser agent or email reader.
- Public key download/copy with clear public-only label. Never expose the private key or a Vault
  secret in page source, logs, exports, URLs or browser persistence.
- Handoff fields: tenancy OCID, bootstrap user OCID, activation administrator user OCID (create only), optional nonsecret discovery context only when
  requested. Preserve input after validation failures; display field-specific errors.
- Primary action: Verify and resume. Describe that this verifies the target and starts automated
  provisioning, not that the button merely records manual acknowledgment.
- Unsupported actions have no misleading live button. Sensitive transient material stays out of
  links/query strings. Reopening the operation shows persisted progress, not a blank wizard.

## Journey I: import an existing child

Parent detachment/attachment happens outside OTM. Import must independently verify that attachment
has completed; a checked checkbox is not evidence of actual parentage. Original OCI tenancy origin
and imported-via-OTM provenance remain separate because deletion eligibility may differ by origin.

| Stage | Screen/input and action | Durable effect and verification |
|---|---|---|
| I1 Identify | Choose owner/type and tenancy OCID; explain external parent-transfer prerequisite | Draft, not a registration/access guarantee; owner may already own other tenancies |
| I2 Bootstrap | Provide temporary username/public key and setup instructions for a child administrator | Private key in Vault; administrator returns bootstrap user OCID. No private-key upload through the browser |
| I3 Inspect | Read-only checks resolve actual metadata, parent, domain and bootstrap privileges; expose collisions | Inspection is itself a durable, audited operation if it requires credential/provider work. Persist draft/check evidence; it does not close the organization review or start configuration |
| I4 Preview/start | Show actual tenancy/owner, preserved existing objects, managed additions and any blocking collision | Revalidate evidence at start; commit onboarding intent/job/audit/review closure atomically. Only now does the organizational decision move to Operations |
| I5 Configure/verify | Reuse C7/C8 with imported tenancy origin and domain capability checks | Verify permanent automation before temporary cleanup; preserve unrelated owner objects. Imports never delete existing unrelated human administrators automatically |
| I6 Complete | Managed detail with provenance retained; same ongoing monitoring/configuration experience | Active ownership published after mandatory checks. Unsupported deletion eligibility stays visible; import does not manufacture provider capability |

A discovered name collision is not permission to take over an existing object. Managed object
bindings use inspected IDs with D6 ownership/collision semantics. Optional inspection may check
existing managed configuration, but changing owner objects requires a separately reviewed action.
On import, do not blindly delete the human who supplied bootstrap access: the target is pre-existing
and may have other administrators. Only explicitly scoped temporary API access is retired by default.

## Readiness decision D20: owner first sign-in

Accepted A, 20 October 2026: completing OTM setup does not require the engineer to sign in first.
Mandatory checks remain validated child identity/parent, verified permanent automation, required
managed baseline, an operational independent recovery path, correct intended owner/admin grants
and required MFA enforcement, plus verified temporary-credential cleanup. D39/D40 select an MFA exemption only for the persistent recovery account; no recovery check may
be described as verified until the exemption scope and actual recovery access are qualified. Security findings/audit-user provisioning remain V2.

Show owner access independently from historical setup success. Candidate labels are Activation
requested / Sign-in not confirmed / Confirmed / Check unavailable, using only evidence the provider
actually exposes. These labels are not yet approved storage/API enums. An accepted invitation request
is not proof of delivery or enrollment. Where no qualified observation API exists, keep Not confirmed
and record any explicit administrator verification with actor/time/source, not as a fabricated OCI fact.

No owner confirmation or approval is added to onboarding. A required first-login MFA challenge may
remain ahead of the engineer while the tenancy is otherwise managed and ready for monitoring.
Never collect their password, factor or activation link as proof. Later access drift changes the
current access observation and can raise an alert; it does not erase the historical setup outcome.
The walkthrough now illustrates this accepted separation, not a pending policy choice.

## Execution contract refinement

[Chapter09](09-execution-contracts.md) defines the candidate internal request/result messages,
state/stage/wait model, precise acceptance/resume/amend/stop boundaries and create/import graph.
It includes machine-checked draft examples and planned runtime failure scenarios. The [separate
Operations walkthrough](../walkthroughs/operations-walkthrough.html#activation)
illustrates these states without implementing them. The labels below remain proposed UI concepts;
no current runtime enum, DB table or route was changed.

## Operation progress and recovery contract

These are proposed UI concepts to refine into storage/API enums, not a new workflow framework.
Each persisted step has an attempt history, expected target, credential reference, intent version,
known provider correlations and last verification outcome/time. Secret values never enter attempts.
Worker retry and administrator retry both resume existing intent; neither creates a fresh tenancy.

| Visible state | Meaning | Available action / guard |
|---|---|---|
| Queued | Accepted and durable; no execution evidence yet | View intent; cancellation only if dispatch exclusion can be proved |
| In progress | A worker is executing bounded steps | View steps; no second Start and no promise of instantaneous cancellation |
| Waiting for OCI | A known provider operation is pending | Poll asynchronously; refresh observes persisted status, not a browser-driven create |
| Waiting for administrator | A specific manual activation/custody/handoff prerequisite is missing | Complete the checklist; Verify and resume rechecks current facts and entitlement |
| Retry scheduled | A qualified retry is due for an observed safe/transient condition | Display last issue and next attempt; no retry of an uncertain write without reconciliation |
| Checking outcome | A mutation may have succeeded; outcome unknown | Reconcile; restrict conflicting changes to the target. Do not offer blind Try again |
| Needs attention | Invalid input, failed verification, expired/revoked bootstrap or incompatible object requires help | Correct input, establish access or inspect conflict; preview any changed intent before resume |
| Setup verified | All mandatory setup checks under accepted D20 A have passed | Open tenancy; owner sign-in status is independent |
| Cancelled / Failed | Safely stopped future work or exhausted a confirmed recoverable execution path | Preserve partial resources/history; show exactly what remains and a scoped recovery action |

Do not hold worker slots, database transactions or a per-tenancy execution lease while waiting for
activation. Keep a durable operation guard against conflicting onboarding/delete/rollout. Read-only
observations may continue where supported; deadline-sensitive credential cleanup retains its reserved
capacity and still obeys mutation/uncertainty coordination. Exact locks/fences remain C2 detail.

Cancelling scheduling does not reverse effects. Before provider creation is dispatched, cancellation
may be safe with an atomic exclusion check. After creation or any import writes, Stop further setup
must show retained resources and outstanding credential cleanup. It must not delete a tenancy,
retire the only usable administrator or silently abandon temporary credentials. Unknown in-flight
writes reconcile before another mutation. Deletion always remains a separate explicit guarded action.
A stopped operation may require manual recovery; it is not a successful onboarding result.

Browser close, refresh, worker restart and different-admin resume read the same persisted operation.
Failed transient parentage/permission queries are Unverified, not Wrong parent or Missing user.
Membership changes or feed absence while waiting trigger visible context review; they do not reassign
ownership, create another operation or delete the tenancy. Revalidate current guards before dispatch.

## Screen and contract inventory

| Design screen | Input/display | Proposed backend intent | Errors/empty/stale behavior |
|---|---|---|---|
| Create details/preview | Owner/type, requested name/region, parent, version, activation actor | Preview create; then accept create with request/preview context | Field errors preserve data; invalidated preview refreshed; duplicate submit recovers original operation |
| Import details/bootstrap/inspection | OCIDs, public key, discovered identity, collisions | Prepare bootstrap/inspect; then preview/accept import | Missing access, wrong parent, bound target or collisions block start; inspection failure does not resolve review |
| Operation list | Type, target, responsible admin, state, last update; search/filter/sort/page | Query persisted operation summaries | Separate empty/no-match/error/stale; normal UI viewing does not schedule work |
| Operation detail | Step timeline, current action, correlation, verified facts and timestamps | Read progress; resume/reconcile scoped intent | Distinguish pending/unknown/partial; success shown only with verification; generic errors and no raw secrets |
| Managed tenancy detail | Verified identity, association/configuration, fresh observations | Read tenancy and linked operation/history | Show owner sign-in separately under D20 A; current access drift does not erase past setup success |

These are command concepts, not promised route strings. API/CLI share application validation,
accepted-intent rules and error types; generated OpenAPI bindings follow reviewed contracts (D11).
API client request IDs remain stable across transport retries. Confirmation screens do not create
extra business approvals. Every real action checks current corporate authorization; local actor labels
and the prototype's Clean workspace feature are excluded.

## Acceptance scenarios to implement later

| Scenario | Expected evidence |
|---|---|
| Create accepted, response lost, same request retried | One operation and one accepted review transition; recover operation ID without another create |
| Create timed out after OCI effect | Unknown state, correlated discovery and no automatic second tenancy |
| Name rejected, corrected, actual name different at handoff | Immutable attempts, verified actual display, same target binding and no duplicate create |
| Wrong/different/already-bound OCID | No configuration write; explicit conflict/reconciliation and audit |
| Bootstrap read works but domain-user creation forbidden | Needs attention before retiring initial administration; no false privilege check |
| Permanent automation probe fails | Temporary access retained, explicit partial result; retry reconciles created identity/key |
| User creation succeeds but baseline/recovery check fails | Not managed-ready; no association-success claim; no destructive compensation |
| Temporary user removal fails | Visible cleanup requirement; no verified completion; no leaked private key |
| Owner has not enrolled MFA | Separate unconfirmed owner access; verified setup may complete; required MFA enforcement still verified |
| Import contains unrelated administrators/policies | Preserved; explicit collision handling; only scoped temporary bootstrap retired |
| Browser or worker restarts during manual wait | Same operation/instructions, no thread/DB transaction held for the wait |
| Source person moves or disappears during setup | Context change visible; no implicit owner transfer/deletion; refreshed guards before resuming |
| Cancel after a partial side effect | Retained resources and credential cleanup visible; no automatic tenancy deletion |
| App unavailable and automation removed | Documented independent recovery path, not a button that needs the removed identity |

These are planned scenarios, not new executed tests. The 134-test prototype remains unchanged.

## Guided local implementation — 31 October2026

[The implemented onboarding guide](../reference/tenancy-onboarding.md) maps actual commands, waits, field custody and tests. New create/import simulations now pause for handoff, verify exact IDs, require cleanup review, then verify replacement access before retirement/publication. This is not real OCI/IAM/Vault or baseline qualification; the production journey above remains authoritative for those boundaries.

## Required creation inputs restored — 31 October2026

The runtime now follows C1/C03: Create requires requested name and parent-subscribed home region before acceptance. Original operation intent preserves them; bootstrap discovery later verifies actual metadata. Import stays discovery-only. Earlier local guide text/screens omitting those inputs were a regression and are superseded by [the corrected field guide](../reference/tenancy-onboarding.md). Successful Operations link directly to the registered tenancy record.

### Documentation-backed handoff checklist (31 October 2026)

The current app shows the child-console activation, tenancy/user OCID copying, bootstrap creation,
separate identity-domain role, and public-key upload steps. Import links the applicable created/invited
transfer procedures separately. [The implementation guide](../reference/tenancy-onboarding.md#oci-console-handoff-instructions)
contains the complete operator procedure and Oracle sources. Simulation remains explicit; no actual
credentials or OCI objects are produced. The existing C05/C06 verification and cleanup gates remain.

### Import target and rejected creation names — 2 November 2026

The import modal chooses the target once; setup carries its OCID read-only, requests only bootstrap
user OCID and rejects forged retargeting. Create still collects child identity at handoff. Local
registry-name rejection keeps the creation form and other choices intact; no operation exists until
admission succeeds. For the future OCI adapter, a definitive no-effect name rejection must allow a
new name on the same paused operation, retaining audit and owner/type/region. An uncertain response
requires reconciliation before a changed request. [Current behavior, tests and live-adapter gaps](../reference/tenancy-onboarding.md#import-target-continuity-and-name-conflict-coverage-2-november-2026)
are explicitly separated; asynchronous OCI name correction is not implemented by today's simulator.


## Local create/import and shared-access refinement — 3 November 2026

Local simulation qualified and installed in both saved instances. New create/import uses guided version 2: initial permanent/
required access checks → frozen baseline policy/quota/budget/tags application/readback → fresh
automation/required-access checks → exact temporary-account retirement → active registry ownership.
The current publication is selected once at admission, never again during a human wait or retry.
Previously accepted version 1/absent-version intents retain their original graphs. Partial simulated
objects survive a failed category; all four must verify before baseline/time heads advance, and a
post-configuration access failure still blocks retirement and ownership activation.

Join shared now supports the accepted D24 alternatives: select an existing non-root compartment in
the registered child, or create a new compartment under a discovered parent. Freeze the exact choice;
reject combined inputs and wrong/root/unknown targets. Shared-member removal validates a scoped
identity receipt and records group-removal/user-deletion steps before reporting completion, while
manual compartment/resource guidance remains explicit. It never inventories/purges resources.
Existing owner/member links and Transfer owner remain; only the redundant top Manage owner &
associations shortcut is removed. Dedicated Overrides presentation and a registration-created-time
status tooltip add no separate lifecycle authority.

[Runtime steps and evidence](../reference/tenancy-onboarding.md) ·
[Membership field map](../reference/organization-workflows.md) ·
[Manual review runbook](../how-to/tenancy-refinements-runbook.md).


## D50 application responsibility takeover checkpoint — 4 November 2026

Application capability qualified locally and installed in both saved instances. Another already entitled administrator can explicitly claim
waiting/needs_attention guided create/import work (accepted versions 1/2), using the existing
responsible subject and operation revision. Confirmation is self-claim only; no Reason, other-admin
picker, view-triggered reassignment or provider job. Creator, activation mailbox/MFA, owner, provider
intent/hash/revision, baseline and verified progress remain unchanged. External activation recovery
stays manual.

The immutable claim captures replacement grant/revision and exact original intent context. Worker
continuation validates that proof and the current replacement grant, retaining all target/policy/
effect guards; creator revocation need not permanently strand a properly claimed operation. A
revoked/regranted replacement cannot silently regain authority through an old proof. Only the current
responsible administrator may submit the next handoff/setup command.

This is the selected OCI-independent application capability while parent-tenancy access is absent.
No temporary simulation-control UI, automation-key permission handoff or new credential flow is
added. [Runtime fields and authority](../reference/responsibility.md) ·
[Manual review](../how-to/responsibility-runbook.md).


## Implemented onboarding identity capture — 6 November 2026

Newly accepted create/import intents now use onboarding version 3. After baseline application and
fresh access probes, a required capture step retains exact automation/recovery domain, SCIM and OCI
identifiers in existing `otm_operation_step.last_outcome` and immutable `audit_event.data` before
retiring temporary access. Failed capture blocks retirement. Historical accepted version 1/2/absent
intents keep their graphs; no name-based adoption or historical binding backfill occurs.

See the [implemented field/storage map](../reference/tenancy-onboarding.md#permanent-user-capture--6-november-2026).
Migration 0022 only expands the existing step constraint. No table, column, credential store or new
ER relationship is added. This supersedes earlier statements that onboarding retains no permanent
identifiers, while keeping the proposed canonical managed-object binding, access-assignment heads,
current-generation checks and full access-health model as future implementation. Capture evidence
alone must not authorize repair, disclosure or live operations. Saved previews are not changed.
Live qualification remains Pending in the [manual manifest](../how-to/real-oci-test-manifest.md).

### Compact operator guidance

Lengthy create/import handoff procedures are available under a default-closed OCI administrator
checklist disclosure. Forms, targets, actions, critical notices and cleanup consent remain
visible. Native summary keyboard behavior and shared help styling follow the
[UI policy](../ui-ux-review-policy.md#optional-operator-instructions--7-november-2026);
[the implemented guide](../reference/tenancy-onboarding.md#collapsed-oci-operator-checklist)
defines the field-preservation and transient-state boundary. No persisted model changes.


## Current local public-key handoff — 12 November 2026

Both create/import now expose the operation-bound public PEM and bootstrap username in visible Enter in OCI controls. Explicit local RSA preparation and legacy preparation action, public-only GET and transaction/live boundaries are mapped in the [implemented onboarding reference](../reference/tenancy-onboarding.md#public-bootstrap-handoff--12-november-2026). Current bundle targeted qualification PASS; saved publication PASS; no installed OCI key or Vault proof.
