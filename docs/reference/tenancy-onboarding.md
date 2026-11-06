# Guided tenancy onboarding

Guided local simulator implemented · Version 3 adds permanent-user capture in source · Saved previews remain on their installed revision · Real OCI remains unqualified

[Journey design](../engineering-design/07-onboarding-journeys.md) ·
[SDK call map](../engineering-design/08-oci-sdk-call-design.md) ·
[Registry and field guide](organization-workflows.md) ·
[Implemented ER](../architecture/diagrams/organization-workflows-implemented.mmd)

## Try the local journey

1. Ensure Configuration has a published baseline. Only the latest published version in this
   workspace is the automatic default, including publications already present before the upgrade.
   No separate selection or new publication is required merely to adopt that latest existing recipe.
   Open an employee's associations or new-employee review.
   Choose Create tenancy or Import tenancy
   and select Individual/Shared. Create requires a requested tenancy name and home region before
   submission. Import asks for an exact simulated child OCID and discovers its existing metadata.
   The dialog shows the selected published simulated baseline; acceptance freezes it for that operation.
2. Follow View operation. The worker pauses at Administrator action required. The pending tenancy
   detail also contains this setup panel, so Operations is not the only way back to the work.
3. Choose Use simulated handoff to populate sample tenancy/bootstrap user OCIDs; create also includes
   the activation administrator's exact user OCID. Verify handoff. To test a failed verification,
   change the bootstrap ID to another `ocid1.user.oc1..otmsim...` ID first; correct it afterward.
4. The worker records discovered name/home region, parent, domain and OCI/SCIM account bindings.
   It pauses again for review. Refresh/reopen retains the same operation and verified facts.
5. Review the exact temporary accounts, explicitly confirm their cleanup, then Start setup.
   The worker establishes and independently checks permanent automation, models owner/recovery
   access, and checks required access. New version 2/3 work then applies and reads back the frozen
   baseline's four managed categories, reprobes automation/required access, and only then retires
   temporary access. Import preserves
   existing human administrators; create retires only the verified activation account.
6. Local setup verified activates the owner association. Owner first sign-in remains unconfirmed.
   The review does not return on ordinary subsequent feeds.

For **app-initiated creation**, requested name and home region are required before the operation
starts. Oracle's [Python SDK model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/tenant_manager_control_plane/models/oci.tenant_manager_control_plane.models.CreateChildTenancyDetails.html)
requires tenancy_name, home_region, parent tenancy OCID and administrator email. The name must use
lowercase letters/numbers; local validation does not establish global availability. The home region
must be one of the configured parent's subscribed regions. The first screen starts with neither
field selected. The API repeats validation before any operation/reservation/audit/job write.

The local facade supplies three **simulated** parent-subscription choices through
`PersonWorkflow.creation_regions`; these are fixtures, not queried OCI facts. The real adapter must
read parent subscriptions through the parent credential context (IdentityClient.list_region_subscriptions).
Admission rechecks the current server-owned choices, never a browser-provided allowed list.

Requested metadata is frozen in original operation intent. Handoff later reads and verifies actual
metadata through the bootstrap context; discovery complements the original inputs. Activation
instructions must not say the administrator first chooses the home region/name at that stage.
The simulator reads back the requested create region, including Phoenix, rather than hardcoding
Ashburn. It preserves compatibility for already accepted intents with missing historical metadata.

Import does not take requested name/home region. Even legacy API fields do not overwrite imported
metadata: the new intent stores null requested values, the pending registry has Pending setup /
Pending discovery labels and a synthetic OCID reservation, and inspection replaces those labels
with its simulated read-back. No simulator reservation is proof of an existing OCI child.

Every screen explicitly says Local simulation. This slice sends no activation email, issues no
usable public/private key, creates no IAM objects, stores no tenancy passwords and calls no OCI SDK.
`public_key` is null. The local recovery administrator has no verified corporate mailbox; show Not
configured instead of inventing one. A baseline is selected and pinned at new admission. New version 2/3 work also applies/reads back its
four authored categories in the local simulator and then repeats access checks. Actual OCI
configuration, identity probes and Vault custody remain unqualified. These local observations are
not a claim of production readiness; version 1 retains the earlier selection-only semantics.

## OCI Console handoff instructions

