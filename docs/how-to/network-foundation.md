# Private network foundation

**Implemented source; live OCI qualification Pending.** This guide covers the network definitions. The [OKE follow-up](oke-foundation.md) now adds cluster/node-pool source to both platform roots; a live platform apply would create worker VMs and the [managed PostgreSQL system](managed-postgresql.md). The application load balancer and application deployment remain separate work. No live resources were created during development. Do not infer working connectivity from mocks; the saved laptop app is unchanged.

Use the [hosting compartment renderer](hosting-compartment.md) to create private `hosting.tfvars.json`
from `OTM_HOSTING_COMPARTMENT_OCID` before planning. All roots use that existing compartment; no child
compartments are created. Pass the file alongside the other reviewed inputs.

## Prior network-only source verification — 13 November 2026

Before the OKE follow-up, six native Terraform suites passed: 19 bootstrap cases, 20 network-module cases and 10
platform-root cases, plus the expected state-bucket replacement rejection. Backend unit-only
qualification passes 2,433 tests with no skips and 95.13% complete-source line coverage; the new
network renderer has 100% line/branch coverage. Documentation links, publication/credential checks,
inline-purpose checks, formatting and lint pass. Independent security and documentation reviews
report no material findings. These are source/offline results, not hosted or live-OCI evidence.
No UI/DB workflow changed; complete PostgreSQL/browser and other required milestone gates must
still pass before opening the combined milestone PR. No saved Atlas snapshot was republished.

## Layout and boundaries

`infra/modules/networking` is composed by the fixed staging/production `platform` roots. Each
uses its own hosting tenancy/compartment, provider identity and private OCI backend configuration.
Bootstrap's state remains separate and local; never migrate it onto the platform key.

| Subnet | Relative allocation in an example `/16` | Intended attachment and routing |
| --- | --- | --- |
| Edge | `.0.0/24` | Public HTTPS load balancer only; internet-gateway route |
| API | `.1.0/24` | Restricted public OKE API; internet-gateway route, human TCP6443 admission |
| Database | `.2.0/24` | Private PostgreSQL; service-gateway route, no NAT/internet default |
| Nodes | `.4.0/22` | Private managed nodes; NAT plus service-gateway routes |
| Pods | `.16.0/20` | Private VCN-native workload pods; NAT plus service-gateway routes |

The VCN input accepts canonical RFC1918 IPv4 `/16`–`/20` networks with no default; subnet sizes
scale with that prefix, remaining disjoint. Live deployment must check enterprise/peered routes,
pod-IP limits and expansion needs before accepting an address plan. Subnets are regional, IPv6 is
disabled, and all but Edge/API prohibit public IPs and internet ingress.

The module manages an empty VCN default security list and explicitly attaches a separate empty
security list to every subnet. This prevents additive default SSH/egress rules from bypassing NSGs.
Provider 9.13.0 represents empty rules by **omitting the rule blocks**; its security-list requests
initialize rule arrays empty. Live readback must still verify both lists. Never add a broad security
list rule to compensate for missing service NSG wiring.

The Edge NSG permits stateful TCP443 only from `app_ingress_allowed_cidrs`. The database NSG
permits TCP5432 only from the pod NSG, with matching pod egress. OCI-managed service requirements,
actual source VNIC/NSG attachments and PostgreSQL TLS remain live qualification work.
The OKE follow-up now installs the [explicit CNI/control/DNS/egress matrix](oke-network-traffic.md)
and attaches API/deployment, node and pod NSGs to the corresponding OKE VNICs. Deployment admission
remains empty until the owned CI workflow provides its temporary `/32`; no full GitHub range is
allowed. Edge/backend/health rules remain pending the actual app load-balancer port contract.
NAT/service routes do not independently grant traffic. All effectiveness requires live qualification.

The owner selected a restricted public Kubernetes API for direct Lens/kubectl and hosted-runner
access. This supersedes the earlier private API/private-runner requirement. Only human-approved
TCP6443 is configured now; job-specific deployment admission and cleanup are separate pending work.

## Offline validation and shared-input rendering

From the repository root, run:

```sh
bash scripts/check_infrastructure.sh
uv run --project backend pytest backend/tests/test_network_release.py -q
```

All Terraform test providers are mocked. The checks initialize with `-backend=false`, never
authenticate to OCI and never open a live state backend. Provider downloads still require network
access. Tests inspect rendered resources/routing/NSG bindings and reject invalid union/scope inputs;
they do not emulate OCI authorization or service behavior.

The protected environment variable **`OTM_ALLOWED_SOURCE_CIDRS`** is the sole release input for
both app ingress and recovery-console configuration. The network renderer reuses the existing
strict parser, then rejects IPv6 because the first network topology has no IPv6 support. It rejects
the entire candidate rather than dropping unsupported entries. Multiple ranges and individual
IPv4 hosts (`/32`) are supported; no operational defaults are stored in source.

With that variable already supplied through a trusted private operator/job environment:

```sh
uv run --project backend python -m otm.network_release \
  --output /absolute/private/path/network.tfvars.json
```

