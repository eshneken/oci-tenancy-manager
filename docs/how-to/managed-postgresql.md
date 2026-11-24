# Managed PostgreSQL foundation

**Implemented Terraform source; live qualification Pending.** Both platform roots now include
`infra/modules/postgresql`. A live platform apply would create a database as well as the network and
OKE nodes. No database, Vault secret or cloud resource was created while developing this slice.
The running local Atlas database and application remain untouched.

## What the module provisions

| Item | Source configuration |
| --- | --- |
| Database | OCI Database with PostgreSQL, exact major from `OTM_POSTGRESQL_VERSION` |
| Compute | Two `PostgreSQL.VM.Standard.E5.Flex` nodes, each 1 OCPU / 16 GB RAM initially |
| Storage | Regional OCI optimized storage, 75,000 IOPS; service-managed data/WAL growth, no fixed disk/PVC |
| Network | Existing environment's private database subnet and exact database NSG; pod-only TCP5432 ingress |
| Credentials | Existing Vault secret OCID and explicit version for the provisioning administrator; no plaintext password input or secret-content lookup |
| Recovery | Daily backups and STANDARD PITR, each configured with 35 days; explicit UTC windows |
| Safety | `prevent_destroy`, major-upgrade opt-in defaults false, no automatic version/shape fallback |
| Connection | Sensitive output containing primary private endpoint and CA; no runtime password |

This follows the accepted modest starting size. The module permits 2–3 nodes, 1–8 integer OCPUs and
16–128 GB integer RAM per node, at most 64 GB/OCPU. Service-discovered shape limits further constrain
these values. There is no automatic scaling or claim that a second node proves HA readiness.

