# How to demonstrate Atlas to stakeholders

10 November 2026 · Presenter script · About 30 minutes, with a 12-minute route below

Tell one story: **a directory change becomes a reviewed infrastructure decision, then a managed
tenancy with visible controls and execution history**. Use Organization first, rather than opening
with a tour of every navigation item. This guide describes the current source/reference checkpoint;
rehearse against the installed build before presenting. It does not certify live OCI behavior.

## Before the meeting

- Use the sole saved application, `https://localhost:8443`, with normal administrator sign-in.
  Do not recreate retired8444, create another persistent instance, reset the saved organization,
  alter provider fixtures or change the clock for this demo. This script creates no running instance.
- Run the changing-data story only when the operator has deliberately prepared an authorized,
  entirely synthetic organization. These files are complete replacement censuses: uploading them
  over a real directory could create departures across that directory. If8443 contains data to
  preserve, use only privately reviewed/redacted read-only views approved for this audience. Without
  that clearance, present the synthetic CSV delta and approved synthetic captures instead of the
  real-data app. Do not execute the upload/offboarding/delete steps against those records.
- Confirm API and native worker are available, ordinary test mail routing is correct and no pending
  lifecycle operation blocks the scenario. If a control is unavailable, use the fallback rather than
  relaxing authorization or changing saved settings during the meeting. Do not display credentials,
  private CIDRs, real employee data, raw feeds or private browser/terminal output on the shared screen.
- Keep a published, rehearsed simulated baseline ready: policy statements, quotas, monthly USD
  budget and tag defaults. Use a 500 budget for this story if appropriate to the synthetic setup.
  Use existing validated statement blocks; this is not an OCI policy-writing exercise.
- Check the newest installed qualification receipts for [password access](../reference/recovery-password-access.md)
  and [signing-key rotation](../reference/signing-key-rotation.md). Source changes from another chat
  do not automatically update the saved API/assets/worker snapshot. A legacy child may legitimately
  show Not prepared; use a normally newly onboarded child for the current credential journey.

### Prepare the story, outside the presentation

In **Application Settings → Organization Mapping**, configure this synthetic organization only:

| Setting | Value |
| --- | --- |
| Root manager name/email | Morgan Lane / `morgan.lane@example.test` |
| Segment1 / leader | Engineering / `avery.patel@example.test` |
| Segment2 / leader | Research / `jordan.reed@example.test` |
| Designees | Leave empty for the main story; add eligible synthetic people only for the optional branch. |

Preview and apply the mapping, then upload [01-baseline](stakeholder-demo-01-baseline.csv).
The three supplied CSVs were authored as synthetic examples, not derived from a private HR export.
The baseline contains nine employee rows. Confirm the actual synthetic export time and Complete organization;
the trusted source must also qualify for absence inference. A checkbox alone does not grant that
authority. The first census establishes a baseline and does not create nine new-hire reviews.

Prepare and finish two simulated individual tenancies ahead of time:

- Casey Morgan: `democasey`, to demonstrate identity/association continuity after a metadata change.
- Drew Park: `demodrew`, to demonstrate explicit departure handling with an existing obligation.

Leave Sam absent from the initial feed and Quinn without a tenancy. Keep a supported, unregistered
synthetic import target ready using the existing import rehearsal flow; record its exact OCID privately.
Do not invent a real OCID or try an unverified identifier in front of the audience. If no rehearsed
import target is available, stop at the import preview and explain the handoff.

Record the baseline version, prepared tenancy names, import target and actual source capture times
in private presenter notes. Generate the change export later than the baseline, within the trusted
freshness window and no later than the server clock. Do not use a fixed calendar date or falsify
an old real export's timestamp. For a repeated rehearsal, preserve history and inspect current state;
these files are a first-run sequence, not an idempotent reset mechanism.

## Running order

| Minutes | Scene | Business point |
| --- | --- | --- |
| 0–2 | Organization and accountability | Start with people and reporting ownership. |
| 2–5 | One CSV change, three outcomes | Metadata, joiner and leaver are different decisions. |
| 5–10 | Create Sam's tenancy | Guided setup with verification before temporary-access cleanup. |
| 10–13 | Import Quinn's existing tenancy | Bring existing infrastructure under the same controls. |
| 13–17 | Publish and apply a baseline change | Versioned intent, explicit rollout and local exceptions. |
| 17–20 | Configuration drift and required users | Separate configuration evidence from access evidence. |
| 20–24 | Recovery access | Controlled, audited disclosure with an original rotation deadline. |
| 24–28 | Offboard Drew; delete Quinn's demo tenancy | Employee departure and resource retirement are separate. |
| 28–30 | Operations and Audit History | Close with accountable, durable evidence. |

