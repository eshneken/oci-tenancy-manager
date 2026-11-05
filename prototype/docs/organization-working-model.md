# Working organization model: pgAdmin walkthrough

> Run lab commands from the repository’s `prototype/` directory. See [setup](../README.md).

13 October 2026 | Tested local prototype, not a deployed production application

The implementation now exposes **Applied organization**, **Proposed organization** and
**Reconciliation**. Normal feed ingestion automatically applies valid metadata. Staging is
an inspection option so you can watch the transition; it is not a required approval step.
Exceptions remain for administrator investigation. No OCI resources or real messages are touched.

Read [the full field-value reference](organization-field-reference.md) for `evidence`, `ancestry`,
`absence_review` and `profile`. For your own changes, use the
[DIY rename-and-add-person exercise](organization-diy-feed-changes.md).

## Connect and start here

Use your existing pgAdmin server connection:

| Property | Value |
|---|---|
| Host / port | `127.0.0.1` / `55432` |
| Database / username | `otm_org_dev` / `otm_dev` |
| Active inspection schema | **`otm_sample_demo_v2`** |
| Password | Private `.local-dev/postgres-connection.json`; unchanged |

Refresh the database's **Schemas** tree, expand `otm_sample_demo_v2`, then expand **Views**.
Right-click a view and choose View/Edit Data or open Query Tool. Inspection is encouraged;
use the CLI for mutations so validation, audit and pointer guards run. Do not edit SQL view
rows or table payloads as a substitute for the tested reconciliation workflow.

| View | What it shows |
|---|---|
| `current_organization` | People and reporting/accountability facts currently applied by the tool. |
| `proposed_organization` | Latest eligible source-based proposal, including explicitly labeled retained/reference/configured evidence. Person overrides are excluded. |
| `organization_reconciliation` | Persisted field deltas and exception episodes, with before/after, source/version IDs and processing status. |
| `pending_organization_reviews` | Open and acknowledged exceptions. Acknowledging investigation does not fabricate source recovery. |

Two workspaces are available: **`root-leader-sample`**, the preserved real sample; and **`synthetic-lab`**,
a fictional five-person organization. Always filter by `workspace_id` to avoid combining them.
The sample remains development-only partial evidence: 281 incoming employee rows, 20 missing
manager profiles, 302 retained/configured/reference identities, and no qualified departure inference.

The original eleven-table `otm_sample_demo` schema remains untouched for history/rollback.
`otm_sandbox_before_preserved_copy` is a retained temporary sandbox, not the active model.
A private pre-migration database dump is under `.local-dev/backups`.

## See the initial difference immediately

The lab is left with a staged rename. Current shows **Synthetic Engineer**; proposed shows
**Synthetic Engineer Renamed**. The name delta has status **`ready`**.

```sql
SELECT c.full_name AS applied_name, p.full_name AS proposed_name,
       c.manager_name AS applied_manager, p.manager_name AS proposed_manager,
       c.email
FROM otm_sample_demo_v2.current_organization c
JOIN otm_sample_demo_v2.proposed_organization p
  ON p.workspace_id = c.workspace_id AND p.person_id = c.person_id
WHERE c.workspace_id = 'synthetic-lab'
ORDER BY c.email;

SELECT person_email, field, before_value, after_value, status
FROM otm_sample_demo_v2.organization_reconciliation
WHERE workspace_id = 'synthetic-lab' AND status = 'ready';

SELECT id, applied_version_id, proposed_version_id, configuration_id
FROM otm_sample_demo_v2.org_workspace
WHERE id = 'synthetic-lab';
```

## Apply the staged rename

Run commands from `<repository-root>`.
`show context` now reports `proposal_status` and an explanatory `message`:

- `already_applied`: no application is pending, even though the two version IDs differ.
- `pending_application`: a staged proposal awaits application.
- `no_proposal`: nothing has been staged yet.
- `stale`: refresh/rebuild the proposal against current state/configuration.

