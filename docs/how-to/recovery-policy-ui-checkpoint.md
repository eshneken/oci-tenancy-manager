# Test recovery-policy checks locally

7 November 2026 · [Qualified local checkpoint](../history/recovery-policy-ui-checkpoint-2026-11-07.md); real OCI remains unqualified

[Current behavior and limits](../reference/recovery-console-verification.md) ·
[Live OCI qualification](real-oci-test-manifest.md#credential-security-lifecycles)

Use the main saved application at `https://localhost:8443` after the qualified matched snapshot is
published. The parallel8444 application remains unchanged. These instructions do not reset an
organization, delete a tenancy or change OCI. Use an employee designated for your local testing.

1. Open **Tenancies** and an existing active tenancy. Find **Required users**. Presence, Console MFA
   exemption and Approved-network restriction are distinct fields. Existing legacy registrations
   without recovery-policy capture cannot establish policy readiness by refreshing.
2. If refresh is disabled, that older record lacks its registered connection/user bindings; use the
   new-setup path below. Otherwise select **Refresh user data**. The request starts one asynchronous read operation. Wait until
   refreshing finishes. Both users may be Present while either policy control is Unable to verify.
   That is expected for older captures; it does not mean the recovery user is missing. Read-only
   refresh never configures/repairs the account or its rules.
3. To exercise a positive new setup, use an eligible test employee's Create tenancy action. Complete
   the normal local simulated activation/handoff and explicit temporary-cleanup review. Do not
   create real OCI resources or upload a private key. A published baseline is still required by
   the existing onboarding flow. The configured recovery-console policy is captured before cleanup.
4. Open the completed tenancy's **Required users**, then select **Refresh user data**. Expect both
   users Present, and both recovery-policy controls **Verified in simulation**. Automation administrator assignments are now checked separately; broader effective
   permissions and password readiness remain unverified; no password-disclosure button is added.
   Import uses the same exact-source validation; it does not trust a matching user name.
5. Check the separately labeled presence/policy dates and follow the **Policy checked (UTC)** date link into Operations.
   Completion means the read finished; individual results remain on the tenancy. No configured
   source-network list appears in the operation or ordinary audit/CSV projections.
6. Navigate away and return, then reload the browser. The dated stored results should persist without
   another provider acquisition. Returning to Tenancies uses the same policy projection. A confirmed
   recovery-policy drift/out-of-date indicator links back to Required users.

There is no product fault-injection panel. Automated unit/PostgreSQL cases cover re-enabled MFA,
weakened/earlier fallback rules, incomplete reads, new desired CIDRs, old queued checks and stale
proof. A desired-policy change makes old policy evidence out of date without changing qualified
presence; a new check compares independent retained fixture facts, never copies desired values into
observed state. Policy distribution/repair is subsequent work, not an effect of a ConfigMap update.

The protected release input/private operator settings are not edited from this page. No interactive
email override or real CIDR list is needed for testing these screens. Actual egress, effective console
precedence, safe policy writes, credentials, four-hour password rotation and30-day key retirement
remain separately qualified against a disposable real child when the provider is available.
