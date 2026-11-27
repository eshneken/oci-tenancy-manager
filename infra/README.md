# Terraform infrastructure

The implementation supplies the **state-bucket bootstrap, network, Enhanced OKE, managed PostgreSQL and Vault custody source**. Staging
and production use separate roots and separate tenancies. Optional [held Caddy/NLB source](../docs/how-to/caddy-ingress.md) and scoped workload Vault-read IAM are implemented. Held [plan/review/apply workflow/federation source](../docs/how-to/infrastructure-plans.md) is implemented; activation, live apply qualification and application deployment/promotion remain separate. A reviewed hosted platform apply can create managed ARM nodes with launch metadata that explicitly disables IMDSv1. The held hosted source is covered by local mock checks.

| Directory | Responsibility |
| --- | --- |
| `environments/development/bootstrap/` | Development compartment, bucket, GitHub delivery trust, shared non-production domain settings and identity policy, and optional laptop enrollment IAM |
| `environments/development/infrastructure/` | Single post-bootstrap root and remote state. Vault and key, plus partial Atlas SSO source held for full ownership review. |
| `modules/state-bootstrap/` | One private, versioned Standard Object Storage bucket, with a namespace check and replacement/destruction guard |
| `environments/staging/bootstrap/` | Staging compartment and state bucket. Uses shared non-production settings and holds delivery activation pending client-bound federation. |
| `environments/production/bootstrap/` | Production compartment, state bucket, GitHub delivery trust, and independent domain settings and identity policy |
| `environments/staging/infrastructure/` | One staging root/state for Vault, generated DB credential, network, OKE, PostgreSQL, IAM and SSO. Live use held. |
| `environments/production/infrastructure/` | One production root/state with independent delivery and same-source staging acceptance. Live use held. |
| `modules/oci-delivery-foundation/` | OCI token exchange, exact GitHub trust, IAM and shared domain setting ownership |
| `modules/github-environment/` | GitHub reviewer/deployment controls and protected inputs |
| `modules/secret-foundation/` | Two Vaults and software-protected AES-256 keys in the existing hosting compartment and exact Vault-ID reader policy |
| `modules/postgresql/` | Private two-node managed PostgreSQL, pinned Vault provisioning references, backup/PITR intent and replacement guard |
| `modules/oke/` | Enhanced cluster, public source-restricted API, private ARM pool and sensitive operator cloud-init |
| `modules/networking/` | VCN, five disjoint regional subnets, gateways/routes, closed security lists and service NSGs |

The environment label is a guard against a mislabeled input, **not authorization or proof that a
principal/compartment belongs to the intended tenancy**. The namespace read checks the configured
tenancy's namespace; independent operator/IAM checks must still establish actual identity and scope.
Use distinct approved principals, compartments and private input/state files for each environment.

## Local checks without OCI access

Install Terraform **1.15.5**, then from the repository root run:

```sh
bash scripts/check_infrastructure.sh
```

The script checks formatting, initializes with `-backend=false -lockfile=readonly`, validates all
fifteen configurations and runs native Terraform provider mocks. It needs network access to install
the locked provider, but no OCI credentials and no OCI API calls. The suites cover all modules and
both environments' bootstrap/platform roots. Negative journeys also verify cluster and state-bucket replacement guards. A separate negative journey performs a mocked apply followed by a blocked replacement
plan; the script requires that precise lifecycle rejection, rather than accepting an arbitrary failure.
No live state backend is initialized. The required Documentation and contracts CI lane runs this
same command, alongside the existing required application/security lanes.

Terraform's provider dependency is pinned to **oracle/oci 9.13.0**. Commit the generated lockfiles;
they include verified package checksums for Linux AMD64/ARM64 and macOS ARM64. Weekly Dependabot
proposals group provider updates across these directories. Review/regenerate locks and rerun the
checks before accepting an update. Terraform CLI upgrades must also update each `required_version`
and the CI installer together; provider updates do not upgrade the CLI automatically.

## Inputs and outputs

Each bootstrap root accepts these inputs; see its synthetic `terraform.tfvars.example`.
Actual deployment values belong in a separate private file, never the example or repository.

