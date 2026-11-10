# Architecture diagrams

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

## Proposed production model

- [application-administrators-proposed](application-administrators-proposed.mmd)
- [configuration-data-model-proposed](configuration-data-model-proposed.mmd)
- [production-core-access-proposed](production-core-access-proposed.mmd)
- [production-finance-proposed](production-finance-proposed.mmd)

Proposed fields and relationships require implementation/provider qualification before they become
runtime guarantees. The retained prototype diagram remains separate in prototype/diagrams/.

Ownership retention/removal reuses the existing membership role/status/identity/cleanup fields and
immutable operation JSON. Physical ER relationships are unchanged; [the exact additional DTO mapping](../../engineering-design/11-production-data-model.md#explicit-ownership-retentionremoval--7-november-2026)
explains the new choice and legacy compatibility.

Required-user alert incidents add [typed JSON evidence and outbox fields](../../reference/required-user-alerts.md#fields-and-persistence), without changing physical ER tables/relationships.

- [Recovery-password source ER](recovery-passwords-implemented.mmd): migration0027 physical subset with three new tables; qualification/install status belongs to the separate password checkpoint receipt. Editable source only; no rendered export is claimed yet. [Field dictionary](../../reference/recovery-password-access.md#physical-field-dictionary).

Signing-key inventory adds [typed JSON evidence/views only](../../reference/automation-signing-keys.md#field-dictionary-and-existing-persistence); the physical ER is unchanged and no API-key custody head is introduced.
