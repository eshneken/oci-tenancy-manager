# Hosted startup foundation

This source checkpoint supplies database, API and worker startup mechanics. It does not activate
hosted workloads. The Kubernetes bundle remains at zero replicas with a suspended migration Job
and held commands until Vault/OCI composition and staging qualification are complete.

## Explicit settings and dependencies

Use the staging or production application profile, with an explicit recovery identity in
`local_auth` and the following nonsecret `[hosted]` settings. No laptop profile or simulator is
selected implicitly. Secrets must come from explicit runtime dependencies, never this TOML file.

| Field | Meaning |
| --- | --- |
| `public_origin` | Required exact public HTTPS origin; loopback/unspecified addresses are rejected; notification links must agree |
| `trusted_proxy_cidrs` | Required 1–64 bounded CIDRs; forwarded headers are trusted only from these proxies, never all sources |
| `database_pool_size` | 1–16 connections per API/worker SQLAlchemy pool, default 2; no overflow |
| `worker_shutdown_seconds` | 1–240 seconds, default 120, within the worker pod's 300-second termination grace |

Public templates contain synthetic origins/networks. Replace them with reviewed environment
values. Configure the ingress proxy networks here, rather than the end-user access allowlist.
`hosted_settings` also enforces the existing release, recovery-network and email-routing policies.

## Initial organization mapping and import

Use `[hosted.organization_source]` from the [staging](../../backend/config/staging.application.toml)
and [production](../../backend/config/production.application.toml) templates. Set an approved
`source_id` and a `population_id` for each environment. Keep both IDs stable after the first mapping Apply.
Set `max_age_seconds` to the permitted age of a dated export. Leave
`census_contract_confirmed = false` until the source is approved as authoritative for absence
review. A CSV marked complete cannot confer that authority by itself.

- **Staging** mirrors the approved real directory and organization mapping in its own database.
  Set `testing.email_override` to the controlled test mailbox. The source policy uses that mailbox
  for its alert address. Keep SMTP disabled until the notifier and worker are qualified with the
  same routing policy as the hosted app. The existing OCI email builders enforce that policy in
  local tests. Hosted OCI activation and contact integration still require qualification.
- **Production** uses its approved directory export, mapping, and non-personal operations mailbox
  in `administrator_alert_email`. The production profile excludes testing overrides.

Before using the UI, have the approved database operator review and apply the
[organization API grants](../../infra/postgresql/hosted-organization-api-grants.sql) to the target
database in one transaction. This assumes the post-migration table owner, the restricted
`otm_api` role, and existing authentication and audit grants. Review the exact role identifier if
the deployment uses a different role name. The startup path itself does not grant privileges.

In each environment, sign in as an administrator. Open **Application Settings → Organization
Mapping** and enter the real root and segment leaders. Select **Preview changes**, review the
proposed mapping, then select **Apply changes**. From **Organization**, upload the CSV through
the authenticated UI with the export's actual UTC capture time and completeness. Verify that the
employee count and segment assignments match the approved export and mapping.

Keep employee feeds and person-level mappings in approved private storage and the app database.
Use deployment-owned source metadata and the designated mailbox in settings. Keep employee rows,
manager emails and names out of source control, deployment inputs and CI artifacts. Startup and
page loads create no organization rows. Once saved, the database owns the mapping and associated
source policy. Changing the TOML template or restarting the service leaves that saved policy in
effect. A source-policy change after setup requires a separately reviewed data change.

## Database connections and migrations

`otm.hosted_database.hosted_engine` requires an explicit PostgreSQL DNS endpoint, database, role,
password and absolute CA file. It rejects URL options, libpq `PG*` environment overrides, IP/loopback
targets and absent/invalid trust material. TLS uses `verify-full`: encryption alone is insufficient.
Connection, query, lock and pool waits are bounded; failures do not expose connection strings.

Supply separate runtime API, worker and migration role credentials. Runtime readiness rejects
superuser, role/database creation, RLS bypass, public schema creation and membership in the
application table-owner role. Effective grants still need staging validation. API authentication
requires its narrowly scoped row-lock/update grants as well as reads; workers need queue access.
The migration role must own the application schema without being a superuser or role/database creator.