If setup takes longer, leave the optional branches out. Do not fill queue time by submitting duplicate
actions. After an uncertain response, inspect the recorded operation before starting different work.

## 1. Start with Organization

**Do:** Open Organization. Search Casey, then clear the filter. Point out direct manager, accountable
leader, industry segment and tenancy association. Briefly open Organization Mapping read-only.

**Say:** “The directory tells us who is here and who is accountable for them. Atlas keeps that separate
from which tenancies exist. Mappings are configurable as the organization changes.”

**Show:** Casey is in Engineering and still owns `democasey`. Do not spend time on every column or setting.

## 2. Upload one change and explain the three outcomes

Open the prepared [02-org-change](stakeholder-demo-02-org-change.csv) beside the baseline, or edit
a copy of01 to make exactly these changes:

| Person | CSV change | Expected result |
| --- | --- | --- |
| Casey | Name becomes Casey Taylor; same email; manager becomes Noah Kim and TOP_MGR becomes Jordan Reed. | Same stable person/tenancy; new manager/accountability/Research segment; metadata history. |
| Sam Chen | Add employee row reporting to Priya Shah, TOP_MGR Avery Patel. | New employee with onboarding action. |
| Drew Park | Remove the row; no remaining row references Drew as manager/TOP_MGR. | Qualified absence review; no automatic offboarding or termination. |

**Do:** Choose **Upload organization CSV**, confirm **Organization data as of (UTC)** and complete
coverage, then **Process feed**. Open **Organization drift**. Show **Actionable** and the adjacent
**Informational & history** view in the workflow-enabled screen. Search Casey in Organization and
confirm `democasey` remained linked. An older intake-only screen may say Informational & changes;
it is not the workflow-enabled build needed for this demo.

**Say:** “A normal metadata update applies without recreating the person or moving their tenancy.
The joiner needs a setup decision. The missing employee needs review, because absence is evidence
to assess, not permission to delete infrastructure.”

**Checkpoint:** Sam has setup work, Drew has an absence review, and Casey's recorded metadata changed.
If absence did not qualify, inspect the intake diagnostics instead of claiming a successful departure
detection. A partial feed or still-referenced manager is not a valid shortcut to absence.

## 3. Create a tenancy for Sam

**Do:** Open Sam's actionable review. Select **Create tenancy → Individual**, use `demosam` and one
offered home region. Show the pinned published baseline, then accept and follow **View operation**.

At **Administrator action required**, expand the operator checklist briefly. Explain that real OCI
activation/bootstrap is an administrator handoff. For this local demo use **Use simulated handoff**,
then **Verify handoff**. Review discovered target/access and exact temporary-account cleanup, check
the required acknowledgments and choose **Start setup**. Follow progress until verified completion.

**Say:** “Acceptance records durable work; it does not pretend setup is finished. Atlas verifies
replacement access and the assigned configuration before retiring the exact temporary access.”

**Show:** Sam's tenancy detail, owner, selected/verified baseline and permanent automation/recovery users.
The screen says Local simulation. Do not open OCI or claim a real cloud account was created. Owner
first sign-in is separate from setup verification. Keep this child for the recovery scene.

## 4. Import Quinn's existing tenancy

**Do:** Open Quinn's employee actions and select **Import tenancy → Individual**. Enter the privately
rehearsed synthetic target and accept. Import discovers name/home region; do not describe these as
new create inputs. Follow its normal simulated handoff, review and setup to completion.

**Say:** “The same controls can cover an existing tenancy. Import is explicit adoption of an exact
target, not a name search, recreation, or automatic deletion of existing human administrators.”

**Checkpoint:** A second managed target is visible with an owner, assigned baseline and operation history.
Do not delete it yet; it will illustrate resource retirement at the end.

## 5. Change the baseline, then deliberately roll it out

**Do:** View the published recipe pinned to Sam, then return to **Configuration**'s baseline list.
Choose **New baseline** (or rehearse **Edit draft** first), retain its statement/tag blocks and change
only the monthly budget from 500 to 650 USD. **Save draft**, review, then **Publish** using the normal confirmation.
Refer to the actual version numbers shown; do not assume they are v1/v2.

Open Sam again before starting any rollout. Point out that publishing did not silently reassign it.
From Sam's detail, use the available **Update to baseline** action and its single-tenancy preview;
inspect the target version, accept, and follow the verified result. Open Quinn/Casey to show that
the scoped update did not silently update them. Avoid the fleet action in this story.

