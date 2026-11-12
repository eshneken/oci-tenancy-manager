# GitHub checkpoints

The GitHub repository stores reviewed source checkpoints. Local runtime data, credentials,
organization exports, database backups, browser captures and private review evidence stay outside Git.
The first checkpoint captures the current application honestly; it does not reconstruct historical
slice commits. Public hosting does not itself grant an open-source license. No project license has been selected.

## Development workflow

1. Create a feature branch from current `master` for one coherent milestone.
2. Implement related slices in small local commits, updating tests, reference guides and affected
   diagrams/screens alongside the work. A slice, follow-up fix or documentation correction does
   not need its own pull request.
3. Keep [the documentation index](../README.md) and affected section indexes current. Run the
   required checks and independent documentation, security and UI reviews as applicable.
4. Optional branch backup pushes may preserve unfinished work without opening a pull request.
   They require the same publication/privacy safeguards and never update protected `master`.
5. Normally keep one active development pull request. Open it for the completed milestone,
   grouping its related slices and describing the resulting behavior, validation and limitations.
6. Merge only after all five required checks pass against the reviewed candidate, with administrator
   protection enforced. Use ordinary merges; do not force-push, bypass protections or rewrite
   reviewed checkpoints. A backup push is not merge approval or a completed milestone.

## Verified hosted baseline

For checkpoint `db08b3b`, all five hosted Checkpoint jobs passed and protected `master` was verified,
including administrator enforcement. This establishes the CI/protection baseline, not a waiver for
later milestones: each reviewed candidate must pass its required checks. Preserve PR-only merges,
no force pushes and no branch deletion. Real OCI/deployment qualification remains separate.

## Required checks

[Checkpoint workflow](../../.github/workflows/checkpoint.yml) defines these named lanes:

| Check | Requirement |
| --- | --- |
| Backend unit coverage | All non-postgres backend units; complete-source unit-only line coverage at least 95%; lint and purpose comments |
| Frontend unit coverage | Executed, unskipped unit tests; complete-source line coverage at least 95%; generated types and build |
| PostgreSQL and Playwright | All postgres marked tests, including real HTTP/worker/browser flows and locally captured email; disposable Docker PostgreSQL, no saved app database |
| Security and publication | Full candidate privacy/asset guard, pinned Gitleaks, Bandit and locked Python/JavaScript dependency audits |
| Documentation and contracts | All candidate documentation links/images, top-level section index, generated schemas and design contract checks |

All lanes run for every pull request to `master`, every push to `master`, and manual workflow dispatch.
There are no path-based skips. No private logs, test databases, screenshots or credential files are
uploaded as CI artifacts. The hosted jobs and protections are verified at the baseline above;
workflow or protection changes still require execution and read-back verification, not YAML alone.

### Backend partition and evidence

The backend unit job invokes `scripts/check_unit_coverage.py` (`-m "not postgres"`); the integration
job invokes `scripts/run_backend_postgres_tests.py` (`-m postgres`). Together they execute every
backend test once across the required lanes. The integration job no longer repeats units already
owned by the independently required coverage job. Frontend units remain a separate required job.
This changes test orchestration only: assertions, unit scope, the 95% threshold and required hosted
checks remain intact. The user approved a 600-second aggregate integration budget; individual test
limits remain unchanged. A lane's missing/skipped/timed-out evidence blocks
merge; a passing companion lane cannot compensate. [Canonical policy](../engineering-test-plan.md#complementary-backend-test-lanes).

## Publication checks

Run from the repository root:

```sh
uv run --project backend python scripts/publication_guard.py
uv run --project backend python scripts/check_design_docs.py
```

The publication guard includes tracked files even if their paths would otherwise be ignored, plus
nonignored untracked candidates. It rejects private runtime paths, non-example contact addresses,
private machine paths and unreviewed binary/data assets. Diagnostics contain locations and rule
names, never matched values. [Reviewed assets](../../scripts/publication-assets.json) bind synthetic
CSV fixtures, generated diagram images and user-authorized Atlas artwork to exact hashes.
A changed asset requires privacy/provenance review before updating that manifest.

The guard cannot identify every arbitrary person's name or proprietary observation. Human review of
examples, diagrams, rendered walkthroughs and source provenance remains mandatory. Gitleaks is a
separate credential check, not a substitute for personal-data review. Preserve required upstream
license attribution; do not remove it merely to make a scanner quiet.

## Initial repository setup

The initial reviewed checkpoint established the previously empty `master` branch. Bootstrap was a
one-time setup, not an ongoing direct-push exception. The hosted baseline above now has all five
required checks and administrator-enforced protection. If a later account/repository change prevents
those controls being enforced, report the limitation and stop normal merges; do not substitute a
local policy for hosted enforcement.

Git commit metadata must use an explicitly chosen publication-safe identity. Prefer the GitHub
account's verified no-reply address rather than a corporate mailbox. Never put private names,
contacts, source exports or secrets in commit messages or PR descriptions.

These checks do not qualify live OCI integration, OKE deployment, restore objectives or scheduled
configuration drift. Those remain separate implementation/staging milestones.

## Installed container gate

The Security and publication lane also runs the [container smoke and exact-image scan](container-development.md).
It builds without cache, verifies private build-context exclusion, installed/native compatibility and
restricted disposable PostgreSQL behavior, then blocks on HIGH/CRITICAL image findings or missing
OS/Python scan coverage. This adds no optional result, vulnerability-ignore policy or sixth check.
Private image archives/logs/test credentials are not uploaded. Local ARM64 execution does not stand
in for the Ubuntu runner's AMD64 image execution; hosted results must be verified before merge.