This status does not mean all review exceptions are resolved. Applied/proposed IDs belong to
separate immutable records; never use equality as a pending-work test.

Copy `proposed_version_id` only when the status is `pending_application`:

```sh
uv run python scripts/organization_cli.py --workspace synthetic-lab show context
uv run python scripts/organization_cli.py --workspace synthetic-lab apply <PROPOSED_VERSION_ID>
```

Refresh the views: applied/proposed names now match, and the delta becomes **`auto_applied`**.
Both earlier versions remain in `org_version`/`org_member`. Applying the same proposal again
returns its existing result. Applying an obsolete proposal after a newer feed is rejected.

## Try the remaining feeds in order

The generated JSON files are under ignored `.local-dev/scenarios`. They contain only synthetic
`.test` identities and explicit timestamps. The lab's seven-day freshness window is test policy,
not a selected production source contract. If you reuse files later, use an appropriate explicit
`--at` scenario clock or update their source capture/external IDs deliberately.

```sh
uv run python scripts/organization_cli.py --workspace synthetic-lab feed .local-dev/scenarios/02-reorg.json
uv run python scripts/organization_cli.py --workspace synthetic-lab feed .local-dev/scenarios/03-absence.json
uv run python scripts/organization_cli.py --workspace synthetic-lab feed .local-dev/scenarios/04-partial-manager-gap.json
uv run python scripts/organization_cli.py --workspace synthetic-lab feed .local-dev/scenarios/05-reappearance.json
```

Refresh pgAdmin after **each** command:

1. **Reorg:** the engineer moves from `one@example.test` to `two@example.test`; LOB becomes
   Synthetic LOB Two. This metadata applies automatically and creates before/after history.
2. **Absence:** a qualified synthetic complete feed omits the engineer. Identity and last manager
   remain; `absence_review=true` and an open `PERSON_ABSENCE_REVIEW` appear. Nothing is deleted.
3. **Partial manager gap:** the next partial feed omits Leader One's own profile. It cannot establish
   new departures or silently clear prior absence. Look for `MANAGER_PROFILE_MISSING` and retained evidence.
4. **Reappearance:** a complete feed includes everyone again. Absence and manager-gap episodes resolve.
   A future recurrence would be a new episode/notification intent, not a repeated daily alert.

```sql
SELECT full_name, email, manager_name, lob_id, evidence, absence_review
FROM otm_sample_demo_v2.current_organization
WHERE workspace_id='synthetic-lab' ORDER BY email;

SELECT kind, target, status, reason, created_at, updated_at
FROM otm_sample_demo_v2.pending_organization_reviews
WHERE workspace_id='synthetic-lab';

SELECT kind, actor, at, data
FROM otm_sample_demo_v2.audit_event
WHERE workspace_id='synthetic-lab' ORDER BY at, id;
```

## Replaying a scenario

Feed snapshot IDs are immutable and idempotent. Once a scenario is published, submitting the
same file with `--stage-only` reports **`duplicate` / `original_state: published`**, with an
explicit already-applied message. It does not undo the published organization or create a new
proposal. Stage an unused later scenario, or a deliberately new capture/external ID, to see new
differences. Repeating an identical completed scenario is not a reset.

Absent people remain represented with `evidence=retained` and `absence_review=true`; a feed
never removes identities or deletes tenancies. To see an absence/reappearance transition,
compare those fields as well as names/managers. Version IDs will differ even when the applied
and proposed facts have converged.

## Make an explicit administrator correction

Get the current context IDs using `show context` again. A correction requires that exact applied/
proposed/configuration context, an administrator label and a reason. In this local harness the
label is supplied by the operator; production must derive it from authenticated SSO identity.

```sh
uv run python scripts/organization_cli.py --workspace synthetic-lab override engineer@example.test \
  --manager one@example.test --actor local:admin --reason "Verified reporting correction" \
  --expected-applied <APPLIED_ID> --expected-proposed <PROPOSED_ID> \
  --expected-configuration <CONFIGURATION_ID>
```

