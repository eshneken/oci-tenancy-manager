# Organization field values

19 October 2026 | Values used by the current local implementation

These columns describe separate facts. Source presence, reporting-chain completeness and an
administrator-defined LOB assignment must not be treated as the same status.

## ancestry

| Value | Meaning |
|---|---|
| `root` | The configured root person. the configured root in `root-leader-sample`; Synthetic Root in `synthetic-lab`. |
| `resolved` | The effective manager chain reaches the configured root. |
| `incomplete` | A complete chain to the root cannot be established, for example because a manager's upstream relationship is unknown. |

A resolved chain can still lack a configured LOB. An incomplete chain is not proof that the
person departed. Cycles and invalid identity conflicts reject the candidate rather than becoming
normal valid ancestry values. Values are declared on `PersonState` in the executable contracts.

## evidence

| Value | Meaning |
|---|---|
| `feed_row` | This person has their own employee row in the feed used for this version. |
| `retained` | The person's own row is missing, but their previously established employee profile is carried forward. They may still be mentioned by another row. |
| `reference` | The person is represented through references, such as another employee's manager/top-manager, without an established employee-row profile. |
| `configured` | Trusted administrator configuration introduced the person, such as the root, a leader/designee or supplemental relationship, without an employee-row profile. |

Evidence is a classification of the person's representation in the selected version, not the
provenance of every attribute. For example, `feed_row` can coexist with an administrator override
of the manager. Exact manager provenance and source observation times remain in `org_member.data`;
configuration and audit records preserve correction evidence. If a real employee row arrives,
it takes precedence over reference/configured classification.

## absence_review

| Value | Meaning |
|---|---|
| `true` | An unresolved absence-review condition exists. A qualified, fresh, complete source omitted a previously observed person without current supported presence evidence. Administrator investigation is required. |
| `false` | No current absence-review condition is recorded. This is not independent proof that the person is still employed by the company. |

A person may have `evidence=retained` and `absence_review=false`: a partial/unqualified feed
omitted their row, so there is no basis for a departure conclusion. A previously established
absence review remains true through later feeds; reappearance does not close it automatically.
An explicit administrator resolution is required; returning presence enables Resolve / keep returned employee.
References can be positive presence evidence even without an employee row, subject to the
implementation's ancestry/presence rules. Missing required manager profiles block census inference.

The person and last-known role/reporting/ownership evidence remain represented for investigation.
The flag never deletes a person/tenancy or revokes access. Departure, transfer, feed error, owner
reassignment and shared-member cleanup are distinct administrative outcomes.

## profile

| Value | Meaning |
|---|---|
| `employee` | An employee row established this person's profile, possibly in an earlier retained version. |
| `reference` | Their profile is known only through references. |
| `configured` | Their initial profile comes from trusted configuration. |

`profile=employee` does not guarantee a row in this particular feed; use `evidence` for that.

## Other visible processing values

| Field | Current values |
|---|---|
| Context `proposal_status` | `no_proposal`, `already_applied`, `pending_application`, `stale`; completion uses recorded feed/application links, not equality of version UUIDs |
| `org_version.kind` | `proposed`, `applied` |
| `org_feed.state` | `received`, `staged`, `published`, `rejected`, `superseded` |
| Identified delivery replay response | `duplicate`, with `original_state`; conflicting reused input is `integrity_conflict`. Each manual/CLI CSV upload instead gets a fresh snapshot ID, even for identical bytes. |
| Metadata recommendation status | `ready`, `auto_applied`, `blocked_override`, `superseded` |
| Exception recommendation status | `open`, `acknowledged`, `resolved`, `ignored`; source warning resolutions are automatic, actionable resolutions are explicit |
| Notification outbox state | `intent_only`; the prototype does not send messages |
| Declared/assessed completeness | `complete`, `partial`, `unconfirmed`; a claim alone does not qualify absence |

See [the table guide](organization-er-diagram.md), [working walkthrough](organization-working-model.md)
and [DIY name/add-person exercise](organization-diy-feed-changes.md). The implemented field declarations
are in [contracts.py](../backend/otm/organization/contracts.py); evidence classification is in
[store.py](../backend/otm/organization/store.py).


## Named accountability and action columns