This exclusively creates an owner-only `0600` JSON file containing only
`app_ingress_allowed_cidrs`. Existing files and symlinks are refused. It prints only source count
and the same effective-union fingerprint used by the recovery-console release; fixed failures
contain no ranges or private paths. Do not use shell evaluation to load untrusted values. This
command does not initialize Terraform, request credentials, deploy settings or change child policies.

## First live platform initialization — operator procedure

The platform roots now include Enhanced OKE and worker VMs. Review the
[OKE/bootstrap guide](oke-foundation.md) before live planning; this is no longer a network-only plan.

Live execution requires explicit approval and a qualified operator identity. This document is
preparation, not authorization. Use staging first:

1. Complete [state-bucket bootstrap](terraform-state-bootstrap.md). Independently verify the actual
   tenancy/principal, existing hosting compartment ancestry, region and namespace. The hosting
   compartment must match the bootstrap/security hosting compartment within this environment.
   Namespace agreement and labels are not IAM proof.
2. With `umask 077`, create a private operator-only directory outside the checkout for this
   environment's platform metadata, inputs and plans. Copy the selected platform root's synthetic
   `terraform.tfvars.example` there and replace target/VCN/profile and OKE OS/placement fields with approved inputs.
   Supply approved environment-owned database administrator Vault references and explicit UTC backup/maintenance windows using the [database guide](managed-postgresql.md).
   Render the protected OKE/PostgreSQL version variables with the [version guide](platform-versions.md)
   into private `versions.tfvars.json`; production also needs its trusted staging image record.
   The source example deliberately contains no app allowlist default; render that into a separate
   private JSON file using the command above. Keep this list and all rendered application consumers
   aligned through one reviewed source revision. No variable edit automatically changes either control. Render the required worker cloud-init secret into private `worker.tfvars.json` using the OKE/bootstrap guide; never use the synthetic fixture as a real bootstrap.
3. Create a **private** `staging.tfbackend` with actual bucket/namespace/region and an explicitly
   selected short-lived SecurityToken profile. The platform root fixes
   `key = "platform/staging/terraform.tfstate"` and `auth = "SecurityToken"`; do not override its
   state key or point it at bootstrap/production state. Production fixes its own
   `platform/production/terraform.tfstate`, in its own bucket/namespace. Use the default Terraform
   workspace only; these environments are different roots, not Terraform workspace names.
4. Select private metadata paths and initialize the **staging platform root**, not bootstrap:

   ```sh
   umask 077
   export OTM_PLATFORM_DIR=/absolute/private/path/otm-staging-platform
   export TF_DATA_DIR="$OTM_PLATFORM_DIR/provider-data"
   terraform -chdir=infra/environments/staging/platform init \
     -input=false -lockfile=readonly \
     -backend-config="$OTM_PLATFORM_DIR/staging.tfbackend"
   terraform -chdir=infra/environments/staging/platform plan \
     -input=false -var-file="$OTM_PLATFORM_DIR/target.tfvars" \
  -var-file="$OTM_PLATFORM_DIR/hosting.tfvars.json" \
     -var-file="$OTM_PLATFORM_DIR/network.tfvars.json" \
     -var-file="$OTM_PLATFORM_DIR/worker.tfvars.json" \
     -var-file="$OTM_PLATFORM_DIR/versions.tfvars.json" \
     -out="$OTM_PLATFORM_DIR/platform.tfplan"
   ```

5. Review the exact saved plan privately. Do not publish raw plan/state/variables or run them in
   public CI logs. Expect network, Enhanced cluster and private ARM node-pool changes, closed lists and exact human HTTPS/API sources. The API endpoint is public but source-restricted. Managed PostgreSQL creation is included, with the exact database subnet/NSG. No app load balancer is included. Treat worker cloud-init as a secret-bearing root script. Do not apply if scope, state key, pins, address plan or approved input fingerprints differ.
6. After approval, apply the exact reviewed plan through the owned operator process. Read back
   subnet flags, route destinations and both empty lists. Prove remote locking with competing
   writers, version recovery and interruption recovery before enabling automated infra delivery.
   Keep the independent bootstrap state protected; no bootstrap-state migration is included here.
7. Qualify OKE endpoint/NSG/IMDS/placement and ARM sensor health using the OKE guide. Qualify full app ingress denial/allow rules after the next slice attaches the load balancer; the managed database source now attaches its exact subnet/NSG. Test UI/API from allowed and unapproved sources, forwarded headers,
   alternate public paths, IPv6, additive/controller rules, private database source identity and
   lockout-safe allowlist changes. Do not mark a non-listening endpoint as proof of correct filtering.

Backend configuration and provider authentication are separate consumers; both require explicit
approved credentials. Future federation must not silently fall back to a different principal.
Do not override the backend's fixed key/auth using an arbitrary user-supplied file in automation;
delivery validation must inspect that private input before credentials are obtained. Native mocks
do not verify backend settings, locking or IAM. Follow the [OCI backend documentation](https://developer.hashicorp.com/terraform/language/backend/oci)
and retain live evidence privately in the [test manifest](real-oci-test-manifest.md#network-foundation).
