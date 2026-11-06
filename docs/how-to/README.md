# How-to and review procedures

Use a deliberate local installation and preserve saved user data. Tests that mutate state use
isolated synthetic fixtures; private enrollment factors do not belong in reports or chat.

- [Real OCI manual test manifest](real-oci-test-manifest.md) — maintain pending live-only cases for every slice
- [Local review: Required users](required-users-runbook.md)
- [Manual check: baseline updates](baseline-update-runbook.md)
- [Manual review: configuration drift visibility](configuration-drift-runbook.md), including
  [pending real-OCI drift/repair tests and automated coverage](configuration-drift-runbook.md#pending-real-oci-manual-validation),
  plus [pending required-user presence cases](configuration-drift-runbook.md#pending-required-user-presence-qualification)
- [Local review: lifecycle email and environment routing](lifecycle-email-runbook.md)
- [Local quality checks](local-quality-checks.md)
- [Organization Mapping — manual test runbook](organization-mapping-runbook.md)
- [Parallel Atlas Test instance](parallel-local-instance.md)
- [Manual review: administrator responsibility takeover](responsibility-runbook.md)
- [Manual review: tenancy detail, shared access and onboarding](tenancy-refinements-runbook.md)

Cloud bootstrap, managed services and scheduled drift acquisition have separate qualification
requirements in [the build order](../engineering-design/18-database-ci-and-build-order.md).
These procedures do not authorize deployment, repository publication or live OCI changes.

- [GitHub checkpoints and CI definitions](github-checkpoints.md)

Workflow definitions are repository artifacts; hosted runs, branch protection and deployment
qualification must be verified separately. This guide does not authorize cloud deployment.

- [Manual review: current-month cost visibility](test-cost-visibility.md)
