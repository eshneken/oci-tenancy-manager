# Documentation

Use this index for the current application. Historical checkpoints explain past decisions; they
are not competing implementation instructions or proof of real OCI behavior.

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
| Prior checkpoints | [Dated history](history/README.md) |

## Source of truth

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
