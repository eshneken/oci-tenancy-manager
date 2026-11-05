# Configuration drift: read-only on-demand checks

3 November 2026 foundation qualified locally at 0018; later schema checkpoints preserve it.
5 November freshness refinement: locally qualified. Real OCI remains unqualified.

[Configuration behavior](../engineering-design/03-templates-and-drift.md) ·
[Full target model](../engineering-design/10-configuration-data-model.md) ·
[Implemented check ER](../architecture/diagrams/configuration-drift-implemented.mmd) ·
[Manual review runbook](../how-to/configuration-drift-runbook.md)

## What a check establishes

An administrator explicitly checks one active registered simulated child or the currently eligible
fleet. Acceptance records an immutable operation intent and queues the existing native worker. A
check compares the assigned immutable baseline plus accepted full-list/budget overrides with the
retained local managed objects. A newer published version, pending review, outdated assignment or
unknown observation is not confirmed drift. Tags inherit the assigned baseline.

The worker reads four local bundles: policy statements, quota statements, monthly budget and tag
defaults. All four must be authorized and complete to confirm Missing/Different or to clear earlier
confirmed drift. Any unavailable/conflicting category makes the attempt Unable to verify. Prior
confirmed same-context drift remains visible with its original evidence time; failed reads cannot
clear it. Unknown is not Missing, and an empty confirmed queue does not establish that unchecked
children are healthy. A complete current matching attempt can resolve the current projection,
without editing historical records.

Checks never call the apply path, change baseline/override assignments, advance last-verified heads,
repair objects or modify configuration_observation. They write operation/step/audit/check evidence
only. Daily drift scheduling is explicitly deferred until staging/Kubernetes deployment (5 November
2026); no local drift CronJob or simulator controls are added. Repair, emails, access-health checks
and production deployment remain separate work. No Repair, dismiss/delete/acknowledgment or automatic mutation is introduced.

## Screens and API

Configuration → Configuration drift opens Confirmed drift by default. Its rows contain only tenancies
with confirmed current-context Missing/Different categories, including retained confirmations after
a later failed read. Checks lists active child records before/after attempts and exposes Matching,
Confirmed drift, Unable to verify, Not checked, Checking and Check out of date filters. Search, sorting and pagination
are server-side. Counters describe tenancies across the authorized current set, independently of
the filtered page; confirmed-drift category counts are a separate measure. A tenancy can have retained
confirmed drift and also count as Unable to verify after its latest failed attempt.

Check all tenancies queues eligible nonbusy current children; it does not silently write to any of
them. A busy/already-checking child is excluded from a fleet acquisition; an explicit one-child busy
request conflicts. A child without a qualified baseline/binding inventory produces unable-to-verify
evidence, not invented Missing objects. Refresh fetches stored evidence only. Queued/running checks
are visible progress; the page polls while checking. Acceptance does not clear earlier evidence.

A row opens /configuration/drift/{tenancy_uuid}. Detail shows the assigned version, override
categories, last attempt, pending operation and all four expected/observed categories. Values are
rendered as text, never executable statements or HTML. Deep links can target category=policy, quota,
budget or tags; returnTo accepts only the allowlisted drift/inventory/registered-child routes.
Directory payloads omit expected/observed text; detail includes the verified bounded payloads.

| Route | Contract and behavior |
| --- | --- |
| GET /api/configuration/drift | ConfigurationDriftQuery → ConfigurationDriftDirectory; no check/repair side effect. |
| GET /api/configuration/drift/{uuid} | Exact scoped ConfigurationCheckSummary including category evidence; foreign/missing is not substituted by another child. |
| POST /api/configuration/checks | At most 4,096 bytes of closed ConfigurationCheckRequest; existing session/Origin/custom-header guards; queued ActionReceipt is HTTP 202, terminal/replay response HTTP 200. |

A request key is scoped to the verified actor/workspace. An exact committed replay returns its
original operation before stale/current-eligibility checks; changed input under the same key
conflicts. The form retains an uncertain-response key while mounted; this does not promise recovery
memory across a full reload. Review Operations before submitting different work after uncertainty.
Operation completion means attempts were recorded; succeeded does not mean every child matched.

## Context, freshness and coverage

