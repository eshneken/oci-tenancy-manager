# Recovery-password custody, disclosure attempts and rotation

9 November 2026 · Implemented local simulator subset; qualification and saved-install status are recorded separately

[Accepted access design](../engineering-design/13-local-support-and-emergency-access.md) · [Source ER](../architecture/diagrams/recovery-passwords-implemented.mmd) · [Model](../engineering-design/11-production-data-model.md#recovery-password-source-subset--9-november-2026) · [Live manifest](../how-to/real-oci-test-manifest.md)

This is a source field dictionary, not a release receipt or instruction to change saved data.
The [checkpoint receipt](../history/recovery-password-checkpoint-2026-11-09.md) is authoritative for qualification and saved-install status.
That receipt now records final local qualification and preserved installation on main 8443. Manual
review below uses only a new normally created/imported simulated child; older children stay Not prepared.
Main 8443 remains the sole review application; the retired 8444 instance must not be recreated.
This reference does not itself establish saved-app installation or real OCI/Vault qualification. Interactive
recovery-network break/repair testing remains deferred until an approved real OCI child is available.

## Current bounded flow

New onboarding version4 adds `prepare_recovery_password` after permanent-user capture/configuration
verification and before `retire_temporary`. The onboarding transaction admits a setup operation and
credential head, enqueues the fixed native task, then waits with `onboarding_password`. The child
remains pending. Only coupled staged-custody/child-password/CURRENT verification permits the parent
to resume and retire temporary access. Versions1–3 keep their accepted graphs and historical bytes.
Existing registrations receive no inferred password, custody head, setup replay or automatic backfill.

Explicit local composition supplies the simulator. Its private, operator-owned file custody is not
OCI Vault, a production fallback or a real child account. Secret values stay outside PostgreSQL,
audit, queue arguments and ordinary API projections. No account, MFA exemption or policy is created
by opening an access view. The standing exact-recovery-user exemption/CIDR boundary remains separate;
this subset does not toggle MFA, enroll a factor, create another recovery user or broker TOTP seeds.

For disclosure, the application requires current administrator entitlement, active registered child,
exact current recovery binding, compatible usable custody, fresh independent user presence, recovery
group/domain-role assignments and verified recovery console controls. Positive existence alone is
insufficient. Missing/stale/unknown controls, overdue windows, uncertain rotation or unexpected CURRENT
block disclosure. The automation context performs machine work; the human recovery user never becomes
a fallback signer. Rotation uses current system/machine authority, not the requester's continuing login.

## Original four-hour exposure window

The first authorized server disclosure attempt commits its append-only request, audit, notification
intents and one due rotation operation **before** reading CURRENT and before releasing any password.
Its timestamp fixes the shared due time at exactly+14400 seconds, including a lost response or failed
secret acquisition. New intentional requests have separate receipts/notices but join the same root,
version, exposure generation and original deadline. A matching request-key replay cannot open a new
window or return a later version. No extension, early-end session feature or universal logout is claimed.

Normal retrieval resolves the stable secret's CURRENT selector and checks the actual immutable version
against reconciled custody evidence. The stored current-version pointer is not a historical fallback.
An unexpected returned CURRENT version holds the head for reconciliation. Transient CURRENT
acquisition failure instead returns503 after durable request/window admission, leaving the usable
head and original deadline intact for deliberate same-request retry. Entitlement, exact
binding, current readiness and the unchanged deadline are rechecked after the external read and before
release. A later requester revocation cannot cancel an already committed system rotation obligation.

Setup/rotation stages a recoverable candidate before the child password write. Only exact candidate
verification against the child and conditional CURRENT promotion/readback permit successful publication.
Vault success or a user GET cannot prove the child password matches. Unknown writes preserve candidate
references and the original obligation; they do not authorize blind resets or historical-password release.
Due work acquires child exclusion at execution, rather than locking ordinary tenancy work for four
hours. Delayed/blocked work does not extend the original deadline. Restore follows D54's paused manual
reconciliation, not an external journal/epoch service or automatic replay.

Audit kind `recovery_password_disclosed` records an **authorized disclosure attempt**, not proof that
a password reached a browser. No audit/notification includes its content. Disclosure notices target
other administrators and the owner/direct manager; they exclude designees and exclude the requester
from the other-administrator audience. Failure notices use administrator routing. Existing role/contact,
environment, frozen-recipient and delivery checks apply; transport acceptance is not inbox delivery.

## API and public fields

| Boundary | Fields and behavior |
| --- | --- |
| `GET /api/tenancies/{identifier}/administrator-access` | Metadata-only `RecoveryPasswordView`; no initialization, provider mutation or secret resolution |
| `RecoveryPasswordView` | `tenancy_id`, `tenancy_name`, optional `user_name`, `state`, `available`, optional `preview_hash`, `first_disclosure_at`, `rotation_due_at`, `operation_id`, explicit simulated `provider_mode` |
| Public states | not_prepared, preparing, ready, exposed, overdue, rotating, attention, unavailable, inactive; these describe this source subset, never live OCI readiness |
| `POST /api/tenancies/{identifier}/administrator-access/password` | `RecoveryPasswordRequest`: request UUID, preview hash, explicit acknowledgment; no caller-selected secret/version/user/clock |
| `RecoveryPasswordDisclosure` | `request_id`, `user_name`, transient `password` (32–256 characters, redacted representation), `first_disclosure_at`, `rotation_due_at`, `operation_id`, simulated `provider_mode`; authenticated last-mile conversion only |
| Cache controls | Metadata, disclosure and handled error responses use no-store/no-cache/Expires0; no password belongs in URLs, persistent browser storage, logs, screenshots or exports |

Dialog consent, visibility, copy handling and focus are client state, not new database columns.
`RecoveryAccess.tsx` is source-composed as a separate Administrator access mini-panel below the
Automation user card. It still retrieves only the exact recovery account’s password; placement does
not change signer or authorization semantics. Regression qualification
and saved-preview publication are established only by the checkpoint receipt, not UI source/DTO availability.

## Physical field dictionary

Migration **0027_recovery_passwords** adds three tables to the prior25 OTM application
tables: **28 source-metadata OTM tables**, excluding separately owned queue tables. This does not
assert installation in the saved main database. Existing operation/audit/step constraints extend to
the password capability and version4 onboarding step. No separate rotation service or queue store is added.

| Table | All physical fields |
| --- | --- |
| `otm_credential` | `id`, `workspace_id`, `tenancy_id`, `principal_binding_id`, `source_operation_id`, `location`, `location_hash`, `state`, `generation`, `current_version_id`, `staged_version_id`, `exposure_generation`, `first_disclosure_at`, `rotation_due_at`, `active_window_grant_id`, `rotation_operation_id`, `created_at`, `updated_at` |
| `otm_credential_version` | `id`, `workspace_id`, `credential_id`, `version_number`, `reference`, `reference_hash`, `created_operation_id`, `created_at` |
| `otm_human_access_grant` | `id`, `workspace_id`, `tenancy_id`, `credential_id`, `disclosed_version_id`, `requesting_subject`, `requester_snapshot`, `request_key`, `payload_digest`, `accepted_operation_id`, `window_root_grant_id`, `exposure_generation`, `accepted_at`, `first_disclosure_attempt_at`, `due_at` |

The credential head owns current mutable custody/window state; versions and requests are immutable
nonsecret evidence. One active head per tenancy and one head per exact bound principal prevent
competing exposure engines. Scoped FKs bind child/principal, operation, same-credential versions and
root request; deferred pointer FKs allow atomic insertion cycles. Versions are unique by credential/
version number, request keys by workspace/requester, and provider secret references cannot be shared
across credentials. Current/staged pointers must differ. Original-window constraints enforce four
hours. Due/history indexes support the existing runner and history; these are not extra schedulers.

`location` is typed `PasswordLocation`: credential ID, exact recovery `RequiredUserTarget` and nullable
`secret_reference`. Setup starts without a fabricated provider locator; staging allocates the actual
simulated reference and persists it. A usable `PasswordVersion` always has a bound location, immutable
`version` and creating `operation_id`. Hashes authenticate location/reference JSON. The purpose/domain/
SCIM/OCI/binding-generation distinctions come from the existing typed target, not guessed names.

## Durable JSON and existing records

| Record | Typed fields / source |
| --- | --- |
| `RecoveryPasswordIntent` | contract/kind, workspace, setup-or-rotation phase, credential/generation, exact location/target, onboarding operation, expected CURRENT reference, exposure generation, original optional due time |
| Operation/step | Existing system operation kind `recovery_password`; step `recovery_password:{credential UUID}`, attempt/execution references and nonsecret candidate/machine-context inputs; native queue passes operation reference only |
| `RecoveryPasswordEvidence` | contract version, credential/tenancy/operation, phase, state/effect/safe code, checked time, optional exact verified/superseded version reference |
| `RecoveryDisclosureEvidence` | contract version, grant/credential/tenancy/version/root IDs, exposure generation, first/due timestamps, fixed duration14400 and first-authorized-disclosure anchor |
| `RecoveryPasswordNotice` | contract version, operation/tenancy/credential/grant IDs, requester subject, org/config revision, frozen recipient reasons/routing issues, original/effective contact, route/origin/profile hash, event, first/due times and creation time |

The proposed general credential/access model contains additional fields/types not implemented here.
This source subset adds no API-key custody/rotation and no legacy-account enrollment workflow.
Actual OCI/Vault allocation, password-change verification, MFA/CIDR sign-in behavior and independent
manual custody remain pending live qualification. Do not promote simulator evidence to live authority.


## Current dialog and future main-only manual review

Use these steps only when the [checkpoint receipt](../history/recovery-password-checkpoint-2026-11-09.md) records actual qualification and
deliberate publication to existing main 8443. Do not create another local instance;8444 remains retired.

1. Create/import a **new normal simulated child** through the existing Organization flow. Complete
   activation/handoff and reviewed cleanup. Version4 waits for custody verification before temporary
   cleanup. Older children deliberately remain Not prepared; do not rewrite their bindings/replay
   setup to backfill custody.
2. Select Refresh user data and verify current presence, recovery group/domain-role assignments
   and both recovery-console controls. Presence alone cannot enable access.
3. In the **Administrator access** mini-panel below Automation user, select **Request password**.
   Review the child, recovery username, state and local-
   simulation notice. This password cannot sign in to OCI. Missing custody/checks show guidance,
   not a configure/reset action. Access and cleanup instructions remain collapsible.
4. Check the acknowledgment and select **Get password**. The response is masked by default;
   **Show password**/**Hide password**, **Copy password** and **Close** are explicit actions.
   Never screenshot/export the value. Copy uses the OS clipboard, whose retention OTM cannot control.
5. Review original first-attempt/due times and **View password operation**. Audit History records
   the authorized attempt without plaintext; acceptance cannot prove browser delivery. Closing or
   signing out does not cancel system rotation. The operation link must reference the returned
   disclosure's rotation operation, not an older setup operation.
6. Close/reopen and make another consented request before due time: its request/audit ID differs,
   but the original four-hour deadline stays unchanged. An uncertain response uses **Retry same
   request**. Transient custody-read503 preserves that request/window; unexpected returned CURRENT
   requires reconciliation. No retry opens a replacement window.
7. Closing, navigation, page hiding, changed checks/target/readiness and deadline expiry clear page-
   held password state. Nothing enters query caches or persistent browser storage. A copied OS
   clipboard value is not guaranteed erased; no hard console logout is promised.
8. Observe rotation in Operations under the original deadline. Do not edit saved timestamps, custody
   files or data to accelerate a demo. Unknown/overdue results block disclosure. Deterministic time,
   concurrency and failure cases belong in disposable automated tests.

Consent, masking, copy feedback, dialog/focus, aborts and visibility are transient client state, not
new columns. API timestamps and operation IDs remain the display sources. No saved-main update or
complete integration result is established by these instructions; consult the checkpoint receipt.

## Local cleanup boundary

The three credential FK tables may participate in local cleanup only while empty. Retained credential
heads, versions or disclosure history refuse cleanup: reset cannot erase audit, custody evidence or
rotation obligations. Do not use local reset for migration, enrollment or secret deletion.


## Trusted worker admission permissions

Version4 setup requires the explicitly trusted local worker to INSERT into `otm_operation` as well
as credential heads/versions, so setup operation, custody head and continuation can commit atomically.
This is **table INSERT authority**, bounded by typed application/tenant/workspace guards; SQL grants
do not restrict insertion to a particular operation kind. Existing column-limited UPDATE remains.
No DELETE, intent-column UPDATE or owner-credential fallback is granted. Future hosted roles/CI must
carry and test the same positive/negative contract using actual installed worker-role connections.
Native permission-test results belong in the checkpoint receipt; they cannot by themselves qualify a hosted role.

The current UI source renders no form content while the dialog is inactive; consent exists only
inside the opened dialog. This presentation fix adds no permission or persistence field and does
not establish completed integration or saved-app publication.


## Access-panel and recorded-results follow-up

The current source places access in a separate mini-panel below Automation user, preserving the
paired user cards. The same component/dialog retains consent, transient password handling, original
deadline and all authority checks. New footer date links target the exact historical check kind and
subject in Operations, rather than a generic operation landing point. Historical results do not
certify current access or password readiness. See the [closed Operations field map](operations.md#recorded-required-user-check-sections--source-follow-up).

This follow-up’s passing combined validation and preserved main installation are [recorded separately](../history/recovery-password-checkpoint-2026-11-09.md#access-panel-and-recorded-results-follow-up).
The earlier440-case receipt and focused header-placement receipt keep their original scope; neither
automatically qualifies this newer source.


## Password operation progress — source follow-up

The Operations source now has a dedicated **Password preparation**/**Password rotation** panel
with recovery username, original first-request/deadline, authorized request count, operation outcome
and **Open tenancy**. Its [six-field read-only projection](operations.md#recovery-password-operation-progress)
comes from immutable intent and exact window-scoped request history, not the current credential head.
Attempts are not proof of browser delivery. No secret action, retry/reset or extension is added.
The panel’s [validation and saved-install status](../history/recovery-password-checkpoint-2026-11-09.md#password-operation-progress-follow-up) pass with the separately recorded full-run/final-copy targeted scope; earlier password behavior retains its own receipt.


## Signing-key metadata independence — source checkpoint

The separate observation-only inventory’s read-time/age fields do not invalidate the existing
password dialog. Current source excludes `automation_keys` from `checksRevision`, preserving
consent and displayed transient password across those independent updates. User identity, recovery
policy and other security-readiness changes still clear access under existing guards. No new stored
field, expiry extension or credential authority is added. [Targeted checkpoint qualification and preserved main installation](../history/automation-signing-key-inventory-checkpoint-2026-11-09.md) pass; broader live claims remain pending.


## Generated password candidates — 12 November 2026

Current source change; targeted bundle qualification PASS; saved publication PASS. Setup/rotation traces
through worker execution, custody staging and `SimulatedRecoveryPasswords.stage` to
`password_generation.generate_recovery_password`. New candidates are 32 characters selected with
cryptographic randomness from lower-case letters, upper-case letters, digits and the explicit special
set `!@#%+-_=`. At least one of each class is guaranteed; Fisher–Yates shuffle removes the old
predictable class prefix. The exact user name is excluded case-insensitively. Bounded candidate
rejection fails closed rather than returning a weak fallback.

This changes new candidate generation only. Existing 54-character CURRENT/candidate values and
idempotent stage/replay retain their original bytes; no secret reset, database edit or backfill is
required. Secret values still remain outside SQL/API/audit/logs. Meeting this local template is not
proof of acceptance under a child's effective custom policy, user-name restrictions or password
history. Actual OCI policy selection and password acceptance remain Pending live qualification.

Oracle's [CNC Console guide, section 5.2](https://docs.oracle.com/en/industries/communications/cloud-native-core/3.25.2.2xx.0/cnc_console_user_guide/cnc-console-user-guide.pdf) documents a Default PasswordPolicy (Custom) example with length 12–40, at least one lower/upper/digit, zero required special characters, name/username exclusion and four-password history. The 32-character template satisfies that example's length/class minima with a stronger special-character minimum; it does not establish universal OCI policy compliance. [OCI identity-domain policy guidance](https://docs.oracle.com/en-us/iaas/Content/Identity/passwordpolicies/Managing-Password-Policies_set-password-policies-your-identity-domain.htm) permits custom criteria and prioritized group policies. The generator does not know first/last names or password history; effective-policy/provider acceptance remains a required live check.

Targeted bundle evidence: [qualification scope](fleet-refresh.md#targeted-bundle-qualification--12-november-2026). Saved publication PASS.
