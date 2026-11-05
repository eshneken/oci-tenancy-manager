# OCI Tenancy Manager

Use `otm` / `OTM` for project identifiers. The production Python package is `backend/src/otm`; the preserved lab is
`prototype/backend/otm`. Use their separate environments and explicit `uv --project` commands;
production code must not import the lab package. The shared coverage gate lives in
`scripts/check_unit_coverage.py`; the prototype entry point delegates to it.

## Code documentation

Follow [the code documentation policy](docs/code-documentation-policy.md) for every change.
Document every class, named function, method, nested helper, async function and test with a meaningful
`#` purpose comment block immediately above the declaration, or above its entire decorator block.
Match the declaration's indentation and leave no blank line before its decorators/class/def.
Class and function docstrings inside their bodies are prohibited. Retain module docstrings and critical
comments inside bodies. Explain invariants, transaction boundaries, retries and destructive-operation
guards. Update documentation alongside code; avoid boilerplate that merely repeats syntax or types.

Run `uv run --project backend python scripts/check_inline_docs.py`, Ruff and checks appropriate to the
change before finishing. The checker verifies above-declaration placement and rejects class/function
docstrings; human/agent review must still assess purpose, accuracy and difficult logic. The user authorizes the
persistent `inline_documentation` subagent for every development slice. Reuse it; if unavailable in a
later session, recreate the role with this same convention and the linked policy. Default reviews to
read-only and coordinate documentation edits explicitly.

Document every application configuration field with an adjacent purpose comment explaining units,
allowed values/bounds and operational effects where relevant. The persistent `inline_documentation`
reviewer must include configuration-field coverage and accuracy in its reviews going forward.

## Infrastructure

In OCI, do not launch a VM that has IMDSv1 enabled. Do not include secrets in code,
documentation, logs or tool output. Keep local connection files under ignored `.local-dev`.

## UI/UX review

The user has authorized a persistent UI/UX review subagent, `ui_ux_review`, alongside the
code-documentation agent. Reuse that agent for UI changes. If it is unavailable in a later
session, recreate the role with the same instructions; this standing authorization applies.
Follow [the UI/UX review policy](docs/ui-ux-review-policy.md) and the approved [UI baseline](DESIGN.md).
Ask the reviewer to check the whole affected flow, shared components, both pages and responsive
layouts. Fix material findings and re-verify before finishing UI work. Preserve the user's live
data; use read-only inspection or an isolated workspace for mutating browser scenarios.
Keep interface guidance, empty states and errors independent of any particular organization.
Real employee names and configured LOB labels belong in data, not hardcoded instructional copy.


## Required testing and merge gates

