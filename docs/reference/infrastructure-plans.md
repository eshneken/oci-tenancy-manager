# Private infrastructure plans

16 November 2026 · Held plan/review/apply source · Live OCI qualification pending

[Documentation home](../README.md) · [Operator procedure](../how-to/infrastructure-plans.md) ·
[Environment design](../engineering-design/24-environments-and-promotion.md)

## Implemented boundary

The manual [staging workflow](../../.github/workflows/infra-staging.yml) and
[production workflow](../../.github/workflows/infra-production.yml) invoke
[`otm.infrastructure_plan`](../../backend/src/otm/infrastructure_plan.py) from the exact protected
master source. Each selects only its own `security` or `platform` root. State-bucket bootstrap
remains a separately authorized operator procedure. The default operation is `plan`; `apply` invokes
[`otm.infrastructure_apply`](../../backend/src/otm/infrastructure_apply.py) to consume a separately
reviewed saved plan. There is no destroy operation, application deployment or arbitrary Terraform
command/ref/path input.

Workflows require deliberate `OTM_INFRASTRUCTURE_ENABLED=true`; absence means failure before
federation. Apply additionally requires `OTM_INFRASTRUCTURE_APPLY_ENABLED=true`. Both variables
default to false in the workflows; enabling plans does not enable apply. No GitHub environments, secrets, IAM trusts or OCI resources are configured by adding
these files. Configure and qualify environment protection before enabling either workflow.
The fixed GitHub Environment must restrict deployment branches to master and require the selected
human reviewer. An environment name or enable flag alone is not proof of protection or authorization.

The apply consumer authenticates the successful producer run and exact attempt/job logs, checks
current private inputs and the reviewed binary-plan hash, then applies only that environment's saved
plan. Production additionally requires a successful staging apply of the same source/component,
shared-input parity and explicit manual staging-test confirmation. These are implemented guards,
not evidence of configured production approval or an exercised OCI apply. Terraform retains native
state locking/stale-plan checks; an obsolete plan must be regenerated and reviewed.

Development uses the fixed `custody` root, its own private bucket and state key, and one
protected GitHub Environment and federated principal. Every dispatch requires approval, and
apply also requires explicit enablement and an exact reviewed plan without deletion or replacement.
Once apply permissions are granted, both dispatches use that principal's effective OCI permissions. See the [development setup](../how-to/laptop-oci-development.md#development-custody-through-github-actions).

## Federation contract

The owner selected GitHub-hosted runners with a separate restricted OAuth client secret in each
protected GitHub Environment. The confidential client needs token-exchange permission, not an
identity-domain administrator role. Bootstrap trust administration uses separate authority that
never enters this workflow. This is federation without persistent OCI user signing keys, **not
fully secretless authentication**.

Each approved job requests a GitHub JWT with audience `otm-infrastructure-staging` or
`otm-infrastructure-production` for those hosted environments. Development uses
`otm-infrastructure-development`. It generates a fresh RSA 2048 pair through a fixed, shell-free
OpenSSL invocation with no inherited credential/configuration environment. The private key is
never sent to GitHub or OCI. Only the public key and GitHub JWT enter the verified identity-domain
`/oauth2/v1/token` request. Both HTTP paths reject redirects and use verified TLS, a 25-second
timeout and bounded JSON responses. The response's `res_tenant` and expiry fence target/lifetime
mistakes; parsing claims is not a substitute for OCI verifying the signed workload JWT.

Planning requests a 60-minute RPST (more than 35 and at most 70 minutes remaining), with a
30-minute job timeout and shared 20-minute Terraform budget. Apply requests a 120-minute RPST
(more than 95 and at most 130 minutes remaining), with a 90-minute job timeout and shared
75-minute Terraform budget, including initialization, inspection, apply and output reads.
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
| `OTM_INFRASTRUCTURE_APPLY_ENABLED` | Separate variable; exactly `true` required for apply; defaults false independently of plan enablement |
| `OTM_INFRA_IDENTITY_DOMAIN_URL` | Secret (private coordinate); exact HTTPS `*.identity.oraclecloud.com` origin, no port/path/query/fragment |
| `OTM_INFRA_CLIENT_ID` | Secret (private reference); environment's restricted token-exchange client |
| `OTM_INFRA_CLIENT_SECRET` | Secret; environment-specific OAuth credential; never bootstrap/admin authority |
| `OTM_SECURITY_INPUTS_JSON` | Secret; JSON with only `target` and `database_provisioner_group_ocid` |
| `OTM_PLATFORM_INPUTS_JSON` | Secret; private existing platform input JSON, excluding the separately rendered fields below |
| `OTM_HOSTING_COMPARTMENT_OCID` | Secret (private reference); existing single hosting compartment; both roots reuse its renderer |
| `OTM_ALLOWED_SOURCE_CIDRS` | Secret (private configuration); comma-separated canonical IPv4 CIDRs, validated by the existing platform/recovery parser; platform only |
| `OTM_OKE_KUBERNETES_VERSION` | Variable; exact canonical reviewed `vMAJOR.MINOR.PATCH`; platform only |
| `OTM_POSTGRESQL_VERSION` | Variable; reviewed two-digit managed major; platform only |
| `OTM_WORKER_CLOUD_INIT` | Secret; existing bounded Bash/cloud-init renderer; syntax checked, never executed on the runner; approved apply supplies it to nodes |

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

### Historical plan-only source checkpoint — 16 November 2026

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

## Reviewed-plan apply contract

