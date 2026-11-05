# Delete an individual or shared tenancy

31 October 2026 · Local provider simulation; no real OCI termination

[Registry guide](organization-workflows.md) · [Production journey](../engineering-design/01-domain-and-journeys.md) ·
[Implemented ER](../architecture/diagrams/organization-workflows-implemented.mmd)

## Screen flow and meaning

Open **Tenancies → tenancy name → Delete tenancy**. This is a tenancy-level decision and works for
both individual and shared registered children. The preview shows exact child/parent OCIDs, every
registered owner/member, their last-known manager role, other current tenancy associations and whether
removing this final association will take them out of the managed directory. The configured
organization root remains in the directory. Source and audit history are retained.

The list is OTM’s tracked associations, not a complete inventory of OCI users an owner may have created.
The action initiates termination of the **entire tenancy and its resources**, including untracked users. It is different from
Remove shared member, which removes only one user's access and leaves resources for manual cleanup.
Shared-impact and manager warnings are shown before one explicit confirmation. All affected
managers, including members, trigger the manager warning. No reason field or extra approver is added.

Acceptance creates one durable operation for one child. The tenancy becomes `terminating`; all its
current associations become `removing`, with every affected person reserved by the same operation.
These remain tracked obligations. Successful **simulated termination initiation** retires all target
links and marks the tenancy `terminated` (the UI says Termination initiated). This does not mean OCI
has completed permanent deletion. V1 does not wait 30 days or monitor final resource destruction.

Each person's other associations are checked independently. A person with other active/pending/
removing associations stays in the managed directory; a last-link person becomes `offboarded`.
Existing directory states on people with remaining obligations are preserved. Remaining absence
work is not dismissed merely because one shared tenancy was deleted. Last-link absence/setup cases
close only after successful publication. No source identity, snapshot or audit record is deleted.

Failures keep the tenancy and every mapping visible as pending work. A second deletion cannot bypass
that reservation. Before any known simulated effect, the existing owner-context Cancel local
simulation restores all target memberships and participant reservations. It never terminates a
second tenancy or compensates for real OCI effects. Real uncertain outcomes remain a later provider
qualification concern; this local facade makes no external calls.

## Admission, dispatch and storage

The browser submits a closed command with a tenancy UUID and preview context. It cannot supply
member IDs or the internal whole-delete flag. Under existing session/grant and workspace locks,
the service derives the complete target set, refuses wrong-parent/parent/unregistered/unqualified
children, rejects conflicting work and checks confirmations. Immutable intent/audit, all reservations
and the native UUID-only job commit together. Replay compares a separate typed deletion-request
hash, so an unchanged retry recovers the same operation even after the original preview is stale.

The worker rechecks authorization/policy and **equality of the entire frozen membership set** before
calling the simulated facade once. It compares each recorded person, role, user/compartment binding,
tenancy revision, target/parent/organization and reservation. Added/changed membership or a newly
unacknowledged manager role blocks execution. Source absence is not a prerequisite for an explicit
tenancy-level decision. Other-tenancy rows are never termination targets.

There is no new table, column or migration. The existing 14-table schema supports this flow:

| Field / UI value | Persisted or derived source |
|---|---|
| Internal whole-tenancy scope | `OrganizationIntent.whole_tenancy_deletion`; server-only, default `false` for historical accepted intents. |
| Complete member identity and last-known role | Existing immutable `intent.associations`, extended with `FrozenAssociation.person_id` and `person_was_manager`; nullable/default `false` preserve old person workflows. |
| Exact target IDs/roles/bindings | Existing FrozenAssociation tenancy/user/compartment/revision fields, not browser-supplied member targets. |
| Pending deletion | Existing tenancy `status=terminating`, memberships `status=removing`, person/link/tenancy operation pointers. |
| Verified local initiation | Existing lifecycle outcome, tenancy status/time and removed membership history. |
| Per-person final disposition | Existing `org_person.directory_status`/pending pointer/absence capture boundary; derived from remaining obligations and protected root. |
| Related cases/history | Existing `org_recommendation`, scoped last-link case closure and one lifecycle-history item per affected person. |

The restricted worker gains only UPDATE(status,resolved_at,resolution,operation_id) on review rows
for these scoped closures. Existing API/worker roles remain separate; no auth-secret permission is
added. Real OCI deletion and its credential/parentage qualification remain behind the facade design.

## Complete public contract dictionary

| Contract | Every field | Meaning/defaults |
|---|---|---|
| `TenancyDeletionCommand` (7) | `kind`, `client_request_key`, `tenancy_id`, `context`, `confirm_manager`, `confirm_shared`, `confirm_deletion` | Fixed kind delete_registered_tenancy; request UUID, registered UUID, full org/registry context. Confirmations default `false`. UI sends warning acknowledgments only after visible impact review and explicit consent. |
| `DeletionPerson` (7) | `person_id`, `name`, `email`, `role`, `is_manager`, `other_tenancy_count`, `leaves_directory` | Server-derived stable identity, current/last-known labels/role and consequences. Other count excludes this target and includes outstanding obligations. Root has leaves_directory=false. |
| `TenancyDeletionPreview` (5) | `context`, `tenancy`, `people`, `manager_warning`, `shared_warning` | Current fenced context, registered TenancyView, complete affected people and required warning flags. |

`GET /api/tenancies/{id}/deletion-preview` is read-only. `POST /api/tenancy-deletions` accepts at most
4,096 bytes of closed JSON, uses the existing session/Origin/CSRF boundary and returns ActionReceipt:
202 queued acceptance or 200 replayed terminal result. Unknown/foreign records are not disclosed.
Malformed bodies, arbitrary affected identities, stale previews and missing confirmations fail
without enqueuing. Generated JSON/TypeScript contracts remain authoritative.

Fresh preview context clears consent, including after background reconnection. Consent/submission
are disabled during preview refresh. Unchanged uncertain retries retain request identity; manual
Reload preview requires new consent. Cancel/Escape closes the native dialog and restores focus.
On sign-out/expiry, one central private-query inventory cancels/removes onboarding/deletion and
other privileged caches. No private preview survives into another administrator's session.
