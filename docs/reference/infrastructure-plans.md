# Private infrastructure plans

16 November 2026 · Source-only, plan-only checkpoint · Live OCI qualification pending

[Documentation home](../README.md) · [Operator procedure](../how-to/infrastructure-plans.md) ·
[Environment design](../engineering-design/24-environments-and-promotion.md)

## Implemented boundary

The manual [staging workflow](../../.github/workflows/infra-staging.yml) and
[production workflow](../../.github/workflows/infra-production.yml) invoke
[`otm.infrastructure_plan`](../../backend/src/otm/infrastructure_plan.py) from the exact protected
master source. Each selects only its own `security` or `platform` root. State-bucket bootstrap
remains a separately authorized operator procedure. There is no apply, destroy, deployment,
production promotion or arbitrary Terraform command/ref/path input.

Workflows require deliberate `OTM_INFRASTRUCTURE_ENABLED=true`; absence means failure before
federation. No GitHub environments, secrets, IAM trusts or OCI resources are configured by adding
these files. Configure and qualify environment protection before enabling either workflow.
The fixed GitHub Environment must restrict deployment branches to master and require the selected
human reviewer. An environment name or enable flag alone is not proof of protection or authorization.

The current slice is intentionally **not** the complete plan/review/apply milestone. A future apply
consumer must independently verify trusted successful plan-run/source identity, current private
inputs, the reviewed plan hash, state freshness and production approval. It must apply the reviewed
environment's exact plan, never a staging plan to production. Nothing here supplies those apply gates.

## Federation contract

The owner selected GitHub-hosted runners with a separate restricted OAuth client secret in each
protected GitHub Environment. The confidential client needs token-exchange permission, not an
identity-domain administrator role. Bootstrap trust administration uses separate authority that
never enters this workflow. This is federation without persistent OCI user signing keys, **not
fully secretless authentication**.

Each approved job requests a GitHub JWT with audience `otm-infrastructure-staging` or
`otm-infrastructure-production`. It generates a fresh RSA 2048 pair through a fixed, shell-free
OpenSSL invocation with no inherited credential/configuration environment. The private key is
never sent to GitHub or OCI. Only the public key and GitHub JWT enter the verified identity-domain
`/oauth2/v1/token` request. Both HTTP paths reject redirects and use verified TLS, a 25-second
timeout and bounded JSON responses. The response's `res_tenant` and expiry fence target/lifetime
mistakes; parsing claims is not a substitute for OCI verifying the signed workload JWT.

The exchange requests a 60-minute RPST. The returned session must have more than 35 and at most 70
minutes remaining. Jobs have a 30-minute hard timeout; Terraform commands share a 20-minute budget.
No human approval waits inside a live credential window. There is no refresh-token daemon or
automatic credential fallback. A new job mints a new pair/session. Failures remain visible.

Provider 9.13.0 supports direct `WorkloadIdentityFederation`, but Terraform 1.15.5's native OCI backend
does not. The common supported boundary is explicit `ResourcePrincipal` for **both**, using:

| Variable | Value passed only to the Terraform child |
| --- | --- |
| `OCI_RESOURCE_PRINCIPAL_VERSION` | `2.2` |
| `OCI_RESOURCE_PRINCIPAL_RPST` | Absolute private temporary token-file path |
| `OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM` | Absolute matching private PEM-file path |
| `OCI_RESOURCE_PRINCIPAL_REGION` | Validated `us-ashburn-1` target region |

Token/key contents do not appear in variables, backend JSON, Terraform CLI arguments or GitHub
environment output files. Existing operator `SecurityToken` defaults remain unchanged; this
workflow explicitly overrides backend and provider authentication. Ambient OCI/TF overrides,
GitHub credentials and OTM secrets are removed from the Terraform child environment. The child
uses an empty private Terraform CLI configuration, its own data directory and the default workspace.
Pinned provider lockfiles remain read-only. A different installed Terraform version is rejected.

Before activation, configure the trust for the exact GitHub issuer/JWKS and audience. Five exact
claim validations can bind immutable `repository_id`, `repository_owner_id`, `environment`,
`ref=refs/heads/master` and the environment's exact `workflow_ref`. Do not assume a legacy default
`sub` format, wildcard/OR rules or that issuer/audience checks alone authorize a repository.
OCI documents unique trust issuers; reuse of the GitHub issuer for additional application-delivery
workflows in the same domain needs a separately qualified trust/IAM design. Do not create extra
domains or relax claims implicitly. Effective OCI IAM must independently constrain state/plan
objects, discovery and resource reads to the intended environment. No complete external-principal
IAM policy is invented by this source checkpoint.

