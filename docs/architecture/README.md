# Architecture

[Documentation home](../README.md) · [Application overview](../../README.md)

| View | Scope |
| --- | --- |
| [OCI deployment (SVG)](diagrams/oci-deployment.svg) | Target OKE, managed PostgreSQL and Vault context; planned, not deployed. |
| [Software/data flows (SVG)](diagrams/logical-architecture.svg) | Current application components, durable work and explicit simulated/future provider separation. |
| [Complete implemented ER (SVG)](diagrams/implemented-full-er.svg) | All 34 migrated public tables, 438 columns and 89 declared foreign keys. |
| [Implemented table/column directory](implemented-database.md) | Human-readable responsibilities, exact PostgreSQL types, keys and relationships. |
| [Focused diagrams and editable sources](diagrams/README.md) | Feature subsets, sources and generated views with implemented/proposed labels. |

The hosting tenancy/compartment need not be the managed parent tenancy. The OCI context view is a
logical target, not a network/IAM deployment plan or evidence that services are running. Terraform,
OKE workload composition, managed-service credentials and live adapters still require implementation
and qualification; see [platform and delivery](../engineering-design/06-platform-and-delivery.md) and
the [live-OCI qualification manifest](../how-to/real-oci-test-manifest.md).

The complete ER was reflected from a freshly migrated disposable PostgreSQL database; it includes
native Procrastinate coordination tables and Alembic's migration marker. Source and frozen migrations
determine actual runtime storage. [Engineering chapters](../engineering-design/README.md) describe
current and planned behavior; proposed future entities are not implied to exist in the database.

Architecture flowcharts have Mermaid sources and Excalidraw exports. The logical component scene
is element-editable; the nested OCI and ER exports contain a single SVG for annotation. Edit their
Mermaid sources to change structure, then re-render. Screenshots use public synthetic fixtures and
are documented in [screenshot provenance](../screenshots/README.md).
