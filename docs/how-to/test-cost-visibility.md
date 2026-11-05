# Test current-month cost visibility locally

Use the main Atlas instance after the coordinated milestone upgrade. Preserve its organization.
These checks read synthetic provider facts and do not create OCI resources or send employee mail.
Use an existing active test child with a baseline, or finish a create/import test flow first.

1. Open **Tenancies**. Existing inventory, owner, status, baseline/overrides and configuration
   indicators should remain. The final columns are **Actual/Budget** and **Forecast**.
2. Before its first read, the child shows **Not collected** and unavailable values, never $0 from
   absence. Choose **Refresh costs** at the top to refresh every eligible child, across pages.
3. The request queues work and returns immediately. Wait for the page to update automatically.
   The simulator reads the saved managed Budget and returns explicitly simulated zero actual and
   forecast. It does not copy a newly edited desired budget into a previous observation.
4. Sort using **Actual**, **Budget**, then **Forecast**. Actual and Budget are independent controls
   despite their shared visual column. Search and **Shared tenancies only** should still work;
   missing/unusable money stays last in either direction.
5. Hover/focus/tap the retrieval info button. It shows OTM retrieval time. Escape/outside interaction
   dismisses it. Check at desktop and a narrow window; the page stays within the viewport and the
   inventory table can scroll horizontally.
6. Open a tenancy. **Current month costs** shows observed budget, actual and full month-end forecast.
   Choose **Refresh costs** here; only that child is queued. **Source details** includes computation
   time, cycle facts and period for diagnosis. Reload the URL; remain on the detail page.
7. After work finishes, its acceptance message clears. Operations shows a completed read-only cost
   operation; Audit history includes refresh and read outcomes. It must not claim a baseline/config
   repair or create a badge for a read failure that has no direct lifecycle action.

The ordinary simulator intentionally has no fake-spend/drift controls. Red/amber overrun cases,
partial/null facts, stale/prior-cycle values, wrong scope, late computations, concurrency, exhausted
retries and environment-routed administrator emails are exercised by automated unit/PostgreSQL/
Playwright tests. They cannot all be produced manually from the normal local UI. Real values and
provider error behavior must later be qualified in a staging tenancy.

Daily acquisition is future staging/Kubernetes work. Do not expect a local daily timer; this runbook
uses explicit manual refresh. Historical reports and over-budget emails are outside V1.

After refreshing costs, open **Audit history** and search for **Cost collection worker**. Completed
read events should load with their operation/tenancy links and outcome code. Export CSV should
include the same worker identity. This exercises actual worker evidence, not a human-shaped fixture.
