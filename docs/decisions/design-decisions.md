# Accepted design decisions D18–D58

These accepted decisions are retained from the design ledger. Later accepted refinements in the
linked current engineering chapters supersede earlier alternatives explicitly; implementation
qualification is described by the current reference guides, not implied by an accepted decision.
D1–D17 remain in [the engineering decision record](engineering-review-decisions.md).

## D58 administrator implementation checkpoint — 29 October 2026

[Chapter19](../engineering-design/19-administrator-provisioning.md#detailed-checkpoint-two-new-tables-existing-sessions-and-audit)
now specifies the two-table administrator/credential extension, exact grant/revision session binding,
restricted operator MFA bootstrap/reset, atomic login/audit and the Administrators screen contract.
The full proposed inventory is 30 tables; the A1 production subset is now six, including the two
[administrator foundation tables](../reference/administrators.md). Local
recovery sign-in requires password plus independent MFA and never depends on corporate SSO.
Implementation proceeds grants/audit → local sign-in → UI → corporate integration. This is a
reviewable design checkpoint, not completed authentication code or whole-package signoff.

Application and configuration releases now have [separate deployment paths](../engineering-design/18-database-ci-and-build-order.md#application-and-configuration-deployment-paths).
Supported settings changes reuse the deployed image, validate its schema and roll consumers;
all existing CI/test/merge requirements remain binding. No hosted pipeline or OKE job is deployed.


## D58 local password/MFA backend checkpoint

[Local application authentication](../reference/local-authentication.md) now implements restricted
one-time operator bootstrap/reset and explicitly composed password-plus-TOTP sign-in, replay-safe
sessions and atomic login/logout history. No passwords/seeds/default account are added to source or
the settings file; local test custody is owner-only and production Vault remains a qualified facade
adapter. The actual model is still six application tables, now six frozen migration revisions.
Next work is the real sign-in/Administrators UI, ordinary grants and corporate provider qualification.
No OKE resources, hosted pipeline or real human account were created by local backend validation.


### D18: initial activation responsibility

Finding: C1-01; medium design gap; high confidence. Existing create flow names administrator
activation but does not distinguish the OTM operator from the future engineer owner.
Evidence: [specification §6.1](../product/oci-tenancy-manager-spec.md#61-create), and current
[Oracle child-tenancy creation documentation](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm).
Plan baseline: creation pauses for manual activation/password/MFA; which identity activates is unresolved.
Runtime evidence: prototype creates a local simulated registry entry; it has no activation integration.

| Choice | Current | A | B |
|---|---|---|---|
| Recipient/responsibility for initial activation | Unspecified | OTM administrators using a designated bootstrap administrator identity | Engineer/tenancy owner activates, then provides the reviewed bootstrap handoff |
| Final owner rights | Full administration approved | Unchanged | Unchanged |
| Application users | Administrators only | Unchanged | Unchanged |
| Manual wait and resume | Approved | Admin activation wait | Owner activation/bootstrap wait |
| Exact email/MFA/identity/credential lifecycle | Pending qualification | Still pending C4 | Still pending C4 |
| Owner access timing/required readiness checks | Pending detail | Remains pending | Remains pending |
| Engineering action now | Design only | Design admin-led activation branch | Design owner-led activation branch |

Question D18: Who should activate a newly created child tenancy?
OCI sends an activation message to the designated initial administrator. We need to choose who
performs that step, because it determines the waiting screen, instructions and bootstrap handoff.
Recommendation: A, OTM administrators, because the first release is an administrator-operated service.
A) OTM administrators (recommended): A designated bootstrap administrator receives activation
instructions and an OTM administrator completes the manual step. This keeps onboarding centrally
operable and makes the human wait clear, but requires an approved bootstrap identity, email handling
and MFA procedure. It does not decide when the engineer receives full admin access.
B) Tenancy owner: The engineer receives activation instructions and performs the step. This uses
their own initial identity, but onboarding waits on an external person and requires a secure handoff
before the tool can complete provisioning. The engineer's eventual full administration is unchanged.
Options differ in operating model, not completeness; no coverage score.
Net: Choose who owns the manual activation step; credential details and owner-access timing follow separately.

State: accepted with refinement, 20 October 2026. Actual answer: A. Use the authenticated
initiating OTM administrator's name/email, not a generic shared activation identity. That person
manually activates the child and establishes temporary SDK access. The app then creates the owner,
permanent operational identities and baseline, and removes the temporary child-local human
administrator and bootstrap access after replacement access is verified. Keep the initiating actor
in immutable history. A requested name/home region is needed before the provider create request;
resumed provisioning discovers the actual name/region from OCI and preserves requested values separately;
provide only the public bootstrap key to the person. Exact grants, owner handoff and emergency
MFA/recovery mechanisms require C4 qualification; D18 does not approve those new alternatives.
History: this refines option A's generic designated-identity wording. D1–D17 remain accepted.
Documentation findings and the proposed safe sequence: [chapter04](../engineering-design/04-identity-and-access.md#administrator-led-creation-d18).


### D19: routine support versus independent emergency recovery

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

Finding: C4-01; high recovery impact; high confidence. An on-demand human account can only be
created while the automation identity and its required privileges still work. Owners retain full
administration and can remove those privileges. This is a dependency problem, not an SDK feature gap.
Evidence: [chapter04 research and qualifications](../engineering-design/04-identity-and-access.md#support-and-emergency-access-proposal-d19).

| Choice | Current accepted baseline | A: hybrid support and recovery | B: recovery account only |
|---|---|---|---|
| Routine organizational support | Disclose shared emergency password | Named, temporary MFA-protected human access created by working automation | Continue using existing emergency disclosure flow |
| Independent last-resort account | Persistent local recovery identity | Retained with an out-of-band access procedure | Retained with an out-of-band access procedure |
| Automation identity | Persistent API administration | Unchanged | Unchanged |
| Engineer owner | Full administration | Unchanged | Unchanged |
| Added workflow | None yet implemented | Named grant, enrollment, expiry/revocation and cleanup | No named support grant workflow |
| Emergency MFA choice | Narrow exemption previously selected | Separate decision, not approved by this choice | Separate decision, not approved by this choice |
| Four-hour limit | Rotation scheduled; session cutoff unqualified | Grant cleanup and recovery rotation require separate verified contracts | Existing rotation contract still needs qualification |

Question D19: Should routine support use named on-demand accounts, while retaining an independent
emergency recovery account? Recommendation: A. This reduces routine sharing without making recovery
depend on the automation identity it may need to repair.
A) Hybrid (recommended): add named, time-limited support access, and keep an independent emergency
account for loss of automation or the application. This adds an enrollment/cleanup workflow and more
qualification work, but separates everyday support from last-resort recovery.
B) Existing recovery flow only: keep the persistent emergency account and audited password-disclosure
workflow for support as well. This is simpler, but routine support continues to use a shared identity.
Options differ in kind, not coverage; no completeness score. No delivery-time estimate established.
Net: choose the support/recovery operating model; the emergency MFA method remains a separate decision.
State: accepted, 20 October 2026. Actual answer: A. Named on-demand support plus independent
persistent emergency recovery. Owner full administration and persistent automation are unchanged.
The user explicitly requires further work on MFA for the non-named custodial recovery account.
Its factor choice, enrollment, custody, backup/recovery and deployment feasibility remain open;
this answer does not adopt an MFA mechanism or confirm a hard four-hour session cutoff.


### D18 refinement: requested name versus actual tenancy identity

Accepted requirement, 20 October 2026: a name selected before activation may not be the final
OCI name. Record and display the actual OCI tenancy identity after handoff; do not require the
administrator to retype its name. The user reports global name collisions during activation;
qualify exactly when the deployed creation path validates/reselects the name rather than claiming
that every activation flow supports renaming.

The create API still requires a requested name and home region. Retain these provisional inputs
for app-initiated creation. Given the supplied/resolved tenancy OCID, bootstrap access resolves
actual name/home region and domain context, and the parent context verifies real child membership.
Requested values and provider attempt history are retained separately from verified current values.
A name difference alone does not authorize a second create, a region change or an OCID substitution.
Wrong parent, protected/already-managed targets or a changed target OCID require a blocked/reviewed
handoff before configuration writes. Confirmed name rejection can request a new name and produce
an audited new attempt; an uncertain create must reconcile first.

Alternative noted, not selected: omit initial name/region only if initial OCI creation is manual
outside OTM, or another qualified provider interface supplies those required values. This changes
the automatic create boundary and is not implied by accepting discovery at resume.
See [discovery and collision design](../engineering-design/04-identity-and-access.md#requested-name-and-verified-tenancy-identity).


### D20: owner first sign-in versus verified tool setup

Finding: C1-02; medium workflow impact; high confidence. Earlier text says owner handoff must be
ready without distinguishing configured, MFA-enforced access from a human completing first login.
Evidence: [onboarding readiness contract](../engineering-design/07-onboarding-journeys.md#readiness-decision-d20-owner-first-sign-in).
Runtime evidence: current prototype simulates success and has no OCI human-login evidence.

| Boundary | A: separate owner sign-in | B: wait for owner sign-in |
|---|---|---|
| Owner full administration and enforced MFA | Required | Required |
| Independent operational recovery and all mandatory setup checks | Required | Required |
| Onboarding completion | After tool configuration/verification and temporary cleanup | Same checks plus confirmed first owner login/MFA |
| Owner human wait | Separate explicit unconfirmed-access status | Operation stays Waiting for owner |
| Proof | Invitation is not proof of delivery/enrollment; show only observed or attributed facts | Same evidence limits; no fabricated API signal |
| Other V1 constraints | Admin-only app; no owner approval added | Admin-only app; no owner approval added |

Question D20: Must onboarding wait for the engineer's first sign-in? Recommendation: A, finish tool
setup when mandatory controls are verified, while separately showing whether owner sign-in is confirmed.
This keeps a provisioning workflow from waiting on an engineer but does not claim the engineer used it.
A) Separate statuses (recommended): complete OTM setup after verified controls, owner grants and
cleanup; show owner sign-in as unconfirmed until supported evidence exists. This avoids a human
bottleneck and retains honest visibility, but administrators must distinguish the two statuses.
B) Wait for first sign-in: keep onboarding open until the engineer completes MFA/first login and
that is verified. This makes completion include human access, but operations may remain open for days.
Options differ in operating model, not coverage; no completeness score or unmeasured delivery estimate.
Net: decide whether first human use blocks setup completion or appears as a separate access status.
State: accepted, 20 October 2026. Actual answer: A. Complete OTM onboarding after mandatory
configuration, owner grants/MFA enforcement, independent recovery and temporary-access cleanup are
verified. Track first owner sign-in independently; missing/unsupported evidence stays unconfirmed.
No first-login confirmation/approval is required to complete tool setup. Owner full administration,
MFA requirements and the unresolved custodial recovery qualification remain unchanged.


### D21: access for members of a shared tenancy

Finding: C1-03; high effect on privilege/cleanup; high confidence. The prototype tracks shared
membership but has no OCI principal, compartment or IAM changes. Owner full administration is
accepted; that does not specify privileges for additional shared-tenancy members.
Evidence: [shared journey/access draft](../engineering-design/01-domain-and-journeys.md#shared-tenancy-access-design-draft).

| Boundary | A: explicit access profile | B: all members administer tenancy | C: membership tracking only |
|---|---|---|---|
| Owner | Full administration | Full administration | Full administration unchanged |
| Additional member access | Administrator chooses compartment-scoped or full tenancy administrator | Always full tenancy administrator | OTM records association; external access is manual |
| Compartment-scoped option | Proposed default; exact supported service scope must be qualified | Not part of this rule | No automated provisioning |
| Preview | Identity, permissions, scope, shared objects and cleanup effects | Explicit warning that member can administer other members' resources/access | Explicitly says no OCI grant/revocation performed |
| Removal | Revoke exact managed grant; distinct identity/resource checks | Remove managed administrator grant; other access may remain | Manual access cleanup evidence required |
| Engineering cost | Profile schema, scope and handler/verification cases | Simpler grant path, broad access and difficult total revocation | Smallest provider scope; more administrator work |

Question D21: What access should Add to shared tenancy create? Recommendation: A, explicitly
select a profile, with compartment-scoped access as the proposed default and full administration
available when deliberately chosen. Owner rights remain unchanged and the app remains admin-only.
A) Explicit profiles (recommended): choose scoped member access or tenancy administrator per
association. This supports different shared workloads and makes intended access/cleanup visible,
but requires qualifying and maintaining more than one grant profile.
B) All members are tenancy administrators: every added member gets full administration. This is
simple and flexible for demos, but members can change other people's resources, identities and controls.
C) Track membership only: retain associations but leave shared-user/access setup and cleanup manual
for V1. This keeps initial automation small, but the UI must not report OCI access granted or revoked.
Options differ in access/operating model, not completeness; no coverage score or delivery estimate.
Net: select shared-member access behavior; the owner always retains full administration.
State: accepted, 20 October 2026. Actual answer: A. Administrators explicitly select a shared-member
access profile. Compartment-scoped access is the default; full tenancy administration is an explicit
alternative. Owner full administration and admin-only application access are unchanged. Exact scopes,
service dependencies, identity bindings and verification remain C3/C4 qualification work. No prototype
IAM implementation or production profile schema is implied by this decision.


