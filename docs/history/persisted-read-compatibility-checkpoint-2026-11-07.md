# Persisted cost and user observations — 7 November 2026

[Cost read contract](../reference/cost-visibility.md#retained-results-after-membership-changes--7-november-2026) ·
[Presence read contract](../reference/user-presence-checks.md#retained-results-after-membership-changes--7-november-2026) ·
[Required test policy](../engineering-test-plan.md#persisted-read-compatibility-regression--7-november-2026)

## DEBUG REPORT

- Symptom: previously refreshed costs and required-user presence disappear after shared membership
  changes and subsequent navigation, appearing to require another provider refresh.
- Root cause: stored evidence was not deleted. Financial queries selected the current strict
  source hash, including registry revision. Presence reads compared the whole snapshot hash,
  including registry revision/name. Membership work increments that revision without changing
  the Budget, required users or connection, so those reads hid compatible persisted evidence.
- Fix: read-only financial selection matches the existing source identity excluding registry
  revision, retaining all prior child/parent/organization/baseline/configuration/policy/access/Budget
  fields and exact whole billing profile. It selects one compatible fact/head per child across
  registry revisions. Presence validates original sealed evidence, then compares exact typed
  subjects/connection/policy excluding only registry revision and tenancy display name. Original
  hashes, timestamps and worker/admission/publication fences are unchanged. No database mutation,
  migration, new table, browser cache or automatic provider read is introduced by GET.
- Evidence: before the fix, a new unit reproduction returned an empty presence projection after
  only a registry revision/name change. After the fix, full local gates below pass, including real
  membership work against disposable PostgreSQL and native browser navigation/reload.
- Regression test: test_saved_presence_survives_registry_metadata_changes and fifteen independent
  changed identity/authority cases in backend/tests/test_user_presence_check_units.py;
  test_saved_reads_survive_shared_membership in backend/tests/test_user_presence_checks_postgres.py;
  frontend/e2e/shared-membership.ts verifies both saved sources across add/remove, detail/list and
  reload, exact original observation timestamps and zero additional provider-acquisition POSTs.
- Status: DONE for the simulated application path. Real OCI qualification remains pending in the
  [manual manifest](../how-to/real-oci-test-manifest.md#pending-persisted-cost-and-required-user-read-compatibility).

## Qualification and publication boundary

- Complete backend unit gate: 1,668 passed; 9,401/9,778 lines (96.1444%), all 139 application modules.
- Complete frontend unit gate: 484 passed; 1,853/1,906 lines (97.21%), all 38 application modules.
- Complete disposable PostgreSQL/native HTTPS Playwright suite: 386 passed; zero failures, errors
  or skips, no timeout. Tests run on synthetic fixtures and the current built frontend.
- Existing changed-target publication, stale/unknown, immutable evidence, failure-through-pending,
  workspace isolation and money/cycle coherence regressions remain green. Negative SQL checks
  reject changed billing authority/lineage/identity, foreign scope and nonidentical profile arrays.
- Independent documentation, security and UI reviews pass. UI source is unchanged; the regression
  checks list/detail values and user badges as well as API facts and original times.
- Ruff, purpose comments, 75 generated schemas/client contracts, documentation/link checks,
  publication/secret scans, Bandit and both dependency advisory scans pass. No gate weakened.
- Main 8443 received paired API/worker and immutable frontend after a private backup. All 29
  preexisting public tables preserve exact row counts/content hashes; no new table. Health,
  deep links, frontend bytes and unauthenticated API refusal pass. Parallel 8444 remains healthy
  with the original frontend fingerprint. No live row repair, feed load or destructive replay.
- This is a local checkpoint; no GitHub push or hosted CI result is claimed. Actual OCI readback,
  identity/access changes and provider calculation delays remain separate live qualification.

Reload main Atlas, refresh costs/users once if no compatible observation exists, then navigate
away/back or add a disposable shared member. Saved results retain their original dates until a
new explicit refresh replaces them or their actual source changes. Normal age rules still apply.
