# Prototype tenancy associations and offboarding

19 October 2026

The local prototype now keeps a real PostgreSQL registry of **simulated** tenancies and person
associations. Creating an entry is a local database operation, not evidence that OCI created a
tenancy. No OCI calls, real OCIDs, credentials, compartments or identity grants are involved.

## Two structures, two meanings

The source organization answers “What does the latest feed report?” It retains employee profiles,
manager relationships, immutable source observations and historical revisions. The managed directory
answers “Who is awaiting onboarding or still associated with a managed tenancy?” Explicitly
completed offboarding can hide someone from that directory without altering the reporting graph.

A first baseline does not invent tenancies or assert that every employee is a new hire. Baseline
profiles with no tracked associations remain visible. Newly detected profiles also remain visible
while an administrator decides how to onboard them. Zero associations alone never silently removes
a baseline or pending employee.

## Registry and relationships

| Record | Important facts |
|---|---|
| `org_tenancy` | Workspace-scoped stable tenancy ID, display name, individual/shared kind and active/deleted lifecycle state. These are local registry IDs, not OCI OCIDs. |
| `org_tenancy_association` | Stable person ID linked to a registered tenancy, owner/member role and active/removed state. Historical associations remain inspectable. |

A person can own several tenancies and belong to several shared tenancies. A shared owner is
separate from its members. Membership removal cannot delete the tenancy. Identity merges retain
the surviving person's stable ID and preserve their ownerships and memberships; conflicting
relationships on the provisional identity must be reconciled rather than discarded.

The versioned administrator configuration stores managed-directory exclusions by stable person ID,
explicit pending onboarding IDs, retained outside-organization IDs and the registry-initialization marker. It does not replace the
registry with configuration-only pseudo-tenancies. Cleaning the lab starts a new empty run; it
archives the prior registry and decisions with the previous run rather than truncating evidence.

## Tenancies inventory screen

**Tenancies** is the first main-navigation destination at `/tenancies`. Its active-only table uses the same
search, LOB filtering, sorting and pagination patterns as Employees. Columns identify the tenancy,
individual/shared type, owner name/email, current owner-derived LOB and member count including the owner.
Click a tenancy or owner to open the existing detail panel. Ownerless legacy tenancies have an
explicit unassigned state and Assign owner repair. Retired tenancies remain historical registry
rows; they are not mixed into this active inventory. Reorgs change the owner's displayed LOB,
not ownership or shared membership. The page owns four summary cards: total active tenancies,
individual, shared and unassigned-owner counts. Its Member count includes the owner; the full
registry endpoint intentionally retains its internal member-only count for ownership/deletion
guards. Employees separately has a sortable Tenancies column counting each person’s active
associations. This screen requires no additional business table.

## Onboarding and association management

Create/import prompts identify a tenancy name and individual/shared type. Both produce a simulated
local registry entry and owner association. Add to shared tenancy selects an existing active shared
tenancy and creates membership, without making the member its owner. A successful choice closes
the employee's setup review. Additional associations can be added later through the person panel;
a completed onboarding decision does not restrict someone to one tenancy.

**No tenancy required** is valid only when no active associations remain. It closes onboarding
and hides the person from the managed directory. It leaves source evidence, reporting relationships
and history intact. The same source row arriving tomorrow does not undo this explicit decision.

Tenancy names and individual/shared classification can be corrected in the prototype. Classification
changes are guarded by the current memberships; shared memberships cannot be silently discarded
by converting their tenancy to an individual tenancy. Ownership transfer selects an eligible,
source-present managed person who is not marked outside the organization, removes the old active
owner association and records the replacement. A replacement who is already a member is promoted
without retaining a duplicate active member relationship.

## Offboard person

Open the person or absence review and inspect **every active association** before confirmation.
Choose an action for each association; an incomplete or stale plan is rejected.

