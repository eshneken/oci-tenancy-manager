# Internal tenancy inspection

28 October 2026 · First production provider capability · No live OCI integration

[Backend setup](../../backend/README.md) · [Execution design](../engineering-design/09-execution-contracts.md)
· [Production data dictionary](../engineering-design/11-production-data-model.md)

## Boundary and current scope

`InspectionProvider.inspect_tenancy` is the first typed provider capability. `TenancyInspection`
validates its output before a caller consumes confirmed facts. The only implementation today is
`SimulatedInspectionProvider`; it performs no SDK, network, database, secret or email operation.
No inspection HTTP route is mounted. The default application factory remains process-liveness
only; the separate [local HTTPS application](local-application.md) explicitly enables authentication
and administrator directory/revocation without exposing this provider capability.

This provider boundary remains an internal read, not an accepted onboarding operation, SSO decision
or proof a signer can write. The [durable simulated worker](worker.md) now loads committed intent,
checks injected authority and attempt generations, and persists scoped normalized evidence. Real
credential resolution and corporate dispatch-policy integration remain future work; structurally
valid messages cannot replace them. No create, terminate, bootstrap, identity or policy write capability
is exposed by this slice.

## Field traceability

The Python models in `src/otm/providers/inspection_contracts.py` are authoritative for this implemented
subset. The wider chapter09 JSON pack remains a design artifact; its historical `home_region` shorthand
is expanded here to the distinct raw key and qualified identifier already required by chapter 11.
The internal version label remains `execution-1-draft`; this is not a stable public HTTP API.

| Runtime fields | Meaning / design destination when persistence is implemented |
|---|---|
| `contract_version`, `kind` | Explicit version and discriminant; undeclared command/result fields are rejected |
| `context.workspace_id`, `operation_id`, `step_key`, `attempt_id` | Original workspace, operation/step and exact execution attempt; correspond to operation/step and immutable audit evidence in chapter 11 |
| `intent_revision`, `execution_generation` | Frozen intent and dispatch ownership metadata; this read service does not query their current database authority |
| `access_binding_id`, `credential_generation` | Selected scoped access and generation; no credential values. The simulator checks these against its own seeded binding; real resolution is future dispatcher/adapter work |
| `payload.organization_id`, `parent_tenancy_ocid`, `tenancy_ocid` | Expected organization, control parent and exact child, from trusted committed intent; OCID syntax alone does not prove existence or registration |
| `tenancy.actual_name`, `tenancy_ocid` | Observed facts; future publication maps to `org_tenancy.name` and `tenancy_ocid` without silently retargeting |
| `tenancy.home_region_key`, `home_region_identifier` | Preserve the raw OCI key and a separately qualified SDK identifier. Identifier is nullable and never inferred just by copying the key |
| `tenancy.parent_tenancy_ocid`, `organization_id`, `role` | Actual observed parent/organization/child facts; a real adapter needs authorized organization evidence, not GetTenancy alone |
| `observed_at` on result/facts/evidence | UTC capture times; future metadata/audit publication retains provenance. All must fall within this synchronous read attempt |
| `provider_request_id`, `provider_operation_id` | Safe optional correlations, not permission to adopt another operation's outcome |
| `milestone`, `identity` | Only `tenancy_inspected`, with identity null. Inspection cannot claim bootstrap, onboarding or termination completion |
| `safe_code`, `continuation` | Closed diagnostics and manual/observe guidance. They do not enqueue work or define a retry policy |
| `evidence[].code`, `evidence_ref` | READ_BACK plus immutable observation reference. The simulator retains `(attempt_id, facts)` in memory; a reference is not yet a durable application audit event |

OCI's [Tenancy model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/models/oci.identity.models.Tenancy.html)
returns a home-region key. This slice implements no region discovery/mapping or parentage SDK call;
its synthetic fixtures explicitly supply facts. The read facade itself adds no registry. The subsequent [admission slice](admission.md) implements
operation/audit tables; the [worker migration](worker.md) now adds a logical step table. The full proposed production inventory is 30 application
tables; the separate prototype still has its ten existing tables.

## Outcomes and verification

- **Confirmed:** only an inspected child. Attempt, child, parent and organization must match the
  request; a parent cannot confirm itself as its own child. Evidence and facts must be captured
  between this call's start and end. This capability intentionally performs fresh reads; cached
  observations need a future explicit freshness policy.
- **Unobservable:** unverified/denied access, delayed visibility, read timeout or an unavailable
  record. Lack of evidence never becomes a confirmed Missing state or authorization to delete.
- **Unsupported:** the capability is not qualified for that case. No signer/privilege/identity-mode
  fallback is performed.

Malformed output, wrong correlation/target/time or an unexpected adapter exception raises a fixed
`ProviderContractError`. Raw provider errors are not chained into the workflow diagnostic. This
normalizes a contract violation; it does not classify its cause as a successful/absent resource.
No raw provider responses, credentials or arbitrary SDK kwargs are accepted by the message models.
Validation inputs are hidden in ordinary error text, but exception dictionaries/arbitrary strings
still must not be logged as though a type check were a redaction guarantee.

## Stateful simulator and tests

The simulator stores access by `(workspace, binding)` and provider facts by `(workspace, child)`.
Permission loss and credential-generation changes affect later reads; it does not return cached
success. A new credential generation is resolved in a new attempt. The manual clock supports delayed
visibility without sleeps. Named read faults cover denied access, timeouts and unsupported capability.
Evidence snapshots survive later simulated changes, but all simulator state is in-memory and is lost
on process exit. It is not a provider emulator for writes, paging, rate limits, activation or crashes.

Tests cover the message families, exact result pairing, source/attempt freshness, populated workspace
isolation, revoked/rotated access, delayed visibility, unavailable records and fixed error diagnostics.
Overlapping identifiers in adversarial workspace fixtures test isolation; they do not authorize a
real child to be registered twice in the production controller. The real-adapter contract suite,
actual IAM/parentage/region behavior and durable publication remain unqualified.

## Generated structural schemas

```sh
uv run --project backend python scripts/export_backend_contracts.py
uv run --project backend python scripts/export_backend_contracts.py --check
```

These commands generate/check `backend/contracts/inspection-command.schema.json` and
`inspection-result.schema.json` from the models. The checks fail for missing or stale artifacts;
no handwritten runtime wire-schema copy is maintained. The schemas carry structural constraints,
not every custom validator: Python enforces UTC-only offsets, whitespace-only value rejection and
request/result pairing. Runtime model/service validation remains authoritative. The relevant
[Pydantic configuration](https://docs.pydantic.dev/latest/api/config/) describes strict instance
revalidation; the generated schema alone does not establish authorization or semantic verification.
