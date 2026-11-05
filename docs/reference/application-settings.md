# Application settings and session cleanup

29 October 2026 · Configurable session policy and bounded housekeeping

[Settings file](../../backend/config/application.toml) · [Authentication](authentication.md) ·
[Production data dictionary](../engineering-design/11-production-data-model.md)

## One nonsecret configuration file

`backend/config/application.toml` is the initial source of application operational settings.
The versioned, strict loader rejects unknown keys, invalid types, nonpositive limits, oversized
files and idle limits greater than the absolute lifetime. It never guesses a saved database,
reads arbitrary environment overrides for policy, or prints raw TOML/validation content on errors.
The packaged local file covers sessions, explicit local recovery authentication, laptop HTTPS and
branding. It intentionally retains 18 explicit scalar keys for offline compatibility. The new
source schema additionally supports ten environment/email leaves, mapped below; omitted notification
settings remain disabled by default. All sample/configuration fields have adjacent purpose comments.
It is separate from per-tenancy configuration baselines/overrides and contains no credentials.

| Key | Default | Meaning |
|---|---|---|
| `schema_version` | `1` | Supported settings structure; unknown versions fail |
| `sessions.idle_timeout_seconds` | `1800` | 30 minutes since qualified activity |
| `sessions.absolute_timeout_seconds` | `28800` | Eight hours after session creation, regardless of activity |
| `sessions.cleanup.hour_utc` | `2` | UTC hour for the daily cleanup CronJob |
| `sessions.cleanup.minute_utc` | `0` | UTC minute for that daily job |
| `sessions.cleanup.batch_size` | `500` | Maximum rows deleted in each transaction |
| `sessions.cleanup.max_batches` | `20` | Maximum transactions per run |

Load configuration explicitly using `load_settings(path)`. Session issuers must use
`session_lifetime(server_utc_now, settings.sessions)` to set `expires_at` and `idle_timeout_seconds`.
The existing verifier then enforces both from the stored row. Local/SSO issuance is still the next
[local authentication implementation](local-authentication.md); the helper alone does not mint a session.

Policy is **pinned at issuance**. File changes affect new sessions when the issuer reloads/redeploys;
existing sessions retain their original idle duration and absolute expiry. Increasing limits cannot
revive an expired old row. Immediate cutover requires explicitly revoking existing sessions through
the approved administration/operation procedure. No automatic hot reload or bulk-revocation command
is introduced here. OKE should mount the same nonsecret file from a ConfigMap for API and maintenance.

## Updating settings in a running environment

