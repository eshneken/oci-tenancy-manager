# Enhanced OKE and worker bootstrap

**Implemented source; live qualification Pending.** The platform roots now compose network and
Enhanced OKE and [managed PostgreSQL](managed-postgresql.md) resources. No OCI cluster, VM,
database or application was created during these source slices. Database provisioning needs approved
private Vault references and explicit UTC windows. The application load balancer/deployment, runtime
IAM and delivery workflows remain separate work. Keep the running local Atlas instance unchanged.

For version variables, automatic image resolution and exact staging selection, use the
[platform version guide](platform-versions.md).

## Cluster and worker configuration

`infra/modules/oke` creates one `ENHANCED_CLUSTER` and one managed `VM.Standard.A1.Flex` node pool.
The Kubernetes API endpoint has a public IP, uses the API subnet and attaches both API and
deployment NSGs. Its subnet uses the internet gateway without a service-gateway route, avoiding
OCI's documented asymmetric-routing problem on public subnets. Nodes and pods attach their exact
private subnets/NSGs; the database subnet remains private. IPv6 is disabled throughout.

`OTM_ALLOWED_SOURCE_CIDRS` supplies the same approved human sources for app HTTPS, recovery-console
policy and Kubernetes TCP6443. The deployment NSG has no Terraform-managed admission rule. A later
owned workflow may add only its temporary runner `/32` on TCP6443 and must clean it up on completion,
failure and interruption. It must not modify the human rule, app/recovery variable or authorize the
whole published GitHub runner range. Static dedicated runner egress is an alternative. Neither path
is implemented/qualified yet. OCI IAM, Kubernetes RBAC and valid credentials remain required.

The platform root takes `oke_kubernetes_version` from the protected Actions variable. It injects
that into the module's `oke.kubernetes_version`; do not maintain a second nested root version.
The `oke` configuration otherwise has these fields, requiring staging qualification:

| Field | Meaning and bounds |
| --- | --- |
| `kubernetes_version` | Required exact `vMAJOR.MINOR.PATCH`; review newest GA supported in target region, then pin; never resolve floating latest during apply |
| `node_os_major` | Explicit Oracle Linux major `8` or `9`, default `8`; image OCID is derived, not entered manually |
| `availability_domains` | Required 1–3 distinct tenancy-specific AD names, checked against discovery; each placement includes all three fault domains |
| `node_count` | Integer3–9, default3; node distribution/capacity and one-node-loss behavior require live tests |
| `node_ocpus` | Integer1–8 per node, default2 |
| `node_memory_gib` | RAM8–64GiB per node, default8, constrained to at most64GiB/OCPU |
| `boot_volume_gib` | Integer50–500GiB per node, default50; OS/images only, not the managed database |
| `max_pods_per_node` | Integer1–31, default31; pod subnet must accommodate the whole pool plus one surge node and reserved addressing |
| `services_cidr` | Canonical private IPv4 `/16`–`/24`, default `10.96.0.0/16`; must not overlap VCN; independently check enterprise routes |

Regional cluster options must include the selected patch and VCN-native CNI. Node-pool options
filter exact version and ARM architecture; Compute filters A1, Oracle Linux major and available state.
The unique newest eligible image is resolved by parsed creation timestamp. Missing/malformed/ambiguous
catalogs fail closed. Production requires the whole staging-qualified selection and revalidates
eligibility instead of silently choosing a newer image. Preserve the approved saved plan. See the
[selection algorithm and provenance boundary](platform-versions.md) for the exact contract.
These capability checks do not establish GA status, Falcon compatibility, image hardening or A1
capacity. Review [supported OKE versions](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengaboutk8sversions.htm)
at qualification time; no live discovery was performed during this source checkpoint.