### D22: previous owner's access after a shared ownership transfer

Finding: C1-04; high offboarding/privilege impact; high confidence. Establishing replacement-owner
administration does not specify whether the previous owner remains a member, keeps administration
or leaves the shared tenancy. The prototype transfer retires the old ownership relationship but
has no OCI grants to revoke. Preserve that distinction when designing production behavior.
Evidence: [transfer flow and failure boundaries](../engineering-design/01-domain-and-journeys.md#transfer-shared-ownership).

| Boundary | A: explicit previous-owner disposition | B: always remove | C: retain full administration |
|---|---|---|---|
| Replacement owner | Verify full administration before changing accountability | Same | Same |
| Previous owner | Select remove access or remain member with D21 profile | Remove managed owner access/relationship | Remains member with full administration |
| Offboarding default | Remove; retaining access must be explicitly selected and remains an outstanding/kept association | Remove | Keep unless a separate removal operation succeeds |
| Standalone transfer | Explicit selection; no implicit keep/remove | Removal is automatic consequence of confirmed transfer | Retention is automatic consequence of confirmed transfer |
| Resources and other identities | Not automatically deleted | Not automatically deleted | Not automatically deleted |
| Partial cleanup | New accountability can publish; old access cleanup remains visible and offboarding incomplete | Same | No revocation implied by transfer |
| Residual access | Show unmanaged/other grants; never equate one grant removal with universal revocation | Same | Full old-owner privileges are intentional |

Question D22: After transferring shared ownership, what happens to the previous owner's access?
Recommendation: A, make the disposition explicit in the transfer preview and default to removal
when the transfer is part of offboarding. This supports both departures and a continuing team member.
A) Explicit disposition (recommended): remove the previous owner's access, or keep them as a member
with a selected scoped/admin profile. This makes the resulting permissions visible and reuses D21,
but adds a required choice to the transfer form. Offboarding defaults to Remove.
B) Always remove: transferring ownership also removes the previous owner's managed access. This is
simple for departures, but a continuing colleague may need to be added back as a member.
C) Always retain full administration: transfer changes accountable ownership and keeps the previous
owner as an administrator member. This avoids interrupting ongoing work, but a departure needs a
separate removal and old privileges persist until that succeeds.
Options differ in access/operating model, not completeness; no coverage score or delivery estimate.
Net: choose the previous owner's post-transfer relationship; replacement-owner access is verified first.
State: accepted, 20 October 2026. Actual answer: A. Every shared ownership transfer explicitly
selects the previous owner's disposition: Remove access or Remain a member with a selected D21
profile. Offboarding defaults to Remove; retaining an association is an explicit choice. Replacement
administration must be verified before old grants are removed; incomplete cleanup remains visible
and does not complete offboarding. Resources are not deleted by ownership transfer.


### D23: shared-member compartment/resource cleanup in V1

Historical review brief below; its proposed resource deletion/verification was superseded by the
user's custom answer. The accepted contract at the end of this entry is authoritative.