The accepted target freezes assigned baseline UUID/hash, accepted configuration UUID/effective hash,
overrides, registered child/parent/organization, tenancy revision, policy revision and retained
category binding IDs/hash. Expected content is reconstructed from that immutable assignment, never
from latest publication, editable drafts or possibly drifted observed text. Legacy null configuration
means inherited values; an absent baseline or incomplete/unverified inventory cannot be qualified.

The worker repeats live administrator authorization/revision, runtime pause/policy, current target
assignment and busy-operation checks. A changed assignment produces superseded evidence; an old
generation cannot turn the current generation green or resolve its findings. Check history is
ordered by database acquisition_sequence, not wall-clock completion. In this local simulator, the
workspace/child locks cover read acquisition and sealed insertion, so ordinals faithfully order
serialized attempts. This is not a qualified network-read protocol: real OCI reads need separate
dispatch/reconciliation and post-read context checks.

The projection retains the latest attempt and latest qualifying complete evidence, validates their
immutable hashes/identities and uses only matching current contexts. Evidence over 24 hours old is
stale. An old Matching result cannot remain fresh healthy status; existing confirmed drift remains
labeled retained with its confirmation age until qualified resolution. No scheduled scan is implied
by this freshness threshold. In-progress mutation is progress/unverifiable context, not a new
confirmed drift signal.

An execution pause with the same trusted policy disables new checks without discarding earlier
same-context confirmed drift. Its availability is Unable to verify and no category can become green
from retained evidence; a queued attempt can still show Checking until recorded. Pause alone does
not change the prior confirmation's timestamp. A changed parent/policy is different: its old context
is invalid for current projection, so historical evidence cannot confirm or green the new authority.
A new authorized attempt is needed for that context.

Missing requires an explicit complete authorized absence envelope for the original retained
binding. None, a missing key, malformed data, permission failure or timeout cannot establish
absence. A conflicting observed OCID/category never becomes name-based adoption. All four category
results are explicit; partial bundles cannot confirm new drift or clear prior confirmation.

## Existing local observation compatibility

ManagedObservation separates the retained binding from externally changed fake-cloud state.
Legacy ManagedConfigurationObject records remain readable as complete present local observations,
without rewriting rows. New envelopes explicitly represent present, missing or unavailable state.
Their binding remains the original category/object; observed identity is independently checked.

The local four-bundle model is not the full proposed production binding inventory. It does not
qualify required-policy composition/domain grants, separate namespace/key/default identities, root
capacity, resource-tag compliance, budget owner/target/alert-rule enumeration or real OCI access.
Comparisons canonicalize JSON object keys only; statement array order, text and values remain
meaningful. No OCI grammar parser or semantic policy normalization is claimed.

## Complete contract field map

Current source defines nine drift DTOs with 83 fields plus the five-field local observation envelope below.
Closed Python models and generated schemas are authoritative for bounds, enum values and nullability.