**Say:** “A published standard is immutable. Publishing and applying are separate decisions, so we
can see exactly which version each tenancy is using and which update was verified.”

**Optional, +2 minutes:** On Sam use **Manage overrides** to preview a 750 monthly budget while policy,
quotas and tags inherit. Cancel, or apply only if rehearsed. Explain that an intentional accepted
override is expected configuration, not drift. Tags inherit; protected recovery/automation access
cannot be edited through this form. Skip staged policy/quota conflict resolution in the main demo.

## 6. Distinguish the three kinds of drift

**Do:** Open **Configuration → Configuration drift → Checks**, open Sam's exact check and choose
**Check now**. Follow completion and inspect policy, quota, budget and tag-default results.

**Say:** “Organization drift asks whether people and responsibilities changed. Configuration drift
compares managed objects against this tenancy's assigned baseline plus accepted overrides. Access
checks separately ask whether the required users and controls are usable.”

Show **Confirmed drift** and **Checks**. Explain that Not checked, Check out of date and Unable to
verify are not confirmed drift. A newer published baseline is also not proof that the assigned
configuration changed out of band. An empty confirmed queue does not prove every tenancy is healthy.

**If genuine retained findings already exist:** Open expected/observed evidence and explain the
selected-object repair preview. Use preview only unless explicitly rehearsed/approved on the synthetic
target. Check and repair are separate actions; repair restores the assigned effective configuration.

**If no findings exist:** Show Matching and explain the other states. Do not invent a difference,
edit database/provider files or introduce a demo-only drift control. Interactive recovery-network
break/repair is deferred to real OCI; do not break the saved main app to produce that screen.

Return to Sam's **Required users** and choose **Refresh user data**. Show separate automation/recovery
presence, administrator group/role assignments, and recovery MFA/network policy results with their
checked dates. Presence alone is not proof of usable administration. A permission failure must not
be presented as “user missing.” Existing findings/blocked states are valid evidence if present.

## 7. Demonstrate controlled recovery access

**Optional signing-key scene, before requesting any password (+2 minutes):** On a rehearsed current
child, show key inventory/age and the automatic rotation schedule, then its operation. If supported
by the installed checkpoint and approved rehearsal, preview **Rotate key**, acknowledge and **Rotate
now**; otherwise cancel and show the schedule only. Never display key material or advance the clock.
An open recovery-password window can legitimately make key rotation wait; do not promise immediate
completion after opening one. Follow the [rotation runbook](signing-key-rotation-runbook.md).

**Do:** On Sam, open **Administrator access → Request password**. Show the readiness/consent dialog
and **Access and cleanup instructions**. Explain the exact-user-only MFA exemption and approved-network
restriction without displaying private configured ranges. Other users retain MFA.

**Say:** “Recovery is a controlled exception for one account. Before disclosure we require current
presence, assignments, console controls and custody evidence. An authorized request is audited,
notifies the responsible contacts, and starts or joins one original four-hour password-rotation window.”

If access is Ready and test notices/custody have been rehearsed, check consent and **Get password**.
Leave the value masked: do not choose Show password or Copy password. Show the original deadline,
then follow **View password operation** while the dialog is open: the link closes/clears it and opens
the recorded operation. Alternatively, close it and find the operation through Operations. Explain
that closing the dialog does not cancel rotation; there is no supported early-end/close-window action.
Repeated requests do not extend the deadline, and password rotation
does not guarantee termination of existing OCI console sessions. Do not wait four hours on stage.

If Not prepared/Checks required/other blocked state appears, show that guard and its explanation.
Do not relax checks, enable mail or backfill custody during the demo. The local simulated password
cannot sign in to OCI. Keep Sam's tenancy; use Quinn's separate child for the later delete example.

## 8. Handle the departure, then contrast deleting a tenancy

**Do:** Return to Drew's absence review. Explicitly select **Offboard employee**. Review every
association in the plan. For the prepared individual `demodrew`, use **Transfer ownership** to eligible Casey
if rehearsed; otherwise use the rehearsed supported disposition. A transfer preserves the tenancy
and changes accountability. For an individual tenancy the former-user disposition is Remove from
tenancy; Keep as a member is shared-only. Read the exact identity removal and explicitly acknowledge
it. Never improvise an unreviewed destructive branch.

Review the destructive-action checkbox and all warnings before acceptance. Follow Operations to the
verified simulated outcome, then show Drew under the directory's removed/excluded-profile filter.
An absent person is not automatically offboarded, and offboarding does not erase source/audit history.

