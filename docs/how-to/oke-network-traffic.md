# OKE network traffic matrix

Source: `infra/modules/networking/oke-rules.tf`, composed with `infra/modules/oke`.
This records configured intent; live OCI routing/NSG effectiveness remains Pending. All rules are
stateful. Each internal connection has matched egress on the source group and ingress on the
destination group; return traffic is tracked. Service NSGs are attached to exact endpoint/node/pod
VNICs by the OKE module. Empty attached/default security lists add no permissive rule.

| Source | Destination | Protocol / destination port | Purpose |
| --- | --- | --- | --- |
| Approved human CIDR union | API NSG | TCP6443 | Lens/kubectl; still requires OCI/Kubernetes authorization |
| Nodes NSG | API NSG | TCP6443, TCP12250 | Node registration/control-plane communication |
| Pods NSG | API NSG | TCP6443, TCP12250 | Native pod/control-plane communication |
| API NSG | Nodes NSG | TCP10250 | Kubelet control/inspection |
| API NSG | Pods NSG | All protocols/ports | VCN-native control-plane-to-pod traffic |
| Nodes NSG | Nodes NSG | All protocols/ports | Internal worker communication |
| Nodes NSG ↔ Pods NSG | Peer NSG | All protocols/ports | VCN-native node/pod communication |
| Pods NSG | Pods NSG | All protocols/ports | Pod networking, including in-cluster DNS |
| API NSG | Regional Oracle service prefix | TCP443 | Managed OKE service access |
| Nodes/Pods NSG | Regional Oracle service prefix | TCP, all ports | OKE/OCI service requirements |
| Nodes/Pods NSG | Internet through NAT | TCP443 | HTTPS image registries, APIs and approved installer retrieval |
| API/Nodes/Pods NSG | `169.254.169.254/32` | TCP53 and UDP53 | OCI resolver requests |
| Any source ↔ API/Nodes/Pods NSG | Scoped group | ICMP type3/code4 only | Path-MTU discovery; no general ICMP/TCP admission |
| Approved app CIDR union | Edge NSG | TCP443 | Atlas UI/API HTTPS; same human input, separate service |
| Pods NSG | Database NSG | TCP5432 | Managed PostgreSQL, pending actual database attachment/TLS qualification |
| Owned deployment job `/32` | Deployment NSG on API endpoint | TCP6443 only | **Future admission workflow; no rule created by this slice** |

The broad internal CNI rules use peer NSG identities, not public or whole-VCN sources. They do not
provide Kubernetes namespace/role isolation. V1 intentionally uses no pod policy engine. OCI NSGs
do not filter link-local traffic, so resolver rule entries do not block metadata HTTP. Least-privilege
workload/instance identity, IMDSv1 disabled and live metadata/network checks remain required.

Only Edge and API subnets allow public IPs and use an internet gateway. Nodes/Pods use NAT and a
regional service gateway. Database has only the service route. No IPv6, inbound SSH or external
TCP12250/TCP10250 is configured. The globally addressed ICMP exception is restricted to the precise
fragmentation-needed message. No unrestricted public TCP/UDP ingress exists.

The Edge NSG is not yet attached to a live application load balancer. The optional
[Caddy HTTP-01 source](caddy-ingress.md) now defines exact edge-to-node TCP 31080/31443 backend and
TCP 32081 health rules when `caddy_ingress_enabled=true`, with paired stateful egress/ingress.
The default false adds none of those rules or the protected reserved IPv4 address. Public TCP 80
is challenge-only at Caddy; edge TCP 443 retains the approved human source union. The NLB Service
disables controller-managed security-rule changes and requires the exact private handoff. Do not
pre-open a general NodePort range. Effective unions, NLB source NAT/controller/health behavior and
exact image-policy/native validation remain qualification prerequisites; no live ingress is created by source checks.

The implementation follows the VCN-native branch of [Oracle's network requirements](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig.htm)
and [public-endpoint examples](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfigexample.htm).
Required ports and actual source identity must be rechecked against the pinned release during
staging qualification; mocked tests validate our configured policy, not OCI's implementation.


Optional `smtp_egress` adds stateful TCP465/587 pod-NSG rules only for explicit relay CIDRs, without narrowing existing Oracle-service/CNI rules. See [V1 boundaries and inputs](nsg-only-networking.md).
