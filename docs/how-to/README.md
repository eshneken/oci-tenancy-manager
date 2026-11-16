# How-to and review procedures

Use a deliberate local installation and preserve saved user data. Tests that mutate state use
isolated synthetic fixtures; private enrollment factors do not belong in reports or chat.

- [Stakeholder demo script](stakeholder-demo.md) — natural 30-minute flow, 12-minute route, presenter cues and three synthetic CSVs; preserve saved data and rehearse installed capabilities

- [Real OCI manual test manifest](real-oci-test-manifest.md) — maintain pending live-only cases for every slice
- [Hosted administrator runbooks](hosted-administration.md) — design-stage application, infrastructure, combined/settings updates and backup/restore procedures; implementation and staging walkthrough required before live use
- [Terraform state bootstrap](terraform-state-bootstrap.md) — implemented isolated roots, mock checks and pending live operator procedure; does not create the application platform
- [Network foundation](network-foundation.md) — subnet/routing/NSG source, private shared-input rendering and platform initialization; OKE/managed PostgreSQL and optional [held Caddy ingress](caddy-ingress.md) source; live qualification pending
- [Enhanced OKE and worker bootstrap](oke-foundation.md) — source-restricted public API, private ARM node/pod bindings, sensitive cloud-init input and pending Falcon ARM64 qualification
- [OKE traffic matrix](oke-network-traffic.md) — explicit control/CNI/DNS/egress rules, optional Caddy backend/health rules and pending job-specific admission
- [Platform versions and image selection](platform-versions.md) — OKE/PostgreSQL Actions variables, automatic image resolution and executable private staging-to-production image handoff
- [Pending credential-security qualification](real-oci-test-manifest.md#credential-security-lifecycles) — recovery-console CIDR boundary and 30-day automation-key retirement
- [Local review: Required users and manual Check now](required-users-runbook.md) — fresh simulated create/import, result provenance and historical unqualified records; [inventory summary follow-up](required-users-runbook.md#inventory-summary-source-checkpoint) is ready in the upgraded main preview
- [Manual check: baseline updates](baseline-update-runbook.md)
- [Manual review: configuration drift visibility](configuration-drift-runbook.md), including
  [pending real-OCI drift/repair tests and automated coverage](configuration-drift-runbook.md#pending-real-oci-manual-validation),
  plus [pending required-user presence cases](configuration-drift-runbook.md#pending-required-user-presence-qualification)
- [Local review: lifecycle email and environment routing](lifecycle-email-runbook.md), including [additional lifecycle notices](lifecycle-email-runbook.md#additional-lifecycle-notices)
- [Local quality checks](local-quality-checks.md)
- [Organization Mapping — manual test runbook](organization-mapping-runbook.md), including [return/consent correction checks](organization-mapping-runbook.md#return-and-destructive-consent-correction-review-after-installation) after deliberate installation
- [Retired parallel Atlas Test instance](parallel-local-instance.md) — historical instructions only; current local use is8443 only, with no new instance creation
- [Manual review: administrator responsibility takeover](responsibility-runbook.md)
- [Manual review: tenancy detail, shared access and onboarding](tenancy-refinements-runbook.md)

Cloud bootstrap, managed services and scheduled drift acquisition have separate qualification
requirements in [the build order](../engineering-design/18-database-ci-and-build-order.md).
These procedures do not authorize deployment, repository publication or live OCI changes.

- [GitHub checkpoints and CI definitions](github-checkpoints.md) — complementary backend unit and PostgreSQL/browser lanes, with all required checks retained

Workflow definitions are repository artifacts; hosted runs, branch protection and deployment
qualification must be verified separately. This guide does not authorize cloud deployment.

- [Manual review: current-month cost visibility](test-cost-visibility.md)

The [required-user runbook](required-users-runbook.md) now uses one Refresh user data action for provider acquisition, with automatic progress updates.

The [live OCI manifest](real-oci-test-manifest.md#pending-explicit-owner-retention-and-identity-removal)
includes replacement verification, identity retention/removal and manual resource-cleanup qualification.

- [Recovery-policy UI checkpoint](recovery-policy-ui-checkpoint.md): safe local inspection of independent user and console-policy controls.

- [Review contextual operation Back links](operation-navigation.md) — source navigation follow-up; check its separate validation/install receipt before manual main review

- [Managed signing-key rotation local review](signing-key-rotation-runbook.md): newly onboarded simulated child, original schedule, guarded manual expedite and immutable history; use after confirmed installation.

- [Container development](container-development.md) — installed image, private build-context checks and disposable image qualification

- [Managed PostgreSQL foundation](managed-postgresql.md) — private two-node service, provisioning references, recovery policy and upgrade safeguards; live qualification pending

- [Vault custody foundation](vault-foundation.md) — separate security roots, shared Vault/HSM keys, private ingestion handoff and database-reader IAM

- [Hosting compartment input](hosting-compartment.md) — required per-environment Actions variable, private renderer and one-compartment placement across infrastructure roots

- [Hosted Kubernetes workload bundle](kubernetes-workloads.md) — disabled API/worker/migration manifests, immutable settings, credential references and strict schema checks; startup mechanics implemented; hosted composition/activation pending.

- [Hosted startup foundation](hosted-startup.md) — explicit TLS/roles, readiness, migration and worker composition; activation remains held.

- [Schema-changing release maintenance](hosted-administration.md#schema-changing-application-release) — approved V1 drain/migrate/start/reopen procedure; unchanged-schema releases roll normally.


- [Laptop OCI development](laptop-oci-development.md) — named API-key profiles, strict mode selection and minimal development Terraform custody.


- [Hosted workload identity and Vault IAM](oke-workload-identity.md) — security-root Vault handoff, cluster-bound policies, projected tokens and remaining live checks.


- [V1 NSG-only networking](nsg-only-networking.md) — network controls, relay inputs and pending live checks; pod policy engine deferred.

- [Caddy HTTP-01 ingress review](caddy-ingress.md) — settings/network handoff, mixed-scope 14-object bundle and native evidence; approved narrow image-risk policy, continuous updates and pending live qualification.

- [Application release review](application-releases.md) — download four public files, run the read-only authenticated provenance/SBOM verifier and distinguish integrity from staging acceptance, deployment and long-term custody.
