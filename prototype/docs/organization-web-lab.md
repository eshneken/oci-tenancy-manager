> **19 October association update:** The lab keeps real local registry rows for simulated

> Run lab commands from the repository’s `prototype/` directory. See [setup](../README.md).
> tenancies and person ownership/membership. Create/import/shared choices close onboarding.
> Offboard person handles every association; removing the last one automatically hides the person
> from the managed directory while preserving source/reporting evidence and history. No tenancy
> required hides a zero-association profile. Qualified absence followed by a qualified full-feed
> return automatically opens fresh onboarding after completed offboarding; No tenancy required
> exemptions still need explicit Re-onboard. No OCI operation occurs. See [the association walkthrough](tenancy-associations.md).

# Local organization dashboard and CSV lab

15 October 2026

This is a working three-screen interface over the existing PostgreSQL organization prototype.
It uses real reconciliation, immutable canonical JSON inputs and administrative action history.
It does not call OCI, provision/delete tenancies, send notifications or implement SSO.
The small UI is plain HTML/CSS/JavaScript served by FastAPI; it is not the production React UI.

## Start and open

Run these commands from the OCI Tenancy Manager project directory:

```bash
uv sync
uv run python scripts/organization_web.py
```

Open **http://127.0.0.1:8765**. The launcher binds only to your laptop's loopback interface.
It uses the saved local PostgreSQL connection under ignored `.local-dev`, and creates an empty
`root-leader-csv-lab` workspace on first run. Other workspaces, including `synthetic-lab` and
`root-leader-sample`, are preserved. Restarting the server preserves the directory you loaded.
Stop the server with Ctrl+C. If the saved database is stopped, start Rancher Desktop and run:

```bash
PATH="<private-local-path>" uv run python scripts/start_local_postgres.py
```

For an independent empty experiment, choose another workspace:

```bash
uv run python scripts/organization_web.py --workspace root-leader-csv-experiment --port 8767
```

The launcher permits only `root-leader-csv-*` and `ui-test-*` names, avoiding accidental reuse of the
older XLSX/JSON labs. You can also use **Clean workspace** on either screen to start another experiment in this
same lab. Confirm in the dialog to clear the visible directory, local simulated registry and review queue. LOB/designee
configuration is preserved, while the prior test run and its immutable audit/feed history are
archived. The exact same initial CSV can then be uploaded as a fresh baseline.

Cleaning is scoped to this CSV lab: it never clears other workspaces, shared person identities,
files on disk or OCI tenancies. A stale confirmation is rejected if another tab changes the run
or changes its applied/proposed/configuration pointers. Cancel leaves everything unchanged. Clean can also be used while already
empty. This control exists only in the local prototype, not the production app design.

Internally a clean creates a new run workspace and records `local_lab_cleaned` on the stable lab.
The browser and CLI resolve the stable name to its active run, including after a restart. When
inspecting PostgreSQL, use `workspace_id` from `/api/local/summary` or CLI `show context`; the old
run's rows remain available as history. Cleaning changes no immutable evidence and requires no
trigger bypass or table truncation.

## Upload the supplied export

Click **Upload organization CSV**, choose `data/root-leader_org_261015_clean.csv`, and click
**Process CSV**. This source copy is unchanged from the supplied download.

The accepted UTF-8 CSV headers are:

```csv
EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR
```

Header order may vary; capitalization and surrounding header whitespace are normalized. Names
may contain Unicode, commas and quoted newlines. Employee email must be present and unique after
normalization. Manager/top-manager emails may be blank, but missing required relationships become
validation failures or hierarchy reviews. Invalid headers/row widths, duplicate emails, malformed
quotes, empty censuses and inputs larger than 2 MiB/5,000 rows are rejected.

The **full organization snapshot** checkbox is an explicit local scenario declaration. Leave it
checked for complete snapshots that should identify missing employees for review. Uncheck it
for partial updates. Missing non-root manager profiles or unresolved incoming paths still prevent
new absence inference, even when full is checked. A previously open absence can persist through
partial snapshots. No person or tenancy is deleted by either mode.

The supplied export has 242 employee rows and all referenced manager profiles except the configured root's.
the configured root is the configured root boundary, intentionally exempt from having his own employee row.
His name is supplied as a known label in this the configured root-specific local UI. All other missing manager
names remain unknown rather than being guessed.

## What each page shows