| Input | Meaning and bounds |
| --- | --- |
| `target.environment` | Exactly the root's fixed `staging` or `production` label |
| `target.tenancy_ocid` | Intended tenancy OCID; syntax validation only |
| `hosting_compartment_ocid` | Existing single hosting compartment, required from protected `OTM_HOSTING_COMPARTMENT_OCID`; no default or child compartments |
| `target.object_storage_namespace` | Exact expected namespace; checked against the tenancy namespace read |
| `target.region` | Explicit OCI region, default `us-ashburn-1`; use the approved regional target |
| `oci_auth` | Explicit `SecurityToken` (default), `ResourcePrincipal` or `InstancePrincipal`; API-key fallback is rejected |
| `oci_profile` | Nonempty profile name, at most 128 characters; used only for SecurityToken |

The shared module's `name_prefix` defaults to `otm` (3–24 lowercase safe characters); the environment
roots deliberately do not expose a rename knob for established state buckets. Bucket names are
`otm-staging-tfstate` and `otm-production-tfstate`, each in its own namespace. The provider supplies
the service's default encryption; customer-managed encryption requirements must be settled before
live qualification. No credential is accepted as a Terraform variable.

Both outputs are marked sensitive to avoid printing private coordinates in ordinary output;
this does not encrypt Terraform state. `environment_binding` records the supplied environment,
tenancy and compartment. `state_backend` supplies the bucket, namespace, region and remote key.
Hosted roots use `infrastructure/<environment>/terraform.tfstate`; development retains
`custody/development/terraform.tfstate`. Bootstrap uses private local state. Reconcile any occupied
legacy hosted `security/` or `platform/` key through a separately reviewed migration before rollout.

## Network composition

The hosted infrastructure roots accept the same target/auth inputs, plus required `vcn_cidr` (canonical private
IPv4 `/16`–`/20`) and `app_ingress_allowed_cidrs` (1–64 canonical IPv4 networks, <=4096 serialized
bytes). There is no default allowlist. Supply it through the private renderer from
`OTM_ALLOWED_SOURCE_CIDRS`; IPv6, host bits and unrestricted unions fail closed. Edge admits human TCP443; the API admits the same human sources on TCP6443. Private database access is scoped to the pod NSG. OKE attaches endpoint/node/pod NSGs and configures the explicit native-CNI matrix; live connectivity is not yet qualified. See the
[network reference and operator procedure](../docs/how-to/network-foundation.md) for subnet allocation,
closed defaults, exact tests, private backend initialization and remaining application-service and job-admission wiring.
For platform roots, `hosting_compartment_ocid` identifies the same existing hosting compartment for bootstrap, security
and platform resources in that environment. No child compartments are created.

## State safety

- Keep local bootstrap state, plans, backups and inputs outside the checkout, with an operator-only
  directory and `umask 077`. Separate staging and production paths; verify ownership and permissions
  even when reusing an existing directory. Never upload these files as CI artifacts.
- The bucket sets `NoPublicAccess`, `Enabled` versioning and `Standard` storage explicitly. Its
  `prevent_destroy` guard blocks Terraform replacement/destruction while the resource declaration
  remains. It does not prevent a privileged OCI operator, configuration removal or direct deletion.
- Do not add retention locks to live state or lock objects: they can prevent legitimate updates and
  lock cleanup. IAM restrictions, versioning, controlled access and a restore drill provide protection.
- Preserve the original bootstrap state after creation. Remote-state migration, concurrent locking,
  version recovery and the live principal's permissions remain separate qualification work.