The live setup panel carries a six-step checklist with direct Oracle links. These are documentation-backed
manual steps for the future OCI integration, not evidence that the current simulator has activated a child,
issued a key, granted privileges or tested live OCI. Local testing uses **Use simulated handoff** without
performing any of these OCI actions. Last checked against Oracle documentation on 31 October 2026.

1. **Create only:** use the activation message delivered to the initiating administrator's verified mailbox;
   finish activation, password setup and MFA, then enter the child Console. Requested name/home region were
   already supplied by OTM; do not issue another create request. See [Oracle's child creation guide](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm).
2. In the **child** profile menu, choose Tenancy and copy its OCID from Tenancy Information. For create,
   also open User settings as the activation administrator and copy that account's OCID. The work-request
   identifier is separate and is never substituted for the tenancy. See [locating OCI IDs](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/contactingsupport_topic-Locating_Oracle_Cloud_Infrastructure_IDs.htm)
   and [user/key identifiers](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm).
3. Within the child, navigate Identity & Security → Domains → Default → Users → Create user. Choose a
   distinct username rather than the email-as-username option, use the displayed bootstrap username,
   complete the required identity/contact fields, assign Administrators and copy the resulting user OCID.
   Administrator contact details do not change the intended owner's identity. See [creating administrator users](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/addingusers.htm).
4. In that same domain, open Administrators (some Console layouts place it under Security), find the
   Identity domain administrator role, and add the bootstrap user. This is separate from membership of
   the OCI Administrators group. See [assigning users to domain roles](https://docs.oracle.com/en-us/iaas/Content/Identity/users/assign-users-roles.htm).
   Actual bootstrap capability and replacement grants still require the qualified probes defined in C06/C10;
   following a checklist alone is not a verified privilege result.
5. On the bootstrap user's details, use API keys → Add API Key → Paste a public key and register the
   app-provided public PEM. Do not generate a replacement key pair in OCI, attach it to the human activation
   account, or enter private key material into the app. See [uploading public API keys](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm).
6. For create, enter tenancy/bootstrap-user OCIDs and activation-user OCID into the labeled fields.
   For import, the original tenancy OCID is already displayed read-only; enter only the bootstrap-user
   OCID. Select Verify handoff. Retain temporary accounts until replacement access is verified and exact cleanup is
   previewed. Passwords, OTPs and private keys are never requested here.

For **import**, skip activation and complete the appropriate manual transfer procedure first. Created
children require [approval for transfer using the CLI](https://docs.oracle.com/en-us/iaas/Content/General/organization/approve-createdchildtenancy-for-transfer.htm);
previously invited children follow [their separate removal and subscription procedure](https://docs.oracle.com/en-us/iaas/Content/General/organization/link-delete.htm).
The new parent [invites the existing tenancy](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm),
and an authorized administrator in the child [accepts the invitation](https://docs.oracle.com/en-us/iaas/Content/General/organization/recipient-invitation-accept.htm).
Confirm the exact child in the configured parent's Organization Management → Tenancies list before
bootstrap. The panel provides these separate procedure links rather than a universal detach instruction.
It does not automate transfer, presume every tenancy can become standalone, or alter subscription/governance
settings. Import preserves unrelated existing human administrators.

Creation handoff currently requires manual tenancy OCID entry; import carries the original selected
OCID forward read-only and cannot be retargeted at handoff. The real adapter may prefill a uniquely
verified child identifier from OCI work-request evidence when qualified; neither a correlation ID nor
an inferred name is sufficient. No schema or contract changes are needed for this copy update.

## State and failure behavior

| Operation state / phase | Meaning and action |
|---|---|
| queued / preparing | Durable initial acceptance; worker has not reached the handoff pause. |
| waiting / handoff | Manual activation/parent transfer/bootstrap prerequisite; submit exact IDs. |
| queued / configuring | A handoff or setup command was accepted; poll stored progress. |
| waiting / review | Read-only checks passed; review discovered identity and exact cleanup targets. |
| needs_attention / blocked | Check failed; temporary access is not declared retired. Correct handoff or retry the incomplete setup suffix. |
| succeeded / complete | All steps required by the accepted onboarding version passed and local ownership was published; version 2 includes baseline readback and post-baseline access checks. |
| cancelled | The existing no-effect local cancellation path stopped future simulation; never a tenancy-delete action. |

Only the currently responsible administrator sees enabled setup actions and may submit them.
Every command repeats live session/grant, workspace, policy/pause, source-person and preview checks.
The worker also repeats the exact original or valid replacement authority revision, target, parent
and reservation checks. A replacement requires the separately audited
[responsibility takeover](responsibility.md); viewing never changes that authority.
A returned facade identity must match the frozen target and submitted bootstrap/activation IDs before
inspection can become verified. A parent, foreign, differently bound or real target is not adopted.

A command carries operation revision and a request UUID. An unchanged retry recovers the accepted
operation instead of creating another tenancy. A changed body with the same request UUID is rejected.
New commands on stale revisions fail closed. Waiting finishes the native job and releases all worker
and transaction locks; resuming commits the command, audit and native UUID-only job together.
Verified setup steps are skipped on retry. A known setup effect blocks no-effect cancellation.
Changing organization membership or revoking the administrator cannot silently retarget pending work.

## Existing storage, no new tables

Historical migration **0010_guided_onboarding** extended three allowed-value constraints only and
retained14application tables. P3.1 later added the fifteenth baseline table;0012 added publication
metadata and0013_baseline_pinning now adds two columns to existing tables, without another table.
Frozen prior migrations and existing records are preserved. New create/import intents carry
`onboarding_version=3`; previously accepted version 2 retains its baseline/access graph, version 1 keeps its original access-only step graph and
an absent version keeps the historical one-step simulator. The browser cannot choose a compatibility
bypass. Migration 0017 expands existing allowed step/evidence values only; the current inventory
remains 18 application tables, with no new column or backfill.

| UI / input / evidence | Database authority |
|---|---|
| Current baseline preview | PersonWorkflow.current_baseline derives the latest published version_number in the workspace, not the deprecated stored current_baseline_id. The registry revision fences stale previews. |
| Frozen selected baseline | OrganizationIntent.baseline contains the complete server-selected BaselineVersion in original immutable operation_intent; OnboardingView.baseline reads that snapshot, not current/latest. |
| Registered tenancy pin | otm_tenancy.baseline_version_id → same-workspace published baseline; TenancyView.baseline_version_id reads it. Selection remains distinct from verified_baseline_version_id. |
| Simulated category state | Existing otm_tenancy.configuration_observation retains the policy/quota/budget/tags ManagedConfigurationObject records, including partial failure state. No separate onboarding object table. |
| Verified baseline and time | Existing otm_tenancy.verified_baseline_version_id / configuration_verified_at advance only after all four category readbacks pass. Their source is configure_baseline, not a confirmation checkbox or latest lookup. |
| Configured parent at handoff | `OnboardingView.expected_parent_tenancy_ocid` from frozen `intent.parent_tenancy_ocid`, separate from the discovered parent. |
| Requested create name/home region | OrganizationAction.name/home_region → immutable intent.name/home_region at acceptance; actual values separately verified at handoff. |
| Region selector | CreationRegion(identifier,name) tuples in PersonWorkflow.creation_regions, supplied by the parent-scoped facade. |
| Completed operation link | OperationSummary.result_tenancy_id, derived from an exact workspace+frozen-OCID join to otm_tenancy after successful lifecycle completion; no new column. |
| Owner, type, initiating admin, synthetic target | Immutable `audit_event.data.intent` in the original `operation_intent`. |
| Verified activation mailbox when available | `intent.activation_email`; null for local recovery identity. |
| Current action, revision, wait | `otm_operation.state`, `.stage`, `.revision`, `.wait_reason`. Reasons are `onboarding_handoff`, `onboarding_review`, `onboarding_check`. |
| Bootstrap username | Derived from operation UUID; display-only local instruction. |
| Submitted OCIDs / cleanup confirmation | Current `otm_operation_step.inputs` for `handoff`. |
| Discovered name, home region, parent, organization, domain, OCI/SCIM bindings | Typed `OnboardingDiscovery` in `inspect_bootstrap.inputs.discovery`; observed name/region also update the pending registry row. |
| Check status and timestamp | Current-intent step row `.state`, `.verified_at`, `.attempt_number`. |
| Previous handoffs and discovery | Append-only `onboarding_action` / `onboarding_outcome` audit events, typed `OnboardingEvidence`, including nonsecret handoff/discovery payloads. |
| Replay | Immutable accepted action's `client_request_key` and canonical request hash, scoped to operation/workspace. |
| Verified local completion | Existing `apply_lifecycle` outcome, active membership/user binding and tenancy verification timestamp. |

Logical onboarding step keys are `handoff`, `inspect_bootstrap`, `establish_automation`,
`verify_automation`, `configure_required`, `verify_required`, `configure_baseline`,
`verify_configured_access`, `capture_required_users`, `retire_temporary`. Capture applies only to
version 3. The two configuration/post-configuration keys apply to version 2/3 with a frozen baseline; version 1 keeps the original seven-key graph.
The `handoff` row's verified timestamp means **administrator input accepted**, not provider access
verified; only `inspect_bootstrap` establishes the separate inspection result. Audit retains every
attempt while the current logical step is updated in place. No credentials enter these payloads.

The simulator executes each queued phase atomically in PostgreSQL. A real network adapter must not
be dropped into that transaction: dispatch/reconciliation and provider evidence boundaries remain
as specified in chapters08/09 and require their own qualification. Real import's inspect-before-final-
adoption contract remains unchanged; this local exercise reserves a pending simulated child at start.
It does not qualify real migration/adoption, last-admin semantics, MFA or OCI root baseline deployment.
Version 2 does exercise simulated root-category application; that local milestone is separate from
real-provider qualification.

## API and UI contract

`GET /api/tenancy-onboarding/{operation_id}` returns `OnboardingView` only for current-workspace guided
organization actions. It never schedules work. `POST` on the same path accepts at most 4,096 bytes of
closed JSON `OnboardingCommand`: request UUID, positive revision, action `verify_handoff` with a
nonsecret handoff, or `start_setup` with explicit cleanup confirmation. Arbitrary fields, credentials
and real bootstrap-user IDs are rejected. Queued acceptance returns202; a replayed terminal result
may return200. Both routes use normal session/Origin/CSRF guards and generic safe failure responses.

Generated Pydantic/TypeScript contracts remain authoritative. `TenancyDetail.onboarding_operation_id`
links pending guided setup; `OperationSummary.guided_onboarding` selects the progress panel. Phase,
available actions, discovered facts and check labels are server projections, not client authorization.
The server clears available actions for other administrators. No reason field or generic retry button
is introduced. Long IDs wrap; desktop/mobile controls retain the shared Field Console styling.

## Complete contract field dictionary

The six onboarding DTOs have52fields in total; reused BaselineVersion is mapped separately in the
[baseline dictionary](baseline-authoring.md#complete-model-and-source-map), not counted as a seventh
onboarding model here. Nested models are included in the generated
[command](../../backend/contracts/onboarding-command.schema.json) and [view](../../backend/contracts/onboarding-view.schema.json)
schemas; immutable evidence remains server-side. Names below match the code exactly.

| Contract | Every field | Source, defaults and nullability |
|---|---|---|
| `OnboardingHandoff` (3) | `tenancy_ocid`, `bootstrap_user_ocid`, `activation_user_ocid` | Administrator input or explicit synthetic helper. Exact child target; bootstrap user must have the simulated-user prefix. Activation user is nullable for import and required for create by admission. |
| `OnboardingCommand` (5) | `client_request_key`, `revision`, `action`, `handoff`, `confirm_cleanup` | Browser request UUID and displayed positive operation revision. Action is verify_handoff/start_setup. Handoff is required only for verification; cleanup defaults false and must be true for start_setup. No secret or arbitrary SDK fields. |
| `OnboardingDiscovery` (10) | `tenancy_ocid`, `name`, `home_region`, `parent_tenancy_ocid`, `organization_id`, `domain_ocid`, `bootstrap_user_ocid`, `bootstrap_scim_id`, `activation_user_ocid`, `activation_scim_id` | Facade read-back checked against frozen child/parent/organization and submitted user bindings. Stored in inspection step and immutable discovery evidence. Activation fields are null for import; create requires the exact account and a SCIM binding. Other fields are required. |
| `OnboardingCheck` (4) | `key`, `label`, `state`, `verified_at` | Ordered server step catalog plus current step state/time. Missing steps project pending; verified_at is null until recorded verification. Fixed labels do not use employee data. |
| `OnboardingView` (23) | `email_contacts`, `baseline`, `operation_id`, `tenancy_id`, `revision`, `state`, `phase`, `origin`, `requested_name`, `requested_home_region`, `can_act`, `expected_parent_tenancy_ocid`, `owner_name`, `administrator_name`, `administrator_email`, `suggested_handoff`, `submitted_handoff`, `discovery`, `bootstrap_username`, `public_key`, `checks`, `issue_code`, `available_actions` | baseline defaults null for historical operations; otherwise it is the complete immutable published BaselineVersion frozen at acceptance, never a fresh default lookup. It records selection, not application. IDs/revision/state come from accepted intent/operation; phase is derived from state/wait. Origin distinguishes create/import. requested_name/requested_home_region are nullable frozen create inputs; imports and missing historical values remain null, independently of observed discovery facts. can_act is false and actions empty for another responsible administrator. email_contacts is nullable for historical operations and otherwise returns exact frozen original/effective activation/bootstrap/owner/person routes; current global override never rewrites it. Parent comes from frozen intent; owner/admin labels are frozen snapshots, not browser claims. administrator_name is the original initiator and the create/import subtitle says Initiated by; current responsible is a separate OperationSummary projection. administrator_email remains the original activation contact, nullable with no verified local mailbox implied. Suggested handoff is deterministic simulation data; submitted handoff and discovery are null before their steps. Username is derived from operation UUID; public_key is always null here. Checks are ordered step projections; issue_code is nullable and closed. |
| `OnboardingEvidence` (8) | `contract_version`, `step`, `outcome`, `safe_code`, `client_request_key`, `request_hash`, `handoff`, `discovery` | Append-only typed audit payload; version onboarding-1. Step/outcome/code are closed. Accepted human commands have request key/hash; worker evidence leaves these null. Exact nonsecret handoff/discovery payloads are nullable and populated only by their corresponding event. No credentials are serialized. |

`can_act` and `available_actions` are affordances, not permission tokens; POST repeats current checks.
The discovery's parent is an observed simulator fact, while expected_parent_tenancy_ocid is the
independent configured target shown before handoff. Operation history is collapsed by default in
guided detail; the current action/checks remain primary. A phase change politely announces the new
heading and refreshes related persisted views; the same unchanged poll does not fan out refreshes.

## Checkpoint validation

The dated validation receipt (private historical evidence; not distributed)
records938passing backend/database/browser tests and separate786backend/147frontend units above95%.
It distinguishes actual installed-role HTTPS/Playwright evidence from local synthetic provider checks.
The existing laptop database was backed up and migrated without changing any application's rows.
No real tenancy, key, MFA setting, email or provider credential was touched.

## Create input and completion correction — 31 October2026

The original SDK design required initial requested name/home region. Their removal in the first
guided local UI was an implementation error, corrected here; earlier checkpoint screenshots record
that historical UI, not current behavior. Existing accepted operations are preserved rather than
rewritten. Successful lifecycle Operations now show one direct **Open tenancy** link in their
completion notice, including historical nonguided operations whose registry record still exists.
The lookup uses workspace plus frozen target OCID, never an owner's other tenancy or the operation
UUID. Queued/failed/unregistered results and inspection-only outcomes expose no result link.
Normal destination authorization remains required; person-wide operations without one target do
not invent a result tenancy. The embedded setup panel suppresses its duplicate completion link in
Operations; standalone setup retains its own link. No application table, column or migration is added.

## Import target continuity and name-conflict coverage (2 November 2026)

The import modal establishes the exact tenancy OCID. The setup panel displays that same server-derived
value in a labeled read-only input; it never asks the administrator to supply it again. The browser
constructs the handoff using the server target, and the server independently compares any submitted
OCID against the frozen operation. A forged client cannot change this binding. Create retains an
editable field because the child identity was not yet available when the request was accepted.
This changes input behavior only: existing handoff fields/storage and exact-target authorization remain.

**Implemented and exercised:** malformed names/unsupported regions are rejected before admission;
a name used by an active, pending or terminating OTM registry record is rejected before operation,
registry, audit or queue writes. The modal stays open, explains the local conflict, restores focus to
the name input, and retains owner/type/region choices. Editing starts a fresh request identity; an
unchanged accepted command replays the same operation. Disposable database tests confirm rollback
and a corrected retry, while browser integration verifies the read-only import field and successful
setup. Import tampering is also rejected against the real database; the correct handoff can still proceed.

**Not yet implemented or qualified:** the simulator does not issue CreateChildTenancy, test OCI-wide
name availability, or model a late OCI name rejection. Registry checks are not a global availability
check. The following is the required real-adapter behavior, not a claim that it runs today:

- A documented definitive name rejection with proof no child request was accepted pauses the existing
  operation for a replacement name. Show a clear name-in-use message as soon as the provider outcome
  arrives; do not cancel the operation or ask for owner/type/region again.
- Authorize the responsible administrator, validate the replacement locally, append a new immutable
  intent revision in the same operation and retain the rejected name/outcome in audit. Preserve the
  operation, pending record and intended owner; recheck scope/entitlement before the corrected attempt.
- A changed request needs a new provider retry token. An unchanged transport retry retains its token.
  Timeout, lost response, generic conflict or ambiguous work-request failure cannot be interpreted as
  permission to request a differently named child. Reconcile the original attempt first.
- Qualify exact OCI error/work-request semantics and exercise repeated rejection, eventual success,
  stale commands, double submissions, reloads, revoked access and uncertain outcomes before enabling
  live creation. A name advertised as available before submission is never a guarantee against a race.

See the [SDK call design](../engineering-design/08-oci-sdk-call-design.md) and
[engineering test plan](../engineering-test-plan.md). No new table or command was added for
the future amendment flow in this slice.


## P3.2b baseline retained across manual waits

The latest published baseline in this workspace, ordered by version_number descending, is the only
default for new create/import operations. No older-version selector, Use for new command or stored
runtime default pointer is used after0014. The old current_baseline_id column/FK/guard remain as
unused historical metadata; selection ignores it. Published history remains read-only; opening a version does
not influence admission. Existing publications automatically participate in the latest lookup.

Publishing advances registry_revision in the same audited transaction. A stale employee workflow
preview must refresh rather than silently accept another recipe. Admission reads the latest
published snapshot under the workspace lock, freezes it in OrganizationIntent.baseline and reserves
the tenancy with its UUID. No baseline ID/content is added to public OrganizationAction; original
request-digest/replay shape remains intact. When no baseline is published, new create/import is rejected before any
operation/tenancy/audit/job write; joining/cleanup and nonprovisioning decisions retain independent rules.

If v1 was accepted before activation, a later v2 publication does not substitute v2 at handoff,
setup, retry or worker restart. Each worker attempt compares the full frozen snapshot with that exact
same-workspace published row/hash/mode and also requires the pending registry baseline_version_id
to match before a facade call. It never reselects latest for an accepted operation. Current
administrator/parent/runtime-policy guards remain live; a pin cannot bypass revocation or contradictory
evidence. Lost initial-response replay returns the original accepted operation/pin before checking a
newer preview/latest publication, after current authorization.

The setup notice links the frozen published version and explicitly labels simulation. Legacy intents
with absent/null baseline retain old behavior and say no version was attached retroactively. Existing
tenancy baseline_version_id values and accepted pins are preserved by0014, including older pins;
null legacy values stay null. Migration0014 preserves that deprecated workspace column and
its guard/FK and only increments registry_revision once to invalidate pre-change previews. It does not
rewrite immutable intent, audit, publication, recipe or assignment history. Historical
baseline_default_changed events remain readable but have no live selection authority.

At the historical latest-only correction, these fields proved selection only. The version 2
refinement below now adds simulated baseline application/readback; version 1 keeps its previous
semantics. configure_required/verify_required still concern identity/access, with separate
configure_baseline and verify_configured_access milestones. No OCI managed-object binding or real
provider qualification is implied. The prior P3.2b receipt (private historical evidence; not distributed)
qualifies its earlier explicit-default source; latest-only correction tests and both saved-instance qualifications pass. See the
correction receipt (private historical evidence; not distributed).


## Version 2: configure the pinned baseline before retiring temporary access

3 November 2026 · Local simulation qualified and installed in both saved instances. This supersedes selection-only behavior
for newly accepted create/import work, without changing previously accepted intents or receipt scope.

The service freezes the complete latest published BaselineVersion at admission, as before. The
worker validates that exact published snapshot and the pending registry pin on every attempt. A
later publication cannot substitute another recipe during activation, human review or retry.
After initial permanent/required access verification, configure_baseline uses the shared
ConfigurationFacade/configure_target path for policy, quota, monthly budget and tag defaults. It
uses the frozen publication, never current/latest. No policy parsing, override editing, live OCI
object or credential qualification is added here.

Partial category observations persist in the existing configuration_observation JSON. Retrying
reads already matching objects before skipping their writes; full category success alone advances
verified_baseline_version_id and configuration_verified_at. An identity/recovery failure after
that milestone does not turn a real completed baseline readback into an unknown one, but keeps
onboarding pending and temporary access retained. A verified baseline is not proof that the entire
onboarding operation succeeded. New onboarding starts with no tenancy-specific override revision;
existing desired_configuration_id/last_verified_configuration_id are not fabricated or backfilled.

verify_configured_access runs fresh verify_automation and verify_required facade probes after root
configuration, even though their earlier steps passed. Only that result permits retire_temporary
and subsequent active ownership publication. Failed category readback uses BASELINE_UNVERIFIED;
failed final access check uses REQUIRED_ACCESS_UNVERIFIED. Both remain bounded nonsecret outcomes.
Known partial effects prevent safe-no-effect cancellation. The simulator remains transactional local
state; a network adapter requires separate dispatch/reconciliation qualification before reuse.

| New evidence/behavior | Existing authority and bounds |
| --- | --- |
| OrganizationIntent.onboarding_version | Closed 1, 2 or 3, nullable for historical operations; server-selected 3 on new create/import. Version 2/3 validation requires create/import plus a non-null BaselineVersion with published_at; it cannot silently skip configuration by omitting the pin. |
| OnboardingEvidence.step | Versions 2/3 include configure_baseline and verify_configured_access; version 3 adds capture_required_users and its typed required_users evidence. |
| OnboardingEvidence.safe_code | Adds BASELINE_UNVERIFIED; no arbitrary SDK error or credential text. |
| OnboardingView.checks | Derived from the accepted version's step graph, preserving order/status/timestamp; same public fields. |
| Category readback | Four existing ManagedConfigurationObject records: category, object_ocid, payload and payload_hash. Synthetic IDs/data are local provider evidence only. |
| Existing baseline pin | Immutable intent snapshot + registry baseline_version_id, distinct from last full category verification and later override revisions. |

See the [six-change manual review](../how-to/tenancy-refinements-runbook.md) for new,
legacy, failure/retry and latest-publication-during-handoff scenarios. Qualification of this new
slice passes locally; earlier guided/baseline receipts remain historical.


### Local qualification results

The final combined backend/PostgreSQL/native-worker/HTTPS-browser run passes 1,237 cases with no
failures, errors or skips. Backend unit-only coverage is 6,405 of 6,673 lines (95.9838%) across all
90 runtime modules, from 1,002 unit tests. The 266 frontend unit tests cover 1,496 of 1,537 lines
(97.33%) across 28 files. A separate final actual HTTPS/browser/PostgreSQL check passes the native
selected-content existing/create/existing mode transition and successful assignment/removal after
the last picker fix; it is additional evidence, not a relabeled all-database test count.

All 59 generated schemas, 238 Python purpose-comment files, 213 formatted Python files, Ruff and
document links pass. Dependency audits, Bandit and scoped Gitleaks report zero findings. Independent
security, migration/installer and final actual-screen UI reviews pass. This qualifies local
simulation only. Both saved instances are upgraded from 0016 to 0017 with private 0600 backups. Old columns/rows
across all 18 application tables have identical fingerprints; baselines, pins and history are
preserved. The 18-table inventory and 20-column baseline table are unchanged; no table/column or
backfill was added. Matching per-instance frontend snapshots, API/worker liveness, current assets,
direct-route HTTP 200 and protected-API HTTP 401 checks pass on both ports.


Local qualification and saved-instance receipt (private historical evidence; not distributed).


## Qualified explicit responsible-administrator takeover

Local qualification and both saved-instance upgrades pass. An entitled different administrator can claim waiting/attention guided v1/v2
create/import through the operation's Administrator responsibility panel. The original initiator
and activation contact displayed by this setup view stay unchanged. The subtitle says Initiated by
for both create and import; it must not call that immutable creator the current responsible
administrator after a takeover. Only current responsible can submit verify_handoff/start_setup.
A validated immutable replacement-authority snapshot plus current grant check permits continuation
after creator revocation without changing provider intent, target, baseline or prior steps.
Claiming queues no setup job; actual resume remains a separate guarded action. External activation
account/mailbox recovery stays manual. [Exact fields and scope](responsibility.md).


Final application qualification and saved-instance receipt (private historical evidence; not distributed).


## Activation/bootstrap contact versus application lifecycle email

Authored notification/policy integration, validation pending. New configured create/import needs
explicit safe contact routing before acceptance even when application notifications are disabled.
Local/staging cannot fall back to an employee address without the configured test destination.
The preview and 23-field OnboardingView distinguish immutable original contact from effective
delivery. Create labels Activation / bootstrap email; import labels Bootstrap contact email and
does not imply a new activation. The manual bootstrap username remains distinct from its guarded
contact. Legacy contacts=null preserve their accepted instructions.

Application action/failure notices can reach local SMTP capture, while the simulator sends no OCI
activation/invitation email and issues no usable key. Owner invitation contact is a future guarded
OCI path, not an extra SMTP recipient. Current notice routing follows the responsible admin; original
activation contact and provider intent stay unchanged through takeover.
[Field/policy/outbox guide](lifecycle-email.md) ·
[Capture and negative-test runbook](../how-to/lifecycle-email-runbook.md).


## Permanent-user capture — 6 November 2026

New create/import admissions use version 3. After the frozen baseline and fresh access probes,
**Record permanent user identities** reads the permanent automation and recovery users separately,
then stores their exact identifiers before **Retire temporary access**. A capture failure blocks
cleanup and publishes a closed `REQUIRED_ACCESS_UNVERIFIED` issue. Retry uses existing operation
steps; completed-work redelivery cannot overwrite the recorded evidence. Version 1/2 and absent-version
accepted intents retain their original graphs; no identity is inferred or backfilled for them.

The shared `OnboardingUsers` result is declared in the neutral lifecycle contract, with explicit
simulation in `lifecycle_simulator.py`. `onboarding_users.capture_users` validates the returned
workspace/organization/parent/child against the accepted intent and domain against discovery.
Both purposes require distinct nonnull OCI user OCIDs and SCIM resource IDs in that domain.
Neither may identify the bootstrap or activation administrator by either identifier.
Names are observed labels, never matching or adoption keys. Results forbid unrecognized fields.

| Model / field | Meaning and storage |
| --- | --- |
| OrganizationIntent.onboarding_version | Server-selected 3 for new create/import; persisted in immutable operation intent. Existing 1/2/absent values preserve accepted semantics. |
| OnboardingUsers.workspace_id, organization_id, parent_tenancy_ocid, tenancy_ocid | Exact accepted scope; parent cannot be its own child. |
| OnboardingUsers.domain_ocid | Exact domain discovered through bootstrap inspection. |
| OnboardingUsers.automation, recovery | Separate ObservedRequiredUser values: domain_ocid, scim_resource_id, nonnull provider_ocid and user_name. OCI and SCIM identifiers remain distinct. |
| OnboardingEvidence.required_users | Nonnull exactly on a verified capture_required_users outcome; forbidden on other/blocked outcomes. Omitted from historical outcomes when absent. |
| otm_operation_step.last_outcome | Typed capture evidence in the existing workspace/operation/intent/step row; evidence_event_id references the immutable audit outcome. No second identity registry is introduced here. |
| audit_event.data | Immutable onboarding_outcome containing the same capture payload, with existing operation/workspace provenance, timestamp and data hash. |

Migration **0022_onboarding_users** only extends the existing step-key constraint; it adds no
columns, tables, grants or backfill. Frozen earlier SQL remains unchanged. Existing ER relationships
remain accurate because capture uses the current operation-step/audit relationship.

These are onboarding provenance facts, **not** current managed-object binding/access-assignment heads,
credentials or proof of signer/privilege/console/MFA/recovery readiness. The later access-health slice
must establish canonical scoped binding heads and generation checks before using presence reads.
No required-user check, repair, password disclosure, scheduled scan or new Access screen is enabled.
The simulator returns only synthetic identities; no live user or key is created by this slice.

### Review locally versus OCI

After this source revision is deliberately installed in a local review instance, create or import a
simulated tenancy through the existing guided flow. Complete the handoff and cleanup confirmation;
**Record permanent user identities** should be verified before temporary cleanup and survive reload.
An existing completed operation need not gain this step. Do not expect a new primary menu or Access page.
The current saved previews are not automatically upgraded by development builds.

Automated unit cases cover exact identities, independent role scope, collisions with temporary users,
malformed/secret extras, closed failures and versioned step ordering. PostgreSQL cases check create
and import evidence, immutable audit agreement and successful-operation redelivery. Browser cases
check the capture step in the normal guided flow. These checks do not prove actual OCI readback,
eventual consistency or credential cleanup; see the
[real OCI manual test manifest](../how-to/real-oci-test-manifest.md).
