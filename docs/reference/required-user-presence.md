# Required-user presence boundary

This is the first internal access-health foundation. It implements exact-identity presence reads
for **automation** and **recovery** users, independently per subject. It does not yet add an Access
screen, API route, database table, native job, scheduled scan, notification or repair action.
The audit user remains V2. Existing saved tenancies are not backfilled or declared healthy.

New version 3 onboarding now retains [exact permanent-user capture evidence](tenancy-onboarding.md#permanent-user-capture--6-november-2026)
before temporary cleanup. Historical operations are not backfilled. Fresh captures now also retain [canonical domain/user bindings](managed-object-bindings.md).
Access-assignment/context/credential heads are not yet implemented. Establish those scoped heads
before composing presence reads into an application worker or UI.
Never reconstruct a required identity from a username, email, successful setup label or naming rule.

## What a result establishes

| State | Required evidence / interpretation |
| --- | --- |
| Present | Complete authorized exact-subject read, verified domain/SCIM scope, exact observed bound identifiers and an in-window capture time. Only existence is established. |
| Missing | Complete authorized absence for that exact subject in the qualified domain. A domain lookup failure or wrong-domain404 is not evidence of absence. |
| Unknown | Unavailable/unverified authority, denied or timed-out read, delayed visibility, incomplete coverage, unqualified domain or unsupported capability. No confirmed identity facts are returned. |

Present does **not** establish API signing, administrative privileges, enabled console access,
MFA exemption/enrollment, usable recovery custody or permission to repair. These are separate facts
in the [approved access design](../engineering-design/12-access-health-and-repair.md). The model
contains no can_repair, password, PEM key or MFA material. An authorized but incomplete observation
still stays Unknown. `authorized` records established authorization evidence for this exact read;
false does not itself prove that the user lacks general privileges. Safe codes distinguish denial
from other unverified conditions.

## Typed field map

Source types live in `backend/src/otm/providers/required_user_contracts.py`; this is the narrow
`required-user-presence-1` internal message version, not the full proposed access_observation/v1.
No HTTP/generated public contract is added in this checkpoint.

| Model | Fields / boundary |
| --- | --- |
| RequiredUserTarget | Inherited organization_id, parent_tenancy_ocid, tenancy_ocid; workspace_id, registered tenancy_id, purpose, subject_binding_id, binding_generation, access_assignment_id, access_generation, identity_domain_binding_id, domain_ocid, scim_resource_id, nullable provider_ocid, user_name. Only automation/recovery and a child distinct from its parent are accepted. Names are labels, never lookup/adoption keys. |
| RequiredUserReadContext | Existing ExecutionContext: workspace_id, operation_id, step_key, attempt_id, intent_revision, execution_generation, access_binding_id, credential_generation; adds context_generation and nullable credential_version_id. This describes the inspecting authority, independently of the subject being checked. Null is explicit, never an alternative-credential fallback. |
| InspectRequiredUser | contract_version, context, target. Context/target workspace must agree. This internal command grants no authorization. |
| ObservedRequiredUser | Actual domain_ocid, scim_resource_id, nullable provider_ocid, user_name. OCI and SCIM identifiers are kept separate; an observed name change cannot select another identity. |
| RequiredUserObservation | contract_version, context, target, captured_at, nullable read_id, checked_domain_ocid, checked_scim_resource_id, state, safe_code, authorized, complete, nullable observed. Confirmed states require nonnull read/checked-identity references. Unknown forbids complete coverage and observed identity facts. |

References/generations are transport provenance in this foundation, not newly implemented foreign
keys or proof that a current database assignment exists. `read_id` is an opaque per-read correlation,
not a durable audit receipt or repair authority. The future worker must resolve/recheck live
administrator/machine authority, active assignments, lifecycle and credential/binding generations
before and after acquisition, then seal separate per-subject evidence/current heads. A pairing
wrapper cannot perform those database checks by comparing echoed fields alone.

## Contract and simulator separation

- `providers/required_user.py` contains RequiredUserProvider and the RequiredUserInspection validation
  wrapper. It imports no concrete simulator or OCI SDK. Composition must select an adapter explicitly.
- `providers/required_user_contracts.py` contains closed nonsecret models, using shared contract and
  inspection primitives. Neutral types accept non-synthetic OCID shapes without claiming membership.
- `providers/required_user_simulator.py` holds independent fake authority, domain and user fixtures.
  Only synthetic child/domain/user fixtures are accepted. No API/worker composes it automatically,
  and there is no product simulation control or live fallback.

The wrapper revalidates provider results and pairs all context/target/generation fields, actual
checked/observed identifiers and aware-UTC capture time with the call window. Wrong-domain results,
changed OCID mappings, cross-subject facts and stale observations fail closed. Same-name identities
are never adopted; the same exact identity can return changed username metadata. Unnormalized
exceptions become fixed diagnostics with suppressed raw error chaining.

The simulator can establish Missing only after an explicitly configured complete domain and matching
read authority. An unconfigured domain or authority is Unknown. A missing exact-user entry establishes absence
only within an explicitly complete, authorized fake-domain state. Reads of recovery and automation
remain independent. Simulator facts do not qualify real OCI authorization, SCIM404 semantics, live
credentials or eventual consistency. No account is created, removed, repaired or queried in OCI.

## Integration order and qualification

1. Implement exact permanent identity/domain binding capture from verified onboarding readback;
   existing unrecorded bindings remain unverified, with no guessed historical backfill.
2. Add durable scoped assignments/observations, authenticated read-only checks and the Required users
   page using current-generation guards and the existing operation/native worker machinery.
3. Add independently qualified signer/privilege/console/recovery-readiness probes, bounded identity
   repair and event-driven notifications. Password custody/disclosure/rotation is a separate slice.

Unit tests exercise both purposes, exact subject scope, correct absence versus domain failure,
partial/denied/timeout/delayed/unsupported reads, same-name nonadoption, returned context/generation
fences, optional identity references, strict clock windows and sanitized errors. Fresh-process import
tests reject simulator imports from neutral modules. Existing full PostgreSQL/Playwright suites
remain regression gates; they do not yet execute this uncomposed presence capability. Real cases
remain pending in [the pending account-read checklist](../how-to/configuration-drift-runbook.md#pending-required-user-presence-qualification).


Fresh canonical identity bindings now exist as described in the
[binding field map](managed-object-bindings.md). They do not themselves supply the required target's
access_assignment_id/access_generation or the inspecting credential/context heads. Historical
captures remain unbound; no synthetic assignment IDs are generated to bypass this integration step.


The later [Required users identity-record view](required-users-screen.md) now exposes these stored
facts in tenancy detail. Earlier no-UI statements describe the prior checkpoint; live presence/
permission checks, authority heads, readiness and repair are still not composed by this read-only
section. See its field map and local test runbook for the implemented boundary.
