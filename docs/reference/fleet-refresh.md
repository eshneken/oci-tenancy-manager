# Refresh all tenancy data

12 November 2026 · Implemented source subset; targeted local qualification PASS; saved publication PASS.

On the Tenancies dashboard, **Refresh all data** replaces the stored-directory Refresh and fleet
Refresh costs actions. It requests read-only acquisition for all eligible active registered children
in the current workspace, across every page and filter. Tenancy detail keeps its focused controls.
It does not ingest an organization feed, apply a baseline, repair configuration or access, rotate keys,
or create/delete resources. Provider reads remain simulated locally; live OCI qualification is Pending.

## Scope and progress

The server selects registered children and independently admits three categories per child:

- **Costs:** the existing managed Budget read.
- **Users:** one existing required-user operation reads presence, permissions, recovery controls and
  supported automation signing-key inventory. This is not four separate new jobs.
- **Configuration:** the existing check compares the assigned baseline and accepted overrides.

Each category retains its own eligibility, current-context checks, signing guards and worker behavior.
A missing connection, busy child or unsupported source can be skipped without rolling back other
accepted work. Unexpected admission failures are counted without returning internal error text.
Authorization loss aborts the request; work already independently committed remains accepted.
Accepted jobs do not make old observations fresh. Completed reads retain their dated results and
findings, including Missing/Different/Unable to verify. A finished job is not a healthy tenancy.

## HTTP and public fields

| Contract | Fields and meaning |
| --- | --- |
| `POST /api/tenancies/refresh` · `FleetRefreshRequest` | UUID `client_request_key` only; no client target/endpoint/credential authority |
| `FleetRefreshReceipt` | `tenancy_count`: selected registered children; `categories`: independent category receipts |
| `RefreshCategory` | `category`: costs/users/configuration; deduplicated `operation_ids`; `skipped_count` and `failed_count` describe admission, not provider health |
| `POST /api/tenancies/refresh/status` · `FleetRefreshStatusRequest` | `operation_ids`: 1–3,000 IDs; server checks current administrator/workspace and read-operation kind |
| `FleetRefreshStatus` / `RefreshJob` | `jobs`: `operation_id` plus pending/finished/failed/unavailable; unavailable does not reveal foreign or non-read operations |

The fleet request bounds selection to at most 1,000 active records; larger selections conflict.
Status uses one bounded SQL projection rather than an operation-detail request per job. Only existing
cost_collection, required_user_check and configuration_check operations are projected. Queued,
running and waiting map to pending; succeeded maps to finished; other known terminal states map to
failed. Missing, foreign or unsupported IDs map to unavailable. Inspect dated check/financial data
and Operations for actual results; polling never calls providers itself.

## Replay and storage boundary

This is a thin batch over existing services, guards, operations, audit and durable queue records.
There is no new table or persisted batch receipt. Child command keys are UUID5 derived from the
batch key plus workspace, category and child. Each child admission commits independently. Compatible
pending work is joined under existing locks. No database transaction spans provider I/O.

Retain the browser command key after an uncertain response. Retrying reevaluates the **currently**
eligible fleet; it is not a frozen snapshot or an atomic batch. Owned accepted child keys replay their
existing receipts. Joining another operation does not persist an alias for the new child key, so a
retry after that joined job finishes may accept another read. This bounded read-only limitation is
intentional; do not claim exactly-once fleet execution or a durable aggregate operation.

See [cost visibility](cost-visibility.md), [required users](required-users-screen.md),
[configuration checks](configuration-drift.md) and [signing inventory](automation-signing-keys.md).


## Targeted bundle qualification — 12 November 2026

Targeted local qualification PASS for combined fleet reads, create/import public bootstrap handoff
and new password candidates; **saved publication PASS**. Complete-source backend units: 2,384
passed, 12,884/13,545 lines (95.12%), 179 source files. Frontend: 650 passed, 2,156/2,221 lines
(97.07%), 46 source files. Native batch `__vclsec` passed 37 cases including fleet, create/import,
recovery and browser flows. After a small bootstrap idempotence guard refinement, focused PG batch
`m9sr0s_f` passed 3 bootstrap-retry cases. These are combined targeted results, not a new complete
integration/milestone run or proof that the final guard received another full native batch.

Independent source security and actual responsive create/import/fleet UI reviews PASS. Privacy,
secret and Bandit scans PASS; no dependencies changed. Real OCI/Vault, effective password policy,
hosted OKE and full-milestone qualification remain Pending. Historical receipts keep their original
scope. Saved publication on sole `https://localhost:8443` PASS: frozen API, immutable assets and
native worker match; health, unauthenticated new-route 401 and exact asset bytes verified. Private
custom database dump catalog validated (not an actual restore drill); all 34 public tables preserved
exactly, including the Alembic marker (33 application tables). No schema/data migration;
`application.toml`, `state.json` and `pgadmin-connection.txt` hashes unchanged. No saved workflow replay,
key backfill or credential reset was performed; ordinary pending native jobs may process normally
following startup. This preserved local installation does not establish live/full-milestone qualification.
