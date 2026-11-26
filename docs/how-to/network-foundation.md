# Private network foundation

**Implemented source; live OCI qualification Pending.** This guide covers the network definitions. The [OKE follow-up](oke-foundation.md) now adds cluster/node-pool source to both composed infrastructure roots; a live infrastructure apply would create worker VMs and the [managed PostgreSQL system](managed-postgresql.md). Optional [held Caddy/NLB source](caddy-ingress.md) is also available; application activation and live deployment remain separate work. No live resources were created during development. Do not infer working connectivity from mocks; the saved laptop app is unchanged.

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

The fixed staging and production `infrastructure` roots compose `infra/modules/networking`
alongside custody, OKE and PostgreSQL. Each uses its own environment compartment, provider identity
and private OCI backend. Operator bootstrap state remains separate and local.

| Subnet | Relative allocation in an example `/16` | Intended attachment and routing |
| --- | --- | --- |
| Edge | `.0.0/24` | Restricted HTTPS load balancer and optional public HTTP-01 challenge listener; internet-gateway route |
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

The base Edge NSG permits stateful TCP443 only from `app_ingress_allowed_cidrs`. With `caddy_ingress_enabled=true`, the [Caddy ingress source](caddy-ingress.md) adds public TCP80 solely for HTTP-01, exact backend NodePorts31080/31443 and health port32081; the Caddy handler rejects other HTTP traffic. The default false value adds none of those optional rules. The database NSG
permits TCP5432 only from the pod NSG, with matching pod egress. OCI-managed service requirements,
actual source VNIC/NSG attachments and PostgreSQL TLS remain live qualification work.
The OKE follow-up now installs the [explicit CNI/control/DNS/egress matrix](oke-network-traffic.md)
and attaches API/deployment, node and pod NSGs to the corresponding OKE VNICs. Deployment admission
remains empty until the owned CI workflow provides its temporary `/32`; no full GitHub range is
allowed. Optional Edge/backend/health rules now follow the [Caddy port contract](caddy-ingress.md); activation and live enforcement remain pending.
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

The protected Environment Secret **`OTM_ALLOWED_SOURCE_CIDRS`** is the sole release input for
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

Use the [composed infrastructure plan and apply](infrastructure-plans.md#one-infrastructure-plan-and-apply-per-environment).
Review the exact approved compartment, private VCN and subnet layout, human HTTPS/API sources,
empty security lists, OKE endpoint, worker image and database subnet/NSG in the same environment plan.
Keep apply held until state, role, permission and resource effects are qualified. Reconcile any
earlier platform state before using the composed backend.

After approved apply, read back route destinations, subnet flags and effective security rules.
Exercise allowed and denied paths, additive/controller rules, IPv6, private database source scope,
OKE IMDSv1 refusal and ARM sensor health. These are live exercises. Retain evidence in the
[network qualification manifest](real-oci-test-manifest.md#network-foundation).
