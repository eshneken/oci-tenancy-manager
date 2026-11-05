# Submit and run a simulated inspection

30 October 2026 · Local durable-submission implementation checkpoint

[Local setup](local-application.md) · [Operations reads](operations.md)
· [Atomic admission](admission.md) · [Worker/evidence](worker.md)
· [Settings](application-settings.md)

The local application now accepts a configured simulated inspection through the UI/API, commits real
operation/intent/native-job rows, and executes it in a separate foreground Procrastinate worker.
The virtual provider makes no OCI call and uses no OCI credentials. It does not adopt a tenancy,
create resources or push policies. PostgreSQL session/grant/job/audit writes are real; the provider
read is simulated. The full tenancy lifecycle/MVP and production OCI/SSO/OKE qualification remain open.

## Upgrade and run

From the repository root, stop the local foreground processes before an explicit setup upgrade, then:

```sh
uv run --project backend otm-local setup
```

This preserves the existing installation UUID, workspace/issuer edits, owner/API passwords,
administrator credentials, sessions, recorded operations and other user data. Legacy private state
can be read without a worker password; setup creates/persists a new separate `worker_password` only
when absent and provisions the local worker role. It does not recreate the human administrator,
rotate existing owner/API passwords, reset MFA or connect to the organization prototype database.
Existing simulation configuration is preserved.

Setup also creates `simulation.json` when missing. This is configuration only: it defines five
virtual targets but seeds no operation, native job, audit activity or tenancy registry row. The
application TOML remains at 14 scalar keys; sandbox policy lives in separate strict JSON.
If this is a new installation, complete private human-terminal bootstrap as described in the
local setup guide. Existing installations must not bootstrap again.

Run the application and worker in two separate foreground terminals:

```sh
uv run --project backend otm-local start
```

```sh
uv run --project backend otm-local worker
```

The first command serves the app at its configured local HTTPS origin. It does not start a worker.
The second polls the scoped native queue until stopped; it does not start the web server or create
an administrator. Both use the same owned loopback installation and explicit settings. Starting or
stopping a process does not manufacture recorded activity. With no worker, a successfully accepted
inspection remains queued. Stop each foreground process with Ctrl-C when finished; persistent data
and queued work are retained.

The lower-level `otm-simulation-worker` entrypoint accepts `--once` only when its explicit local
runtime environment has already been supplied. It drains currently available jobs with `wait=False`;
it is not a one-job limit. `otm-local worker` does not forward that flag. Normal worker mode is
long-lived with one concurrent job, one-second queue polling and a ten-second graceful-shutdown
window. Abrupt termination can still require owned native stalled-job inspection/recovery; no
automatic retry scheduler or generic retry/resume UI is added.

## UI flow and submission uncertainty

1. Sign in with the existing local password/TOTP account and open Operations.
2. Choose **Run simulated inspection**, then explicitly select a configured synthetic target.
   The dialog shows its OCID and scenario and states that no OCI resources change. Cancel has the
   safe initial focus; no target is silently preselected.
3. Confirm submission. A 202 receipt follows successful database commit, then the UI opens the
   recorded operation detail. Acceptance is not verification or tenancy adoption.
4. The separate worker consumes that committed job and publishes an outcome/step/audit transaction.
   List/detail polling and Refresh expose the new committed state; polling does not refresh session
   idle time. A healthy read becomes Succeeded; unverified outcomes become Needs attention.

| Configured scenario | Recorded simulated outcome |
| --- | --- |
| `healthy` | Verified `TENANCY_INSPECTED`; operation succeeds, without adopting/configuring the tenancy. |
| `access_denied` | `ACCESS_DENIED`; no confirmed access/absence. |
| `timeout` | `READ_TIMEOUT`; no inferred absence or successful verification. |
| `unsupported` | `UNSUPPORTED_CAPABILITY`; the capability remains unsupported. |
| `unobservable` | `TENANCY_UNOBSERVABLE`; unavailable evidence does not prove nonexistence. |

Request identity is a UUID generated for each selected target in the mounted Operations-list form.
An uncertain retry in that modal reuses the same key, including Cancel/reopen while the list component
remains mounted. The API's compatible committed replay returns the existing operation and does not
append another job/intent. Fresh authorization is still required before that replay.

