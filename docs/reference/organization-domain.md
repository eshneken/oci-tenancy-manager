# Organization intake and reconciliation domain

30 October 2026 · Production extraction of tested organization behavior

[Production data model](../engineering-design/11-production-data-model.md) ·
[Domain and journeys](../engineering-design/01-domain-and-journeys.md) ·
[Preserved prototype](../../prototype/README.md)

The subsequent [authorized storage slice](organization-storage.md) now persists these domain
results. This guide describes the pure functions; storage transactions, guards and source maps
are documented separately. CSV/screens are integrated; durable review/association coordination is implemented in the separately documented workflow milestone.

## Implemented scope

`backend/src/otm/organization` contains the production copies of the reusable organization-domain
logic: canonical contracts, strict CSV intake, pure graph reconciliation and review-condition
fingerprints. The code and tests do not import the prototype package, private feeds, local actors,
local web server, persistence adapters or simulated tenancy-success actions. The original pure extraction added no database migration, HTTP route, CLI command, permission grant or OCI call. Subsequent authorized storage/screens and the current parity coordination are separate from these pure functions. The separate prototype remains available for existing demonstrations.

The extraction preserves the accepted behavior rather than introducing another organization model.
Prototype-only review simulation fields and unused local registry initialization/onboarding flags
are omitted. Production association/workflow coordination must supply those facts through its
approved persisted authorities, not a prototype configuration boolean.

## CSV intake boundary

`parse_csv(bytes)` accepts UTF-8 (optional BOM), exactly four headings in any order/case with
heading whitespace trimmed: `EMPLOYEE_FULL_NAME`, `EMAIL`, `MGR`, `TOP_MGR`. It handles CSV quoting
and Unicode names, normalizes email case/outer whitespace and retains the full name without
guessing first/last-name parts. Manager/top-manager hints may be empty. Manager requiredness and
reporting-graph validation occur in reconciliation, not in CSV syntax parsing.

Reject malformed encoding/CSV, null characters, missing/duplicate/extra headings, wrong column
counts, invalid names/emails, duplicate normalized employee emails, empty populations, more than
5,000 nonempty employee rows, or more than 2 MiB of raw content. Blank rows are ignored.
`read_csv(path)` reads at most the limit plus one byte before applying the same parser. Safe CSV
errors describe the shape/line, not raw cell contents. Canonical-model exceptions are configured
not to include input values in their string representation; callers must still never log raw
exception dictionaries, intakes or employee profiles indiscriminately.

CSV email keys are represented as `email:<normalized-email>` in `source_record_id`. This is
provenance, not a stable employee identifier or permission to merge identities. Both name and
email changing produces separate identities until an explicitly verified one-way identity remap.

`csv_intake(content, policy, captured_at=..., complete=...)` first parses content, then returns a
canonical `Intake` and the source-byte SHA-256 digest. Each call creates a new delivery identity,
even when the bytes match an earlier upload. A transport retry must retain and reuse the original
returned intake/envelope; call this helper again only for a genuinely new delivery. Hash equality
is evidence, never a global duplicate-upload suppression rule.

The caller supplies server-owned source/population policy and independently qualified source
capture time. The helper does not infer trusted freshness/completeness from CSV headings, file
names, upload time or browser input. Unknown capture time remains unknown. Upload authority, body-size enforcement while streaming, transport idempotency and persistence
are separate service boundaries, not provided by this pure helper; their implemented subset is
described in the organization screen/storage guides.

## Reconciliation and fields

`prepare(records, envelope, configuration, previous_revision, observed_at)` returns a `Candidate`.
It never persists, sends mail, changes tenancy associations or calls OCI. Important field sources:

| Candidate/person field | Meaning and source |
| --- | --- |
| `expected_head_id`, `expected_configuration_id` | Exact organization/configuration inputs; later publication must compare them atomically. |
| `people[].id` | Stable UUID retained from prior state or a verified one-way merge; new identities receive UUIDs. |
| `full_name`, `email`, `manager_email`, `reported_top_manager_email` | Normalized source metadata, with explicit trusted name/manager corrections and alias rules. Top-manager hint never overrides graph truth. |
| `source_values`, `source_record_id` | Retained source facts/provenance, distinct from corrected effective values. |
| `profile` | `employee` for an actual row, `reference` for a manager/hint-only identity, `configured` for policy-created placeholders. |
| `manager_provenance`, `known_manager` | Feed or explicit correction/edge evidence; manager status is retained for later deletion warnings. |
| `manager_path`, `ancestry` | Direct-manager-first path, excluding self; `root`, `resolved`, or `incomplete`. Missing profiles cannot be invented from hints. |
| `lob_id`, `accountable_leader_email`, `designee_emails` | Derived from validated reporting paths and explicitly configured LOB leaders/designees; source data does not nominate designees. |
| `last_row_observed_at`, `last_reference_observed_at` | Positive observation evidence, kept separately. A reference is positive presence but not a received employee profile. |
| `last_source_capture_at`, `last_qualified_census_at` | Source time versus last qualified complete-census time. |
| `absence_review`, `absence_review_since` | Persistent unresolved departure-review flag and episode key; never an instruction to delete. |
| `diagnostics`, `rejected` | Input/graph findings; any fatal diagnostic makes publication unsafe. |
| `assessed_coverage`, `absence_eligible` | Derived coverage classification and the stricter permission to infer absence. |
| `issues`, `employee_row_emails` | Current graph/review findings and actual employee-row keys, for future persisted recommendation projection. |

