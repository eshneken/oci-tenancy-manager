# Organization pages and data contracts

Current implementation: [the simpler working model](organization-working-model.md) and [executable contract](organization-m1-contract.md). Earlier proposed normalized tables/layouts below are historical design context, not the current physical schema.

12 October 2026 | D16 revision-pinning behavior accepted; layout and endpoint details remain drafts

The historical production-layout drafts connect the [organization model](organization-detailed-design.md) to the screen inventory (private historical evidence; not distributed). The dated section below records the implemented local UI; the broader revision-pinning/production API layouts remain design work. The approved visual baseline is [DESIGN.md](../../DESIGN.md), and executable local boundaries are documented in [the M1 contract](organization-m1-contract.md) and [web lab guide](organization-web-lab.md).

## Current design authority — D34, 21 October 2026

The working prototype below remains the approved directory/review UI reference. Current production
navigation labels it **Organization → Organization drift** without changing review semantics.
Organization screens added to configuration walkthroughs are placeholders and must not replace it;
those menu entries are non-clickable until approved content is integrated. Earlier hierarchy/API
wireframes below remain drafts. See [screen authority and common menu](../../docs/ui-screen-authority.md).

## Implemented local screen contract — 19 October 2026

The local prototype now has **Tenancies**, **Employees** and **Exceptions** main-menu screens.
This current contract supplements the historical production-layout drafts below; the local UI
is implemented, while production authentication, revision-pinned browser journeys and durable
OCI operation views remain separate engineering work. See [the local web guide](organization-web-lab.md)
and [association model](tenancy-associations.md) for current behavior.

Tenancies is the first menu item. `/tenancies` lists active registered simulated tenancies, with name, individual/shared kind, owner
name/email, current owner-derived LOB and member count including the owner. Reuse employee-directory search,
LOB filtering, sortable headers, page size, numbered pagination and result ranges. Tenancy and
owner are clickable and open the existing detail dialogs. Unassigned ownership and unknown LOB
remain explicit; deleted tenancies are retained in registry/history but excluded from this active
list. Mobile tables scroll within their panel without page overflow.

`GET /api/local/tenancies` accepts `page`, `page_size`, `query`, `lob`, `sort`, `direction`.
Sort fields are `name`, `kind`, `owner_name`, `owner_email`, `lob_name`, `member_count`. Rows contain
`id`, `name`, `kind`, `status`, `owner_person_id`, `owner_name`, `owner_email`, `lob_name`,
`member_count`. LOB uses the owner's current reporting mapping; it does not rewrite ownership.
Member counts in this list include the owner; full-registry internal member counts exclude owners
for lifecycle guards. Tenancies summary cards use total active, individual, shared and unassigned
owners. Employees exposes sortable `association_count` through its Tenancies column. This read
contract adds no table and performs no OCI discovery. Empty inventory offers the relevant
next step, while filtered no-match results let the administrator clear filters. A request failure
must not be presented as an empty successful inventory. Action dialogs do not request free-text
Reason; the server generates factual descriptions and preserves actor/action/context/outcome.
Qualified full-feed return after qualified absence opens durable onboarding only for fully
offboarded zero-association people, not explicit No tenancy required exemptions or retained links.

## Shared page context

Engineering decision D16, accepted A on 12 October 2026: every hierarchy/person read returns `organization_revision_id`, publication time and source/configuration evidence. The UI keeps the same revision while opening related people/branches and paging an organization result. A new-head banner offers Refresh; it does not silently replace one page's managers while another retains an older revision. Historical context is visibly labeled. Actions use current authorization/eligibility, not a historical page's permission or warning facts.

This consistency guarantee covers organization facts. Tenancy inventory, active operation state, current exception resolution and notification delivery have their own observation/version evidence and may change independently. Label their current/as-of context rather than suggest that pinning an organization revision freezes all application data.

### Accepted refresh and action rules

