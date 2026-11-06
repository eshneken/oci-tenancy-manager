# Local review: Required users and Check now

Use the deliberately upgraded main preview on port 8443 with its matching API, foreground worker and immutable frontend snapshot. Local qualification and preserved-data upgrade pass; reload the main page once. The parallel preview on port 8444 is unchanged and may not offer Check now. Do not reset an existing organization or assume a development build updates either preview. These steps exercise simulated producer fixtures, not OCI.
No real cloud user, permission probe, email or password disclosure is part of Check now.

## 1. Inspect an older registered child

1. Sign in and choose Tenancies → an existing tenancy. Find Required users below registration.
2. Confirm Automation user and Recovery user each show their own identity record. Historical
   children may say Not recorded; some have Recorded identities but no selected connection.
3. Check now must be disabled when the required current bindings/connection are absent, with an
   explanation. Do not interpret this as missing cloud users or try to manufacture a connection.
4. Refresh reloads stored data only. Permissions stays Not checked on both cards. No reset,
   repair, password control or invented successful presence result is expected.

## 2. Create or import a fresh simulated child

1. Use a clearly synthetic employee through the normal Organization action. Create a tenancy with
   a unique lowercase name and subscribed simulated region, or import a simulated child using the
   normal exact-target handoff. Preserve the existing organization; no reset is needed.
2. Pending setup shows Not recorded and setup-in-progress context, with Check now unavailable.
   Continue through the existing handoff, reviewed temporary accounts and explicit cleanup consent.
3. Complete setup and wait for the local verified completion. Fresh opted-in onboarding should
   retain the domain, two permanent identity mappings and selected simulated connection together.
4. Open the now-active child. Both identity records should say Recorded. Expand Identity details
   with keyboard or mouse: the user OCIDs and SCIM IDs differ, the domain is shared, UTC recording
   times and View setup operation are available. Permissions remains Not checked twice.
5. Select Check now. Checking… and dated previous results reflect queued/running work. Keep the
   foreground worker running; Refresh alone cannot execute the job.
6. When the check finishes, expect two Present results for the normal authenticated simulated
   producer fixture and two Permissions: Not checked labels. Each card has its own Checked (UTC)
   time and View check link. These labels establish simulator existence only, not live OCI access.
7. Open View check. Verify the actual read-only required-user operation, safe result and retained
   history. Its tenancy context returns to the child. Check operations never offer repair or create
   an actionable attention badge. The setup operation remains a separate provenance link.
8. Reload the child URL and Refresh. The same recorded IDs and persisted last-check results
   should remain, while timestamps continue to describe their original acquisition.

## 3. Freshness, failures and layout

- At 24 hours after a subject's capture, its result is Check out of date with its last result shown
  separately. Check now starts a new explicit acquisition; it does not alter old audit evidence.
- Missing, unavailable, partial, stale-authority, late callback and clock cases use disposable
  automated fixtures. No product fault-injection control, local simulator CLI or live mutation is
  added. An unqualified read must be Unable to verify, not Missing. Each subject retains its own time.
- If a check submission response is uncertain, Retry check request keeps the same UUID while this
  component remains mounted. After navigating/reloading, inspect Operations before submitting
  again. Do not interpret a request error as proof that no operation was accepted.
- A failed record refresh explicitly labels retained data. Expired/unauthorized access hides facts
  and requires sign-in. No provider work runs on GET.
- Review desktop/tablet/mobile widths and keyboard focus: cards align, stack below 700px, long
  IDs remain contained and the Check now/Refresh/disclosure/source links stay reachable.
- Optional, only for a disposable simulated child: initiate deletion through the existing guard.
  Reopen its saved detail URL; retained retired identities are history, and Check now is disabled.
  This does not assert actual OCI user deletion or final cloud termination.

The [22-field UI map](../reference/required-users-screen.md) and
[check storage/authority reference](../reference/user-presence-checks.md) define the source contract.
All real-provider cases remain Pending in the [OCI manifest](real-oci-test-manifest.md).

## Verification status before manual review

The backend unit, frontend unit and all-postgres/native-browser lanes are independently required.
Final results are 1,556 backend units, all 351 PostgreSQL/native-worker/browser cases and 446 frontend units, each lane passing independently. The complete integration run took 429.457 seconds within the approved 600-second aggregate budget. Earlier 420-second deadline-expired attempts remain invalid full results. Main-preview preservation is verified; the parallel preview is unchanged. This runbook does not authorize a reset or another upgrade. [Final receipt](../history/manual-presence-checkpoint-2026-11-06.md).
[Separate lane ownership](../engineering-test-plan.md#complementary-backend-test-lanes).

## Inventory summary source checkpoint

The summary revision is qualified and installed in the main preview on port 8443; reload it once before review. Port 8444 is unchanged and may not show this follow-up. All 29 preexisting public tables were preserved exactly; no migration or data backfill was added. Preserve existing organization/tenancy data and do not reset. [Final summary receipt](../history/required-users-summary-checkpoint-2026-11-06.md).

1. Open Tenancies. For an active child find Users: … within the existing Status cell, alongside
   existing lifecycle/configuration facts. Inventory configuration badges use Config: (for example Config: Not checked or Config: Drift), while account summaries use Users:. No new column, filter or navigation item is expected.
2. On an older unbound/unqualified child, expect Users: Not checked, not Missing. For a child with
   a fresh successful simulated pair, expect Users: 2/2 present. The link's description contains
   separate Automation/Recovery results and UTC times, simulation and Permissions not checked.
3. Activate the exact child's Users link by keyboard or mouse. The child detail must open at
   the actual Required users section and move focus to its heading after the read completes, including a closed 503 unavailable view. Unauthorized 401/403 must neither focus nor expose retained data. Confirm the same per-user facts in successful cards. Open-in-new-tab and a direct URL reload should reach that same child/section.
4. On a fresh qualified simulated child, use Check now. Checking… is secondary to any retained dated
   result. After completion, the detail and inventory agree without inventing a new check from GET.
5. Verify existing search/sort/pagination controls remain unchanged. At desktop/tablet/mobile sizes,
   the compact link stays within the Status cell and its accessible label matches the Users: prefix and correct child. Config: labels remain distinguishable. At 320 pixels, verify actual page/viewport containment, including the hidden description, without body-level overflow clipping.
6. Mixed missing/unavailable/stale/corrupt-record cases use disposable automated fixtures; no product
   simulator control or live mutation is added. Only fresh confirmed absence is labeled Missing.
   Out-of-date positives must become Check out of date; permissions never become verified. A coarse positive missing its own date/check reference becomes Unable to verify. A configured connection with corrupt canonical references is unavailable, while genuine historical/unconfigured context remains Not checked. These injected failures are automated fixture cases, not live data-edit instructions.

[All summary fields, precedence and query scope](../reference/required-users-summary.md).
