# Executable organization contract

> Run lab commands from the repository’s `prototype/` directory. See [setup](../README.md).

13 October 2026 | Applied/proposed/reconciliation local prototype

The organization slice now implements the approved simpler working model. See [table descriptions
and ER diagram](organization-er-diagram.md), [pgAdmin walkthrough](organization-working-model.md)
and [validation](organization-prototype-validation.md). The earlier [simplification audit](organization-simplification-audit.md)
records why the eleven-table representation was changed. Production source authority/integration, SSO, delivery jobs and OCI behavior remain future work. The
local frontend and explicit reviewed identity correction now exist; see [exception workflows](exception-workflows.md).

## Canonical input and trusted configuration

[Intake JSON Schema](contracts/organization-intake.schema.json) contains a source/population-bound
envelope and typed employee rows: source record ID, full name, normalized email, manager email/name
and optional top-manager/territory hints. Unknown fields are rejected. Source capture time and
completeness are separate from receipt time and assessed authority/coverage.

[Configuration](contracts/organization-configuration.schema.json) is trusted server-side state,
separate from uploaded claims. It includes source/freshness/census rules, scope/root, LOB/designees,
supplemental edges and explicit name/manager overrides with author/reason. Corrections cannot change
source authority through the override operation. Manager/source-ID ambiguity and reused identities
require investigation. Explicit absent/new identity merging is implemented in the local review
workflow, preserving the absent person's stable ID through frozen administrator alias rules.

The XLSX adapter never evaluates formulas or rewrites the workbook. Production raw-file quarantine
and transport qualification remain future boundaries. The sample has no confirmed capture/authority
and cannot establish departures.

## Eight tables and four readable views

[Generated DDL](contracts/organization-schema.sql) defines six organization tables (`org_person`,
`org_feed`, `org_workspace`, `org_version`, `org_member`, `org_recommendation`) plus shared
`audit_event` and `notification_outbox`. `Store.initialize` also infrastructure-services evidence/seal guards
and `current_organization`, `proposed_organization`, `organization_reconciliation` and
`pending_organization_reviews` SQL views. Exported DDL is descriptive, not a production migration.

Full immutable versions preserve stable person identities and history. Readable member columns
expose names, manager relationships, LOB/leader/designees and review evidence. Same-version manager
FKs and scope/kind-constrained workspace pointers prevent mixed organizational contexts.

## Reconciliation flow

1. Register canonical source payload/digest and immutable receipt event. CSV uploads each receive
   a fresh UUID observation identity, even for identical file contents. Future API/object storage
   acquisition follows the same per-observation rule; content hashes are audit provenance.
   Retries of one delivery must reuse its persisted identity and capture metadata. Same snapshot identity
   with conflicting content is rejected as an integrity conflict; repeated terminal input reuses outcome.
2. Read stored feed, trusted settings and current applied baseline. Validate identity, freshness,
   graph/root and coverage, including retained edges and reference-only profiles.
3. Persist a proposed version excluding person overrides, plus readable before/after deltas.
   Invalid/stale deliveries retain diagnostics without replacing usable current pointers.
4. Rebuild effective state from stored source, honoring explicit overrides. Automatically apply valid
   metadata in one transaction with full applied version, exception episodes, frozen intent, history
   and head. Newer proposals invalidate stale apply previews; waiting proposals recheck freshness.
5. Missing manager profiles block absence even when retained profiles/supplemental edges resolve paths.
   Only qualified complete fresh source can establish absence review. No feed creates/deletes tenancies.
6. Administrator corrections check applied/proposed/configuration IDs, audit settings changes, and
   recompute the same stored feed. Overrides persist across later disagreement; acknowledgment leaves
   the source issue pending instead of falsely resolving it.

