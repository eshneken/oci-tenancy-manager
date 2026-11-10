# Repair approved recovery networks

9 November 2026 · Qualified local simulated UI/integration checkpoint; main preview published; real OCI pending

[Recovery policy checks](recovery-console-verification.md) · [Selected design](../engineering-design/22-credential-security-lifecycles.md) · [Live qualification](../how-to/real-oci-test-manifest.md#recovery-network-repair-qualification)

## Narrow scope

This action conditionally replaces the network list on one retained, owned recovery perimeter for
one registered child. It preserves the exact recovery user, selector group, application, policy,
ordered rules and standing MFA exemption. It cannot edit MFA, rule priority/selectors, administrator
assignments, passwords, users or workload resources. It is not fleet propagation or user recreation.

A current complete check must establish recovery presence, a verified exact-user MFA exemption and
network-only drift. Missing/unknown/stale evidence, unsupported rules, unexpected group membership,
wrong ownership, unconfigured desired networks, a busy child or unavailable inspecting authority
block repair. Successful user presence/group reads do not establish write authority. The provider
must independently establish permission and ownership for this exact conditional perimeter update.

Preview and provider calls run outside database transactions. Before sending, the worker rechecks
current administrator entitlement, registered-child lifecycle, exact identity/connection generations,
source ownership/binding provenance, desired fingerprint and retained policy objects. The latest
sealed policy check supplies the actual-before fingerprint; setup or last-repair facts do not
substitute for a newer independent observation. Preview and first worker authority must both match
that sealed fingerprint. It uses a provider compare token;
a changed target is not permission to overwrite newer state. It does not remove restrictive rules
or create an unrestricted interval. The real adapter must separately qualify those properties.

## Screen and command flow

From tenancy detail → Required users, a confirmed eligible network difference offers
**Repair approved networks**. The modal shows the tenancy, current/replacement network counts and
safe fingerprints. The current count comes from fresh matching provider authority; the observed
fingerprint comes from the latest sealed check. It does not expose actual CIDRs or raw policy facts. The acknowledgment starts
unchecked and explains that replacement can restrict or expand recovery sign-in locations. Both
the UI and server require acknowledgment; cancellation before admission changes nothing.

- `GET /api/tenancies/{identifier}/recovery-network-preview` returns a bounded safe preview.
- `POST /api/tenancies/{identifier}/recovery-network-repair` accepts only request UUID,
  `preview_hash` and `acknowledged`; authority, source and networks are server-selected.
- Acceptance atomically records the existing operation/audit/queue continuation and reserves the
  child. A request retry recovers its own receipt; it does not authorize a second provider write.
- Operations tracks the one-shot conditional update and independently observed readback. Verified
  success requires the intended networks and unchanged remaining policy facts. It does not certify
  passwords, all privileges or live OCI access.
- After known completion, a separate user-data refresh acquires newly dated presence/policy results.
  Existing check history is not rewritten to manufacture a successful repair observation.

Unknown dispatch/write/readback effects remain held for independent reconciliation, with no automatic
write retry or ordinary Retry action. A known applied change whose context became obsolete retains
private applied evidence as superseded, without certifying the latest desired revision. Merely
navigating away cannot cancel accepted work or clear uncertainty. Manual reconciliation uses the
existing owned procedure; this slice does not add a reconciliation service or credential fallback.

## Fields and existing storage

Migration **0026_recovery_network_repair** extends existing operation-kind, audit-kind and step
constraint branches. It creates no table, column or competing ER model. The existing operation,
step, immutable audit evidence, child reservation and native queue carry this capability.

| Contract / record | Fields and meaning |
| --- | --- |
| `RecoveryNetworkRequest` | `client_request_key`, `preview_hash`, `acknowledged`; no CIDRs, credentials or caller-selected provider IDs |
| `RecoveryNetworkPreview` | `tenancy_id`, `tenancy_name`, `preview_hash`, `desired_fingerprint`, `observed_fingerprint`, `current_network_count`, `desired_network_count`, `expires_at`, explicit simulated `provider_mode` |
| `RecoveryNetworkIntent` | `contract_version`, `kind`, `workspace_id`, `administrator_id`, `authorization_revision`, exact `snapshot`, `source_check_id`, `source_hash`, desired/observed fingerprints, preview hash, exact `target`, `expires_at` |
| Source identity | `source_check_id` names the source check **operation UUID**, not the physical presence-check row ID; `source_hash` authenticates retained ownership/binding/producer provenance, not current before-state. `observed_fingerprint` pins the latest sealed actual policy check. The snapshot binds both exact subjects and the desired policy fingerprint. |
| Existing step `inputs` | Before dispatch, private `RecoveryNetworkAuthority`: exact command/context/target/binding/desired policy, `captured_at`, independently observed `facts`, `can_replace_perimeter`, `conditional_update`, `owns_perimeter`, opaque `compare_token` |
| `RecoveryNetworkEvidence` | `contract_version`, `operation_id`, `tenancy_id`, `snapshot`, `effect`, `state`, `safe_code`, `checked_at`, private `capture` |
| Result states | verified/known, blocked/none, unknown/unknown, superseded/known; exact capture exists only for verified or applied-but-superseded outcomes |
| Read projection | Later simulated reads reuse authenticated latest known applied capture; a desired revision alone never becomes observed provider state. Separate check dates and operation links retain their original meaning. |

Retained known applied captures are selected by the existing source check’s monotonic
`acquisition_sequence`, joining its operation UUID through the immutable repair intent. Equal wall
clock times or UUID ordering cannot select an arbitrary older result. The original intent/evidence
hashes and exact binding compatibility are checked; desired settings alone cannot replace capture. Retained capture establishes ownership/binding and
simulator continuity, not a requirement that actual networks still equal setup. A legitimate external
network edit can be repaired after a fresh complete check; an unrefreshed third state or a change
after admission blocks the write.

Private captures/authority can contain configured CIDRs and normalized rules. They remain in private
server-side evidence/backups; public Operations, APIs, audit exports and errors use explicit safe
projections. No plaintext password, key or MFA seed is introduced. Unknown effects retain the child
reservation; known outcomes release it. No new generic access-plan or credential table is required.

## Manual local checkpoint runbook

**Interactive recovery-network repair testing is deferred by the user until real OCI is available**
and an actual approved policy difference can be introduced and repaired. Do not create another local
instance or modify main settings/provider fixtures to manufacture drift. Main8443 is the only local
application; the former8444 instance has been [retired](../how-to/parallel-local-instance.md).

The complete430-case automated simulator qualification, independent responsive UI review and
preserved main publication remain valid in the [final receipt](../history/recovery-network-repair-checkpoint-2026-11-09.md).
This deferral concerns additional interactive qualification, not reversal of that automated evidence.
A healthy saved child need not expose Repair, and refreshing a legacy record does not backfill policy.

When an approved real OCI child becomes available, use the [pending live matrix](../how-to/real-oci-test-manifest.md#recovery-network-repair-qualification)
for actual break/check/preview/acknowledgment/repair/readback testing. Actual ownership, conditional
API authority, propagation and sign-in remain unqualified. No new local environment is required.
Password custody, four-hour rotation,30-day key retirement and broader repairs remain subsequent work.


## Live API surface and remaining qualification

Oracle’s [IdentityDomainsClient.put_network_perimeter documentation](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.put_network_perimeter)
(version 2.190.0 checked for this design) exposes a `network_perimeter` replacement payload,
`if_match` for conditional ETag matching and explicit `NoneRetryStrategy`. This verifies the documented
API surface only. It does not qualify our payload normalization, signer permissions, conditional
failure behavior, propagation, safe sign-on enforcement or any real provider adapter. No OCI SDK
dependency or live call is introduced. Local simulator qualification passes in the linked final receipt; live provider qualification remains pending.
