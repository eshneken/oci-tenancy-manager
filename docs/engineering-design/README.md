# Engineering design

The current design retains accepted decisions while keeping implemented local behavior separate
from future live OCI and deployment qualification. Start with [the product scope](../product/oci-tenancy-manager-spec.md)
and [implemented reference guides](../reference/README.md). The earlier organization prototype is
retired; historical checkpoints preserve decisions rather than runnable prototype instructions.

The current application has real authentication, durable organization/tenancy workflows, baseline
management, read-only drift visibility and lifecycle email capture. OCI effects are simulated;
corporate SSO, real provider bindings and infrastructure deployment need separate qualification.
Drift scheduling is explicitly deferred until staging/Kubernetes deployment. All five hosted CI jobs
and administrator-enforced master protection are verified at baseline `db08b3b`. Use
[one milestone PR](../how-to/github-checkpoints.md) for related implementation slices; the five
required gates and protections apply to every reviewed candidate.

## Chapters

[Imported shared-tenancy membership adoption](24-imported-membership-adoption.md) describes the
17 November local simulator implementation: existing owner/member identities, full lifecycle consent,
multi-scope provenance and independent read-only access checks. The477-test complete suite and
saved8443 migration0029 publication passed under explicit local dependency-risk acceptance; the
hosted security gates remain required, with the [exact advisory exception](../reference/frontend-security-exception.md) and real OCI Pending. This is separate from chapter24's environment design.

