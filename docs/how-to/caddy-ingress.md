# Review the held Caddy HTTP-01 ingress source

15 November 2026 · Implemented source; approved exact image-policy and native checks pass; live qualification pending

This procedure prepares private review artifacts. It does not apply Terraform/Kubernetes resources,
change external DNS, contact Let's Encrypt or update saved Atlas 8443. The owner selected HTTP-01:
public port 80 handles active challenges only; other HTTP returns404 without redirects or app proxying.
HTTPS 443 stays CIDR-restricted by the exact edge NSG. See the [design and accepted image-risk scope](../engineering-design/25-https-ingress-and-certificates.md).

## Settings and private network handoff

| Source / field | Meaning and validation |
| --- | --- |
| `hosted.ingress` | Optional `CaddyIngressSettings`; absent retains the eight-object base bundle. Presence requires a separately pinned Caddy image and complete network handoff. |
| `hosted.ingress.acme_email` | Operator's ACME contact; validated mailbox, 1–254 characters; rejects Caddy placeholder characters `{`, `}` and `$`. Omitted from model representation, but present in the private Caddy configuration; not a secret-storage mechanism. |
| Existing `hosted.public_origin` | Canonical HTTPS origin; ingress additionally requires one lowercase DNS hostname, labels of 1–63 characters, total hostname at most 253, no IP, wildcard, explicit port or trailing dot. The existing origin contract also bounds its overall length. |
| `CaddyNetworkBinding.environment` | Exact `staging` or `production`; must match independent renderer target and namespace. |
| `compartment_ocid` | Exact hosting compartment reference, validated compartment OCID; no lookup or live ancestry proof. |
| `https_allowed_cidrs` | 1–64 canonical bounded IPv4 CIDRs using the shared non-universal allowlist validator; must equal the configured recovery-console/human source set. IPv6 is rejected for this ingress path. |
| `reserved_ipv4` | Canonical IPv4 text, 7–15 characters; private/local/link-local/multicast and explicitly rejected reserved ranges fail validation. Documentation addresses are allowed for synthetic tests. Actual allocation is established by the private Terraform handoff, not syntax. |
| `edge_subnet_ocid` | Exact reviewed edge subnet OCID; no arbitrary annotation text. |
| `edge_nsg_ocid` | Exact reviewed edge network-security-group OCID; it must enforce the public port 80 versus source-restricted 443 distinction. |

OCID fields accept their exact resource kind/realm prefix and a bounded 1–220-character suffix.
Contracts reject unknown/coerced fields. These seven new configuration/handoff fields contain no
DNS API credential, certificate or private key; actual contacts and cloud references stay private.
The handoff is a closed six-field JSON object; the CLI reads at most 16 KiB. It is not a Terraform
state file or full `terraform output -json` map with type/value wrappers.

## Prepare a review candidate

Use a private reviewed staging settings file containing the existing `[hosted]`, proxy-trust and
recovery-console settings, with the externally assigned hostname as `hosted.public_origin`. Add:

```toml
[hosted.ingress]
acme_email = "operator@example.test"
```

The address above is documentation data; configure the actual approved contact privately.
Production uses its own hostname/contact, settings, image approvals and state. No external DNS
provider credential is used. Do not publish an AAAA record: this source is IPv4-only.

Both hosted platform roots accept `caddy_ingress_enabled=false` by default. Only a separately
approved infrastructure plan may enable it. Enabling defines the reserved address, public TCP 80 and
exact edge-to-node NodePorts 31080/31443/32081; it does not activate app pods or create external DNS.
Review the platform's sensitive `ingress` output and privately export its **object value**, for example
with `terraform output -json ingress` from the approved initialized platform directory. A null output
means disabled infrastructure and cannot serve as an ingress handoff. Never upload these references,
state or plans as public CI artifacts.

From the repository root, with private paths and both approved digest references supplied separately:

```sh
umask 077
uv run --project backend python -m otm.kubernetes_release \
  --config "$OTM_REVIEW_SETTINGS" \
  --expected-environment staging \
  --image "$OTM_APP_IMAGE" \
  --caddy-image "$OTM_CADDY_IMAGE" \
  --ingress-network "$OTM_INGRESS_NETWORK" \
  --output "$OTM_REVIEW_BUNDLE"
```

The output path must be new; existing files are not overwritten. The renderer reports only its
content hash and held status, not the private contents. Digest syntax is not a clean-image proof;
complete the [approved exact image policy](../reference/caddy-security-exceptions.md), native checks
and remaining release/live prerequisites before any separately authorized deployment.

## Inspect scope, networking and credentials

Optional ingress adds six objects: immutable Caddyfile ConfigMap, token-free `otm-ingress`
ServiceAccount, cluster-scoped StorageClass, namespaced PVC, zero-replica Deployment and NLB Service.
The result is 14 objects, not 14 namespaced objects. Infrastructure authority owns StorageClass
bootstrap/review; ordinary namespaced application delivery must not acquire cluster-admin permission
or blindly apply this mixed-scope list. The base API/worker/migration commands remain held; Caddy's
own command runs Caddy only after separately qualified activation of its zero-replica Deployment.