The current and proposed SQL views now append these readable columns. Names and LOB labels
come from the selected version's members and frozen configuration, so a staged reorg can be
compared with the current organization without mixing reporting structures.

| Column | Meaning |
|---|---|
| `accountable_leader_name` | Name of the configured top-level accountable leader in this version; null if no leader/name is established. |
| `lob_name` | Organizational rollup/LOB label from the selected version's configuration, such as Platform Engineering. Null means no configured LOB assignment. |
| `known_manager` | Whether reporting relationships establish that this person manages someone; managers can also require a tenancy. |
| `designee_names` | Names corresponding to the validated `designee_emails`; falls back to email when a name is unavailable. |
| `designee_status` | `assigned`, `not_configured`, `needs_review` (some configured designees could not be validated), or `no_lob`. |
| `tenancy_setup_review` | Employee profile established after the workspace's initial applied census, including a reference/configured profile subsequently enriched by an employee row. |
| `tenancy_association_status` | The SQL organization-only views retain the compatibility value `not_tracked`; it does not mean zero associations. Use registry/API `association_count` and `management_status` for current local tenancy relationships. |
| `required_actions` | Distinct open/acknowledged person-specific exception kinds, plus `TENANCY_SETUP_REVIEW` for a later employee profile. |

`TENANCY_SETUP_REVIEW` means investigate whether to create, import, or associate an existing
individual/shared tenancy. It never provisions anything. Initial census employees are not
all flagged for creation: many already have tenancies. This is a provisional, history-derived
read-model indicator, not a completed onboarding workflow or an additional recommendation row.
The web layer augments this source-derived setup flag for explicit re-onboarding and filters
managed exclusions. Raw SQL setup flags do not by themselves express the full managed-directory
workflow; consult the registry/API for that state. In the web flow it persists until the administrator confirms a simulated create/import/shared-tenancy choice or
No tenancy required. The choice closes onboarding and is audited atomically; no separate Resolve
step or real OCI operation occurs. The web history marks simulations as Simulated success.
A staged addition is a preview of this review requirement, not an already-applied employee.

`required_actions` includes **live** exception status even in the proposed view. It is not a
frozen record of the exceptions that existed when the version was created. LOB-wide exceptions
without a person association remain in `pending_organization_reviews` rather than being copied
onto every employee. An absence action means investigate, not delete. If an employee is also
marked for setup review, investigate their absence before provisioning anything.

Empty designees are distinguishable from missing ancestry. In `synthetic-lab`, LOB One has
Synthetic Designee; LOB Two has no designees configured. In `root-leader-sample`, only Platform Engineering
currently has named designees (Quinn Blake and Robin Lee). Others require administrator
configuration; the tool does not invent nominations.

## Reported versus derived top manager

`reported_top_manager_email` is an **optional source hint**, preserved in the canonical input
and member evidence. It is not required to reconstruct reporting relationships and is not a
synonym for `accountable_leader_email`. The latter is the configured top-level ancestor established
by the effective manager chain. The synthetic feed leaves the hint null, but the supplied real
sample has values in all 281 employee rows. Preserve these as source evidence until the feed
owner confirms their semantics; do not make this field mandatory for production intake.

## Name and email changes

A name-only edit with unchanged email is automatic metadata. A changed email is a provisional
new identity until an administrator explicitly merges its new-employee review with the absent
identity. The absent person's stable UUID survives, while current name/email/reporting metadata
comes from the new row. `org_person.email` remains an immutable original identity anchor;
`org_member.email` is the current versioned address. Explicit one-way aliases live in trusted,
frozen configuration. The local registry ownership/shared memberships reference the survivor UUID;
production OCI access changes remain a separate workflow.

Historical source/versions remain immutable. Retired employee addresses cannot silently reappear
in a changed source file; that source is rejected. See the complete
[exception workflow design](exception-workflows.md) for merge prerequisites, lifecycle statuses,
soft org exclusions, durable ignore/resolution and planned tenancy flows.

`org_member.data.source_values` retains observed name/manager values separately from overrides,
so a resolved override conflict does not suppress a later different conflicting source value.
`org_member.data.absence_review_since` identifies the current continuous absence episode. It may
remain set after `absence_review=false`: that means the review was settled while the person is
still absent. Retaining this episode key prevents repeated missing feeds from reopening it.
Positive presence clears a settled episode; a later genuine absence gets a new key. The local
employee API exposes `retained_absence=true` for this state. Association-aware offboarding now
controls managed-directory inclusion without deleting the reporting profile. Legacy pending episodes without a key remain available for explicit resolution.

