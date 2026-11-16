# Hosted OKE workload identity and Vault reads

The source now defines scoped Vault-read IAM and explicit service-account token/CA projection.
It does not apply IAM, start pods or open networking. Hosted workloads remain at zero replicas,
the migration Job remains suspended and commands remain held. Live qualification is still required.
Laptop API-key development is [separate](laptop-oci-development.md).

## Identities and authority

| Role | Service account | Projected OCI identity | Source Vault grant |
| --- | --- | --- | --- |
| API | `otm-api` | Only for explicit OCI mode | Read application `secret-family` |
| Worker | `otm-worker` | Only for explicit OCI mode | Read application `secret-family` |
| Migration | `otm-migration` | None | None; database credential remains an explicit private runtime input |

`infra/modules/workload-vault-access` creates one policy for each reader. Each policy requires all
of the following: principal type workload, exact cluster OCID, fixed `otm-staging` or `otm-production`
namespace, exact role service account, existing hosting compartment and exact application Vault.
`any-user` in OCI's workload policy syntax does not omit these conditions or grant public access.
The policies permit retrieval only. They grant no mutation privileges or administrative authority
over tenancies, encryption resources, Kubernetes RBAC or node instance principals. Review other
pre-existing IAM grants separately.

Both platform Terraform roots now require `application_vault_ocid`. Select it from the
`application-secrets` domain of that environment's security-root `custody` handoff, never the
`database-provisioning` domain. The same platform root supplies its newly created cluster ID to
the IAM module. This avoids a dependency cycle: create security custody first, then platform/cluster
and its workload IAM. No Terraform remote-state secret lookup or secret content is involved.

Names are fixed by the module; namespace and service accounts cannot be supplied as arbitrary policy
text. The root's sensitive `workload_vault_access` output contains only deployment references.
Provider identity, compartment ownership and effective live IAM still require operator qualification.
The laptop development custody root receives none of these workload grants.

## Explicit pod projection

`provider_mode="oci"` with hosted `[oci] auth_method="oke_workload_identity"` selects projection in
API and worker templates only. Existing simulated previews receive no token volume. Both pod and
ServiceAccount automatic mounting remain disabled; the explicit projection is narrowly attached to
the consumer container. No RoleBinding, cluster-wide token Secret or sidecar controller is created.

The projection contains:

- A pod-bound service-account token at `token`, requesting 3,600 seconds validity. Audience is omitted
  to select the API server's default; this source choice still requires actual OKE audience
  acceptance, expiry and refresh tests before activation.
- `ca.crt` from the namespace's standard `kube-root-ca.crt` ConfigMap. Its existence and trust chain
  must be verified on the target cluster.

The directory mounts read-only at `/var/run/secrets/kubernetes.io/serviceaccount` without `subPath`,
so kubelet updates remain visible. Mode0440 with the existing group10001 makes the projection readable
by the nonroot application user. The region environment variable comes from the validated OCI
settings. The SDK uses the Kubernetes service host provided to the pod; no custom endpoint is added.

API and worker clients reuse one OKE signer per composition. No `~/.oci` volume, browser credential,
node authority or alternate credential fallback is introduced. Migration needs only the separate
DB role/CA and receives neither the OCI token projection nor the OCI-region environment variable.

## Networking and activation remain separate

Existing OCI pod/API NSGs define the required control-plane port edges. The later approved
[NSG-only V1 model](nsg-only-networking.md) removes the earlier NetworkPolicy object; no pod policy engine is installed.
Qualify explicit DNS, proxymux token exchange, Vault regional endpoints and database/SMTP/registry
paths in the release network design before activation. Successful NSG or schema checks alone do not
prove the projected identity can obtain a token or read Vault.

Granting read access is not enough to enable secret creation/rotation/cleanup. Those service adapters
and their narrowly scoped mutation permissions remain subsequent work. Full Vault/OCI launch
composition and database-secret delivery remain pending; held commands must not be replaced with
laptop simulator commands.

## Offline and live tests

Native Terraform mock tests compare the complete policy statement set and exact role membership;
exercise staging/production binding and invalid environment/OCID rejection; and verify each platform
root uses its own cluster and handed-off Vault. Python tests check role-only projection, mount
permissions/path, token lifetime request, absent migration credentials, NSG-only bundle and
held execution. Native Kubeconform validates all60 resources, plus a separate invalid-field rejection control, across simulated/OCI modes in both
environments plus the required invalid-field rejection control.

The [live OCI manifest](real-oci-test-manifest.md#hosted-workload-vault-identity) records actual token
refresh, IAM denials, mounting, reachability and nonroot consumption. No interactive saved-demo test
or real credentials are required for the source tests.

Official references: [OKE workload access](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm),
[Vault IAM variables/resources](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/keypolicyreference.htm)
and [Kubernetes projected service-account tokens](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#serviceaccount-token-volume-projection).

## Source validation receipt — 14 November 2026

The complete backend unit gate passed 2,801 cases with no failures/errors/skips and 95.37%
complete-source line coverage across 195 modules. All 41 focused bundle/schema cases passed.
Native Kubeconform passed all36 strict resource checks across both modes/environments plus the
invalid-field rejection control. The complete mocked Terraform gate passed 149 cases and seven
replacement guards; the new module and both platform compositions are included.

Inline-purpose, Ruff, Bandit, documentation/link, publication, credential and whitespace checks
passed. Independent documentation/security reviews completed; IAM inheritance, token audience
assumptions and stale implementation-status wording were corrected. No UI or data model changed.
Full application integration/Playwright and live OKE qualification remain separate gates; no cloud
apply, migration or saved8443 snapshot publication occurred.