Node metadata hardcodes `areLegacyImdsEndpointsDisabled = "true"` at launch, following
[OCI's OKE IMDS guidance](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengconfiguringimds.htm).
There is no public node/pod address, supplied SSH key or arbitrary metadata override. Paravirtualized
attachments request encryption in transit; service-managed encryption is the initial configuration,
with no speculative customer KMS dependency. Live compute options/metadata must confirm enforcement.

Changes to images, versions or bootstrap use explicit `INSTANCE_REPLACE` cycling with one surge
node, zero unavailable, a 30-minute non-forced drain and no force delete/action. This is a rolling
replacement request, not a zero-downtime guarantee. Staging must prove work draining, capacity,
disruption budgets and new-node initialization. The cluster has `prevent_destroy`; the native
negative journey checks that replacement is blocked. Privileged direct OCI changes/configuration
removal are outside that Terraform guard. See [OCI node replacement](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/replace-worker-node-top.htm).

## Operator-owned cloud-init and Falcon

The full worker script is supplied as the per-environment **GitHub Actions secret**
`OTM_WORKER_CLOUD_INIT`, not a public repository variable/file. It is required: missing or malformed
input blocks the platform plan instead of creating uninitialized workers. The module accepts only
plain Bash starting with `#!/bin/bash` and a newline, no NULs, with encoded base64 length at most
16,384 bytes (12KiB raw UTF8). This leaves room under OCI's combined metadata limit; actual OKE-added
metadata size still needs live qualification. Do not include credentials or real installer URLs in
repository examples/tests. Public fixtures contain only harmless synthetic scripts.

The script is privileged operator code. It must retain the documented OKE bootstrap retrieval and
execution, using IMDSv2, as well as the approved private sensor installation. Review `set -euo pipefail`,
bounded TLS-verified downloads, safe temporary paths, integrity/version validation and exit status.
Avoid shell tracing and verbose download output that could expose credential-bearing URLs. A
pre-authenticated Object Storage URL is a bearer credential; keep its scope/expiry controlled and
do not publish it. The reference installer supplied privately is not copied, fetched or executed by
this implementation.

**The sensor's ARM64 support is unknown.** Before deploying application workloads, qualify the
private installer and sensor on A1 with the pinned OKE image/kernel; verify service startup,
management-console registration, health and recreation on replacement nodes. An OKE Ready node
does not prove Falcon is healthy. The supplied reference sequence starts OKE before sensor setup,
so a node may join before installation finishes. Staging acceptance must account for that interval;
do not claim this source enforces sensor-before-join. This remains a production go-live prerequisite.
The same interval affects existing workloads during replacement and scale-out, so initial staging
success does not establish continuous sensor-before-workload protection. Verify every new node;
any stronger scheduling gate or reordered bootstrap must be reviewed and qualified separately.

Assign an infrastructure owner to installer credential expiry. That owner must refresh the private
script/secret before its PAR expires, review the new candidate and test it in staging, accounting
for unplanned node recreation as well as scheduled cycling. A successful earlier install does not
make an expired download credential usable for replacement nodes. Prefer an approved immutable or
integrity-checked installer and record its lifecycle privately.

From a trusted environment already holding the secret, render a private candidate:

Use the operator/infra runner's pinned Python environment with `/bin/bash` available. This offline
helper is not invoked by the API/worker and does not require adding Bash to the minimal app image.

```sh
uv run --project backend python -m otm.worker_bootstrap_release \
  --output /absolute/private/path/worker.tfvars.json
```

The renderer bounds/validates the script and runs `/bin/bash --noprofile --norc -n` with script bytes
on stdin and Bash startup-file variables disabled. It **does not execute the installer**. Syntax
checking has a five-second limit, and errors are fixed/non-disclosing. Valid input exclusively creates
a new owner-only `0600` JSON file; existing files/symlinks are refused. Its receipt contains only a
SHA256 fingerprint, not the script or download URL. Syntax/fingerprint validation does not prove the
script's safety, bootstrap semantics, downloaded content or runtime success.

For the future protected-environment infrastructure workflow, bind the secret as data:

```yaml
# Release-job fragment, not a deployed workflow. Never expose this to PR/fork jobs.
env:
  OTM_WORKER_CLOUD_INIT: ${{ secrets.OTM_WORKER_CLOUD_INIT }}
```

Pass `worker.tfvars.json` alongside private target and network inputs to the reviewed plan. Never
interpolate the secret directly into shell commands. Never upload rendered files, raw plans/state,
Terraform JSON/debug output, cloud-init scripts or node logs to public artifacts. Required mock CI
uses synthetic scripts and needs no environment secrets.

**Sensitive is redaction, not encryption.** Terraform puts the base64 script into node metadata
`user_data`, and it is recoverable in Terraform state and saved plans. Node metadata/root cloud-init
files can also contain it. Restrict state-bucket versions/backups, plan access, node access and logs
accordingly. Expired URLs can remain in retained state; revocation/expiry must invalidate the bearer
credential. Keep `TF_LOG` and shell tracing disabled in secret-bearing jobs. Do not claim GitHub
secret masking or base64 removes this exposure. Future authenticated installer retrieval can reduce
embedded credential exposure after its identity/custody design is qualified.

Update each environment's secret from an approved private file when ready:

```sh
gh secret set OTM_WORKER_CLOUD_INIT --env staging \
  --repo eshneken/oci-tenancy-manager < /absolute/private/path/approved-worker-init.sh
```

Repeat deliberately for production with its own approved secret. Updating a secret alone does not
change existing nodes. Render a new private candidate, review the plan and replace/cycle nodes through
the infrastructure runbook; do not attempt to mutate a launched VM's immutable `user_data`.

## Access and qualification

### Prior OKE/cloud-init source verification — 13 November 2026

Before the image-resolution follow-up, seven native Terraform suites passed: 19 bootstrap, 23 network, 16 OKE and 10 platform-root
cases. Both state-bucket and cluster replacement negative journeys reject destruction for the
expected lifecycle reason. Backend unit-only validation passes 2,446 tests without skips and
95.14% complete-source line coverage; the worker-input renderer has 100% line/branch coverage.
Lint, inline-purpose, publication, credential and Bandit checks pass. Independent security review
approved only the two exact B404/B603 exceptions for the fixed nonexecuting Bash parser; no global
scanner rule was disabled. Documentation and independent design reviews retain the live gaps above.
Complete required PostgreSQL/browser/frontend and other milestone gates still precede the combined
milestone PR. No saved Atlas snapshot, real script, OCI resource or hosted deployment was changed.

After approved staging provisioning and OCI/Kubernetes grants, Lens and kubectl can reach the public
API directly from an approved source. Generate an environment-specific kubeconfig using OCI's
supported CLI flow; retain certificate verification and short-lived authentication. The local Atlas
recovery administrator is not an OCI/Kubernetes administrator. No Bastion tunnel or private runner
is required for the approved public endpoint design. Application builds remain standard hosted CI;
production deployment authority is limited to reviewed environment-bound jobs.

Use the [traffic matrix](oke-network-traffic.md), [network/state procedures](network-foundation.md)
and [pending OKE/sensor qualification](real-oci-test-manifest.md#enhanced-oke-and-worker-bootstrap).
Runtime IAM, application/RBAC manifests, load-balancer health/backend rules, hosted schedules,
deployment admission cleanup and actual provider/service behavior remain separate qualification.
