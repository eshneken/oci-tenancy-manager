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
The recovery/access milestone adds [conditional recovery-network repair](docs/reference/recovery-network-repair.md),
[audited recovery-password access and original-window rotation](docs/reference/recovery-password-access.md),
and [managed signing-key rotation](docs/reference/signing-key-rotation.md) with observed key inventory;
all provider effects remain explicitly simulated. [Operations type filters](docs/reference/operations.md#operation-type-filtering--10-november-2026)
help find the recorded work. Dated checkpoint receipts keep their original test/publication scope.
[Manual required-user presence checks](docs/reference/user-presence-checks.md) are locally qualified; the main preview is upgraded with existing data preserved. The [dated receipt](docs/history/manual-presence-checkpoint-2026-11-06.md) distinguishes simulation and its original test lanes. The parallel preview was later retired;
8443 is now the sole saved review instance.
Real OCI integration, corporate SSO and managed-service deployment remain separately unqualified.
Daily drift scheduling is deferred until staging/Kubernetes deployment. All five hosted CI jobs and
administrator-enforced protected `master` are verified at baseline `db08b3b`; development uses
[one PR per completed milestone](docs/how-to/github-checkpoints.md), grouping its related slices.

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
