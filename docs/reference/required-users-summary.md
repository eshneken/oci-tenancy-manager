# Required users in the Tenancies status cell

Local qualification and the main-preview update pass; the parallel preview remains unchanged. [Final summary receipt](../history/required-users-summary-checkpoint-2026-11-06.md). The underlying [manual presence-check pipeline](user-presence-checks.md) remains unchanged; its earlier receipt retains its own scope.

Active Tenancies rows now include a compact **Users: …** link inside the existing Status cell.
There is no new column, navigation item, filter, attention count, SQL table or provider job. Opening
the inventory or detail only reads retained facts; it cannot start a presence check or call OCI.
Inventory configuration badges now use a separate Config: prefix (for example Config: Not checked,
Config: Unable to verify and Config: Drift · 1 category), while this link uses Users:. Their accessible
names match their visible prefixes. Configuration labels inside detail retain their section context.
The badge describes existence in the selected local simulator, not permissions, usable credentials,
MFA or recovery readiness. Its description explicitly scopes this badge to simulated existence. Separate assignment and
recovery-policy indicators do not imply password readiness or all effective permissions.

## Complete field map

TenancyView now has 38 fields. Its one new additive field is a derived RequiredUsersSummary; the
existing directory/detail routes populate it. Other uses of the shared view receive its explicit
Not checked default until enriched. It is not an independently writable registry attribute.

| Model / field | Source, meaning and default |
| --- | --- |
| TenancyView.required_users | RequiredUsersSummary projected from current scoped canonical bindings/connection and validated retained check evidence, with no SQL column. Default is the closed model below. |
| RequiredUsersSummary.state | not_checked, present, missing, unavailable or stale. Derived by the precedence table below; default not_checked. |
| automation | Existing four-field UserPresenceView for the exact automation subject. Independent default not_checked/null/false/null. |
| recovery | Existing four-field UserPresenceView for the exact recovery subject, with the same independent defaults. |
| checking | True when a queued/running required_user_check has a valid immutable intent and the same current context hash. False by default; pending work never becomes a positive existence result. |
| recovery_console | Independent derived RecoveryConsoleView from sealed recovery policy evidence; defaults not_checked. Same projection as detail, not inferred from account presence. |
| administrator_access | Automation AdministratorAccessView: group, domain_role, stale, checked_at, operation_id; default not_checked without retained proof. |
| recovery_administrator_access | Independent recovery AdministratorAccessView with the same five fields/defaults; never substitutes for automation assignments or credential readiness. |
| UserPresenceView.state, on each subject | not_checked/present/missing/unknown from that subject's validated observation. The aggregate names unknown as unavailable; it does not change the per-user result. |
| checked_at, on each subject | That observation's captured_at, nullable. Exposed in the title/accessible description in UTC; never copied from aggregate completion or the other account. |
| stale, on each subject | The shared server UTC age rule: stale at 24 hours or for a future timestamp. No independent summary freshness threshold is introduced. |
| operation_id, on each subject | Exact retained check UUID, nullable; provenance stays available in the expanded Required users cards. |

RequiredUsersSummary now has seven fields: state, automation, recovery, checking, recovery_console,
administrator_access and recovery_administrator_access. Each nested UserPresenceView still has
four fields; its existence model is reused rather than replaced. The
[required-user directory](required-users-screen.md), [assignment field map](administrator-assignments.md)
and [recovery-policy field map](recovery-console-verification.md) describe the independent extensions. All 75 generated
public schema files remain the same inventory; nested tenancy schemas/types reflect the additive
field. Python validation remains authoritative.

## Aggregate precedence and visible labels

Evaluate these rules from top to bottom; the first match wins:

| Condition | state / visible label |
| --- | --- |
| Either subject has confirmed Missing, is fresh and has its own captured timestamp/check-operation reference | missing → Users: Missing. This remains a confirmed fresh absence even if the other subject is stale or unavailable. |
| No qualifying fresh Missing, and either claimed Present/Missing lacks its own timestamp or operation reference | unavailable → Users: Unable to verify. A coarse positive label is insufficient evidence. |
| No earlier condition, and either subject is stale | stale → Users: Check out of date. Old positives never stay green. |
| No earlier condition, and either subject is Unknown | unavailable → Users: Unable to verify. |
| Both subjects are fresh Present with their own timestamps and operation references | present → Users: 2/2 present. This establishes simulator existence only. |
| Otherwise, including unbound, unconfigured, context-changed or never checked | not_checked → Users: Not checked. |

Both the backend DTO validator and frontend wire guard reject a coarse Present/Missing summary
without qualifying individual dated check references. The UI degrades such a label to Unable to
verify. This is a nonnull-metadata guard, not a replacement for server-side typed evidence/hash/
current-context validation. No field or persisted state is added.