Oracle documents [E5 Flex shape bounds](https://docs.oracle.com/en-us/iaas/Content/postgresql/supported-shapes.htm)
and [storage performance tiers](https://docs.oracle.com/en-us/iaas/Content/postgresql/performance-tiers.htm).
Measure query/queue load, failover, connections, WAL, retained history and cost in staging before
increasing capacity. There is no backup-volume allocation to size as a disk; retain the
[backup storage accounting and recovery targets](../engineering-design/06-platform-and-delivery.md#ashburn-v1-backup-policy-proposal--13-november-2026).

## Required private inputs

Both platform roots require `database_administrator` and `database` alongside the existing private
network, version, OKE/bootstrap and target inputs. Synthetic examples are in their
`terraform.tfvars.example`; actual secret references and deployment coordinates stay outside Git.

| Field | Meaning / bounds |
| --- | --- |
| `database_administrator.username` | Provisioning role: lowercase letter followed by lowercase letters/digits/underscores, 1–63 characters; common service-reserved names are rejected |
| `database_administrator.secret_ocid` | Existing environment-owned Vault secret OCID; reference only |
| `database_administrator.secret_version` | Explicit positive integer version string; no CURRENT/latest alias |
| `database.instance_count` | Integer 2–3, default 2 |
| `database.ocpus` | Integer 1–8 per node, default 1 |
| `database.memory_gib` | Integer 16–128 per node and at most 64/OCPU, default 16 |
| `database.backup_start_utc` | Required `HH:MM`, 00:00–23:59 UTC |
| `database.maintenance_start_utc` | Required `MON`–`SUN HH:MM` UTC |
| `database.allow_major_version_upgrade` | Boolean, default false; explicit reviewed maintenance opt-in, not authorization by itself |

The module emits service-compatible time strings with seconds/timezone (`02:00:00Z`,
`SUN 04:00:00Z`). Example windows are provisional operator choices, not claims that maintenance
cannot overrun or overlap backup activity.

The authorized operator must create a strong administrator password in that environment's database-provisioning Vault
through an approved secret-ingestion procedure. Before planning/applying, verify the approved
requester group has the scoped secret-family/Vault reads; the custodian separately needs ingestion
and key-use authority. Do not add a speculative PostgreSQL service-principal or direct decrypt grant. The [Vault custody foundation](vault-foundation.md) now creates separate Vaults/keys in the existing hosting compartment and an exact-Vault-conditioned
requester read policy before platform creation. The custodian must still ingest the
secret privately; references alone do not prove effective grants or that it belongs to the right tenancy.
Do not put a password, secret bundle, `TF_VAR` plaintext password or raw connection URI in Terraform.
The database module never reads the secret value into state. Sensitive outputs are redacted, not
encrypted; private state/plan custody remains mandatory, including existing worker cloud-init.

These are **initial database provisioning credentials**, not the application login. Runtime API,
worker and migration roles, grants, secrets and connection-pool configuration are a separate slice.
Use hostname-verified TLS (`verify-full`) with the returned primary FQDN and service CA, not a raw IP
or a disabled verification mode. Live tests must validate certificate identity, service SSL policy
and runtime grants. A new secret version or changed reference is not a supported password-rotation
procedure by itself; qualify provider/service behavior and use reviewed database credential rotation.

## Discovery and version upgrades

Terraform queries service shapes and active default configurations. It requires exactly one flexible
E5 shape and exactly one active flexible configuration for the selected major and compatible shape.
The configuration can report its exact E5 shape or list it in `compatible_shapes` for a multi-shape
configuration. Zero or multiple matches stop the plan; no API-order choice, guessed ID or fallback
major is used. Apply the reviewed saved plan. Catalog changes on replan require renewed review.
These reads validate declared compatibility, not quota, provisioning success, performance or GA policy.

The platform root now consumes `postgresql_version` in a real `oci_psql_db_system` resource and exposes
private `database` references. The former `requested_postgresql_version` placeholder output is removed.
The output's `requested_version` remains the configured major, not an observed minor/build or evidence
of completed maintenance. The root is not deployed merely because source tests pass.

Follow the [infrastructure update runbook](hosted-administration.md#infrastructure-update):

1. Change staging's protected major pin and qualify the approved source/target path, application,
   Psycopg, migrations, extensions, Procrastinate schema and restore behavior on that major.
2. Obtain a usable pre-change checkpoint and a reviewed production maintenance/rollback plan. Retain
   the accepted version/configuration/source evidence; update CI's disposable PostgreSQL baseline
   deliberately, rather than assuming its current version changed with the Actions variable.
3. For an existing DB, explicitly set `allow_major_version_upgrade = true` only for that reviewed
   change. The provider's documented conditional behavior otherwise plans replacement for a version
   change, which this resource's lifecycle guard must block. A creation simply uses the requested major.
4. Review each environment's own saved plan; reject unexpected deletion/replacement. Apply staging
   first, then production's separately approved plan. Verify completion and reset the opt-in afterward.

See [OCI's version-update contract](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/psql_db_system.html).
Neither this boolean nor `prevent_destroy` proves safe upgrades. Configuration removal, manual service
operations and privileged Terraform changes can bypass lifecycle protection. Do not use target flags,
state removal or guard deletion to force an unreviewed replacement. Downgrades and restore/cutover
need their own supported recovery procedure; changing a version string is not rollback.

## Backups and recovery qualification

The resource requests DAILY `retention_days = 35` and STANDARD PITR `restore_days = 35` with no
cross-region copy. The provider describes backup retention in terms of retention after DB deletion;
verify actual backup expiry/accounting while active and after deletion rather than inferring those
semantics from the field name. The 35-day PITR window is separate. Confirm both policies coexist and
produce usable retained recovery sources. [Oracle's PITR procedure](https://docs.oracle.com/en-us/iaas/Content/postgresql/point-time-recovery.htm)
creates a new database system; it does not rewind the existing one.

Configured retention is not a measured recovery window or a 15-minute RPO guarantee. Qualify the
actual earliest/latest recoverable time, successful backups, encryption/key access, independent
monitoring, deletion survival and an isolated restore before go-live. Repeat drills quarterly and
after material changes against the accepted in-region 15-minute RPO / four-hour RTO targets.
Pre-change seven-day checkpoints, alerting and scheduled monitoring follow the
[backup/restore operating procedures](hosted-administration.md#backup-operations); this module does
not add an application-owned backup engine, recovery journal or cross-region DR service.

## Offline checks and remaining boundaries

Run `bash scripts/check_infrastructure.sh`. All configurations use provider mocks and
`init -backend=false`; no OCI authentication, live state backend or database connection is involved.
The module tests cover private subnet/NSG bindings, provisioning references, HA sizing, UTC windows,
backup/PITR intent, discovery failure/ambiguity and explicit upgrade-request fields. A mock apply then
forced replacement must fail specifically because of `prevent_destroy`.

**Mocked providers do not execute OCI's custom version-diff logic.** The upgrade-request fixture
checks inputs only; it does not prove an in-place service upgrade or that the real provider will
reject an unapproved version change. The [live database test manifest](real-oci-test-manifest.md#managed-postgresql-foundation)
retains those exact transition cases, downtime, restore, TLS and effective network/IAM behavior.
Complete application/PostgreSQL/browser/security milestone gates still precede a combined PR;
source-only module qualification does not qualify the hosted platform.

### Source verification — 13 November 2026

All eight native suites passed (108 cases), plus the state-bucket, cluster and database replacement
guards. In a disposable counterfactual, disabling the database lifecycle guard allowed replacement,
confirming the negative test depends on that protection. Documentation/contracts, publication,
inline-purpose and Ruff checks passed. Independent security and documentation reviews passed.

The credential scan passed after owner approval of two exact-value, named-file exceptions for the
synthetic Vault reference and public `VAULT_SECRET` enum. Disposable scope checks accepted both
approved matches and still detected an unrelated password, a changed reference in an approved file
and the enum outside approved files. No detector was disabled. This infrastructure-only slice did
not change application Python/React or rerun the complete application integration suites; full
milestone and live-service qualification remain separate gates.