Primary contracts: [OCI JWT-to-RPST exchange](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/token_exchange_grant_type_workload_id-federation.htm),
[pinned provider federation](https://github.com/oracle/terraform-provider-oci/blob/v9.13.0/internal/provider/workload_identity_federation.go),
[pinned backend authentication](https://github.com/hashicorp/terraform/blob/v1.15.5/internal/backend/remote-state/oci/auth.go),
[GitHub OIDC claims](https://docs.github.com/en/actions/reference/security/oidc).

## Inputs

These names belong to the selected GitHub Environment, never repository-wide shared credentials.
All settings below are documented configuration, not actual configured values.

| Input | Kind and effect |
| --- | --- |
| `OTM_INFRASTRUCTURE_ENABLED` | Variable; exactly `true` only after live setup/qualification; otherwise held |
| `OTM_INFRA_IDENTITY_DOMAIN_URL` | Secret (private coordinate); exact HTTPS `*.identity.oraclecloud.com` origin, no port/path/query/fragment |
| `OTM_INFRA_CLIENT_ID` | Secret (private reference); environment's restricted token-exchange client |
| `OTM_INFRA_CLIENT_SECRET` | Secret; environment-specific OAuth credential; never bootstrap/admin authority |
| `OTM_SECURITY_INPUTS_JSON` | Secret; JSON with only `target` and `database_provisioner_group_ocid` |
| `OTM_PLATFORM_INPUTS_JSON` | Secret; private existing platform input JSON, excluding the separately rendered fields below |
| `OTM_HOSTING_COMPARTMENT_OCID` | Secret (private reference); existing single hosting compartment; both roots reuse its renderer |
| `OTM_ALLOWED_SOURCE_CIDRS` | Secret (private configuration); comma-separated canonical IPv4 CIDRs, validated by the existing platform/recovery parser; platform only |
| `OTM_OKE_KUBERNETES_VERSION` | Variable; exact canonical reviewed `vMAJOR.MINOR.PATCH`; platform only |
| `OTM_POSTGRESQL_VERSION` | Variable; reviewed two-digit managed major; platform only |
| `OTM_WORKER_CLOUD_INIT` | Secret; existing bounded Bash/cloud-init renderer; syntax checked, never executed by this workflow |

Selected JSON is passed as `OTM_INFRASTRUCTURE_INPUTS_JSON`. `target` has exactly `environment`,
`tenancy_ocid`, `object_storage_namespace` and `region`; explicit region is `us-ashburn-1`.
Platform JSON may contain only `target`, `vcn_cidr`, `oke`, `database_administrator`, `database`,
`application_vault_ocid`, `qualified_node_image`, `smtp_egress` and `caddy_ingress_enabled`.
Native Terraform validation remains authoritative for each existing variable's structure/bounds.
Authentication, versions, compartment, allowlist and cloud-init cannot be overridden in that JSON.
Existing [input examples](../../infra/environments/staging/platform/terraform.tfvars.example) describe
the fields, but are synthetic HCL examples, not JSON to paste verbatim. Production's qualified-image
record still requires the separate staging evidence/handoff; a record alone is not acceptance.

## Private plan and public result

All inputs, keys, tokens, raw Terraform output and the binary plan use a private temporary directory.
Normal success/failure cleans it and restores the process umask. Hard runner loss/cancellation is
also a hosted-runner custody qualification item; this is not secure erasure or indefinite token renewal.
No public log contains the full Terraform plan or provider diagnostics. The workflow uploads no
GitHub artifacts, database data, source feed, private configuration or state.

After planning with state locking, the source inspects JSON action kinds and creates a two-file tar:

- `plan.tfplan`: secret-bearing binary plan, not an approval or executable deployment bundle.
- `receipt.json`: source/run/attempt/environment/root, private-input digest, plan digest and counts.

The fixed private destination is the existing `otm-<environment>-tfstate` bucket in that target's
namespace, under `infrastructure-plans/<environment>/<component>/<run>/<attempt>/plan.tar`.
The SDK checks its expected hosting compartment, `NoPublicAccess` and enabled versioning before
conditional `if-none-match:*` creation. No additional bucket, compartment, database or registry is
introduced. State retains its existing separate `security/...` and `platform/...` keys; a plan object
is never a state file. OCI and IAM must qualify actual object conditional-write semantics and encryption.
Private plans can contain cloud-init and other sensitive values; restrict retrieval accordingly.

Only these public JSON fields are emitted after successful upload: `status=planned`, `environment`,
`component`, `source_sha`, `run_id`, `attempt`, `inputs_sha256`, `plan_sha256`, `changes`, `object_key`
and `applied=false`. Counts separate create/update/delete/replace; replacements do not masquerade
as harmless updates. Resource names, identifiers, settings and raw errors are excluded. Failure returns
exit 1 with fixed `INFRASTRUCTURE_PLAN_FAILED` guidance for preparation failures. Missing or invalid
CLI choices return argparse usage errors with exit 2 and no receipt. Failed/uncertain uploads do not become success;
do not rerun an uncertain request before inspecting its exact private object.

## Qualification boundary

Synthetic tests cover both roots/environments, fixed-context and target guards, input renderers,
TLS/no-redirect/auth response failures, token target/lifetime, actual local key generation, private
archive shape/custody, unknown Terraform actions, command budgets, cleanup and public diagnostics.
These do not validate a real IAM trust, backend lock, provider read, OAuth secret or OCI object upload.
No schema, ER model, application UI or saved local instance changes are required.
See [the live manifest](../how-to/real-oci-test-manifest.md) before enabling hosted plans.

### Local source checkpoint — 16 November 2026

Complete-source backend unit validation passed 3,109 tests with 95.5339% line coverage across 200
modules; frontend unit validation passed 650 tests with 96.99% line coverage. The complete disposable
PostgreSQL/native-worker/Playwright run passed 472 cases with zero failures, errors or skips and no
persistent database use. Existing native Terraform mock suites and eight replacement guards passed.
Native Caddy/ACME and image-policy checks passed with the same two approved findings and no blocked
finding. Source/purpose, documentation links/contracts, publication and credential checks passed;
independent security and documentation reviews closed their findings without scanner exceptions.

The SDK-construction test uses actual generated keys and a synthetic session to construct the
installed file-backed signer/client, explicitly prohibiting API calls. It is not signature, IAM or
service qualification. No app snapshot, migration, UI or dependency lock changed. This is a local
plan-only source checkpoint, not a new hosted workflow, image-publication or deployment qualification.
The complete milestone's normal PR/CI gates and the live checklist remain required before release.
