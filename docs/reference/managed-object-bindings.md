# Canonical managed identity bindings

This is the first implemented subset of `otm_managed_object_binding`, from the
[approved generic binding model](../engineering-design/10-configuration-data-model.md#5-otm_managed_object_binding-which-oci-objects-belong-to-otm).
A fresh version 3 onboarding capture creates exactly three rows: an observed identity-domain
reference and the permanent automation/recovery users. It records identity and ownership intent,
not account health, credentials, administrator privileges or permission to repair.

## Three-row structure

| Logical key | Kind / ownership | Exact provider identity | Domain reference |
| --- | --- | --- | --- |
| identity/domain | identity_domain / observed_reference | Discovered domain OCID; no SCIM ID or fabricated name | Null |
| identity/user/automation | managed_user / managed | Read-back user OCID and separate SCIM resource ID; observed username is a label | Same child's domain binding |
| identity/user/recovery | managed_user / managed | Separate read-back user OCID and SCIM resource ID | Same child's domain binding |

`active` means the current canonical identity mapping. A binding can be active while its tenancy
is still pending after capture or cleanup failure. Future checks must also qualify the child
lifecycle and current authority heads; this flag alone cannot make the tenancy operational. It does **not** mean the account can sign,
log in, administer the tenancy or release a password. No access assignment, access generation,
credential/context head, MFA state or console endpoint is fabricated from this mapping.

## Physical fields — all 18 columns

| Field | Type / meaning |
| --- | --- |
| id | UUID primary key, allocated once for the stored binding, never a substitute OCI identifier. |
| workspace_id | Bounded workspace ID; included in every scoped reference and query. |
| tenancy_id | Same-workspace registered child UUID. Parent/organization/tenancy OCIDs are joined from the registry and source evidence, not copied as editable binding attribution. |
| logical_key | One of the three keys above; stable identity role, never selected by a person's name or email. |
| kind | identity_domain or managed_user. Other proposed kinds need a later handler/migration. |
| handler_contract_version | required-user-binding-1. |
| generation | Positive object-binding generation, initially 1. No replacement/rebinding flow is implemented. This is not an access-health generation. |
| identity_domain_binding_id | Nullable same-workspace/same-child binding UUID; mandatory for users and null for the domain. The referenced active row must be the exact observed domain from the same capture. |
| provider_ocid | Required domain/user OCID with the matching resource prefix; immutable. |
| scim_resource_id | Required nonblank SCIM ID for a user, null for the domain; never stored in provider_ocid. |
| user_name | Required bounded observed username for a user, null for the domain. Display metadata, never an adoption or authentication key. |
| ownership_mode | observed_reference for the domain, managed for the permanent setup users. Observing a domain does not make OTM its destructive owner. |
| state | active or retired. No arbitrary replacement/update state is exposed. |
| created_operation_id | Same-workspace operation UUID, jointly referenced with its exact capture evidence. |
| source_evidence_event_id | Immutable onboarding_outcome audit event UUID for the exact successful capture; its IDs/scope must agree with every binding. |
| retired_operation_id | Null while active; required same-workspace termination-initiation operation when retired. Creation provenance remains unchanged. |
| created_at | UTC timestamp of the accepted capture evidence, not proof of an OCI calculation or independent current read. |
| updated_at | Same timestamp at insertion; advances for logical retirement and cannot precede created_at. |

## Acceptance, replay and retirement

The simulation worker retains typed capture evidence, then inserts all three mappings within its
existing locked transaction before temporary cleanup. A nested savepoint rolls back the entire
three-row insert if any row fails; the onboarding step becomes blocked and cleanup does not run.
Retry appends fresh evidence and may complete the same workflow.

Before insertion, the application validates the audit hash, typed outcome, exact current verified
capture step, accepted workspace/organization/parent/child, source timestamp and identifiers. Managed
ownership also requires the same intent's six verified setup steps: establish_automation,
verify_automation, configure_required, verify_required, configure_baseline and verify_configured_access.
The database independently checks source kind/outcome, current operation/step, the pending child
reservation, those prerequisite steps, domain/user identity agreement and scoped foreign keys.
This records the setup contract's management intent; actual OCI creation/probes remain unqualified.

One active key and one active provider OCID are allowed per child; user SCIM identities are also
unique within the child's bound domain. Replaying the identical source returns the same three IDs
and generation. Partial, conflicting, retired or differently sourced mappings fail closed instead
of being overwritten or adopted. There is no replacement API.

Verified termination initiation retires the local mappings atomically with existing lifecycle
publication. The database requires the exact reserved child/current accepted deletion intent.
Creation IDs and evidence survive. Retirement neither deletes the domain/user objects itself nor
waits for final OCI termination after the hold period. Failed initiation keeps the mappings.

## Historical behavior and privileges

There is no startup, GET or ordinary worker-redelivery backfill. Earlier versions and already-recorded
version 3 captures remain unbound if they have no rows; unbound must be presented as unverified,
not Missing or healthy. A separately designed fresh reinspection is required before adopting them.

The installed API role has SELECT only. The worker can SELECT/INSERT and update only state,
retired_operation_id and updated_at. Immutable-identity/provenance and no-delete/no-truncate triggers
also protect the table. The owned laptop-only organization reset explicitly includes this table,
under its existing container/owner/local-mode/settled-simulation guards; retained operation/audit and
administrator history remain untouched. No new reset HTTP endpoint is introduced.

Migration **0023_managed_identity_bindings** adds this table, scoped constraints, live uniqueness
indexes and guards; earlier frozen migrations remain unchanged. Existing policy/quota/budget/tag
observations retain their current storage and behavior. Other kinds, assignments, credentials,
replacement and check heads remain proposed future subsets of the same model.

## ER and qualification boundary

[Rendered SVG](../architecture/diagrams/managed-identities-implemented.svg) ·
[PNG](../architecture/diagrams/managed-identities-implemented.png) ·
[Mermaid source](../architecture/diagrams/managed-identities-implemented.mmd) ·
[Excalidraw annotation artifact](../architecture/diagrams/managed-identities-implemented.excalidraw).
The ER Excalidraw export contains a rendered image for annotation, not editable entity cells.

Unit tests cover source scope/hash/step/version, stable replay, conflicting rows and sanitized failures.
Disposable PostgreSQL tests cover actual capture persistence, rollback/retry, scope/provenance
constraints, termination success/failure, historical unbound behavior and installed role privileges.
The full native browser flow exercises onboarding with the real worker/database; no new UI or Access
screen is introduced. Saved review instances remain unchanged until deliberately upgraded.

The [presence boundary](required-user-presence.md) is still not composed into durable checks.
Its targets require real scoped assignment/context/credential heads in addition to these identity
mappings. No readiness, repair, notification or password-disclosure authority follows from a binding.
All real-provider behavior remains Pending in the [manual manifest](../how-to/real-oci-test-manifest.md).
