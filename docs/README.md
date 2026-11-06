# Documentation

Use this index for the current application. Historical checkpoints explain past decisions; they
are not competing implementation instructions or proof of real OCI behavior.

| Need | Start here |
| --- | --- |
| Product scope and acceptance criteria | [Product specification](product/oci-tenancy-manager-spec.md) |
| Current architecture and approved future design | [Engineering design](engineering-design/README.md) |
| Run the application | [Local HTTPS setup](reference/local-application.md) |
| Implemented fields, API behavior and limits | [Reference guides](reference/README.md) |
| Review/test/operator procedures | [How-to guides](how-to/README.md) |
| Accepted engineering decisions | [D1–D17](decisions/engineering-review-decisions.md), [D18–D58](decisions/design-decisions.md) |
| Diagram source and generated views | [Architecture diagrams](architecture/diagrams/README.md) |
| GitHub checkpoints and CI definitions | [Checkpoint workflow guide](how-to/github-checkpoints.md) |
| Pending real-OCI drift and repair validation | [Manual checklist and automated coverage](how-to/configuration-drift-runbook.md#pending-real-oci-manual-validation) |
| Required quality/security conventions | [Testing](engineering-test-plan.md), [security](security-review-policy.md), [code documentation](code-documentation-policy.md), [UI review](ui-ux-review-policy.md) |
| Visual and interaction authority | [UI baseline](../DESIGN.md), [screen authority](ui-screen-authority.md) |
| Prior checkpoints | [Dated history](history/README.md) |

## Source of truth
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
