# DIY exercise: rename an engineer and add another

> Run lab commands from the repository’s `prototype/` directory. See [setup](../README.md).

14 October 2026 | Local synthetic workspace; no OCI provisioning or messages

Use **`synthetic-lab`** for this exercise. Change the source feed, stage it, inspect the differences,
then apply. A normal `feed` command without `--stage-only` automatically applies valid metadata.
A name override is a different workflow: use it only for a trusted manual correction that must
persist when later feeds disagree. This exercise models changes arriving from the source.

## 1. Open the project directory

```sh
cd "<repository-root>"
uv run python scripts/organization_cli.py --workspace synthetic-lab show context
```

Look for `proposal_status: already_applied`. If it is `pending_application`, finish reviewing/applying
the existing proposal first; if `stale`, refresh and rebuild it. Different proposed/applied UUIDs
do not mean work is pending. Complete any pending proposal before making another full-feed scenario. Creating a newer proposal
supersedes older pending metadata. Do not reset tables or change immutable historical rows in pgAdmin.

## 2. Copy the latest applied source into a new file

This reads the database and writes a local file; it does **not** ingest or apply anything.
It copies the whole current input, preserving existing rows, IDs and manager relationships.
It stops if another source capture is pending or if the target file already exists.

```sh
uv run python - <<'PY'
import json
from pathlib import Path
from sqlalchemy import select
from scripts.organization_cli import local_store

path = Path('.local-dev/scenarios/06-my-changes.json')
store = local_store()
try:
    applied = store.head('synthetic-lab')
    proposed = store.proposed('synthetic-lab')
    if applied is None or proposed is None:
        raise SystemExit('Initialize the synthetic lab first.')
    if applied.snapshot_id != proposed.snapshot_id:
        raise SystemExit('Finish the existing staged proposal before creating another.')
    with store.engine.connect() as connection:
        feed = store.tables['feed']
        payload = connection.execute(
            select(feed.c.data).where(feed.c.id == str(applied.snapshot_id))
        ).scalar_one()
    if payload['envelope']['declared_completeness'] != 'complete':
        raise SystemExit('Use a full source baseline; do not label a partial fragment complete.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as destination:
        json.dump(payload, destination, indent=2)
        destination.write('\n')
    print(path.resolve())
finally:
    store.engine.dispose()
PY
```

For a later experiment, choose a different filename. Do not always start from scenario 05 after
adding people: a complete older baseline could omit newly added employees and flag false absences.
The stored source may differ from applied overrides; the configuration still controls those overrides.

## 3. Edit the copied JSON file

Open `.local-dev/scenarios/06-my-changes.json` in your text editor.
The file contains an `envelope` and a `records` array. Keep all existing rows for this complete-feed exercise.

Find the record whose email is `engineer@example.test`. Change **only** its `full_name`, for example:

```json
"full_name": "Synthetic Engineer Updated"
```

Keep its existing email and `source_record_id`. Those identify the person; changing them is not a
name change and can trigger an identity-conflict rejection.

Append this object as another element of the `records` array, with a comma separating objects:

```json
{
  "source_record_id": "synthetic-new-001",
  "full_name": "Alex Example",
  "email": "alex.example@example.test",
  "manager_email": "two@example.test",
  "manager_name": "Synthetic Leader Two"
}
```

The new source record ID and email must be unique. `manager_email` should identify a manager already
represented by this full feed. Optional top-manager/territory fields may be omitted. LOB and designees
are derived from the trusted configuration; do not add them as extra source fields.

## 4. Give it a fresh source identity and timestamp

Run this **after editing and before ingestion**. It validates the input shape and stamps this new
synthetic capture. The real production source must supply its actual capture time; this is a test clock.

```sh
uv run python - <<'PY'
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import json
from otm.organization.contracts import Intake

path = Path('.local-dev/scenarios/06-my-changes.json')
payload = json.loads(path.read_text())
payload['envelope']['external_snapshot_id'] = 'manual-experiment-' + uuid4().hex
payload['envelope']['captured_at'] = datetime.now(UTC).isoformat()
validated = Intake.model_validate(payload)
path.write_text(validated.model_dump_json(indent=2) + '\n')
print('New capture:', validated.envelope.external_snapshot_id)
PY
```

Keep `source_id` and `population_id` as `synthetic-lab`. Do not change source authority/configuration
through the file. Shape validation does not replace hierarchy/source validation during staging.
Never change a submitted snapshot's contents under its existing source identity. For a new change,
copy/update the file and stamp a new ID/capture. Replaying the exact completed snapshot is a duplicate.

## 5. Stage and inspect

```sh
uv run python scripts/organization_cli.py --workspace synthetic-lab feed .local-dev/scenarios/06-my-changes.json --stage-only
```

Expect **`state: staged`**, with a `proposed_version_id`. If rejected/superseded, inspect diagnostics;
do not proceed to apply. `duplicate` means that input already has a terminal result, not a new draft.

In pgAdmin Query Tool:

```sql
SELECT workspace_id, email, full_name, manager_email, lob_id, evidence, ancestry, absence_review
FROM otm_sample_demo_v2.current_organization
WHERE workspace_id='synthetic-lab'
  AND email IN ('engineer@example.test', 'alex.example@example.test');

SELECT workspace_id, email, full_name, manager_email, lob_id, evidence, ancestry, absence_review
FROM otm_sample_demo_v2.proposed_organization
WHERE workspace_id='synthetic-lab'
  AND email IN ('engineer@example.test', 'alex.example@example.test');

SELECT person_email, field, before_value, after_value, status
FROM otm_sample_demo_v2.organization_reconciliation
WHERE workspace_id='synthetic-lab'
  AND person_email IN ('engineer@example.test', 'alex.example@example.test')
  AND status IN ('ready','blocked_override')
ORDER BY person_email, field;
```

Expected before apply: current retains the engineer's old name and has no Alex row; proposed has the
new name and Alex. Both incoming people have `evidence=feed_row`. Alex's chain resolves through Leader
Two to Synthetic Root, so LOB is `two`. New-person deltas can include multiple fields, not one task per field.

The global `org_person` identity anchor may already exist after staging Alex. That does not make Alex
part of the applied organization and does not create an OCI tenancy. Use the current/proposed views
to judge membership. If a configured override blocks the name change, `blocked_override`/conflict
shows that intentionally different outcome rather than silently overwriting the correction.

## 6. Apply when ready

Copy the `proposed_version_id` from the staging output:

```sh
uv run python scripts/organization_cli.py --workspace synthetic-lab apply <PROPOSED_VERSION_ID>
```

Refresh/re-run the queries. Current now shows the updated name and Alex; metadata rows become
`auto_applied`. Historical person/name/manager versions remain available. A newer feed or config
change invalidates the old preview; restage/review current evidence rather than force an old apply.

No tenancy is provisioned for Alex. This exercise creates organization metadata only.

## Optional: a persistent manual name correction

If the intended change is an administrator correction rather than a feed change, get fresh context
IDs and use the existing `override EMAIL --name "Correct Name" --actor local:admin --reason ...`
command with `--expected-applied`, `--expected-proposed` and `--expected-configuration` IDs.
It applies immediately with audit and persists across later source disagreement. See the
[administrator-correction walkthrough](organization-working-model.md#make-an-explicit-administrator-correction).
Adding a new employee is done through the feed; an override does not create an employee record.

For column meanings, see [the field-value reference](organization-field-reference.md).
