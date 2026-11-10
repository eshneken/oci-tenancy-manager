# Real OCI manual test manifest

Maintain this manifest with every development slice. Any behavior that cannot be verified locally
must have a pending live test before that slice is declared complete. Local simulator, PostgreSQL
and browser results remain separate evidence; they never qualify actual OCI behavior.

## Execution and evidence

For each pending case, retain prerequisites, administrator steps, expected results and status in
the linked procedure. Record the tested application/provider revision, test date, sanitized evidence
and result when executed. Use Pending, Passed, Failed or Blocked; a failed or blocked case remains
open until retested successfully. Record missing infrastructure or adapter support as a prerequisite,
not a passing result. Keep real account identifiers, employee data and secrets out of public evidence.

Run destructive or credential-changing cases only on approved disposable child tenancies with
independent recovery access. This manifest does not itself authorize live resource changes.

## Pending qualification groups

| Area | Procedure / expected qualification | Status |
| --- | --- | --- |
| Configuration drift and selected repair | [Live scenario matrix](configuration-drift-runbook.md#pending-real-oci-manual-validation): exact objects, override preservation, permissions, partial outcomes, concurrency and unrelated-resource protection. | Pending |
| Required-user presence | [Live presence matrix](configuration-drift-runbook.md#pending-required-user-presence-qualification): exact domain/SCIM/OCI identities, qualified absence, independent subjects and stale authority. | Pending |
| Permanent-user capture during onboarding | Create and import a disposable child; retain provider-returned automation and recovery domain/SCIM/OCI identities independently. Verify durable values against OCI. Retry interrupted setup without adopting same-name/different-ID accounts or inventing bindings for older records. Preserve post-policy access checks before retiring temporary credentials. Version 3 implements simulated capture; qualification still requires a real adapter and approved disposable child. Saved previews must be deliberately upgraded before local UI review. | Pending |

## Remaining provider and deployment qualification

These tests cover real effects that local simulations cannot establish. Some require future adapters
or deployment slices as well as tenancy access. Keep them Pending until those prerequisites exist;
linked local runbooks are preparation and comparison material, not live qualification receipts.

| Area | Live administrator steps and expected outcome | Preparation | Status |
| --- | --- | --- | --- |
| Create and activate child | Start creation under the approved parent; exercise an unavailable tenancy name and correct it without losing the operation. Complete actual activation/bootstrap handoff. Verify returned child OCID, name, home region and parent before setup; verify baseline and replacement access before exact temporary-account retirement. | [Onboarding](../reference/tenancy-onboarding.md) | Pending |
| Import child | Manually transfer a disposable child into the approved parent, then submit its exact OCID/bootstrap handoff. Reject a different parent or mismatched account; verify replacement setup and preserve unrelated administrators/resources. | [Tenancy refinements](tenancy-refinements-runbook.md) | Pending |
| Shared access and ownership | Add a member with a new compartment, then another with an existing compartment. Verify exact users/groups/compartment assignments. Remove one user and verify identity/group cleanup while resources remain for owner cleanup. Transfer ownership and check associations/accountability without deleting another member. Verify removal/transfer never offboards the employee or settles an independent absence review, including their last association; require fresh destructive consent for each new reviewed plan. | [Tenancy refinements](tenancy-refinements-runbook.md) | Pending |
| Initiate tenancy termination | On an approved disposable registered child, confirm the impact and initiate termination; verify OCI accepted it before releasing associations. Reject parent/unregistered targets. Exercise denied and ambiguous responses without falsely reporting success or blindly repeating an uncertain write. Every affected employee must retain their directory status and absence work, even when absent or losing their last association. Fresh full/partial employee returns must not recreate terminated infrastructure, identities or access. Final termination after the OCI hold is outside OTM scope. | [Deletion reference](../reference/tenancy-deletion.md) | Pending |
| Publish/apply baselines and overrides | Validate real policy/quota statements, root budget and tag definitions/defaults; apply to a disposable child and compare retained OCI object IDs/readback. Update individually and in bulk; resolve affected overrides first. Verify scope, partial failure/retry and unrelated objects remain safe. | [Baseline updates](baseline-update-runbook.md), [repair matrix](configuration-drift-runbook.md#pending-real-oci-manual-validation) | Pending |
| Current-month costs | Read the child managed budget and compare budget/actual/forecast/currency/cycle with OCI. Exercise daily and manual reads, stale/unavailable data, retries and month rollover; refreshing must not imply OCI recalculation. Historical budget reporting remains V2. | [Cost visibility](test-cost-visibility.md) | Pending |
| Recovery credentials | With independent recovery access, qualify per-child Vault secret custody, audited disclosure, required notices and four-hour password rotation. Verify the actual user and Vault CURRENT agree after rotation and that failures block unsafe disclosure. Exercise the approved manual restore/recovery procedure without publishing credential material. | [Access design](../engineering-design/12-access-health-and-repair.md) | Pending |
| Email and staging isolation | Route actual OCI activation/identity and application emails to the authorized testing administrator in staging. Verify every external email path is covered, correct responsible-admin delivery and bounded retry/failure handling for create/import, deletion, shared-membership, ownership-transfer and person-offboarding action/failure notices. Verify routine successes and provider-only waits send no mail, changed/revoked responsible contacts block without fallback, and uncertain acceptance is never blindly resent. Production must reject staging override configuration. | [Email runbook](lifecycle-email-runbook.md) | Pending |
| OKE schedules and recovery | Deploy reviewed infrastructure/configuration, verify daily drift/cost jobs and cleanup schedules run through the normal worker, and test least-privilege service access. Complete an in-region backup/restore drill against the 15-minute RPO/four-hour RTO targets. Verify corporate SSO and independent local recovery authentication in the hosted environment. | [Build/deployment design](../engineering-design/18-database-ci-and-build-order.md) | Pending |

## Canonical binding qualification

| Planned live scenario | Steps / expected outcome | Status |
| --- | --- | --- |
| Fresh exact identity mappings | Complete approved disposable-child onboarding. Compare the domain and both user bindings with actual OCI/SCIM IDs and immutable capture provenance. Confirm each operational role identifies its intended managed account, distinct from the owner and temporary bootstrap/activation users; account presence alone does not establish that ownership or grant profile. Same-name unrelated accounts must never be adopted; historical unbound captures must remain unverified until a qualified reinspection is designed. | Pending |
| Failed setup and termination | Interrupt binding persistence and verify temporary cleanup does not proceed. Retry without duplicate mappings. Deny termination initiation and verify bindings remain; accept it and verify logical retirement preserves creation/source history, without waiting for final OCI termination. | Pending |

## Required users identity display

| Planned live scenario | Steps / expected outcome | Status |
| --- | --- | --- |
| Stored identities versus live presence | Compare the Required users cards and expanded identifiers with qualified fresh OCI onboarding. Refresh must only reload stored facts. Registration alone must never imply current presence or permissions. Current manual results use simulation fixtures; a future qualified live exact-subject check may update Presence, while Permissions remains Not checked until its separate probe is implemented and qualified. Retired registration does not assert OCI account deletion. | Pending |

## Presence-only automation connection

| Planned live scenario | Steps / expected outcome | Status |
| --- | --- | --- |
| Qualified connection and stale-result fencing | With the real adapter/credential resolver implemented, bind the exact canonical automation signer and child domain. Qualify reads for both user subjects; change/revoke the selected connection during a read and reject stale results. Authentication failure remains Unable to verify, never Missing. No parent/recovery fallback. Existing simulated records must not be promoted to live authority. | Pending |

## Per-slice maintenance

Add new live-only scenarios here or to a linked matrix in the same slice as implementation, including
failure/retry and authorization cases relevant to that change. Link the local automated coverage
separately and state what it cannot prove. In checkpoint reports, identify available local manual
checks and any new pending live cases. Keep earlier pending cases until they are actually qualified.

This is an ongoing qualification register, not evidence that every future design feature is already
implemented. Expand it as provider, credentials, scheduling and deployment slices are delivered.

## Manual presence acquisition qualification

The [manual simulated pipeline](../reference/user-presence-checks.md) is a source checkpoint, not
live qualification. Keep every case below Pending until a real adapter and approved disposable
children exist. The local [review runbook](required-users-runbook.md) exercises only producer fixtures.

| Case | Live prerequisites / expected outcome | Status |
| --- | --- | --- |
| Exact independent accounts | Authenticate the selected child automation connection and query exact qualified domain/SCIM subjects. Confirm Present/Missing independently, with actual observed IDs and capture times; same-name identities cannot substitute. | Pending |
| Authentication versus absence | Test missing/revoked signer, denied domain access, wrong-domain 404, partial inventory and delayed visibility. They must be Unable to verify, not false Missing. Never fall back to recovery/parent credentials. | Pending |
| Bounded I/O and context changes | Qualify SDK/network timeouts, interrupted reads and adapter cancellation/reconciliation separately from the local 30-second late-return fence. Rotate/revoke connection or alter lifecycle/bindings during reads; stale context cannot publish current success. | Pending |
| Ordering, freshness and retained evidence | Overlap acquisitions and reverse completion order; newest admitted context governs. Verify independent 24-hour freshness, dated last results, safe unavailable outcomes and immutable audit/operation links without certifying privileges. | Pending |

Daily scheduled checks remain deferred to staging/Kubernetes. Their noninteractive machine
admission/authorization must be qualified separately; an interactive admin session is not an
implemented scheduler identity. No scheduled deployment or lifecycle email is claimed by this row.

## Inventory presence-summary qualification

| Case | Required live qualification | Status |
| --- | --- | --- |
| Shared summary/detail truth | After a real adapter is qualified, compare each inventory summary with the exact child's account observations and UTC times. Confirm fresh absence, stale/unknown facts and context changes never become a false positive; pending context stays dated. Navigation/GET must not acquire provider facts or imply privilege checks. Current source uses simulation only. | Pending |

## Pending: persisted cost and required-user read compatibility

On a disposable real child, refresh costs and both required-user observations once. Record the
original retrieval/check times. Add and remove a shared member, navigate through Operations,
return to Tenancies/detail and reload the browser. Unchanged Budget and required-user identities
must retain the same dated facts without an additional provider acquisition. Then change a
qualified Budget/configuration or required-user/connection binding and verify old incompatible
facts cannot appear current. Existing unit, PostgreSQL and native-browser simulation regressions
cover the application path; actual OCI identities, permissions and calculation delays remain Pending.

## Pending: explicit owner retention and identity removal

Prerequisites: qualified real lifecycle facade, controlled disposable child/identity domain and
recorded distinct personal/replacement/automation/recovery identities. Never use employee production
accounts for destructive qualification. These cases remain Pending; simulator results do not close them.

1. Transfer shared ownership to an existing member with Keep. Verify the old user OCID, enabled state,
   groups, permissions, credentials and compartment scope remain unchanged; verify replacement full
   administration before success, with one accountable owner and both tracked members.
2. Transfer with Remove. Independently verify replacement administration first, then exact former
   user's group/user deletion and loss of that identity's access. Automation/recovery and other
   members must remain intact; no fallback credentials or guessed identity is allowed.
3. Confirm all resources, compartments and additional accounts remain; follow the displayed manual
   responsibilities, deleting only an empty dedicated compartment after owner review.
4. Exercise missing/reused/protected identities, changed recipient bindings and partial group/user
   failures. No premature relationship retirement or false success; uncertain effects retain pending
   scope and require reconciliation before any further write. Test qualified retry semantics.
5. Repeat for individual transfer (Remove only) and absent-owner offboarding, including shared Keep
   retaining an outside-directory obligation. Confirm live API permission/readback behavior and
   request replay do not duplicate provisioning or removal.


## Pending: confirmed missing required-user notices

With a controlled disposable real child and approved test mailbox routing, qualify exact Missing
versus denied/incomplete reads. Verify one scoped initial per subject, correct owner/manager/designee
and administrator contacts, unavailable-contact fallback evidence, repeated/Unknown suppression,
Present then relapse, disabled delivery, stale-role suppression and no retargeted retry. Compare
actual SMTP acceptance/uncertainty and staged redirection with immutable Operations/Audit evidence.
No identity repair, privileged probe or live outgoing notice is implied by simulator qualification.
Daily scheduled checks remain deferred until staging/Kubernetes qualification. Status: Pending.

## Credential security lifecycles

Status: **Pending**. The [selected chapter 22 design](../engineering-design/22-credential-security-lifecycles.md)
requires disposable-child qualification with synthetic identities and separately approved live mutations.
Use private approved source ranges, never publish operational CIDRs/secrets in receipts or CI artifacts.

1. Verify the exact recovery user can sign in without MFA from every approved CIDR and is denied
   elsewhere. Qualify rule priority/fallback, IPv4/IPv6, actual VPN/proxy egress and split tunneling.
   Owners/members/general administrators keep MFA. Profile/My Apps/API credentials and existing sessions
   are separate evidence, not assumed covered by console sign-on restrictions.
   Re-run recovery-user validation after re-enabling its MFA challenge, changing group membership,
   disabling/reordering its rules or widening/removing CIDRs. Verify drift and blocked readiness/new
   disclosure; denied/incomplete inspection stays Unable to verify. Repeat creation/recreation/import
   against exact bindings. Missing enrollment must not be mistaken for a verified exemption.
2. Exercise initial setup/import, multiple CIDRs, invalid/empty/all-Internet unions, widening/narrowing,
   rollback and an offline child. Keep deny-outside effective throughout changes. Record desired versus
   verified applied revisions; failed narrowing remains visible and affected new disclosure blocked.
3. Qualify configuration-only release with retained image, strict deployed-schema validation, environment
   lock, consumer rollout and per-child updates. Missing variables fail safely; editing GitHub alone
   does not apply. Stale/late writes reconcile before successor; no false fleet completion.
4. Use the SAME recovery user with independent password custody when OTM/automation are unavailable;
   record VPN/corporate identity dependencies. Verify D40 first-disclosure clock and four-hour child/Vault
   password rotation; boundary/exemption remain. Restore under maintenance and inspect actual policy
   and CURRENT before resuming. No extra human account, TOTP broker or public bypass is required.
5. Qualify domain key create/list/get/delete, exact IDs/fingerprints, permission/propagation and three-key
   capacity. Prove the new signer alone can operate, old use drains and exact old deletion is verified.
6. Exercise day29/day30, unknown creation age, occupied slots, upload/delete timeouts, candidate failure,
   overlapping scans and restore before activation. Never delete the sole working/unowned key or reset
   original age. Unresolved retirement remains overdue with scoped repair available. Inventory every
   registered managed automation principal and explicitly owned parent/hosting keys.

## Automation administrator assignment qualification

Pending a real provider and staging tenancy: independently discover the protected built-in
Administrators group and exact domain application/administrator role; verify SCIM IDs rather than
names or OCI IAM group OCIDs. Qualify direct and supported group role grants, complete pagination,
removed membership/role, disabled resources, denied/partial reads, wrong-app/group/user replacements
and connection changes during reads. Confirm Missing versus Unable to verify, separate user
presence, dated persisted list/detail consistency and no provider/list disclosure in public outputs.
Validate actual SDK authentication and identity-domain administration separately; assignment success
alone must not authorize credential disclosure, destructive workflows or claim all effective access.
No live cases in this section have been run by the local simulation slice.


Apply the administrator-assignment matrix independently to automation and recovery. Remove only
one subject’s membership/direct or group role grant and prove the other remains independently
verified. Qualify coherent shared group facts, recovery identity replacement, cross-purpose
substitution, stale connection/attempt publication, denied/partial coverage and persisted reload.
Recovery Assigned must never by itself authorize password disclosure or imply console readiness.
These cases remain pending real OCI; local fixtures do not qualify the live APIs.


## Recovery network repair qualification

**User deferral — 9 November 2026:** additional interactive recovery-network repair testing waits
for real OCI and an approved actual policy break/repair. Do not create another local installation
or manufacture drift in main8443. The former8444 instance is retired;430-case automated simulator
qualification remains valid, while every live case below remains Pending.

All cases remain **Pending**. Local simulated repair is not provider/sign-in qualification.

| Live case | Required evidence | Status |
| --- | --- | --- |
| Exact conditional authority | Prove the automation signer can replace this owned perimeter; qualify exact domain/SCIM IDs, ownership and provider compare-token semantics. Presence/group membership is insufficient. | Pending |
| Narrow replacement and access | From confirmed network-only drift, preserve exact user/group, MFA exemption, application, policy and ordered allow/deny rules; verify allowed IPv4/IPv6 sources and denial elsewhere, including fallback rules. Never remove restrictions first. | Pending |
| Concurrent owner/operator edit | First edit networks externally, run a fresh complete check and qualify repair against that sealed actual state without rewriting setup. An unrefreshed third state or changed perimeter/rules after preview/admission must block; reject changed compare tokens or retain unknown effects without overwriting unrelated changes. | Pending |
| Readback and interruption | Qualify independent complete readback, propagation, lost write responses and process interruption. Unknown effects hold the operation; no blind duplicate write. | Pending |
| Desired/authority/lifecycle changes | Replace desired policy, signer, bound identity or child lifecycle during work. No stale write or obsolete readiness; retain known applied-but-superseded evidence when necessary. | Pending |
| Privacy and later checks | No CIDRs/rules in public responses/exports/errors; separate dated user/policy refresh reads actual applied facts. No password or credential action follows repair. | Pending |

Use only an approved disposable child. This flow does not qualify assignment repair, user recreation,
password custody, rotation or fleet rollout. See the [current source field map](../reference/recovery-network-repair.md).


## Recovery password custody and original-window qualification

All cases remain **Pending**. Source/local simulator work does not qualify OCI/Vault or sign-in.
Use an approved disposable real child when available; main8443 remains the sole saved local review
environment. Interactive recovery-network break/repair remains deferred; no legacy custody backfill.

| Live case | Required evidence | Status |
| --- | --- | --- |
| Version4 setup | Stage/allocate real custody and verify exact recovery user, child password and CURRENT before temporary cleanup; preserve old accepted versions/unrelated users. | Pending |
| CURRENT and references | Use actual returned Vault locator, CURRENT for normal reads and exact candidates for writes; no invented OCID, LATEST or historical DB fallback. | Pending |
| Original window | Persist request/audit/notices/due work before release; lost response and transient read failure preserve first-attempt+4h, joining requests never extend, unexpected version blocks. | Pending |
| Independent authority | Qualify automation context, exact recovery identity/assignments and MFA/CIDR controls. Stale/denied/incomplete facts are not readiness; no recovery signer fallback. | Pending |
| Coupled rotation | Stage recoverably, change only bound child user, independently verify candidate, conditionally promote CURRENT and read back; unknown effects never permit blind reset. | Pending |
| Lifecycle and restore | Exercise concurrency, requester departure, target/connection replacement, busy child and paused worker; preserve original deadlines and D54 paused manual reconciliation. | Pending |
| Notices and disclosure | Other-admin/owner/direct-manager attempt notices, admin failure notices, frozen roles/routing and environment checks; no secret in email/audit/log/cache/export; exceptional response is authenticated/no-store. | Pending |
| Sign-in limits | Verify actual allowed-source sign-in/outside denial separately; rotation does not promise existing-session termination; preserve independent same-account manual recovery. | Pending |

[WIP UI steps](../reference/recovery-password-access.md#current-dialog-and-future-main-only-manual-review)
require future local qualification/publication and do not establish that milestone today.