- Opening the current organization workspace resolves the latest applied revision once. Related branch/person links and pagination carry its ID explicitly; a revision ID is read context, not authorization.
- Observing a newer head only updates the new-data banner. It does not invalidate the selected immutable revision or substitute current records into a response. Notification events and background operations continue independently.
- Refresh selects the latest head and reloads affected organization data coherently. Preserve valid search/LOB/sort controls; reset page position where the changed result set requires it. If the selected person/branch is not represented in that revision, show a clear unavailable-in-this-revision state rather than silently choose another identity.
- Back navigation restores the selected revision and result context. Deep links may carry a revision explicitly; links without one start from the latest applied revision. The final URL/router implementation remains an implementation detail.
- Historical names/addresses/manager chains are displayed as historical facts. Notification recipients and lifecycle previews resolve from current accepted action context, not from stale displayed contact values.
- Entering an action obtains a current preview. If relevant owner, role, shared status, routing, baseline, parentage or access evidence changed, show those differences and require the corresponding refreshed preview/confirmation. Recheck current guards at acceptance/dispatch; the old organization revision cannot waive them.
- An invalid, inaccessible or unavailable requested revision produces a visible diagnostic. Never silently fall back to latest. The exact HTTP/error envelope is defined in the API draft below.

The head-change detection transport/poll interval remains implementation design; D16 does not require websocket infrastructure. Cache keys for organization reads include the revision plus filters, ordering and page; head freshness is a separate query. Actual current registry/operation/check queries retain their own freshness and version keys.

Proposed response sections:

| Section | Required information |
|---|---|
| `context` | Applied organization revision, source snapshot/capture, publication time, configuration revision, completeness assessment and whether the response is historical |
| `person` | Stable ID, full display name, normalized/original current contact, profile/reference status, role evidence and separately recorded profile/reference/census times |
| `accountability` | Direct manager, resolved path/root/LOB/leader, designees, provenance and explicit unresolved reasons |
| `exceptions` | Incident IDs/types and observed evidence; distinguish current resolution/delivery state from historical organization facts |
| `related_tenancies` | Stable tenancy ID/OCID, observed name, owner versus shared-member relation, type/lifecycle and registry observation/version evidence; unavailable until registry integration |
| `pagination` | Requested page/size, total matching count, selected ordering, stable person-ID tie-breaker and organization revision |

Exact DTO field spelling, enums and error envelopes remain draft. Keep normalized source fields and display labels distinct; neither a UI name nor source territory is an identity or inferred LOB key.

## Organization page

Purpose: navigate the accountable hierarchy and inspect known/unresolved branches.

```text
Organization                       [Search people or managers............]
Applied revision / publication     Source capture / coverage   [Feed status]
[New organization revision available                         Refresh]

LOB [All v]   Profile [All v]   Show exceptions [ ]

Hierarchy panel                    Selected branch: Platform Engineering
Organization root                        Leader: Riley Morgan
  Business Applications                       Designees: Robin Lee, Quinn Blake
  Platform Engineering               People count / managed tenancies / exceptions
    Riley Morgan
      Taylor Quinn               Name       Direct manager  Profile  Tenancies
      Jamie Parker                 ...        ...             ...      ...
      Example contributor               sortable headers; linked people/tenancies
  Developer Experience
  Partner Engineering                              [Previous] 1 2 3 ... [Next]  Rows [25 v]
  Data Services
  Infrastructure Services
```

Hierarchy labels may show a configured LOB with its leader; do not insert a LOB as a fabricated reporting relationship. Display arbitrary manager depth beneath leaders. Root and missing-profile references remain navigable with explicit evidence labels. Counts identify their scope: known descendants, incomplete/unmapped branches and current managed-tenancy inventory are not interchangeable totals. The illustration uses user-confirmed labels/relationships; configured mappings still require source reconciliation.

Selecting a manager requests that branch's descendants for the selected revision. Search is an explicit search result view with path/context; it does not erase or invent ancestors to make matches appear connected. Sort/pagination operate on the selected result set. Clicking a person opens Person detail with the revision token; clicking a tenancy opens Tenancy detail with current registry context and the selected organizational context labeled.

