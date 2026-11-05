# Local organization workflow exercises

These CSVs contain synthetic people only. They match the sample two-LOB configuration in
[the backend fixtures](../../tests/test_organization_fixtures.py), not your private organization
configuration. To use this sample set in the UI, install that configuration deliberately in an
**empty test organization**. Do not overwrite your current organization's configuration merely
to try the files. Existing personal feeds can exercise the same sequence with their own configured
leaders. The [workflow reference](../../../docs/reference/organization-workflows.md) explains the production model.

1. Load `01-baseline.csv`. The first census establishes the directory without opening onboarding
   reviews for every existing employee. An employee record can still start create/import manually.
2. Load `02-add-employee.csv`. New Engineer gets a New employee review. Start Create tenancy or
   Import tenancy. The review closes on acceptance; follow Operations for verified simulation.
3. Load `03-absence.csv`. The absent employee stays in the review inbox across later feeds.
   Offboard lists every association: delete an individual tenancy, remove shared membership,
   transfer ownership, or explicitly keep an association. The last verified removal excludes the
   employee from the managed directory. Shared compartments/resources are preserved for manual cleanup.
4. After completing offboarding, load `04-return.csv`. A qualified later census reopens onboarding.
   Create/import again to prepare for the rename exercise. Continuous presence alone never reopens
   onboarding after a source-present deletion.
5. Load `05-name-and-email-change.csv`. Pair the absent New Engineer with Renamed Engineer using
   Merge employee identity. The old stable ID and all its registered associations survive; name,
   email and reporting metadata come from the new source identity. No OCI identity is renamed.

Confirm a newer, accurate **as-of UTC timestamp** for each new observation. The files themselves
contain no export timestamp. Repeated bytes are allowed as separate uploads; stale/equal capture
boundaries still cannot establish a newer authoritative census. No-tenancy exemptions remain
exempt until explicit Re-onboard. Name-only changes update metadata automatically.

Use the existing privileged local reset command to start over after pending simulations are handled:

```sh
uv run --project backend otm-local reset-organization --confirm-reset-organization
```

Reset clears the eight organization/registry tables while preserving authentication and audit/
operation history. It requires the local opt-in setting and refuses unsettled lifecycle work. All OCI
lifecycle effects in this checkpoint are local simulations; no cloud users/resources are changed.