**Employees** displays name, email, manager name, reported top-level manager name, configured
LOB and a sortable Tenancies count of active associations. Click a header to sort, search any displayed field, filter by LOB and change page/page size.
Absent employees awaiting a decision or retaining associations remain visible, with a highlighted row. Explicitly offboarded/no-tenancy profiles are hidden from the managed directory while their source and reporting records remain available. Placeholder identities used to complete
reporting relationships are not presented as employees. The full model remains inspectable in
pgAdmin under the same schema as your existing lab, filtered by the active `workspace_id` from
`/api/local/summary` or CLI `show context` (initially `root-leader-csv-lab`; a clean starts a new run).

The top-manager column resolves `TOP_MGR` through known person names. LOB and accountable leader
are independently derived from the reporting chain and trusted six-LOB configuration. Their
agreement is checked; a disagreement creates `TOP_MANAGER_MISMATCH`, never a silent remap.
For the configured root's direct reports, `TOP_MGR=the configured root` is an allowed boundary convention, even for a configured
LOB leader whose own accountability branch is their LOB. Raw hints remain preserved in JSON.

**Tenancies** is a main-menu screen at `/tenancies`, alongside Employees and Exceptions. It lists
active local registry tenancies with tenancy name, individual/shared type, owner name/email,
owner-derived LOB and member count including the owner. This is the first main-menu destination
and owns summary cards for total active tenancies, individual, shared and unassigned owners. Search, LOB filter, sortable headers, page-size selection
and numbered pagination follow the Employees table. Tenancy names open the existing tenancy panel;
owner names open the existing person panel. An unassigned owner remains explicit and can be repaired
through the tenancy panel. Deleted tenancies remain in database/audit history rather than the active
list. A change in the owner's reporting LOB changes the displayed rollup, never the ownership itself.
The list is a simulated local inventory; it does not discover or query OCI resources.

**Exceptions** displays open/acknowledged hierarchy/configuration exceptions plus new employee
setup review indicators. It supports search, type filtering and pagination. Historical metadata deltas are grouped per employee in Informational & history rather than
being treated as pending administrator work. A setup review indicates a need
to decide whether to create, import or associate a tenancy; it does not establish that no tenancy
already exists. Resolve/ignore, managed-directory decisions, registry associations and verified identity merges have real local database effects;
tenancy choices simulate successful completion and close their organizational review atomically.
The result is logged explicitly as simulated success; no OCI operation occurs. Dated informational history is separate from work.

The first accepted census is the baseline: its employees are not all labelled confirmed new hires.
Employee profiles added after it appear in new-employee reviews and remain flagged across feeds.
An absent new employee may have both an arrival/setup indicator and an absence review; investigate
absence/identity before provisioning anything.

Use a synthetic employee profile for this scenario; do not use real employee data in distributed examples.
the configured root outside the six configured LOB branches. No new LOB is invented. Designee nominations remain
configuration-driven and are not imported from CSV. The current API does not supply nomination
nomination controls; review-completion controls are available in the exception modal.

## Demonstrate changes

Generate optional, editable local scenarios without changing database state:

```bash
uv run python scripts/csv_demo_scenarios.py
```

Upload these in order, with full snapshot checked:

1. `.local-dev/csv-scenarios/01-baseline.csv`: original 242 employees.
2. `.local-dev/csv-scenarios/02-new-employee.csv`: adds **Demo Engineer (fictional)** under Riley Morgan.
   The directory has 243 employees and Exceptions includes a new-employee tenancy review.
3. `.local-dev/csv-scenarios/03-absence.csv`: omits that fictional employee and changes the first
   source employee's displayed name. The name updates automatically. The fictional employee is
   retained with an absence review; nothing is deleted.

You can instead edit a copy of the original CSV. Keep unchanged employees in a full snapshot.
Change names, managers and `TOP_MGR` consistently, then upload the edited file. Email is the
identity key, not an immutable HR ID: an email change appears as an arrival plus a possible
absence of the old address. Never automatically match people by name; audited identity remapping
is an implemented, explicitly confirmed workflow.

The CLI also accepts this CSV in a configured CSV workspace:

```bash
uv run python scripts/organization_cli.py --workspace root-leader-csv-lab feed data/root-leader_org_261015_clean.csv
```

