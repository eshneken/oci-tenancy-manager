# 12: required access, observations and bounded repair

21 October 2026 | C4 first screen/flow slice | Proposed production contract, not implemented access

[Design hub](README.md) · [Identity decisions](04-identity-and-access.md) ·
[Shared model](11-production-data-model.md#identity-access-and-credential-model) ·
[Access walkthrough](../walkthroughs/access-walkthrough.html#missing)

## Scope and authority

This slice designs the tenancy-detail **Required access** page, scoped observation acquisition and
repair preview. It preserves owner full administration, the existing organization/prototype behavior,
D19 independent recovery, D27 identity domains, and the single OTM root policy from D30.
The walkthrough uses illustrative facts; it performs no OCI calls, secret reads, jobs or notifications.
Names in samples are data, while guidance and error text remain organization-independent.

D39 selects the exact recovery-user-only MFA exemption; this does not qualify deployed policy behavior, complete session revocation or a final provider permission profile.
D40 administrator password/disclosure/rotation pages are described in chapter13; temporary named support is deferred. D35 A selects the visible protected required-access policy section below. Recovery-only exemption behavior and
provider permission qualification remain open; selecting composition does not qualify either.

## Flow and navigation

1. Open **Tenancies → tenancy detail → Required access**. Current design has a concrete link on the
   matching `lab-casey-01` example only. Do not retarget another tenancy silently or add a new primary menu.
2. Read stored current observations for each required assignment. No SDK request occurs per table row.
   Show observation time, coverage and explicit unverified/stale status. Owner access and first sign-in
   are distinct from the two required operational users; the audit user remains V2.
3. **Check now** accepts one scoped observation operation under C2, returning its operation ID.
   This does not mutate identities or erase current findings while a new acquisition is running.
   Daily scheduled checks and manual requests use separate logical occurrence IDs; delivery retries
   reuse the same one. One operation may acquire two check records, each with exactly one assignment/
   coverage owner. A shared failed provider attempt may explain both inability results, but it cannot
   manufacture a complete inventory. The walkthrough only acknowledges what that command would do.
4. **Repair** is offered only for confirmed repairable loss/difference plus current independent
   evidence that permanent automation can execute that exact repair profile. A failed authentication,
   stale capability result or missing authority produces recovery guidance rather than a false button.
   A read of one user is not a proof of user/group/password/policy administration.
5. A repair preview freezes tenancy, coverage subject, affected logical keys, binding generations,
   assignment, observation and credential/context generations. Review and acceptance use existing
   `action_preview`/operation intent and the C3 persisted repair selection where appropriate; there
   is no second access-plan table. Identity-only repair uses a typed C2 preview/intent, not a fabricated
   configuration revision or configuration-plan kind.
6. At acceptance and dispatch, recheck entitlement, lifecycle, active assignment, coverage, exact target,
   credentials and sufficient repair-profile evidence. Commit operation/audit/initial continuation
   atomically. Outdated preview returns a conflict and refreshed facts, never silent broader repair.
7. Operations tracks accepted work separately. The access issue stays open until a current qualifying
   observation verifies the original condition. Restored identity/grants do not prove console readiness.
   No success toast or operation completion substitutes for provider evidence.

The current modal presents the exact scope and a simulated Start repair action when the sample has sufficient independent repair authority. Acceptance acknowledges queued work and keeps the issue open until verification. This does not qualify real repair permissions or the deployed recovery exemption. No additional approval role or Reason field is introduced.

## Status semantics and evidence

| Fact | Possible result / meaning | How it is established |
|---|---|---|
| User presence | Present, confirmed Missing, Unable to verify | Verified binding in the right domain plus authorized complete result; a denied call is never absence |
| API authentication | Verified signer, Authentication failed, Unable to verify, Not applicable | A qualified signed request under exact current key/context; recovery is a human console identity, not a machine signer |
| Required privileges | Profile verified, mismatch, Unable to verify | Versioned profile requirements plus qualified evidence for its required operations; successful generic reads are insufficient |
| Console capability | Disabled by intent, observed enabled/disabled, Unable to verify | Separate observed capabilities; intent alone must not be labeled observed enforcement |
| MFA/enrollment | Observed enrolled, not enrolled, unknown/not verified | Supported provider enrollment/policy facts and manual qualification where required; no factors/seeds are retrieved |
| Recovery console readiness | Qualified, Exemption not verified, Not qualified, Unable to verify | Exact recovery-only MFA-exemption scope plus independent custody/sign-in evidence; never inferred from user presence |
| Freshness | Current, stale, pending acquisition, unable to verify | Captured time plus versioned freshness policy, current head and coverage/generation checks |

The page is a derived summary of the separate automation and recovery checks. Display both source
references and each row’s observation time; do not invent one check that verifies two assignments.
Each assignment has its own stable coverage owner and check head. Automation and recovery scans cannot
close each other's failures; a person's passing check cannot hide another person's failed access.
A complete current matching follow-up resolves the matching issue episode. Failed/partial/stale checks
retain prior confirmed findings with their last confirmation time and current uncertainty. An obsolete
scan cannot advance a head or resolve anything. UI counts include each required assignment once.

For V1, a daily scan is the accepted minimum. A check/profile result is bounded by its explicit
operation set, evidence source, time, target and versions. It is not a perpetual proof of every admin
power. Effective-write permissions that cannot be safely proven by reads need a qualified profile
and provider pilot; no destructive probe is run simply to make the UI green.

## Repair scope and lifecycle

| Condition | Offered action | Completion boundary |
|---|---|---|
| Recovery user confirmed missing, automation sufficient | Preview → accepted recreate-user/grants operation | New binding recorded; identity/grant checks pass. Required enrollment remains a separate manual obligation |
| Required grant differs, signer sufficient for exact change | Preview exact grant/policy delta | Current scoped observation matches; coordinate the one managed policy revision if it changes |
| Automation cannot authenticate / cannot verify authority | Guidance only; restore through qualified independent recovery/manual process | Fresh authorized evidence, then new preview; no parent-membership bypass |
| User present but recovery exemption/custody unqualified | Verify exact recovery-only sign-in policy and independent procedure | Evidence of policy scope/precedence, custody and successful recovery checks; never inferred from presence or password retrieval |
| Repair write result unknown | Reconciliation in Operations; no duplicate create | Qualified exact-target reconciliation establishes effect before retry or binding replacement |
| Assignment retired / tenancy terminating after preview | Refuse obsolete repair | Never recreate intentionally offboarded access or mutate a protected/terminating tenancy |

Recreation changes the bound provider ID. Preserve the retired binding generation and connect the new
one; do not rewrite historical observations or adopt an owner-created same-name user. New recovery
password material is generated/staged inside Vault before provider application; it is not in the
repair preview, job payload or audit. Unknown writes retain both candidate/prior nonsecret references
until reconciled. User/grant repair cannot delete workload resources or compartments.

A verified missing/change episode records an initial notification intent to the configured owner,
manager and designees, with administrator routing/fallback as needed. Repeated observations of the same
open condition do not create daily duplicate initial alerts. Capture recipients/routing revision in the
outbox at trigger commit. Delivery cannot authorize a repair. Reminder cadence remains a later explicit
notification policy; no new noisy reminder is assumed here.

## Application and facade command boundaries

These are semantic message contracts; final HTTP routes/generated OpenAPI are not frozen here.
They reuse chapter09 typed results and chapter11 receipt/intent storage.

| UI / application message | Validated input | Result and persistence boundary |
|---|---|---|
| Read required-access view | Workspace + registered tenancy ID + current entitlement | Local head/observation/issue projection; explicit per-subject timestamps and source checks; GET performs no acquisition or provider write |
| Request access observation | Tenancy ID, required coverage subjects/profile versions, command request key/digest | One accepted C2 observation operation and stable acquisition identity; each coverage owner receives its own check ID; retries of the command return the same accepted result |
| Capture access-repair preview | Exact issue/subject, source observation, selected identity/grant logical keys, binding/config/access/context generations | Typed immutable action-preview receipt with exact actions, blocked reasons and validity; no job or provider write |
| Accept access repair | Captured preview ID, actor request key/digest, expected current context | Same accepted operation on matching retry; reject stale/unsafe input without dispatch; issue remains unresolved until follow-up verification |
| Read repair progress | Accepted operation ID + current entitlement | Persisted C2 steps/outcomes/waits; no inferred provider effect or synchronous SDK call from the page |

For observation acquisition, the worker resolves the exact active access assignment, canonical domain
binding, current authorized signer and immutable credential version. It calls the existing chapter08/09
**Observe item/access** facade capability for the user, required group/role relationships, signer and
supported capability/enrollment facts. Snapshot all verified target IDs and context versions in the
attempt evidence. No SDK object, domain URL supplied by a browser, private key or console password
crosses the application-message boundary.

The typed facade result carries local `target_tenancy_id`, provider `target_tenancy_ocid`, `coverage_subject_kind/key`, `access_assignment_id`,
`binding_id`, `provider_ocid`/`scim_resource_id` where applicable, `captured_at`, exact context/
credential generations, `result`, `coverage`, safe `diagnostics` and nonsecret provider request
correlation. Each user/group/capability observation is scoped to that subject. Unsupported MFA facts
return unknown/unsupported coverage rather than an invented boolean. A provider timeout/denial
cannot be converted into a successful empty list.

Repair uses the already cataloged **Apply one identity/grant/item** and exact credential-reference
capabilities. Each independently consequential effect is a durable step, with qualified write identity,
known/unknown effect and reconciliation behavior. Reads and writes go through the same typed facade
in real and simulated environments. Required contract fixtures therefore include signed request works
but domain read denied, user read works but grant mutation denied, read absence versus wrong-domain 404,
partial pagination, delayed propagation, response lost after user creation and changed credential
context mid-check. These are designed fixtures, not new executed provider tests. The [SDK map](08-oci-sdk-call-design.md#identity-key-and-grant-primitives)
remains the source of candidate calls and permission qualification.

## Field-by-field contract

All IDs below are scoped by workspace and tenancy. Sample labels such as `access-check-42` are display
labels, not proposed UUID values. The walkthrough does not contain real provider IDs or credentials.

| Rendered/input field | Canonical source / derivation |
|---|---|
| Tenancy name and breadcrumb | `org_tenancy.name`, local registry `id`; actual name observed, pending names explicitly labeled |
| Owner, direct manager, LOB, accountable leader, designees | Current owner association plus pinned applied organization revision/configuration; do not copy as a second tenancy authority |
| Signed-in administrator | Current authorized SSO session subject/display; sample identity is a lab label |
| Required user count | Count of required canonical operational access heads for this tenancy; excludes deferred audit identity and retiring obligations |
| Matching identity count | Current complete matching user/grant facts per required head, same target/generations; does not count unqualified repair powers or console readiness as verified |
| Emergency readiness | Latest qualified manual/provider evidence for recovery profile, captured in typed observation/audit; explicit unqualified status while method is pending |
| User type | Canonical operational head purpose `automation` or `independent_recovery`, rendered as human-readable label |
| Bound identity username | Domain binding's latest sanitized `observed.user_name` fact, with binding ID + OCI/SCIM references retained internally |
| Presence result | `otm_object_observation.result`, typed `observed.identity_presence`, complete authorized coverage; logical key identifies exact user |
| API authentication result | Typed `observed.authentication.result` plus named context/credential generation and probe-evidence fields below |
| Privilege result and profile label | `otm_access_assignment.profile_reference/profile_version` and typed `observed.privileges.result` and named evidence fields below; no generic-read shortcut |
| Console capability / enrollment display | Typed observed capability/policy/enrollment facts; use explicit “by intent” text for desired-only data |
| Expected block | Immutable assignment profile/parameters plus exact bound required subject/scope; expected observation snapshot |
| Observed block | Sanitized typed observation facts/diagnostics, no password/PEM/MFA material |
| Observation timestamp | Observation `captured_at` and check completed/start times; no browser clock claim of provider verification |
| Coverage and failure explanation | Check/observation typed coverage and diagnostics; stable result codes plus generic display text |
| Source checks / access-intent revisions | One check `id` and `access_assignment_id` per operational coverage owner, plus immutable assignment `revision_number`; the panel is a derived two-subject summary, never one check with two intent FKs |
| Per-user evidence reference / observed time | That row’s own scoped check/observation ID and `captured_at`; do not copy the latest aggregate time over older facts |
| Daily schedule / last check | `org_workspace.runtime_policy.access_checks.schedule` (daily), `.freshness_policy_version` plus scoped check timestamps/occurrence; no fabricated per-row success |
| Repair visibility and blocked guidance | Current issue, sufficient fresh exact-profile capability evidence, supported kind, entitlement/lifecycle/assignment guards |
| Repair preview target/steps/scope | Captured `action_preview` typed payload → immutable accepted operation/step intent; selected current issue/binding/assignment/generations |
| Check now / local feedback | Production accepted observation operation ID; walkthrough-only acknowledgment is transient and never advances a check head |
| Sample condition dropdown | Transient demonstration routing only, not a production database field or editable evidence |
| Runbook guidance | `org_workspace.runtime_policy.recovery.runbook_reference` + profile version; approved nonsecret artifact reference, no secret URL or activation link |
| Issue dates, resolution / operation progress | Shared issue episode + scoped evidence; current operation/steps queried independently, not copied into organization review |

The runtime policy properties above are part of the workspace’s closed versioned nonsecret schema.
Exact freshness durations and the approved runbook content remain qualification work; no hidden
default converts old evidence into permission to repair. The page’s current generic runbook guidance
is not a working runbook link or a claim the procedure is approved.

### Typed access observation envelope

Use `contract_version="access_observation/v1"` for these proposed bounded facts. Existing observation
columns store them; no new table is introduced. The closed `expected`/`observed` schema includes:

- `subject_binding_id`, `identity_domain_binding_id`, `user_name`, exact `provider_ocid` and
  `scim_resource_id` when present; identifiers remain distinct.
- `identity_presence`: present, missing, unknown, with completeness/authorization evidence.
- `authentication`: closed object with `result` (verified, failed, unknown, not_applicable),
  `access_context_id`, `context_generation`, `credential_version_id`, `credential_generation`,
  `probe_contract_version`, `evidence_event_id`, `failure_code`, `captured_at`. Non-applicable or
  unavailable values are nullable according to result; no key or signed request body is stored.
- `privileges`: closed object with `result` (matching, different, unknown), `profile_reference`,
  `profile_version`, `observed_group_binding_ids`, `observed_role_binding_ids`,
  `qualified_operation_keys`, `capability_evidence_event_ids`, `captured_at`. Matching observed grants
  is distinct from qualified operation evidence. Each capability receipt names its qualification/
  probe contract, exact target, signer/credential/context generations, covered operations, timestamp
  and evidence provenance; no UI label or cached boolean can invent that authority.
- `console_capability`: enabled, disabled, unknown; `mfa_policy_state` and `enrollment_state` as separate
  observed statuses, not a stored factor/seed. Desired capabilities remain on immutable access intent.
- `recovery_readiness`: qualified, needs_enrollment, unqualified, unknown; optional qualified
  `qualification_event_id`/`qualified_at` and profile version. A manual assertion is labeled manual,
  with authenticated witness/evidence contract, not falsely classified as an automated console test.

The check pins `coverage_subject_kind/key`, assignment/access generation, credential/context
generations, binding inventory and schema/profile versions. Expected/observed arrays have bounded
limits and validated same-tenancy references. Null means unavailable, never a false passing boolean.
Newly proposed observed/profile labels in this slice are not final OCI API field names.

## Required-grant composition: D35 A accepted

The user selected A on 21 October 2026: **one OTM root policy containing administrator-authored
statements plus a visible read-only required-access section**. Policy overrides replace the entire
authored section only; they cannot remove generated owner/automation/recovery/active-member
requirements. Quotas remain a complete-list replacement. Budget/tag behavior is unchanged. Owners
retain OCI administration; this protection is within OTM, not an assertion that owners cannot alter
cloud objects outside the tool. Such changes remain observable drift/access loss.

The editor, historical baseline view, override editor, conflict review and tenancy detail expose
the source distinction. A global baseline has no concrete tenancy identity, so its required section
is clearly a per-tenancy example, not content stored in the published baseline. The tenancy preview
shows the combined list destined for the same bound `policy/main` OCID. No second policy is created.
The final statement array is one OCI payload; the section boundary/provenance lives in OTM.

[Chapter10’s D35 field contract](10-configuration-data-model.md#d35-required-policy-manifest-and-rendered-evidence)
pins `required_policy_manifest`, `required_policy_manifest_hash` and `policy_render_contract_version`
on the immutable tenancy configuration revision. A grant workflow that changes this root-policy
manifest creates a new tenancy configuration revision using the same baseline/override values. It
does not publish a fleet baseline. Pure membership/direct-role changes that do not change the manifest
need no fabricated policy write. Active and accepted pending/retiring access obligations are taken
from the reviewed access workflow, never blindly from the feed or active members alone.

Required entries carry stable keys, immutable assignment/profile/template provenance and typed logical/
known binding references. At provider dispatch, registered rendering resolves qualified identity/domain/
compartment bindings into exact strings. Preserve immutable `policy_rendering` audit evidence with
`authored_policy_statements`, `required_policy_statements`, `effective_policy_statements`, manifest/
binding hashes, exact versions and target. Do not mutate accepted configuration/step inputs to fill
in later provider IDs. Missing bindings make rendering pending/blocked, never fake strings for OCI.

The effective list contains authored statements first, then required entries in stable key order.
Exact duplicate text is emitted once while every source/contributor remains in the manifest/evidence.
This is not semantic policy merging or proof of permissions. If the same statement supports another
assignment, removing one contributor must retain that statement until all obligations are gone.
Conflicting templates/references, unresolved scope or unavailable pinned renderer block dispatch.

All workflows changing `policy/main` use the same binding/revision/generation fence. Baseline/override
acceptance captures and rechecks the required manifest; a relevant access change invalidates stale
previews and bulk reviews before any write. During an ownership transition, preserve old and replacement
grants until replacement access verifies, then retire only the reviewed old obligations. Unknown prior
policy effects exclude another write until reconciled. A template/profile library deployment cannot
silently rewrite captured intent; profile changes require a separately accepted versioned operation.

Drift compares the complete bound policy with the captured authored+required list for its configuration
revision, not current-for-new baseline or latest profile code. Absence of a required statement is a
policy mismatch with missing-required provenance; inaccessible policy content remains Unable to verify.
Identity/group/domain-role checks remain separate and cannot be inferred from a matching policy.

The operating model is accepted; exact policy grammar, domain roles, permission qualification and
safe provider propagation/rotation behavior remain pilot gates. No OCI operation or DB migration is
implied by this design update. The walkthrough examples are inert and use illustrative group names.

## Validation and next slices

Planned contract cases: authorized 404 versus 403/timeout; partial inventory; stale late check;
recovery/automation coverage isolation; signer works but domain administration fails; missing account
recreation with new provider IDs; same-name collision; last-admin protections; assignment retired
mid-repair; unknown write; check-head generation changes; notification dedup/routing; and restored
credentials newer in Vault/OCI than the DB. These are not executed DB/provider tests.

The completed UI review (private historical evidence; not distributed)
passed 17 targeted interaction checks plus 16 layouts (three conditions and repair modal at 1440, 768,
390, 320px). A bounded reverse-Tab follow-up passed. A clean isolated console pass had no errors;
unrelated historical renderer errors are preserved separately in the receipt. Root inspected the
four final screenshots. The documentation review caught and closed the combined-check ambiguity:
each assignment now has its own visible source reference/time. No remaining concrete screen-field
mapping gap was found in that bounded review.

Final JavaScript syntax, all local document links/anchors, the inline-documentation checker and Ruff
passed. These checks validate design/source artifacts only; the application test suite, real database
concurrency and OCI/Vault permissions were not run or qualified. No prototype prototype/data/runtime changed.

Current: D40 administrator password disclosure/rotation screens and complete field maps are in chapter13. Verify the selected recovery-only MFA exemption and independent custody before declaring recovery
production-ready. Follow with C5 financial/source/freshness/notification screens and C6 operational
handoff. C1–C6 remain open; this slice is not a blanket implementation-ready approval.

## Documentation research receipt

Oracle's [domain API authorization guide](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/api-get-started.htm)
distinguishes supported API authorization from console username/password use. This supports separate
API-signing and human-console facts; it does not qualify the chosen repair profile.
Oracle's [session clearing guide](https://docs.oracle.com/en-us/iaas/Content/Identity/users/clear-signed-in-sessions-for-users.htm)
describes Keep Me Signed-In sessions; do not relabel it universal session/token revocation.
Oracle's [emergency access guide](https://www.oracle.com/apac/a/ocom/docs/security/oci-iam-emergency-access-accounts-v1.8.pdf)
describes local recovery and custodial MFA options. That source review preceded D39/D40: the recovery-only exemption and persistent recovery flow are now selected, while exact policy/login/restoration behavior remains provider qualification. Sources checked 21 October 2026;
no OCI endpoint, production credential or provider account was used.


## D38 presentation update — 24 October 2026

Required users, Administrator access and Recovery share access-page navigation. Required-user results
and the next action are primary; Check details collapses existing expected/observed/coverage/source
facts. Repair opens a short confirmation and Start repair acknowledges a sample request without
clearing its issue. No automated repair is offered when automation cannot authenticate. The captured
repair authority, generation, dispatch and verification guards above still apply in production.
Scenario selection moves to the collapsed preview footer. See [chapter13](13-local-support-and-emergency-access.md#d38-accepted-product-screens-and-separate-design-narrative)
for the updated flow and field mapping, and the current UI review (private historical evidence; not distributed).
Earlier evidence in this chapter predates this presentation change. No model fields are removed.

D40 tab continuity: all current required-user fixtures have an unverified recovery sign-in exemption, so Administrator access opens the blocked state. Matching user observations alone cannot enable Get password. A future verified-ready record may open the available state only with the full readiness evidence.


## Required-user presence foundation — 6 November 2026

The [internal implemented boundary and full field map](../reference/required-user-presence.md)
separates automation/recovery subject identity, inspecting authority and returned presence evidence.
Only Present/Missing/Unknown are implemented; no privilege, signer, console or recovery-readiness
qualification follows. These are typed transport models, not new database tables or established
foreign keys. ER diagrams and current persisted schema are unchanged. Current onboarding does not
yet retain permanent user bindings; verified binding capture and live-head checks must precede
worker/UI composition. There is no guessed backfill, API route, schedule, repair, secret retrieval
or saved-instance change. The broader proposed access model above remains future work.
