# How-to and review procedures

Use a deliberate local installation and preserve saved user data. Tests that mutate state use
isolated synthetic fixtures; private enrollment factors do not belong in reports or chat.

- [Real OCI manual test manifest](real-oci-test-manifest.md) — maintain pending live-only cases for every slice
- [Local review: Required users and manual Check now](required-users-runbook.md) — fresh simulated create/import, result provenance and historical unqualified records; [inventory summary follow-up](required-users-runbook.md#inventory-summary-source-checkpoint) is ready in the upgraded main preview
- [Manual check: baseline updates](baseline-update-runbook.md)
- [Manual review: configuration drift visibility](configuration-drift-runbook.md), including
  [pending real-OCI drift/repair tests and automated coverage](configuration-drift-runbook.md#pending-real-oci-manual-validation),
  plus [pending required-user presence cases](configuration-drift-runbook.md#pending-required-user-presence-qualification)
- [Local review: lifecycle email and environment routing](lifecycle-email-runbook.md), including [additional lifecycle notices](lifecycle-email-runbook.md#additional-lifecycle-notices)
- [Local quality checks](local-quality-checks.md)
- [Organization Mapping — manual test runbook](organization-mapping-runbook.md), including [return/consent correction checks](organization-mapping-runbook.md#return-and-destructive-consent-correction-review-after-installation) after deliberate installation
- [Parallel Atlas Test instance](parallel-local-instance.md)
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
