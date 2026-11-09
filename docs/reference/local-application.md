# Run the local application

30 October 2026 · Local HTTPS, administrator and Organization UI checkpoint

[Backend setup](../../backend/README.md) · [Local authentication](local-authentication.md)
· [Administrator model](administrators.md) · [Application settings](application-settings.md)

This `otm-local` guide is for the laptop wrapper. Cloud bootstrap/reset will use the separately
qualified [temporary Kubernetes operator pod](local-authentication.md#cloud-operator-target); these
Docker/file/TLS commands are not a production runbook. The command name `reset-local` refers to the
application-local identity rather than the machine running it.

The application now has real React sign-in, administrator, Audit History and recorded Operations screens with
explicit simulated-inspection submission, served by the
Python backend over local HTTPS. It uses the real password/TOTP, session, grant and audit services.
The separate organization prototype is preserved; this application does not import its environment,
connect to its database. Registered tenancy workflows now use durable local simulation;
[baseline authoring and version history](baseline-authoring.md) adds Configuration without applying changes to OCI.
Organization directory, authenticated CSV/as-of
intake and current drift are now available through the production snapshot store.

## First setup

Run from the repository root with `uv`, Node/npm, OpenSSL and a working local Docker engine available:

```sh
uv run --project backend otm-local setup
```

Setup creates a private installation under `.local-dev/application/`. It generates a persistent
installation UUID, separate database-owner/API/worker passwords and an installation-local issuer.
It starts an instance-labeled PostgreSQL 16 container from the source-pinned image digest, exposes
its database port only on `127.0.0.1`, applies the reviewed migrations through `0019_operation_responsibility` and provisions a restricted
local API role. It creates no application administrator or default password. Explicit setup upgrades legacy state
with missing worker custody and adds a separate worker role while preserving existing owner/API
credentials, account/MFA and all recorded user data.

The private directory must be owned by the current user with mode `0700`; generated state and
secret files use `0600`. Setup validates its own container ownership label rather than adopting
another database, and does not use a saved organizational-lab DSN. Repeated setup preserves the
installation identity, credentials and existing `application.toml` edits. It can restart its stopped
owned database container. It does not erase data or reset an existing administrator.

The directory contains:

| Local artifact | Purpose |
| --- | --- |
| `organization.json` | Optional private initial organization policy/LOB profile. Not employee rows; never replaces an existing database configuration. |
| `state.json` | Installation ownership, generated owner/API/worker credentials and actual loopback database port. Legacy worker password may be null until explicit setup. Private plaintext custody, not an export. |
| `application.toml` | Nonsecret settings copied once, with stable local workspace/issuer and local HTTPS origin; 18 scalar keys with optional instance branding. |
| `simulation.json` | Separate typed virtual-target/policy configuration created only if missing; no operation/job/activity is seeded. |
| `mfa/` | Immutable, digest-bound laptop TOTP secret versions; see the authentication guide. |
| `tls.key`, `tls.crt` | Private key and 30-day self-signed localhost certificate; never a production certificate or machine-wide trust installation. |

Existing certificate pairs are reused. Setup does not automatically renew an expired certificate;
replace local TLS material deliberately in this private installation when needed. Do not publish,
copy into screenshots or attach private installation files to a support conversation.

## Private enrollment

Run bootstrap yourself in a private human terminal:

```sh
uv run --project backend otm-local bootstrap
```

The command prompts without echo for a strong password and confirmation. It displays a new TOTP
seed in that terminal for authenticator enrollment, then asks for a real current code. Do not paste
the password, seed or codes into chat, record the terminal or retain its output as an ordinary
artifact. The consumed enrollment code cannot immediately be reused for sign-in; wait for a fresh
code after enrollment.

Bootstrap verifies operator database authority and atomically commits grant, verifier/reference,
consumed step and audit. It refuses a second bootstrap. No account is inferred from visiting a page,
changing settings or running the web server. Its success creates no browser session.

For a deliberate credential reset, use the separate operator flow:

```sh
uv run --project backend otm-local reset-local
```

Reset preserves the protected identity, requires fresh password/TOTP enrollment, changes its
authorization revision, revokes its sessions and records audit. It does not rebind an installation
by changing the issuer. Failed or uncertain enrollment/reset commits never trigger automatic seed
deletion: inspect committed references before any manual cleanup. Old versions remain retained.

## Start and return later

```sh
uv run --project backend otm-local start
```

Start infrastructure-services the locked frontend dependencies with install scripts disabled, builds the React
bundle and runs the backend in the foreground at [https://localhost:8443](https://localhost:8443).
On first use, the browser may show its self-signed certificate warning. Verify that the origin and
certificate belong to this local installation before accepting a browser-local exception where
supported. No machine-wide certificate trust root is installed.

Sign in as `recovery-admin` using the privately enrolled password and a fresh six-digit authenticator
code. Ctrl-C stops the foreground web server; the database container and private installation remain.
On a later visit, run `otm-local start` again. If Docker or the owned container was stopped, start
Docker and rerun `otm-local setup` before starting the application. Bootstrap is not a startup step.
There is no automatic teardown or reseeding.

For async inspection execution, run `uv run --project backend otm-local worker` in a separate
foreground terminal. API startup never starts that worker. See [simulation setup and retry limits](simulation.md).

The launcher defaults to port 8443. For a new installation, `otm-local setup --port <local-port>` can
select a port from 1024–65535. An existing installation preserves its copied settings, so later
`--port` arguments do not overwrite them. Change the nonsecret `[local_server].public_origin`
deliberately and restart; use a localhost/127.0.0.1 HTTPS origin with an explicit nondefault port.
The generated certificate covers localhost and 127.0.0.1. Paths, query strings and credentials do
not belong in that origin.

## What the screens do

The sign-in form sends factors only in guarded same-origin JSON. It never stores them in browser
storage or a URL. The response sets the secure host-only cookie after successful session/audit
commit. Browser access to a public shell or built asset is not authorization to read an API.

The administrator screen reads real application grants. It provides name/email search, sortable
columns, selectable page sizes, pagination, refresh and whole-workspace statistics. The protected
recovery account is labeled operator-managed. An active ordinary corporate grant, if present, can
be revoked through a confirmation dialog; the backend rechecks live authority, target protection
and the displayed authorization revision. This changes application access and sessions, not OCI
tenancy ownership/resources. There are no fictitious directory rows or demonstration revocations.

Add administrator is disabled because verified corporate identity enrollment is not configured.
Ordinary grant creation/regrant and corporate SSO remain unimplemented. Operations now reads real
persisted inspection records. Organization/Organization drift are enabled. Tenancies and Configuration now expose the implemented local registry, baselines, overrides, updates and read-only drift checks. Provider effects remain simulated.

Session polling checks authorization but does not extend idle time. Trusted browser pointer/key
input separately sends throttled activity assertions; the server remains authoritative for idle and
absolute expiry. Expiry clears the directory view and returns to sign-in. Sign-out revokes the
presented handle with audit and clears its cookie; an unavailable confirmation is shown honestly.
No corporate provider is required for local sign-out.

## Implemented HTTP and model boundary

The default `create_app()` is still health-only. The explicitly configured local factory adds:

| Route | Implemented behavior |
| --- | --- |
| `GET /`, `/login`, `/administrators`, `/operations`, `/operations/{id}`, `/audit-history`; `/assets/*` | Public nonsecret React shell/assets under configured HTTPS/Host guards. No directory or operation data is embedded in the shell. |
| `POST /api/auth/local/sign-in` | Password/TOTP verification, atomic issuance and secure cookie; retains exact Origin/custom-header guards without requiring an old session. |
| `GET /api/session` | Current verified display/workspace/expiry context. |
| `POST /api/session/activity` | Explicit guarded refresh of a still-live session. |
| `POST /api/logout` | First handle revocation and immutable logout event, independent of current entitlement/IdP. |
| `GET /api/administrators` | Fresh authorized directory read in the session workspace. |
| `POST /api/administrators/{id}/revoke` | Closed `{expected_revision: UUID}` command reusing the atomic revocation service. |
| `GET /api/operations` | Current-workspace persisted inspections with state/search/sort/pagination controls. |
| `GET /api/audit-history` | Safe immutable event projections with current workspace scope, actor/ID search, categories and paging. |
| `GET /api/operations/{id}` | Exact-intent summary, current steps and newest 50 operation events. |
| `GET /api/inspection-sandbox` | Current-admin virtual-target catalog and pause state; configured simulator only. |
| `POST /api/operations/inspect` | Bounded child/request-key submission with server-owned policy and atomic 202 acceptance; no OCI call. |

Directory query fields are `page` (1–100000, default 1), `page_size` (10/25/50/100, default 10),
`sort` (`display_name`, `email`, `identity_kind`, `status`), `direction` (`asc`/`desc`) and `query`
(at most 128 characters). Search is literal case-insensitive containment over display name/email;
SQL wildcards in input are escaped. Sorting uses a stable UUID tie-break and places nulls last.
The server clamps an oversized page to the last page; even zero results report one available page.

`AdministratorView` exposes only `id`, `display_name`, nullable `email`, `identity_kind`, `status`
and `authorization_revision`. `AdministratorDirectory` returns `items`, filtered `total`, effective
`page`, `page_size`, `pages` and `statistics`. The statistics' `total`, `active` and
`protected_recovery` cover the whole authorized workspace independently of the search. These are
projections of the existing grant table, not new database tables. Neither credentials nor raw
issuer/subject/session hashes are returned. The original read-history milestone had23exported schemas; the frontend generates public TypeScript types from authoritative models. The current generated schema inventory is checked against the Python models; that earlier count is historical.
Static TypeScript types do not replace server validation or prove a response's runtime contents.

## Local boundaries and remaining gates

The HTTPS process receives the restricted local API database credential; migration/bootstrap/reset
use the separate owner credential; the worker has its own restricted database role/password.
Both runtime factories reject owner/superuser-like authority
even if called outside the launcher. That is real database-role separation, but not production process
isolation: both commands run as the same OS user, which can read the private state holding both
passwords. The local API role is not a qualified OCI managed-PostgreSQL deployment role. No production
Vault adapter, ingress/IP limiter, corporate SSO, OKE resource or hosted CI pipeline is installed.

The local application is persistent developer state, separate from disposable database/browser test
fixtures. Tests must not modify its human account or saved data. Final unit, PostgreSQL, Playwright,
coverage and security evidence are recorded in [development progress](../history/development-progress.md)
when completed; this guide makes no provisional result claim. The 95% complete-source backend and
frontend gates, browser integration and independent reviews still apply. No Git check-in,
publication or production deployment is authorized by a local browser demonstration.

## Operations read visibility

The [Operations guide](operations.md) maps the working list/detail pages to existing `otm_operation`,
`otm_operation_step` and `audit_event` records. The page shows committed inspections or an honest
empty state; detail uses exact current intent, current-intent steps and bounded immutable history.
Dates are recorded UTC instants, and the simulated-provider notice appears in list and detail.

State/search/sort/page controls and manual refresh create read queries; list settings survive detail/
back navigation, and sign-out clears privileged query data. Every read rechecks session/workspace
authority. A foreign UUID and missing UUID produce the same unavailable detail. Final validation
results belong in development progress after the final gate run.

The recorded projections remain read-only. [The subsequent simulation slice](simulation.md) now
adds an explicit **Run simulated inspection** form/API and separate foreground queue worker. It
creates real local operation/job/audit rows only after submission, with configured virtual provider
outcomes and no tenancy adoption/OCI write. No generic retry/resume/cancel workflow is added.
The first [read-visibility checkpoint](../engineering-design/18-database-ci-and-build-order.md#operations-read-visibility-checkpoint)
is distinct from that subsequent durable submission path; neither completes the MVP or live OCI
qualification. Cloud operator-pod infrastructure remains a separate task.

## Activity & history navigation

Daily Tenancies/Organization/Configuration remain their separate management contexts. Operations and
[Audit History](audit-history.md) sit under **Activity & history**; Administrators sits under
**Application settings**. Audit rows are real immutable evidence with safe actor/target/code fields,
search/category filters, sort/paging and Operations links. No raw JSON or edit/export action exists;
audit export is still planned MVP work.

Operations is visibility/troubleshooting, not an inbox. Current simulated issue detail says
“Simulation ended with an issue. No action is required.” Its stored `needs_attention` state is
unchanged. The simulation submission/uncertainty rules remain in force, and real future remediation
will originate in the affected tenancy/org/config/access context rather than a generic Retry button.


### Local instance name and logo

This instance displays **Atlas**, configured in the `[branding]` section of
`.local-dev/application/application.toml`. The repository default is
[documented with asset paths and update steps](application-settings.md#instance-branding).
Changing branding does not rename the database or alter administrator identity, passwords or MFA.
Restart the app after changing the local file; setup preserves existing file edits.


### Audit date filters and CSV download

In **Activity & history → Audit history**, use **From (UTC)** and **Before (UTC)** to select a
half-open date/time range. **Export CSV** downloads all matching events across pages with the
current category/search/order. The synchronous cap is10,000events; narrow filters for larger
results. The download uses nine safe columns and records **Audit export prepared**. This records
server preparation, not proof the browser saved/opened the file. See the
[export field and security guide](audit-history.md#utc-filtering-and-complete-filtered-csv-exports).

Forward migration0007 is applied by explicit `otm-local setup`, preserving existing accounts,
MFA, branding/configuration and history. A local backup was taken before this development update.
Migration0008 adds the separate production organization snapshots. The [Organization intake and
screen guide](organization-screens.md) covers the enabled Organization and Organization drift menu,
private initial source setup, CSV validation, source-time attestation and remaining workflow limits.
The production directory starts empty; the prototype retains its existing data independently.


### Reset an organization test run

[The local reset instructions](organization-screens.md#local-test-reset) describe the explicitly
enabled `otm-local reset-organization --directory "/absolute/path/to/this/installation" --confirm-reset-organization` command. Organization's testing
control shows the command without executing it. It clears organization test tables and preserves
your application login, credential custody, sessions, operations and administrative history.

## In-progress organization parity routes

The [workflow parity guide](organization-workflows.md) records current authored production routes:
`GET /api/organization/reviews`, `GET /api/organization/people/{id}/workflow`,
`POST /api/organization/actions`, `GET /api/tenancies`, `GET /api/tenancies/{id}` and public nonsecret
`/tenancies`/`/tenancies/{id}` shells. All data/actions retain current session/workspace guards;
POST uses bounded closed JSON and normal CSRF checks. Tenancies now exposes a basic simulated registry;
Configuration/financial/provider qualification remain incomplete. The foreground local worker must
be started separately for accepted lifecycle work. The default app factory remains health-only.
The reset command's reviewed scope is eight org/registry tables and refuses unsettled simulated work.
Final candidate test/package counts are pending and supersede none of the historical receipts.


## Parallel local test organization

[The parallel Atlas Test guide](../how-to/parallel-local-instance.md) describes the prepared
`.local-dev/runbook` installation at `https://127.0.0.1:8444`; the existing Atlas remains on
`https://localhost:8443`. Separate databases, issuers, credentials and host-only cookies preserve both
environments. Bootstrap/start/worker/reset commands must explicitly select the intended `--directory`.
The CLI's omitted-directory default remains the original `.local-dev/application`, so reset guidance
now uses a placeholder requiring deliberate replacement. No default source policy or administrator
is inferred from a browser visit; the test's explicitly prepared source policy is synthetic only.


### Existing-tenancy baseline updates

Configuration → Update existing tenancies previews all eligible active children. A tenancy's own
Baseline updates card scopes that action to one child. Every blocker must clear before Start update.
The accepted version and targets remain fixed even if another baseline is subsequently published.
Progress and supported retries live on Configuration/tenancy detail; Operations links back to progress.
Only local simulated managed objects are changed. See [the complete guide](configuration-updates.md).
The0015 forward migration appends three nullable verification/observation fields and extends existing
operation evidence checks; it does not rewrite existing pins or claim old setup is freshly verified.


## Shared-access/onboarding source upgrade — 3 November 2026

The authored setup migration chain now includes 0017_membership_onboarding, expanding the existing
step allowlist without a new table/column or data backfill. This refinement is qualified locally;
both saved instances are upgraded from 0016 with private 0600 backups and matching old-data
fingerprints across all 18 existing tables, without a reset. The
[manual review](../how-to/tenancy-refinements-runbook.md) uses only synthetic test data and
keeps the API/foreground worker separate. New version 2 onboarding applies its accepted baseline in
simulation; prior accepted versions retain their graph. There is no new application setting or secret.


### Saved preview asset consistency

Saved review installations on 8443/8444 must use a private per-instance snapshot of the qualified
frontend assets, supplied to their server through OTM_FRONTEND_DIST. Keep this stable-review launch
separate from ordinary otm-local start, which builds and serves the mutable working frontend/dist.
A new development build must not silently replace the frontend under an older running saved API.
Update the backend and its qualified frontend snapshot together, retain the existing backup/data
preservation checks, and verify actual served JS/CSS hashes. Disposable tests can use the current
working build. This is a saved-preview operating rule, not a production deployment qualification.


## Qualified local on-demand drift — 3 November 2026

The authored Configuration drift page queues read-only local checks through the separate existing
worker. Its new immutable check table is the nineteenth application table; qualification and both saved-instance upgrades pass. There is no daily scheduler, repair or operator simulation CLI. Use only
disposable synthetic PostgreSQL/browser fixtures to demonstrate external missing/different/unknown
state; do not mutate a saved installation's observation JSON or reset its data.
[Runbook](../how-to/configuration-drift-runbook.md) · [Field guide](configuration-drift.md).


## Qualified local guided responsibility — 4 November 2026

The authored 0019_operation_responsibility migration extends only the audit-kind allowlist, with
19 application tables/20 baseline columns unchanged. New guided operation detail supports explicit
audited self-claim; it does not add an administrator, require a real tenancy or change original
activation mailbox/credentials. Positive multi-admin and revocation cases use prepared disposable
authorized fixtures; a one-admin saved installation cannot invent another claimant.
[Runtime guide](responsibility.md) · [Manual review](../how-to/responsibility-runbook.md).
Qualification and both saved upgrades pass; existing backups/data/snapshots are preserved.


## Local lifecycle email source candidate — 4 November 2026

Qualification/install pending. Default packaged settings remain disabled/offline. Explicit private
settings can enable loopback capture with one test mailbox and the selected instance's matching
Mailpit ports: main SMTP 1025/UI 8025, test SMTP 1026/UI 8026. Keep capture@otm.test out of canonical
employee/admin identity fields. Preserve all existing sessions/auth/workspace/branding settings and
use coordinated API/worker restart with the qualified frontend snapshot; do not reset data.

[Capture and configuration commands](../how-to/lifecycle-email-runbook.md) ·
[All settings leaves](application-settings.md) · [Outbox/state guide](lifecycle-email.md).
There is no SMTP relay configured and ports are loopback-only; normal Docker bridge does not mean
network egress is firewalled. Injected production secrets, real OCI email contacts and hosted SMTP
remain future qualification. The source migration chain adds 0020_email_delivery (20 tables); saved
instances are not yet claimed upgraded.

## Manual presence-check source revision

After deliberate coordinated installation of the matching API/frontend/worker and migration 0025,
a fresh simulated create/import can use Required users → Check now. Keep the foreground worker
running. Older recorded identities without an accepted connection remain unqualified; do not reset
or invent connections to enable them. No extra service, scheduler or simulator-control CLI is
required. Local qualification and the main-preview upgrade pass; the parallel preview is unchanged. See the
[manual runbook](../how-to/required-users-runbook.md).

## Local verification uses separate required lanes

The persistent preview is not a test database. Run backend unit/coverage separately with
`uv run --project backend python scripts/check_unit_coverage.py`; it selects all non-postgres tests
and measures the entire production source inventory. Run the integration wrapper separately with
`uv run --project backend python scripts/run_backend_postgres_tests.py`; it selects all postgres
marked tests, including native worker/HTTPS/browser fixtures, in disposable owned databases.
The frontend unit/coverage gate remains separate. Both backend lanes and the frontend gate must
pass; an integration receipt does not stand in for unit execution or coverage. The user approved
a 600-second aggregate integration budget; individual test limits and all assertions are unchanged. Final Check now qualification passes 1,556 backend units, all 351 PostgreSQL/native-worker/browser cases (429.457 seconds), and 446 frontend units separately. Main port 8443 is upgraded with all 28 preexisting public tables preserved and one empty 14-column check table added. Port 8444 remains unchanged and healthy. [Final receipt](../history/manual-presence-checkpoint-2026-11-06.md). [Canonical lane ownership](../engineering-test-plan.md#complementary-backend-test-lanes).

## Saved-preview publication safeguards — 9 November 2026

Before changing a saved local preview, verify its exact local origin, owned runtime processes,
container label and running state. The container must expose exactly one PostgreSQL binding on
127.0.0.1, with the port matching saved instance state; backup and preservation reads must target
that same database. Refuse redirected/symlinked instance paths.

After complete qualification, freeze the exact frontend file hashes in private evidence. Reject
symlinks in the source tree and snapshot paths, hidden/nonregular frontend entries and reused
snapshot destinations. Copy into the instance's new immutable release directory, then verify the
entire copied file set/hash map before serving it. Start matching API and worker code, verify SPA
routes and served asset bytes, and preserve the independent parallel instance.

Keep database/configuration backups private. Compare complete preexisting table-content hashes
before and after preparation, with no automatic replay or user/session-row repair. A local settings
change must be explicitly scoped and model-checked to the approved fields before atomic replacement.
Changing the local idle limit applies to newly issued sessions; it never rewrites existing deadlines.