Finding: C1-05; meaningful implementation scope; high confidence. Removing membership/access is
different from disposing of workloads. The original shared-tenancy use case includes member
compartment cleanup, but its automation was explicitly left light in the initial design. OCI
requires an empty compartment before deletion; deleting a non-empty scope needs service-specific
resource/dependency handling. Evidence: [removal flow](../engineering-design/01-domain-and-journeys.md#remove-member--offboard)
and [Oracle compartment deletion](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_delete_a_compartment.htm).

Common requirement: explicitly choose Keep/reassign responsibility or Clean up the selected scope;
never infer resource deletion from removing a person or transferring tenancy ownership. Full-admin
membership does not prove that all tenancy resources belong to that member. The shared tenancy,
other members, protected identities and unrelated resources remain outside this cleanup intent.

| Boundary | A: manual workload cleanup in V1 | B: supported automated workload cleanup in V1 |
|---|---|---|
| Access removal | Automated scoped grant/user handling with verification | Same |
| Keep resources | Explicit choice plus continuing responsible person; no claimed resource move | Same |
| Clean up non-empty scope | Manual wait/checklist; inspect/recheck after administrator cleanup | Explicit preview of supported resources/dependencies, then automated handlers |
| Delete empty compartment | Only after explicit choice, ownership/scope checks and qualified empty verification | Same |
| Unsupported or uncertain resources | Manual cleanup/review; no empty/success inference from missing visibility | Same fallback; never a generic blind purge |
| Completion | Required cleanup verified or explicitly retained/reassigned; no early directory removal | Same |
| Added engineering scope | Compartment binding/checks and resumable manual step | Also resource inventory, per-service retirement, dependency order and partial-recovery tests |

Question D23: How much workload cleanup should shared-member offboarding automate in V1?
Recommendation: A, automate access changes and safe empty-compartment deletion, while guiding and
verifying manual cleanup of non-empty compartments. This retains the required flow without making
V1 a general OCI resource-deletion engine.
A) Guided manual workload cleanup (recommended): administrators explicitly keep/reassign or clean
up resources; OTM removes access, tracks any required manual step and verifies the selected result.
OTM can delete an explicitly selected, verified-empty managed compartment. Non-empty workloads are
cleaned outside OTM, adding manual work but a smaller qualified provider surface.
B) Automate supported workload cleanup: add reviewed resource/dependency handlers for a defined V1
service set, with inventory, destructive preview, verification and resumable partial failures.
Unsupported or unverified resources still require manual cleanup; this extends the automation/test scope.
Options differ in automation/operating model, not completeness; no coverage score or delivery estimate.
Net: choose whether non-empty workload cleanup is a guided manual stage or a supported automated V1 stage.
State: accepted custom answer, 20 October 2026. Actual answer: automate removal of the member's
child-tenancy user ID and group memberships; guide the administrator to direct the shared-tenancy
owner to manually clean resources in the specified compartment. **No automated resource or
compartment cleanup/deletion in V1, including empty compartments.** This supersedes both original
options' proposed empty-compartment automation and resource-cleanup verification/completion gate.

V1 completion verifies the selected identity and membership removal, then retires that association.
Manual workload cleanup is owner follow-up guidance, not an OTM-verified result or a gate on completed
membership removal/directory offboarding. The tenancy owner remains accountable for retained
resources/cost. Display the owner and known compartment name/OCID; missing scope is shown honestly,
not replaced with an inferred whole-tenancy target. No automatic cleanup message is sent by this
choice; the administrator receives guidance to direct the owner. Future automation remains V2+.

Safety qualification: only the inspected, bound child-local personal user may be deleted. Shared,
protected operational, upstream corporate identities or a user still required by another obligation
must not be deleted blindly. Ambiguous/unsupported deletion remains blocked/manual and cannot be
reported as successful user removal. Removing access does not prove every session or independently
created identity has been revoked. Existing independent-recovery/MFA requirements remain unchanged.


### D24: providing a compartment for scoped shared-member access

Finding: C1-06; medium onboarding scope; high confidence. D21 selects compartment-scoped access
by default, but no decision specifies who creates the target compartment. D23 forbids automatic
resource/compartment cleanup, not provisioning. The initial scope must be explicit and bound by OCID.
Evidence: [shared profile contract](../engineering-design/01-domain-and-journeys.md#shared-member-profile-contract-d21-accepted)
and [Oracle compartment creation](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm).

| Boundary | A: create or select | B: select existing only |
|---|---|---|
| Scoped-member onboarding | Default to create a compartment; explicit select-existing alternative | Administrator selects an existing compartment; creates it externally if needed |
| Preview | Parent, proposed name/description and scope, or inspected existing OCID | Inspected existing name/OCID and scope |
| OCI changes | Qualified compartment creation plus identity/grants; no workload creation | Identity/grants only |
| Binding | Record actual OCID and whether created or adopted; do not adopt by name | Same explicit adoption checks |
| Failures | Name conflict, permission loss, uncertain create and partial setup require reconciliation | Missing/inaccessible target blocks grants; no implicit fallback to root/admin |
| Offboarding | D23 owner-directed manual cleanup; no automatic compartment deletion | Same |

Question D24: For scoped shared-member access, should OTM create the compartment or require one
that already exists? Recommendation: A, offer Create new by default and Select existing explicitly.
It completes member onboarding without an external setup dependency while preserving existing layouts.
A) Create or select (recommended): show compartment creation/selection in preview, create if selected,
then verify the returned scope before granting access. It adds a small qualified provisioning step,
including partial/uncertain failure handling; offboarding still leaves the compartment untouched.
B) Existing only: the administrator supplies an existing compartment, which OTM inspects/binds before
granting access. This reduces V1 provisioning scope but requires external setup for a new compartment.
Options differ in provisioning/operating model, not completeness; no coverage score or delivery estimate.
Net: decide whether new compartment provisioning is part of member onboarding; cleanup remains manual.
State: accepted with refinement, 20 October 2026. Actual answer: A. Default to Create new with
an explicit Select existing alternative. For creation, the administrator selects the parent from
the existing compartment hierarchy of the target shared tenancy. Do not hardcode a parent or assume
the tenancy root. Show full paths and bind by OCID; recheck target tenancy, parent lifecycle and
creation permission before execution. New-compartment creation does not grant the member access to
its parent/siblings. D23 still leaves all compartments/workloads unchanged during offboarding.


### D25: initiation of multi-tenancy offboarding

Finding: C1-07; high deletion-authorization impact; high confidence. The spec says no bulk deletion,
while accepted person-level offboarding requires a complete plan and permits multiple owned tenancies.
Evidence: [spec §6.3](../product/oci-tenancy-manager-spec.md#63-delete) and
[offboarding preview](../engineering-design/01-domain-and-journeys.md#person-level-offboarding-preview-and-d25-boundary).
Runtime evidence: prototype simulates local association changes, not actual deletion authorization.

| Boundary | A: one complete person plan | B: individual deletion starts |
|---|---|---|
| Preview | Every association and exact selected target/disposition | Same complete inventory/plan |
| Initiation | One confirmation can accept selected scoped actions, including multiple owned-tenancy deletions | Each tenancy deletion needs its own explicit Start; plan links their operations |
| Deletion guards/warnings | Per target at acceptance and execution; no relaxation or extra approver | Same |
| Scope | One selected person's associations; no fleet-wide arbitrary bulk-delete endpoint | One tenancy per deletion initiation |
| Partial results | Linked operations retain independent verified/failed/unknown outcomes | Same linked progress; more administrator interactions |
| Completion | Required effects verified, no retained links; D23 resource guidance does not block | Same |

Question D25: Can one offboarding confirmation start all selected actions for that person, including
multiple owned-tenancy deletions? Recommendation: A, one complete preview/confirmation with exact
per-target guards and independent operations. This avoids a fragmented workflow without adding a
fleet bulk-delete feature, but explicitly refines the earlier no-bulk-deletion wording.
A) One person plan (recommended): review every association and confirm the complete selected plan.
Each target retains its own execution guards, warnings and result; failures do not hide completed work.
This is convenient but one confirmation can authorize more than one tenancy deletion.
B) Separate deletion starts: review the complete plan, then individually confirm/start each tenancy
deletion. Member removals/transfers can still be linked, but deleting several owned tenancies requires
more interactions. This preserves a strict one-tenancy-per-deletion-initiation boundary.
Options differ in authorization/operating model, not completeness; no coverage score or delivery estimate.
Net: choose the initiation boundary; all target safeguards and verified-completion rules remain required.
State: accepted A, 20 October 2026. Actual answer: "a". One complete person-plan confirmation
may initiate all selected scoped actions, including multiple individually owned-tenancy deletions.
Each target retains the existing warnings, current registration/parent/protected-target/eligibility
and permission checks, independent operation/results and scoped resume. No additional approver,
Reason field or fleet-wide arbitrary bulk deletion is introduced. Acceptance is not verified
completion. D26 defines confirmed provider initiation as the required deletion effect.



### D26: deletion scope ends at confirmed termination initiation

State: accepted custom direction, 20 October 2026. Actual user instruction:
"We don't need to worry about the official termination after 30 days. Our job is just to initiate termination."
This supersedes the unaccepted draft alternatives requiring suspension verification or finality monitoring.

OTM's deletion workflow completes when the qualified OCI response/evidence confirms termination
initiation for the intended tenancy. Local operation/job acceptance alone is insufficient. Persist
provider confirmation/correlation and the result; retire the deletion association then. If that is
the last required association and no links are kept, complete the person's managed-directory removal.
Other selected member-removal/transfer operations still need their own verified results.

