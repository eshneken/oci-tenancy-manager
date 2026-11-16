# V1 networking: OCI NSGs without a pod policy engine

Approved 14 November 2026: Atlas V1 uses OCI NSGs/security lists and the existing VCN-native OKE
networking. Do not install Calico, Cilium or another policy engine for this release. The dedicated
Atlas cluster hosts one trusted application. Kubernetes pod-level policy enforcement is deferred.

The bundle no longer emits a NetworkPolicy. Creating a default-deny object without a policy engine
would not enforce the claimed boundary; leaving it in the bundle could also cause unexpected denial
if a policy engine were introduced later. No live object was deleted: these manifests have never
been applied to a real cluster. Do not delete externally managed policies from an existing cluster;
inspect corporate cluster controls and effective access during staging qualification.

## Configured V1 network boundaries

The [NSG traffic matrix](oke-network-traffic.md) remains authoritative for network intent:

- Source-restricted HTTPS at the edge and source-restricted Kubernetes administration on TCP6443.
- OKE CNI/control-plane connections between the intended NSG peers.
- PostgreSQL access from the pod NSG to the database NSG on TCP5432.
- Regional Oracle service access and existing outbound public HTTPS through NAT.
- Optional relay-specific SMTP egress from the pod NSG.

These are source rules, not proof of live routing or effective enforcement. Check all attached NSGs,
security lists and routes together. Rules are additive: a narrow rule cannot deny access already
allowed by another applicable rule. The existing regional Oracle-service and CNI allowances remain.
Public TCP443 egress is not a hostname allowlist limited to OCI.

API, worker and migration pods share the pod NSG; it does not distinguish their Kubernetes labels or
service accounts. Database role privileges, workload IAM, application authentication/authorization
and TLS remain separate controls. In particular, migration has no grant from the application Vault
workload policies even though its network placement is shared. No pod-to-pod default-deny or
role-specific network restriction is claimed in V1.

OCI security rules do not filter link-local traffic in 169.254.0.0/16. The existing resolver rule
entries express DNS intent; they do not block metadata HTTP. IMDSv1 remains disabled on every managed
node, but disabling IMDSv1 is not an IMDSv2 access firewall. Node identities must not receive
application-secret authority through our workload policies; audit other policies and actual metadata
reachability before activation. This slice adds no node permission or host firewall configuration.

## Optional SMTP relay access

Both hosted platform roots accept the same optional `smtp_egress` input, passed to the network module:

```hcl
# Documentation addresses only; replace privately with approved relay destinations.
smtp_egress = {
  cidrs = ["192.0.2.80/32", "198.51.100.64/28"]
  port  = 587
}
```

Omit it or use null to create no additional relay-specific rules. The object requires explicit port
465 or587 and 1–64 canonical IPv4 CIDRs totaling at most4096 serialized bytes. IPv6, malformed values,
host bits, /0 and unions covering all IPv4 are rejected. A /32 represents one relay address; overlapping
ranges remain valid without double-counting the effective union. There is no DNS hostname input or
automatic resolution of a hostname into long-lived firewall rules.

Each rule is stateful outbound TCP from the shared pod NSG to the exact destination/one selected
port. It adds no inbound port, node/edge rule, broad mail egress or VM. Existing Oracle-service/CNI
rules may already permit a destination; null is not an overall SMTP-denial switch.

Match these inputs to the approved service's current destinations and the application
`notifications.smtp_port`. Require STARTTLS or implicit verified TLS in the application; selecting
port465/587 in an NSG does not itself enforce TLS. Store SMTP credentials separately. Qualify actual
DNS/IP/routing/TLS and effective rule unions before enabling hosted notifications. Relay address or
port changes require reviewed Terraform changes, separate from an ordinary app-only deployment.

The base `caddy_ingress_enabled=false` configuration opens no backend/health ports. The optional
[Caddy ingress source](caddy-ingress.md) defines the exact paired NodePorts and health-check NSGs;
no permissive NodePort range or public backend ingress is opened. Image pulls are node-level
traffic, not application pod traffic. Hosted commands remain held, replicas zero and migrations
suspended until the remaining launch/deployment qualifications pass.

## Tests and future work

Bundle tests assert no NetworkPolicy resources in either environment or provider mode, while retaining
held commands, token-role restrictions and pod hardening. The base fixtures have 32 resources
(eight per bundle, two modes, two environments). The later [optional Caddy source](caddy-ingress.md)
adds two 14-object fixtures, making the current native gate 60 resources plus its required invalid-field rejection.

Terraform mocks verify no extra relay rule by default; exact NSG/destination/protocol/port behavior;
implicit-TLS port465; and invalid ports, malformed/noncanonical/IPv6/default/unrestricted CIDRs,
empty/oversized sets and oversized serialized input. The existing full networking tests preserve
PostgreSQL, OKE/CNI, inbound allowlist and route boundaries. No cloud connection occurs in those tests.

The [manual manifest](real-oci-test-manifest.md#nsg-only-v1-network-boundary) tracks actual routing,
rule unions, metadata/IAM and SMTP checks. Pod policy engines can be reconsidered if the cluster is
shared or strict intra-application network separation becomes a requirement; they are not a V1 gate.

Official references: [OCI security rules, unions and link-local exception](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm),
[OKE policy engine requirement](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupcalico.htm)
and [OCI SMTP TLS configuration](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted_topic-Configure_the_SMTP_connection.htm).

## Source validation receipt — 14 November 2026

The complete backend unit gate passed 2,801 cases without failures/errors/skips and 95.37%
complete-source line coverage across 195 modules. All41 focused bundle/schema cases passed; native
Kubeconform passed32 resources plus its invalid-field rejection. The complete mocked Terraform gate
passed161 cases and seven replacement guards, including the new relay-boundary cases.

Inline-purpose, Ruff, Bandit, documentation/link, publication, credential and whitespace checks
passed. Independent security/documentation reviews completed; stale default-deny wording and current
resource counts were corrected while dated receipts were retained. No UI/data model changed, no
cloud operation or migration ran, and the saved8443 snapshot remained unchanged and healthy.
Full application integration/Playwright and actual OCI network qualification remain separate gates.
