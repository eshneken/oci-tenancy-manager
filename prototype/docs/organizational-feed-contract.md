# Organizational feed contract

Generic adapter/reference contract for the retained local organization prototype. This document
contains no private HR export, employee analysis or production source certification. Current
application behavior is described in [the organization reference](../../docs/reference/organization-domain.md).

## 1. Source profile and delivery evidence

Configure the source/population, schema profile, root email, capture time and completeness evidence
independently of employee rows. Receiving a file is not proof that it is a current complete census.
The public regression fixtures are invented; original workbooks and exports remain private.

## 2. Expected fields and normalization

The CSV adapter accepts EMPLOYEE_FULL_NAME, EMAIL, MGR and TOP_MGR. The workbook adapter may map
ID, ECA_NAME, ECA_EMAIL, ECA_MANAGER, ECA_MANAGER_EMAIL, ECA_TOP_MGR_DIR_MINUS_3 and ENG_TERRITORY.
Select fields by configured headers, never row order, formatting or a private sample's row count.

| Concept | Rule |
| --- | --- |
| Email | Required matching key; trim/case-normalize consistently, preserve source evidence and reject duplicate normalized rows. No alias guessing. |
| Name | Preserve a full display name; do not invent first/last names by splitting spaces. |
| Manager | Resolve the direct-manager email; names are labels, not relationship keys. |
| Top-manager hint | Preserve separately; cross-check derived accountability without inventing a direct edge. |
| Source record ID | Source-scoped evidence until immutable identity semantics are qualified; never silently merge changed emails. |
| Territory/classification | Optional source evidence; never overrides administrator-configured LOB/designees. |

Reject malformed identity fields, conflicting duplicates, missing required headers and formula-based
identity values. Blank optional labels do not justify deleting a person.

## 3. Internal organization records

Stable internal UUIDs carry identity, management and tenancy history. Source rows and immutable
versions are separate from administrator decisions and tenancy associations. Explicit alias/merge
workflows preserve prior UUID provenance; fuzzy name matching is not automatic identity transfer.

## 4. Hierarchy construction

Reconstruct manager edges by normalized email, retaining reference-only profiles for unresolved
managers. Detect cycles, missing manager profiles, conflicting edges and paths outside the configured
root. Do not interpret a referenced-only manager as a complete employee row. Missing evidence blocks
qualified absence conclusions rather than manufacturing departures.

## 5. LOBs, territory and designees

Administrators configure the root, LOB leader and designee mappings. Derived ancestry follows manager
edges; classification hints do not choose leaders or designees. Validate configured role identities
and surface unresolved/excluded role defects. The source graph and managed-person visibility remain
separate so exclusions do not destroy history or reporting references.

## 6. Automatic synchronization and absence handling

Valid metadata may publish automatically under the configured policy. Absence requires a later,
qualified complete census with compatible source/population and capture order. Missing people stay
visible for explicit review; the feed does not prove departure from the employer or authorize OCI
deletion. Preserve sticky absence and explicit exemption/return semantics.

### Publication and recovery (D5 accepted)

Publish coherent immutable versions atomically. Keep received/staged evidence separate from applied
heads; conflicting deliveries or stale context cannot replace a current head. Retry exact delivery
identities safely; a new later capture of equal content is new evidence, not the same delivery.

## 7. Delivery metadata and remaining source questions

Production source delivery, immutable employee identifiers, full-population guarantees and broader
organization boundaries require independent qualification. No private sample establishes them.
The prototype may use explicitly non-authoritative development policy; production must retain its
source and authority guards.

## 8. Acceptance scenarios to add

Maintain synthetic tests for duplicate/case-varied emails, reference-only managers, cycles, partial
feeds, capture ordering, unchanged content at later captures, explicit merges, role departures,
qualified absence/return, configuration-only reapply and transaction rollback. Unit tests prove
policy; disposable PostgreSQL tests separately prove storage/atomicity.

## 9. Missing manager profiles to investigate

Report unresolved manager identities to an administrator using scoped diagnostics. Do not publish a
private employee roster in documentation. Fixtures should invent the entire graph and use reserved
example/test contacts; source-profile gaps remain evidence-quality issues until resolved.
