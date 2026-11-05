# OCI Tenancy Manager

An administrator-operated application for OCI child-tenancy lifecycle, organizational accountability
and managed configuration. The current Python/React application runs locally with real authentication,
PostgreSQL persistence and durable workers; OCI lifecycle and configuration adapters are simulated.

Start with the [documentation home](docs/README.md), [local application setup](docs/reference/local-application.md)
and [engineering design](docs/engineering-design/README.md).

The implemented local application includes Organization intake/mapping/reviews, individual/shared
Tenancies, guided onboarding and deletion, immutable administrative Audit History and CSV export,
Operations, administrator responsibility takeover, baseline publication/overrides/updates, read-only
configuration-drift checks, and lifecycle email with safe nonproduction routing and local capture.
Real OCI integration, corporate SSO, managed-service deployment and hosted CI remain separately
unqualified. Daily drift scheduling is deferred until staging/Kubernetes deployment.

| Location | Authority |
| --- | --- |
| [docs/](docs/README.md) | Product scope, current design, developer references and operating procedures |
| [backend/](backend/README.md) | Python application and frozen database migrations |
| [frontend/](frontend/README.md) | React application and generated TypeScript contracts |
| backend/contracts/ | Generated schema snapshots; Python validation remains authoritative |
| [prototype/](prototype/README.md) | Retained local organization lab; not current application authority |

Follow [the test/merge policy](docs/engineering-test-plan.md), [security review policy](docs/security-review-policy.md),
[documentation convention](docs/code-documentation-policy.md) and [UI baseline](DESIGN.md).
Runtime state, original feeds, credentials and unsanitized evidence remain private and ignored.
No default administrator account is created; enrollment happens privately through an explicit
operator procedure. Repository cleanup does not qualify a production deployment.
