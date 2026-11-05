# Organization Mapping — manual test runbook

Use the isolated [Atlas Test instance](https://127.0.0.1:8444/organization-mapping), not your current
Atlas at localhost:8443. Complete [parallel-instance enrollment](parallel-local-instance.md) first. All supplied people are fictional
`example.test` identities. This exercise tests the actual application against the simulated OCI
provider; it does not create or terminate real OCI tenancies. Allow about45–60minutes for the full
exercise. Stop after any unexpected result; note the file, its as-of time, employee, action and result.
Do not put real CSV files, credentials or screenshots containing employee data in GitHub.

## Prepare a clean test run

This runbook targets the separate `.local-dev/runbook` installation. Every operator command must
include that explicit directory. Omitting it selects `.local-dev/application`, your original instance.
These full-organization CSVs intentionally omit people from
earlier files; do not upload them over a real organization or a test run you want to retain.

1. Sign in using your enrolled administrator. Confirm the local API and simulation worker are running.
2. Finish or cancel any pending tenancy workflows. A mapping Apply is blocked by unsettled lifecycle
   work. Operations is under Activity & History; complete human steps from the linked workflow.
3. If you want to start empty, use Organization → Reset test organization to view the operator
   instructions, then run this from the repository directory:

   ```sh
   uv run --project backend otm-local reset-organization --directory "$PWD/.local-dev/runbook" --confirm-reset-organization
   ```

   This is destructive to the eight local organization/registry test tables, including mapping
   settings and test tenancies. It preserves administrators, credentials, sessions, operations and
   audit history. It requires the already-enabled local reset setting, refuses unsettled workflows,
   and has no undo. See [the complete reset boundary](../reference/organization-screens.md#local-test-reset).
4. Refresh Organization. It should be empty and require saved mappings before upload.
5. In Application Settings → Organization Mapping, enter:

   | Setting | Value |
   | --- | --- |
   | Root manager email | `root@example.test` |
   | Segment1 name / leader | `Alpha` / `alpha@example.test` |
   | Segment1 designee | `delegate@example.test` |
   | Segment2 name / leader | `Beta` / `beta@example.test` |
   | Segment2 designees | Leave empty |

6. Preview: nominations are unverified before the first feed; no employee impact can yet be
   calculated. Back to editing retains your entries. Preview again and Apply. Reload to verify saved values.

**Upload timing:** each file is a full census. Confirm Complete organization and an accurate
Organization data as of (UTC) on every upload. For this synthetic exercise, pick a starting time
about one hour ago and advance by one minute for **every deliberate new upload**, including repeats
of the same file and corrections. Keep all selected times in the past and within the configured
freshness window. The counter tracks uploads, not file numbers; repeating file02 consumes a new time
before file03. An unchanged transport retry in the same open dialog retains its original inputs,
request key and as-of time; do not edit those just to retry a request with an uncertain result.
If the displayed snapshot says absence inference is not qualified, investigate source policy/profile
diagnostics before expecting absence reviews. Do not weaken validation just to make a test pass.

## 1. Initial organization and basic controls

Upload [00-baseline.csv](organization-mapping/00-baseline.csv) through Organization.

- Seven employees appear. Test Engineer and Shared Member report to Team Manager, roll up to
  Alpha Leader, and belong to Alpha. Beta Leader belongs to Beta.
- Organization Mapping shows role health above the editor and no role defects after this complete feed.
- Leader email is a normal email field. Find designee offers employee suggestions; merely typing a
  partial name does not change the nomination list. Add designee appends an email; avoid duplicates.
- Search, sort and pagination work. Open an employee and confirm Choose an action is the default.
- The first census establishes the baseline; it does not create a new-hire review for every
  existing employee. You can still start tenancy work from employee actions. Having no tenancy
  must not prevent later role-health detection.

Optional tenancy setup for realistic cleanup: create one individual tenancy for Test Engineer,
create a shared tenancy owned by Team Manager, and add Shared Member to it. Finish the simulated
handoff steps using the displayed instructions. Wait for each operation to succeed. Verify the
Tenancies page, owner-inclusive membership counts and employee association counts. Keep Alpha
Leader and Alpha Designee without tenancies so the later test demonstrates role repair without
associated infrastructure. No initial onboarding review is expected for these baseline profiles.
No-association offboarding in step5 must not hide their configured-role defects.

## 2. Preview, cancel and safe mapping edits

1. Change Alpha's display name to Alpha Test. Preview opens a modal with employee impact.
2. Press Escape. The dialog closes, focus returns to Preview changes, and Alpha Test remains in the draft.
3. Preview again, then Back to editing. Same result. Saved directory labels must remain Alpha.
4. Choose Cancel edits: Alpha is restored. No configuration write occurred.
5. Rename to Alpha Test again, preview and Apply. Organization and existing tenancy rows update to
   Alpha Test without changing people, tenancy IDs, owners or memberships. Reload to verify persistence.
6. Repeat to restore Alpha. Try an empty segment name or duplicate leader/segment name: validation
   prevents Apply. Cancel edits to restore valid settings.
7. Check at desktop and narrow width: fields and buttons remain readable, the page has no horizontal
   overflow, and the modal scrolls to every action. Tab/Shift+Tab stay within an open modal.

## 3. New employee and silent metadata update

Upload [01-new-and-metadata.csv](organization-mapping/01-new-and-metadata.csv) at the next as-of time.

- New Engineer appears with a new-employee action item.
- Test Engineer becomes Test Engineer Updated with the same email and tenancy association.
  This is a metadata update, not a second identity or new tenancy requirement.
- Existing closed decisions do not reopen simply because the file was uploaded again.
- Use the new employee's action to create/import a simulated tenancy or add them to the shared
  tenancy. The accepted workflow is tracked in Operations; finish it before continuing mapping tests.
  Alternatively choose No tenancy required. The original onboarding action should close as designed.

## 4. Persistent absence and independent cleanup

Upload [02-employee-absence.csv](organization-mapping/02-employee-absence.csv).

- Test Engineer Updated remains visible with Absence review, including any existing tenancy.
- Upload the same file again with a later source time. It is a new snapshot; the absence stays open
  without creating duplicate open reviews for the same continuous absence.
- If the engineer has an individual tenancy, initiate termination and finish the simulated flow.
  If they also have shared memberships, review and remove those separately through offboarding.
  Their managed profile should not disappear while associations or cleanup remain outstanding.
- Complete offboarding when all associations are gone. The actionable absence closes. Retained feed
  and audit history remain; this is not deletion of historical identity evidence.
- If you choose not to offboard yet, leave the review open and continue. Do not expect a later return
  to silently settle an unfinished administrator decision.

For shared-member cleanup, use Shared Member independently: removing their user/memberships does
not delete the shared tenancy. The owner receives instructions for manual resource cleanup; V1 does
not automatically delete resources from the member's compartment. Finish the operation before the next step.

## 5. Segment leader and designee departures, including people without tenancies

Upload [03-role-departures.csv](organization-mapping/03-role-departures.csv). This removes Alpha Leader
and Alpha Designee and adds Acting Alpha Leader. Team Manager now reports to Acting Alpha Leader.

1. Organization drift should expose the absent employees' cleanup decisions independently of the
   Alpha leader/designee role defects. In Mapping, both invalid nominations remain visible at the top.
   A no-tenancy decision or excluded profile must not hide a configured-role defect.
2. Provisioning is blocked for the affected unmapped employees: Create tenancy, Import tenancy and
   Add to shared tenancy are unavailable until mapping is repaired. Their dialog provides a Repair
   Organization Mapping link. Other branches and departure/tenancy cleanup remain available.
   Complete no-association offboarding for Alpha Leader and Alpha Designee if you want to test it.
   Their role defects must persist even after their ordinary employee cleanup is complete.
3. Follow Repair mapping. In Alpha set Leader email to `acting.alpha@example.test` and remove
   `delegate@example.test` from designees. Preview and Apply. Acting Alpha Leader is a current
   source-present direct report of the root, so the replacement is eligible.
4. Alpha role defects and the affected employees' industry-segment mapping reviews disappear
   automatically. Team Manager's subtree retains Alpha, with the new accountable leader. Acting Alpha
   Leader can still have a separate New employee/tenancy-setup review; mapping repair does not close it. Any still-open Test Engineer absence remains independent. Existing shared/individual
   tenancies keep their IDs and memberships.

Optional multi-segment case: before step03, nominate the same person for roles in multiple segments
and inspect every resulting segment-specific defect. Eligibility still follows each actual reporting
chain; merely being nominated does not grant access or make an out-of-branch designee valid.

## 6. Replace the overall organization leader

Do this **before uploading file04** to exercise a successor absent from the latest accepted feed.

1. In Mapping the root email is normally read-only. Choose Change organization leader: the input
   unlocks and receives focus. Enter `discard@example.test`, then Cancel edits. The saved root is
   restored and read-only again.
2. Choose Change organization leader again and enter `successor@example.test`. Preview.
3. Verify old/new leader emails, the warning that the successor is not in the latest feed, and the
   unresolved reporting-chain count. The source still reports to the old root; OTM must not invent
   new manager edges. Role health and employee-impact entries explain those gaps. No tenancy is deleted.
4. Apply is disabled until I reviewed this leader replacement and its reporting gaps is checked.
   Back/Escape retains the draft; reopening Preview requires confirmation again.
5. Check the confirmation and Apply. The new root is saved and the normal input relocks. Reporting
   gaps are expected until the feed catches up; this action alone must not manufacture departures
   or settle existing cleanup. No new leader/segment is selected automatically.
6. Upload [04-new-organization-leader.csv](organization-mapping/04-new-organization-leader.csv).
   It replaces the root row and makes both current segment leaders report to the successor.
7. After processing, Alpha/Beta ancestry and role health recover. The former root now has an ordinary
   absence review when the complete fresh feed qualifies it; the mapping change alone did not create it.
   With no tenancy associations it can be offboarded independently. Do not remove the new root.
8. Check Audit history: the mapping change has the acting administrator/time and old/new root evidence.
   Expand View changes on the mapping event to see both exact root emails and any segment,
   leader or designee changes. The list and CSV export use the recorded historical values. Existing tenancy ownership/memberships must be unchanged.
9. With no tenancy associations for `successor@example.test`, open the new leader's New employee
   review or employee actions and choose No tenancy required. The setup review closes without
   changing the configured root or descendants' reporting paths. The normal directory can hide this
   exempt profile; turn on Include excluded profiles to inspect it. Alpha/Beta must remain healthy
   and existing tenancy relationships unchanged. Offboard employee and identity merge must not be
   offered for the configured root.
10. Deliberately upload file04 again using the next increasing source time. The successor remains
    exempt and its setup review does not reopen. Use Include excluded profiles if needed; an explicit
    Re-onboard action is available later when source-present and unassociated. Do not choose it during
    this check unless intentionally testing a fresh onboarding episode. Then continue to file05 at
    another later source time. This validates tenancy exemption, not removal of the hierarchy root.

If a new-root CSV is uploaded first and fails validation, the latest **accepted** feed remains the
preview source. Change the root deliberately, then re-upload the corrected CSV with a later as-of
time. A former-root row left in a fresh CSV with no manager is invalid now that it is not the root;
remove that departed row or supply its real new manager. OTM does not repair the source CSV silently.

## 7. Qualified return after completed offboarding

Upload [05-engineer-return.csv](organization-mapping/05-engineer-return.csv).

- If Test Engineer was fully offboarded in step4, the qualified return renews onboarding. The same
  identity returns with its new name; its terminated tenancy/membership must not be resurrected.
- If the absence was still unresolved, it remains an administrator decision. Presence alone must
  not silently close it.
- The repaired Alpha mapping stays assigned to Acting Alpha Leader. Returning or acknowledging an
  old leader/designee never silently replaces saved nominations.

## 8. Stale preview and validation checks

Use a second browser tab, not a different account if only one is enrolled.

- Preview a segment rename in tabA. Apply another valid mapping edit in tabB. Return to A and Apply:
  it must reject the stale preview, retain edits, and require Refresh saved settings plus a new preview.
- Repeat with a newer CSV published in tabB. Same stale-preview rejection.
- Start a tenancy workflow and leave it waiting for manual action. Mapping preview should explain
  the unsettled-work blocker and disable Apply. Finish/cancel the operation, refresh and preview again.
- Upload a copy with a required column missing, an invalid email, duplicate employee rows, or a
  reporting cycle. Inspect the validation diagnostics; the previous accepted organization remains.
  Do not test with real secrets or actual malicious scripts. Text that resembles SQL is still data.
- A CSV missing a referenced manager profile should show coverage/profile diagnostics and cannot
  establish qualified absences. A root-row omission is permitted only under the configured root
  exemption; it does not on its own prove the overall leader departed.

## Record your results

For each section mark Pass / Fail / Not run. For a failure include the section number, file name,
confirmed source time, identity/action and expected versus actual result. Include the Operations
identifier for unsettled workflows. Screenshots should omit passwords, MFA codes and real HR data.

| Checkpoint | Result / notes |
| --- | --- |
| Saved setup and initial census | |
| Preview, Back/Escape, Cancel and mapping Apply | |
| New employee and metadata changes | |
| Persistent absence and final-association cleanup | |
| Leader/designee departure and separate role repair | |
| Overall leader replacement, corrected feed and root No tenancy required | |
| Qualified return without resurrecting access | |
| Stale preview, pending work and CSV validation | |
| Desktop/mobile/keyboard and audit evidence | |