Label the result **Termination initiated**, never **Permanently deleted**. Retain tenancy and audit
history with last-known owner/OCID. No 30-day wait, scheduled final-deletion monitoring or finality
state machine is required. Timeout/lost response stays unverified until reconciled; rejection/failure
remains actionable in Operations. Do not issue a duplicate termination blindly. Existing protected
parent/child/registration/eligibility guards and imported-origin feasibility constraints remain.
See [the confirmed-initiation contract](../engineering-design/01-domain-and-journeys.md#deletion-completion-d26-accepted).



### D27: identity-domain scope confirmed

State: accepted clarification, 20 October 2026. Actual answer: "All use identity domains".
V1 uses an identity-domain user/group/credential adapter; no standalone legacy-IAM identity
implementation or parallel legacy simulator is required. Keep IAM infrastructure APIs for metadata,
domain discovery, compartments and root policies. Import must still inspect actual domain/endpoint,
OCID-to-SCIM bindings and permission/capability requirements. No assumption that every tenancy uses
Default, shares a domain, or has identical federation/MFA follows from this answer. Unsupported
identity models are reported and blocked with no automatic fallback. The inspected 91-call source
inventory remains evidence, with per-call scope labels distinguishing planned, conditional bridge
and reference-only legacy calls. Custodial MFA and password/session qualification remain open.



### D28: removing a managed configuration item

Finding: C3-01; high configuration/access impact; confidence9/10 that a product boundary is needed.
[Chapter03](../engineering-design/03-templates-and-drift.md#extensible-item-contract) explicitly leaves
apply/update/retire and remove/unset semantics to define; D6 binds dedicated managed objects but
neither that binding nor a conditional SDK delete method approves automatic removal.
The following question records the original alternatives; accepted A is recorded below. It changes
the design boundary, not the working prototype.

Question: when the resolved desired configuration explicitly removes a whole managed item, may
an explicitly confirmed rollout delete its tool-managed OCI object? Example: baseline v1 creates a
quota and baseline v2 removes it, with no remaining assignment requiring it. This does not decide
field-level unset/inherit semantics or imply that deleting an override deletes a baseline object. Publishingv2 still changes nothing under D1; the question concerns a later reviewed rollout.

| Boundary | A: previewed managed-object removal | B: report manual removal required |
|---|---|---|
| Rollout diff | Show exact owned policy/quota/budget object and Remove action | Show retained object and manual-removal requirement |
| Execution | After explicit rollout confirmation, remove only eligible bound objects in dependency-safe order and verify | Tool does not delete the object through baseline removal; admin cleans it outside the tool and verifies |
| Unknown/partial effects | Retain bindings/history and reconcile; no blind retry or delete/recreate repair | Preserve observation/history until manual outcome is verified |
| Mandatory safeguards | Never remove required automation/recovery or active-owner/member access by omission; preserve unrelated/shared objects; protected/locked scope blocks | Same protected/unrelated-object rules |

A (recommended) supports complete automated configuration lifecycle within a reviewed rollout.
This is not automatic deletion on publication/feed processing. Identity/group changes with active
association obligations route through their dedicated workflows; generic omission cannot bypass
D18–D27. D23 still forbids workload/compartment cleanup, and D26 tenancy termination remains separate.
B keeps removals manual in V1; stale managed objects remain visible with explicit cleanup requirements,
rather than disappearing from governance because a template stopped mentioning them.
Completeness: options differ in who performs removal, not in whether it must be accounted for.
State: accepted A, 20 October 2026. Actual answer: "a". A confirmed rollout may delete obsolete,
eligible explicitly bound tool-managed configuration objects and verify removal. Publication/feed
processing alone still performs no writes. Apply dependency, live binding/permission and ownership
checks; preserve unrelated/shared objects and protect mandatory automation/recovery and active
owner/member access. Whole-item removal is distinct from clearing an inherited field override.
No resource/compartment cleanup or automatic tenancy termination is added. Overlay add/exclude
permissions are a separate unresolved C3 choice, not implicitly approved by this answer.



### D29: historical numeric-limit model, superseded by D30

State: accepted custom limited approach, 20 October 2026. Actual answer: "lets go with the limited v1
approach. I can see some tenancies, like shared tenancies, needing larger budgets than others".
This was accepted on20 October and is now superseded by D30 below. Its no-policy-override and numeric-rule-only restrictions no longer describe V1.

One baseline lineage has immutable versions and one current-for-new published version. New creation
and import pin that version at operation acceptance; in-flight work never switches to latest.
Existing tenancies remain assigned until a previewed, confirmed bulk/single update. Version age alone
is Update available, not configuration drift. This refines D1's earlier manual new-version selection.

Baseline categories: root policies, root defined-tag defaults, budget and quota rules. Only budget
amount and supported named quota-rule numeric limit can be overridden per tenancy. No tag/policy
changes or item additions/exclusions through overrides in V1. A shared tenancy can explicitly keep
budget 500 while standard defaults move 200→300. Currency/period and quota service/metric/unit/scope
are fixed; compatible values persist through a baseline update. Removed/redefined overridden settings
block the affected target before writes until the override is cleared/replaced and preview refreshed.

Resolve target baseline plus values first, then apply a guarded diff; never strip all old controls
before applying the new baseline. D28 eligible removals remain part of confirmed baseline updates.
Identity/bootstrap/recovery access stays in its separately defined mandatory onboarding flow.
General/additive overrides are deferred. No runtime app/DB change is introduced by this acceptance.

The revised [chapter03](../engineering-design/03-templates-and-drift.md), [numeric examples](../contracts/configuration-examples/grant-overlay.json)
and [Configuration views](../walkthroughs/configuration-walkthrough.html) now follow
this model. The former general-overlay walkthrough/fixtures/checker are retained as
superseded history (private historical evidence; not distributed).
Current bounded design checks cover 9 positive, 33 negative and 8 invariants; production schemas,
pointer/rollout/drift execution and real OCI qualification remain open. C3 is not complete.



### D30: accepted complete managed objects and full-list overrides

State: accepted direct user requirements, 21 October 2026. Supersedes D29's numeric quota editor and
no-policy-override restriction. One root OTM policy with administrator-authored statement list;
one root OTM quota policy with administrator-authored statement list; one root monthly budget with
no alert rules; one root OTM namespace with defined keys/static values and root default per key.
Policy/quota overrides copy the assigned baseline list, then replace that complete category's list
inside the same bound object. Budget amount alone is overridden; tag overrides remain outside V1.

The user also explicitly selected required review when a new baseline changes an overridden
policy/quota: compare old baseline/new baseline/full override, then keep/edit/clear before updating
that target. No automatic merge/discard or append. Review is tied to exact content/revisions. Other
eligible targets could proceed under this earlier boundary; D31 below supersedes that pre-start
behavior and requires all reviews resolved. Current-for-new version capture and existing explicit bulk updates
remain accepted; an older assigned version alone is not drift.

[Chapter03](../engineering-design/03-templates-and-drift.md) specifies root bindings, in-place statement replacement,
namespace/key/default dependencies and daily comparisons. Preserve mandatory access through a single
coordinated root policy binding; no separate hidden OTM policies per workflow/profile. Exact access
composition and provider qualification remain open C3/C4 work. Child-root budget placement is required
and must be qualified, not silently replaced by a parent-owned budget. Defaults do not backfill tags.

The [walkthrough](../walkthroughs/configuration-walkthrough.html),
[full-list fixtures](../contracts/configuration-examples/grant-overlay.json) and
bounded check receipt (private historical evidence; not distributed)
now follow D30. Prior D29 artifacts are retained as history (private historical evidence; not distributed).
The reference checker covers9 positive,34 negative and7 invariants without OCI calls; no production
resolver/rollout/drift engine or database migration is introduced. C3 remains in progress.

Current D30 checkpoint review (private historical evidence; not distributed)
records corrected scope references, bounded evidence and remaining qualification gaps.



### D31: connected publication flow and all conflicts before bulk start

State: accepted direct user instruction,21 October2026. The baseline walkthrough must show the actual
button journey from creation/publication to Update existing tenancies, not depend on a screen selector.
Bulk review shows only ready count plus conflict exceptions. Click a tenancy to compare old baseline,
new baseline and override, then choose Use new baseline or Keep override and return. No inline edit
required for conflict resolution; regular override editing remains a separate assigned-version flow.

**All reviews must resolve before the bulk update starts.** This supersedes D30's early ready-subset
execution. Decisions stage the proposed plan only, with no active assignment/override changes or OCI
writes. Counts are per tenancy; several block conflicts do not double-count a tenancy. The start
button and server gate require zero unresolved reviews and current complete plan/revision evidence.
No skipping/deselecting conflicts to start a subset. After acceptance, independent target progress,
provider failures/unknown outcomes/retries remain; this is not atomic fleet-wide OCI execution.

[Chapter03](../engineering-design/03-templates-and-drift.md#d31-baseline-publication-to-existing-tenancy-update) defines the
connected screens, stage boundary and stale-review handling. The [walkthrough](../walkthroughs/configuration-walkthrough.html)
implements the journey in memory with explicit simulated publication/queueing; it does not change
the organization app/database or create real OCI operations. The earlier D30 artifact is retained as
history (private historical evidence; not distributed).

D31 design review (private historical evidence; not distributed)
and batch-gate receipt (private historical evidence; not distributed)
retain the bounded design evidence.

The D31 UI review (private historical evidence; not distributed)
records the actual connected journey and18 responsive checks, with screen captures linked there.


### D32: baseline history, override entry points and focused issue queues

State: accepted direct user instruction, 21 October 2026. Configuration opens on a tabular published
baseline history with **New baseline** and **Create tenancy override** actions. Historical version
views are read-only and do not change current-for-new, assignments or bulk targets. Override creation
starts from Configuration or tenancy inventory/details, not the baseline editor; it uses the
selected tenancy's assigned version. The connected D31 publication/bulk journey remains unchanged.

Organization Exceptions belongs under Employees. Configuration → Drift restores an exception-only
queue for confirmed Missing/Different observations. Healthy objects, unable-to-verify checks, older
baseline versions and pending bulk conflict reviews are distinct. Tenancy table exception icons
open an exact issue, or a tenancy-filtered list when several issues exist; check/access issues remain
reachable without inflating the confirmed-drift count. Detail pages expose expected/observed facts,
observation freshness and appropriate guarded repair/manual recovery. Queued repair is not verified
resolution. Deep links preserve identity and unknown targets show a visible error.

[Chapter03](../engineering-design/03-templates-and-drift.md#configuration-navigation-and-issue-resolution-d32) and
[specification screens](../product/oci-tenancy-manager-spec.md#screens) record the navigation contract. The
[configuration walkthrough](../walkthroughs/configuration-walkthrough.html)
implements illustrative navigation in memory only; no local application, database or OCI changes
are introduced. The prior D31 walkthrough is retained as
history (private historical evidence; not distributed).
C3 remains in progress; navigation approval does not qualify provider capabilities or production
execution contracts.

D32 UI review (private historical evidence; not distributed) and
browser receipt (private historical evidence; not distributed)
record the connected navigation, retained bulk gate and responsive evidence. The documentation
review found no material inconsistency across chapter03, the specification and this ledger.


### D33: Organization and Organization drift terminology

Accepted direct user instruction, 21 October 2026. Rename the Employees navigation area to
**Organization** and its review submenu to **Organization drift**, matching **Configuration drift**.
Update headings, breadcrumbs, links, back actions and empty-state language consistently. This changes
navigation terminology, not the existing actionable/informational review behavior. Configuration drift
remains a separate queue for confirmed OCI configuration differences. The walkthrough uses canonical
`#organization` / `#organization-drift` routes and preserves old route aliases. The local organization
application remains unchanged in this design checkpoint. The previous D32 walkthrough is preserved
as history (private historical evidence; not distributed).

D33 UI review (private historical evidence; not distributed)
verified the renamed routes, legacy aliases, labels and navigation at desktop and mobile widths.


### D34: approved prototype page authority and shared design menu

Accepted direct user clarification, 21 October 2026. The working organization prototype's directory
and review layouts remain correct and authoritative. Configuration walkthrough Organization and
Organization drift bodies are placeholders, not alternative approved designs. Make those menu
entries non-clickable to avoid implying otherwise; preserve compatibility direct routes with an
explicit placeholder only, no fake employee list or misleading empty queue.

Back-propagate the current menu structure into the earlier onboarding and operations walkthroughs.
Use one small shared design menu manifest/renderer and stylesheet for current walkthroughs, keeping
labels, order, nested grouping, context and responsive treatment consistent. Existing workflow pages
and gates remain intact. Preserve historical checkpoints and the working application's UI/data.
The [screen authority map](../ui-screen-authority.md), [UI baseline](../../DESIGN.md) and
[review policy](../ui-ux-review-policy.md) establish how future changes avoid conflicting designs.

D34 follow-up: retain **Assigned baseline** and a clickable **Configuration issues** indicator as
explicit additions to the approved tenancy inventory. Keep its existing fields, counts and controls;
assignment does not imply verified application, and unknown checks are distinct from confirmed drift.
This is a design requirement, not a claim that live OCI data exists in the prototype.

D34 validation: the UI review (private historical evidence; not distributed)
and browser receipt (private historical evidence; not distributed)
record the common menu, non-interactive organization context, retained tenancy columns/issue links,
query-preserving local navigation and representative workflow checks. Root inspected the desktop
and mobile captures; the documentation reviewer found no material source-authority inconsistency.


## D35: visible protected required access in the single policy

Accepted 21 October 2026, option A. Each OTM policy combines administrator-authored baseline/override
statements and visible read-only generated required-access statements. An override replaces the
authored block only. The same bound OCI policy object receives the combined list; no second policy
or hidden grant is created. Owner OCI administration is unchanged. Quota/budget/tag semantics and
D31’s all-conflict batch gate remain binding.

The immutable tenancy configuration adds `required_policy_manifest`,
`required_policy_manifest_hash` and `policy_render_contract_version`. The generated statement
provenance/resolved arrays live in typed immutable rendering evidence. Root-policy requirement
changes create a new local configuration revision using the same baseline/overrides; no new global
baseline is published. [The exact field contract](../engineering-design/10-configuration-data-model.md#d35-required-policy-manifest-and-rendered-evidence)
and [access behavior](../engineering-design/12-access-health-and-repair.md#required-grant-composition-d35-a-accepted)
govern the editor, override/conflict preview, operation payload and complete policy drift comparison.

Global baseline screens show per-tenancy required examples; current tenant screens show the combined
list. Historical baseline values remain authored-only. Template/profile updates are explicitly pinned,
not live-library rewrites. No prototype/database/provider change occurs in this design checkpoint.

D35 validation: the UI review (private historical evidence; not distributed)
records 18 targeted checks and 32 representative layouts, with a bounded later generated-context
staleness/refresh recheck. Field audit and regenerated ER include all three new manifest/renderer
columns and resolved statement provenance. `scripts/check_design_docs.py`, JS syntax, inline docs
and Ruff pass. The older D30 authoring-phase checker still passes 9 positive/34 negative/7 invariant
cases; those are structural examples, not a production composer or executed DB/OCI tests.

During this update an edit accidentally copied the hub into the product spec. It was restored from
the SHA-verified source checkpoint plus exact subsequent task-local edits. All 57 prior criteria
remain, with AC58 added for D35; the documentation reviewer verified restoration and hashes.
A retained header/section/criteria guard rejects this overwrite in an in-memory regression probe.
The recovery receipt (private historical evidence; not distributed)
records provenance. A source-only D35 artifact checkpoint is saved under
`.local-dev/checkpoints/d35-design-2026-10-21/`; it is not a database or full-project backup.


## D36: local human console accounts

Confirmed 21 October 2026, option A. Human console users in child tenancies use local identity-domain
accounts. OTM administrator SSO stays separate; V1 does not depend on child federation. This does
not select an MFA exemption for the custodial recovery account.

[Chapter13](../engineering-design/13-local-support-and-emergency-access.md) and the [human access walkthrough](../walkthroughs/human-access-walkthrough.html#access-ready)
now develop named activation/MFA/grants/cleanup and separate emergency review/disclosure/uncertain
rotation states. All screen fields map to named grant/assignment/binding/credential/observation
records or transient/secret-response boundaries. D37 now fixes named support cleanup four hours from acceptance, with no extensions or early-end control; the
existing emergency four-hour first-disclosure rotation rule does not change. No prototype data,
provider accounts or credentials are created. C4 remains in progress.


D36 design validation: the human access UI review (private historical evidence; not distributed)
records 28 interaction checks and 28 responsive combinations. Field review closed the domain
label/console-destination gap: the separately verified `domain_metadata` properties cannot reuse the
API/SCIM endpoint as a login URL. Chapter13 maps every screen value/control to explicit fields or
transient/nonsecret/secret-response boundaries. The proposed core ER exports are regenerated.
The retained design checker validates 18 documents, 13 configuration fields, five human-access
fields and the 28-table proposed inventory; inline documentation, Ruff and JS syntax pass. These
are static design checks, not executed provider permissions, MFA, cleanup, credential or DB tests.
A verified source-only checkpoint is saved at `.local-dev/checkpoints/d36-design-2026-10-21/`;
it excludes runtime state, live data and secrets.



## D37: fixed named-support deadline and mandatory cleanup

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

Accepted 24 October 2026, option A. Named support has a fixed four-hour deadline from request
acceptance, including activation/MFA setup. Cleanup is mandatory even for abandoned setup. No
extensions and no user-facing End access/session early action. The existing grant fields capture
14400 seconds, request_acceptance and accepted_at+4h; no new table/column is needed. Failed/unknown
cleanup remains visible and blocks replacement grants until verified. Chapter13 and the walkthrough
are updated together. The separate independent recovery account/credential exists to handle loss of
automation authority; the user is revisiting whether its in-app disclosure UI is needed. D37 does
not remove D19 recovery or select custodial MFA. No prototype data, account or credential changed.



## D38: independent recovery retained; app-style walkthroughs

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

Accepted 24 October 2026. Retain independent recovery alongside routine named support. The two access
walkthroughs now model short product screens and confirmation/status interactions rather than showing
flow documentation. Request → setup → grants, cleanup attention/complete, recovery confirmation/window
and uncertain rotation remain backed by the existing proposed model. Optional scenarios are collapsed;
engineering detail and the exact field/transition map live in chapter13. Required-user diagnostics
are collapsed, and repair acknowledgment leaves the issue open. No new table/column or real credential.

[Open Administrator access](../walkthroughs/human-access-walkthrough.html#access-ready),
[Recovery](../walkthroughs/human-access-walkthrough.html#emergency-review), or
[Required users](../walkthroughs/access-walkthrough.html#missing).
The current app-flow review (private historical evidence; not distributed)
supersedes earlier layouts; current validation is recorded there. Custodial MFA/permissions remain
qualification work; production-ready recovery is not implied. This presentation rule applies to future
design slices while preserving the accepted organization prototype and other workflow semantics.



## D39: V1 recovery authentication and workflow scope

Historical decision record: D40 supersedes the named-support V1 flow; current behavior is the single recovery-password access flow in chapter13.

24 October 2026. The user selects an MFA exemption for only the persistent recovery user, with
one distinct OCI Vault secret/password per managed tenancy and rotation in both the child user
and corresponding secret after use. Ordinary named human accounts keep MFA. No central federation
or shared TOTP custody service is adopted for V1. This is an accepted design direction, not a live
sign-on policy change or proof that every identity-domain page supports the same exemption.

Bind the exception to the exact managed recovery identity, or a dedicated group restricted to that
identity. Never exempt the general Administrators group, all OTM admins or all users. Observe its
policy scope/precedence and group membership as managed access intent/drift. Qualify console access
and actual automation-restoration tasks: My Profile/My Apps have separate MFA enforcement. No
unsupported workaround or domain-wide MFA removal is authorized by this choice.

Preserve the accepted per-tenancy first-authorized-disclosure exposure window and four-hour rotation
obligation; this message specifies no replacement timer. Stage a candidate Vault version before the
child password write; reconcile and publish the exact usable version only through qualified evidence.
A Vault update alone is not a child-password update; partial/unknown effects block further disclosure.
Manual independent recovery is still required when automation cannot perform the rotation.

The user initially retains temporary local named administrator creation, then asks whether rare human
access should instead use only the recovery mechanism. D40 now accepts that consolidation: named provisioning/cleanup is deferred and current UI/model requirements use recovery-password access only. The comparison is named MFA-protected access and
identity-bound activity/cleanup versus a simpler shared-password retrieval/rotation path. Rotation
is not proof that an existing shared-account session has ended, and checkout audit is not exact
attribution of every subsequent OCI action. No new table/column, production account or real secret.


## D40: single V1 administrator-access flow

Accepted 24 October 2026. The user approved simplifying human access to the persistent recovery account
and requested model, design and screen updates. This resolves the consolidation question in D39 and
supersedes D19/D37 named-account provisioning/cleanup for V1. D38's concise product-screen treatment
and independent recovery requirement remain. There is no temporary support-account operation in V1.

The persistent recovery user and automation signer remain separate. Use distinct per-tenancy Vault
passwords, the selected recovery-only MFA exemption, audit/notifications on every retrieval and a
four-hour rotation obligation anchored at the first authorized disclosure attempt. Joining retrievals
share the original deadline/version; lost responses count. Stage and reconcile child/Vault rotation,
block unknown outcomes and preserve independent recovery. Rotation does not imply session termination
or exact attribution of actions under a shared account.

Chapter11/core ER simplify the retained disclosure-request table and remove grant-owned access
assignments/cleanup fields, keeping 28 proposed application tables. Chapters04/13 and the current access
screens describe the same single flow. This is proposed design only; the working prototype database,
provider accounts, secrets and application operations have not changed.

D40 validation: final design/UI review (private historical evidence; not distributed)
records84 passing browser checks plus retained documentation, field/ER, syntax and lint checks.
Independent source/screenshot review and narrative/model consistency review found no remaining
material issue. Source-only verified checkpoint: `.local-dev/checkpoints/d40-design-2026-10-24/`;
this is not a database backup, migration or provider qualification.


## D41: accepted child Budget financial source; history post-V1

Accepted 24 October 2026. Read the exact bound root OTM Budget in each child through existing automation.
One snapshot supplies budget amount, current-cycle actual, complete cycle-end forecast and OCI spend
computation time. Never add actual to forecast, infer unknown currency, substitute parent budgets or
turn missing/unverified values into0. OTM retrieval time is distinct from OCI calculation time.
Historical reporting, prior-month selection, trends/backfill and parent Usage API financial collection
are post-V1. Retained observations/audit are correctness evidence, not a history-reporting feature.

Chapters05/08/11/14, the finance ER, product requirements and call-inventory scope are aligned. Two
existing proposed financial tables suffice; no prototype migration or provider call occurs. Exact
no-alert-budget calculations, current cycle/rollover, currency, permissions and decimal normalization
remain real-provider qualification. D42 accepts daily plus manual refresh. Dashboard indicators and rendered cost screens follow that reporting-policy review.


## D42: accepted daily collection plus manual refresh

Accepted 24 October 2026, option A. Daily jobs read eligible children’s bound Budget objects; admins
may request an additional refresh. Keep OCI calculation time distinct from collection time. Manual
refresh does not imply OCI recalculation. Preserve independent child progress, stable delivery keys,
request idempotency, original source/cycle context and credential-work capacity. Fleet and single-child
scope are explicit; the dashboard itself reads persisted snapshots. Exact runtime time/jitter and
qualified freshness policy remain implementation/operations settings. No additional OCI alert rule,
resource action or historical reporting is introduced.


## D43: accepted spend indicators; original separate-list layout superseded by D44

Accepted 24 October 2026, option A. Amber indicates qualified forecast above observed budget; red
indicates actual above observed budget. Data status remains separate; there is no 80% early warning,
cost-email dispatch or automatic resource action. The current provider budget is the comparison,
with desired/pending override shown separately. Historical reporting remains post-V1.

[Cost list](../walkthroughs/financial-walkthrough.html#costs) and
[shared-tenancy detail](../walkthroughs/financial-walkthrough.html#tenancy?tenancy=jordan)
now demonstrate the proposed layouts. Existing inventory and tenancy pages link them; the working
organization prototype is unchanged. Layouts are ready for user review, not already accepted as final.
Chapter14 records each control/status field and its model/derivation. Current-cycle snapshot, currency,
source timestamps and per-child uncertainty remain explicit. C5 notification/operations contracts,
provider qualification and C6 handoff still remain; this is not a blanket design-complete claim.

Financial slice validation: review and captures (private historical evidence; not distributed)
record 99 passing browser checks plus retained model/doc/syntax/lint checks. Source-only verified
checkpoint: `.local-dev/checkpoints/d43-design-2026-10-24/`. No production database or provider state
changed; cost layouts remain ready for user review.


## D44: accepted unified Tenancies dashboard

Accepted direct user instruction, 24 October 2026. There is one Tenancies dashboard, no Inventory/Costs
tabs. Five columns consolidate existing fields: Tenancy (name/type/owner-inclusive count plus cost-data
information), Owner/LOB, Configuration (assigned baseline/override/linked issues), Actual/Budget and
Forecast. Timestamp details may use a hover/focus/tap information control; important missing/stale/
unverified data remains visible. D41 source, D42 cadence, D43 warnings and post-V1 financial history
scope do not change. Counts include the active owner and distinct members, using the full filtered
scope for summaries and preserving existing query/navigation controls.

The shared Tenancies menu and legacy list aliases resolve to
[one dashboard](../walkthroughs/financial-walkthrough.html#tenancies). Tenancy detail
and its existing Configuration links remain. [Chapter14](../engineering-design/14-financial-journeys.md), [DESIGN.md](../../DESIGN.md)
and the [authority map](../ui-screen-authority.md) record field/interaction ownership. No table, column,
prototype/database or provider change is implied. D44 source/layout/browser review (private historical evidence; not distributed) passes 29 focused journeys and 84 responsive/popup checks with independent source/screenshot review. D46 subsequently approves the final dashboard; real-provider qualification remains separate. Earlier D43 receipts describe the superseded two-list layout.


## D45: accepted independent spend highlights and retrieval-only list tooltip

Accepted 25 October 2026. Keep the unified five-column Tenancies dashboard. Actual and forecast compare independently to the same qualified observed budget: red actual above budget and amber forecast above budget may appear simultaneously (Grant actual240/budget200/forecast320). Qualified below-budget numbers may be green; exact-at-budget and unqualified/unavailable numbers stay neutral. Number backgrounds replace redundant second-row spend badges and the list's overall warning badge, with screen-reader-only per-value status and hover titles preserving textual meaning. Detail may retain a highest-severity summary alongside independent values.

The accessible hover/focus/tap tooltip exposes OTM retrieval time, optionally status/cycle, but no OCI calculation timestamp. Important missing/stale/prior-cycle/unverified-currency and pending-budget messages remain visible. Retain calculation time in the internal snapshot and stale-data qualification and technical detail. D45 supersedes D43's exclusive overall-warning presentation only: D41 source/observed-budget qualification, D42 daily/manual cadence and post-V1 history remain unchanged. No model field/table or cost automation is added. [Chapter14](../engineering-design/14-financial-journeys.md) and [UI authority](../ui-screen-authority.md) carry the field contract. D45 final design/UI review (private historical evidence; not distributed) passes 38 browser journeys and 84 responsive/popup checks with independent source/screenshot review. User visual acceptance and provider qualification remain separate.


## D46: approved dashboard and independent monetary sorting

Accepted 25 October 2026. The user approved the final D45 dashboard and explicitly retained separate
Actual and Budget sort controls inside the shared Actual/Budget header. Actual selects
`actual_spend`; Budget selects `observed_budget_amount`, never a pending desired override. Each key
has ascending/descending behavior, with unavailable values last in either direction. A new key starts
ascending; activating the selected key toggles direction. Sorting resets the page to 1 and preserves
filters/page size; detail return preserves the selection and valid page. These are query-state
controls over existing snapshot facts, not additional visual columns or stored sort-status fields.

This approves the final five-column layout, independent amount colors, retrieval-only tooltip and
existing contextual links, not production OCI behavior. The D45 review (private historical evidence; not distributed)
records 38 interaction and 84 responsive checks; no new runtime/browser run is claimed for this
acceptance-only update. AC66, the [UI baseline](../../DESIGN.md), [authority map](../ui-screen-authority.md),
[financial journeys](../engineering-design/14-financial-journeys.md) and proposed model now record the same contract.

Next design slice: [C5 collection and operational events](../engineering-design/15-collection-and-operational-events.md).
Finish its facade/normalization, publication/query, scheduling/failure and notification-policy
contracts before declaring C5 closed. C6 then develops production delivery, database security/indexes,
backup/restore and executable development packages. Earlier chapters' remaining provider/API/schema
qualification gates remain explicit; dashboard approval does not mark all checkpoints complete.


## D47: accepted email-only operational delivery

Accepted 25 October 2026: email in V1; Slack later. Keep the notification port extensible but do not
build Slack setup, credentials or dispatch for V1. Required triggers, recipients, urgency, source-
event/outbox atomicity, manual Send boundaries and uncertainty/restore guards remain unchanged.
The [delivery contract](../engineering-design/15-collection-and-operational-events.md#d47-delivery-contract-email-in-v1)
maps messages, sender references and attempt results to the existing runtime policy, outbox and audit
fields. No new table, migration, UI or actual email send is part of this design update. AC67 records
channel scope. Email provider/sender/endpoint and result semantics remain C6 qualification work.

D48 now selects one administrator email after bounded cost-read retries are exhausted. It does not change immediate access-loss, disclosure or urgent rotation notifications, and it cannot add cost-threshold emails. C5 remains open for lifecycle notification policy and remaining source/fixture contracts.

D47 validation: delivery design review (private historical evidence; not distributed)
records the cross-tier audit and captured-provider-context correction. Documentation, field/link,
inline-documentation and Ruff checks pass; no live email/provider or new browser test is claimed.


## D48: accepted failed-cost-read email after retry exhaustion

Accepted 25 October 2026, recommended option. Failed acquisition attempts are visible immediately;
only bounded automatic retry exhaustion creates the initial administrator email. Continuing retries,
manual refreshes and daily failures remain one incident until verified same-source read recovery;
relapse is a new episode. No recovery/reminder emails, 24-hour delay or owner/manager/designee
expansion is introduced. Null forecast, normal computation lag and over-budget values are not this
trigger; existing urgent access/disclosure/rotation notices remain binding.

[Chapter15](../engineering-design/15-collection-and-operational-events.md#d48-accepted-alert-after-automatic-cost-read-retries-are-exhausted)
and chapter11 trace the episode to immutable audit data, current collection/operation context and
existing outbox uniqueness. Source-scoped coordination must prevent late/duplicate results from
reopening or duplicating an incident. AC68 records the policy. No new tables, runtime delivery,
UI or database changes are part of this design adoption. Retry counts/backoff and real provider/
email/transaction behavior remain explicit implementation/C6 qualification.

C5 continuation now has an explicit [remaining-review matrix](../engineering-design/15-collection-and-operational-events.md#remaining-c5-review-items).
D49 now accepts lifecycle email for administrator action or terminal failure; D50 selects the responsible administrator only, with no automatic fallback. Collection/notification model examples and
normalization fixtures remain design work; real email/OCI and runner/restore qualification remain
later implementation/pilot evidence. No C5 completion is claimed merely from accepting D48.

D48 validation: incident-policy review (private historical evidence; not distributed)
records cross-tier/model review with no remaining material issue. Documentation/link/field, inline
and Ruff checks pass; incident-concurrency and provider/delivery cases remain planned, not executed.


## D49: accepted lifecycle action/failure emails

Accepted 25 October 2026. Email when an accepted lifecycle operation requires administrator action
or reaches known terminal failure. Routine progress and success stay in Operations; no new operation
state is introduced. Human-action waits and actionable Needs attention have deduplicated episodes;
provider/retry waits and uncertain external outcomes cannot be relabeled terminal failures to send
mail. [The contract](../engineering-design/15-collection-and-operational-events.md#d49-accepted-lifecycle-email-only-for-action-or-terminal-failure)
links exact operation/intent/step/transition evidence, affected children, partial-resource context and
existing outbox intent. AC69 records the policy. D50 selects responsible-admin-only routing with no automatic fallback. No UI,
provider, database or actual email change occurs in this design adoption. C5 stays open for the remaining typed source/normalization examples before C6 delivery/operations handoff.

D49 validation: lifecycle-policy review (private historical evidence; not distributed)
records cross-tier/state/model review with no remaining material finding. Documentation/link/field,
inline and Ruff checks pass; production transition/concurrency/email cases remain planned tests.


## D50: accepted lifecycle emails to responsible administrator only

Accepted 25 October 2026. The user selected only the responsible administrator, overriding the
previous proposed admin-team fallback. Initially this is the initiating authorized administrator;
explicit audited takeover may reassign responsibility without changing creator/activation history.
Lifecycle notices do not copy all admins, owners, managers or designees. Missing/ineligible/unreachable
routing stays visible/blocked for explicit correction or takeover. Other notification families keep
their required recipients. AC70 records the rule.

[Chapter15](../engineering-design/15-collection-and-operational-events.md#d50-accepted-responsible-administrator-only) and
chapter11 map assignment/revision, frozen recipient, correction and delivery-context evidence to
existing fields. Reassignment cannot rewrite accepted email recipients or bypass uncertain-send
reconciliation. No automatic takeover, new table/column, UI or actual delivery is implemented by
this adoption. C5 notification policy decisions are settled through D50; typed source/normalization
examples and contract validation remain before the C6 production/development handoff.

D50 validation: routing-policy review (private historical evidence; not distributed)
records the cross-tier/model review with no remaining material issue. Documentation/link/field,
inline and Ruff checks pass; actual entitlement/reassignment/delivery race tests remain planned.



## D51/D52 accepted: production recovery objectives — 25 October 2026

D51 accepts **15-minute RPO** and **4-hour RTO** engineering targets. D52 scopes them to **in-region
recovery** in V1; full-region loss requires separately reviewed future disaster recovery. These
are not measured service guarantees. [Chapter06](../engineering-design/06-platform-and-delivery.md#d51d52-accepted-recovery-objectives-and-in-region-qualification)
defines incident/recovery clocks, committed-write evidence, read-only versus safe-service readiness,
external fencing, quarantined unknown effects and independent credential-deadline recovery.

The nonsecret runtime-policy example maps targets to existing workspace settings; typed recovery
receipts map to existing operation/audit storage. No application table, migration, UI or real restore
is introduced. AC71/AC72 record the accepted objectives/scope; provider retention/lag/fencing and
measured qualification remain C6 gates. Next, make the external recovery controls and deployment
release protocol concrete without letting a restored database authorize its own replay.



## D53 accepted: testing and protected master — 26 October 2026

The user requires unit tests with 95% or greater coverage, Playwright UI integration, database tests
using a disposable Docker database, all tests on every build and mandatory pass/coverage gates for
PR merges to protected `master`. [The canonical test/merge policy](../engineering-test-plan.md#d53-required-test-and-merge-gates)
operationalizes line coverage over complete first-party source, separate prototype/backend/frontend unit reports,
real UI/API/persistence and PostgreSQL checks, fail-closed required statuses and P0 protection probes.

Updated spec AC73–AC76, platform/implementation/review plans, README and AGENTS. No production table,
application dependency or remote repository setting is changed; the existing reusable prototype/test
work remains intact. Do not infer 95% measured coverage or implemented Playwright/CI from this decision.





## D54 accepted: Vault CURRENT, manual restore and simplicity — 26 October 2026

Normal passwords resolve the bound stable secret OCID with `stage="CURRENT"`. Exact returned versions
remain audit evidence; staged candidate versions remain required for interrupted rotation. API-key
selection is unchanged. [Chapter17](../engineering-design/17-recovery-and-release.md) now contains the short manual restore
runbook. Pause the deployment, hold restored work, review OCI/Vault/mail state and explicitly resume
safe work. Original credential deadlines and D51–D53 remain binding.

The external control buckets, per-dispatch receipt/dependency/exposure journal, independent release
CLI/manifest, extra execution envelope and their active schemas/checker/reports have been removed.
Their earlier source-only checkpoint is historical, not current work or evidence. Unused workspace
recovery mirrors were removed from the proposed ER. No extra secret-locator column/table is added.

The standing design rule is simplest adequate V1 behavior, with human recovery for rare cases where
appropriate. Retain critical correctness/security checks and ask before introducing substantial
edge-case infrastructure. Continue C6 with minimal feature-ordered migrations, query-driven indexes
and concrete required CI jobs. Do not implement all 28 proposed tables before a vertical slice.



## D55 accepted: explicit activation administrator identity at create handoff

28 October 2026. Following independent Astra review, the user selected a required create-only
activation administrator user OCID alongside tenancy/bootstrap OCIDs. Verify and preview/confirm
the exact same-child domain/OCI/SCIM cleanup binding before removal; retain immutable operation
intent/provenance and existing last-admin/replacement guards. Import preserves unrelated humans.
Existing intent/binding tables suffice; no new table or service. [Chapter11 field mapping](../engineering-design/11-production-data-model.md#create-only-activation-administrator-binding-d55).

Astra also identified a contradictory candidate open-issue unique key. It now includes both coverage
subject fields, preserving the already-designed independent automation/recovery incident scopes.
See [review and disposition](../history/astra-design-review-2026-10-28.md). Whole-package user approval remains pending.



## D56 accepted: security review for each development slice

28 October2026. Add the persistent `security_review` subagent alongside documentation and UX review.
Review each completed slice/security-sensitive change for OWASP/application vulnerabilities,
authorization/target isolation, secret and real employee PII leakage, and dependency/CI/IaC supply
chain risks. [The security policy](../security-review-policy.md) defines the lightweight workflow
and blockers. Required automated `security` CI complements the independent review. P0 must sanitize
the first publish set and provide synthetic test fixtures; current local HR inputs/examples and
raw screenshots are not cleared for GitHub. Private repository status is not an exemption.



## D57 accepted: original A / Field Console

28 October 2026. After the side-by-side comparison, the user chose **left / original A** over
rounded A2. [DESIGN.md](../../DESIGN.md) is the visual authority: navy navigation, cobalt accents,
cool light surfaces, crisp 3px corners and technical typography. Apply it to future production
components and screen updates while preserving approved UX, fields and all quality/security gates.
The comparison (private historical evidence; not distributed) remains reference evidence;
no runtime/model/workflow change or whole-package Git/publication approval is implied.



## D58 accepted: OTM-managed administrator grants and independent local recovery

29 October 2026. The user selected application-managed administrator grants and a non-SSO initial
administrator retained as the application's break-glass path. Implement local authentication first
for testing; add corporate SSO later while retaining recovery. This is separate from child tenancy
D39/D40 recovery accounts. [Chapter19](../engineering-design/19-administrator-provisioning.md) records accepted scope,
bootstrap/admin-management requirements and the accepted strong-password plus SSO-independent MFA
policy (also used for local testing). Detailed schema/ER,
audit/API/UI integration was the next checkpoint at that decision. The later local implementation
below now supplies the grant/authentication foundation and React directory/revocation screens;
corporate integration and ordinary add/regrant remain future work.



## Presence-only simplification — 6 November 2026

Accepted: first read-only user-presence checks use exact canonical identity bindings plus the current
automation connection revision. Defer access-assignment/profile tables until privilege checks and
repairs. Authentication failure means Unable to verify; recovery and parent credentials are never
automatic fallback. The [implemented connection foundation](../reference/user-presence-connections.md)
records the minimal simulated subset, legacy behavior and remaining worker/credential qualification.

## Manual presence implementation boundary — 6 November 2026

The earlier accepted simplification now has a [source implementation](../reference/user-presence-checks.md):
exact canonical subjects and one current connection revision feed manual authenticated worker reads.
No assignment/profile tables are needed for this presence-only subset. Simulation producer fixtures
are explicit and not live OCI verification; current authority/attempt/context and per-subject time
checks remain mandatory. Daily scheduler/notifications/privilege repair remain later work, with
local qualification and the main-preview upgrade complete; the parallel preview is unchanged. [Final receipt](../history/manual-presence-checkpoint-2026-11-06.md).

## 7 November 2026 — explicit former-owner disposition clarification

The administrator chooses Keep as a member or Remove from tenancy on standalone transfer.
The user confirmed Keep is available only for shared tenancies. Keep preserves the former
owner's identity, bindings, groups and permissions, including any admin access; it changes OTM
accountability and tracked role. It supersedes the earlier retained D21-profile/downgrade wording.
Remove authorizes exact personal-user/group removal in the existing queued transfer operation,
with explicit destructive consent and verified effects. New offboarding transfers default to
Remove; shared retention remains an outside-directory obligation after offboarding. Historical
omitted choices keep their original meaning and never gain new deletion effects.

V1 publishes the ownership/association result after replacement and requested removal verification;
uncertain removal keeps the current OTM owner and pending scope rather than claiming completion.
The default-closed manual cleanup panel explains resources/shared scopes, empty dedicated
compartments and additional manually created identities; this work is not automated.
[Current flow and field map](../reference/organization-workflows.md#explicit-former-owner-disposition--7-november-2026).

## 7 November 2026 — credential security lifecycle proposal

Historical same-day proposal: enable the recovery-only MFA exception on demand, with cleanup committed
before activation and an earlier four-hour clock. The user subsequently rejected extra human-account
complexity and selected the CIDR alternative below. That temporary-exception proposal is withdrawn;
it is not a concurrent V1 requirement. The 30-day automation-key retirement requirement is retained.

## 7 November 2026 — recovery console CIDR boundary selected

User approved the [chapter22 V1 design](../engineering-design/22-credential-security-lifecycles.md):
one existing recovery user per child, standing recovery-only MFA exemption and console sign-in allowed
only from multiple configurable source CIDRs. Explicitly deny this identity elsewhere before broader
allows; other users retain MFA. No new human recovery account, per-window exception mutation or central
TOTP broker. D40 first-authorized-disclosure four-hour password rotation and D54 CURRENT/manual restore
remain unchanged. This refines D39's exception scope; provider implementation/qualification is pending.

Expose `OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS` through protected GitHub Environment variables and map it to
`recovery_console.allowed_cidrs` in the strict rendered configuration. Use the existing configuration-only
rolling release, retaining the image; no new settings UI/hot reload. Variable edits alone do not apply.
Validate nonempty canonical lists and reject unrestricted unions. Review/confirm widening and lockout
risk; keep exact-user deny-outside intact and record desired versus verified applied state per child.
Actual supplied VPN ranges stay in private environment configuration, not publishable examples.

User clarification: apply the boundary/exemption when creating each exact recovery identity and
include both controls in its ongoing validation. Confirm MFA remains exempt and access outside the
approved CIDRs remains denied; presence alone is insufficient. Re-enabled MFA or weakened rules are
policy drift; incomplete inspection is unverified, not success. Both block readiness/new disclosure
until resolved through the existing authorized workflow. No control applies to unrelated identities.

Automation keys still retire by 30 days from original creation/upload, with proposed day29 preparation:
stage private material in Vault, upload public key, independently verify new signer, switch exact binding,
drain bounded old use and verify old deletion. Capacity/unknown effects retain overdue obligations.
Reuse existing operations and records; no extra coordinator/journal/table or live mutation is added.

## 9 November 2026 — Read-only automation administrator assignments

Following UI review, user approved the next UI-verifiable slice to check automation administrator
membership separately from account presence. Scope is exact built-in Administrators-group and
identity-domain administrator-role assignments, using captured references and the existing queued
read/evidence mechanism. Broader effective privilege proof, repair and real provider qualification
remain distinct. Complete negative reads mean Missing or disabled; incomplete/denied/legacy reads
mean Unable to verify. Simulation labels remain explicit.
