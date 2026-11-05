# Architecture diagrams

Mermaid files are editable sources. Companion SVG/PNG files are generated views; Excalidraw files
are auxiliary editing/annotation artifacts and may embed a rendered image rather than editable
entity cells. Regenerate views after changing a source. A diagram never substitutes for frozen
migrations or Python validation.

## Implemented local subsets

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

- [financial-implemented](financial-implemented.mmd): exact collection/observation scope and reused operations/outbox.
