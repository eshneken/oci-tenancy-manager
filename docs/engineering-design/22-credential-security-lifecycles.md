# 22: recovery console CIDR boundary and scheduled API-key rotation

7 November 2026 | User-selected V1 design | Local policy checks and perimeter-only repair qualified; remaining credential flows and live OCI qualification pending

[Design hub](README.md) · [Administrator access](13-local-support-and-emergency-access.md) ·
[Credential model](11-production-data-model.md#identity-access-and-credential-model) ·
[Configuration releases](18-database-ci-and-build-order.md#application-and-configuration-deployment-paths) ·
[Manual qualification](../how-to/real-oci-test-manifest.md#credential-security-lifecycles)

## Decision status and boundaries

The user selected a standing MFA exemption for the existing recovery administrator, with console
sign-in restricted to a configurable list of approved source CIDRs. Multiple CIDRs are required.
Only this exact recovery identity is exempt. Keep one recovery user per child, its unique Vault
password, D40's original first-authorized-disclosure four-hour password-rotation obligation and
D54 Vault CURRENT resolution/manual restore. OTM automation API keys retain 30-day retirement.

This selected design replaces the earlier temporary-exception proposal, including its pre-activation
clock and extra MFA-protected recovery-path prerequisite. There is no per-window group mutation,
additional human recovery account or OTM TOTP-seed broker. Owners, members, general administrators
and OTM-local recovery authentication keep existing MFA requirements. Selection does not establish
implementation, a deployed exception or live qualification. Earlier temporary-exception proposals
in decision history are superseded.

## Recovery-only console boundary

Bind a managed network perimeter per child identity domain to dedicated recovery-only rules for the
OCI Console application. Where a group selects the user, it contains only the exact bound recovery
user, grants no additional privileges and is not the general Administrators group. Preserve existing
recovery administration grants separately. Qualify exact payloads, ordering and application bindings.
The effective rule sequence must:

1. Allow the exact recovery user from any approved CIDR without an additional MFA challenge.
2. Deny that exact recovery user from every other source before broader allow rules can match.
3. Leave existing rules and MFA for all other identities unchanged.

An allow-inside rule alone may fall through to a broader rule. Empty/unavailable settings never mean
unrestricted access. Verify the complete resulting sequence, not a named perimeter alone. Block
recovery readiness and password disclosure if required policy evidence is missing, stale or
inconsistent. Do not auto-repair unexpected group members, ownership or unrelated rules.

### Provisioning and ongoing recovery-user validation

When creating the OTM recovery user in each child's identity domain, configure this exact identity's
MFA exemption and CIDR rules as part of the same onboarding operation. Apply and read back the
complete boundary before declaring that user ready or disclosing its password. Recreated recovery
users require the same setup against their new exact binding; import must verify/apply the boundary
before readiness rather than trust a preexisting user name or policy label.

Include both controls in the recovery user's required-access validation at setup, after repair or
CIDR changes, and in subsequent manual refreshes and scheduled checks when implemented:

- The exact recovery identity remains exempt from the console MFA challenge under the effective
  sign-on rules; no general administrator/owner/member exemption was introduced. An absent enrolled
  factor is not evidence of exemption, and an enrolled factor alone is not evidence that MFA is required.
- The exact identity is allowed only within the current approved CIDR union and explicitly denied
  outside it. Check rule enablement, priority, console application assignment, exact group membership,
  perimeter contents and broader fallback rules, including both IP families.

Keep these findings separate from user presence, password health and general grants. Unexpected MFA
enforcement or a weakened/missing boundary is recovery-policy drift; insufficient permission, incomplete
or stale evidence is Unable to verify, never compliant. Block readiness/new password disclosure and
surface the failed control through existing required-access/Operations and applicable alert policy.
Repairs require existing preview/authority/target checks; validation itself is read-only and never
silently disables MFA or rewrites policy. The [current local UI implementation](../reference/recovery-console-verification.md) adds these independent
read-only controls and exact setup capture. Policy repair, actual provider enforcement and live
qualification remain pending.

Qualify actual sign-in behavior from allowed and outside sources using the disposable-child test
procedure, including a broad fallback allow rule. Ordinary validation inspects qualified effective
configuration evidence; it does not log in as the user, read its password or claim a successful
end-to-end sign-in test merely because a policy read succeeded.

Use actual source egress observed by the identity service, not a workstation's private VPN address.
Qualify gateways, proxies, split tunneling and IPv4/IPv6. A password remains sufficient from an
approved source; VPN availability and its identity dependencies remain recovery prerequisites.
Independent custody/manual recovery uses this SAME user, not another account. If approved networking
is unavailable, follow the existing owned provider-support/manual procedure; no public bypass is added.

This boundary restricts console sign-in. It does not prove restrictions on API signing keys, OAuth,
Profile/My Apps or existing sessions. Four hours remains a password exposure/rotation deadline,
not an exception lifetime or universal console logout. A stolen current password could be used
from an approved source outside an OTM disclosure window.

## Configuration contract and GitHub Actions

Use the existing operator-owned configuration-only release path. The validated deployed configuration
is the single desired-policy source; GitHub variables are release inputs, not a second live store.
No new settings UI, hot-reload service, coordinator, table or per-tenancy override is introduced.

| Field | Purpose, format, bounds and operational effect |
| --- | --- |
| `recovery_console.allowed_cidrs` | Required nonempty array of canonical IPv4/IPv6 network CIDRs; 1–64 entries and at most 4096 serialized input bytes. Entries are ORed. Restricts only each bound recovery user's console sign-in. No organization-specific default. Missing/invalid policy blocks live recovery provisioning/disclosure, while unrelated functions may remain available. |
| `OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS` | Comma-separated release input for the array. Trim surrounding whitespace, reject empty elements and host bits, strictly validate every network, deduplicate and sort deterministically. Required in both live deployment paths; not an arbitrary runtime environment override of the strict loader. |

Reject malformed entries, individual `/0` networks and effective unions covering all IPv4 or all
IPv6 (including narrower ranges that together allow everything). Never silently widen host addresses
to networks or partially accept an invalid list. Rejected changes preserve the previous valid desired
configuration. Private networks are syntactically valid but need evidence of actual observed egress.

Settings example; the [internal source foundation](../reference/recovery-console-verification.md) now validates
this section. Runtime policy composition and deployment remain pending:

```toml
[recovery_console]
# Approved console sources for only the recovery user: 1–64 canonical IPv4/IPv6 CIDRs, ORed.
# Empty, malformed and unrestricted unions are rejected; no organization-specific default.
allowed_cidrs = ["198.51.100.0/24", "203.0.113.0/24"]

```

Define `OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS` as a configuration variable in each protected GitHub
Environment. Map it into the release job environment; do not hardcode operational ranges in YAML:

```yaml
# Release-job fragment; the existing job selects the trusted protected deployment environment.
env:
  # Approved recovery-console source CIDRs; validated before obtaining deployment credentials.
  OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS: ${{ vars.OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS }}

```

Pass values as data to a strict renderer, never interpolate them into shell code. Render the single
TOML array with adjacent purpose comments and a blank line after the setting. Both application and
configuration releases validate the full candidate against the actual target image schema before
acquiring deployment/provider credentials. A new field requires compatible code first. Use existing
protected environments, deployment authority and required checks; untrusted/PR jobs cannot update OCI.

Configured corporate ranges are operational information: do not echo the list, dump environments or
publish rendered files as CI artifacts. Keep the supplied initial ranges in ignored local configuration
and deployment variables. Public docs/fixtures use synthetic CIDRs. No GitHub variable/workflow or
running provider is created by this document.

### Update the running environment

Edit the GitHub environment variable and run the reviewed configuration-only release. A variable
edit alone does not update the app or OCI. Retain the image digest, update the validated ConfigMap
and roll API/worker consumers using the existing configuration checksum. No image rebuild is needed;
this is the existing rolling deployment model, not hot reload or guaranteed zero downtime.

Before acceptance, show added/removed ranges, affected children, desired revision and widening/lockout
risk. Require explicit confirmation of the security-policy change, including removal of the final
known working route. Use the private operator candidate/preflight file and existing release-review
procedure for the actual ranges, not CI logs or a new settings web screen. Bind confirmation to the
reviewed candidate fingerprint/revision; any changed input invalidates it. CI reports safe fingerprints,
counts and outcome only. Empty final lists are rejected; there is no disable-boundary toggle. Reuse the
environment deployment lock, audited configuration revision and durable per-child operation steps.
Store desired fingerprint and each child's verified applied fingerprint/evidence with existing
configuration/managed binding/operation records, not a separate reconciliation table.

Immediately before each provider write, recheck exact child/domain/user/perimeter/rule ownership
and current desired revision. Serialize writes per binding. Obsolete known-unsent work cannot reapply
an old list. In-flight/unknown effects reconcile under their original attempts before a successor
mutates the same object: database/configuration fences cannot cancel an OCI call already sent.
Never hold a database transaction open over provider calls.

Preserve exact-user deny-outside enforcement throughout updates. Qualify conditional in-place perimeter
updates/readback; never remove the restrictive rules first or temporarily allow all sources. A path
that cannot maintain that invariant is unsupported until safely qualified. Initial setup/import
must verify the complete restriction before recovery readiness; broad old exemptions are not compliant.

ConfigMap rollout is not fleet completion. Show desired revision and Pending, Applied and Needs
attention child counts, with details in Operations. Failed/unknown changes retain actual last-verified
state and reconcile visibly. During narrowing, removed networks may remain effective on failed children:
alert, never claim fleet-wide enforcement and block their new OTM disclosures until current policy
is verified. This cannot revoke an already copied password. New children receive the current list
before readiness. Include retained inactive recovery identities in inventory; skip only with verified
removal/disablement or explicit owned manual disposition, never because a binding/permission is missing.

Rollback is a new reviewed revision, including re-widening risk; old local rows do not undo external
effects. After database restore, retain maintenance/disclosure fences and reconcile desired config,
actual policy, Vault CURRENT and outstanding password/key obligations under the existing manual procedure.

## Password disclosure and rotation

Recheck entitlement, exact binding and verified current boundary before disclosure. Commit audit,
notification intents and durable password rotation under credential-head serialization before returning
the password. D40's first authorized disclosure attempt starts the original four-hour clock, including
lost responses; concurrent requests/retries never extend it. Resolve the verified password via Vault
CURRENT. At deadline stop disclosure and rotate child password/Vault version through the existing
recoverable sequence. Unknown effects remain unresolved/overdue with urgent notice and same-account
manual recovery. The standing boundary and exemption remain in place when the password window closes.

## Thirty-day OTM API-key policy

Every active signing key on each registered OTM-managed automation identity has a maximum active age
of 30 days (2592000 seconds). Inventory all registered child automation identities; apply the same
policy to registered long-lived parent/hosting API-key credentials where OTM has explicitly qualified
rotation authority. Workload identities have no static API key to rotate. Bootstrap keys must be
retired after verified handoff, not kept for a 30-day cycle. This policy does not authorize management
of arbitrary employee/customer keys, SSH keys, SMTP credentials or application passwords.

Set the retirement deadline from trustworthy provider key creation/upload evidence, or earlier known
key-material creation time; activation, observation, failed rotation and app restarts do not reset it.
An unknown-age existing key needs prompt replacement and visible qualification status, not a new
30-day lease inferred from discovery. Inventory unexpected active keys on a bound automation account;
require an owned disposition and do not declare that account compliant while unmanaged/overdue keys
remain. Never delete an unrelated key merely because it is occupying a slot.

Proposed scheduling default: start one day before the deadline (day 29), with a bounded existing
CronJob fan-out scanning at least hourly and jittering work per credential. The user-selected maximum
remains 30 days; this is not a calendar-month or 'attempt every 30 days' schedule. Reuse C2's native
jobs, credential generations and operation/step records. Admission deduplicates each original
credential generation/deadline; restarts and overlapping scans resume that operation. No second
rotation daemon, central controller or separate scheduler table is required.

### Replacement sequence

1. Recheck exact principal/domain/tenancy, current fingerprint, privileges, key capability, original
   deadline, restore fences and provider key-slot inventory. Serialize rotations per bound principal;
   never hold a database transaction open around network calls. Keep recovery-password rotation runnable
   through a verified signer and prioritize urgent closure over routine key work.
2. Generate a fresh key pair in bounded process memory. Persist the private PEM as an exact recoverable
   staged Vault version before uploading only the public key. Record only nonsecret fingerprint,
   key-resource ID, context, version and correlation evidence in the application database.
3. Add/read back the exact candidate. OCI documents a three-key-per-user limit; leave room for the
   replacement and never delete the sole working key to free a slot. If an upload response is lost,
   reconcile that same public-key fingerprint before another upload. Full or unexplained slots
   require attention; do not silently remove an unknown key.
4. Build a new independent SDK signer from that exact staged private version and fingerprint. Verify
   required OCI and identity-domain capabilities through qualified safe probes; listing a public
   key or succeeding at one unrelated GET is not proof of operational authority. No implicit old-key
   fallback is allowed to make this probe appear successful.
5. Atomically publish the verified active version/generation with audit under compare-and-set guards.
   All new attempts resolve that exact binding. Bound in-flight old-key use must drain/reconcile before
   retirement within the original deadline. Do not keep an old SDK client cached indefinitely or
   replay an ambiguous destructive call with the new key as a new operation.
6. Use the verified replacement to delete only the managed old key and verify its absence plus the
   new signer's continuing access. Keep the rotation operation unresolved if old-key removal is
   unknown or fails; a successful current-pointer switch alone is not completed rotation. Remove all
   retiring managed keys by their original limits. The next version's deadline comes from its own
   original creation/upload time, not from completion of old-key cleanup.
7. Once provider retirement is verified and no accepted operation legitimately needs the old private
   version, retire its ordinary resolver eligibility and schedule secret-version deletion under the
   approved Vault retention/recovery procedure. Keep nonsecret immutable audit/version evidence.

Existing accepted operations retain intent and target identity while dispatch rechecks current
authority and credential generation. Keep overlap bounded by the original 30-day limit. If new-key
verification fails before activation, retain the known working key while still within policy and
reconcile/clean the known candidate; do not destroy recoverability. A compromised key follows urgent
incident revocation, not the routine overlap policy.

At/after an uncompleted retirement deadline, report the actual key as overdue, alert administrators
and block ordinary new provider work through overdue/unverified material. Permit narrowly scoped,
audited rotation/reconciliation and independent recovery so expiry guards do not prevent their own
repair. OCI API keys do not automatically expire because OTM records a due time; a failed deletion
can leave an externally usable overdue key and must not be described as enforced provider expiry.

## Model and user-facing implementation work

Extend the existing config schema/provenance, managed bindings, credential versions and operation
evidence only as needed; no executable migration/schema is added here. Record desired/applied boundary
fingerprints and exact rule/perimeter/user IDs. Key creation/deadline and unresolved retiring-key evidence
stay on the owning credential/version; never overload password exposure deadlines.

Proposed key settings remain maximum age 2592000 seconds, prepare lead 86400 seconds and bounded hourly
fan-out. Implement strict bounds and adjacent comments with code. D54 CURRENT is for recovery passwords;
API keys retain exact Vault versions/fingerprints.

Recovery access explains the approved-network requirement and original password-rotation deadline;
it never claims per-window MFA activation/revocation. Public sign-in errors expose no configured ranges.
Only authorized operators see the list through private release preflight. Runtime UI changes cover
recovery guidance and convergence status in existing Operations, using Field Console and accessible
status text; CIDR editing/approval remains in the operator release procedure. Cancelling
before acceptance has no effect; navigation afterward does not cancel durable work. Password appears
only on the authorized non-cacheable disclosure surface, never status UI, logs, exports or ordinary errors.

## Provider evidence and outstanding qualification

Oracle documents IPv4/IPv6 CIDR perimeters and console sign-on conditions/actions. These support the
mechanism, not proof of exact policy precedence, authority, safe updates or our VPN routes:
[network perimeters](https://docs.oracle.com/en-us/iaas/Content/Identity/networkperimeters/overview.htm),
[sign-on policies](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/add-sign-policy.htm).
GitHub documents `vars` inputs mapped into job `env`:
[Actions variables](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables).

Candidate domain perimeter/policy/rule and key create/get/list/delete calls require qualification of
SCIM IDs, payloads, ETags, permissions and signer interoperability against the selected dependency pin:
[IdentityDomainsClient](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html).
This does not alter chapter08's older pinned inventory or certify the latest SDK as deployed.
Oracle documents at most three signing keys and IAM upload/delete primitives:
[signing keys](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm),
[IdentityClient](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/client/oci.identity.IdentityClient.html).
Legacy IAM/domain identity and key IDs are not interchangeable. No live mutation was run.

## Required acceptance scenarios

| Scenario | Required result |
| --- | --- |
| Multiple approved CIDRs | Same recovery user signs in without MFA from each qualified source; denied outside, including other IP-family/proxy/split-tunnel paths. |
| Other identities | Owner/member/general-admin and OTM-local MFA unchanged. |
| Creation/recreation/import and later recovery validation | Exact-user exemption and current deny-outside rules verified before readiness; presence alone never passes. Re-enabled MFA, widened rules or incomplete reads surface drift/Unable to verify and block new disclosure. |
| Empty/missing/malformed/host-bit CIDRs or unrestricted union | Entire candidate rejected; no permissive fallback or partial list; fixtures/artifacts synthetic. |
| Priority, broad fallback or unexpected membership | Exact-user deny-outside before readiness; wrong scope blocks without widening unrelated access. |
| Config-only release/concurrent application release | Deployed schema validates; protected environment/lock, retained image, consistent checksum; variable edit alone has no live effect. |
| Widening/narrowing, rollback and partial fleet failure | Reviewed delta/consent; desired/applied evidence separate; failed narrowing visible with affected disclosure blocked. |
| Old queued/in-flight update | Stale known-unsent work blocked; unknown original reconciled before successor, no false convergence from a single read. |
| Setup/import/new child/retained recovery identity | Current restriction before readiness; retained identities never silently skipped. |
| First disclosure, joins, lost response and deadline | Original D40 clock and durable password rotation; boundary/exemption persist; no universal logout claim. |
| OTM/automation/VPN unavailable or database restore | Same-account manual custody and explicit VPN dependency; maintenance reconciliation; no new account/public bypass. |
| Day29/day30, duplicate scan and unknown key age | Original creation-based deadline; one rotation per generation; discovery never resets age. |
| Full slots, unknown upload or failed signer probe | No sole-working/unowned deletion; exact candidate reconciled and independently verified without fallback. |
| Activation race, old in-flight call or retirement failure | Bound drain, exact verified deletion, unresolved old-key obligation retained; overdue repair available. |
| Secrets and CI output | Password only on protected disclosure surface; no secret/configured corporate CIDRs/private operational files in public artifacts or logs. |

Implementation requires D53 complete-source unit coverage, disposable PostgreSQL concurrency tests,
simulator fault injection, meaningful Playwright flows and D56 review/scans. Live disposable-child
policy, actual egress, update propagation, API authority, session and signer tests remain separately
pending. No static/simulator check establishes those provider outcomes.


### Read-only recovery assignments — 9 November 2026

[Required-user assignments](../reference/administrator-assignments.md) now inspect recovery group
and domain administrator role grants independently of automation grants and recovery console policy.
Assigned means those two simulated assignments only. It does not implement password retrieval,
Vault custody, a recovery signer fallback, or the durable four-hour rotation flow. Credential
disclosure remains unavailable until custody and rotation qualify together.


### Perimeter-only repair source subset — 9 November 2026

[Guarded recovery-network repair](../reference/recovery-network-repair.md) is locally qualified in simulation,
with preserved main publication recorded in the [final receipt](../history/recovery-network-repair-checkpoint-2026-11-09.md). Real OCI remains pending. It replaces only the retained perimeter's CIDR list
under exact scoped authority and a conditional compare token, preserving all rules and the standing
exact-user exemption. The latest sealed policy observation pins actual before-state; setup/last-repair capture authenticates
ownership/bindings rather than freezing networks forever. Fresh preview and first worker authority
must match that observation; preview counts come from fresh authority. Unrefreshed third states,
changed before-state or a changed persisted compare token block dispatch. Preview exposes counts/hashes only; explicit unchecked acknowledgment is
required. Readback must verify networks and unchanged surrounding policy. Applied-but-superseded
capture is retained without current readiness; unknown writes remain held without automatic retry.
No assignment repair, MFA/rule edits, user recreation, password custody/rotation or fleet rollout is
implemented by this subset. Migration 0026 extends existing constraints with zero new tables.


### Password source subset — 9 November 2026

The [current custody/disclosure/rotation source subset](../reference/recovery-password-access.md) is
an implemented local subset; [the checkpoint receipt](../history/recovery-password-checkpoint-2026-11-09.md) records qualification and main8443 installation separately. It preserves the standing exact-user MFA/
CIDR boundary, CURRENT and the original first-attempt four-hour deadline. API-key retirement, live
provider qualification and deferred interactive network break/repair remain separate pending work.
