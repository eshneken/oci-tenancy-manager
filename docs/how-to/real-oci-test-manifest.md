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