Normal `ingest` registers then stages/applies automatically. `register` + `stage` + `apply` provides
an inspectable local test journey without creating a metadata approval requirement. Processing states
are `received`, `staged`, `published`, `rejected`, `superseded`; duplicate/conflict are delivery responses.
Metadata recommendations use `ready`, `auto_applied`, `blocked_override`, `superseded`; exception episodes
use `open`, `acknowledged`, `resolved`. Continued issues deduplicate notification intent; recurrence after
recovery generates a new episode. The outbox remains `intent_only`, with no outbound delivery.

## Read interfaces and local controls

[Generated OpenAPI](contracts/organization-openapi.json) exposes current head, explicit revision-pinned
people list/detail, coherent applied/proposed/configuration workspace context and bounded live
reconciliation history/pending reviews. People filters/search/sort/pagination operate within one
selected immutable version. Unknown versions never fall back to latest. Live recommendation status
is not presented as frozen historical organization data.

The API is an explicitly opted-in read-only ASGI harness. No production SSO server or HTTP mutation
endpoint is provided. [Local CLI](../scripts/organization_cli.py) offers source ingestion/staging/apply,
inspection, audited name/manager corrections/removal and exception acknowledgment with explicit
expected context. Local actor labels are supplied by the operator and must become authenticated
identity before production. [The scenario generator](../scripts/organization_scenarios.py) seeds an
isolated synthetic lab without resetting existing data. [Legacy migration](../backend/otm/organization/migration.py)
retains the original schema, IDs, history and evidence, copying into a separate target transactionally.

## Validation and remaining application work

54 tests pass in isolated PostgreSQL, including the previous 36 invariants and 18 new workflow/
migration scenarios. See the validation record for warnings/limits. The live inspection database
contains preserved real sample state and a fictional lab left with a staged rename.

Still required: frontend/review journeys, authentication/authorization, production migrations/roles,
durable intake/delivery/recovery, email-binding corrections, confirmed out-of-scope archiving,
production source authority and all tenancy lifecycle/access/configuration/finance/OCI modules.
No simulation or local test qualifies the deployed service or real Oracle departure decisions.


### Identity and inspection refinement — 14 October 2026

Named leader/LOB/designee columns and provisional post-baseline tenancy setup review are included
in the SQL inspection views; see the field reference for exact semantics. Identity continuity
across email changes is required: a future audited remap must retain person UUIDs and immutable
source/history, with collision checks and versioned aliases. No employee-ID stability guarantee
is available yet, and the current prototype deliberately rejects ambiguous email changes rather
than silently creating a replacement identity. The optional reported top-manager source hint is
not the configured accountable leader and is not required to reconstruct the manager graph.

### CSV and local web iteration — 15 October 2026

The latest export contains `EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR`; no immutable employee ID is
available. `csv_feed.py` converts UTF-8 rows to the existing canonical JSON contract with an
explicitly synthetic email-based source key. JSON/XLSX evidence and prior workspaces are retained.
The strict adapter is shared by local CLI and web intake. The root-profile policy exemption now
correctly permits exports of the configured root's descendants while retaining all other manager-profile gates.
Reported top-manager discrepancies create review items; trusted manager paths/configuration
continue to determine the effective accountable leader and LOB.

The laptop UI has employee and exception screens, server-side search/sort/paging and CSV upload.
It uses the existing PostgreSQL model in an isolated workspace, not an in-memory simulation.
The local scenario contract permits full-snapshot absence demonstrations using receipt time as
the scenario clock; production source freshness/authority remains unconfirmed. See the
[web lab guide](organization-web-lab.md) for exact behavior, initial-baseline semantics, identity
limitations, replay behavior and the absence of production/OCI/review-completion actions.

### Review workflow iteration — 16 October 2026

[Exception lifecycle](exception-workflows.md) is the current catalogue and remediation contract.
All actionable episodes require administrator closure, informational source warnings clear with
corrected evidence, and history groups metadata changes per employee/revision. Trusted configuration
now also freezes `review_decisions`, `excluded_emails` and `identity_merges`. No extra business
tables were added. Generated local-web OpenAPI documents the guarded review/merge endpoints.