A network/503 outcome does not prove rejection. The UI says to check Operations before starting
another request and offers **Check submission again** with the same current-modal request identity.
A 409 is a conflicting reuse requiring review; invalid input is reported separately. Closing the
dialog does not cancel an accepted inspection, and pending submission cannot be dismissed as though
nothing happened.

Navigating away, reloading or signing out clears the form's in-memory keys. Backend committed-key
idempotency remains durable if the original key is known and reused, but this UI does not recover
that key after a reload. Check recorded Operations before starting new work. This bounded guarantee
is accepted for read-only simulation; a future mutating workflow must qualify stronger recovery UX.

## HTTP and atomicity

Only explicit `SandboxAdmission` composition enables these routes:

| Route | Closed public boundary |
| --- | --- |
| `GET /api/inspection-sandbox` | Current-admin catalog: `provider_mode`, `execution_paused`, `targets[]` with virtual OCID/name/scenario. Internal policy/binding data is omitted. |
| `POST /api/operations/inspect` | JSON `{client_request_key: UUID, tenancy_ocid}` only; 202 `Acceptance` with committed `operation_id` and `state`. |

The POST requires the existing session, HTTPS/Host, exact Origin/custom-header guards and
`application/json`; its body is bounded to 4,096 bytes. Actor/workspace/parent/organization/policy/
binding values come from current verified session and server configuration, not browser input.
New work must select a configured virtual child. The parent cannot be one of those children.

`AcceptInspection` reuses existing atomic acceptance: operation, immutable intent and native job
share one PostgreSQL transaction/connection. No raw provider payload or credential goes in the job;
it carries only the operation UUID. A failed commit cannot produce a success receipt. If commit's
outcome is uncertain, the same request identity permits later inspection/replay rather than assuming
nothing committed. Replay authorization precedes lookup; compatible replay precedes policy reload,
so later pause/removal/unavailable configuration does not rewrite already committed acceptance.

Invalid body/target produces 400 `INVALID_INSPECTION_COMMAND`; conflicting key reuse produces 409
`REQUEST_KEY_REUSED`. Missing, malformed, wrong-workspace or paused sandbox configuration makes
new submission unavailable with 503, rather than being silently ignored or reported as a user-input
error. Catalog failure is 503 `INSPECTION_SANDBOX_UNAVAILABLE`; an absent optional feature is not
replaced with a fake catalog. Current authorization failures retain session diagnostics. Recorded
Operations reads remain available independently of catalog/submission availability.

## Simulation configuration and field map

`OTM_SANDBOX_CONFIG` selects the explicit local `simulation.json`. Parsing is bounded to 65,536
bytes, validates a regular file and rejects final-component symlinks/FIFOs. Strict closed contracts
reject unknown keys, invalid types or scope. JSON has no comment keys; field purposes are documented
in the typed configuration and this map. The application/server configuration remains outside public
built assets. No secret, real OCI adapter or arbitrary SDK argument can be selected here.

| Configuration field | Meaning and validation |
| --- | --- |
| `schema_version` | Exactly integer 1. |
| `provider_mode` | Exactly `simulated`; no live provider selector. |
| `policy.workspace_id` | Exact session/installation workspace, 1–256 nonblank characters; must match loader scope. |
| `policy.policy_revision` | Trusted policy UUID frozen in intent and checked at dispatch. |
| `policy.organization_id` | Virtual organization text, 1–256 nonblank characters. |
| `policy.parent_tenancy_ocid` | Virtual parent tenancy OCID; never supplied by the form. |
| `policy.access_binding_id` | Trusted virtual binding UUID frozen in intent. |
| `execution_paused` | Required Boolean; true blocks new acceptance/dispatch. Compatible committed replay still works. |
| `targets` | Required list of 1–20 unique virtual child OCIDs; none may equal the parent. |
| `targets[].tenancy_ocid` | Virtual child OCID, 15–256 characters with the tenancy syntax contract. |
| `targets[].name` | Configured display name, 1–256 nonblank characters; not a real discovered tenancy name. |
| `targets[].scenario` | One of the five explicit scenarios above. |

