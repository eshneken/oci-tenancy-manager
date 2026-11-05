# 13: administrator password access and independent recovery

24 October 2026 | D40 accepted | Single V1 human-access flow; proposed design, no live OCI changes

[Design hub](README.md) · [Access model](11-production-data-model.md#identity-access-and-credential-model) ·
[Walkthrough](../walkthroughs/human-access-walkthrough.html#access-ready)

## Current decision and scope

V1 uses the persistent per-tenancy recovery account for occasional administrator console access.
There is one human-access flow, not a temporary named-account workflow followed by a second recovery
workflow. D40 supersedes the named-support portions of D19/D37. Named local support provisioning,
activation/MFA enrollment and scheduled account removal are deferred. Their earlier design remains
historical in the D38 source checkpoint, not an active V1 requirement.

Permanent automation and recovery remain separate users. Owners and shared members keep their local
identity-domain accounts and ordinary MFA requirements (D36). OTM administrators sign into OTM through
corporate SSO; that does not federate the child. D39 selects an MFA exemption limited to the exact
bound recovery identity, or a dedicated group containing only that identity. It does not exempt the
Administrators group, owner accounts or other users. Its actual scope, precedence and required console
operations must be qualified; a selected exception is not a verified deployed policy. My Profile/My Apps
can have separate enforcement and must not be assumed to inherit a console exception.

Each tenancy has a distinct strong password stored in an OCI Vault secret. Authorized retrieval is
audited and notified to other administrators and the tenancy owner/manager. The first authorized
server disclosure attempt, including a response the browser never receives, fixes rotation at +4 hours.
Repeated retrieval joins that same window without extending it. No extension or early-end session
control is introduced. The persistent account is not deleted after use; its password is rotated in
both the child and Vault. Rotation is not proof that all existing sessions or independently created
credentials have stopped working. Retrieval records identify who requested the shared password;
they do not provide exact attribution for every later action performed under the shared OCI identity.

## Product entry and interaction

From the selected tenancy, **Access** has two tabs: **Required users** and **Administrator access**.
The latter displays the bound account/domain, current readiness, password storage and one primary
**Get password** action. There is no temporary-account creation, enrollment or cleanup page.
**Recovery instructions** opens the independent recovery procedure. Detailed evidence stays behind
required-user Check details or in Operations, rather than filling the normal task page with prose.

1. Preview the exact registered child, bound recovery user, current entitlement and current verified
   credential/readiness. Display the username and verified domain label, not an arbitrary user picker.
2. **Get password** opens a focused confirmation with tenancy, account and rotation rule. Cancellation
   has no disclosure effect. Recheck current authorization and fences at acceptance.
3. Before release, atomically commit the authenticated retrieval request, audit, notification/outbox
   intents and durable exposure/rotation obligation. A request key/digest retry returns the same result
   identity and never opens another window. A separate retrieval gets its own audit/notifications.
4. Return only the exact usable Vault version through an authenticated non-cacheable response.
   The active screen shows the original first-attempt time and rotation deadline. **Get password again**
   preserves the original version/window/deadline, subject to current guards.
5. At or after due time, or while rotation is unresolved, refuse new disclosures. Scheduled durable
   work rotates and reconciles the child password and matching Vault version. UI time or a clicked
   acknowledgment cannot establish completion.
6. After verified rotation, a new authorized request opens a separate window on the new usable version.
   Prior versions are not exposed as a fallback. The account stays in place.

The preview contains no password, SDK request, clipboard write, email or actual job. The Show action
explains this; Copy is disabled. Seeded transitions demonstrate UI behavior only. Old support-* links
normalize to the one current entry without provisioning anything. Scenario controls stay collapsed.

## Exposure window and transaction invariants

The credential head is the canonical owner of `exposure_generation`, `rotation_due_at`, the root
request and `rotation_operation_id`. C2 operations/steps own provider attempts and durable execution.
`otm_human_access_grant` is the retained table name for disclosure request/window evidence, not an OCI
user, access-assignment owner or second rotation engine.

The root request establishes `first_disclosure_attempt_at`; `due_at` is that instant plus the captured
`duration_seconds=14400`. `deadline_anchor=first_authorized_disclosure` is a server-selected policy.
Joining requests reference the same credential, exact disclosed version, exposure generation, root and
deadline. Concurrent first requests serialize on the credential head. The durable due job and outbox
are committed before any credential can leave the server. A lost response or repeat browser request
cannot restart the clock. A command retry is distinct from a new separately audited retrieval.

The requester's entitlement is checked on every new retrieval. Revoking their OTM access prevents
further use of OTM but does not cancel a previously committed system rotation obligation. It also
does not by itself invalidate an already known shared password or child session. If the due worker
is unavailable, the original deadline remains overdue and visible; never relabel it as extended.

## Password rotation and uncertain effects

1. Capture exact child/domain/user binding, credential head generation and current version references.
   D54 normal retrieval resolves the stable secret OCID with `stage="CURRENT"`; capture the returned
   actual version for audit, rather than selecting the DB's historical version number.
   Verify this operation's authority and relevant restore/context fences.
2. Generate a strong replacement and stage it in Vault recoverably **before** sending the child write.
   Keep only nonsecret exact-version references and provider correlation in the application database.
3. Change the bound child's password through the qualified identity-domain facade. Any timeout or
   ambiguous response means unknown effect, not permission to generate another replacement blindly.
4. Reconcile the original attempt and qualify that the child password corresponds to the staged
   candidate. A successful Vault write, SCIM user read or changed timestamp alone is insufficient.
5. Promote the confirmed matching candidate to Vault CURRENT, then publish the observed version
   and credential head under guarded C2 completion. Promotion failure remains unresolved/blocked.
   Record verification/audit evidence and resolve requests for that window. Publish no successful
   state until the coupled outcome is known. Unknown state blocks disclosure, prior-version fallback
   and uncorrelated resets; independent recovery/manual reconciliation remains available.

If automation is removed, OTM cannot pretend it can rotate through a lost signer. Alert administrators,
retain the original obligation and use the approved independent recovery procedure. Database restore
must reconcile external Vault/child effects and later disclosures before releasing restore fences.
A restore cannot resurrect an old usable password or erase an outstanding exposure window.

## Proposed fields and screen mapping

This uses the existing proposed tables in [chapter11](11-production-data-model.md); it adds no new
table and no prototype migration. The production proposal remains 28 application tables.

| Record/field | Meaning and UI use |
|---|---|
| `org_tenancy.id`, `name`, `tenancy_ocid` and owner association | Exact selected tenancy, breadcrumb and notification target; an OCI identifier is not a display name |
| Recovery `otm_managed_object_binding` | Exact user, domain and operational assignment; persistent and separate from automation |
| Domain binding `domain_metadata` | Observed `display_name`, separately qualified console URL/provenance; do not guess a login URL from the SCIM API endpoint |
| Grant `requesting_subject`, `requester_snapshot` | Authenticated issuer/subject and immutable verified name/email provenance, not a caller-selected recipient |
| `request_key`, `payload_digest`, `accepted_operation_id` | Retry identity and accepted C2/audit correlation |
| `credential_id`, `disclosed_version_id` | Exact same-tenancy credential and same-credential Vault version; no password plaintext |
| `window_root_grant_id`, `exposure_generation` | Shared window for all retrievals of the exposed version; no separate per-request deadline engine |
| `lifetime_policy_version`, `duration_seconds`, `deadline_anchor` | Captured policy version, 14400 seconds and first-authorized-disclosure anchor |
| `accepted_at`, `first_disclosure_attempt_at`, `due_at` | Acceptance evidence, original attempted-disclosure time and immutable effective window deadline |
| Credential head `rotation_due_at`, `rotation_operation_id`, state/generation | Canonical due work, pending/unknown/verified progress and disclosure fences |
| Grant `state`, `verified_rotation_at`, `resolution_evidence_event_id`, `resolved_at` | Projection/evidence from verified credential rotation; never an editable success assertion |
| Credential/version Vault references and provider binding snapshot | Storage label and resolver/reconciliation context; no secret references need appear in the ordinary UI |
| Check/observation/issue evidence | Required user/grants, exact recovery-only MFA exemption and current credential readiness; Unknown is not Missing |
| Accepted audit/outbox routing snapshot | Requester, other admins and owner/manager notification intent; delivery status is separate |
| Versioned runtime recovery runbook reference | Approved independent procedure, permissions and custodian references; no fabricated URL |
| Dialog, focus, preview selector and busy indicator | Transient client state, not database columns |

No named-support `kind`, grant-owned assignment FK, access-check head, access generation, cleanup
operation or verified user-revocation timestamp is required on the V1 disclosure request. Association
or operational bindings own access assignments. Credential heads own rotation; immutable requests
retain requester/window/evidence. This avoids a circular grant/assignment ownership relationship.

## Screen states and source of truth

| Route | Visible status/actions | Required production source |
|---|---|---|
| `#access-ready` | Available; Get password; Recovery instructions | Exact verified recovery user/grants/sign-in exemption, reconciled usable Vault version and independent procedure |
| `#access-window` | Rotation scheduled; original timestamps; Get password again | Committed disclosure/window and current still-authorized usable version; never a client-generated new deadline |
| `#access-blocked` | Unavailable; View required checks; Recovery instructions | Incomplete/failed readiness, missing access, unresolved credential or restore fence; no disclosure |
| `#rotation-running` | Rotating password; Check rotation | Accepted original rotation operation, current attempts and canonical head; disclosure blocked |
| `#rotation-unknown` | Rotation needs attention; Check rotation | Unknown child/Vault effect; checks preserve uncertainty until qualifying evidence exists |
| `#rotation-complete` | Password rotated; Get password starts new window | Verified coupled outcome, current new usable version and resolved old exposure |

Required users is a separate observation/repair view. Its unqualified sample records link Administrator access to the blocked state, not Available. Matching user observations alone do not verify
console readiness or the MFA exception. A repair is offered only if fresh exact authority exists;
a missing/unverifiable automation signer cannot repair itself by clicking a button. A preview repair
acknowledges a queued example and leaves the issue until verified provider evidence clears it.

## Independent recovery and security boundaries

The application is not the sole credential-custody path. Authorized custodians need approved Vault
access, account/domain references and a runbook reachable when OTM, its SSO or automation is unavailable.
Record external use and reconcile/rotate the child password and Vault version before ordinary
retrieval resumes. Manual evidence is structured actor/time/target/source/checklist evidence, not a
button that claims a provider fact without verification. Independent custody permissions, recovery
exercises and post-restore release controls are production qualification/operations deliverables.

The recovery-only MFA exemption is the accepted V1 posture. Do not silently expand it, automatically
weaken normal accounts or add a central federation/TOTP mechanism. Observe its exact scope and group
membership for drift. Passwords remain unique per tenancy; never shared across the fleet. Real
password responses are exceptional, authenticated and non-cacheable; keep values out of URLs,
browser persistence, ordinary API/task results, logs, traces, exports, screenshots and notifications.
Neither the ordinary automation PEM nor bootstrap private PEM is a user-facing disclosure feature.

## Facade operations and planned verification

Use qualified identity-domain password, policy/readiness, credential-resolver and Vault primitives
behind chapter08/09's typed OCI facade. Keep semantic operations separate from provider method names.
The pinned SDK inventory is static design evidence, not proof of permissions, exemption behavior or
password verification. This change adds no unverified SDK call and performs no live provider action.

| Scenario | Required result |
|---|---|
| First retrieval response lost | One root window/deadline remains; idempotent retry cannot reopen or extend it |
| Concurrent/repeated authorized retrievals | Separate audit/notifications for new requests; same version/generation/root/original deadline |
| Cancellation or rejected authorization | No credential release; no false disclosure success |
| Due time reached or requester deprovisioned | Further retrieval denied; previously committed rotation persists |
| Vault staging fails | No child password mutation without recoverable candidate |
| Child write times out | Unknown effect, no release/promotion/blind reset; reconcile original attempt |
| Child changes but head publication fails | Preserve candidate/correlation and reconcile exact matching state before publication |
| Automation lost or application unavailable | Alert/retain overdue obligation; independent manual custody/recovery, no claimed automatic success |
| Restore predates disclosure/rotation | Deployment maintenance holds writes/disclosure/mail; resolve Vault CURRENT and manually review uncertain child/window state before administrator resumption |
| Verification succeeds | Resolve prior window with evidence; only a separate request opens new version/window |
| Other child admin changes recovery user/policy | Access/configuration issue, not an immutable-backdoor guarantee |

## D38 accepted product screens and separate design narrative

D38's app-shaped presentation remains accepted: concise task pages, focused dialogs, collapsed preview
controls, accessible keyboard/focus behavior and responsive layout. D40 changes the active content to
one administrator-access flow. Previous named-support screens and their D37 cleanup rules remain
historical/deferred. The D40 review and captures (private historical evidence; not distributed) record final verification against the single-flow sources.


## D54 accepted: Vault CURRENT and manual restore

Normal password retrieval uses `get_secret_bundle(secret_id, stage="CURRENT")` for the stable bound
secret OCID. Vault is the usable-password authority; record its returned version in existing
credential/grant/audit evidence. Do not request LATEST or an old DB version for ordinary disclosure.
A CURRENT change during an outstanding exposure window requires reconciliation, not a reset timer.
Unknown/in-progress rotations still block disclosure until the coupled child/Vault outcome is known.
API signing keys retain their fingerprint/version contract. See [the simple restore procedure](17-recovery-and-release.md).
