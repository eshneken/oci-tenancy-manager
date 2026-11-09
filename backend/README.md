# OCI Tenancy Manager backend

This is the separate production backend foundation. The preserved organization prototype remains
under `prototype/`, with its own environment and executable regression evidence.

The default application exposes only `GET /health/live`, confirming process liveness rather than
external readiness. [Session verification](../docs/reference/authentication.md) can be explicitly composed to add
session context and explicit activity/logout endpoints. Non-health access requires current
administrator authority, except narrowly guarded logout and explicitly composed local sign-in.
[Local recovery authentication](../docs/reference/local-authentication.md) provides operator bootstrap/reset
and real password/TOTP issuance. The [local HTTPS application](../docs/reference/local-application.md) adds
React sign-in/logout, an authenticated administrator directory, ordinary-grant revocation and
[Operations list/detail](../docs/reference/operations.md) and [Audit History](../docs/reference/audit-history.md). A configured [simulated-inspection form/API](../docs/reference/simulation.md)
now accepts durable work, which a separately started foreground worker executes asynchronously.
The [Organization directory/upload and current drift](../docs/reference/organization-screens.md) now use
authorized production snapshots. The [workflow guide](../docs/reference/organization-workflows.md) describes durable reviews, registered simulated tenancy/member flows and managed-person decisions.
[Manual required-user checks](../docs/reference/user-presence-checks.md) connect authenticated API admission to a separate worker and independent dated simulated results. Local qualification and the main-preview upgrade pass; [the receipt](../docs/history/manual-presence-checkpoint-2026-11-06.md) preserves exact test lanes and installation limits.
Public shell/assets contain no identity data; APIs retain current authority and request guards.
There is no permissive provider or corporate SSO. Tenancy routes expose only the explicitly simulated local registry in this parity candidate.
The durable simulated provider runs in a separate worker process; HTTP acceptance does not claim
its outcome. This foundation
is not a deployable tenancy-management release.

Run these commands from the repository root:

```sh
uv sync --project backend --locked
uv run --project backend python scripts/check_unit_coverage.py
uv run --project backend ruff check --config backend/pyproject.toml backend scripts/check_unit_coverage.py
uv run --project backend ruff format --config backend/pyproject.toml --check backend scripts/check_unit_coverage.py
uv run --project backend python scripts/check_inline_docs.py
uv run --project backend python scripts/export_backend_contracts.py --check
uv build --project backend --no-sources
```

To run the application, follow [setup, private bootstrap and HTTPS startup](../docs/reference/local-application.md).
No password or MFA seed belongs in chat. To serve only the liveness endpoint:

```sh
uv run --project backend uvicorn otm.app:create_app --factory --host 127.0.0.1 --port 8000
```

Use the explicit project argument. Both environments use the `otm` import name; they must stay
isolated. A test checks that production imports resolve to `backend/src/otm`, not the prototype.
No production module imports prototype code. Later slices will extract the proven domain behavior,
adapt its persistence boundaries and port its tests rather than rebuilding those decisions.

## First provider capability

[Internal tenancy inspection](../docs/reference/inspection.md) implements the first typed OCI facade capability
and a stateful, clock-controlled simulator. The [durable simulated worker](../docs/reference/worker.md) now
consumes the accepted operation, persists scoped step/results and uses required current authority.
Inspection verifies exact child/parent/organization/attempt
pairing and fresh evidence; denied/delayed/unavailable reads do not imply absence. The models generate
checked structural schemas under `backend/contracts`. No real OCI adapter, cloud secret access or provider mutation is implemented. Internal durable admission
is described below; simulated execution now builds on it. The approved data model supplies separate raw home-region key
and qualified identifier fields; unknown mapping remains null.

## Runner integration prerequisite

The [isolated native-runner qualification](../prototype/experiments/runner/README.md) proves the
same-transaction enqueue path and controlled worker lifecycle against disposable PostgreSQL.
The qualified dependency versions are now adopted by the production package; the toy tables and
experiment code are not imported. [Internal operation admission](../docs/reference/admission.md) implements the
first production operation/audit migration and atomic native enqueue with required injected
authorization. A [registered simulated read worker](../docs/reference/worker.md) now executes that capability;
that initial checkpoint provided no permissive production authorizer, tenancy-management route or production deployment
composition or real OCI worker.

Run real database tests with `uv run --project backend python scripts/run_backend_postgres_tests.py`.
This requires local Docker, Node/npm and the pinned Playwright Chromium browser (install with
`npm --prefix frontend exec -- playwright install chromium`). The runner infrastructure-services/builds the locked frontend
and creates/removes a fresh isolated PostgreSQL container; it does not
change the preserved prototype database.

## Application settings and cleanup

[Settings and usage](../docs/reference/application-settings.md) document the nonsecret
[application TOML file](config/application.toml), eight-hour local idle/absolute policy (hosted profiles retain 30-minute idle/eight-hour absolute limits),
explicit activity, logout and bounded expired/revoked-session cleanup. The `otm-maintenance` command
can run cleanup or render its daily UTC CronJob. No scheduler is installed automatically; credentials
are injected separately and no saved development database is used.