Settings are nonsecret deployment configuration, supplied through a Kubernetes ConfigMap rather
than baked into the application image. A supported value change requires **no image rebuild**.
The [separate configuration deployment path](../engineering-design/18-database-ci-and-build-order.md#application-and-configuration-deployment-paths)
validates the candidate against the deployed image, updates the ConfigMap and any affected CronJob
schedule, then rolls API/worker pods using a configuration-checksum annotation. Every required CI
suite still runs; only the image build/publish step is avoided. Both application and configuration
deployments are serialized per environment. New fields/behavior require a compatible code release.

V1 operators edit the reviewed file; end users do not edit settings through the application UI.
Settings are loaded once per process. Existing pods/jobs do not hot reload, and existing sessions
keep their pinned limits. Configuration rollback uses the same path with a previous compatible
file. This is the approved deployment design; hosted pipelines and OKE resources are not installed.

## Runtime expiry, activity and logout

Every authenticated request rejects `revoked_at`, `now >= expires_at`, or
`now >= last_seen_at + idle_timeout_seconds`. Expiry is enforced before and after external
entitlement verification and does not wait for cleanup. A 401 response clears the secure host-only
cookie. A browser/session expiry never cancels an already accepted durable operation.

- `GET /api/session` and ordinary polling do not refresh `last_seen_at`.
- `POST /api/session/activity` rechecks current authority, then conditionally updates only the exact
  live session, with server UTC and `GREATEST(last_seen_at, now)`. A concurrently revoked, deleted,
  idle-expired or absolute-expired row cannot be revived. Neither issued policy nor absolute expiry
  changes. The future UI should call this from input activity, throttled, not from polling timers.
  This is a client assertion of activity, not proof that a human is present; the absolute cap remains.
- `POST /api/logout` retains HTTPS/Host/Origin/custom-header guards but does not require a working
  IdP or current admin entitlement. It invalidates only the presented opaque handle and clears the
  cookie with Secure, HttpOnly, Path=/ and no Domain. Missing/invalid handles are idempotent.
  If storage revocation fails, it still clears the browser cookie but returns unavailable: server
  revocation is not falsely reported complete.

These endpoints exist only in explicitly authenticated app composition. The default factory remains
liveness-only, without login, bootstrap, local-credential or tenancy mutation routes. The explicitly composed [local sign-in path](local-authentication.md) now issues sessions, with
login/logout audit integration; housekeeping does not invent that history.

## Actual cleanup

The session table is an operational store, not the durable security audit. Cleanup deletes only
rows that are revoked or expired by their pinned idle/absolute limits. It does not delete identities,
grants, operations or immutable audit events. Invalid rows may remain until a run executes, but they
cannot authenticate. Migration 0004 adds the required positive idle duration with no database default;
pre-policy rows are explicitly revoked and backfilled, rather than granted a new lifetime.

Each transaction selects at most the configured batch size with `FOR UPDATE SKIP LOCKED` and rechecks
eligibility when deleting. Independent concurrent runs do not double-delete or block on another
owner's locked row. A failed run may have committed earlier batches; rerunning is safe. The command
reports only aggregate `deleted`, `batches`, and `batch_limit_reached` values. A false work-limit flag
is **not** a claim that no locked or newly expired rows remain. A later scheduled/manual run can
remove them. No extra application table, queue or coordinator is needed.

Run from the repository root after installing the backend, with credentials supplied separately:

```sh
uv run --project backend otm-maintenance cleanup-sessions \
  --config backend/config/application.toml
```

`OTM_DATABASE_URL` must be explicitly injected through an operator environment/deployment secret.
There is no saved/default connection. URL query overrides and all libpq `PG*` environment overrides
are rejected. Remote connections require `OTM_DATABASE_CA_FILE`, verify-full TLS and disabled GSSAPI
fallback; explicit loopback is the only permitted non-TLS development target. The maintenance role should have DELETE and column-scoped SELECT on
`id, expires_at, last_seen_at, idle_timeout_seconds, revoked_at`, plus UPDATE(id) solely because
[PostgreSQL row locks require an UPDATE privilege](https://www.postgresql.org/docs/16/sql-select.html).
It needs no access to identity/hash columns, credential updates, audit, DDL or administrator tables.
Managed PostgreSQL role/TLS qualification remains part of deployment. A real Docker regression
sets a restricted NOLOGIN role and verifies the same repository query works while identity reads,
credential/revocation changes and audit access are denied.
Do not run this command against the preserved organization lab database.

## Daily OKE job

The same settings generate a Kubernetes CronJob JSON manifest (JSON is valid Kubernetes YAML):

```sh
uv run --project backend otm-maintenance render-session-cleanup \
  --config backend/config/application.toml \
  --image REGISTRY/IMAGE@sha256:REPLACE_WITH_THE_ACTUAL_IMAGE_DIGEST
```

The placeholder above is intentionally rejected until replaced by a real 64-hex digest. Rendering
requires no database credentials and does not contact or deploy to a cluster. The generated job
uses explicit Etc/UTC, concurrency Forbid, bounded execution/retries, a nonroot restricted container,
read-only config/CA mounts and secret references. Deployment must supply `otm-application-settings` with key `application.toml`,
`otm-session-maintenance-database` secret containing key `url`, the `otm-database-ca` secret containing
`ca.crt`, and the qualified backend image/role/network permissions. No raw credentials are rendered.

Changing hour/minute requires regenerating/applying the CronJob as well as updating the ConfigMap;
changing batch bounds is read by each new invocation. The renderer is ready for the later Terraform/
OKE slice; no cluster or laptop scheduler has been installed, and no persistent database was purged.
Kubernetes job status/logs report failures; email/operations UI integration is not claimed here.

## Schema and validation

`otm_admin_session` now has 16 implemented fields, adding `idle_timeout_seconds`; total implemented
application table count is now six after the later [administrator foundation](administrators.md). `last_seen_at` is server activity time, not background polling.
No raw token or password is stored. New row inserts must explicitly use a qualified issued policy.
All six migration revisions and their SQL checksums are packaged, along with the settings sample.

Unit and real PostgreSQL tests cover file parsing/policy changes, exact idle/absolute boundaries,
outage-safe logout/cookie clearing, revoked/expired touch rejection, nondecreasing activity, cleanup
bounds, SKIP LOCKED, concurrent sweeps, audit preservation, legacy migration revocation and the real
maintenance command against a disposable database. The 95% production unit gate remains separate
from database integration coverage. The local React frontend now wires input activity separately
from polling; its browser suite is distinct from these backend ASGI tests. Actual deployment remains
later work.


## Local recovery settings

The application file has 18 scalar keys: seven version/session/cleanup keys above, six in
optional `[local_auth]`, two in optional `[local_server]` and three in optional `[branding]`. The [local authentication guide](local-authentication.md#settings-and-identity-scope)
lists all six names, bounds, defaults and effects. Older session-only files remain valid without
this section; absence does not activate a local sign-in route. Workspace and local issuer are stable
installation identity, not routine tunables; set them before first bootstrap and retain them.
Production credential paths/DSNs remain injected separately, and a settings change cannot reseed an
existing protected administrator or bypass MFA.

## Local HTTPS origin

Optional `[local_server].public_origin` is a canonical HTTPS origin of at most 256 characters, with
no credentials, path, query, fragment or explicit default port. The sample is
`https://localhost:8443`. The laptop launcher additionally requires localhost/127.0.0.1 and an explicit
port from 1024–65535; this setting does not configure production ingress/proxy trust.

The [local launcher](local-application.md) copies settings once and retains edits on repeated setup.
Changing the origin requires a deliberate settings edit and restart; a later setup `--port` does
not overwrite the existing file. The setting contains no TLS private key or database password.
Absent local-server settings do not expose a frontend or start a process. Existing session-only
and local-auth-only files remain valid.

## Separate simulator policy

Simulator policy is separate from the 18 application TOML scalar keys. [The simulator configuration](simulation.md#simulation-configuration-and-field-map)
is separate `simulation.json`, with strict `SandboxConfig`/target/policy models, fixed simulated mode,
1–20 virtual children and explicit `execution_paused`. It contains no password/PEM/OCI signer and
cannot select a real adapter. Setup creates this file only when missing, without seeding activity.

Catalog, new admission and worker boundaries reread/validate this explicit JSON file. Unknown fields,
invalid scope or unavailable configuration fail closed; pause blocks new work/dispatch but not a
compatible committed replay. Unpause does not resume old Needs-attention work. This per-boundary
sandbox-policy read does not make application TOML hot-reloadable or change issued session limits.
Private nullable `LocalState.worker_password` is a separate owner-only JSON-state upgrade, never a
TOML/catalog/public field; explicit setup preserves the existing owner/API credentials and data.


## Instance branding

The app may be white-labeled without renaming OTM code, tables, commands or technical documents.
This installation is **Atlas**; the generic default when `[branding]` is omitted is
**OCI Tenancy Manager** with no custom images.

```toml
[branding]
display_name = "Atlas"
logo_url = "/branding-assets/atlas-wordmark.png"
icon_url = "/branding-assets/atlas-icon.png"
```

| Setting | Purpose and bounds |
| --- | --- |
| `branding.display_name` | Nonblank display name, at most 80 characters; shown as text/accessibility identity and browser title. Default OCI Tenancy Manager. |
| `branding.logo_url` | Optional same-origin asset path under `/branding-assets/`; used in sign-in/sidebar with natural aspect ratio and name fallback. Omit to use text only. |
| `branding.icon_url` | Optional same-origin asset path under `/branding-assets/`; browser favicon. Omit for no custom favicon. |

Only reviewed raster image filenames are accepted; external URLs, data URLs, scripts, traversal,
queries and fragments are rejected. These are public assets: never place HR data or secrets in the
branding directory. `GET /api/branding` returns only these three nonsecret values before sign-in;
it does not expose authentication policy, workspace configuration or credentials. All privileged
APIs retain their session/current-grant checks. Text is escaped and the existing same-origin CSP
remains in force. An image that fails to load in the browser falls back to the configured name. A configured
asset that is missing or a symlink at process startup fails configuration validation instead;
operators must correct the path/file before starting the app.

Repository assets live in `frontend/public/branding-assets/` and the frontend build copies them
into `frontend/dist/branding-assets/`. Preserve supplied originals privately under
`reference/branding/atlas-originals/`; optimized app assets omit unnecessary image metadata.

For the laptop, edit `.local-dev/application/application.toml`, then restart `otm-local start`.
The already-installed file is intentionally preserved by setup; editing the shipped default alone
does not change it. Do not change `local_auth` identity bindings while adjusting branding. Existing
accounts, sessions and database data require no migration or reset.

In OKE, supported name/asset-path changes use the separate reviewed configuration-release flow
and pod restart, with no image rebuild. A new asset must first be available at the same public
asset location, through the image or a reviewed read-only deployment asset mount; changing a path
does not upload a file. Asset provisioning and configuration rollout must be coordinated. This is
deployment design, not a claim that OKE/configuration CI is already installed.


### Local test organization reset

`[local_server].organization_reset_enabled` is a boolean, false by default. It permits only the
explicit confirmed `otm-local reset-organization` operator command in a verified owned local
installation and enables the Organization screen's command-instructions control. It creates no
reset HTTP endpoint or new runtime database privilege. The CLI reads the current private file on
each invocation; the screen reflects startup settings, so restart the app after changing the flag.
[Reset scope and safeguards](organization-screens.md#local-test-reset) cover the physical deletion of
organization snapshots and retention of authentication, operational and audit records.


## Environment email and SMTP settings — source candidate

4 November 2026. The authored notification slice loads operator-owned local/staging routing and a
trusted expected environment without rewriting canonical employee/SSO identities. One explicit
test destination covers SMTP and OTM-supplied OCI email contact paths; production rejects override/
bypass and unresolved real responsible contact blocks delivery. Original local-recovery email
remains null even when an explicit test route supplies an effective destination.

The [accepted policy](../engineering-design/21-environment-email-policy.md) requires frozen
original/effective route evidence, dispatch fingerprint revalidation and independent offline gates
in both application/configuration deployments. The source contract below maps current fields. Full test, saved-instance, hosted SMTP/Vault and OCI
contact qualification remain pending; source validation alone is not production readiness.


### Complete new environment/email leaves

ApplicationSettings has eight top-level fields; environment/testing/notifications are the three
additions. TestingSettings has one field and NotificationSettings has eight. There are ten new
supported scalar leaves, bringing the complete source schema to 28 leaves when optional sections
are populated. The unchanged default local sample still explicitly contains 18, the staged example
14 and production example 13; defaults/optional fields are not invented as present TOML entries.

| Key | Default | Bounds and operational effect |
| --- | --- | --- |
| environment | local | local/staging/production; independently matched to the trusted release target. Not a browser field. |
| testing.email_override | null | One validated mailbox, at most 254 characters; required staging, optional for local startup but required for local egress. Entire testing section forbidden in production. |
| notifications.enabled | false | Explicitly stages/registers delivery when true; disabled defaults retain offline behavior. Does not bypass contact safety for email-capable lifecycle actions. |
| notifications.smtp_host | 127.0.0.1 | Nonblank operator endpoint; no path/user/header/control characters. Local cleartext requires loopback. |
| notifications.smtp_port | 1025 | Integer TCP port 1–65,535; match the selected local capture instance or approved hosted service. |
| notifications.sender_email | no-reply@otm.test | One validated envelope/header service sender; never inferred from employee records. |
| notifications.tls_mode | local | local/starttls/implicit; local is cleartext only to loopback, enabled hosted notifications reject it. TLS modes verify the peer using system trust. |
| notifications.application_origin | null | Trusted HTTPS origin for operation links. Required when enabled without local_server; local serving derives public_origin and rejects an explicit conflict. Frozen into notice and rechecked before send. |
| notifications.username | null | Optional SMTP login; must be paired with a password_secret_reference. Not an application/admin login. |
| notifications.password_secret_reference | null | Nonsecret reference paired with username. Actual password comes from an injected loader and never enters TOML/records/UI. Vault adapter is unqualified. |

Loading a production profile rejects any testing section, even empty; unknown toggles are also
rejected by the closed schema. Staging requires its override even when mail is disabled. Local
startup may remain offline without one, but MailPolicy.guard/guard_address deny egress rather than
falling back to a known employee address. Original-null local-recovery contact is preserved.

MailPolicy's fingerprint covers environment and override. The transport profile additionally
binds SMTP endpoint/port/sender/TLS/login/secret reference (never the password), and notices retain
application origin separately. The local worker compares freshly loaded notification/local-server
settings with its startup composition before egress; edits block old sends until reviewed API/
worker restart. Do not assume changing a file atomically reconfigures consumers or recalls mail.

### Offline release validator, both paths

The [local runbook](../how-to/lifecycle-email-runbook.md) shows both release-kind commands
and safe capture setup. otm-validate-release requires --config, --expected-environment and
--release-kind application|configuration. It parses bounded nonsecret settings without provider
credentials. Invalid/mismatched environments, unsafe production testing, missing staging routing,
hosted local_server, enabled hosted cleartext or absent origin fail closed with a fixed diagnostic.
Success returns environment, release_kind, settings_sha256, email_policy_hash and email_redirected.
It does not deploy, fetch secrets or prove a real SMTP endpoint. Both protected deployment paths
must invoke it independently before delivery/OCI credentials/apply. Hosted CI/OKE enforcement is
not installed by the standalone validator.

## Cost collection settings

[costs] defines the qualified simulator profile, independent retrieval/source age thresholds
(default 86400 seconds, each 1–604800) and 0–2 retry delays (each 1–3600 seconds; default30/120).
See [cost visibility](cost-visibility.md). These do not start a daily scheduler. Coordinated
configuration rollout/restart, rather than an image rebuild, applies changes.
