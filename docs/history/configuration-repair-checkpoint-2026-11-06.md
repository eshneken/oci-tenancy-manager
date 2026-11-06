# Provider separation and configuration repair — 6 November 2026

This coherent local checkpoint separates provider contracts from their concrete simulators and
adds explicit selected-object configuration repair. It does not enable live OCI, deploy scheduling,
change saved review servers or introduce a database migration.

- [Contract/simulator layout](../reference/provider-layout.md): lifecycle, configuration, budget and
  baseline contracts stay implementation-neutral; concrete classes move to `*_simulator.py`.
  Inspection's validation wrapper and existing deterministic IDs/hashes/guards are preserved.
- [Repair flow and field dictionary](../reference/configuration-repair.md): fresh complete confirmed
  evidence authorizes an exact selected-object preview. The modal shows current/expected values,
  preserves uncertain request identity across close/reopen, and confirms the frozen assignment.
- The existing native configuration worker repeats authority/context/binding guards, writes only
  selected objects and independently observes all four categories. Acceptance and failure retain
  findings; complete verification preserves unselected drift and seals final-generation evidence.
  No new desired revision, table, provider registry, fallback or simulator-control UI is added.

| Local validation | Result |
| --- | --- |
| Backend unit-only complete-source gate | 1,302 tests; 8,431/8,789 lines, 95.9267%; all 125 application source files |
| Frontend unit-only complete-source gate | 422 tests; 1,729/1,775 lines, 97.40%; all 34 application source files |
| Full disposable PostgreSQL/native worker/HTTPS Playwright | 1,590 tests; zero failures, errors or skips; no timeout |
| Additional focused new repair SQL/browser run | Five cases pass against a separate owned disposable database |
| Generated contracts | 73 backend schemas current; generated client and production build pass |
| Documentation and purpose comments | Link/model checks and above-declaration comments pass |
| Privacy, credentials, Bandit, Python/npm dependency audits | Pass; no reported leaks or known dependency vulnerabilities |
| Independent documentation, security and UI/UX reviews | Findings corrected; source and responsive desktop/mobile visual review pass |

Browser check and repair scenarios use separate owned installations. Source-age tests authenticate
a fresh session after advancing time; observation aging never bypasses authentication. No timeout,
coverage threshold or merge protection was relaxed. Screenshots and raw diagnostic evidence remain
private local artifacts rather than publication candidates.

This is local qualification, not hosted CI or permission to bypass protected master. No new PR,
remote push, saved-instance refresh, real recipient email or OCI mutation is part of this checkpoint.
Real adapter qualification, access/recovery implementation and staging/Terraform/OKE deployment
remain future milestones. Daily configuration drift scheduling remains deferred until staging.


## All-category coverage follow-up — 6 November 2026

The next local checkpoint closes the earlier automated budget/tag and non-default-override repair
coverage gaps. Changes are confined to tests, synthetic fixtures and documentation; production
code, settings, dependency locks, generated contracts and database schema are unchanged.

- Unit and PostgreSQL each add 16 cases: four managed categories × Missing/Different × inherited/
  override profile. The override profile authors policy/quota blocks and a $650 budget; tags inherit.
  Exact authored values, unselected objects, desired/verified IDs, version counts, later-publication
  pins and repeated native delivery are asserted independently of provider output.
- A real PostgreSQL race uses two distinct simultaneous request keys from the same administrator;
  one operation wins and the competing request is blocked. This is not multi-admin entitlement coverage.
- The native browser journey now repairs policy/quota/budget/tags sequentially, checks expected
  overrides and remaining unselected findings, verifies whole-dollar budget rendering and reloads.
  Its mixed scenario has missing quota and different policy/budget/tag content, not every possible
  browser fault/profile combination. Two UI units add budget/tag value and escaped-text assertions.

| Local follow-up gate | Result |
| --- | --- |
| Full disposable PostgreSQL/native worker/HTTPS Playwright | 1,623 tests pass, zero failures/errors/skips, no timeout |
| Backend unit-only complete 125-source inventory | 1,318 tests pass; 8,431/8,789 lines, 95.9267% |
| Frontend unit-only complete 34-source inventory | 424 tests pass; 1,729/1,775 lines, 97.40% |
| Focused new SQL/native browser run | 22 cases pass |
| Documentation/inline/lint/generated/design contracts | Pass |
| Independent documentation, security and responsive visual review | Pass after comment/prose fixes |
| Publication, credential scanning, Bandit and Python advisories | Pass |
| npm advisories | Blocked by registry TLS certificate verification, including trusted-system-CA retry; not counted as a passing audit |

The unchanged dependency locks do not waive the npm audit. Retry it after connectivity is corrected
before publishing/merging this milestone; TLS verification is not disabled. This local commit is
not hosted CI or a protected-master release. No remote push/new PR, saved-instance refresh, live
OCI action or cloud test was performed. All 13 [real-OCI manual cases](../how-to/configuration-drift-runbook.md#pending-real-oci-manual-validation)
remain Pending; no local drift-injection product feature was added.
