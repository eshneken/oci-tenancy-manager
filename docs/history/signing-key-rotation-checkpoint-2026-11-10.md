# Signing-key rotation targeted UI checkpoint — 10 November 2026

**Targeted local qualification and preserved saved installation PASS.** This is not a fresh
complete-integration, milestone, PR, GitHub or live-OCI qualification receipt.

[Source/field map](../reference/signing-key-rotation.md) ·
[Execution accounting](../engineering-design/23-signing-key-rotation.md) ·
[Operator review after installation](../how-to/signing-key-rotation-runbook.md) ·
[Pending live cases](../how-to/real-oci-test-manifest.md#managed-signing-key-rotation-qualification)

## Scope and evidence

The explicit simulator supports fresh owned signer setup, original-clock day 29/day 30 scheduling,
manual expedite, durable phase checkpoints, exact replacement/old-key retirement, scoped pause/drain,
password closure priority and deduplicated administrator attention email. Candidate migration 0028 adds
one managed head and extends existing constraints; immutable history/outbox reuse existing records.
The material markers cannot sign against OCI. Existing children are not enrolled from inventory.

- Backend complete-source unit gate: **2,305 passed**, no failures/errors/skips;12,613/13,267 lines,
  **95.0705%**,174 source files. Artifact `backend/.local-dev/quality/unit-sffqf70c/summary.json`.
- Frontend final complete-source unit gate: **635 passed**,2,101/2,164 lines, **97.08%**,44 source
  files. Prior failed/intermediate receipts are not substituted for this passing rerun.
- Targeted disposable PostgreSQL/native/SMTP/browser gate: **9 passed**, zero failures/errors/skips,
  no timeout; artifact `.local-dev/quality/backend-postgres-mfc7oyst/summary.json`.
  Includes seven signing PostgreSQL cases plus actual SMTP and native HTTPS/worker/browser coverage;
  responsive views include 1280/900/390/320. It is deliberately **not** the complete integration suite.
- Independent source security, documentation and final responsive UI reviews PASS. Bandit, npm and
  Python dependency audits PASS with zero reported findings; publication guard PASS. Gitleaks PASS
  with the independently reviewed exact 0028 digest exception and all upstream rules retained.
  These checks do not imply complete-suite/PR/live qualification.

Earlier exploratory PostgreSQL runs, failed browser/setup/queue-priority attempts and below-threshold
unit receipts remain diagnostic history. They are not substitutes for the passing artifacts above.
In particular the earlier enrollment exploratory run was PG-only, regardless of its generic browser
flag. Initial future jobs now use priority -1, immediate phase/manual jobs 0 and password closure 100
on the same queue/operation lock; the real native worker exposed and exercised this ordering issue.

## Installation and live boundary

Sole saved main [https://localhost:8443](https://localhost:8443) publication **PASS**. The private
backup/preservation procedure verified all **32 preexisting public tables preserved**, adding only
`otm_signing_credential` (33 public / 29 OTM tables total). Private settings and connection-file
contents were preserved. The saved installation selects frozen backend and frontend release paths;
matching API, native worker and immutable assets started successfully. No second local instance or
live OCI call was used.

The private custom backup's catalog was validated, **not restored as an actual drill**. Restore
qualification remains Pending. No reset, legacy signer adoption/backfill or historical evidence
rewrite is implied. The manual runbook is now usable for a newly onboarded simulated child.

Real RSA generation/signing, exact Vault versions/permissions, OCI identity-domain key CRUD/capacity/
propagation, dynamic current-grant/root-policy capability proof, deployed OKE schedule, credentials
across restore, and overlapping live password-window closure remain Pending in the manual manifest.
The simulator's retained grant/static-root fixture is an explicit limit, not a qualified live proof.

Final source documentation review PASS: declared purpose comments, nonsecret field map, phase/lock/queue accounting and saved-versus-live limits agree. No source edits were made during documentation review.

## Local source checkpoint and formatting note

Local feature commit `6d1ff61` records this targeted UI checkpoint; it has not been pushed or
qualified as a PR/full-suite milestone. The frozen, installed 0028 SQL retains generated trailing
spaces, which `git show --check` reports as formatting warnings. The migration checksum and installed
bytes are preserved; no whitespace-check exemption or historical migration rewrite was introduced.
Check newly generated SQL formatting before freezing future artifacts. This does not change the
passing execution, security, coverage or preserved-data results above.

## Scheduled-start/current-generation clarification follow-up

**Earlier schedule-only gates PASS; publication/UX are covered by the later combined-clarity receipt below.** The original
nine-case installed feature checkpoint above remains separate from this two-case follow-up:

- Backend complete-source unit gate: **2,310 passed**,12,614/13,268 lines, **95.0708%**,174 source files;
  artifact `backend/.local-dev/quality/unit-mb934x2g`.
- Frontend complete-source unit gate: **636 passed**,2,101/2,164 lines, **97.08%**,44 source files.
- Targeted disposable PG and actual HTTPS/native-browser cases: **2 passed**, artifact
  `.local-dev/quality/backend-postgres-uit6c6ax`. Covers future scheduled date, same-operation manual
  expedite removing the date, current generation1→2, responsive layout and contextual return.
- Additive independent security review PASS; the later combined-clarity result below supplies final
  independent UX and matched publication evidence for the expanded patch.

No migration, query deadline or custody behavior changed. These two cases are neither a repeat of the
original nine-case qualification nor a complete integration/full-suite/PR gate. The later combined-clarity publication below supersedes this intermediate unpublished state. Optional derived `scheduled_for` separates earliest scheduled start from
Accepted in Operations, only while a signing rotation is `waiting/signing_rotation_due`. The tenancy
panel distinguishes Current key: generation N from Next rotation scheduled, and confirmation Rotate
now expedites the same operation. No DB column/migration, new schedule or custody behavior is added.

### Combined event-label and schedule clarity — targeted gates PASS

A later addition to the same combined clarity patch introduces omitted-null
`OperationEventView.summary`, a fixed typed-checkpoint projection shared with Audit. Labels separate
staging, upload authorization/verification pending, observation, signer verification, activation with
old retirement pending, removal authorization/verification pending, verified old absence, completion
and attention. Existing history is projected read-only; no migration or payload rewrite. The UI hides
only redundant `SIGNING_KEY_PROGRESS` when a friendly summary exists, retaining failure/final codes.
The earlier two-case schedule follow-up and original nine-case feature receipt remain distinct.
The combined clarity candidate now has its own passing gates:

- Backend **2,324 passed**,12,630/13,284 lines, **95.0768%**,174 source files; artifact
  `backend/.local-dev/quality/unit-j0up8_rh`.
- Frontend **637 passed**,2,101/2,164 lines, **97.08%**,44 source files.
- Targeted disposable PG and actual native HTTPS/browser **2 passed**; artifact
  `.local-dev/quality/backend-postgres-26oz9v4_`. Covers future scheduled date/current generation,
  same-operation immediate start, explicit event headings and responsive scheduled/history views.
- Independent source security and final source/history-visual UX **PASS**, including 1280/320 views.
  Final static/privacy/publication scanners PASS.

These are targeted combined-clarity gates, not a complete integration/PR/full-suite qualification.
Combined clarity **republished successfully to sole https://localhost:8443** with matching frozen
backend, immutable assets and native worker. The private preservation result verifies **all 33 existing
public tables retained**, `new_tables=[]`, private settings/connection file contents preserved,
backend snapshot selected and API/worker started. No migration/schema changes were introduced.
The private backup catalog was verified, **not an actual restore drill**.

The original feature's nine-case receipt, intermediate schedule-only two-case receipt and final
combined-clarity two-case receipt remain distinct; no full-suite, PR or live-OCI qualification is
claimed. Final source documentation review PASS; no source edits were made during this review.