## Feed status page

Purpose: distinguish feed delivery, candidate processing and successfully applied state.

```text
Organization feeds                         [Upload development sample]
Applied revision + publication time        [Open organization]
Source + last capture + coverage            Absence detection: eligible / blocked

Delivery / snapshot  Captured  Received  Processing  Applied revision  Diagnostics
...                  ...       ...       ...         ...               ...

Selected intake
Source identity / scope / declared and assessed completeness
Stage + outcome reason + candidate revision inputs
[Diagnostics] [Changes] [Notification intents]
```

Upload is a configured development/intake capability, not a declaration of production census authority. The current sample clearly displays that absence detection is blocked. Diagnostics link affected rows/people and explain missing manager profiles, identity/graph errors, stale ordering or incomplete coverage. No Approve/Reject metadata controls are shown. Automatic publication must remain distinguishable from receipt or validation success.

Duplicate receipts link to the existing snapshot/outcome. Infrastructure failure shows retry/recovery information instead of labeling source data invalid. Receipt history can update independently while the displayed applied revision remains stable. Tables include search/filter/sort/pagination; statuses have text and accessible indicators.

D17 declared-complete input with missing required manager rows displays: **Declared complete; assessed incomplete; eligible metadata applied; absence detection blocked**. Link the missing manager profiles and feed-quality incident/admin notification. Publication and coverage are separate indicators; retained prior manager profiles cannot make the incoming census appear complete. Other validation/trust failures retain their actual rejection/eligibility outcome.

## Person detail page

Purpose: connect identity, source evidence, accountability and owned/shared tenancies.

```text
Person: Casey Rowan                         [Back to branch]
Email / stable identity                    Organizational revision + current/history

Accountability
Direct manager: Taylor Quinn              LOB: Platform Engineering
Accountable leader: Riley Morgan              Designees: Robin Lee, Quinn Blake
Manager path + provenance / unresolved facts

Presence and profile
Last employee row / reference / qualified census
Profile complete or reference-only; absence review separate

Owned tenancies             Shared memberships              Change history
Linked tenancy/name/OCID     Role / compartment references   Before/after evidence
```

Source display names, reported territory and top-manager hints appear in an evidence panel, not as replacements for derived accountability. Reference-only people display the known name/email and missing fields explicitly. Show manager-role evidence conservatively; missing direct reports in incomplete data does not imply an IC.

Future Create/Import/associate actions originate here with the stable person ID. Absence offers investigation and the existing guarded per-tenancy deletion entry point only after registry/lifecycle integration. It never offers Delete employee as a proxy for deleting owned tenancies or shared resources.

## Organization exceptions page

Purpose: separate operational owner/membership investigations from source-quality problems.

```text
Organization exceptions
Category [Ownership v]  LOB [All v]  Status [Open v]  Search [........]

Person  Exception  Last-known manager/LOB  Evidence/time  Related tenancies  Action
...     ...        ...                     ...           ...                ...

Selected incident: source/revision, first/last detection, routing/delivery, history
[Open person] [Open source evidence] [Open tenancy]
```

Categories include qualified owner absence, shared-member cleanup, provisioning candidates, invalid designees and source/identity/ancestry issues. A source-quality omission does not appear as confirmed employee absence. No selection checkboxes or bulk-delete action is implied. Multiple tenancies are investigated individually; missing shared members point to manual user/compartment cleanup information in V1.

Start deletion opens a current per-tenancy preview, validates all existing guards and then asks for explicit confirmation. An alert recipient, incident resolution or data-quality correction cannot authorize lifecycle work. Incident status/notification delivery may change while the source revision/evidence stays immutable.

## Proposed API operation inventory

These are operation names, not committed URL paths:

