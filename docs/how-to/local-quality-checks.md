# Local quality checks

28 October 2026 · P0.2 tooling / P0.3 reusable-test checkpoint · Hosted merge gates remain unconfigured

[Progress](../history/development-progress.md) · [Required test policy](../engineering-test-plan.md#d53-required-test-and-merge-gates)
· [Security review policy](../security-review-policy.md)

Run commands from the project root unless a command explicitly changes directory. These checks
below characterize the preserved Python prototype and shared tooling. Production uses its own
[backend setup and coverage gate](../../backend/README.md), enforced from the first production slice.
Prototype coverage remains diagnostic during extraction; it does not describe production coverage
or establish production application readiness.

## Unit-only coverage

```sh
cd prototype
uv sync --locked
uv run --locked python scripts/check_unit_coverage.py
```

The runner executes every non-PostgreSQL test and writes isolated coverage, JUnit, log and summary
files under ignored `.local-dev/quality/unit-*`. It returns a nonzero exit code on test failure,
skipped selected tests, empty collection, missing/invalid reports or insufficient coverage.
It measures every Python module under `backend/otm`, including unimported modules, with no excluded
lines. It checks raw counts against 95%; 94.99% fails even if a display rounds it up. Branch coverage
is diagnostic. PostgreSQL/integration coverage is never combined into this result. Developer scripts
are outside the application denominator; frontend coverage remains a separate future gate.

The current result is **184 unit tests passing, 1,028/1,878 lines covered (54.7391%), 15 source files**.
The runner correctly exits 1. The largest gaps are association/review workflows, repository access,
local HTTP handlers and migration code. Existing PostgreSQL tests exercise much of this behavior,
but do not satisfy the unit-only gate. Add meaningful isolated behavior tests while retaining the
real-database regressions; do not omit modules, relabel integration tests or lower the threshold.

## Disposable PostgreSQL regression tests

```sh
cd prototype
uv run --locked python scripts/run_postgres_tests.py
```

Docker must be available. The runner starts a pinned PostgreSQL image on a dynamic loopback port,
uses generated disposable credentials, runs the full suite and synthetic publication, then stops
only its own container in a `finally` block. It does not use the saved lab connection. On this Mac,
include `<private-local-path>` in `PATH` if Docker is not already available.

Current result: **285 tests passed**, including 101 PostgreSQL cases. The suite retains the
18 gate/schema regressions and adds 120 isolated registry/review/evidence cases. The synthetic publication produced 242 people without reading either private HR feed.
One existing framework deprecation warning remains visible.

## Static analysis and tool installation

```sh
uv run --project prototype ruff check --config prototype/pyproject.toml \
  prototype/backend prototype/scripts scripts/install_security_tools.py scripts/check_c5_contracts.py
uv run --project prototype python scripts/check_inline_docs.py
uv run --project prototype bandit -r prototype/backend/otm
uv run --project prototype python scripts/install_security_tools.py
```

Python tool versions and the Hatchling build backend are locked in `prototype/uv.lock`. Gitleaks is
pinned separately in `scripts/security-tools.json`. Its small installer supports the reviewed
macOS ARM64 and Linux x64 releases, checks the official release manifest and pinned archive SHA-256,
and extracts only the exact regular executable into ignored `.local-dev/tools`. A digest validates
the reviewed archive, not the author's intent or the absence of malicious behavior.

Bandit's five B608 suppressions apply only to reviewed SQL expressions: schema names have a
restrictive identifier regex, table/view names come from fixed allowlists, and workspace values
are bound parameters. `install_guards` validates the schema even for direct callers. Four negative
tests prove unsafe identifiers are rejected before any execution. There is no blanket rule disable
or scanner baseline. Independent review checked these boundaries and the 18 gate/schema tests.

## Dependency and secret scan evidence

The local advisory audit queried **all 64 external exact-version entries** in the lockfile,
including build tooling and platform-inactive dependencies: **zero known vulnerabilities and no
missing/skipped packages** on 28 October 2026. The all-platform inventory is for metadata queries
only, using `pip-audit --no-deps --disable-pip`; it must never be used as an installation requirements
file. Normal installation uses `uv sync --locked`, respecting hashes and environment markers.
Advisory results are time-dependent and do not prove that dependencies are free of malicious code.
The independently isolated design-check script has its own dependency declaration and remains a
separate tool scope; the 64-package result does not silently include it.

Gitleaks scans a local source-only copy of the proposed publish set, with 100% redaction and reports
under ignored `.local-dev/quality`. It does not scan the live database, private input directory or
virtual environments. A generated nonfunctional token-shaped value independently exercises secret
detection; it is deleted after the check. Never add a real credential as a scanner fixture or print
matched secret values. The initial 418 findings were three synthetic UUID identifier references in
C5 design examples. Independent review verified every match; consistent low-entropy valid UUIDs
replace them without adding scanner exclusions. C5 reference/negative checks must still pass.

The P0.2 **167-file** source candidate had **zero secret findings**; subsequent checks are dated
in [development progress](../history/development-progress.md).

Secret scanning does not detect all real employee names or reporting relationships. The local
inventory found corporate email examples in five candidate files, and names/graphics still require
manual review. Neither a clean secret scan nor ignored raw feeds grant publication clearance.
No Git commit, push, repository creation or hosted CI setup has occurred at this checkpoint.

## Remaining P0 gates

- Enforce 95% over all production source as behavior is ported; add the separate frontend gate
  when built. Keep prototype coverage diagnostics and reusable regressions during extraction.
- Finish synthetic replacements and inspect the entire publish set, including rendered artifacts.
- Validate a fresh sanitized export with no saved environment or private inputs.
- After final user design approval and publication clearance, configure required GitHub checks,
  protected `master`, Playwright integration tests and PR-only changes. Local checks are not branch
  protection and cannot substitute for it.
