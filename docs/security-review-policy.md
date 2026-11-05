# Security review policy

28 October 2026 | D56 accepted by user request | Applies to every development slice

[Development plan](engineering-design/18-database-ci-and-build-order.md) ·
[Test and merge gates](engineering-test-plan.md#d53-required-test-and-merge-gates)

## Standing reviewer and completion gate

Use the independent `security_review` subagent when each P0–P5 slice is ready for review, and on
security-sensitive changes within a slice. Reuse the role; if it is unavailable in another session,
recreate it from this policy. This is a standing review responsibility, not an unattended background
service. The implementing agent remains accountable for resolving findings and checking the result.

Give the reviewer the exact candidate revision or local patch, affected flows, relevant tests,
dependency/lockfile changes and sanitized scan results. Review the whole affected trust boundary,
including unchanged callers, jobs, adapters and shared controls. Return evidence-based findings
with severity, file/line, realistic entry point/impact and the smallest adequate correction.
Separate confirmed issues, unverified hypotheses and pilot-only qualification. Never label a
package or application safe merely because one scanner produced no findings.

Record scope, reviewed revision/patch, tools/advisory timestamp, findings, dispositions, verification
and remaining limitations. Re-review security-relevant fixes or later changes that invalidate the
review. No slice is complete without this review; no affected PR merges while blocking findings or
required security checks remain unresolved. Keep reviews lightweight; do not add a security service,
custom scanner platform or separate job coordinator for this requirement.

Review is read-only by default. Use synthetic data and disposable environments for reproduction;
no live OCI mutations, production probing, real employee-data upload or outbound messages are
implicitly authorized. Report locations and safe diagnostics, never secret values or actual HR rows.

## Assets, inputs and boundaries

OTM can provision/delete OCI children, grant administration, change policies and disclose recovery
credentials. Review admin SSO/entitlement, browser/API/CLI, CSV ingestion, durable jobs, PostgreSQL,
OCI/Vault/mail facades, parent-versus-child contexts, deployment/IaC and CI credentials.
Treat all uploaded fields, request parameters, stored text, provider responses, file names and
repository/PR content as untrusted input. A person being in the organization is not application-admin
authorization. Local prototype actor labels, reset endpoints and simulated-success behavior must not
become production bypasses.

## Application security checklist

- **Authentication and authorization:** validate server-side SSO/session/entitlement for reads,
  commands, exports and secrets; prevent IDOR/cross-workspace or cross-tenancy access. Recheck target
  and authority at dispatch, not just in the UI. Test revoked/stale sessions and forged identifiers.
- **Injection and untrusted content:** parameterize SQL values and allowlist SQL identifiers,
  sort/filter names and dynamic paths. Avoid shell interpolation, unsafe deserialization/eval and
  raw HTML insertion. Use context-appropriate output escaping; test stored/reflected/DOM XSS.
  Treat exported CSV formulas safely. Validation complements escaping/parameterization; it does not
  replace them. OCI policy/quota statements are privileged configuration, never shell/Python code.
- **Browser and API:** address CSRF for cookie-authenticated mutations, restrictive CORS, secure
  session cookies, appropriate CSP/security headers, safe errors, secret-response cache controls,
  authorization on direct API calls and bounded uploads/parsing. Guard traversal, file-type spoofing,
  malformed encodings and resource exhaustion; reject unnecessary active document formats.
- **Outbound calls and credentials:** block SSRF through caller-supplied OCI/domain/mail URLs;
  validate actual target/domain/realm, TLS and qualified endpoints. Keep per-target credentials
  scoped, never fall back to another signer, never expose private keys or recovery passwords in
  job payloads, logs, telemetry, traces, exports, URLs, browser storage or persisted screenshots.
- **Destructive/concurrent operations:** inspect registered-child and protected-target guards,
  object bindings, explicit activation-user cleanup target, last-admin checks, atomic audit/job
  acceptance, idempotency and unknown-outcome handling. Test negative cases, not only success.
- **Infrastructure/data:** private authenticated TLS database/Vault access, least-privilege runtime
  and CI roles, no runtime DDL/audit rewriting, restricted network/RBAC/container privileges,
  reviewed migrations/backups and independent credential recovery. Never launch an OCI VM with
  IMDSv1 enabled.

D39/D40 explicitly select an MFA exemption only for the exact persistent recovery identity;
review its scope, custody, audit/notifications, CURRENT resolution and original four-hour rotation
window. Do not extend it to owners/members or app SSO, claim universal logout, or invent a temporary
named-access flow. The selected exception is not a blanket exemption from security review.

## No secrets or real employee PII in GitHub

This applies even to the planned **private** repository, its history, issues/PR bodies, logs,
CI artifacts, releases and container build contexts. Real employee names, email addresses, reporting
relationships and source HR exports stay in approved local/runtime storage. Application processing
of authorized employee data at runtime remains necessary; committing that data is not.

Before the first commit, P0 must inventory and review the complete proposed publish set. Preserve
original samples privately; replace publishable fixtures, seeded configuration, walkthrough examples,
documentation, generated contracts/reports and images/decks with consistent synthetic data, such as
`person@example.test`. Re-render images after sanitizing their source; inspect OCR/visible text and
embedded metadata. `.gitignore` alone neither sanitizes files nor removes already tracked history.

Current local HR samples, lab screenshots, dated design evidence and pitch/reference artifacts are
excluded by default. Current design prose/walkthroughs and some prototype source/test expectations
still contain real identities; **the repository is not cleared for publication yet**. Convert tests
that depend on private source exports to meaningful synthetic fixtures before publishing or CI;
do not include the real workbook to make a test pass or weaken the required test gate.
Validate the build, required tests and documentation links in a clean export/checkout of only the
approved publish set, not just the working directory where ignored private files are still present.
Replace or remove references to private artifacts before publishing; do not unignore raw HR/evidence
just to satisfy a broken link or test. Only sanitized, reviewed replacements may be publication-listed.

Run a local secret scan over candidate files and any Git history **before the first commit and
every push**; a CI scan alone would happen after publication. Also review staged text for PII and inspect non-text artifacts.
Require a passing publication review and synthetic-fixture validation; never print discovered values.
If a credential is exposed, block publication, notify the owner privately and revoke/rotate it;
removing a file or making a repository private is not credential remediation. PII needs removal from
all affected published surfaces under the organization's process. No history rewrite or external
notification is performed automatically by this reviewer.

## Dependencies and build supply chain

P0 must implement a minimal toolchain that covers first-party static analysis, secret scanning,
Python and frontend dependency advisories, and deployable images/IaC as those artifacts appear.
Select compatible tools during setup; examples are `pip-audit` for Python, the chosen frontend
package manager's audit, and an image/IaC scanner. These are proposed tool choices, not installed or
passing controls. Check direct **and transitive** runtime/development dependencies against current
advisories using the exact resolved lockfiles; record advisory freshness and scanner failures.
Do not hide failures behind blanket ignores or mark an unavailable scan successful.

For new packages and significant updates, review the necessity, exact name, source/publisher,
maintenance, install/build scripts, unexpected network/native-code behavior, transitive additions
and available integrity/provenance. An advisory scan cannot prove absence of malicious code.
Use approved registries; prevent public/private index confusion and unreviewed Git/URL dependencies.
Keep toolchains and dependencies locked, use frozen infrastructure-services and integrity checks, and update through
reviewed, tested changes. Inventory build/test/scanner tooling as well as runtime modules.

Pin GitHub Actions to reviewed full commit SHAs, deployable base images to reviewed digests, and
Terraform providers/modules to locked versions or immutable revisions as applicable. Keep CI token
permissions minimal; untrusted PR code must not receive production credentials or privileged runner
access. Do not execute untrusted PR code through a privileged `pull_request_target` path. Protect
deployment environments/credentials, scan and inventory the exact built image, and promote only
artifacts produced by a successful trusted build. Use short-lived workload credentials where qualified.

## Merge and release disposition

Known secrets/real employee PII in the publish set, malicious dependencies, exploitable injection,
authorization/target-isolation failures and confirmed critical/high findings block merge/release.
Fix confirmed medium/low findings as part of the slice, or obtain an explicit human disposition with
impact, compensating controls, owner and expiry/revisit point before treating the slice as complete.
Only the human owner can accept residual risk; the agent cannot waive controls or silently suppress
scanner findings. False positives need evidence and narrowly scoped reviewed suppressions.
Existing accepted product decisions remain binding; changes to them require a user decision.

Add a required `security` CI job to every build for automated checks. Its failure, absence or skipped
required scan blocks `required-ci` and protected-master merging. Independently record the subagent
review as part of slice/PR acceptance; a PR's self-written 'passed' file is not trusted approval.
Use a normal maintainer review/checklist rather than inventing a review bot. P0 must demonstrate a
seeded synthetic secret and a deliberately vulnerable fixture/dependency are detected and block the
gate without ever using a real credential or publishing an unsafe dependency in the application.

## Primary guidance

Use applicable controls from [OWASP's verification/cheat-sheet mapping](https://cheatsheetseries.owasp.org/IndexASVS),
[SQL injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
and [input validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).
Follow [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).
[PyPA's pip-audit scope](https://github.com/pypa/pip-audit) explains why advisory checks complement
package/provenance review rather than certifying supply-chain safety.


## Policy review checkpoint — 28 October2026

The independent `security_review` subagent reviewed D56 and found no material missing requirement.
It identified private source samples and existing sample-dependent tests as P0 publication work.
Default ignore rules were checked for seven sensitive artifact/runtime paths; all were excluded.
Git currently tracks zero files. These checks validate policy/path controls, not the absence of
PII/secrets elsewhere or application/dependency security. No full security scan was performed.