| Model | Fields | Source and constraints |
| --- | --- | --- |
| ConfigurationCheckRequest (2) | client_request_key, tenancy_id | UUID request identity; nullable child UUID means fleet. No actor/workspace/desired content. |
| CheckTarget (15) | tenancy_id, tenancy_name, tenancy_ocid, parent_tenancy_ocid, organization_id, revision, policy_revision, baseline_id, baseline_hash, configuration_id, effective_hash, overrides, bindings, bindings_hash, qualified | Server-frozen registered assignment/inventory. Positive qualification requires all four retained IDs plus baseline/hash/effective hash. Nulls represent legacy/unqualified context, not successful setup. |
| ConfigurationCheckIntent (10) | contract_version, kind, workspace_id, policy_revision, organization_id, parent_tenancy_ocid, administrator_id, authorization_revision, targets, target | configuration-check-1 / configuration_check; 1–500 unique scoped targets. Shared display target has one child's OCID or null for fleet; no invented fleet OCID. |
| ConfigurationObjectCheck (7) | category, state, safe_code, complete, binding_ocid, expected, observed | policy/quota/budget/tags; matching/missing/different/unavailable/conflict. Complete determinate evidence requires binding and expected data; Missing alone has absent observed payload. Payloads at most 700,000 characters. Unknown/conflict has complete=false and no verified observed value. |
| ConfigurationCheckEvidence (8) | contract_version, check_id, tenancy_id, state, safe_code, checked_at, context_hash, results | Sealed immutable outcome; exactly four distinct categories. matching/drifted needs full coverage; drifted needs an actual missing/different category. unavailable/superseded cannot establish success. |
| ConfigurationIssue (8) | category, state, safe_code, binding_ocid, expected, observed, evidence_at, retained | Read-derived current or earlier same-context evidence; adds not_checked. Retained marks earlier confirmed drift, with its original confirmation time. Directory omits payload text. |
| ConfigurationCheckSummary (14) | tenancy_id, tenancy_name, baseline_id, baseline_version_number, override_categories, state, checked_at, issue_count, confirmed_issue_count, stale, can_check, pending_operation_id, last_operation_id, categories | Joins current registry/assigned version/accepted overrides and immutable checks. Adds derived not_checked/checking states; can_check reflects current provider/busy scope, not proof the child is healthy. The current service sets issue_count and confirmed_issue_count to the same confirmed Missing/Different category count. Unknown/conflict/staleness are check status, never invented drift counts. |
| ConfigurationDriftQuery (8) | tab, query, state, tenancy_id, sort, direction, page, page_size | confirmed/checks; search up to 128 characters; state filter all/matching/drifted/unavailable/not_checked/checking/stale, with stale a filter alias only; name/checked_at/issue_count sorting; asc/desc; page 1–100,000; sizes 10/25/50. |
| ConfigurationDriftDirectory (11) | items, total, page, pages, page_size, confirmed_count, unavailable_count, unchecked_count, checking_count, stale_count, provider_mode | Paginated summaries plus independent full-scope tenancy counters; simulated only. stale_count defaults 0 and counts stale flags independently. unchecked_count selects not_checked without stale; overdue evidence is not never-checked evidence. |
| ManagedObservation (5) | contract_version, binding, state, observed, complete | managed-observation-1; original ManagedConfigurationObject binding; present/missing/unavailable; explicit consistent coverage, no credential/raw SDK response. |

## Computed tenancy inventory/detail fields

TenancyView now has 36 fields. Five additive fields reuse the very same ConfigurationCheckSummary
projection in inventory and detail; they add no SQL column, second health cache or interpretation.
Compatibility defaults are empty/not-checked, not proof that configuration is healthy.

| Computed TenancyView field | Source and meaning |
| --- | --- |
| configuration_issue_count | check.issue_count; confirmed Missing/Different category count only, equal to current confirmed_issue_count. Retains prior complete same-context findings through stale/unknown/rechecking status. Default 0 for older DTO producers; unknown/freshness issues do not create a count. |
| configuration_confirmed_issue_count | check.confirmed_issue_count; categories confirmed Missing/Different by complete same-context evidence, retained after later unknown reads. Default 0. |
| configuration_check_state | check.state; matching, drifted, unavailable, superseded, not_checked or checking. Default not_checked; pause/old context cannot imply matching. |
| configuration_checked_at | check.checked_at; nullable UTC latest relevant attempt time, independent of last successful application time. |
| configuration_check_stale | check.stale; 24-hour evidence-age flag, default false, distinct from paused/unavailable capability. |

Inventory and detail use the shared configuration status formatter. Confirmed categories appear as
Configuration drift · N categories; independent check-health messages are Check out of date, Unable
to verify, Not checked or Checking. A child can show retained drift together with age/failure/progress.
Inventory omits a fresh Matching-only message; tenancy/check detail can show Matching. These links
open the exact child's check evidence. A check-status link never invents a confirmed-drift count,
Repair action or navigation-inbox badge. The latest attempt time remains separate from confirmation
age. Zero confirmed categories alone does not establish a checked/matching child.

## One new immutable table

Forward migration 0018_configuration_drift adds otm_configuration_check to the existing 18-table application,
for 19 tables. It does not create the full proposed otm_tenancy_check/object-observation/issue model
or duplicate a queue/audit engine. No configuration-head column or backfill is added.