See the [bootstrap operating procedure](../docs/how-to/terraform-state-bootstrap.md),
[environment/promotion design](../docs/engineering-design/24-environments-and-promotion.md),
[hosted administration runbooks](../docs/how-to/hosted-administration.md) and
[live qualification manifest](../docs/how-to/real-oci-test-manifest.md#terraform-state-bootstrap).

## OKE and private worker initialization

Both hosted infrastructure roots require explicit `oke` OS/placement and a sensitive `worker_cloud_init` string,
with no script default. Render it from the per-environment `OTM_WORKER_CLOUD_INIT` GitHub Actions
secret using `python -m otm.worker_bootstrap_release`; do not put the private script/PAR URLs in source.
Normal plans redact the base64 `user_data`, but saved state/plans and node metadata retain it.
Review the [complete OKE inputs/bootstrap procedure](../docs/how-to/oke-foundation.md),
[traffic matrix](../docs/how-to/oke-network-traffic.md) and pending ARM64 Falcon checks before live use.

## Protected platform version inputs

`OTM_OKE_KUBERNETES_VERSION` and `OTM_POSTGRESQL_VERSION` are staging/production Actions variables.
The deployment plan sets both environments to OKE `v1.37.1` and PostgreSQL `18`.
The [version renderer and selection guide](../docs/how-to/platform-versions.md) supply the required
flat `oke_kubernetes_version` and `postgresql_version` inputs through private tfvars. OKE derives its
unique newest compatible image from exact version/ARM options and A1/OS image metadata. Production
requires the whole trusted staging selection (`qualified_node_image`); it never silently advances
that image during promotion. Provider lookups still require live qualification. The major input now reaches the managed database resource; no live DB was provisioned or upgraded here.
The offline `python -m otm.image_handoff` command converts the accepted staging cluster output into
production's private `qualified_node_image` tfvars file. See the version guide's operator handoff;
it validates the binding without claiming acceptance/provenance or implementing automated delivery.

## Managed PostgreSQL

Both hosted infrastructure roots now include the [managed database module and operator guide](../docs/how-to/managed-postgresql.md). The hosted roots generate the provisioning credential inside Vault and supply its OCID and initial version to PostgreSQL. Backup and maintenance windows remain explicit. Runtime database role/secret provisioning and live restore/upgrade qualification follow separately. Scoped [workload Vault-read IAM](../docs/how-to/oke-workload-identity.md) and optional [held Caddy ingress](../docs/how-to/caddy-ingress.md) source are implemented but require deployment qualification.

## Vault custody foundation

The [Vault foundation](../docs/how-to/vault-foundation.md) composes custody and service-side PostgreSQL password generation in each hosted root. Live readiness and effective IAM remain unqualified. Exact API/worker [workload Vault-read grants](../docs/how-to/oke-workload-identity.md) exist as source. Federation grants, runtime database role provisioning and live activation remain separate work. The [hosted organization setup](../docs/how-to/hosted-startup.md#initial-organization-mapping-and-import) documents the additional [organization API table privileges](postgresql/hosted-organization-api-grants.sql).

The required [hosting compartment Actions input](../docs/how-to/hosting-compartment.md) is rendered privately from `OTM_HOSTING_COMPARTMENT_OCID`; no live target value is configured until the real tenancy is available.

The [Kubernetes workload bundle](../docs/how-to/kubernetes-workloads.md) is separate from
Terraform. It keeps workloads disabled until the existing [hosted startup foundation](../docs/how-to/hosted-startup.md)
is composed with Vault and OCI and qualified in staging.


## Laptop development infrastructure

Terraform ownership of all OTM-created infrastructure is the target. Development bootstrap currently references the existing GitHub exchange client by immutable GUID. The [development ownership design](../docs/engineering-design/26-administrator-sso.md#development-terraform-ownership)
assigns the compartment, state bucket, GitHub authentication and trust, scoped IAM and shared
domain setting to the local operator bootstrap. The upstream corporate identity federation is
an external dependency.

The [development runbook](../docs/how-to/laptop-oci-development.md#development-infrastructure-through-github-actions)
covers the single post-bootstrap root and state for the Vault, software key, Atlas client,
assignment group, app grants, policies and rules. Preserve existing groups and app grants when
qualifying their Terraform adoption. Atlas manages individual membership and database grants.

Bootstrap source declares the compartment, bucket, GitHub exchange client/trust, scoped IAM
and shared non-production domain settings. The optional `local_app_iam` adds laptop enrollment IAM.
Development bootstrap owns the shared non-production
[`otm-github-identity` policy](../docs/how-to/terraform-state-bootstrap.md#domain-owned-github-identity-policy);
its development and staging statements keep separate workflow and group bindings.
The optional [named development subject](../docs/how-to/terraform-state-bootstrap.md#named-development-workflow-subject)
also declares ownership of the exact workflow dynamic group and Application Administrator grant.
The environment root owns the Vault and key and declares the SSO group, client, app grant,
policies and rules. A [protected native group adoption plan](../docs/how-to/laptop-oci-development.md#development-group-adoption-proof)
verified the existing group's exact-name and native-OCID read and no changes to Vault/key.
Fresh-group reads remain unqualified. The protected workflow then completed
[in-place activation and assignment](../docs/how-to/laptop-oci-development.md#development-atlas-browser-client-activation).
The replacement passed the 8445 native-session sign-in test. The protected follow-up with the
named workflow subject proposed zero resource actions.

## Hosted workload Vault reads

`modules/workload-vault-access/` supplies read-only policies for exact API/worker workload identities, bound to each environment cluster/namespace/service account/application Vault. Each composed hosted root derives the application Vault OCID from its own custody module. No node/migration grants or secret writes are added. [Handoff and qualification](../docs/how-to/oke-workload-identity.md) remain distinct from a live apply.


## Hosted administrator enrollment

The staging and production platform roots do not grant administrator enrollment permissions.
The hosted milestone must qualify the exact environment's API workload and demonstrate denial
of unrelated identity-domain writes before adding the policy.

## V1 NSG-only network boundary

The owner approved [NSGs only](../docs/how-to/nsg-only-networking.md), without Calico or Kubernetes NetworkPolicy objects. Optional platform `smtp_egress={cidrs=[...],port=587}` adds bounded relay-specific pod-NSG rules; null adds none. Existing CNI/Oracle service allowances remain additive. Live network unions, metadata/IAM and ingress/SMTP qualification remain pending.

## Corporate sign-in application registration

The provider-free [application registration module](modules/application-registration/main.tf)
defines the OCI integrated application and app-assignment group names and descriptions for
development, staging, and production. Use its outputs when adopting the application and group
resources. It requires no live
credentials to test. Live adoption remains gated on preserving the registered client ID and
excluding the OAuth secret from Terraform state. See the [Atlas pilot reference](../docs/reference/corporate-sso.md#terraform-follow-through).

## Held environment plan/review/apply workflows

The [common Terraform layout](../docs/engineering-design/24-environments-and-promotion.md#terraform-layout-for-each-environment)
uses operator bootstrap for delivery foundation and one composed infrastructure root/state per
environment. Staging and production have fixed composed `infrastructure` workflows. Keep both
held until separate authorization and live qualification.
They use separate protected-environment OAuth client secrets to exchange a GitHub JWT for an
ephemeral signing session. Provider and backend explicitly use file-backed `ResourcePrincipal`;
operator defaults remain unchanged. Default operation is plan; apply additionally requires the
separate default-false `OTM_INFRASTRUCTURE_APPLY_ENABLED` flag and an exact reviewed producer plan.
There is no destroy operation. Environment approval and both enable flags are required before apply.

Secret-bearing plans are stored only under `infrastructure-plans/` in that environment's existing
private versioned state bucket; no public GitHub plan artifact or raw plan output is produced.
See the [reference](../docs/reference/infrastructure-plans.md) and
[operator procedure](../docs/how-to/infrastructure-plans.md). Backend locking, actual trust/IAM,
private storage, job cleanup and actual apply remain live qualification. The apply consumer
authenticates the exact successful GitHub producer run/attempt/job logs, matches private inputs and
reviewed binary hash, and conditionally consumes the producer plan once. Production requires its own
plan, same-source successful staging apply, manual test confirmation, explicit shared-field parity,
qualified ARM image and production approval. Failed/interrupted apply requires investigation and a
fresh plan; native failed-backend state is best-effort retained privately for manual repair only.
The permanent attempt marker is never removed. No live OCI or saved Atlas change is claimed.
