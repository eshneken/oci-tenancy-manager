# Architecture diagrams

## Complete application views — 12 November 2026

- **[OCI deployment](oci-deployment.svg)** ([PNG](oci-deployment.png), [Mermaid](oci-deployment.mmd), [Excalidraw](oci-deployment.excalidraw)): OKE, OCI Database with PostgreSQL and Vault context. Nested export is one SVG for annotation.
- **[Logical software architecture](logical-architecture.svg)** ([PNG](logical-architecture.png), [Mermaid](logical-architecture.mmd), [Excalidraw](logical-architecture.excalidraw)): components/data flows with simulated and OCI adapters explicitly separated. Scene is element-editable.
- **[Complete implemented ER source](implemented-full-er.mmd)** ([SVG](implemented-full-er.svg), [PNG](implemented-full-er.png)): 34 tables/439 columns/89 foreign keys through freshly reflected migration0029, including native queue and migration tables. SVG/PNG regenerated17 November with pinned Mermaid CLI12.2.0 and visually reviewed; asset publication review remains separate. [Table responsibilities and every column](../implemented-database.md).

The ER source metadata was re-reflected on 17 November from a freshly migrated empty disposable
PostgreSQL database through0029, confirming439 columns including nullable `imported_access`.
The earlier438-column reflection at `786f83b` remains historical. No saved organization data or
row values were inspected. It does not fold proposed production entities or prototype
tables into the implemented schema. Existing feature diagrams below retain their own scope labels.


Mermaid files are editable sources. Companion SVG/PNG files are generated views; Excalidraw files
are auxiliary editing/annotation artifacts and may embed a rendered image rather than editable
entity cells. Regenerate views after changing a source. A diagram never substitutes for frozen
migrations or Python validation.

## Implemented local subsets

- [financial-implemented](financial-implemented.mmd): exact collection/observation scope and reused operations/outbox.
- [user-presence-connections-implemented](user-presence-connections-implemented.mmd) — [all 14 fields and limits](../../reference/user-presence-connections.md)
- [user-presence-checks-implemented](user-presence-checks-implemented.mmd) — all 14 check columns; context connection/subject references remain typed JSON, not invented SQL FKs
- [managed-identities-implemented](managed-identities-implemented.mmd) — [SVG](managed-identities-implemented.svg), [field guide](../../reference/managed-object-bindings.md); Excalidraw is an image annotation export
- [baseline-authoring-implemented](baseline-authoring-implemented.mmd)
- [configuration-drift-implemented](configuration-drift-implemented.mmd)
- [configuration-updates-implemented](configuration-updates-implemented.mmd)
- [lifecycle-email-implemented](lifecycle-email-implemented.mmd)
- [organization-snapshots-implemented](organization-snapshots-implemented.mmd)
- [organization-workflows-implemented](organization-workflows-implemented.mmd)
- [tenancy-overrides-implemented](tenancy-overrides-implemented.mmd)

Each diagram is scoped to the feature/checkpoint named in its source; it is not a separate complete
inventory of every current table. See [the current model](../../engineering-design/11-production-data-model.md)
and its runtime guide links for the whole implementation boundary.

Both organization-workflows and complete ER Mermaid sources include the migration0029 source
column. It stores [initial adoption provenance](../../engineering-design/24-imported-membership-adoption.md),
not secrets or a second writable user registry. Fresh full-schema metadata reflection and exact table/column name-set checks passed; the complete
ER exports were regenerated and visually reviewed on17 November. Privacy/provenance review must
precede publication-manifest hash updates.
The [separate saved8443 publication](../../engineering-design/24-imported-membership-adoption.md#scoped-local-development-risk-acceptance-and-follow-up) applied0029 under scoped local dependency-risk acceptance with preserved data/settings.
Hosted security gates remain required with the [exact approved exception](../../reference/frontend-security-exception.md) and real OCI Pending; reflection alone does not establish
those runtime/provider outcomes.

## Proposed production model

- [application-administrators-proposed](application-administrators-proposed.mmd)
- [configuration-data-model-proposed](configuration-data-model-proposed.mmd)
- [production-core-access-proposed](production-core-access-proposed.mmd)
- [production-finance-proposed](production-finance-proposed.mmd)

Proposed fields and relationships require implementation/provider qualification before they become
runtime guarantees. The earlier prototype diagrams are retired; use the current implemented diagrams above.

Ownership retention/removal reuses the existing membership role/status/identity/cleanup fields and
immutable operation JSON. Physical ER relationships are unchanged; [the exact additional DTO mapping](../../engineering-design/11-production-data-model.md#explicit-ownership-retentionremoval--7-november-2026)
explains the new choice and legacy compatibility.

Required-user alert incidents add [typed JSON evidence and outbox fields](../../reference/required-user-alerts.md#fields-and-persistence), without changing physical ER tables/relationships.

- [Recovery-password source ER](recovery-passwords-implemented.mmd): migration0027 physical subset with three new tables; qualification/install status belongs to the separate password checkpoint receipt. Editable source only; no rendered export is claimed yet. [Field dictionary](../../reference/recovery-password-access.md#physical-field-dictionary).

Signing-key inventory adds [typed JSON evidence/views only](../../reference/automation-signing-keys.md#field-dictionary-and-existing-persistence); the physical ER is unchanged and no API-key custody head is introduced.

- [Signing-credential candidate source ER](signing-credentials-implemented.mmd): one new head in 0028 plus existing operations/audit/connection/binding/outbox relationships; targeted local qualification/saved installation PASS; full-suite/PR/live Pending. [All fields](../../reference/signing-key-rotation.md#physical-field-dictionary). Source only; no rendered export claimed.
