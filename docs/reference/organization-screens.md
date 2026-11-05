# Organization directory and CSV intake

30 October 2026 · Production application integration, not the preserved prototype

[Storage and implemented ER](organization-storage.md) · [Domain rules](organization-domain.md) ·
[UI authority](../ui-screen-authority.md) · [Application](local-application.md)

## Try the screens

Sign into the local application and choose **Organization**. The directory starts empty. Choose
**Upload organization CSV**, select a UTF-8 file, confirm **Organization data as of (UTC)** and
whether it contains the complete organization, then choose **Process feed**. The default time is
fetched from the server when the dialog opens; confirm the actual export time rather than treating
upload time as evidence. An older or equal capture time cannot replace a newer applied/proposed
snapshot. To test a later organizational change, use a later genuine source time.

The required headings are `EMPLOYEE_FULL_NAME`, `EMAIL`, `MGR`, `TOP_MGR`. Heading case, surrounding
whitespace and order can vary; missing, duplicate and extra headings cannot. Blank manager values
are allowed; an omitted employee name/email is not. The limits are 2 MiB, 5,000 employee rows,
256 characters per employee name and 320 per email. UTF-8 BOM is accepted. Null bytes, invalid UTF-8,
malformed quoted CSV, wrong column counts, invalid emails, duplicate normalized employee emails,
empty files and excessive inputs produce safe, location-based errors without quoting source cells.

Valid metadata applies automatically. A partial feed may update metadata but cannot establish
absence. A complete checkbox does not grant census authority: the trusted source policy, capture
freshness, root requirements and reporting-chain coverage still govern absence inference. Graph or
scope failures never replace the current organization. Intake diagnostics distinguish rejection,
supersession and accepted warnings. A rejected source is retained when it reaches domain processing;
a structurally invalid CSV never creates a feed. Organization Mapping must already be saved before
first upload; a semantically rejected feed publishes no organization head.

## Current screen scope

The directory shows employee name, email, manager name, accountable leader name, line of business
and an absence-review badge. Search matches these displayed fields literally. All five columns sort;
paging is performed on the server and stale page numbers clamp to the last page. Referenced or
configured identities without employee rows support reporting paths and findings but are not
represented as employees in the directory. Missing profile names fall back to email.

**Organization drift** now reads durable episodes/history through the in-progress
[workflow parity implementation](organization-workflows.md). Actionable cases retain first/last/closure
dates; source warnings and grouped metadata changes remain historical rather than disappearing with
the next feed. The accepted top-level-leader boundary convention is unchanged. The current directory
joins stable-person managed controls and active/removing plus separately pending tenancy counts;
source/reporting evidence remains immutable. All displayed times are UTC.

The original read-only screen milestone omitted tenancy decisions and durable review storage.
The current parity candidate adds those interactions with real application decisions and explicitly
simulated queued lifecycle effects; see the [complete field/scope guide](organization-workflows.md).
It is not a claim of actual OCI creation/import/IAM/termination, a complete configuration/cost
dashboard, email delivery or final passing qualification. There is no destructive reset endpoint.

## API and fields

Both endpoints require a current authorized administrator session in the current workspace.
They inherit secure cookies, same-origin/CSRF protection, no-store responses and session checks.

| Endpoint | Contract / behavior |
|---|---|
| `GET /api/organization` | `OrganizationQuery` → `OrganizationDirectory`; coherent read-only snapshot |
| `POST /api/organization/feeds` | Raw `text/csv`; `X-OTM-Request: 1`, `X-OTM-As-Of` aware timestamp, `X-OTM-Delivery` UUID, `X-OTM-Complete: true/false`; returns `OrganizationOutcome` |

| Projection | Fields and source |
|---|---|
| `OrganizationQuery` | `page` (1–100000), `page_size` (10/25/50), `sort` (full_name/email/manager_name/leader_name/lob_name/tenancy_count), `direction` (asc/desc), `query` (≤128 literal characters), `include_removed` (explicit managed-directory filter) |
| `EmployeeView` | `id`, `full_name`, `email`, `manager_name`, `leader_name`, `lob_name`, `absence_review`, `tenancy_count`, `pending_tenancy_count`, `directory_status`, `pending_operation_id`; source labels plus live managed/association authority, mapped in the workflow guide |
| `OrganizationFinding` | Compatibility fields `category`, `code`, `employee_name`, `email`, `detail`, `at`; workflow-enabled directory returns an empty compatibility list and reads durable review/history contracts instead |
| `OrganizationDirectory` context | `configured`, `upload_enabled`, `server_time`, `test_reset_enabled` (local instructions only, false by default), `pending_workflows`, `workflows_enabled`, `provider_mode`, `actionable_count`, `history_count`; full source map is in the workflow guide |
| Directory/paging | `items`, `total` (filtered), `employee_count` (all displayed employees), `absence_count`, `page`, `pages`, `page_size` |
| Snapshot status | `applied_at`, `source_as_of`, `absence_eligible`, `latest` (`OrganizationOutcome`), `findings`; current applied revision plus latest received feed, which may have failed |

The generated schemas under `backend/contracts` are authoritative and generate the TypeScript types.
No raw feed/configuration/SQL, session token or source credentials appear in public error projections.

## Delivery and SQL safety