Follow [the D53 test and merge policy](docs/engineering-test-plan.md#d53-required-test-and-merge-gates).
Unit tests must achieve at least 95% line coverage of first-party application code; measure unit-only
coverage separately for backend and frontend application code, including unimported source files. Add meaningful Playwright
UI integration tests and database integration tests against disposable Docker PostgreSQL. Run every
required suite on every CI build. Any failed test, insufficient coverage or missing/skipped required
result blocks merging into protected `master`. Use PR-only changes and required checks; direct/force
pushes, branch deletion and routine check bypass are prohibited. Configure and verify hosted controls
in P0; these instructions do not imply that a remote CI/protection setup already exists.


Production source must meet the 95% unit-only gate from its first slice. The separate retained
prototype has diagnostic coverage and does not block starting the production foundation; every
ported production module enters the complete-source gate immediately. See the transition rules
in the canonical test policy. Do not hide prototype imports behind an unmeasured production wrapper.

## Design simplicity

Prefer the simplest solution that satisfies the actual V1 requirement. Reuse existing tables,
services and workflows. Do not add a coordinator, journal, service, table or elaborate automation
solely for a rare edge case unless it is critical to correctness/security or an explicit requirement.
For rare recovery cases, prefer an owned manual procedure where adequate. Audit previous designs
for avoidable complexity too. If a material proposal may be too complicated, explain the concrete
failure scenario and the simpler alternative, then ask the user before adopting the extra machinery.
Do not silently weaken essential authorization, destructive-target checks, secret handling or D53
quality gates in the name of simplicity. D54 selects Vault CURRENT for normal recovery-password
retrieval and manual paused database restore; the withdrawn C6-A control/journal is not V1 work.


## Repository layout and design finalization

Keep executable organization lab code/tests/data/contracts and lab-only design under `prototype/`.
Keep current application design under `docs/engineering-design`, production contracts under
`docs/contracts`, approved screens under `docs/walkthroughs` and production ER under `docs/architecture/diagrams`.
Historical alternatives in `reference/history` do not supersede current decisions. Preserve reusable
prototype business logic/tests; do not carry local actor/reset/synchronous-success bypasses into production.
Complete an independent Astra design review and address material findings before final user signoff.
Do not commit, push, create a PR or publish the repository before the user approves the finalized design.


## Independent security review — D56

The user authorizes a persistent `security_review` subagent alongside documentation and UI/UX
reviewers. Reuse it for every completed development slice and security-sensitive change; recreate
from [the security review policy](docs/security-review-policy.md) if unavailable in a future session.
Review application/OWASP risks, secret/PII exclusion, direct/transitive dependencies, images/IaC and
CI supply chain. Use independent read-only review with exact scope/evidence; fix blocking findings,
re-review changes and record disposition before slice completion/merge. Never publish real employee
data, secrets, private keys, raw screenshots or HR feeds to GitHub, including a private repository or
CI artifacts. Preserve originals locally; use synthetic repository fixtures. Current local design
examples are not yet cleared for publication. Add required automated `security` checks in P0; an
agent review does not replace scanners, negative tests or live provider qualification. No Git
check-in/publishing is authorized before final user design approval and the publication review.


## Selected visual direction — D57

The user chose **original A / Field Console (left)** after comparing it with rounded A2 on
28 October 2026. Follow [DESIGN.md](DESIGN.md): navy navigation, cobalt accents, cool light
surfaces, crisp 3px corners and technical typography. Do not introduce A2's 9px rounding or
B/C/D styling without a later user decision. Preserve approved workflows, accessibility and
security; this visual decision does not authorize Git check-ins or publishing.


## Saved local preview consistency

Saved review instances on 8443/8444 must serve a per-instance snapshot of qualified built frontend
assets. Do not point their running APIs at the mutable shared frontend/dist while building the next
slice: a new form can otherwise reach an older in-memory API. Publish frontend and backend together,
with the existing private backup, migration and preserved-data checks. Disposable tests may use the
working build. Keep normal development serving and stable saved-review serving distinct.


## Documentation table of contents

[docs/README.md](docs/README.md) is the top-level documentation table of contents. When adding,
moving, removing or materially changing documentation, update that index and affected section
indexes in the same change. Every intentional docs subdirectory must be directly referenced.
Keep current design, implemented reference, operating procedures and historical checkpoints distinct;
public links must resolve within the publication candidate, not depend on ignored local evidence.


## Incremental GitHub checkpoints — 5 November 2026

The user approved sanitized public source checkpoints after repository review. Keep public OCI
provider/API information, but no source-organization names, corporate contacts, real business-segment
labels, private feeds or internal project observations. The required public candidate checks are
`scripts/publication_guard.py`, `scripts/check_secrets.py` and `scripts/check_design_docs.py`, in
addition to application tests, independent reviews and dependency scans. Asset-manifest changes need
privacy/provenance review; never add broad secret-scanner exceptions to silence findings.

The initial qualified checkpoint established master; baseline `db08b3b` has all five hosted
Checkpoint jobs passing and protected master verified with administrator enforcement. Thereafter
use one pull request per completed coherent milestone, grouping related implementation slices,
fixes, tests and documentation. Keep small local commits; optional privacy-checked feature-branch
backup pushes may preserve unfinished work without opening a PR. Normally maintain one active
development PR. Every reviewed milestone must pass all five required gates; administrator
protection, PR-only master merges, no force pushes and no branch deletion remain unchanged.
Do not use initial-bootstrap or backup-push authorization for routine direct master updates or
bypasses. Keep commit metadata publication-safe and use the configured GitHub no-reply identity.
Update docs/README.md and affected section indexes with documentation structure changes.