Check the separately pinned Caddy image, nonroot UID/GID 10001, dropped capabilities, read-only root,
no token/database/app-secret mounts, `admin off` and no Service/admin port 2019. `/data` uses the 50 Gi
ReadWriteOnce claim; the environment-specific CSI StorageClass is `Retain`/`WaitForFirstConsumer`.
`/config` and `/tmp` are16 Mi scratch volumes. Recreate with target one pod permits ingress outages;
retention does not implement encrypted backup, cross-AD rescheduling or automatic restoration.

The Service exposes80/443, uses IPv4, `externalTrafficPolicy: Local`, source preservation false and
PROXY protocol false. Its shared source range is 0.0.0.0/0; matching Terraform-managed edge NSG rules
must restrict443 independently. Controller rule management is disabled. Real NLB/controller and NSG
union behavior remain unqualified. Ordinary HTTP paths/methods have no app backend or redirect;
Caddy responds to active HTTP-01 tokens internally. TLS-ALPN challenge is disabled and the issuer is
explicitly Let's Encrypt, with no alternative public-CA fallback selected by the source.

Caddy overwrites forwarding headers from its observed peer, removes `Forwarded`/`X-Real-IP`, and
proxies only the configured hostname. With explicit NLB SNAT, do not treat that peer as the original
human IP. API proxy trust remains a separate exact network configuration. Private9090 liveness and
API-backed readiness are not NLB public listeners, and TCP health alone does not qualify TLS/app health.

## Automated evidence and exact accepted exceptions

Run only disposable source checks; no real hostname or cloud credentials are needed:

```sh
uv run --project backend python scripts/check_kubernetes_bundle.py
uv run --project backend python scripts/check_caddy_ingress.py
```

The schema gate now requires 60 resources:8+8+14 in each of two environments, plus an independent
invalid-field rejection control. The Caddy gate builds the pinned separate image and uses a local
isolated Pebble CA, synthetic backend and private disposable volume. Native HTTP-01 issuance,
verified TLS, spoofed-header replacement, HTTP 404/no redirect/no upstream access, process restart
with persisted certificate and short-lived-certificate renewal have passed. This does not qualify
Let's Encrypt issuance, OCI DNS/NLB/IAM/CSI behavior or public reachability.

On 15 November, the owner accepted the two exact DoS findings in the latest verified official
Caddy 2.11.9 binary: CVE-2026-116587/go-jose/v3 v3.0.5 and CVE-2026-78661/x/net v0.60.0, only at
`usr/bin/caddy`. The [machine-scoped policy](../reference/caddy-security-exceptions.md) retains the
findings and accepts their availability risks; it does not prove absence of an attack path. Other
or changed HIGH/CRITICAL findings, wrong release/component versions or paths, and missing scans remain blocking. Dockerfile digests are reviewed separately; a same-release digest update may retain exact matching accepted tuples. No
blanket ignore-unfixed or general Caddy waiver is approved. The policy-specific native rerun now
passes with two accepted and zero blocked findings. This is not a full milestone pass, deployed
workflow or hosted installation.

## Initial source-check disposition — 15 November 2026, before exception approval

The complete backend unit-only gate passed 2,845 cases with 95.4027% line coverage across 197
application modules. The 41 focused cases, 165 native Terraform mock cases plus eight replacement
guards, and 60 strict Kubernetes resource validations plus the rejection control passed.
The final isolated native result reports `protocol_checks_passed=true`, `image_scan_passed=false`
and `stage=image-scan`; all owned ingress containers, volumes and networks were removed.

These are historical source/targeted results from before the owner's narrow exception approval,
not a full milestone pass or deployment approval. The subsequent approved-policy rerun has its own passing
scan/protocol result below; approval alone does not turn this earlier failed run into a pass.
No saved application, live OCI resource or public-CA state changed. Independent purpose/comment and
documentation checks pass; real deployment and certificate-state recovery remain unqualified.

## Approved-policy targeted validation — 15 November 2026

The complete backend unit-only gate passed 2,861 cases with 95.4027% line coverage across 197
application modules. The final isolated native run passed HTTP-01/proxy/persistence/renewal and
image-policy checks: latest official 2.11.9, two accepted findings and zero blocked findings. The
stricter final evaluator rechecked that same actual scan with the same result. The official Docker
Hub tag/digest was verified against the pinned image. Purpose, formatting, publication/privacy and
independent security reviews passed; the approved findings remain accepted, not fixed.

The earlier 165 Terraform cases/eight replacement guards and 60 strict Kubernetes resources plus
rejection control remain the infrastructure/schema evidence for this source. No new focused-test
count is inferred here. This targeted checkpoint is not a full application milestone run or hosted
activation. Saved 8443, live OCI and public-CA state remain unchanged; the daily workflow still needs
publication/hosted activation. Normal PR/release and live qualification gates remain in effect.

## Pending live review

After the exact policy/native checks and remaining release gates, use the [live manifest](real-oci-test-manifest.md#external-dns-and-caddy-certificates)
for external A routing, allowed/denied 443, challenge-only 80, actual issuance/renewal, controller NSGs,
NLB source NAT/health, private backends, nonroot CSI ownership/encryption/placement and restricted
certificate/account backup/restore. Do not test by mutating the saved laptop app or by issuing public
certificates from CI. Keep separate ACME state and persistent volumes in staging and production.