Add `--partial` for a partial CSV or `--stage-only` to stage without applying. The browser directory
continues to show applied data, not a staged proposal. Existing canonical JSON CLI intake remains
supported for earlier tests.

## Snapshot identity, receipt clock and evidence

Every manual CSV upload is a new snapshot, including a file identical to any earlier upload.
Each CLI CSV ingestion has the same behavior. A UUID identifies the observation; the raw-byte
SHA-256 records content evidence and does not deduplicate observations. Uploading an earlier
file intentionally applies its contents as a current observation: it can update metadata,
flag employees missing from that file, or supply positive presence for a returning employee.
Full/partial coverage and all validation/absence gates still apply. Decisions already recorded
for onboarding or a continuous absence remain durable; a new snapshot does not reset them.

CSV has no guaranteed export ID, capture timestamp or stable employee ID. The adapter creates
`source_record_id='email:' + normalized_email`; this is a lookup key, not an HR ID. Canonical
records and envelope remain in `org_feed.data`; raw content hash remains audit evidence.
The local lab uses receipt time as its scenario capture clock, not proof of real source freshness.

For future manual, API and object-storage intake, every newly initiated observation is a fresh
snapshot even if the bytes, API result or object version are unchanged. Connectors must create
and persist an observation/delivery ID and acquisition time, then reuse that same envelope for
retries of that one delivery. Content hashes, ETags and object versions are provenance, not the
identity of a scheduled observation. Production authority/completeness/capture-time contracts
remain integration requirements. The current CSV endpoint treats each POST as a new observation;
it does not automatically retry ambiguous POSTs. Canonical JSON intake still uses its explicit
external snapshot ID: replaying that same identified delivery remains idempotent, and conflicting
content under that ID remains rejected.

Malformed uploads leave current organization state intact. Valid CSV with invalid graph structure
is retained as a rejected feed with diagnostics; the upload dialog shows the failure. The dashboard
summary describes the current applied organization, not the most recent rejected receipt.
The app retains version and administrative receipt history. Its setup indicator distinguishes baseline/pending onboarding from explicit managed-directory exclusions; the tenancy registry separately records simulated ownership and membership.

## Exercise tenancy relationships

Open a person to inspect current associations, add another individual/shared tenancy or join an
existing shared tenancy. Use Offboard person to make a complete per-association decision. Shared
member cleanup removes only that membership; shared owners must transfer ownership or remain
associated. The last removed association automatically hides a deliberately offboarded person.
A baseline or new employee with no tracked associations is not automatically hidden.
A retained outside employee who reappears in source stays outside until Mark returned to
organization is confirmed. A fully offboarded person without associations automatically enters
new onboarding after qualified absence and a later qualified full applied-feed return. Repeated
present or missing feeds retain that pending work; old tenancies stay retired. No tenancy required
remains an explicit exemption until manual Re-onboard, and repeated unchanged-present uploads
without a genuine absence do not trigger return.
Ownerless legacy shared tenancies expose Assign owner; choose a present managed employee to
repair accountability before adding members.

The [association walkthrough](tenancy-associations.md#exercising-the-flow) covers multiple mappings,
retained membership, source reappearance and explicit Re-onboard. Registry and association rows
are in `org_tenancy` and `org_tenancy_association` under the active run workspace. No real OCI OCIDs
or credentials are needed. Legacy simulated-success history is conservatively reconstructed;
unknown ownership is shown as unassigned rather than invented.

## Validation

The latest complete run passed **123 tests**. The automated Python/PostgreSQL suite covers CSV parse failures, normalization, quoting, root
exemption, top-manager conflicts, empty state, full/partial uploads, repeated identical CSV observations, canonical JSON
storage, new employee reviews, reorgs, absences and rejected uploads. Ruff and inline documentation
checks pass. Browser verification uses an independent `ui-test-csv-browser` workspace, preserving
the user workspace and earlier experiments. See the current validation record under
`output/engineering/local-web/validation.md` for the latest run count and browser evidence.

The local web interface follows FastAPI's [file-response support](https://fastapi.tiangolo.com/advanced/custom-response/).
SSO, production access controls and durable ingestion jobs remain part of the production design.

UI commands no longer ask for free-text Reason. The server automatically records a factual action
description, actor, selected target/context and outcome; API/CLI callers may still supply an
optional reason. Tenancies list Member counts include the owner; internal full-registry member
counts exclude owner-role links for lifecycle guards.
