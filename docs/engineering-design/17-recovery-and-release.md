# 17: simple V1 credential resolution and manual restore

26 October 2026 | D54 accepted | Replaces the withdrawn C6-A control/journal proposal

[Design hub](README.md) · [Platform plan](06-platform-and-delivery.md) ·
[Credential model](11-production-data-model.md#identity-access-and-credential-model) ·
[Administrator access](13-local-support-and-emergency-access.md)

## Accepted boundary

The [7 November security refinement](22-credential-security-lifecycles.md) selects a standing
recovery-only MFA exemption with configurable console CIDRs and 30-day key retirement. It preserves
D54 CURRENT password lookup, exact API-key version/fingerprint resolution and same-account manual
restore; reconcile actual network policy and outstanding rotation effects before resuming.

Normal password retrieval uses the tenancy's **stable Vault secret OCID and `CURRENT` version**.
PostgreSQL records workflow/audit information; an old database version pointer does not select an
old password. Database disaster recovery is a documented administrator procedure. V1 does not add
an external recovery coordinator, control bucket, receipt journal, dependency-snapshot archive,
per-dispatch Object Storage calls or independently signed release manifests.

The user accepted this simplification on 26 October 2026. D12 still means stop old processes, restore
paused, manually inspect uncertain effects and explicitly resume reviewed work. D51/D52 remain
15-minute RPO/4-hour RTO engineering targets for in-region recovery, measured against this manual
procedure. D53's 95% unit-only coverage, Playwright, Docker DB and protected-master gates are unchanged.
No new table, prototype migration, runtime feature or production qualification is claimed here.

## Password resolution and rotation

| Operation | V1 behavior |
|---|---|
| Normal authorized retrieval | Resolve the registered credential's stable `vault_secret_ocid`; call `get_secret_bundle(secret_id, stage="CURRENT")` through the facade. Enforce entitlement, access readiness, disclosure audit/window and rotation state first |
| Returned version | Record the actual returned version as audit/disclosure evidence. Do not pass the database's old `vault_version_number` for normal recovery-password retrieval |
| Begin rotation | Generate a replacement and store it as a recoverable staged/PENDING version; retain that exact candidate reference in the durable operation |
| Apply replacement | Change the exact bound child's recovery password; resolve a timeout/unknown outcome through that same operation, not an unrelated new reset |
| Complete rotation | Confirm the child change, then promote the candidate to CURRENT. Update observed version/history and close the original exposure window only after completion |
| Interrupted rotation | Block disclosure while child/CURRENT state is uncertain. Resume the known operation or have an administrator reconcile; never pick LATEST or fall back to an old version |

Oracle's [Secret Retrieval SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/secrets/client/oci.secrets.SecretsClient.html#oci.secrets.SecretsClient.get_secret_bundle)
supports stage selection and defaults to CURRENT when a version selector is omitted. LATEST is not
substituted: the newest version may be a candidate rather than a usable password. The secret OCID
identifies the secret across versions. Actual password-change/promotion behavior still requires pilot
qualification; a successful Vault write alone does not prove the child changed.

The existing `otm_credential_version.vault_secret_ocid` supplies the stable locator through the bound
credential/version relationship. Reuse that OCID for all password rotations. Existing
`current_version_id` means the last reconciled version record for a recovery password; it remains
useful evidence but is not an instruction to retrieve that historical version. `staged_version_id`
identifies an in-progress candidate. No redundant new secret-locator table/column is needed.
A secret replacement/rebinding is an explicit audited action, not automatic fallback by display name.

The four-hour exposure rule remains. Each authorized retrieval records the actual disclosed version;
repeated requests in an active window retain the original deadline. If Vault CURRENT changes during
an outstanding window, block disclosure until the credential/window state is reconciled. Do not
silently open a fresh four-hour clock. API signing-key selection retains its existing independently
verified fingerprint/version contract; this decision simplifies recovery passwords only.

## Manual database restore runbook

1. **Stop and pause.** Stop the old API, workers, mail dispatcher and scheduled triggers. Confirm old
   processes cannot keep making changes. Configure the replacement deployment's maintenance/read-only
   mode **outside the restored database**, with workers/dispatchers/triggers suspended before startup.
   This is an ordinary deployment setting, not a separate control service or runtime object store.
2. **Restore and check.** Restore managed PostgreSQL/PITR and verify the new endpoint, TLS, schema,
   roles and runner compatibility. Revoke all restored OTM app sessions using existing session state
   and require fresh corporate SSO/current entitlement; a revoked session must not become valid again
   because its revocation row was rewound. Record the selected restore point and incident/readiness
   times. Read-only screens may be available; no mutation, password release or email is allowed.
3. **Inspect restored pending work.** Use the existing Operations state/audit to hold all restored
   nonterminal work for review. Old queue deliveries cannot dispatch those held operations. Review
   recent create/import/delete/config/access effects using OCI, Vault and available logs. Completed
   effects must not be repeated; unknown effects stay held. Missing history is documented, not invented.
4. **Check credentials and notifications.** Read Vault CURRENT rather than replaying historical
   password pointers. Review PENDING/interrupted rotations and known exposure deadlines; verify or
   manually rotate uncertain affected credentials before allowing disclosure. If disclosure history
   was lost, record uncertainty and use conservative manual credential recovery. Do not automatically
   resend restored pending/uncertain messages; review delivery evidence and explicitly send only when safe.
5. **Resume deliberately.** Record the administrator's review and selected actions in existing audit
   and operation state. Resume/cancel/recreate only reviewed work under normal target/version/identity
   guards. Turn off maintenance and restart workers only after held work cannot replay automatically.
   No blanket queue replay and no special independent release CLI/manifests are required.

An operator can keep uncertain targets held while resuming independently safe work. If old processes
cannot be stopped or the state cannot be verified, remain paused and obtain operational help. A normal
API/worker restart without a DB restore follows the existing durable-job behavior automatically.

This runbook does not guarantee that all audit/workflow evidence survives a restore. Up to the accepted
RPO gap can require manual reconstruction. The 4-hour recovery target is a drill target, not permission
to bypass checks. Password exposure deadlines retain their original anchor; urgent recovery during
an outage is manual if automation is unavailable. No promise of zero lost history, exact-once external
effects, hard session logout or an automatic regional-disaster solution is introduced.

## Minimal model and deployment mapping

| Information | Existing location |
|---|---|
| Secret locator and observed/staged versions | `otm_credential_version.vault_secret_ocid/vault_version_number`, credential current/staged pointers; CURRENT comes from Vault at retrieval |
| Disclosure/window/deadline | Existing credential/grant fields and immutable audit; no external exposure journal |
| Pending/uncertain rotation or other work | Existing operation/step state, exact candidate/correlation and ordinary retry/reconciliation guards |
| Restore pause | Deployment maintenance setting and suspended processes/triggers, not a database-controlled auto-resume flag |
| Restore review and selected work | Existing recovery operation/audit data and operation `recovery_release_event_id` where needed |
| Recovery objectives and measurements | Existing runtime-policy objectives plus documented drill/review evidence |

The unused workspace-level `recovery_epoch/recovery_state/recovery_release_event_id` mirror proposal
is removed from the current model/ER. Ordinary operation/configuration/credential generations remain:
they protect normal concurrent work and are not the withdrawn external recovery mechanism.
The proposed application table count remains 28 (10 existing plus 18 additions); tables are introduced
only as their feature milestones need them, not all at once merely to satisfy a diagram.

## Planned tests and qualification

- A restored old version record still resolves the same secret's CURRENT password; record the actual
  returned version. LATEST/PENDING/historical versions cannot be normal disclosure fallbacks.
- Candidate staging failure makes no child change. Child/Vault promotion failure leaves an uncertain
  rotation held until resumed or manually reconciled. Exact candidate versions remain available.
- Original four-hour windows, concurrent retrievals, revoked entitlement and unexpected CURRENT
  changes retain their existing guards. No historical password is disclosed from an old DB pointer.
- Restore with workers/dispatcher disabled; prove a stale queued job cannot execute held work. Review
  already-completed creates/deletions/rotations and accepted/uncertain email without blind replay.
- Reject restored app sessions, including one revoked after the backup; fresh SSO/current entitlement
  is required without an external session-cutoff service.
- Rehearse the manual in-region restore, including API maintenance behavior and deliberate resumption.
  Measure both restored-read availability and safe service against D51/D52. No live drill has run.

No additional reference controller/schema/checker is maintained for the withdrawn proposal. Production
unit, Playwright and disposable PostgreSQL tests cover the actual implementation under D53. The
facade/simulator must model CURRENT selection, interrupted rotation and restore-maintenance behavior;
the design cannot stand in for provider permission or actual managed-service qualification.
