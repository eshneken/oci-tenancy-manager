# Cost visibility checkpoint — 5 November 2026

[Implemented reference](../reference/cost-visibility.md) · [Manual review](../how-to/test-cost-visibility.md)
· [Financial ER](../architecture/diagrams/financial-implemented.mmd)

The milestone adds current-month financial visibility to the single Tenancies dashboard/detail,
not another inventory. Exact Budget-source facts, independent Actual/Budget/Forecast sorting,
per-value overrun indicators, coherent partial/late observations, explicit degraded state and
accessible retrieval information use the existing durable operation/native worker path. The
read-only facade is simulated; normal local spend is synthetic zero and there is no simulator UI.

Local verification of the application content:

| Gate | Result |
| --- | --- |
| Backend unit-only, complete119-source inventory | 1,260 tests pass; 8,282/8,629 lines, 95.9787% |
| Frontend unit-only, complete33-source inventory | 408 tests pass; 1,692/1,735 lines, 97.5216% |
| Full backend/disposable PostgreSQL/native worker/HTTPS Playwright | 1,532 tests pass, zero failures/errors/skips at application commit5ff3988; seven later unit regressions pass separately |
| Focused financial SQL/native-browser qualification | 12 cases pass, including desktop1280/mobile390/320 and distinct rendering-only response fixtures |
| Inline purpose documentation | 298 Python files pass |
| Documentation links/model checks | 115 documents, 1,533 links; zero errors before this checkpoint note |
| Generated backend/client contracts | 72 backend schemas current; client build passes |
| Publication/Gitleaks/Bandit | Zero findings; exact reviewed candidate initially678files/29approved assets |
| Independent code/security, documentation, UI/UX | All pass after findings corrected |

The full test driver must run serially with any other frontend-building driver in the same
checkout: they rebuild shared frontend/dist and node_modules. Separate checkouts are appropriate
for parallel builds. Browser diagnostics now live in each owned disposable runtime, so another
browser invocation cannot clear its failure evidence. No test threshold or timeout was loosened.

The first local npm advisory calls could not verify the network's registry certificate. After
switching to mobile, the same strict-TLS audit passed with zero vulnerabilities. The [hosted Checkpoint run](https://github.com/eshneken/oci-tenancy-manager/actions/runs/42088304351)
passed its Security and publication job, including both locked dependency audits. Its link records
per-job results for that exact application commit; subsequent documentation checkpoints have their
own hosted run. Neither a local transport failure nor a pending/failed job is treated as a pass. The first hosted
integration job reported one failure; follow-up CI diagnostics expose only bounded source-style test
module/function identifiers, excluding parameter values, assertions, SQL, raw errors and credentials.
The final hosted run must pass before the milestone is declared complete. Seven additional unit
regressions cover this privacy boundary and numeric money ordering before pagination (three monetary
sort keys, both directions, stable ties, stale/null values last). Application runtime source is
unchanged by this diagnostic/test follow-up.

Both saved local preview instances received private restorable database dumps, label-verified forward
migration0021, and matching immutable frontend snapshots with coordinated API/worker restarts.
**All24 pre-existing tables in each database matched their before/after content hashes.** The
15-column otm_financial_collection and 17-column otm_financial_observation tables are installed.
Health, direct SPA route reload, exact asset bytes and unauthenticated API rejection were verified.
No saved organization, membership, baseline, identity, credential or history was reset.

The source is checkpointed on milestone/cost-visibility under the approved batching policy.
Protected master is unchanged; this milestone checkpoint creates no PR. Daily cost/drift scheduling,
live OCI response/currency/cycle qualification, OKE deployment and historical financial reporting
remain separate staging/post-V1 work. Over-budget emails and resource actions remain outside V1;
D48 exhausted acquisition emails use the existing environment-routed outbox.