| Column (13 total) | Authority and purpose |
| --- | --- |
| id | UUID primary key for this sealed child attempt. |
| workspace_id | Current verified application scope; part of scoped child/evidence foreign keys. |
| tenancy_id | Same-workspace registered child; never an arbitrary browser OCI target. |
| operation_id | Existing accepted configuration_check operation; at most one child record per operation. |
| acquisition_sequence | Globally unique database identity ordinal, positive; current child history orders by it under serialized local acquisition. |
| contract_version | Fixed configuration-check-1. |
| started_at | UTC start of this child's bounded read attempt, not operation acceptance. |
| checked_at | UTC sealed attempt time, never before started_at. |
| context | Closed frozen CheckTarget JSON, including exact assignment and retained binding inventory. |
| context_hash | Canonical SHA-256 of original context; validated again on reads. |
| state | matching, drifted, unavailable or superseded; not a new tenancy lifecycle state. |
| results | Exactly four closed ConfigurationObjectCheck JSON records, validated against immutable outcome. |
| evidence_event_id | Same-workspace/operation audit_event reference for immutable configuration_check_outcome evidence. |

Existing otm_operation_step uses configuration_check:{tenancy_uuid}, command_kind=configuration_check
and effect_knowledge=none. Native task otm.configuration_check receives only the operation UUID on
the existing scoped queue, with no automatic task retry. Complete determinate attempts have verified steps; unavailable/superseded
attempts retain needs_attention evidence. These diagnostics have no generic retry/acknowledgment
action or navigation-inbox badge; a fresh explicit check begins in Configuration. Workers deduplicate
sealed child attempts and retain one check/outcome per operation/child. Audit and check insertion
commit together. Scoped foreign keys, unique child-attempt identity and immutable guards preserve
history; privileged database owners remain outside ordinary DML protection. The explicitly opted-in,
owned local test-reset scope grows from 12 to 13 tables to include checks; it preserves audit history
and is not a repair, HTTP action or authorization to reset either saved installation.

## Review and qualification

Required source-unit, disposable PostgreSQL/native-worker, actual HTTPS/browser and independent
security/UI/documentation checks pass. Both saved instances are upgraded from 0017 to 0018 with
private 0600 backups and matching fingerprints for all old columns/rows across all 18 pre-existing
application tables. The new check table brings the inventory to 19, with 20 baseline columns
unchanged; baselines, accepted pins, overrides and history are preserved. See the manual runbook for disposable synthetic database/browser fixture
scenarios. There is no operator simulator CLI or saved-observation editing helper in this slice; no current guide authorizes a saved-data reset, live OCI mutation or publication.


### Final local qualification and installation

All 1,306 combined backend/PostgreSQL/native-worker/HTTPS-browser cases pass with no failures,
errors or skips, using disposable synthetic databases. The 1,060 backend unit tests cover 6,953 of
7,248 executable lines (95.9299%) across all 99 runtime modules. The 320 frontend unit tests cover
1,571 of 1,613 lines (97.396%) across 29 files. Unit-only coverage is separate from database/browser
evidence. The final focused actual native-browser check also passes after workflow-based fixture
setup in its own disposable database; it uses real API/native-worker behavior, not a mocked browser
response or a user simulator helper. Final UI review covers three viewport widths.

All 63 generated schemas, 253 Python purpose-comment files, 229 formatted Python files, Ruff and
document links pass. Fresh dependency audits report zero known vulnerabilities across 75 locked
Python packages with no skips and zero npm findings; Bandit and scoped Gitleaks also report zero.
Independent security, migration/installer, documentation and final actual-screen UI reviews pass.

Both saved instances are upgraded from 0017_membership_onboarding to 0018_configuration_drift.
Private 0600 backups are retained; fingerprints of every old column/row across all 18 existing
tables match. The one new check table brings the inventory to 19; the 20-column baseline table,
accepted pins, overrides and history are preserved. Both API/worker pairs are alive, with matching
private qualified frontend snapshots. Liveness/current assets/direct drift HTML return HTTP 200;
private drift APIs reject unauthenticated requests with HTTP 401. No saved-data reset, backfill,
credential change, live OCI action or Git publication occurred.

This completes read-only on-demand local drift visibility. Repair, daily scheduling/infrastructure,
email and full real OCI binding/permission coverage remain separate future qualification. The next
review is the implemented checks and evidence; this checkpoint does not silently start those later
workstreams.