| Association | Supported disposition | Consequence |
|---|---|---|
| Owner of an individual tenancy | Delete, transfer ownership or keep | Delete retires the tenancy and the selected ownership. Transfer preserves the tenancy under the replacement owner. A tenancy with other active members cannot be deleted through individual cleanup. |
| Owner of a shared tenancy | Transfer ownership or keep | Shared ownership must be reassigned before fully offboarding the owner. Member offboarding is never permission to delete a shared tenancy. |
| Member of a shared tenancy | Remove membership or keep | Remove retires only that person's association. Shared tenancy and other people's associations remain intact. |
| No tracked associations | Confirm that none exist | An explicit confirmation is required because an empty prototype registry cannot prove there are no real OCI resources. |

After successful simulation, **no associations remain** means the person is automatically hidden
from the managed directory. There is no redundant Resolve or separate Remove-person step. If any
association is kept, the person stays visible as an outside-organization/association-retained case
even if their feed row later returns. A later pass can complete the remaining cleanup.
Feed reappearance is evidence, not permission to undo a deliberate retained/outside decision.
**Mark returned to organization** (`return_to_org`) is available when the retained person is
present in the latest source; it clears that explicit outside flag and preserves existing
associations. It creates no tenancy and does not replace zero-association Re-onboard.

The registry changes, managed-directory decision, review closure and administrative history are
one local transaction. Failure rolls back the whole command. Every command requires the current workspace/version/configuration context. The UI has no
free-text Reason field: the server generates a factual action description and retains the actor,
action, context and outcome. API/CLI callers may supply an optional reason. Stale dialogs must be refreshed. The
result is labeled simulated success; it never claims an OCI deletion or access cleanup happened.

Managed-person absence and LOB-mapping work is suppressed for explicitly unmanaged profiles.
Source warnings and configuration-level LOB-leader/designee issues remain visible: removing someone
from the managed directory does not make an invalid reporting graph or nomination correct.

## Return and re-onboarding — adopted refinement, 19 October 2026

This supersedes the earlier manual-re-onboarding-only rule for completed offboarding. After a
qualified absence, a fully offboarded person with **zero active associations** who appears in a
later qualified full applied feed automatically returns to the managed directory with a fresh
onboarding review. Old tenancies and memberships are not restored. The feed transaction persists
pending onboarding and clears the relevant exclusion/old setup completion, so the new review
survives repeated present or later missing feeds until acted upon. Staged, rejected and partial
feeds cannot trigger this automatic return.

A still-present employee whose last association was deleted does not automatically re-onboard
from another unchanged present upload: the genuine absence-and-return cycle is required.
**No tenancy required** is an intentional exemption and remains excluded through absence/return
until explicit Re-onboard. That manual control remains available for source-present unmanaged
zero-association employees. It opens onboarding without creating a tenancy.

A person with retained active associations stays outside until **Mark returned to organization**
is explicitly confirmed after source presence returns. This clears outside status while preserving
existing links; it does not create a duplicate onboarding review. Source reappearance alone does
not silently restore retained outside employees. All source/reporting and audit history persists.

## Exercising the flow

1. Load a baseline, then a full feed adding a fictional employee. Open that employee's setup review
   and create an individual tenancy. Confirm the review closes and the association appears.
2. Through the person panel, add membership in an existing shared tenancy. If none exists, create
   a simulated shared tenancy for another eligible owner first.
3. Load a full feed omitting the fictional employee. Open Offboard person and inspect both mappings.
   Delete the individual tenancy but keep shared membership. The person remains visible with the
   remaining association, and the completed decision appears in history.
4. Reopen the person and remove the shared membership. The shared tenancy survives; the person
   disappears from the active managed directory automatically.
5. Repeat the qualified full missing feed, then upload a qualified full feed containing that
   employee again. The zero-association offboarded person returns automatically with a new
   onboarding review; no previous tenancy or membership is restored. Repeat the feed and verify
   the same pending review remains. Try No tenancy required separately: that exemption must remain
   excluded until explicit Re-onboard.
6. Exercise shared-owner departure separately: transfer ownership to an eligible managed person.
   Verify the old owner leaves the active association list while members and tenancy survive.

