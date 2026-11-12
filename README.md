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


## Technology catalog

These are the direct application dependencies and the main development, testing and security tools.
Transitive package inventories and exact versions belong in [the backend manifest](backend/pyproject.toml),
[Python lockfile](backend/uv.lock), [frontend manifest](frontend/package.json) and
[npm lockfile](frontend/package-lock.json). Build/test tools are not all shipped in the runtime image.

### Backend and API

| Technology | How we use it |
| --- | --- |
| [Python](https://www.python.org/) | Backend business logic, provider boundaries, background workers and operator commands. |
| [FastAPI](https://fastapi.tiangolo.com/) | HTTP API routes and integration of validated requests/responses. |
| [Starlette](https://www.starlette.io/) | ASGI middleware, browser/authentication boundaries and static frontend delivery beneath FastAPI. |
| [Uvicorn](https://www.uvicorn.org/) | Runs the Python ASGI web application. |
| [Pydantic](https://docs.pydantic.dev/latest/) | Validates settings, request/response contracts and domain data; produces authoritative JSON Schema. |
| [JSON Schema](https://json-schema.org/) | Describes exported API/domain contract shapes for generated frontend types and consistency checks. |

### Database and durable jobs

| Technology | How we use it |
| --- | --- |
| [PostgreSQL](https://www.postgresql.org/) | Stores organization snapshots, tenancy associations, operations, audit history and durable job state; disposable containers support integration testing. |
| [SQLAlchemy](https://www.sqlalchemy.org/) | Defines database tables and builds parameterized SQL and transactional repository operations. |
| [Psycopg](https://www.psycopg.org/psycopg3/) | PostgreSQL driver, native database communication and connection pools, including Procrastinate connections. |
| [Alembic](https://alembic.sqlalchemy.org/) | Versions and applies frozen database schema migrations. |
| [Procrastinate](https://procrastinate.readthedocs.io/) | PostgreSQL-backed durable queue; Python workers execute asynchronous application operations. |

### Web frontend

| Technology | How we use it |
| --- | --- |
| [React / React DOM](https://react.dev/) | Renders the administrator interface and manages interactive screens. |
| [TypeScript](https://www.typescriptlang.org/) | Type-checks frontend code and the generated backend contracts. |
| [TanStack Query](https://tanstack.com/query/latest) | Fetches/caches API data and coordinates mutations, invalidation and refresh behavior. |
| [TanStack Table](https://tanstack.com/table/latest) | Builds application tables with controlled sorting and pagination. |
| [Vite](https://vite.dev/) and [its React plugin](https://github.com/vitejs/vite-plugin-react) | Development tooling and the production frontend build, including JavaScript/CSS bundling and minification. |
| [Node.js](https://nodejs.org/) and [npm](https://www.npmjs.com/) | Execute frontend build/test tooling and install locked JavaScript dependencies; not required in the final runtime image. |
| [json-schema-to-typescript](https://github.com/bcherny/json-schema-to-typescript) | Generates TypeScript interfaces from backend JSON Schema snapshots. |
| [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped) | Supplies TypeScript declarations for Node, React and React DOM through the direct `@types/*` development packages. |

The interface uses custom CSS following [our design system](DESIGN.md); it does not depend on a
separate CSS component framework. HTML/CSS are web standards rather than additional package dependencies.

### Authentication, cryptography and secure parsing

| Technology | How we use it |
| --- | --- |
| [Argon2-cffi](https://argon2-cffi.readthedocs.io/) | Hashes and verifies the application's local recovery-administrator password. |
| [PyOTP](https://pyauth.github.io/pyotp/) | Implements independent TOTP MFA for that local application administrator. |
| [OpenSSL](https://www.openssl.org/) | Generates/parses local bootstrap RSA keys and development certificates; supports TLS through Python's SSL integration. |
| [PyYAML](https://pyyaml.org/) | Uses safe YAML loading in tooling tests to validate dependency-update configuration. |
| [defusedxml](https://github.com/tiran/defusedxml) | Parses test/coverage XML evidence with protections against unsafe XML features. |

### Testing and quality

| Technology | How we use it |
| --- | --- |
| [pytest](https://docs.pytest.org/) | Backend unit and disposable PostgreSQL integration tests. |
| [Coverage.py](https://coverage.readthedocs.io/) and [pytest-cov](https://pytest-cov.readthedocs.io/) | Measure complete-source, unit-only backend line coverage and enforce the95% gate. |
| [Vitest](https://vitest.dev/) and [V8 coverage](https://vitest.dev/guide/coverage.html) | Frontend unit tests and the separate complete-source95% line-coverage gate. |
| [Testing Library](https://testing-library.com/), [user-event](https://testing-library.com/docs/user-event/intro/) and [jest-dom](https://github.com/testing-library/jest-dom) | Test React behavior through user interactions and accessible DOM assertions. |
| [jsdom](https://github.com/jsdom/jsdom) | Provides a browser-like DOM for frontend unit tests. |
| [Playwright](https://playwright.dev/) / [Chromium](https://www.chromium.org/) | Exercise real browser journeys against disposable application/database environments. |
| [HTTPX](https://www.python-httpx.org/) | Exercises HTTP/ASGI API behavior in backend tests. |
| [Ruff](https://docs.astral.sh/ruff/) | Python linting and formatting. |
| [Mailpit](https://mailpit.axllent.org/) | Captures test/local lifecycle emails without sending them to real recipients. |

### Packaging and local containers

| Technology | How we use it |
| --- | --- |
| [uv](https://docs.astral.sh/uv/) | Manages locked Python dependencies/environments and installs the noneditable backend in the image build. |
| [Hatchling](https://hatch.pypa.io/latest/) | Builds the Python package, including explicitly packaged migration and settings assets. |
| [Docker Engine / Moby](https://mobyproject.org/), [BuildKit](https://github.com/moby/buildkit) and [Buildx](https://docs.docker.com/build/) | Build the multistage image and run owned disposable PostgreSQL/application/scanner containers. |
| [Alpine Linux](https://alpinelinux.org/) / [musl](https://musl.libc.org/) | Selected Linux base/C runtime for both Python build and final runtime stages. |
| [Debian](https://www.debian.org/) | Base of the temporary Node frontend-build stage; not copied into the final Alpine runtime. |
| [Rancher Desktop](https://rancherdesktop.io/) | Optional local container-engine environment used on the development laptop; not an application dependency. |

### Security and engineering workflow

| Technology | How we use it |
| --- | --- |
| [Trivy](https://trivy.dev/) | Scans the exact final image's OS/Python packages; HIGH/CRITICAL findings or unavailable/incomplete scans block qualification. |
| [Gitleaks](https://github.com/gitleaks/gitleaks) | Scans the publication candidate for exposed credentials. |
| [Bandit](https://bandit.readthedocs.io/) | Static security analysis of Python application source. |
| [pip-audit](https://pypi.org/project/pip-audit/) / [npm audit](https://docs.npmjs.com/cli/commands/npm-audit/) | Check locked Python/JavaScript dependency sets for known advisories. |
| [Git](https://git-scm.com/) | Source history, feature branches and reviewable checkpoints. |
| [Dependabot](https://github.com/dependabot/dependabot-core) | Configuration in this checkpoint proposes grouped image/scanner and CI-action update PRs after merge; updates still require tests and human review. |
| [gstack](https://github.com/garrytan/gstack) | Development/review/QA/documentation/shipping workflow used by the coding agent; not shipped in the application image. |

Project-owned publication, secret, contract, documentation and code-comment checks supplement these
tools. The main [documentation index](docs/README.md) links to their policies and operating guides.

### Retained organization prototype

The separate [prototype](prototype/README.md) reuses several Python tools above and adds
[openpyxl](https://openpyxl.readthedocs.io/) for historical XLSX feed experiments. It is not
installed in the production application image; current application intake uses CSV.

### Hosted services and planned infrastructure

These are deployment/service choices, not additional open-source runtime dependencies already
qualified by the local application:

| Technology or service | Status and intended use |
| --- | --- |
| [GitHub Actions](https://github.com/features/actions) | Current hosted CI service; runs the five required checkpoint jobs. The service itself is distinct from the open-source actions and runner projects. |
| [Kubernetes](https://kubernetes.io/) | Planned orchestration of API/worker pods and maintenance CronJobs; Kubernetes is open source. |
| [Terraform](https://developer.hashicorp.com/terraform) | Planned OCI infrastructure provisioning. [Current Terraform licensing](https://github.com/hashicorp/terraform/blob/main/LICENSE) is source-available, so it is not classified as an open-source dependency here. |
| [OCI OKE](https://www.oracle.com/cloud/cloud-native/container-engine-kubernetes/), [OCI Database with PostgreSQL](https://www.oracle.com/cloud/postgresql/) and [OCI Vault](https://www.oracle.com/security/cloud-security/key-management/) | Planned managed hosting, PostgreSQL and credential custody. These OCI services are not open-source projects or locally qualified integrations. |

For the built/runtime distinction and current image qualification limits, see
[container development](docs/how-to/container-development.md). Exact tool versions/digests live in
manifests and locks rather than being duplicated in this catalog.