Final local qualification and installation receipt (private historical evidence; not distributed).


## Daily schedule deferral — accepted 5 November 2026

The current supported trigger remains Check now / Check all tenancies. A daily read-only drift
CronJob belongs to the later staging/Kubernetes build slice, using authorized noninteractive
admission and the existing native worker; it is not implemented locally. Its later qualification
must prove schedule idempotency, missed/overlap behavior and evidence freshness. The 24-hour stale
threshold is not a claim that a schedule already runs. Separate session-cleanup scheduling and
native retry deferral remain unchanged.


## Confirmed drift versus freshness: 5 November 2026

Locally qualified refinement. issue_count is now the confirmed_issue_count alias in current
read projections: only Missing/Different established by a complete current-context check counts.
A stale, unavailable, conflicting or never-checked observation alone is not confirmed drift. Prior
complete same-context findings remain counted/visible during stale evidence, failed reads or a
recheck in progress; only qualifying complete follow-up resolves them. Zero issues is not healthy
proof. Freshness/status labels must use the existing state, stale flag and attempt timestamp.

ConfigurationDriftDirectory adds stale_count (compatibility default 0) without a storage field. It
counts every stale tenancy independently, including those with retained drift, current uncertainty
or a recheck. unchecked_count excludes stale entries, distinguishing no relevant check for the
current assignment from an overdue prior check. Counters are not necessarily mutually exclusive;
none claims that the tenancy was never checked under every historical assignment. The complete
DTO remains 11 fields. Existing summary/tenancy fields and persisted check/summary state values
are unchanged; only the query filter adds the stale alias.

Inventory, tenancy detail, check directory and check detail must use one shared interpretation and
consistent current/overdue/unknown/rechecking copy. Recheck acceptance is progress, not a freshness
reset; committed completion refreshes all related read views so a new complete result clears stale
status/count while retained confirmed drift changes only when qualified evidence resolves it. No
new check state, table, migration or local scheduler is introduced. The daily drift CronJob remains
explicitly deferred until staging/Kubernetes deployment.


### Filter and counter interpretation

| Query state | Selection within the chosen tab/scope |
| --- | --- |
| all | Every row in that scope. |
| matching | Matching state with fresh evidence only. |
| not_checked | Not-checked state without stale evidence; no relevant check for the current assignment. |
| stale | Any stale flag, regardless of retained drift or current attempt state. This is a filter alias, not a new evidence/summary state. |
| drifted | confirmed_issue_count greater than zero, including retained findings during Unavailable or Checking. |
| unavailable | Latest projected attempt state is unavailable. |
| checking | Latest projected attempt state is checking. |

Tab selection still applies: the Confirmed drift tab requires actual confirmed categories before its
state filter. Counters cover the complete scoped active inventory independently of tab/filter/page;
one child may contribute to confirmed, stale and checking/unavailable counters. Matching and
Not checked filters must not hide the fact that old evidence is overdue by treating it as fresh or
never checked. Exactly 24 hours remains within the age bound; evidence older by even one microsecond
is stale. A clock-advanced test must obtain fresh legitimate authentication after session expiry.

The shared UI formatter can display confirmed drift plus Check out of date and Checking/Unable to
verify together. A queued recheck does not reset evidence time or clear old findings. The page
observes the accepted operation through terminal completion, including fast fleet checks that
remove matching rows from the confirmed queue; completion invalidates tenancy inventory/detail,
the drift directory and individual check detail caches. Checks observed finishing elsewhere use
the same refresh scope. These are UI cache invalidations, not new persisted health state or a daily
acquisition service. Current refinement qualification is recorded in its own validation
receipt; the original 3 November receipt retains its original scope.


## Final local freshness qualification — 5 November 2026

Validation record (private historical evidence; not distributed):
both unit-only line-coverage gates exceed 95%; focused PostgreSQL/HTTP and native worker/HTTPS
browser checks pass. Independent security, documentation and UI/UX reviews pass. Both saved
instances are refreshed, preserving existing rows and schema. Daily scheduled admission remains
deferred until staging/Kubernetes and its noninteractive-authority qualification.
