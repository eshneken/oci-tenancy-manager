# 25: external DNS, Caddy ingress and automatic certificates

15 November 2026 · HTTP-01 source and approved image-policy/native checks pass · No live ingress or public-CA issuance

[Design hub](README.md) · [Environment delivery](24-environments-and-promotion.md) ·
[Source contract and review procedure](../how-to/caddy-ingress.md) ·
[NSG-only V1 boundary](../how-to/nsg-only-networking.md)

## Accepted requirements

The owner selected an externally managed hostname, Caddy-managed Let's Encrypt certificates and
**HTTP-01** validation. Atlas creates no OCI DNS zone and has no external DNS API integration,
external-dns controller, cert-manager or separate OCI certificate-upload workflow. The earlier
DNS-01 versus HTTP-01 question is resolved; no DNS-provider credentials or custom DNS module are
needed for this design. Actual domains and deployment inputs remain private and unavailable here.

Public TCP 80 serves only active ACME HTTP-01 challenges. Ordinary HTTP requests receive 404,
without an application response or HTTPS redirect. TCP 443 remains restricted to the existing
approved human CIDR union. IPv4 is the only implemented address family: publish an external A record
to the reviewed reserved address, and do not publish AAAA without a separately qualified IPv6 path.

Staging and production use separate hostnames, private inputs and certificate/account state.
Local Atlas 8443 and laptop OCI development remain independent. No source test authorizes cloud
provisioning, public certificate requests or changes to the saved application.

## Implemented request and trust path

An OCI network load balancer passes TCP 80/443 through to Caddy on high container ports 8080/8443.
Caddy terminates TLS and proxies the configured hostname to internal `otm-api:8080`, which routes to
the API replicas. The NLB receives no TLS private key or certificate upload. Caddy pins the Let's
Encrypt ACME directory, disables TLS-ALPN-01 and automatic HTTP redirects, and enables no arbitrary
on-demand hostname issuance.

The Service selects `externalTrafficPolicy: Local`, explicit source NAT
(`is-preserve-source=false`) and no PROXY protocol. Consequently, Caddy's observed transport peer
is not proof of the original human client address. Caddy removes untrusted `Forwarded`/`X-Real-IP`
and overwrites `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host`; the API's separately
configured proxy trust and session/origin/CSRF/authorization checks still apply. Qualify the actual
OKE controller/NLB translation, source-address behavior and API proxy boundary before activation.

The Service's shared source range is `0.0.0.0/0` so public HTTP-01 can work; **the exact edge NSG
handoff is what independently keeps443 CIDR-restricted**. Controller-managed security-rule changes
are disabled. Never apply this public Service without the matching reviewed firewall/address
resources, or assume a Service-wide range enforces different restrictions for its two ports.

Caddy has `admin off`; no port 2019 is exposed. A separate private port 9090 listener provides process
liveness and proxies readiness to the API. It is not a public Service port. TCP load-balancer health,
Caddy process liveness, TLS validity and application readiness are separate checks.

## Availability and persistent state

The source targets one Caddy pod per environment, held at zero replicas, using `Recreate` and a
single ReadWriteOnce 50 Gi claim for `/data`. The environment-specific StorageClass uses the OCI block
volume CSI driver, `WaitForFirstConsumer`, expansion support and a `Retain` reclaim policy.
Certificate private keys, ACME account state and locks must persist; `/config` and `/tmp` are bounded
pod-local scratch directories. Block-volume encryption, placement, CSI permissions and restoration
remain live qualification requirements, not results of the local Docker-volume test.

This is single-writer ingress with a rescheduling/update outage tradeoff, not highly available TLS
termination. Losing state may require reissuance, validation reachability and CA rate-limit headroom.
Retained volumes are not automatic backups. Document restricted backup/restore custody before
activation; do not add a synchronization service or independent certificate stores to hide the tradeoff.