Each newly opened manual upload gets a new delivery UUID even if the file matches an older export.
Retrying unchanged inputs in the same still-open dialog reuses the UUID and source time; the store
rejects changed content under that identity. Changing any input, closing/reopening or reloading starts
a new acquisition. This is not reload-durable retry storage. After an uncertain response, check the
latest intake before starting another upload. File bytes never enter browser storage or query caches;
leaving the Organization component aborts the client request, which does not imply rollback of already committed work.

Source values are bound SQL data, never interpolated into SQL. Sorting uses a closed list of fields;
search is literal in the bounded read model. Apostrophes and SQL-looking employee names are accepted
as text rather than corrupted by keyword blacklists. React text rendering escapes markup. Browser
and PostgreSQL tests verify these boundaries. The runtime role has SELECT/INSERT on organization
tables, column-scoped UPDATE for guarded heads/feed outcomes/version sealing, and no DELETE rights.
Guarded settings/decision commands may update current configuration; source digests and frozen
member evidence cannot be rewritten. Each publication rechecks
administrator authority in its write transaction; every request is scoped by the verified session.

## Trusted operator setup

The local launcher optionally binds `OTM_ORGANIZATION_CONFIG` to the private
`.local-dev/application/organization.json`. It contains a validated initial `Configuration`, not
employee rows. It is forbidden under the public frontend directory; production rejects the undated
development compatibility flag. CSV upload never initializes mappings from that file. Save
Organization Mapping explicitly first; existing database configuration is never silently overwritten.
Changing the file is not an ongoing mapping update API. The application does not discover or connect to the prototype database.
The operator prepared the already-approved local LOB mapping separately; it remains ignored/private.

## Verification

Unit tests cover parser/input bounds, safe HTTP errors, authentication/CSRF, literal values,
source authority, retry identity, screen controls and current drift. Disposable PostgreSQL tests
exercise installed restricted-role publication and denial of forbidden writes. Playwright runs the
built UI over real HTTPS with real MFA/session/SQL: malformed upload, complete feed, absent employee,
valid leader-boundary handling, literal script text, search/sort and desktop/mobile screen layouts.
These tests use synthetic source data only. Backend and frontend unit-only coverage gates remain
95% independently; database/browser tests do not inflate them.


## Local test reset

The local operator command below physically clears **the fixed eight organization/registry tables** (`org_workspace`,
`org_person`, `org_feed`, `org_version`, `org_member`, `org_recommendation`, `otm_tenancy`,
`otm_tenancy_membership`), including snapshots, imported configuration,
identity IDs and derived current findings. It preserves administrator grants, credentials, sessions,
operations and immutable administrative audit. Existing audit events keep their original correlation
IDs even though the corresponding test snapshots no longer exist. There is no undo or archive.

```sh
uv run --project backend otm-local reset-organization --directory "/absolute/path/to/this/installation" --confirm-reset-organization
```

Replace the placeholder with the installation you actually intend to reset; never omit the
explicit directory when running parallel instances. The
[Atlas Test guide](../how-to/parallel-local-instance.md) gives the exact runbook command.
The UI shows a deliberately non-runnable placeholder rather than implicitly selecting the default
installation. The CLI default itself remains `.local-dev/application`.

It requires `organization_reset_enabled = true` under `[local_server]` in the private local
`application.toml`; the default is false. Restart the local app after changing the setting. This also
shows **Reset test organization** beside Upload on the Organization screen. That button opens command
instructions, not a reset endpoint; **Refresh organization** then reloads the directory after the
operator command succeeds. No owner credential or process-execution capability enters the browser.

The command accepts only the owned laptop Docker installation with its exact label/loopback port,
expected owner/database, configured scope and local recovery identity. It refuses a different
workspace, unexpected organization/registry tables outside that exact set; new schema needs explicit
reset review. Unsettled organization-action operations or non-simulated registry rows also refuse reset. No arbitrary database URL/schema/table list is accepted. Referencing tables outside
the fixed list prevent truncation because the command never uses CASCADE. It enforces a real
READ COMMITTED transaction, takes exclusive locks with a five-second lock timeout and a30-second
statement timeout, temporarily disables only the eight truncate guards, truncates the fixed tables,
and restores those guards before commit. Any failure rolls back data and trigger changes together.
The running API keeps its restricted role and gains no destructive privileges or reset route.

The private `organization.json` trusted source-policy profile, if present, survives. Save Organization
Mapping again before the next upload; no file-based mapping is silently reinitialized. Without a
trusted source policy, operator source setup is needed. The command reads
its current opt-in from disk; the screen reflects the configuration loaded at app startup. Testing
uses a disposable installation and verifies reset/reload, unchanged auth/audit/operation rows,
restored guards and rollback after a simulated interruption. The live user's organization is never
reset by automated tests.

## Parity candidate validation status

The source/field authority for the new dialogs, durable review tabs and Tenancies entry point is
[Organization workflows](organization-workflows.md). Implementation and required qualification are in
progress; final counts and independent review disposition have not yet been recorded for this new
candidate. Earlier read-only screen test descriptions do not certify the added workflows.

## Organization Mapping and role repair

[The settings implementation guide](organization-mapping.md) supersedes the old file-based first-upload
setup. Industry segment is the visible term; internal `lob_*` fields remain unchanged. Leader and
designee defects link to their segment's settings independently of employee tenancy cleanup, including
excluded/no-tenancy profiles. Changes apply immediately through explicit server preview and Apply.
