# Required users: stored identity records

Tenancies → select a tenancy → **Required users**, below Accountability & registration.
This embedded section reads stored account identities. It does not query OCI, start an operation,
check presence/permissions, repair accounts or disclose credentials. No new primary menu is added.

Two cards always appear after a successful read: **Automation user** and **Recovery user**.
They use neutral registration labels. Presence and permissions explicitly remain **Not checked**.
An absent stored identity is **Not recorded**, never evidence that an OCI account is missing.
**Retired record** describes OTM's retained management record, not confirmed OCI account deletion.
Pending setup and inactive-tenancy history have separate contextual notices.

## API and complete field map

`GET /api/tenancies/{UUID}/required-users` uses the existing current administrator/session boundary.
Scope derives from the principal, never a URL workspace parameter. A foreign registered child and
an unknown UUID return the same 404 response. Malformed UUIDs are rejected before the service.
Each response is noncacheable; one read-only repeatable snapshot covers registry and binding facts.
No provider, secret service or queue is invoked. Stored-shape/relation errors return a closed
unavailable response rather than a successful empty inventory.

| DTO / field | Source and interpretation |
| --- | --- |
| RequiredUsersDirectory.tenancy_id | Exact same-workspace otm_tenancy.id. |
| tenancy_status | Registry status in that snapshot; pending, active, terminating, terminated, failed or cancelled. It does not certify current OCI lifecycle state. |
| provider_mode | Registry provider context, currently simulated; not a live probe result. |
| users | Exactly two ordered records, automation then recovery. Uniform item schema with min/max length 2 and a server purpose-order validator. |
| RequiredUserRecord.purpose | Closed automation/recovery purpose derived from logical identity keys. |
| identity_state | recorded for an active canonical user mapping; not_recorded when none exists; retired for retained retired mapping. These are registration states, not cloud health. |
| identity | Null exactly for not_recorded; otherwise the following closed identity model. |
| RequiredUserIdentity.user_name | Managed user binding.user_name; escaped display metadata. |
| user_ocid | User binding.provider_ocid; distinct from SCIM identity. |
| scim_resource_id | Exact user binding.scim_resource_id. |
| domain_ocid | Referenced same-child domain binding.provider_ocid. |
| recorded_at | User binding.created_at, displayed in UTC; not a new provider-read time. |
| retired_at | User binding.updated_at only when retired, otherwise null. |
| source_operation_id | Binding.created_operation_id; UUID-only internal View setup operation link. |

The reader selects only the three canonical logical keys and takes their latest binding generation.
Domain/user kind, ownership mode, exact domain reference, shared capture source and compatible
record states must agree. The existing [binding schema/ER](managed-object-bindings.md) is unchanged;
no table, migration, assignment, credential/context head or current-health observation is added.
Historical unbound records remain unbound on every GET. This does not backfill or adopt accounts.

## Screen behavior and field coverage

- Username and Identity record map to the record/identity fields above. No fake username or OCID is
  shown for an unrecorded identity. Presence and permissions: Not checked is explicit capability
  guidance for this view; it is not a positive observation from stored registration.
- Identity details is a native keyboard-operable disclosure. It contains domain/user OCIDs, SCIM ID,
  recorded/retired UTC times and the scoped setup-operation link. Internal binding IDs and generation
  counters are not exposed as ordinary user controls. Long identifiers wrap inside each card.
- Refresh records performs another GET only. It preserves focus, disables while busy and cannot
  create a job or repair accounts. The main detail Refresh also invalidates these records.
- Initial loading, initial read failure and successfully unrecorded identities are distinct. A failed
  nonauthorization refresh labels retained earlier records explicitly and offers Try again. After a
 401/403 response, retained identities are hidden immediately while the app expires the session.
- The query key is under tenancies and includes the child UUID. Existing workflow invalidation
  refreshes it, and private-cache clearing removes it on logout. Switching children does not display
  another child's identities. There is no extra polling or new navigation/action badge.
- Cards share a row on desktop/tablet and stack below 700px. Header actions align vertically; card
  expansion is independent. Existing Field Console spacing/colors/focus styles remain authoritative.

## Qualification and remaining work

Unit/API tests cover role cardinality/order, registration/retirement coupling, inconsistent stored
relations, authenticated reads, missing/foreign targets, safe server failures and no mutation route.
PostgreSQL tests cover actual pending/new/imported/legacy/retired records, exact IDs/provenance,
foreign-workspace isolation and unchanged audit/operation/binding counts. Native Playwright checks
create/import transitions, read refresh, keyboard disclosure, source links and responsive containment
at 1280/768/390/320. Frontend units cover loading/error/retained refresh, expiry and cache isolation.

The proposed full Access view still requires scoped assignments, authority/credential/context heads,
independent presence/probe publication and qualified repair/readiness. This section is the implemented
identity-record subset, not that full feature. Real cases remain Pending in the
[manual manifest](../how-to/real-oci-test-manifest.md). Use the
[local review runbook](../how-to/required-users-runbook.md) only after this revision is installed in
the saved preview. Before coordinated upgrade, its older screens/data remain unchanged.
