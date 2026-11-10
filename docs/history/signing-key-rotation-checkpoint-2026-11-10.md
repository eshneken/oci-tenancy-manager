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