Checking… is separate secondary text and can coexist with a dated preceding result. It does not
replace that result with a fabricated success. Each subject's title/accessible description retains
its own last state, stale indication and UTC time. A malformed stored proof or pending intent
produces an unavailable summary for that child without inventing account facts or breaking other
rows. It must not silently fall back to an older green result. Missing registration is not a claim
that a cloud user is missing. Non-active rows do not render this link; retained history stays in detail.

## Scoped batched reads and shared semantics

The service first derives the existing filtered/sorted/paginated Tenancies page. The summary receives
only those server-selected visible child IDs and the authenticated workspace. For active visible
children it adds four queries, independent of page size:

1. Current simulated connections, bounded by workspace and the visible ID set.
2. Active canonical domain/automation/recovery identity bindings with the same scope.
3. Latest terminal check per child by database admission sequence, joined to its exact immutable
   outcome event in the same workspace/operation. Window ranking and ID predicates select only
   this page, not arbitrary browser-supplied children.
4. Pending required-user operations and their immutable accepted intents, under the same scope.

This is four added summary queries, **not** a claim that the whole directory endpoint performs only
four queries. Empty/non-active summary inputs issue no additional summary queries. Existing
principal authorization and the coherent read-only snapshot remain in force; detail uses the same
projection for its single selected child.

bound_snapshot is shared with the expanded view's context resolver. presence_views shares the exact
closed evidence/hash/attempt/context validation and per-subject age calculation with that view.
Latest terminal evidence follows the persisted acquisition_sequence admission order, not callback
completion order. An old context cannot become current merely
because the list is reopened. Current expected IDs are targets, not invented observed facts.
A genuinely unconfigured or unselected-policy context, inactive/busy child or validly replaced
context has no current matching result and stays Not checked. A currently configured eligible
connection with broken canonical three-row identity/domain/signer/source references instead raises
an unavailable read: the batch marks that child Unable to verify while preserving other rows; the
expanded Required users endpoint returns a closed 503. Corruption must not look like a genuine
unchecked/unconfigured context. Foreign workspace page input is rejected before summary SQL. No backfill,
provider acquisition, new grant or stored state transition occurs in these reads.

## Link, focus, refresh and accessibility

The native link targets the exact child at /tenancies/{encoded UUID}#required-users, matching the
actual section id required-users. Once the initial read finishes, the section heading scrolls into
view and receives keyboard focus once after success or a terminal nonauthorization error such as
503. A 401/403 never moves focus into the section or exposes retained identity facts. Ordinary link/open-in-new-tab behavior is retained. The visible badge has a
stable accessible label containing the tenancy name and state, plus a linked description containing
both subject results/times, simulation/permission limits and any running-check explanation.
The ordinary title carries the same facts; no custom tooltip state or inferred health is added.
The visually hidden description is positioned relative to its inventory container so it cannot
expand the body's viewport width. Normal body overflow is retained; native containment checks must
verify the actual 320-pixel viewport, not conceal extra width with page-level clipping.

Inventory polling also observes visible rows' checking flags and runs every two seconds while any
visible check or existing operation/cost work is pending. The Required users cards keep their
existing one-second pending-result polling. Successful check admission and refreshed card data
invalidate the appropriate inventory/detail caches; Operations/Audit refresh their retained facts.
GET polling/invalidations remain read-only and cannot enqueue another check. No extra global
scheduler or navigation badge is introduced.

## Review and remaining qualification

Qualified unit/SQL/browser coverage verifies every aggregate state and mixed-state precedence,
per-subject timestamps, exact list/detail equivalence, context changes, stale and corrupt proof,
no historical fallback-to-green, configured corruption versus genuine unconfigured records,
positive-label metadata guards, pending intents, foreign scope, four-query page scoping and empty
inputs. Final native UI review includes success/503 deep-link focus, no focus/data on 401/403, Users:/Config:
label separation, actual 320-pixel body containment, long IDs/names and fresh create/import
check completion updating both views, paging/sort/search stability and responsive containment.
The final unit/integration/security/UI gates and preserved-data main update pass; [the dated receipt](../history/required-users-summary-checkpoint-2026-11-06.md) records exact scope and metrics. Use the
[local summary review steps](../how-to/required-users-runbook.md#inventory-summary-source-checkpoint).

The existing [14-column check table/ER](user-presence-checks.md#physical-storage-all-14-check-columns)
is unchanged: 25 application tables, no migration or new persisted summary. Live OCI reads, daily
scheduling, email, privilege checks, credentials and repair remain separately unqualified or future
work. The [real-provider manifest](../how-to/real-oci-test-manifest.md) stays Pending.