A frozen review decision may include `operation`, `person_id` and `simulation="succeeded"`.
These are audit facts, not actual tenancy records. `TENANCY_ACTION_SIMULATED` is a derived web
history kind with `simulated_success` status, not a new database table or recommendation status.

## Registry and managed-directory fields

The SQL organization views describe versioned reporting state; the local employee API adds live
registry state. A managed-directory filter is not a rewrite of `org_member` or the source feed.
The registry API retains unmanaged profiles for inspection and explicit re-onboarding.

| Field / value | Meaning |
|---|---|
| Registry `org_tenancy.kind` | `individual` or `shared`. |
| Registry `org_tenancy.status` | `active` or `deleted`; retirement retains the row. |
| `org_tenancy.legacy` | Reconstructed from an earlier simulated decision; does not imply discovery of an OCI resource. |
| `org_tenancy_association.role` | `owner` or `member`. One active owner at most, and one active relationship per person/tenancy. |
| `org_tenancy_association.status` | `active` or `removed`; transfer/removal retains previous relationship evidence. |
| Registry person `managed` | Whether the person is included in the managed-directory scope. Independent of source presence. |
| Registry person `source_present` | Whether their employee email occurs in the current applied source records. |
| Registry person `eligible_transfer` | Source-present managed employee who is not explicitly outside; eligible replacement owner/owner-assignment candidate. |
| Employee API `association_count` | Number of currently active local registry associations for the stable person ID. Zero is not proof that no real OCI tenancy exists. |
| Employee API `management_status` / registry person `status` | `Managed`, `Onboarding`, `Outside organization · association retained` or `Not managed`. Explicit pending onboarding produces Onboarding; absence with associations or an explicit retained/outside decision produces outside status. |
| Association `allowed_actions`, `block_reasons` | Server-calculated per-association choices and reasons an unsafe operation is unavailable. The server revalidates the command; UI availability is not authorization. |

Trusted configuration fields are frozen with each organization version:

| Configuration field | Meaning |
|---|---|
| `managed_exclusions` | Stable UUIDs explicitly offboarded/no-tenancy; hide only from the managed directory. A qualified absence/full-feed return clears completed zero-association offboarding, but not No tenancy required exemptions. |
| `pending_onboarding_person_ids` | Durable onboarding IDs from explicit re-onboarding or a qualified absence/full-feed return after completed zero-association offboarding. Persists across repeat/missing feeds until a decision. |
| `outside_person_ids` | Explicit retained/outside decisions. Source reappearance alone does not clear these; Mark returned to organization requires a source-present person and an audited command. |
| `registry_initialized` | Whether legacy simulated decisions have been persisted to local registry rows. Read-only projection before initialization does not write rows. |
| `excluded_emails` | Legacy effective-organization exclusions retained for compatibility. New offboarding uses managed-directory exclusions; explicit source-present re-onboarding can clear a legacy exclusion. |

`return_to_org` keeps existing associations and clears an outside flag. `reonboard` instead requires
an unmanaged, source-present employee with no active associations and opens onboarding. An ownerless
legacy shared tenancy can be repaired with `assign_owner`; promoting an existing member retires
their member relationship before creating ownership. See [the registry contract](tenancy-associations.md).

## Current list counts and audit input

`GET /api/local/tenancies.member_count` includes the owner and every active member relationship.
The full registry's internal tenancy `member_count` excludes owners for lifecycle guard logic;
do not substitute it for the list's people count. `GET /api/local/summary.tenancies` exposes
`total`, `individual`, `shared`, `unassigned_owner`. Employees supports numeric sorting by
`association_count`, displayed as Tenancies.

Review/registry HTTP `reason` is optional. The UI omits Reason textboxes and the server supplies
a factual operation description while retaining actor, target, expected context and outcome.
Qualified return changes pending/exclusion configuration in the feed-publication transaction;
no new table is required, and old tenancy associations stay retired. Staged/rejected/partial
feeds and unchanged-present uploads without a genuine absence do not initiate automatic return.
