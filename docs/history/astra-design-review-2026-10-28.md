# Independent Astra design review

28 October 2026 | Both findings addressed and independently rechecked | Final user approval pending

[Finalization checklist](design-finalization-2026-10-28.md) · [Current design](../engineering-design/README.md)

## Scope and result

A separate OpenAI **gpt-6-astra** subagent reviewed the consolidated V1 design read-only, with fresh
review context and no implementation edits, database access or live OCI calls. Scope included
journeys, specification, proposed model/contracts, UI field coverage, prototype reuse, operations
and simplicity. It found no P0/P1 architectural issue and two P2 design inconsistencies.

Astra independently rechecked the bounded corrections and reported **no remaining material design
issue in that correction delta**. It considers the reviewed design suitable for final user approval.
This is independent model review assistance, not external certification or provider qualification.

## Findings and disposition

| Finding | Smallest adequate correction | Disposition / trace |
|---|---|---|
| P2: create required deleting the initial local activation administrator without collecting/binding that account | Add create-only activation administrator user OCID; verify same-child domain/OCI/SCIM identity, preview and explicitly confirm the retirement target; retain operation provenance and protected/replacement/last-admin guards. Imports preserve existing humans | **User accepted D55; fixed and Astra rechecked.** [Spec AC78](../product/oci-tenancy-manager-spec.md), [journey](../engineering-design/07-onboarding-journeys.md#activation-administrator-cleanup-target-d55), [field/storage contract](../engineering-design/11-production-data-model.md#create-only-activation-administrator-binding-d55), SDK/execution chapters08/09, onboarding/Operations forms and planned CX29. Existing intent/binding records suffice |
| P2: candidate open-issue unique constraint omitted coverage-subject identity, contradicting independent automation/recovery incidents | Include `coverage_subject_kind` and `coverage_subject_key` in the open-issue partial unique key; resolve/deduplicate within that exact subject scope | **Fixed and Astra rechecked.** [Chapter10 constraints](../engineering-design/10-configuration-data-model.md#keys-indexes-and-readable-query-projections); planned simultaneous-subject regression in [test policy](../engineering-test-plan.md#astra-final-review-regression-cases--28-october-2026). No new table |
| Minor: current onboarding/Operations still called recovery MFA undecided; configuration check field retained obsolete human-grant ownership | Align current copy with D39/D40 recovery-only exemption and remaining live qualification; remove human-grant access-owner wording | **Fixed and Astra rechecked.** Current walkthroughs and chapters07/10. Historical alternatives stay labeled historical |
| Minor recheck note: scenario catalog note still said28 after adding CX29 | Correct the catalog note to29 unique future runtime scenarios | **Fixed.** Static execution checker verifies unique IDs/count; scenarios are planned tests, not claims of runtime execution |

## Boundaries that remain

Production implementation must prove atomic runner integration, authorization, migrations/indexes,
95% unit-only coverage, disposable PostgreSQL integration and Playwright behavior. Pilot gates still
include OCI permissions/domain behavior, imported-child termination eligibility, recovery password/MFA
scope and verification, Budget source/currency/cycle qualification, SSO/email and measured in-region
restore objectives. These are explicit implementation/integration gates, not unresolved product choices
requiring new V1 architecture. No additional table, service or external recovery journal is recommended.

No commit, push, PR or repository publishing was performed. Whole-package final approval remains with
the user; chapter-level approvals and this review do not grant that approval automatically.
