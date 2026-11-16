# Kubernetes workload bundle

This first source slice renders **disabled review manifests**, not a runnable hosted application.
The existing image has laptop-only API/worker startup. Hosted API, worker, readiness and migration
composition must be implemented and qualified before activation. No Kubernetes or OCI resources
are created by rendering or validation, and the saved local application is unaffected.

## What the bundle contains

`backend/src/otm/kubernetes_release.py` generates standard Kubernetes JSON (`v1/List`). JSON is
accepted by Kubernetes tooling; there is no Helm dependency, custom controller or separate template
language. The renderer reuses the existing strict application/release settings validator.

| Resource | Purpose |
| --- | --- |
| One immutable ConfigMap | Exact nonsecret application.toml, named with its content hash |
| Three ServiceAccounts | API, worker and migration identities, with token automount disabled and no RBAC grants |
| API Deployment | Zero replicas; rolling-update contract, port 8080 and process/readiness probe contracts |
| Worker Deployment | Zero replicas; Recreate avoids overlapping old/new workers during rollout |
| Migration Job | Suspended, one completion/parallelism, no automatic retry, ten-minute deadline |
| API ClusterIP Service | Internal-only port 8080; no public load balancer or ingress |
| Network boundary | OCI NSGs only in V1; no NetworkPolicy or pod policy engine |

The base eight resources are namespaced: `otm-staging` or `otm-production`, selected independently of the
submitted settings. The environments still live in separate OCI tenancies/clusters. The platform
must create the namespaces and enforce Restricted Pod Security admission; the bundle grants no
cluster-wide privileges and does not claim that namespace admission enforcement already exists.

The base API/worker/migration containers explicitly override the image command with a fixed
`OTM_HOSTED_RUNTIME_NOT_QUALIFIED` failure. This is a temporary source-stage hold, not an activation
flag or new application subsystem. Even manually scaling a Deployment or unsuspending the Job cannot
invoke the image's local default. Remove the hold only as part of implementing qualified hosted
startup. Do not apply this preview to an operating environment as an application release.

## Image, settings and credentials

Supply one registry-qualified `repository@sha256:<64 lowercase hex>` reference. Mutable tags are
rejected. All three roles use that exact image. Registry credentials, image provenance, tested ARM64
platform identity, production acceptance and live pull permissions still require delivery integration;
digest syntax alone proves none of them.

Settings must pass the existing staging/production release gate: matching environment, no local
server settings, required recovery-network policy and existing testing-email/SMTP rules. ConfigMaps
contain no credential values; unknown settings are rejected. Rendered output still contains private
operational settings such as approved networks and contacts: keep it local/private and out of public
CI artifacts. The CLI prints only a bundle hash and held status. It creates a new mode0600 file and
refuses existing outputs or output symlinks.

The settings hash names an immutable ConfigMap and appears on every consuming pod template, together
with an image/settings/environment release hash. A settings change therefore selects a new mount and
pod revision while retaining the image. Existing pods retain their old immutable settings. Do not
remove old ConfigMaps until old consumers/jobs have drained and rollback retention is satisfied.
The migration Job name is release-specific; repeated renders of the same candidate have the same
identity. Reapplying a Job is not permission to rerun a failed or already completed migration.

| Role | Required Secret reference | Key |
| --- | --- | --- |
| API | otm-api-database | url |
| Worker | otm-worker-database | url |
| Migration | otm-migration-database | url |

Only that role's credential reference enters each pod. No Secret object/value or migration credential
is copied into API/worker manifests. The `otm-database-ca` ConfigMap must supply `ca.crt`; mounts are
read-only at `/etc/otm-ca`. `OTM_DATABASE_CA_FILE` and `OTM_DATABASE_URL` are inputs to the future hosted
composition, which must enforce verify-full TLS and qualified least-privilege DB roles. Naming a
Secret does not create a DB login, connect Vault, encrypt Kubernetes storage or prove TLS enforcement.
Full Vault service composition and registry pull credentials remain pending.
[Explicit OCI workload token projection and read IAM](oke-workload-identity.md) are implemented as source; live qualification and network allows remain pending. No broad Secret-read RBAC or automatic token/fallback credentials are introduced.

## Pod security and initial sizing

Containers run as UID/GID 10001, non-root, with RuntimeDefault seccomp, all capabilities dropped,
privilege escalation disabled and a read-only root filesystem. Only the pod-local `/run/otm` temporary directory is writable
through a64Mi emptyDir, with TMPDIR and fsGroup10001 explicitly set. No host networking, privileged pod, hostPath or Docker socket is requested.
Scheduling selects Linux ARM64 nodes. The workload bundle never launches or changes a VM or IMDS.

| Role | CPU request / limit | Memory request / limit | Termination grace |
| --- | --- | --- | --- |
| API | 250m /1500m | 512Mi /1Gi | 120seconds |
| Worker | 500m /2CPUs | 512Mi /1Gi | 300seconds |
| Migration | 250m /1CPU | 256Mi /512Mi | 120seconds |

These are starting pod budgets, not measured capacity guarantees. Staging must mirror production: both target two API replicas and two worker pods with one
execution slot each. Their node/database sizing, software versions, pod budgets and security/rollout
controls match; qualify node-loss/surge headroom and both workers together in staging. The preview
Deployment annotations record target-replicas=2 for each role; actual replicas remain zero. The source bundle remains at zero. Authentication memory, database pools, worker
concurrency and total node allocatable resources must be measured together before activation.

