# Review operation return navigation

9 November 2026 · Targeted navigation checks pass; installed in main8443, full native integration not rerun

[URL field map](../reference/operations.md#context-sensitive-return-navigation--source-follow-up) ·
[Follow-up receipt](../history/recovery-password-checkpoint-2026-11-09.md#operation-return-navigation-follow-up)

Use the existing main8443 application with this follow-up’s matched publication. Reload the
**tenancy page**, then reopen its operation link to attach the new origin. Previously open/direct
bare operation URLs cannot infer an earlier origin and retain Back to operations. No other local
instance, data reset, new operation or provider write is required.

1. From an existing tenancy, open a recorded setup/password/check operation link. Verify **Back to
   tenancy** returns to that same tenancy. If the origin was its Required users anchor, retain it.
2. From a recorded check-date link, verify Operations still targets the exact user/check section;
   the return destination and the operation’s result fragment must both remain in its actual href.
3. Reload operation detail, or open the link in a new tab. Verify the same recognized return page
   survives. Open another recorded operation from that context and retain the original destination.
4. Repeat from recognized Organization, Organization drift, configuration, configuration drift,
   Tenancies and Audit History pages. An exact configuration-check UUID origin returns with **Back
   to configuration check**. Follow an existing onboarding baseline or configuration-check link
   from an operation, then Back to operation and Back to tenancy: preserve the original tenancy
   context and any exact check anchor. No arbitrary filters are captured.
5. From the Operations list or a direct operation URL without a recognized return query, expect
   **Back to operations**. Invalid, duplicate or external return inputs must use that same safe fallback.
6. Check keyboard links, focus, responsive placement and ordinary browser Back behavior. Exact
   filter/search/page restoration is not added by this helper; do not infer it from the Back label.

This is navigation only. Existing scope/authentication, recorded dates, user checks, password windows
and provider actions remain unchanged. Validation/install status remains in the linked receipt.

Nested operation-return candidates are bounded to512 characters, reject whitespace and require only
one validated return query and a supported check fragment. Unit/build evidence does not imply the
updated Playwright assertions have been executed; consult the separate receipt.
