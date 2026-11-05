# GitHub checkpoints

The GitHub repository stores reviewed source checkpoints. Local runtime data, credentials,
organization exports, database backups, browser captures and private review evidence stay outside Git.
The first checkpoint captures the current application honestly; it does not reconstruct historical
slice commits. Public hosting does not itself grant an open-source license. No project license has been selected.

## Development workflow

1. Create a short-lived feature branch from current `master`.
2. Implement one bounded slice, updating its tests, reference guide and affected diagrams/screens.
3. Update [the documentation index](../README.md) and the affected section indexes when documentation changes.
4. Run the required checks and independent documentation, security and UI reviews as applicable.
5. Open a pull request describing the problem, resulting behavior, validation and limitations.
6. Merge only after all required checks pass against the reviewed candidate. Use ordinary merges;
   do not force-push, bypass protections or rewrite checkpoints that have been reviewed.

## Required checks

[Checkpoint workflow](../../.github/workflows/checkpoint.yml) defines these named lanes:

| Check | Requirement |
| --- | --- |
| Backend unit coverage | Executed, unskipped unit tests; complete-source line coverage at least 95%; lint and purpose comments |
| Frontend unit coverage | Executed, unskipped unit tests; complete-source line coverage at least 95%; generated types and build |
| PostgreSQL and Playwright | Disposable Docker PostgreSQL, real HTTP/worker/browser flows and locally captured email; no saved app database |
| Security and publication | Full candidate privacy/asset guard, pinned Gitleaks, Bandit and locked Python/JavaScript dependency audits |
| Documentation and contracts | All candidate documentation links/images, top-level section index, generated schemas and design contract checks |

All lanes run for every pull request to `master`, every push to `master`, and manual workflow dispatch.
There are no path-based skips. No private logs, test databases, screenshots or credential files are
uploaded as CI artifacts. Defining a workflow does not prove it has run successfully on GitHub.
Hosted required checks and branch protections must be configured and verified separately.

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

The repository remains empty until public-release sanitization and local qualification pass.
The empty repository has no existing base branch. The first reviewed, fully qualified checkpoint
must establish `master` before normal pull requests can target it. This is the one-time repository
bootstrap, not an ongoing direct-push exception. Verify the initial hosted checks, configure PR-only
protected `master` with all five required checks, enforce administrator coverage, prohibit force pushes
and branch deletion, and read back the resulting controls. If the GitHub account cannot enforce these
controls for the repository, report that limitation and stop normal merges; do not describe
local policy or workflow YAML as hosted enforcement.

Git commit metadata must use an explicitly chosen publication-safe identity. Prefer the GitHub
account's verified no-reply address rather than a corporate mailbox. Never put private names,
contacts, source exports or secrets in commit messages or PR descriptions.

These checks do not qualify live OCI integration, OKE deployment, restore objectives or scheduled
configuration drift. Those remain separate implementation/staging milestones.