Use GitHub CLI **2.104.0 or newer**. The consumer uses an explicit job token and isolated CLI
configuration against github.com; no local-login fallback or caller-supplied URL is accepted.
`operation=apply` requires `plan_run_id` and lowercase 64-hex `reviewed_plan_sha256`. Production
also requires `staging_apply_run_id` and `staging_tests_confirmed=true`. Component is `security`
or `platform`; source/ref/environment are fixed by the protected workflow.

For each producer, authenticated GitHub metadata must identify a successful completed manual master
run of the correct environment workflow and the consumer's exact source SHA. Its selected attempt
must contain exactly one successful `Infrastructure` job. Exactly one status report in that job's
native logs supplies the expected hash and identity; a matching receipt in a mutable bucket is
insufficient. Attempt identity is rechecked after reading logs, and producer evidence is rechecked
immediately before claiming apply. Missing logs, changed attempts or unavailable evidence stop use.

The exact private `plan.tar` may contain only bounded regular `plan.tfplan` and `receipt.json` members.
The receipt must match the authenticated report and the binary SHA256 must match both the report
and operator-reviewed digest. There is no separately attested whole-tar hash. Current rendered input
hash must also match. Terraform 1.15.5 initializes the own-environment backend with readonly provider
locks, inspects the saved plan and checks action counts before invoking `apply` on that exact binary.
It does not create another plan, append variable overrides or automatically retry a failed apply.

### Production staging gate and exact parity whitelist

Production generates and reviews its **own** plan against production state/identities. It never
reuses staging's binary. Both producer runs and the apply consumer must use the same immutable
source SHA. A successful staging apply is necessary, plus explicit operator confirmation that the
referenced staging deployment passed the required tests. The boolean is manual evidence; no test
workflow, test-result signature or automated staging-acceptance proof is authenticated here.
Protected production Environment review remains separately required before credentials are minted.

For `platform`, parity hashes only these effective saved-plan variables: complete `oke`, complete
`database`, `oke_kubernetes_version`, `postgresql_version` and `caddy_ingress_enabled`. OKE
availability-domain lists are sorted after removing each tenancy-specific prefix before the last
colon, so logical domain names/count and remaining OKE sizing/settings must agree. Other values
such as target identity, VCN CIDR, Vault references, contacts, cloud-init and SMTP settings are not
part of this automatic parity check; review environment-specific security and deployment behavior
separately. For `security`, parity contains only the component name, not an assertion that secrets,
IAM identities or live behavior match.

Platform production also requires the canonical four-field staging image selection:
`image_ocid`, `kubernetes_version`, `architecture=AARCH64` and `os_major` (8 or 9). Its hash must match
production's `qualified_node_image` plan value; the cluster output after apply is checked against the
staging image hash again. A recorded image selection plus manual tests does not prove every live
compatibility or capacity property. No private image OCID is printed in the public report.

### Single attempt and failed-backend recovery

Immediately before Terraform apply, a conditional `if-none-match:*` write creates
`apply-attempt.json` beside the selected producer's `plan.tar`, recording plan hash and consuming
apply run/attempt. This is one apply attempt per producer plan across all consuming jobs/reruns.
The marker is never cleared, even after failure, cancellation or an uncertain write response.
A changed apply-run ID is not permission to consume the same plan again. Actual OCI conditional-write
and IAM enforcement remain live qualification requirements.

A failed/interrupted apply may already have changed infrastructure. Investigate the selected run,
provider effects, state and marker before generating/reviewing a fresh plan; never force-unlock or
replay automatically. If Terraform emits its native `errored.tfstate` after backend persistence
failure, the consumer best-effort preserves that bounded regular file privately beside the plan,
with conditional creation. It never edits, pushes or restores state automatically. Retention failure
must not trigger another apply; reconcile through a separately authorized manual state-repair
procedure. The marker remains in place after repair.

Success emits exactly 15 fields: `status=applied`, `environment`, `component`, `source_sha`, `run_id`,
`attempt`, `plan_run_id`, `plan_attempt`, `plan_sha256`, `inputs_sha256`, `parity_sha256`,
`node_image_sha256`, `staging_apply_run_id`, `staging_tests_confirmed` and `applied=true`.
Security has null node-image hash; staging has null staging-run reference and false test confirmation.
Failure returns exit 1 with fixed `INFRASTRUCTURE_APPLY_STOPPED`, a `recovery_state_retained` boolean
and investigation guidance, never a rollback claim or raw Terraform/provider diagnostics. Invalid
CLI choices return argparse exit 2. No live apply, staging tests or Atlas data changes are claimed.

### Local reviewed-apply validation — 16 November 2026

The final backend unit run passed 3,201 tests with 95.5811% complete-source line coverage across
201 modules. Focused plan/apply regressions passed 191 cases. Frontend units passed 650 cases
with 96.99% line coverage; the native disposable PostgreSQL/Playwright run passed all 472 cases
with zero failures, errors or skips and no persistent database use. It rebuilt the frontend from
source. Native Terraform mocks, eight replacement guards and strict Kubernetes schema checks passed.
Independent security and documentation reviews closed their findings; publication, credentials,
source/purpose and dependency checks remain part of the checkpoint evidence.

The outer verification wrapper reached its separate 600-second default before the native integration
run finished successfully. Review-driven test/documentation corrections also invalidated its tree
receipt. These native results are recorded independently; final stable-tree PR certification remains
required before shipping. Live OCI setup, IAM, conditional writes, state locking/recovery and actual
applies remain Pending in the qualification manifest. Atlas and its saved data were unchanged.
