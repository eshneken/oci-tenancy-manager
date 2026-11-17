# Architecture

[Documentation home](../README.md) · [Application overview](../../README.md)

| View | Scope |
| --- | --- |
| [OCI deployment (SVG)](diagrams/oci-deployment.svg) | OKE, managed PostgreSQL and Vault context. |
| [Software/data flows (SVG)](diagrams/logical-architecture.svg) | Application components, durable work and explicit simulated/OCI provider separation. |
| [Complete implemented ER source](diagrams/implemented-full-er.mmd) | 34 public tables, 439 columns and 89 declared foreign keys through freshly reflected migration0029; [SVG](diagrams/implemented-full-er.svg)/PNG regenerated and visually reviewed on17 November with pinned Mermaid CLI12.2.0. |
| [Implemented table/column directory](implemented-database.md) | Human-readable responsibilities, exact PostgreSQL types, keys and relationships. |
| [Focused diagrams and editable sources](diagrams/README.md) | Feature subsets, sources and generated views with implemented/proposed labels. |

The [table directory](implemented-database.md) records the 17 November fresh empty-database reflection
through migration0029 and its nullable membership JSONB addition. The separately verified
[saved8443 local publication](../engineering-design/24-imported-membership-adoption.md#scoped-local-development-risk-acceptance-and-follow-up) applied0029 under explicit local risk acceptance; hosted security gates remain required, with the [exact advisory exception](../reference/frontend-security-exception.md)
and live OCI Pending. No new table or foreign key was added. Current full ER SVG/PNG match the439-column reflected source;
asset privacy/provenance review precedes publication-manifest updates.

The hosting tenancy/compartment need not be the managed parent tenancy. The OCI context view is a
logical target, not evidence that services are running. Terraform foundations, scoped workload IAM,
held Kubernetes manifests and hosted startup seams are implemented source. Full credential/service
launch composition, delivery activation and live qualification remain separate work; see [platform and delivery](../engineering-design/06-platform-and-delivery.md) and
the [live-OCI qualification manifest](../how-to/real-oci-test-manifest.md).

The OCI context view describes one environment's layout. [Staging and production](../engineering-design/24-environments-and-promotion.md)
each have their own instance of that layout, separate OCI parent/child tenancies and isolated
hosting, databases, Vault, Terraform state and identities. The shared delivery pipeline builds once,
qualifies the exact release in staging and promotes those immutable artifacts to production.

The complete ER was reflected from a freshly migrated disposable PostgreSQL database; it includes
native Procrastinate coordination tables and Alembic's migration marker. Source and frozen migrations
determine actual runtime storage. [Engineering chapters](../engineering-design/README.md) describe
current and planned behavior; proposed future entities are not implied to exist in the database.

Architecture flowcharts have Mermaid sources and Excalidraw exports. The logical component scene
is element-editable; the nested OCI export contains a single SVG for annotation. Edit diagram
Mermaid sources to change structure, then re-render. Screenshots use public synthetic fixtures and
are documented in [screenshot provenance](../screenshots/README.md).


## Laptop with real OCI — 14 November 2026

[Development topology](../how-to/laptop-oci-development.md): local API/workers and Rancher PostgreSQL may use a named API-key profile to reach a development Vault and registered children under the non-production parent. Hosted staging uses its own sibling compartment, platform, Vaults, database and children with OKE workload identity. There is no shared application database or cross-environment inventory service; production remains isolated. The full live adapter/launcher composition is still pending.
