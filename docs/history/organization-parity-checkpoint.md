# Organization workflow parity checkpoint

Validated local review checkpoint · 30 October 2026

This checkpoint ports the approved prototype interactions into the production application. It uses
explicitly labeled local simulated OCI execution; it does not qualify actual child creation,
activation/bootstrap credentials, IAM deployment or deletion against OCI.

The delivery includes a durable organization review inbox and dated informational history; tenancy
registry/memberships and employee association counts; new-person create/import/join/no-tenancy
choices; per-association offboarding with transfer/remove/delete/keep choices; permanent LOB ignore;
conditional review closure; explicit one-way identity merges preserving associations; and a useful
Tenancies list/detail entry point. The same native PostgreSQL queue and Operations history track
accepted simulated lifecycle work. An accepted operation closes its organization handoff atomically,
while pending/failed execution remains visible on the tenancy/operation. No UI pretends that queue
acceptance means OCI completion.

Source graph snapshots remain immutable. Managed-directory status is an independent attribute of
the stable person identity. Offboarded people disappear from the managed directory without losing
source/reporting history; a later qualified absence-to-return sequence opens onboarding again.
Explicit no-tenancy decisions remain exempt until deliberately re-onboarded. Source-only warnings
clear automatically when corrected, while their dated history remains queryable.

Implementation order:

1. Forward schema and typed review/association/action/provider contracts.
2. Transactional review reconciliation, metadata decisions, merge and lifecycle admission.
3. Registered simulated lifecycle worker behind the OCI facade; atomic registry publication.
4. Organization review dialogs, association-aware offboarding, tenancy list/detail and counts.
5. Reset scope, private local migration/restart, documentation/ER and full unit/PG/Playwright gates.

All writes retain fresh administrator authorization, workspace scoping, immutable audit, exact
preview revisions and request-key replay protection. Parent/unregistered deletion is refused;
manager/shared warnings are explicit. Shared-member removal records manual compartment cleanup,
not resource deletion. Tests use disposable databases and synthetic people; human local data is
preserved by migration and not mutated by automated tests. Unit-only coverage stays at least95%
separately for backend/frontend. Independent documentation/security/UI reviews remain required.

## Implemented checkpoint and validation

[Current field/reference guide](../reference/organization-workflows.md) ·
[Implemented ER](../architecture/diagrams/organization-workflows-implemented.mmd).

Migration0009 and the current candidate add three physical tables: `org_recommendation`,
`otm_tenancy`, `otm_tenancy_membership`, plus stable-person managed controls and a registry revision.
The source has14application tables across nine forward revisions. Full current API, command,
immutable intent, outcome, preview and storage field maps are in the guide. This checkpoint passed
902 combined backend/database/real-browser tests, 752 backend unit tests at96.01% complete-source
line coverage, and131frontend unit tests at98.51%. Database tests used disposable Docker PostgreSQL;
UI flows used real HTTPS and a separate native worker with restricted installed roles. Ruff, purpose
comments, contract freshness, documentation links and wheel/source checks pass. Independent security,
documentation and desktop/mobile UI reviews pass; secret/static/dependency scans found no findings.
See the validation receipt (private historical evidence; not distributed).

The candidate includes local-only cancellation of unverified simulated work, eight-table explicit
owned-laptop reset, and ten-column safe audit CSV. Broader OCI creation/activation/bootstrap/IAM,
real import/termination effects and recovery remain qualification work. The existing approved full
configuration/finance dashboard is not claimed complete by the basic Tenancies entry point.

Explicit checkpoint refinements: a currently unmapped LOB case offers permanent Ignore; conditional
Complete/Resolve is offered once the person actually has a mapping. Other conditional reviews retain
their relevant-facts closure. This is a deliberate simpler interaction, not a fictitious LOB assignment.
Malformed CSV remains a parser rejection without a canonical feed; retained domain-rejected feeds
and their diagnostics remain distinct. No new durable malformed-upload journal is introduced.
Qualified full-feed absence/return is tested separately from continuous presence, partial feeds and
No tenancy required; old associations are never automatically restored.


The local installation was backed up and advanced from0008 to0009, preserving existing employee/feed/
version/audit and authentication evidence. API and worker were restarted; no human organization reset
was performed. Private test CSVs matching the current local configuration are under
`.local-dev/application/scenarios`; public [synthetic examples](../../backend/examples/organization/README.md)
use the separate sample two-LOB configuration. Local CSVs and backups remain ignored and private.
