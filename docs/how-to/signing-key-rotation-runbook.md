# Review managed signing-key rotation locally

10 November 2026 · The checkpoint is **installed in sole saved main 8443**. Targeted qualification and preserved
publication have passed; exact scope is recorded in the
[checkpoint receipt](../history/signing-key-rotation-checkpoint-2026-11-10.md). Do not create a second
local instance or edit saved main provider fixtures/settings to manufacture a fault.

1. Reload `https://localhost:8443` for the installed checkpoint. Use normal authorized simulated
   Create tenancy or Import tenancy and complete its ordinary onboarding/activation/handoff steps.
   A **newly created/imported child is required** for the fresh opted signer-setup contract. Existing
   children deliberately remain Rotation not prepared; refreshing inventory never adopts their keys.
2. Let setup finish. Open that tenancy's separate signing-key panel below Required users. Automatic
   rotation should show Rotation scheduled, next rotation and original retirement deadline. The
   initial waiting operation is scheduling ownership and has not paused child provider work.
3. Open View scheduled rotation to inspect the operation. Back navigation returns to the known local
   origin where provided. No metadata view/operation link retrieves private key material.
4. Choose Rotate key. Confirm the correct child in the preview and review the brief provider-work
   pause; consent begins unchecked. Cancel leaves the durable schedule intact. To proceed, check
   consent and Start rotation. This expedites the SAME scheduled operation, not another generation.
5. Watch the operation/automatic status refresh. It drains prior work and any open recovery-password
   window before taking the child reservation, then stages/uploads/reconciles/probes/activates/retires.
   Cached views and other children remain available. Do not interpret the short-pause design as a
   bounded duration when unknown effects require attention.
6. After verified completion, confirm Last rotation links to the completed operation and a new scheduled
   successor appears with the replacement's original clock. Refresh user data through the normal
   Required users action to obtain fresh public inventory; old sealed inventory becomes stale when
   the head changes and is never fabricated into a fresh observation. Historical checks stay historical.
7. If attention occurs, review the exact operation before the guarded Resume action. Lost request
   responses use Retry same request, preserving its original request key. Do not clear an unknown
   upload fence or manually toggle a running job; hard-crash recovery requires owned paused-worker
   review. Routine progress/success does not imply a new email. Repeated holds of the same operation
   deduplicate administrator incidents; original queued notices remain valid through exact-operation
   resume/activation until the original obligation resolves, subject to frozen-recipient checks.

Day 29/day 30, lost responses, occupied slots, exact-retirement and password-window overlap are covered
by isolated automated fixtures; do not advance the saved app clock or break actual main policy for
this walkthrough. Live versions of these cases remain in the
[manual manifest](real-oci-test-manifest.md#managed-signing-key-rotation-qualification). This UI exercises
nonusable synthetic material only; no PEM, secret locator, Vault value or raw operational CIDR should
be copied into a report. Full milestone/PR and real OCI qualification remain separate.