| Operation | Input | Result / visible failure |
|---|---|---|
| List people/branch | Revision, optional manager/LOB/query, sort, page/size | Consistent records/counts with explicit unresolved facts; invalid filter/revision/pagination diagnostic |
| Get person | Stable person ID, selected revision | Profile/ancestry/accountability and current related-registry evidence; missing identity distinct from unavailable source facts |
| List/get feed intake | Source/snapshot/receipt filters, pagination | Received/processed/applied facts and diagnostics; never imply a failed intake changed the head |
| Submit configured intake | Source binding, request identity, file/envelope | Receipt/status handle; duplicate outcome reference or validation/trust restriction; no synchronous promise of application |
| List/get exceptions | Category/LOB/status/entity filters, pagination | Incident/evidence/current delivery state; qualified absence distinguished from data-quality gaps |
| Get changes | Revision/person filters, pagination | Before/after, actor and source/configuration links; no edit operation |

Review the DTO shapes/state vocabulary and annotated layouts before production API-client generation. M1 can exercise these contracts with synthetic sources and a disposable database; it needs neither a final feed delivery transport nor real OCI tenancies.

## Proposed API read contract examples

The prototype now implements head, people listing/manager-descendant filtering and person-detail reads under the illustrated paths; see [generated OpenAPI](contracts/organization-openapi.json). Other paths/fields below remain proposals rather than implemented endpoints. They make revision handling reviewable before OpenAPI/client generation. All calls require current application entitlement; a stored revision never creates public access to employee data.

| Proposed call | Contract |
|---|---|
| `GET /api/v1/organization/head` | Current applied revision/publication/source/configuration facts, or an explicit no-applied-revision result. This small query can discover new data without reloading pinned tables |
| `GET /api/v1/organization/people?revision_id=...&page=...` | Requested revision, known filters/sort, bounded page size and deterministic person-ID tie-breaker; count and rows read from the same revision |
| `GET /api/v1/organization/people/{person_id}?revision_id=...` | That person's effective profile and accountability in the selected revision; related live registry/incident sections carry separate observation/version evidence |
| `GET /api/v1/organization/branches/{manager_id}?revision_id=...` | Branch membership/path facts from that revision; incomplete paths remain explicit; selected LOB is a configuration-derived view, not a fabricated reporting edge |
| `GET /api/v1/organization/changes?revision_id=...` | Immutable change evidence with bounded pagination and actor/source/configuration links |

Proposed consistent response context:

```json
{
  "context": {
    "organization_revision_id": "<selected revision UUID>",
    "configuration_revision_id": "<immutable configuration UUID>",
    "source_snapshot_id": "<source snapshot UUID>",
    "published_at": "<UTC timestamp>",
    "source_captured_at": "<UTC timestamp or null>",
    "coverage": "<assessed coverage code>"
  },
  "data": "<typed page or detail payload>"
}
```

The actual OpenAPI model uses typed payloads, not a string or arbitrary object for `data`. Unknown timestamps are null with a reason, not invented receipt timestamps. The latest head is fetched separately; a newer head does not turn a valid selected-revision read into a conflict. No implicit `latest` substitution occurs when an explicit ID was requested.

Proposed error codes distinguish unknown/unavailable revision, person absent from selected revision, invalid query and unauthenticated/unauthorized access. Action conflicts are separate and include safe current evidence needed for refreshed review; no secrets appear in errors. Exact error status codes, pagination limits, enums and operation DTOs remain to be reviewed.

## Worked reorganization example

An administrator is reviewing Casey Rowan and his Platform Engineering branch at revision R1, with Taylor Quinn as the direct manager. A synthetic test feed publishes R2 assigning Grant to a different manager. The open R1 page and its next-page/person links still show R1 facts; a banner offers Refresh. Current incident delivery and operations may advance independently and are labeled accordingly.

If the administrator starts a guarded action, the server obtains current R2 accountability and current tenancy/access facts, displays relevant differences and requires refreshed action evidence. Refresh then reloads the organization view at R2. R1 remains available for historical investigation. This is a test scenario, not a claim that Grant actually changed managers.