The catalog projects `provider_mode`, `execution_paused` and the three target fields; the dialog
maps only those values to its selection/summary. Submission contributes only request UUID and child
OCID. The receipt/detail link uses existing `Acceptance.operation_id/state`; subsequent list/detail
fields retain the [Operations source matrix](operations.md#public-dto-and-ui-field-map).

Private `state.json` adds nullable `worker_password` for legacy compatibility. It is generated only
by explicit setup and serialized deliberately into owner-only local custody; it is never a catalog,
TOML, job or public DTO field. Owner/API values and identities remain preserved. This adds no
application table, migration or durable operation kind: there are six application tables, six frozen
migrations/17 migration assets. The subsequent Audit History/shared-read slice brings current
exports to23 schemas and runtime modules to45.

## Worker scope, permissions and policy changes

Admission and worker use `otm.sim.<32 hex characters>`, where the suffix is the first 32 SHA-256 hex
characters of the trusted UTF-8 workspace ID. This fixed 40-character ASCII name leaves room for the
native NOTIFY channel prefix within PostgreSQL's 63-byte limit. It is scheduling isolation, not a
replacement for workspace/actor/target authorization; the browser cannot choose another queue; composed services derive it from the trusted workspace.

The API role can append operations/audit/native jobs but has no worker operation-update/job-delete
grants. The separate worker role reads current administrator grants and operation evidence, updates
permitted operation/step state, appends immutable worker events and uses the native queue tables.
It does not receive MFA custody or an owner credential. Both runtime compositions reject operator
membership; the local worker accepts only the qualified IPv4 loopback target. These are local
DB-role boundaries, not production isolation: the same OS user can read all private local state.

Dispatch needs no live browser session, but it rechecks the original issuer-qualified actor's current
OTM grant and the current server policy. Policy revision, parent/organization, binding, selected child
and pause state must remain valid. A runtime policy revision derived from the whole current config
also prevents publishing a read across a config change. Credential generation 1 is virtual simulation
metadata, not a real PEM/Vault credential. The simulator rebuilds independent virtual facts per read;
accepted intent and immutable audit are not rewritten by editing config.

Unpausing is not a resume command and does not restart a prior Needs-attention operation. Setup,
API start and worker start never clear pause or create activity. Production generic mutations,
real credentials/OCI access, corporate SSO and cloud worker/operator-pod deployment remain future
qualification. The simulation checkpoint passed **484 backend unit tests**, **2092/2107 executable lines
(99.2881%) across all 41 modules**; **62 frontend unit tests**, **301/301 lines (100%) across all ten
source files**; and **593 combined backend/PostgreSQL/browser tests** with zero failures or skips.
The two real Playwright scenarios use separate restricted API/worker roles and synthetic isolated
fixtures, rather than the human's persistent account/database. Backend/frontend unit coverage is
measured separately from database/browser execution. [Development progress](../history/development-progress.md)
and its validation receipt record exact evidence, reviews and source-scan results. These local
results do not authorize Git/publication or production deployment.

## Simulated issues are history, not required remediation

Operations sits in **Activity & history** beside Audit History. A current simulated issue retains
its recorded `needs_attention` state, while detail explains **“Simulation ended with an issue. No
action is required.”** Virtual denied/timeout/unsupported/unobservable outcomes are troubleshooting
examples, not a new assigned-work inbox. There is no generic Retry operation control.

Submission uncertainty is different: keep the documented same-key/current-modal check and inspect
Operations before creating another request after reload. The issue explanation does not claim an
unknown acceptance failed or completed. Real future remediation belongs to the affected higher-level
tenancy/org/config/access context under its own authorization and uncertain-effect rules.

## In-progress lifecycle simulation extension

The same separately started local worker now also registers the [organization lifecycle facade](organization-workflows.md).
These simulated mutation milestones are distinct from the five read-inspection scenarios described
above; they do not qualify activation, IAM, baseline, real import or termination. Pending/verified
registry relationships and local-only cancellation appear in the person/tenancy flow. Queue/native
completion alone never establishes registry/provider success. Final evidence for this added path
is pending; the original simulation receipt remains scoped to its recorded source.
