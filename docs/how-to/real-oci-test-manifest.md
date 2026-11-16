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
| Terraform state bootstrap | [Private bucket, target identity, local-state custody and future backend qualification](#terraform-state-bootstrap); mock plans are not live authorization or recovery evidence. | Pending |
| App source allowlist | [Shared ingress contract](../engineering-design/06-platform-and-delivery.md#shared-inbound-source-allowlist--13-november-2026): permit HTTPS from each approved range/host and deny unapproved sources for UI and API. Inspect all NSG/security-list/controller rules for broad unions; reject missing/invalid input and ensure no alternate endpoint, NodePort, IPv6 or forwarded-header bypass. Qualify shared recovery-console propagation and lockout-safe updates independently. Network/allowlist and optional Caddy ingress source are implemented; full deployment/activation and effective live enforcement remain Pending. | Pending |
| Network foundation | [Source and operator procedure](#network-foundation): actual private subnet flags, closed default/attached lists, routing/service prefix, deployment runner reachability, pod-to-database NSG identity and state separation. | Pending |
| Enhanced OKE and private worker bootstrap | [Cluster, launch metadata, sensor and public-API qualification](#enhanced-oke-and-worker-bootstrap). ARM64 sensor compatibility is unknown and must be established before application deployment. | Pending |
| Secret version retention and cleanup | [Cleanup qualification](#secret-version-retention-and-cleanup): exact binding/IAM, keep-five retention, protected versions, conditional scheduling, quota pressure and actual purge. | Pending |
| Single hosting compartment input | [Placement/input qualification](#single-hosting-compartment-input): environment variable origin, tenancy/ancestry, all-resource placement and fail-closed targeting. | Pending |
| Vault custody foundation | [Vault/IAM qualification](#vault-custody-foundation): Vault-conditioned access isolation, group scope, secure ingestion, key custody/rotation and actual provisioning. | Pending |
| Managed PostgreSQL foundation | [Database qualification](#managed-postgresql-foundation): private bindings/TLS, Vault provisioning, HA/load, backup/PITR and real provider upgrade/replacement behavior. | Pending |
| Platform version and image promotion | [Version/image matrix](#platform-version-and-image-promotion): real regional lookup, saved-plan pinning, full staging selection/provenance and safe future PostgreSQL-major changes. | Pending |
| Initial multi-worker production sizing | [Two-worker qualification](#initial-multi-worker-production-qualification): identical staging/production two one-slot workers; locks, child isolation, deadlines, crash recovery and connection budget. | Pending |
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

## Platform version and image promotion

Status: **Pending**. [Implemented selection/input contract](platform-versions.md) uses mock-tested
OCI option/Compute intersection; no live image or database upgrade was qualified.

- Verify Actions environment values reach exactly their fixed staging/production roots as strings.
  Rejected/missing/floating/malformed pins must not create a candidate or obtain deployment authority.
- Query actual version/AARCH64/shape/OS options in Ashburn and verify the resolved image is the
  newest approved eligible image, with a correct timestamp and no architecture/OS fallback.
- Apply the exact reviewed saved staging plan and qualify actual ARM image/kernel, CNI, metadata,
  Falcon health and application workloads. A fresh plan selecting a new image needs new acceptance.
- Retain the whole selected image/version/architecture/OS record with trusted source/acceptance
  evidence. Verify artifact provenance before production credentials; raw JSON agreement is not proof.
- Exercise the implemented `otm.image_handoff` operator procedure against the accepted staging
  cluster output, retain its private digest/evidence, and plan production with the resulting tfvars.
  Confirm endpoints, state and worker cloud-init never enter the handoff or public workflow artifacts.
- Publish a newer same-version image between staging and production and prove the reviewed
  still-eligible staged image remains selected; reject missing/mismatched records and withdrawn IDs.
- With the implemented managed database module, qualify service-supported majors and explicit upgrade
  behavior, replacement prevention, backup/restore, extensions, migrations and matching CI coverage.
  The source now includes a real database resource, but source tests perform no live creation/upgrade.

## Enhanced OKE and worker bootstrap

Status: **Pending**. [OKE/bootstrap source procedure](oke-foundation.md) and
[traffic matrix](oke-network-traffic.md) are mock-tested intent, not live enforcement evidence.

- Qualify the newest approved regional GA patch, exact version/ARM-filtered OKE image, OS/kernel,
  A1 availability and AD/fault-domain placement. Reject unavailable pins, never substitute silently.
- Provision only after explicit approval, with operator-reviewed private script and scoped IAM.
  Confirm `areLegacyImdsEndpointsDisabled=true` on every launched/replacement compute instance;
  verify IMDSv1 refusal, IMDSv2 availability, private node/pod VNICs and exact NSG attachments.
- Qualify public API TCP6443 access from approved human sources with certificate verification and
  actual OCI/Kubernetes authorization; deny unapproved sources. Verify external TCP12250/10250/22
  remain closed, API IGW-only routing, private node/pod routing and no IPv6/public workload bypass.
- Exercise node/pod registration, CNI, in-cluster DNS, kubelet inspection, OCI service access,
  HTTPS registries/API/installer access and PMTU. Read back the effective NSG/security-list union.
- **Falcon ARM64 compatibility is unknown.** Validate the private installer and sensor against A1,
  the exact OKE image/kernel and required prerequisites. Confirm sensor service health, registration
  and policy before application workloads; repeat for each replacement node. A Ready node alone is
  insufficient. The reference bootstraps OKE before installing the sensor; account for that interval.
- Confirm private full script retains OKE initialization, uses IMDSv2, has bounded verified downloads,
  correct exit/failure reporting and approved installer integrity/version. Validate cloud-init failure
  visibility and total metadata size, with no bearer URLs/secret script in public logs/artifacts.
  Private state/versions/backups, saved plans and node metadata retain recoverable script bytes.
- Change the approved script/image/version and prove `INSTANCE_REPLACE` cycling, one surge node,
  zero unavailable, sufficient pod IPs, non-forced draining and restored sensor health on every node.
- Qualify owned deployment `/32` admission, job identity/RBAC and cleanup after success/failure/
  interruption. No job admission or full GitHub CIDR rule is supplied by this source slice.
- Qualify the optional [Caddy/NLB backend/health rules and controller annotations](caddy-ingress.md), managed
  database/TLS, scoped [workload IAM](oke-workload-identity.md) and held application manifests before marking the full app deployable. Their source exists; full launch composition and activation remain pending.

## Network foundation

Status: **Pending**. [Implemented source and offline operator guide](network-foundation.md) add
network resources and the shared private-input renderer. The platform roots now also compose the
OKE cluster/workers, managed PostgreSQL and workload Vault-read IAM described above. Optional Caddy ingress adds reserved-IP/NSG source and a held NLB renderer; no runner is included and no application is activated. No live
resource was created during source qualification. Native mocks verify plans only.

- Independently verify live target identity/compartment ancestry and regional service-prefix lookup;
  check enterprise routing overlap and pod-IP capacity before applying the address plan.
- Read back all subnet public-IP/internet-ingress flags, disabled IPv6, explicit security-list
  associations and both empty security lists. Verify Edge and API use internet-gateway routes,
  private nodes/pods route through NAT/services, and Database has no internet default.
- Compare actual remote backend key, tenancy, namespace and bucket with the selected root and
  independent bootstrap state. Test locking, interrupted operations and version recovery separately.
- With later resources attached, verify edge allowlist enforcement and absence of alternate paths;
  qualify required OKE/CNI/health-check egress and internal rules without broadening app admission.
- Qualify actual PostgreSQL source VNIC/pod NSG membership and TLS. A created NSG does not establish
  that a managed service honors the intended source path; never widen to whole-VCN/public access
  merely to pass a connectivity test.
- Qualify public endpoint administration/CI identity and narrowly scoped API access.
  The selected public API admits approved humans directly. Job-specific runner `/32` admission, cleanup and authentication remain pending; no private runner is required by this design.

## Terraform state bootstrap

Status: **Pending**. Source and mock-only checks are in [infra](../../infra/README.md);
the [operator procedure](terraform-state-bootstrap.md) requires approved tenancy access.

- Verify the actual short-lived principal, intended tenancy, compartment ancestry and namespace.
  Exercise a wrong namespace and a wrong-tenancy record, including a principal with access to
  multiple tenancies. Labels/OCID syntax must not be treated as authorization.
- Create staging's bucket first; verify private access, Standard storage, encryption, versioning
  and the expected compartment. Repeat independently for production only after approval.
- Protect and recover each environment's separate local bootstrap state and backup. Exercise
  interrupted creation without losing ownership or attempting an independent duplicate creation.
- Before remote delivery is enabled, qualify the later platform backend's separate state key,
  concurrent-writer locking, interrupted lock recovery, version restore and least-privilege IAM.
  Bucket creation alone does not establish these properties; no live retention lock is permitted
  on mutable state or lock objects.
- Verify deletion protections and access roles against direct OCI changes, not only Terraform's
  configuration-dependent `prevent_destroy`. Keep state, plans, identifiers and credentials out
  of public evidence and CI artifacts.

No OKE, database, federation or live state migration is implemented by this bootstrap checkpoint.

## Isolated environments and staging-first promotion

| Planned live scenario | Steps / expected outcome | Status |
| --- | --- | --- |
| Tenancy/identity/state isolation | Provision separate staging and production parent/child populations and hosting resources in Ashburn. Prove staging credentials cannot access production OCI/Kubernetes/DB/Vault/state resources, and production jobs do not load staging credentials. Validate per-environment trust subjects, approvals, private registry pulls, target preflights and mandatory staging email override / production override rejection. | Pending |
| Exact artifact promotion and negative gates | Build/attest one ARM release, deploy it to staging and complete applicable acceptance. Promote by release ID and confirm production uses the same image/platform and deployment-bundle identities, without rebuild. Reject arbitrary or mismatched source/run/artifacts, failed/incomplete acceptance, mutable-tag substitution, changed unreviewed inputs and wrong tenancy. Re-scan before promotion and reject newly blocking CVEs. Old candidate results cannot qualify another candidate. | Pending |
| Separate infrastructure/settings release and rollback | Qualify the same Terraform/module/provider-lock revision in staging, then generate/review a separate production plan against isolated state and inputs. Re-plan on drift; never reuse staging plans. Qualify settings changes using the deployed image and separately validated production profile. Verify per-environment serialization, migration/worker drain, compatibility, post-deploy smoke and rollback to a previously qualified digest without DB/OCI replay. | Pending |
| Administrator runbook walkthrough | After workflows and controls exist, an administrator other than the author follows the [hosted runbooks](hosted-administration.md) for application-only, infrastructure-only, combined and settings updates, manual backup and isolated restore without undocumented assistance. Replace proposed entry points with actual links/inputs/results; verify stop/recovery paths, irreversible-version handling and credential deadlines. Record observed duration, downtime, gaps and restricted evidence before go-live. | Pending |

See [the environment and promotion contract](../engineering-design/24-environments-and-promotion.md). These cases require hosted staging/production resources; no cloud or deployment gate is qualified by local simulation alone.

## Ashburn backup and restore qualification

| Planned live scenario | Steps / expected outcome | Status |
| --- | --- | --- |
| Managed backup/PITR configuration and cost | In `us-ashburn-1`, validate the proposed daily/35-day backup and 35-day PITR policy, actual recovery-window endpoints, pre-change checkpoint expiry, backup survival after approved DB deletion and encryption/restore permissions. Measure baseline, incremental, WAL/PITR and manual-checkpoint storage without double counting or assuming compression; verify independent failure/freshness/retention/cost monitoring and retained keys. No runtime or ordinary application-deploy identity can delete backups. | Pending |
| Full isolated in-region restore drill | Restore recent and older retained points across the drill program into explicitly owned private replacement systems, with sufficient quotas and no real child/email effects. Execute old-process fencing, endpoint/TLS/roles/schema/queue checks, invalidation of restored sessions, pending-work holds and OCI/Vault reconciliation under the existing manual restore runbook. Measure the 15-minute RPO / four-hour end-to-end RTO, retain evidence and remove owned drill systems only after review. No regional-loss recovery claim. | Pending |

See the [backup policy and sizing proposal](../engineering-design/06-platform-and-delivery.md#ashburn-v1-backup-policy-proposal--13-november-2026) and [manual restore procedure](../engineering-design/17-recovery-and-release.md#manual-database-restore-runbook). These scenarios require managed-service staging access and have not been exercised locally.

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
6. Exercise day 29/day 30, unknown creation age, occupied slots, upload/delete timeouts, candidate failure,
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
or manufacture drift in main 8443. The former8444 instance is retired;430-case automated simulator
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
Use an approved disposable real child when available; main 8443 remains the sole saved local review
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


## Automation signing-key inventory qualification

All cases remain **Pending**; local inventory simulation cannot qualify real key/signer behavior.

| Live case | Required evidence | Status |
| --- | --- | --- |
| Exact key resource/subject | Normalize actual identity-domain SCIM/composite API-key resource ID and fingerprint; require exact automation domain/user context, not an OCID-shaped assumption or name match. | Pending |
| Complete list | Qualify pagination, authorization, supported lifecycle state, duplicates and bounds; complete empty differs from denied/partial/unavailable. Never truncate a list and certify zero or complete coverage. | Pending |
| Original creation evidence | Identify trustworthy provider key creation/upload timestamp and normalize UTC; absent/future/untrusted time yields Unknown age, never observation/user/connection/feed time or a new lease. | Pending |
| Repeated/historical views | Preserve original timestamps through refresh/restart; current server-time age and historical capture-time age remain explicitly distinct. Test exact day 29/day 30 and stale/clock boundaries. | Pending |
| No added authority | Inventory must not expose PEM/private material, select a signer, establish custody/compliance, rotate/delete, notify or block unrelated work. Existing parent/recovery fallback remains forbidden. | Pending |

Broader30-day rotation, key capacity, new-signer verification and verified old-key retirement remain
pending in chapter22’s separate matrix. See the [current source map](../reference/automation-signing-keys.md).

## Managed signing-key rotation qualification

Status: **Pending — real OCI and hosted execution**. The [targeted local checkpoint](../history/signing-key-rotation-checkpoint-2026-11-10.md)
uses nonusable simulator material and cannot establish any live behavior below. Use approved disposable
children/test mailboxes and exact scoped credentials; do not create another local saved instance.

| Live case | Required evidence | Status |
| --- | --- | --- |
| Fresh create/import enrollment | Exact canonical automation identity, real original keypair/material clock, source bindings, no legacy/inventory adoption or premature temporary-admin cleanup | Pending |
| Exact signer and Vault custody | Original exact immutable secret version, least required custody permissions, independently created candidate signer, no CURRENT/LATEST or old-signer fallback | Pending |
| Key CRUD/slots | Actual identity-domain key IDs/fingerprints, complete listing, occupied three-key capacity, inactive/unknown keys, no unowned/sole-working deletion | Pending |
| Upload and propagation | Before-dispatch persistence, lost response/restart, same candidate fingerprint reconciliation, absent-after-uncertain hold and no blind reupload | Pending |
| Candidate permissions | Fresh current OCI identity, identity-domain admin/group and root-configuration capability; removed grants/denied/incomplete reads cannot reuse retained onboarding proof | Pending |
| Activation and retirement | Exact-generation CAS, original old deadline across activation, exact old ID/fingerprint deletion/response loss, continuing replacement proof and full old absence | Pending |
| Native OKE execution | Day29 original ETA/day30 guard, scheduled/manual priority and same-operation locks, hourly bounded rescue deployment, no competing rotation, restart/crash manual recovery | Pending |
| Recovery-password overlap | Requested/due signing rotation waits with ordinary reads available before hard key retirement, blocks NEW windows, preserves same-window redisclosure deadline; only after closure does short I/O drain/reservation/replacement begin. No deadline extension, closure deadlock or unsafe signer fallback. | Pending |
| Isolation and notices | Cached views/other children continue; no raw key material; one original-operation/admin incident across holds/resume/activation with frozen routing and no uncertain resend | Pending |
| Lifecycle/restore | Confirmed termination tombstones only that child; pending termination defers; D54 paused restore reconciles actual key custody/provider effects before continuation, no resurrection | Pending |


## Initial multi-worker production qualification

**Pending — staging/OKE and real OCI required.** Qualify the same two-worker/one-slot-each
topology, node/database sizing and software versions in staging and production, from the
[accepted sizing decision](../engineering-design/06-platform-and-delivery.md#accepted-initial-worker-sizing--10-november-2026).
Measure queue wait/provider latency and database connection use. Confirm unrelated-child progress,
operation lock/claim exclusion, the per-child rotation pause, duplicate delivery, graceful and abrupt
worker death, and recovery-password closure while a signing rotation drains. No uncertain write may
be retried merely because a second worker is available. Local simulation is not evidence of live
permissions, provider propagation or production timing guarantees.


### Initial signer authority and overlapping closure

**Pending — approved real provider/staging environment required.** Revoke or change the responsible
onboarding administrator after signer setup admission but before execution, and hold the parent
operation; prove no enrollment or parent continuation. Explicitly transfer responsibility to a live
administrator and qualify the correct continuation. Verify a due password closure remains system-owned
after the requester loses access. Exercise a real open password window while signing rotation drains:
the closure must finish without losing its original deadline before key activation/old-key retirement.
Local setup/privilege/consumer and isolated drain tests do not qualify provider propagation or OKE
queue latency. Keep the existing fixed window and retirement deadlines during this exercise.

The [availability correction evidence](../reference/signing-key-rotation.md#availability-correction-targeted-evidence--10-november-2026) records passing local direct-worker PG overlap cases and separate native-browser journeys. These do not close any live OCI/OKE row above or prove simultaneous native-queue closure timing; saved republication PASS.


## Combined fleet refresh qualification

[Refresh all data](../reference/fleet-refresh.md) currently uses local simulated provider workflows.
The combined live-provider qualification below remains Pending; unit/source checks do not close it.

| Case | Required live evidence | Status |
| --- | --- | --- |
| Registered fleet read boundary | Include all eligible active registered children, including filtered-out and off-page rows; acquire costs, required-user presence/privileges/recovery controls/key inventory, and configuration against each assigned baseline/overrides. Verify independent partial failures, current-signer/busy/rotation guards, workspace-scoped status/cache/readback and dated results. No repair, key rotation, baseline application or organization synchronization may be triggered. | Pending |


## Bootstrap key and generated-password policy qualification

Local source implementation does not establish either live result below.

| Case | Required live evidence | Status |
| --- | --- | --- |
| Create/import bootstrap custody and installation | Qualify Vault-backed exact operation-scoped preparation/replay and loss recovery outside SQL transactions; expose public PEM only, install it on the exact temporary child identity, independently verify signer privileges/authentication, and retire only after replacement access is verified. No private material in API/log/audit. | Pending |
| Effective recovery-password policy | Resolve the exact child's effective identity-domain/custom/group password policy and user/history restrictions; verify newly randomized 32-character four-class candidates are accepted for setup/rotation. Preserve original CURRENT/candidate bytes on replay and original four-hour window/unknown-effect fences; no reset/backfill shortcut. | Pending |

## Container hosting qualification — Pending

- Deploy the installed image through the approved hosted composition; verify OKE nonroot/read-only
  execution, resource limits, ingress/TLS and authenticated readiness. Packaging smoke is not this test.
- Verify managed PostgreSQL with certificate/hostname validation, external secrets and distinct
  API/worker/maintenance roles. No local-loopback relaxation or implicit simulator fallback.
- Exercise API browser journeys, actual Procrastinate work, SIGTERM/drain/restart and due maintenance
  using the hosted image; confirm schedules, backup/restore and Vault behavior.
- Verify both supported target architectures before publishing a multiarchitecture release; local
  host image checks alone do not qualify another architecture.

- On the selected musl-based image, qualify the actual OCI SDK and any introduced native libraries,
  remote PostgreSQL verify-full/CA behavior and authenticated lifecycle worker operations. Current
  image probes cover generic native jobs and local simulator composition, not those provider calls.

## Managed PostgreSQL foundation

Status: **Pending**. The [implemented source module](managed-postgresql.md) is mock-tested only.

- Verify the approved major, E5 shape/resource bounds and uniquely compatible configuration against
  actual Ashburn service results; confirm plan pins and no version/shape fallback.
- Provision the strong initial administrator secret in the correct environment's Vault, verify exact
  version/requester reads and separate custodian key-use grants, and confirm no secret content is exposed in plans, state or outputs.
  Separately create least-privileged runtime/migration users; never use this provisioning login for pods.
- Verify actual private database subnet/NSG attachments, no public endpoint, pod-only TCP5432,
  rejection from other sources, FQDN/CA hostname-verified TLS and service SSL policy.
- Load-test real query/queue/connection/history/WAL behavior, HA placement/failover, transient retries
  and the initial two-node1OCPU/16GB capacity/performance choice before accepting cost/latency.
- Verify DAILY35-day retention semantics, STANDARD35-day PITR coexistence, usable recovery-window
  freshness, encryption/key custody, deletion survival, independent monitoring and backup cost.
- Complete an isolated restore/cutover drill against15-minute RPO/four-hour RTO and repeat quarterly;
  test both recent and older recovery points. Confirm backup/key permissions and replacement capacity.
- On a disposable live staging DB, prove an unapproved major change plans replacement and is blocked
  by prevent_destroy; mocks cannot exercise OCI custom diff. Qualify an explicit supported in-place
  major upgrade with target configuration, checkpoint, maintenance window, application/driver/queue/
  migration tests and opt-in reset. A downgrade must not silently replace the database.
- Qualify initial Vault reference and later administrator-password rotation separately; updating a
  secret or Terraform reference alone must not be assumed to rotate the existing database password.

## Vault custody foundation

Status: **Pending**. [Implemented security roots](vault-foundation.md) use mocked providers only.

- Verify independent staging/production tenancy, hosting ancestry, actual group membership/principal,
  state key/bucket grants and IAM propagation; no inherited policy may unintentionally bridge domains.
- Verify no child compartments are created; both DEFAULT shared Vaults and enabled HSM AES256 keys use the selected existing hosting compartment; no
  secret payload enters Terraform input, state, plan, GitHub logs/artifacts or public source.
- Through the approved custodian, ingest a strong initial database password into its exact DB Vault/key in the selected hosting compartment. Retain only private OCID/version references and verify real DB provisioning
  using the intended requester read grants; add no speculative broad service/tenancy fallback.
- Prove provisioning readers can read only the intended DB-Vault secrets/metadata via exact Vault-ID conditions and cannot create,
  update, move or delete them or read application-Vault secrets through other grants. Verify future workload
  identities cannot read initial provisioning credentials. Source policy text is not effective IAM proof.
- Verify manual master-key version rotation preserves decryption of retained old secrets and recovery
  dependencies. Qualify the custodian's schedule/runbook and deletion/disable alerts before go-live;
  shared Vaults do not claim private-vault automatic key rotation or cross-region recovery.
- Review Vault/key lifecycle protections and private state recovery; confirm no app
  deployment needs security-state or initial DB-administrator access. Terraform guards do not prevent
  direct privileged deletion/disablement or configuration removal.

## Single hosting compartment input

Status: **Pending**. [Implemented input/renderer](hosting-compartment.md) is offline-tested only.

- Configure each protected Environment's real OTM_HOSTING_COMPARTMENT_OCID only after verifying the
  approved existing compartment in that tenancy. No synthetic live value, default or PR/fork override.
- Confirm bootstrap bucket, all Vaults/keys/policies, networking, OKE and PostgreSQL are in that exact
  compartment with no children created. Tenancy/namespace/label agreement is not ownership proof.
- Verify workflow-sourced input/digest and reviewed saved plans; malformed/missing values stop before
  mutation. Wrong-tenancy or unauthorized targets must fail under the actual identity/IAM.
- With both Vaults in the same compartment, prove database readers can read the intended Vault's
  secret/versions/bundles but cannot read application-Vault secrets, with no broad fallback grant.
  Validate actual target.vault.id condition support for all required calls and effective inherited IAM.

## Secret version retention and cleanup

Status: **Pending**. The [keep-five planner/simulator/executor](../reference/secret-lifecycle.md)
has no live adapter, rotation hooks, durable cleanup dispatch or hosted schedule yet. Historical
retirement-proof and SQL projection experiments were removed following the owner's simplification.

- Qualify the exact registered application Vault/region/secret binding and actual name length/charset;
  platform/KMS/bootstrap secrets remain outside permanent child version retention.
- Create more than five versions and verify only the newest five unscheduled versions remain, plus
  protected CURRENT/PREVIOUS/PENDING and explicit operation pins. Unsorted inventory must not alter
  selection; only older unpinned DEPRECATED versions qualify.
- Force an unresolved/failed rotation and an execution pause: cleanup skips the secret. Qualify reuse
  of the existing per-tenancy rotation reservation, including overlapping worker requests and release
  after failures; no SQL transaction is held across SDK calls.
- Verify complete pagination and actual active/pending quotas; scheduled but overdue versions still
  count until purged. Confirm protected versions are never sacrificed to make room.
- Schedule eligible versions at the approved delay, verify CURRENT remains usable, observe actual
  irreversible purge and confirm capacity accounting. Never substitute whole-secret deletion.
- Force provider permission/transport/revision failures: cleanup retries safely without extending
  existing deadlines or misreporting a successful rotation as failed. Record scheduling/failures in
  existing audit and qualify email incidents/pressure alerts.
- Verify daily CronJob duplicate/missed-trigger handling and bounded durable worker work, including
  paused restore behavior. No historical-retirement reconstruction or additional journal is required.
- Qualify temporary bootstrap whole-secret cleanup separately after verified replacement access and
  temporary-account removal. Never infer numeric Vault versions from local counters or opaque saved
  simulator references.


## Hosted Kubernetes workloads

Status: **Pending**. The [disabled workload bundle](kubernetes-workloads.md) is source/schema-tested,
not an active hosted application. No cluster, hosted runtime or migration command is composed yet.

- Validate the actual selected OKE API version and Restricted Pod Security admission; qualify ARM64
  digest/pull identity and node resource/surge/loss headroom. Confirm API/worker/migration use the
  exact accepted image and environment-specific namespaces/settings.
- Qualify named OCI workload identities, Vault custody, registry pulls, role-specific Kubernetes
  credential references, PostgreSQL verify-full CA/hostname checks and migration/runtime SQL grants.
- Implement/qualify hosted API and worker composition with no laptop fallback; readiness must reject
  missing/wrong DB schema/role and use bounded checks. Liveness stays process-only. Measure password
  hashing memory and connection pools against initial requests/limits; qualify the identical
  two-worker/one-slot-each topology in staging before production deployment.
- Qualify effective NSG/security-list rules and approved ingress, DNS, database, OCI/Vault and email
  paths. Keep public application CIDRs restricted and trusted proxy/TLS boundaries explicit.
- Prove migration runs only as an approved single-owner release step, fails visibly without automatic
  retry/down-migration, and gates deployment. Reapplying the same Job must not silently rerun it.
- Qualify worker SIGTERM/drain/deadline handling and partial external effects, API surge/availability
  protection and immutable ConfigMap rollout/rollback. Verify no stale queued deployment wins.
- Remove source-stage held commands/zero replicas/suspension only after these prerequisites and
  staging acceptance are implemented. A local schema pass does not authorize production activation.


### Selected OKE 1.37.0 qualification

Owner-selected target is v1.37.0 in both environments. Oracle currently labels this OKE release
preview; record that support limitation in deployment approval. Confirm us-ashburn-1 catalog/version,
compatible ARM64 OKE image and add-on/CNI/sensor support before applying. Local mocked Terraform or
Kubernetes1.37.0 schema checks do not establish service availability or production qualification.
For future load balancers, explicitly size bandwidth and keep TLS Secret references in the same
namespace; qualify the OKE1.37 behavior changes. No preview-to-GA or patch change happens implicitly.


## Hosted startup and database qualification

Pending staging: verify managed PostgreSQL DNS/CA chain and separate API/worker/migration grants; reject wrong CA/hostname and excessive runtime authority. Rehearse migration ownership, competing migration rejection, failure rollback and exact-schema readiness. Confirm proxy trust/HTTPS, Vault MFA reader, complete OCI/mail task registration, queue TLS and one slot per worker. Exercise SIGTERM API/worker drain under load, bounded DB/network outage handling, restore and schema-changing release sequencing. Source-only disposable TLS tests are not deployed evidence. See [startup contract](hosted-startup.md).


## Vault retrieval and OKE identity

Pending: deploy explicit service-account token/CA mounts and workload IAM scoped by exact cluster, namespace, service account and application Vault. Verify permitted metadata/bundle reads, wrong Vault/compartment and unauthorized-secret denial; confirm no database-provisioning access. Exercise workload token refresh, denied/expired identity, network/TLS failures, CURRENT changes and exact version reads. Validate no credential-file/node/simulator fallback and no plaintext in logs. Qualify each service consumer separately before activating held manifests. [Source/test boundary](../reference/vault-retrieval.md).


## Laptop API-key development

Pending tenancy access: register a dedicated development API key/profile and verify intended principal/region/tenancy, least-privilege development Vault and parent authority, denial for staging Vault access, real SDK signature verification and revoked-key errors. Qualify all OCI-triggered activation/owner emails go to the configured test address. Confirm laptop/local database and hosted staging manage independent child inventories without sharing credentials or state. Apply/review the minimal development custody Terraform root only with private inputs/state and verify Vault/key guards/effective IAM. Full live service/launcher composition remains pending; synthetic profile tests do not prove live permissions. [Runbook and source boundary](laptop-oci-development.md).


## Hosted workload Vault identity

Pending Enhanced OKE access: confirm both role service accounts can exchange projected default-audience tokens and read only the intended application Vault; verify numeric-version/CURRENT reads. Run nonroot, wait past token expiry and confirm directory projection/signing refresh without restarts. Deny wrong cluster, namespace, service account, compartment/Vault; verify migration and node identity gain no grant from these policies. Audit other broader IAM grants independently. Confirm CA ConfigMap existence, actual mode/group readability, issuer/audience/expiry, IAM propagation and required network paths. Ensure no local config mount/fallback and no token/secret values in logs. Keep workloads held until launch/service/network/DB-secret composition and staging rehearsal pass. [Source contract](oke-workload-identity.md).


## NSG-only V1 network boundary

Pending staging: verify effective union of attached NSGs/security lists/routes; inbound allowlists; private PostgreSQL TCP5432; OKE/CNI/proxymux and regional/public HTTPS paths; the implemented optional [Caddy load-balancer backend/health paths](caddy-ingress.md), after approved staging activation. Confirm no Atlas NetworkPolicy or policy-engine installation is expected; do not claim role/namespace network isolation. Audit actual metadata reachability, IMDSv1 disabled and node IAM lacking unintended Vault/parent privileges; NSGs do not filter link-local traffic. For SMTP, qualify approved relay IPs/port, matching app settings, verified TLS, routing and blocked unapproved destinations outside any other allowed rule. Removing an explicit relay rule must not be misreported as denying a broader overlapping OSN/CNI rule. See [approved source contract](nsg-only-networking.md).


## External DNS and Caddy certificates

Pending remaining release gates and domain/OCI access; targeted policy/native checks pass with two accepted findings and zero blocked findings: HTTP-01 is selected. Qualify external IPv4 A routing to the reserved address, real Let's Encrypt issuance/renewal, ordinary HTTP 404/no redirect/no app proxying, active challenge-only 80 and allowed/denied 443 through the exact edge NSG. Verify controller rule-management annotations, NLB source NAT/Local behavior, overwritten forwarding headers and API proxy trust, private NodePort/backend/health paths, infrastructure-owned StorageClass bootstrap, CSI encryption/nonroot ownership/placement and certificate/account-state backup/restore. Validate TLS/app health independently of TCP health. Keep separate environment state; do not publish AAAA or silently select a DNS plugin/alternative CA. Local Pebble protocol evidence is not public-CA or OCI qualification; the two exact official-Caddy DoS findings have owner-approved scoped exceptions, while any other/new HIGH/CRITICAL finding still blocks. No live deployment follows from the risk acceptance. See [design](../engineering-design/25-https-ingress-and-certificates.md) and [source review](caddy-ingress.md).

## Immutable ARM64 release artifacts

Status: **Pending**. [Implemented source](../reference/artifact-releases.md) and [review procedure](application-releases.md)
do not establish hosted publication or staging acceptance.

- Qualify the protected-master Checkpoint follow-on with exact standard SHA context and independent
  run/five-job API validation. Deny forks/PR/manual/spoofed runs, stale source and partial job evidence.
- On the actual native ARM runner, build each app/Caddy image once, inspect architecture/installed
  migration/settings contract, scan saved image bytes with OS/language coverage and produce SBOMs.
  App findings have no exception; recheck the exact approved Caddy policy and current official release.
- Verify GHCR tag-to-digest/manifest identity and permissions, standard image/descriptor/public-source
  provenance and image-bound SBOM attestations. Verify expected repository/workflow/ref/source and
  exact subjects from trusted records; a matching JSON hash or arbitrary signed artifact is insufficient.
- Exercise partial build/push/attestation failures without producing a qualified release. Confirm only
  four public files upload, 90-day retention, no sensitive logs/config/image archives and separately
  retained long-term descriptor/archive/SBOM/verified-attestation custody. Missing evidence blocks use;
  never silently rebuild under old acceptance.
- Qualify private OCI ARM pulls, registry credentials/rotation, actual staging deployment/render/schema
  compatibility and trusted acceptance records. Verify production selects the exact accepted candidate
  without rebuild and rejects fingerprint/source/platform/artifact substitution. These deployment and
  authenticated acceptance workflows are not implemented by the current content-matching helper.