The [later shared-root/owner-promotion source follow-up](24-imported-membership-adoption.md#transfer-privilege-evidence-local-source-follow-up-and-real-adapter-gate)
adds conditional verified administrator proof, operation-authenticated current expectations and
persistent fake-provider observations. Its [separate published local checkpoint](24-imported-membership-adoption.md#root-membership-and-owner-promotion-follow-up--17-november-2026) records targeted qualification and a successful focused retry after initial full-run
failures; the fresh app1564f8c integration run passed481 tests with zero failures/errors/skips. It does not inherit the earlier477-test receipt or clear hosted security gates.

Required-account foundation: [implemented presence boundary and remaining integration](../reference/required-user-presence.md).
Current configuration repair: [implemented flow and field map](../reference/configuration-repair.md).


Provider implementation layout: the [5 November decision](02-operations-and-provider.md#provider-contract-and-implementation-files--5-november-2026)
separates functional contracts, simulators and future OCI adapters. The
[implemented extraction](../reference/provider-layout.md) preserves local behavior; real OCI
integration remains separately qualified.

| Design area |
| --- |
| [01: domain, workflows, data and screens](01-domain-and-journeys.md) |
| [02: durable execution, OCI facade and simulator](02-operations-and-provider.md) |
| [03: managed root objects, baseline versions and tenancy overrides](03-templates-and-drift.md) |
| [04: identities, credentials, access and break glass](04-identity-and-access.md) |
| [05: usage, financial visibility, operational notifications and history](05-cost-and-observability.md) |
| [06: production operations, database and development handoff](06-platform-and-delivery.md) |
| [07: create, import and onboarding operations](07-onboarding-journeys.md) |
| [08: OCI SDK call design and qualification](08-oci-sdk-call-design.md) |
| [09: facade messages and durable onboarding execution](09-execution-contracts.md) |
| [10: proposed configuration data model and screen contracts](10-configuration-data-model.md) |
| [11: unified proposed production data model and UI field guide](11-production-data-model.md) |
| [12: required access, observations and bounded repair](12-access-health-and-repair.md) |
| [13: administrator password access and independent recovery](13-local-support-and-emergency-access.md) |
| [14: financial screens and collection contract](14-financial-journeys.md) |
| [15: financial collection and operational events](15-collection-and-operational-events.md) |
| [16: financial and email contract review](16-c5-contract-review.md) |
| [17: simple V1 credential resolution and manual restore](17-recovery-and-release.md) |
| [18: database, CI and incremental build order](18-database-ci-and-build-order.md) |
| [19: application administrators and local recovery sign-in](19-administrator-provisioning.md) |
| [Organization mapping settings](20-organization-mapping-settings.md) |
| [21: environment email routing and release guards](21-environment-email-policy.md) |
| [22: recovery console CIDR boundary and 30-day API-key rotation](22-credential-security-lifecycles.md) |
| [23: proposed managed signing-key rotation execution and accounting](23-signing-key-rotation.md) |
| [24: isolated staging/production and build-once promotion](24-environments-and-promotion.md) |

## Authority and decisions

[Accepted D1–D17](../decisions/engineering-review-decisions.md) and [D18–D58](../decisions/design-decisions.md)
retain rationale and explicit supersessions. [The current data model](11-production-data-model.md)
distinguishes implemented tables from the full proposed model; [implemented diagrams](../architecture/diagrams/README.md)
are grouped separately from proposals. Source and frozen migrations determine actual storage.

[UI baseline](../../DESIGN.md), [screen authority](../ui-screen-authority.md),
[test policy](../engineering-test-plan.md) and [security policy](../security-review-policy.md)
remain required. The [old design index](../history/engineering-design-index-2026-11-05.md) is preserved
as history; dated receipts and progress do not supersede current requirements. Private source
feeds, screenshots and unsanitized reports are not distributed.

Current-month financial implementation and deferred/live boundaries: [cost visibility](../reference/cost-visibility.md).

Current manual user-presence source, fields and qualification boundary: [presence checks](../reference/user-presence-checks.md).

Compact required-user inventory summary: [qualified field/state reference](../reference/required-users-summary.md), with the main preview updated and the parallel preview unchanged.

Normal-directory onboarding without provisioning: [Keep in organization without a tenancy](../reference/organization-workflows.md#keep-in-organization-without-a-tenancy).

Current member entry and user-data refresh follow the [workflow reference](../reference/organization-workflows.md#add-a-member-from-a-shared-tenancy) and [presence screen guide](../reference/required-users-screen.md).

Compact create/import help: [Collapsed OCI operator checklist](../reference/tenancy-onboarding.md#collapsed-oci-operator-checklist).

Owner retention, verified identity removal and manual cleanup: [explicit former-owner disposition](../reference/organization-workflows.md#explicit-former-owner-disposition--7-november-2026).

Confirmed required-user email: [current incident/routing/storage contract](../reference/required-user-alerts.md).

Implemented source: [recovery-password custody/disclosure/rotation subset](../reference/recovery-password-access.md). Migration0027 adds three tables; the [checkpoint receipt](../history/recovery-password-checkpoint-2026-11-09.md) records qualification and saved-app status. Main8443 remains the sole local review environment.

Accepted hosted sizing: [two API pods and two one-slot workers in both staging and production](06-platform-and-delivery.md#accepted-initial-worker-sizing--10-november-2026). Source manifests remain held at zero replicas; the local saved worker is unchanged.

Hosting direction: [paid tenancy, Enhanced OKE, multiple ARM nodes and managed PostgreSQL](06-platform-and-delivery.md#paid-tenancy-platform-direction-and-candidate-sizing--13-november-2026). Numerical capacity is a proposal pending qualification, not an approved allocation.

Hosting region: `us-ashburn-1`; no second-region DR site in V1. [Backup policy and capacity proposal](06-platform-and-delivery.md#ashburn-v1-backup-policy-proposal--13-november-2026) covers retained recovery points, storage accounting and restore drills.


- [25: external DNS, Caddy HTTP-01 ingress and automatic certificates](25-https-ingress-and-certificates.md) — implemented held source; two exact image-risk exceptions approved with continuous updates; targeted policy/native validation passes; live issuance remains pending.

- [Repeatable release verification](24-environments-and-promotion.md#repeatable-release-verification--16-november-2026) — [candidate and workflow contract](../reference/artifact-releases.md); genuine native ARM publication, six signed subjects and hosted manual verification qualified, including wrong-Checkpoint rejection; remaining custody and OCI acceptance/deployment stay Pending.

- [Infrastructure plan/review/apply delivery](24-environments-and-promotion.md#infrastructure-planreviewapply-delivery--16-november-2026)
  — held OAuth-assisted workflows, authenticated own-environment plans, single-use apply and explicit
  manual staging-test confirmation; live OCI remains Pending.