## Coverage starts here

The shared [coverage checker](../scripts/check_unit_coverage.py) runs all non-database tests in
this project, measures every module under `src/otm` including unimported files, and requires at least
95% unit-only line coverage using raw counts. Empty collection, skipped selected tests, exclusions,
incomplete source inventory or invalid evidence fail. Database/browser execution cannot inflate it.
Artifacts remain under ignored `backend/.local-dev/quality`.

The initial P0.4 bootstrap passed seven tests with 11/11 lines covered across two source files.
The current gate measures all production source files, including local composition, under the same
rules. Its denominator does not measure business features that have not been ported. A temporary
unimported-file probe independently demonstrated failure at 11/12 lines despite all seven tests
passing; the probe was removed. Every later production slice must meet the same gate from the start.
The retained prototype's broader coverage report is diagnostic for extraction, not a passing
production result or a reason to exclude imported production modules.

The frontend has a separate complete-source 95% unit gate and browser integration tests. Current
results belong in [development progress](../docs/history/development-progress.md); backend ASGI tests do not
substitute for Playwright. Production authentication/ingress, managed OCI/runner deployment
qualification remain deployment work. Hosted checkpoint CI and protected `master` are established;
[checkpoint policy](../AGENTS.md#incremental-github-checkpoints--5-november-2026) requires passing
checks, independent reviews, publication privacy checks and PR-only merges. The owner approved
sanitized source checkpoints; passing local bootstrap alone does not qualify a production deployment.


## Administrator foundation

[Administrator grants and revocation](../docs/reference/administrators.md) adds two tables and internal current-grant
lookup/atomic ordinary-grant revocation. Sessions must match the current grant reference and revision.
The [local authentication slice](../docs/reference/local-authentication.md) now uses that credential shape for
interactive bootstrap/reset and guarded password/TOTP sign-in. Corporate provider qualification,
ordinary add/regrant and production deployment remain subsequent slices. The current React screens
use the same services through guarded directory/revocation HTTP routes; see the local application guide.

## Generated contracts and local state

The frontend derives public TypeScript contracts from authoritative backend models; Python validation remains authoritative. The current schema has 25 OTM application tables through migration 0026, excluding separately owned native job-queue tables. Generated contracts are checked against the current Python models; earlier checkpoint counts on this page are historical.

The launcher owns separate persistent laptop state under ignored `.local-dev/application/`; the
organization prototype is untouched. Database owner and runtime credentials are separate, but the
same OS user can read both from local private state. This is not production process isolation, OCI
Vault custody or deployment qualification. Test/browser fixtures must remain separate from a human's
persistent local administrator and data. No local launch authorizes Git check-in or publishing.

## Operations read visibility

[Operations API/UI fields and snapshot behavior](../docs/reference/operations.md) document two guarded GET routes
over the existing operation/step/audit tables. The directory has bounded state/search/sort/pagination;
detail exposes current-intent steps and the newest 50 immutable events with an explicit limit notice.
Both views read one read-only repeatable database snapshot and expose closed public projections.

This makes recorded Operations navigation live. The subsequent [simulation slice](../docs/reference/simulation.md)
adds explicit configured inspection submission and `otm-local worker`, using the same durable
admission/worker/audit services. No generic retry/resume/cancel or real OCI action is added.
Successful simulated inspection is not tenancy adoption; current evidence remains separate from
full create/import and production qualification.

## Submit a simulated inspection

For an existing installation, rerun explicit `otm-local setup` to add separate worker custody/role and
`simulation.json` while preserving owner/API credentials and user data. It creates configuration,
not recorded operations. Run `otm-local start` and `otm-local worker` in separate terminals, sign in,
then use **Run simulated inspection** in Operations. The 202 receipt records atomic acceptance;
the worker asynchronously publishes verified/Needs-attention state. No OCI credentials/calls or
adoption occurs. [The simulation guide](../docs/reference/simulation.md) documents request-key uncertainty,
scoped queues, all configuration/public fields and the bounded browser retry guarantee.

## Activity and history

Operations and [Audit History](../docs/reference/audit-history.md) are grouped under **Activity & history**;
Administrators is under **Application settings**, separate from the future daily-management pages.
Operations is visibility/troubleshooting. Current simulated issues retain `needs_attention` but say
“Simulation ended with an issue. No action is required.” Real future remediation starts from the
relevant tenancy/org/config/access context; no generic Retry operation control is introduced.

Audit History reads the existing immutable event table with current scoped authorization, safe
actor/category/ID projections and search/sort/paging. Worker events show Inspection worker, operator
events use a generic Database operator label, and failed sign-ins are Unverified attempt—not an
authenticated human. Raw JSON and record editing remain unavailable. UTC date bounds and the
guarded CSV export share the existing filtered projection; an immutable preparation event commits
before bytes are released. Exports include every matching row up to the explicit10,000-event bound,
never a silently truncated first page. The source guide maps all query, directory, entry, export
request and preparation-evidence fields. At that earlier store checkpoint the inventory was27schemas/54runtime modules, eleven
application tables/eight migrations/21migration assets and17application TOML keys. That inventory is historical; the current settings and local schema are described in the reference guides. Current test
and independent-review evidence is recorded in development progress.

## Production organization domain

[Organization intake and reconciliation](../docs/reference/organization-domain.md) now extracts the reusable
CSV/parser, canonical models, graph reconciliation and review rules into production modules with
synthetic regression tests. It does not import the prototype. [Authorized snapshot storage](../docs/reference/organization-storage.md)
now persists received feeds and distinct proposed/applied versions with stable scoped people,
sealing guards and automatic valid metadata publication. Authenticated Organization CSV/screens are integrated. The validated [workflow parity guide](../docs/reference/organization-workflows.md) maps durable reviews, stable-person managed controls and the registered simulated lifecycle handoff. See the [parity checkpoint](../docs/history/organization-parity-checkpoint.md) for completed qualification.

## Validated organization workflow parity

[Detailed current fields and implemented ER](../docs/reference/organization-workflows.md) cover three new physical
production tables (`org_recommendation`, `otm_tenancy`, `otm_tenancy_membership`) and the stable-person
managed controls added by migration0009. At the organization parity checkpoint, the schema had14application tables/nine forward revisions;
subsequent configuration work adds the baseline table. Current counts and required validation are
recorded in [development progress](../docs/history/development-progress.md).
Human identity/organization decisions are real application changes; lifecycle work remains explicitly
simulated and queued. No real OCI adapter or full MVP is qualified by this checkpoint. Earlier counts
and receipts on this page describe their original completed slices, not the current cumulative application.


## Shared-access and onboarding refinement — 3 November 2026

Local simulation qualified and installed in both saved instances. The existing organization-action/step/audit path gains exact
shared-member identity-removal receipts, existing-versus-new compartment binding and guided
onboarding version 2. New create/import applies/readbacks its frozen baseline through the shared
configuration simulator, then freshly checks access before temporary-account retirement. Previously
accepted version 1/legacy work is preserved. Migration 0017 extends step allowlists only; 18 tables
remain. These changes do not qualify a real OCI adapter, object grammar, user deletion or Vault.

[Field and step mapping](../docs/reference/tenancy-onboarding.md) ·
[Shared-access contracts](../docs/reference/organization-workflows.md) ·
[Isolated review runbook](../docs/how-to/tenancy-refinements-runbook.md).


## Qualified local on-demand configuration drift

The new [read-only drift guide](../docs/reference/configuration-drift.md) describes explicit queued checks of
assigned baseline/overrides, confirmed-versus-check views and immutable per-child evidence. Source qualification and both saved-instance upgrades pass. It adds one table (19 application tables),
reusing operation/step/audit/native queue storage. Checks call observation only, not apply, and do
not alter configuration heads or fake-cloud state. No repair, daily infrastructure, email, user
simulation helper or real OCI qualification is included.


## Qualified local guided responsibility

[Audited administrator responsibility](../docs/reference/responsibility.md) adds explicit self-claim for waiting/
attention guided create/import, current-responsible-only continuation and a captured replacement
authority snapshot rechecked at dispatch. Original creator/activation mailbox/provider intent/owner
remain unchanged. Migration 0019 expands one audit constraint, with no new table/column or job on
claim. Qualification and both saved-instance upgrades pass. This real application capability
needs no OCI access, adds no temporary simulator controls and does not qualify mail/SSO/OCI grants.


## Lifecycle email and environment routing

The [lifecycle email guide](../docs/reference/lifecycle-email.md) maps responsible-admin lifecycle notices (create/import, deletion, shared membership, ownership
transfer and offboarding),
immutable contact/policy/profile/origin evidence and bounded SMTP delivery knowledge. One outbox
table brought the lifecycle-email checkpoint through 0020 to 20 application tables; later presence
checkpoints bring current OTM metadata to 25 through 0026. Both release kinds use the offline
otm-validate-release gate against a trusted expected environment. Hosted checkpoint CI is installed;
staging/production OCI delivery and infrastructure qualification remain pending.
[Local capture runbook](../docs/how-to/lifecycle-email-runbook.md). Local capture and saved-instance
qualification pass; OCI/Vault/production-SMTP and uncontrolled provider mail remain unqualified.

[Current-month cost visibility](../docs/reference/cost-visibility.md) adds coherent stored Budget reads,
bounded worker retries and the consolidated Tenancies dashboard behind an explicitly simulated facade.
Daily scheduling and live OCI qualification remain staging work.

The [recovery-network repair source subset](../docs/reference/recovery-network-repair.md) reuses existing operations, steps, audit and checks. Migration0026 extends CHECK-constraint branches only; the 25 OTM tables are unchanged. Full local UI/integration qualification and preserved main-preview publication pass; live OCI remains pending.

- [Recovery-network repair final checkpoint](../docs/history/recovery-network-repair-checkpoint-2026-11-09.md):430 complete integration cases, independent reviews and preserved main data/settings.
