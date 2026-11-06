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
