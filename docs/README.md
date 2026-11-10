# Documentation

Use this index for the current application. Historical checkpoints explain past decisions; they
are not competing implementation instructions or proof of real OCI behavior.

**Current local environment — 9 November 2026:** use only [Atlas on localhost:8443](https://localhost:8443).
The [former8444 instance is retired](how-to/parallel-local-instance.md); no additional local instances
are requested. Interactive recovery-network repair testing is [deferred until real OCI](reference/recovery-network-repair.md#manual-local-checkpoint-runbook).
Earlier dated preservation receipts remain historical evidence.

| Need | Start here |
| --- | --- |
| Product scope and acceptance criteria | [Product specification](product/oci-tenancy-manager-spec.md) |
| Current architecture and approved future design | [Engineering design](engineering-design/README.md) |
| Lifecycle action/failure email | [Responsible-only scope and parity](reference/lifecycle-email.md#lifecycle-notice-parity--6-november-2026), [source checkpoint](history/lifecycle-notice-parity-checkpoint-2026-11-06.md) |
| Run the application | [Local HTTPS setup](reference/local-application.md) |
| Manual required-user presence checks | [Current check fields, authority and ER](reference/user-presence-checks.md) |
| Presence-only connection foundation | [Current fields, ER and qualification boundary](reference/user-presence-connections.md) |
| Compact required-user inventory summary | [Fields and state rules](reference/required-users-summary.md) — [local qualification/main update](history/required-users-summary-checkpoint-2026-11-06.md) |
| Review required user identities | [Screen and field map](reference/required-users-screen.md), [local runbook](how-to/required-users-runbook.md) |
| Canonical domain/user identities and ER | [Binding field guide](reference/managed-object-bindings.md) |
| Implemented fields, API behavior and limits | [Reference guides](reference/README.md) |
| Directory return and destructive consent correction | [Current source contract](reference/organization-workflows.md#destructive-consent-and-directory-return-correction--source-checkpoint) — locally qualified; main preview updated, live OCI pending |
| Review/test/operator procedures | [How-to guides](how-to/README.md) |
| Accepted engineering decisions | [D1–D17](decisions/engineering-review-decisions.md), [D18–D58](decisions/design-decisions.md) |
| Diagram source and generated views | [Architecture diagrams](architecture/diagrams/README.md) |
| GitHub checkpoints and CI definitions | [Checkpoint workflow guide](how-to/github-checkpoints.md), [required backend lane partition](engineering-test-plan.md#complementary-backend-test-lanes) |
| All pending real-OCI manual qualification | [Live test manifest](how-to/real-oci-test-manifest.md) |
| Pending real-OCI drift and repair validation | [Manual checklist and automated coverage](how-to/configuration-drift-runbook.md#pending-real-oci-manual-validation) |
| Required quality/security conventions | [Testing](engineering-test-plan.md), [security](security-review-policy.md), [code documentation](code-documentation-policy.md), [UI review](ui-ux-review-policy.md) |
| Visual and interaction authority | [UI baseline](../DESIGN.md), [screen authority](ui-screen-authority.md) |
| Former-owner retention/removal qualification | [Current workflow](reference/organization-workflows.md), [dated receipt](history/ownership-disposition-checkpoint-2026-11-07.md) |
| Saved costs and user results | [Read compatibility and persistence](reference/README.md), [qualified fix](history/persisted-read-compatibility-checkpoint-2026-11-07.md) — membership changes retain compatible dated database observations |
| Confirmed missing required-user notices | [Incident/routing model and full field dictionary](reference/required-user-alerts.md), [qualified checkpoint](history/required-user-alerts-checkpoint-2026-11-07.md) |
| Local build cadence | [Targeted UI checks, full milestone/PR gates and the 15-minute budget](engineering-test-plan.md#current-local-cadence-and-integration-budget--9-november-2026) |
| Prior checkpoints | [Dated history](history/README.md) |

## Source of truth

[Selected credential security design](engineering-design/22-credential-security-lifecycles.md):
recovery-only MFA exemption with configurable console CIDRs and 30-day automation-key retirement.
User-selected design; local policy checks and perimeter-only repair are qualified. Remaining
credential flows and live OCI qualification remain pending.

Current [manual required-user checks](reference/user-presence-checks.md) connect the internal presence
boundary, exact identity mappings and one selected simulated connection to asynchronous acquisition
and dated per-account results. Local qualification and the main-preview upgrade pass with all existing data preserved; [the dated receipt](history/manual-presence-checkpoint-2026-11-06.md) records the complete results and unchanged parallel preview. Live OCI presence, permissions and credentials remain unqualified.

Earlier checkpoints remain historical context: [internal boundary](history/required-user-presence-checkpoint-2026-11-06.md),
[onboarding capture](history/onboarding-user-capture-checkpoint-2026-11-06.md),
[canonical bindings](history/managed-identity-bindings-checkpoint-2026-11-06.md),
[identity-record screen](history/required-users-screen-checkpoint-2026-11-06.md) and
[connection foundation](history/presence-connection-checkpoint-2026-11-06.md). Their earlier no-check
statements do not supersede the current check reference or qualify actual OCI behavior.
Current configuration work includes [guarded selected-object repair](reference/configuration-repair.md)
through the existing durable operation worker, with [all-category/override regression coverage](reference/configuration-repair.md#all-category-repair-qualification--6-november-2026). Its [local checkpoint](history/configuration-repair-checkpoint-2026-11-06.md)
records qualification and remaining deployment boundaries.


The [provider file-separation decision](engineering-design/02-operations-and-provider.md#provider-contract-and-implementation-files--5-november-2026)
records the contract/simulator/real-adapter layout. The [implemented provider layout](reference/provider-layout.md)
describes the extracted files and qualification limits.

Application source, frozen migrations and qualified tests describe implemented behavior. Python
models and validators generate backend/contracts/ and frontend types; exported schemas do not encode
every cross-field or transaction rule. Reference guides explain these boundaries. Engineering chapters
and accepted decisions also describe future OCI/hosting capabilities; a design approval is not runtime
qualification. Static walkthroughs illustrate their declared design subset and do not override the
current React implementation. The retained prototype has its own local-only authority and contracts.

Private evidence and HR inputs are intentionally not distributed. Public validation requirements
must not depend on those files. The bounded [C5 static-contract receipt](contracts/receipts/c5-contract-checks-2026-10-28.json)
is retained for reproducible contract checking, not as production/provider certification.


## Documentation directory contents

| Subdirectory | Contents |
| --- | --- |
| [product/](product/) | Product scope and acceptance criteria |
| [engineering-design/](engineering-design/README.md) | Approved architecture, journeys and future qualification boundaries |
| [reference/](reference/README.md) | Implemented API/model/settings reference |
| [how-to/](how-to/README.md) | Setup, development and manual/operator review procedures |
| [architecture/](architecture/README.md) | Architecture [diagram sources and generated views](architecture/diagrams/README.md) |
| [decisions/](decisions/README.md) | Accepted engineering decisions and supersessions |
| [contracts/](contracts/README.md) | Proposed design contracts, [examples](contracts/configuration-examples/) and [reviewed receipts](contracts/receipts/) |
| [walkthroughs/](walkthroughs/README.md) | Static illustrations of declared design flows |
| [history/](history/README.md) | Dated checkpoints and development records |

When adding, moving or removing documentation, update this table and the affected section indexes
in the same change. Each intentional subdirectory must remain discoverable; generated/private
outputs are not an excuse to leave a broken public link.

## Cost-visibility milestone

The [implemented current-month cost reference](reference/cost-visibility.md) covers the unified
Tenancies dashboard, durable reads, two financial tables, failure emails and deferred staging schedule.
See the [implemented ER](architecture/diagrams/financial-implemented.mmd) and
[manual cost test runbook](how-to/test-cost-visibility.md).

Financial validation and saved-data preservation: [5 November checkpoint](history/cost-visibility-checkpoint-2026-11-05.md).

Cost-refresh audit regression coverage: [Audit history](reference/audit-history.md#cost-collection-worker-events).

Root manager naming and paired settings controls are specified in the
[implemented Organization Mapping guide](reference/organization-mapping.md#root-manager-display-name).

Current directory-return and destructive-consent qualification: [6 November checkpoint](history/employee-restoration-consent-checkpoint-2026-11-06.md).

Normal-directory onboarding without provisioning: [Keep in organization without a tenancy](reference/organization-workflows.md#keep-in-organization-without-a-tenancy).

- [Keep in organization without a tenancy: local qualification and preserved main preview](history/keep-without-tenancy-checkpoint-2026-11-07.md)

Member management and provider refresh labels: [shared member entry](reference/organization-workflows.md#add-a-member-from-a-shared-tenancy), [required-user refresh](reference/required-users-screen.md#consistent-provider-refresh-terminology--7-november-2026).

- [Shared-member entry and single provider refresh: final qualification and main preview](history/shared-members-refresh-checkpoint-2026-11-07.md)

Compact create/import help: [Collapsed OCI operator checklist](reference/tenancy-onboarding.md#collapsed-oci-operator-checklist).

- [Compact operator help and consistent action emphasis: qualification and main preview](history/compact-help-action-emphasis-checkpoint-2026-11-07.md)

Owner retention, verified identity removal and manual cleanup: [explicit former-owner disposition](reference/organization-workflows.md#explicit-former-owner-disposition--7-november-2026).

- [Recovery console checks, private setup evidence and remaining credential milestone](reference/recovery-console-verification.md): private CIDR settings, exact setup capture, independent policy/presence UI results and remaining custody/rotation work.

- [Manual recovery-policy UI checkpoint](how-to/recovery-policy-ui-checkpoint.md): exercise separate presence/MFA/network results and stored refresh behavior in local simulation.

- [Recovery-policy UI qualification — 7 November](history/recovery-policy-ui-checkpoint-2026-11-07.md):402 complete integration cases, independent reviews and main-only preserved publication.

The [required-user presence reference](reference/required-user-presence.md#responsive-tenancy-detail-layout)
and [design baseline](../DESIGN.md#tenancy-detail-density--9-november-2026) describe the compact,
responsive tenancy detail layout for laptop and mobile screens.

The [UI review policy](ui-ux-review-policy.md#whole-page-section-rhythm--9-november-2026)
requires full-page spacing checks alongside cropped panel reviews.

- [Required-user administrator assignments](reference/administrator-assignments.md): scoped simulated group/role checks, evidence fields and local review.

- [Automation assignment UI checkpoint](history/automation-assignments-ui-checkpoint-2026-11-09.md): final qualification receipt and saved-preview preservation.

The [compact checked-date policy](ui-ux-review-policy.md#compact-checked-date-provenance--9-november-2026)
and [local session defaults](reference/application-settings.md#local-eight-hour-sessions--9-november-2026)
record the date-footer and local-only eight-hour session refinements.

[Saved-preview publication safeguards](reference/local-application.md#saved-preview-publication-safeguards--9-november-2026) cover owned database ports, private backups and qualified asset snapshots.

- [Compact check-date and local-session checkpoint](history/check-date-footer-local-session-checkpoint-2026-11-09.md): qualification and preserved local preview.

The [Recovery overview row](reference/required-users-screen.md#recovery-overview-row--9-november-2026)
records the compact three-fact layout and aligned cost/override header actions.

The [Recovery overview and matching header actions checkpoint](history/check-date-footer-local-session-checkpoint-2026-11-09.md#recovery-overview-and-matching-header-actions) records final responsive qualification and unchanged data/settings.

- [Recovery assignments UI checkpoint](history/recovery-assignments-checkpoint-2026-11-09.md): independent recovery group/role results and compact permission summary.

The backend [implementation overview](../backend/README.md) and current required-user field dictionaries
were reconciled during the whole-milestone publication audit. Historical checkpoint counts retain
their original scope; current application metadata contains 28 OTM tables through migration 0027.

- [Guarded recovery-network repair](reference/recovery-network-repair.md): qualified simulated conditional perimeter-only repair and preserved main preview; live OCI pending.

The [recovery-network repair source subset](reference/recovery-network-repair.md) reuses existing operations, steps, audit and checks. Migration 0026 extends CHECK-constraint branches only; the 25 existing OTM tables were unchanged at that checkpoint. Full local UI/integration qualification and preserved main-preview publication pass; live OCI remains pending.

- [Recovery-network repair final checkpoint](history/recovery-network-repair-checkpoint-2026-11-09.md): 430 complete integration cases, independent reviews and preserved main data/settings.

- [Recovery-password source subset](reference/recovery-password-access.md): explicit simulator, version4 custody handoff and original-window rotation; qualification/install status is in its checkpoint receipt.

- [Recovery-password checkpoint](history/recovery-password-checkpoint-2026-11-09.md):440 clean-tree integration cases, independent reviews and preserved main installation; live OCI pending.

- [Access-panel and historical-check follow-up](history/recovery-password-checkpoint-2026-11-09.md#access-panel-and-recorded-results-follow-up): installed mini-panel layout and exact Operations results; combined438+2 integration evidence is separate from earlier clean440 receipts.

- [Password operation progress follow-up](history/recovery-password-checkpoint-2026-11-09.md#password-operation-progress-follow-up): installed original-window status panel;440 complete cases plus later explicitly targeted-qualified copy.

- [Context-sensitive operation returns](history/recovery-password-checkpoint-2026-11-09.md#operation-return-navigation-follow-up): recognized local origins, durable href context and exact result anchors; targeted validation and preserved main installation pass; no full native rerun.

- [Automation signing-key inventory source checkpoint](reference/automation-signing-keys.md): separate observation-only panel and original-time age; targeted qualification/main installation pass; rotation enforcement separate.

- [Signing-key inventory checkpoint status](history/automation-signing-key-inventory-checkpoint-2026-11-09.md): targeted public metadata/age checkpoint installed; no new full-suite/milestone/PR qualification.