The StorageClass is **cluster-scoped** and must be reviewed/bootstrapped by infrastructure authority.
Its appearance in the review bundle does not grant namespaced application CI cluster-admin rights.
The separate `otm-ingress` account receives no token automount, application/child credentials,
database mounts or workload-Vault grant. The nonroot image uses UID/GID 10001, dropped capabilities,
read-only root filesystem and high listener ports.

## Source inputs and object counts

The [complete field dictionary](../how-to/caddy-ingress.md#settings-and-private-network-handoff)
covers `[hosted.ingress].acme_email` and the six-field private Terraform network handoff. The public
hostname comes from the existing canonical `hosted.public_origin`; it must be a DNS hostname without
a port, wildcard or placeholder. The Caddy image is separately digest-pinned from the app image.

Terraform `caddy_ingress_enabled` defaults to false. Reviewed enablement defines public HTTP 80,
exact backend/health NodePorts 31080/31443/32081, and a protected reserved IPv4 address; it creates no
DNS records or NLB itself. The optional renderer adds six resources to the eight-resource base:
Caddy ConfigMap, ServiceAccount, StorageClass, PVC, Deployment and LoadBalancer Service. Thus a
Caddy candidate has 14 objects, of which one is cluster-scoped. Current schema fixtures total 60:
base simulated, base OCI and OCI+Caddy in each of staging/production, plus a separate rejection control.
No application database table, migration or UI screen changes.

## Validation and approved image-risk scope

Native tests have exercised real Caddy against an isolated Pebble CA: HTTP-01 issuance, verified
TLS/proxy/header behavior, ordinary HTTP 404 without redirects/upstream access, process restart with
persistent certificate state and actual short-lived-certificate renewal. These are real local ACME
protocol effects on disposable synthetic resources, **not Let's Encrypt or live OCI qualification**.

On 15 November, the owner approved **exactly two availability-risk exceptions** in the latest
verified official Caddy 2.11.9 build: `CVE-2026-116587` in `github.com/go-jose/go-jose/v3` v3.0.5 and
`CVE-2026-78661` in `golang.org/x/net` v0.60.0, only in `usr/bin/caddy`. These are accepted risks, not
proof of unreachable code or guaranteed protection against denial of service. The original scan
findings remain visible. All other/new HIGH or CRITICAL findings and incomplete scans still block.
See the [exact policy and continuous-update contract](../reference/caddy-security-exceptions.md).

The approved path uses the latest official build with continuous update checks, not a pending
wait-versus-custom-build choice. The 15-November TLS-verified GitHub API check reported official
v2.11.9, published 5 November. Daily workflow source checks the latest stable release and runs native
protocol/image qualification with fresh vulnerability data; existing weekly Dependabot proposes
version/digest updates without automatic merging. Hosted daily execution is not established until
the workflow is published/enabled. Dockerfile digests receive normal PR review; a new release or changed finding tuple requires exception re-review. Same-release digest updates may retain matching accepted tuples.

The approved-policy native rerun passed protocol and image-policy checks, with two accepted
findings and zero blocked findings; the stricter final evaluator also passed against that same real
scan. The complete backend unit gate passed 2,861 cases at 95.4027% line coverage across 197 modules.
The latest official release and Docker Hub tag/digest were verified against the pinned image.
These are targeted source results, not a full milestone/hosted deployment qualification. Complete
the remaining gates, then qualify real DNS, HTTP-01, NSG unions, NLB/controller behavior, private
health and CSI/state recovery in staging. Workloads stay held and saved 8443 remains unchanged.
See the [live manifest](../how-to/real-oci-test-manifest.md#external-dns-and-caddy-certificates).

Official references: [Caddy automatic HTTPS and persistent storage](https://caddyserver.com/docs/automatic-https),
[Caddy HTTPS prerequisites](https://caddyserver.com/docs/quick-starts/https)
and [OCI OKE load-balancer annotations](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingloadbalancer_topic-Summaryofannotations.htm).