`/health/live` is process-only. The [implemented startup mechanics](hosted-startup.md) provide
`/health/ready` with a bounded DB/schema/role check; deployed composition still needs qualification. Liveness must not
restart healthy processes merely because OCI or the database is temporarily unavailable. Worker
process exit is handled by Kubernetes; no fake import-only or database-only heartbeat probe claims
job progress. Worker stall monitoring and actual graceful Procrastinate drain must be qualified.
Termination grace alone does not prove safe shutdown, external-effect reconciliation or handoff.

## Render and validate locally

This is source inspection; no OCI tenancy or kubeconfig is needed. From the repository root, prepare
a private reviewed staging settings candidate using the existing release renderer. Set
`OTM_ALLOWED_SOURCE_CIDRS` privately and `OTM_IMAGE_DIGEST` to the selected digest-qualified image
reference; neither variable is supplied by an untrusted pull request.

```sh
umask 077
mkdir -p .local-dev/kubernetes
uv run --project backend otm-validate-release \
  --config backend/config/staging.application.toml \
  --expected-environment staging --release-kind application \
  --render-recovery-console-from-env .local-dev/kubernetes/staging.application.toml
uv run --project backend python -m otm.kubernetes_release \
  --config .local-dev/kubernetes/staging.application.toml \
  --expected-environment staging --image "$OTM_IMAGE_DIGEST" \
  --output .local-dev/kubernetes/staging.bundle.json
```

Inspect that private file in an editor. Do not publish its content or run kubectl apply. Rendering
fails if the output already exists; choose a new path for another candidate. Production rendering
uses its own reviewed production settings and independent `--expected-environment production`.

Run the synthetic automated checks:

```sh
uv run --project backend pytest -q backend/tests/test_kubernetes_release.py backend/tests/test_kubernetes_schema_check.py
uv run --project backend python scripts/check_kubernetes_bundle.py
```

The second command uses a uniquely owned disposable Docker container, not a new app instance or
Kubernetes cluster. It validates60 synthetic resources across base simulated/base OCI/optional OCI+Caddy candidates in both environments against Kubernetes1.37.0 strict schemas and
requires rejection of one deliberately invalid Deployment field. Missing/skipped schemas, tool/network
failure and unexpected results fail the check. It accesses the public registry/schema service, with
normal TLS verification; it never receives operator settings or cloud credentials. Containers and
synthetic files are removed after each run. A schema pass is not API-server admission, CNI behavior,
OKE support for that patch or successful deployment.

The validator image version/digest lives in `tools/kubeconform/Dockerfile`, separately from the app
runtime and covered by the grouped weekly Dependabot image-update proposals. The existing required
Checkpoint documentation/contracts job runs this native schema gate on every build. Python unit
coverage includes the renderer; script regressions verify failure and negative-control enforcement.

## Before activation

Qualify the [implemented startup mechanics](hosted-startup.md), managed PostgreSQL TLS/role separation and migrations,
Vault/identity/registry integration, permitted DNS/DB/OCI/SMTP/ingress network paths and Pod Security
admission. Add API availability protection for the qualified active topology. Then rehearse migration
ownership, worker drain, identical two-API/two-worker/one-slot-per-worker staging and production behavior,
settings/app rollback and strict trusted-proxy/TLS
handling in staging. A separate delivery workflow must promote the exact accepted image/configuration
with human production approval. No apply, GitHub federation or release promotion is implemented here.

See [hosted administration](hosted-administration.md),
[environment/promotion design](../engineering-design/24-environments-and-promotion.md) and
[the real OCI qualification manifest](real-oci-test-manifest.md#hosted-kubernetes-workloads).

References: [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/),
[Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/),
[Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/),
[ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/),
[Kubeconform](https://github.com/yannh/kubeconform).


## Source qualification — 13 November 2026

The final target is owner-selected Kubernetes1.37.0, with matching staging/production activation
annotations of two API and two one-slot workers; actual replicas remain zero. All94 focused
bundle/schema/update/version/handoff unit cases passed. The complete backend unit suite passed2,641
cases without failures/errors/skips and95.27% complete-source line coverage across189 files. Native
Kubeconform0.8.0 passed18 strict resource validations plus the required invalid-field rejection.
All137 mocked Terraform cases and five negative replacement guards passed with the1.37.0 fixtures.

Inline-purpose, full backend/scripts Ruff, Bandit, documentation/contract, publication, credential
and whitespace checks passed. Independent documentation and security reviews passed, including
worker-topology parity and scoped fixed-argv subprocess scan annotations. No UI/DB/runtime process
changed; no OCI call, Kubernetes apply, migration execution or saved8443 publication occurred. The
full PostgreSQL/Playwright integration suite was not rerun for this source-only slice; complete
milestone/PR gates and the listed hosted qualification remain required before release.


The [14 November NSG-only decision](nsg-only-networking.md) supersedes earlier NetworkPolicy intent. Current bundles have eight resources; dated validation receipts below/above retain their historical counts.

## Optional Caddy HTTP-01 source — 15 November 2026

The [ingress review guide](caddy-ingress.md) adds `--caddy-image` and `--ingress-network` only when
`hosted.ingress` is present. Six extra objects make14 total; one is a cluster-scoped StorageClass
that infrastructure authority must bootstrap separately from namespaced application delivery.
Caddy has its own command and zero replicas/target one; the base API/worker/migration holds remain.
The native schema gate now covers 60 objects across six candidates. Dated earlier receipts retain
their original object counts. Local Pebble protocol tests pass; the [two exact image-risk exceptions](../reference/caddy-security-exceptions.md)
are owner-approved with continuous updates. Targeted policy/native validation passes with two
accepted and zero blocked findings; remaining milestone/release/live qualification is separate.
No live OCI/public-CA call or saved app update is implied.