Applied now honors the correction; proposed still shows what the source said. An
**`OVERRIDE_CONFLICT`** makes that intentional difference visible. Later feeds cannot silently
overwrite the correction. Reuse `override ... --clear` with refreshed context IDs, actor and
reason to remove the override and reconcile to source evidence. Both operations are audited.

Acknowledgment of an exception uses:

```sh
uv run python scripts/organization_cli.py --workspace synthetic-lab acknowledge <RECOMMENDATION_ID> \
  --actor local:admin --reason "Investigating possible transfer" \
  --expected-applied <APPLIED_ID> --expected-proposed <PROPOSED_ID>
```

The exception remains pending with status `acknowledged`. It resolves only when the underlying
supported evidence changes. Fatal source identity/cycle errors require source repair; overrides
are not used to silently rescue an invalid raw-source hierarchy.

## Add a scenario of your own

Edit a **copy** of one canonical Intake JSON file. Keep stable `source_record_id` and email for
existing people. Give each new capture a new `external_snapshot_id` and a later aware `captured_at`.
Keep source/population bound to `synthetic-lab`. Change a name, manager, add a row, omit a person,
or introduce invalid/cyclic input. Submit with `feed FILE --stage-only` to inspect before application,
or with `feed FILE` for the normal automatic workflow.

There is no reset command that discards history. Reinitializing the lab preserves its existing
state/files. Additional scenarios can be supplied through the same CLI; a future UI will wrap
these domain operations after authentication and authorization are implemented.

## Executed coverage and limits

**61 tests pass**: the original 36 tests, 18 workflow/migration tests, four staging/replay regressions, and three explicit workspace-context status tests.
Coverage includes staging, deltas, superseded proposals, invalid/stale inputs, same-feed admin
corrections/routing, persistent overrides/conflicts/recurrence, source-candidate binding, new-person
identity, absence acknowledgment/reappearance, expiration, atomic rollback, immutable evidence,
manager/pointer scope constraints, historical reads and migration preservation/rollback.

Ruff lint/format and named-definition documentation checks accompany the runtime tests.
The two known warnings are TestClient/httpx deprecation and the source workbook's missing default style.

This validates the implemented organization slice, not every future application scenario.
The browser frontend, SSO, durable delivery worker, production migrations, real feed authority,
OCI lifecycle/access/configuration and spend integration remain unimplemented/unqualified.
The outbox stores immutable `intent_only` records and sends nothing. Email-binding correction,
confirmed out-of-scope archiving and arbitrary new override fields remain future workflows.

## Staging replay debug report: 13 October 2026

```text
Symptom: --stage-only returned published and both views remained converged.
Root cause: the source snapshot already had a terminal published result; the public stage
            response did not distinguish replay from a new processing result.
Fix: public staging reports duplicate/original_state and CLI explains already-applied input.
     Re-read terminal feed state after locking to avoid duplicate concurrent publication.
Evidence: two replay regressions failed before the fix; final suite 58 passed, 2 known warnings.
          Replaying scenario 03 now reports duplicate/published without changing applied state.
          Scenario 05 is staged: current absence_review=true, proposed absence_review=false.
Regression tests: backend/tests/test_organization_workflow.py
Related: no reset/undo occurs on duplicate delivery; source identities/captures remain immutable.
Status: DONE
```

Scenario 05 was staged during this investigation. Scenario 04's earlier capture cannot replace
that newer proposal; use a deliberately new source ID/capture if testing the partial-gap case later.


### Named rollups and required actions (14 October update)

Refresh `otm_sample_demo_v2.current_organization` and `proposed_organization` in pgAdmin.
Both now show accountable leader name, LOB name, designee names/configuration status, known-manager
status and required actions. Filter `tenancy_setup_review = true` to see employee profiles added
since the initial census. The local additions Manager Next and Engineer Deep should appear here,
without altering your edited feed or applying a new version. This is setup **review** until the
application has a tenancy registry to distinguish creation, import and shared association.
See [field values and identity-change limitations](organization-field-reference.md).