Source scope, metadata permission, UTC-aware observation time, capture freshness/order, duplicate
identity keys, missing required manager edges, explicit-edge conflicts and reporting cycles are
checked before publication can be considered. Retained prior profiles do not complete a gapped
new census. Iterative graph walks avoid recursive depth limits; memoized paths retain direct-manager
ordering. Missing managers remain visible placeholders and block absence inference.

Absence requires trusted authority plus a confirmed census contract, fresh known capture time,
complete declaration, all required profiles, rooted incoming paths and no fatal diagnostics.
Partial/unconfirmed/stale/undated inputs cannot invent departures. The inherited trusted
`allow_undated_development_metadata` compatibility option permits only non-authoritative metadata
review; it cannot be combined with authoritative census policy. No production route enables it.

An unresolved absence persists on later feeds even if the person returns, until an explicit
reviewed decision. Settling continuous absence does not reopen it on every missing feed. Positive
return evidence clears the settled episode key; a subsequent genuine departure opens a new review
without replacing the person's UUID. An excluded email cannot silently re-enter a publishable effective graph. References to an
excluded identity from reporting edges or top-manager hints produce fatal
`EXCLUDED_IDENTITY_REFERENCED` diagnostics, including references retained during a partial feed.
Saved leader/designee nominations instead remain visible as ineligible role defects; they never
recreate an excluded profile or authorize routing. Both exclusions and references are compared through the complete verified email-alias
chain; an old email cannot reintroduce its excluded renamed identity. Rejected candidates may contain temporary placeholders solely to complete safe graph
diagnostics; they are not a valid organization or new identity authority. Operators must correct
incompatible references/configuration or explicitly return the person before publication. Future
production return handling must clear the removal marker explicitly under the approved association
rules. Source/historical identity remains intact.

## Review rules and remaining coordination

`review_rules` separates actionable kinds (absence, setup, LOB mapping/leader, designee and
organization override conflict) from informational kinds (top-manager mismatch, missing manager
profile, unresolved ancestry). It computes fingerprints for conditional closure and supports
permanent ignore. Changed relevant facts reopen conditional review; a permanent ignore remains
suppressed. Managed-directory exclusions do not hide unrelated designee-integrity problems.
Informational mismatch findings disappear from the current candidate after corrected source data;
persisting their dated history belongs to the later repository/projection.

The pure candidate does **not** generate a complete actionable UI queue: setup requirements depend
on persisted tenancy/member associations, and metadata history/durable recommendation recurrence
depend on snapshots and review storage. These remain later production work. Review closure on
tenancy workflows must happen at durable operation acceptance; this module supplies no pretend
success. Association retirement/removal/return, merge of tenancy memberships, compare-and-publish
transactions, raw-feed custody, authorization and immutable audit are not completed by pure tests.

## Verification

The production suite includes ported synthetic reconciliation/CSV cases plus additional scenario
coverage for metadata/reorg identity retention, repeated absence/closure/return/redeparture,
explicit email merge and retired email rejection, condition versus permanent suppression, source
trust/freshness, manager gaps, designee changes, corrected top-manager hints, CSV boundaries and
new-delivery versus transport-retry identity. No private workbook or employee names are required.
Run from the repository root:

```sh
uv run --project backend pytest backend/tests/test_organization_*.py -q
uv run --project backend python scripts/check_unit_coverage.py
```

Pure unit coverage is measured as part of the full production source gate. It is not proof of
database locking, publication transactions, real provider execution or UI integration.


## Production screen integration

The [Organization screen/API guide](organization-screens.md) covers the authenticated CSV adapter,
immutable snapshot directory and current drift/last-feed change projection. It reuses this domain's
issues rather than duplicating graph rules. Association-aware setup reviews, durable recommendations
and review/identity-merge commands remain later production work. Pure tests still do not qualify
provider behavior; the separate real PostgreSQL/HTTPS/Playwright suite tests this implemented boundary.

## In-progress workflow coordination

[The workflow parity guide](organization-workflows.md) now describes authored durable reviews,
stable-person managed controls and simulated lifecycle acceptance/publication. The pure module's
limitations remain: it does not itself authorize, persist associations or prove provider effects.
Persisted orchestration reuses its identities, coverage and conditional-review rules. Final testing
and real OCI qualification are separate; do not infer them from the pure reconciliation tests.

## Mapping-only recalculation and independent roles

`configuration_only=True` is distinct from source freshness permission `trusted_reapply`. It cannot
refresh clocks or create absence/return/onboarding episodes from reused evidence. Newly recorded
administrator decisions may settle their own absence in a working copy; unchanged historic
suppressions do not change flags during mapping edits. Every configured nomination is evaluated
independently of employee tenancy associations, generic review acknowledgment and valid leadership.
[The mapping guide](organization-mapping.md) documents the role states and regression matrix.