The migration-only entry point is:

```sh
python -m otm.hosted_runtime migrate --config /etc/otm/application.toml --expected-environment staging
```

Provide `OTM_DATABASE_URL` and `OTM_DATABASE_CA_FILE` through private runtime secret/configuration
references, not command arguments or checked-in files. The packaged Alembic configuration is resolved
relative to the installed package, never the current directory. A transaction-scoped PostgreSQL
advisory lock allows one migration runner; failure rolls back the transaction. Only upgrade to the
bundled head is supported. API startup performs no DDL and never seeds administrators.

## API and worker composition

`create_hosted_application` composes existing authentication, organization, audit and Operations
services with an explicitly injected MFA secret reader and API-role pool. Enabled notifications
also require an injected notifier with the active email policy. Provider-backed mutations
remain unavailable in this partial composition. A real Vault/OCI composition root and executable
API/worker launch wiring are subsequent work; this is not a standalone hosted application launcher.

`serve_hosted_api` binds one process to port 8080 inside the pod, disables Uvicorn's implicit proxy
trust and access logging, and allows 90 seconds for graceful shutdown within the 120-second pod grace.
`/health/live` is independent of PostgreSQL. `/health/ready` is unauthenticated, non-cacheable and
returns only ready/unavailable. It checks TLS, restricted role and exact bundled Alembic head;
failed checks return 503 without database diagnostics. Shutdown disposes the owned pool.

Exact-head readiness means a schema-changing migration can make older API pods unready. The owner approved a brief maintenance window for schema-changing V1 releases. Drain API/worker
activity before migration, then start the matching release and verify readiness before reopening
access. Do not weaken exact-schema checks or claim zero downtime for these releases. Releases
without schema changes can roll normally. Follow the [release sequence](hosted-administration.md#schema-changing-application-release).

`run_hosted_worker` requires explicit trusted task registration before consuming the existing
workspace queue. All operation handlers and the retained notification handler must be present with
the correct queue and no native retry policy. There is no adapter registry, dynamic import or
simulator fallback. Procrastinate owns its verified-TLS native pool (1–2 connections), one execution
slot per pod, polling and signal handling. SQLAlchemy remains a separate bounded application pool.
Native job records are retained. Graceful shutdown finishes within the configured drain deadline
and releases both pools; deployed signal behavior still requires qualification.

With two API and two worker pods and default pools, steady application capacity is at most twelve
database connections (four API, four worker SQLAlchemy, four native queue). Budget additional
connections for migrations, maintenance, rollout surge and operators.

## Qualification and remaining work

Synthetic unit tests cover invalid settings/connections, readiness failures, startup composition,
migration ownership/locking and worker handler/drain contracts. The dedicated disposable TLS
PostgreSQL tests exercise hostname/CA rejection, real restricted-role authentication, transactional
migration failure and a real Procrastinate queue round trip. No cloud resources or saved demo data
are involved. These tests do not replace the full milestone integration gate.

Before activation, qualify managed PostgreSQL grants/CA delivery, Vault readers and the
[implemented token/IAM source](oke-workload-identity.md), OCI handlers,
SMTP notification composition, ingress trust boundaries, network failures, signal drain, migration
release sequencing and restore in staging. Track those in the
[real OCI manifest](real-oci-test-manifest.md#hosted-startup-and-database-qualification).
No database tables or ER relationships were added by this checkpoint.

## Source validation receipt — 13 November 2026

The complete backend unit gate passed 2,702 cases with no failures/errors/skips and 95.32%
complete-source line coverage across 191 modules. Focused startup/bootstrap units passed 68 cases.
Four disposable TLS PostgreSQL cases passed. Native Kubernetes schema validation passed all 18
resources plus its invalid-field negative control. Ruff, inline-purpose, Bandit, documentation/link,
publication and credential checks passed. Independent documentation/security reviews completed;
stale implementation-status wording and the CLI example were corrected. No UI was changed, so
no UI review was required. The full integration/Playwright suite remains a milestone/PR gate, not
a result claimed by this source checkpoint. Saved Atlas 8443 was not updated.