Use a separate test workspace or Clean workspace for experiments. Do not assume the source employee
count equals the managed-directory count after explicit offboarding or no-tenancy decisions.

## Existing prototype history

Earlier simulated-success decisions did not have registry rows. The compatibility adapter can
reconstruct known create/import ownerships and earlier shared membership for display. Reads do
not write bootstrap data; the first explicit mutation persists it transactionally. A historical
shared target with unknown ownership is marked owner-unassigned rather than assigned an invented
person. **Assign owner** (`assign_owner`) repairs an ownerless shared tenancy by choosing a
present managed employee who is not marked outside. Existing members remain; if the selected
person was a member, their former member association is retired and they become the owner.
New members cannot be added until that owner is recorded. Ambiguous old deletion history is reported and preserves associations rather than guessing
which of several owned tenancies was deleted. New commands use explicit registry selections.

Legacy organization-exclusion configuration remains readable for older runs. Explicit re-enrollment
can clear that exclusion when the source contains the person; new offboarding uses managed-directory
state so the reporting graph is retained.

## Production boundary

Production closes the organizational decision only after a linked workflow is durably accepted.
The person remains Offboarding while required deletion, ownership or membership changes execute.
Failed or ambiguous work remains visible in the tenancy operations workflow. Only successful removal
of the last association completes directory offboarding. The prototype intentionally skips these
asynchronous stages and simulates the successful end state immediately.

Production deletion still requires registered eligible child tenancies, parent verification and
manager/shared warnings. Imported and newly created tenancies have equivalent eligibility. Never
delete an unregistered tenancy or parent, or use shared-member cleanup to delete shared resources.

## Local API contract

`GET /api/local/tenancy-registry` returns the current context, people, active tenancies, unmanaged people,
legacy-bootstrap flag and any compatibility warnings. Person fields include `managed`,
`source_present`, `eligible_transfer`, `status`, `association_count` and association details.

`GET /api/local/tenancies` is the active-inventory list contract for `/tenancies`. Parameters are
`page`, `page_size`, `query`, `lob`, `sort` and `direction`. Sort keys are `name`, `kind`,
`owner_name`, `owner_email`, `lob_name` and `member_count`; pagination/filtering operate on the
matching active result set. Each row includes `id`, `name`, `kind`, `status`, `owner_person_id`,
`owner_name`, `owner_email`, `lob_name` and `member_count`. LOB is derived from the owner's current
organization rather than copied into ownership. List `member_count` includes all active
associations, including the owner. Full registry `member_count` counts member-role links only for
guards; these two fields have intentionally different scopes. `/api/local/summary.tenancies`
contains `total`, `individual`, `shared` and `unassigned_owner`. Null owner/LOB is displayed honestly. The full
registry endpoint remains available to populate the person/tenancy panels and command previews.

`POST /api/local/tenancy-registry/operate` accepts the current context, `operation`, stable `person_id`
and operation-specific inputs. `reason` is optional; omitting it records a factual server-generated
action description rather than prompting the operator for boilerplate. Operations are `create_tenancy`,
`import_tenancy`, `join_shared`, `offboard_person`, `reonboard`, `return_to_org`,
`no_tenancy_required`, `update_tenancy`, `transfer_owner`, `assign_owner`, `remove_member`
and `delete_tenancy`. Offboarding supplies an exact `plan` with one `association_id`, `action`
and optional `recipient_person_id` per active association. Zero-association offboarding requires
`confirm_no_associations=true`. Transfer/owner assignment uses `owner_person_id`; tenancy edits,
membership and direct actions select `tenancy_id`. The strict request model rejects unsupported
input. These endpoints retain the existing loopback/same-origin local prototype boundary.

Responses report `status`, `operation`, `simulated`, `oci_performed=false`, `person_removed`,
`remaining_associations` and the resulting organization outcome. Re-onboard, no-tenancy and
mark-returned decisions have real local effects and `simulated=false`; external tenancy/access
operations are simulated. The immutable `tenancy_registry_changed` event records the before/after
registry projection, reason and resulting inclusion/association counts in the same transaction.