**Then:** Open Quinn's imported demo tenancy and choose **Delete tenancy**. Read the exact target and
affected people in the preview. Acknowledge the required warnings/consent, accept only the rehearsed
synthetic target, and inspect its operation. Show **Termination initiated**, not “OCI permanently deleted.”

Search Quinn in Organization: the employee is still present. **Say:** “Retiring a tenancy removes its
tracked associations. It does not tell the directory that the employee has left. Offboarding is its
own explicit decision.” If time is short, cancel this deletion preview instead of rushing consent.

**Optional return, +1 minute:** Only after Drew's offboarding completes, generate/upload
[03-return](stakeholder-demo-03-return.csv) with a newer actual synthetic capture time. Show Drew's
same stable directory identity restored by fresh positive feed evidence; onboarding may reopen.
Old tenancies/accounts/associations are not resurrected. An unresolved, never-offboarded absence is
a different case; do not promise that the return silently settles it.

## 9. Close in Operations and Audit History

**Do:** Open **Operations**, use type/state/search filters to find a create/import/check or recovery
operation from this session, then open the exact detail. Show waiting versus queued/running/completed,
step evidence and the contextual return link. In **Audit History**, find the corresponding initiating
decision and worker result. Use the Organization/Operations category, UTC time and exact operation ID;
Audit search is not a general employee-name or summary-text search. Distinguish an accepted request
from a verified outcome.

**Say:** “We started with a change in the directory and ended with explicit infrastructure decisions,
verified controls and a record of who requested what and what the worker actually established.”

Close with the boundary: application decisions and durable history are real locally; OCI-facing
effects use the simulator. Real OCI/IAM/Vault, network login enforcement and production schedules
retain separate qualification. Do not call the demonstration a production-readiness certification.

## 12-minute route

Use existing prepared synthetic records. Spend 3 minutes on Organization and the CSV delta/history,
3 on Sam's create handoff or its completed operation, 2 on the published baseline versus assigned
version/check evidence, 2 on Required users/recovery consent (cancel without disclosure), and 2 on
the departure/delete previews and Audit History. Skip live import completion, baseline editing,
override application, key rotation and the return feed. Explain those branches from their prepared
screens rather than racing through every mutation.

## Fallbacks and aftercare

| What happens | Presenter response |
| --- | --- |
| Saved app contains real data | Use only approved/redacted read-only projections or approved synthetic captures and CSVs. No raw real-data screen sharing or upload/reset. |
| Feed rejected/absence not qualified | Show diagnostics and existing history; confirm mapping, freshness, census authority and no references to the departing employee before a later rehearsal. |
| Queue waits or a command response is uncertain | Open the original operation. Do not submit a second create/import or change request identity to force progress. |
| Import target or new baseline is not rehearsed | Show preview/published history and cancel; continue the story on Sam's prepared child. |
| No confirmed drift | Show a complete Matching check and the checks/confirmed distinction; do not manufacture a fault. |
| Recovery blocked or key rotation waiting | Show the guard and original operation/deadline; do not reset credentials, skip checks or alter clocks. |
| A destructive preview has unexpected impact | Cancel and explain the guard; do not improvise cleanup in front of stakeholders. |

Afterward, retain the operation IDs privately and leave accepted worker/password obligations intact.
Do not reset the organization, delete other demo resources or roll back clocks as an automatic cleanup.
Any further cleanup is a separately reviewed operator action. A hidden password stays out of recordings;
if anything was copied deliberately, clear the clipboard through normal operator handling.

## Source and rehearsal references

- [Organization intake](../reference/organization-screens.md), [mapping](../reference/organization-mapping.md)
  and [employee/association workflows](../reference/organization-workflows.md).
- [Guided onboarding](../reference/tenancy-onboarding.md) and [tenancy deletion](../reference/tenancy-deletion.md).
- [Baseline authoring](../reference/baseline-authoring.md), [updates](../reference/configuration-updates.md),
  [overrides](../reference/tenancy-overrides.md), [drift](../reference/configuration-drift.md) and
  [selected repair](../reference/configuration-repair.md).
- [Required-user screens](../reference/required-users-screen.md), [recovery controls](../reference/recovery-console-verification.md),
  [password access](../reference/recovery-password-access.md), [key rotation](../reference/signing-key-rotation.md)
  and [deferred interactive network repair](../reference/recovery-network-repair.md#manual-local-checkpoint-runbook).
- [Operations](../reference/operations.md), [Audit History](../reference/audit-history.md) and
  [pending live qualification](real-oci-test-manifest.md).
