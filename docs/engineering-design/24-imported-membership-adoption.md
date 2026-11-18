# 24: adopt existing shared-tenancy identities

17 November 2026 · Source/full-suite and saved8443 publication passed · Exact milestone advisory exception approved; hosted checks required

[Design hub](README.md) · [Onboarding reference](../reference/tenancy-onboarding.md#shared-import-adoption-source-candidate--17-november-2026) ·
[Required-user checks](../reference/required-users-screen.md#adopted-member-access-source-candidate--17-november-2026) ·
[Live qualification](../how-to/real-oci-test-manifest.md#shared-import-existing-user-adoption)

This chapter describes the authored simulator implementation and bounded source validation below,
not a completed hosted milestone. The final complete suite
passed 477 tests with zero failures, errors or skips. The user explicitly accepted the current
picomatch risk for local development and requested the sole saved 8443 update; matched local
publication and preservation checks passed as recorded below. Normal hosted security gates remain required; the later [exact milestone advisory exception](../reference/frontend-security-exception.md) supersedes the earlier local-only restriction for this finding.
Live OCI identity-domain behavior remains separately Pending.

**Later source follow-up:** shared-root joining, verified owner promotion, authenticated current
grant expectations and persistent fake-provider observations now have a
[separate published local checkpoint](#root-membership-and-owner-promotion-follow-up--17-november-2026).
Its targeted validation and unchanged-source retry are not a clean full-suite milestone receipt;
the earlier477-test result does not qualify this later work. A later fresh integration run at app1564f8c passed481 tests with zero failures/errors/skips; see the final milestone update below.

Importing a shared child must bind its existing owner and selected members without creating
replacement human accounts, changing their credentials or reassigning resource compartments.
An Atlas owner/member role describes accountability, independently of existing OCI privileges.

## Bounded implementation

Use the existing import onboarding review, operation steps/audit, membership registry and required-user
check worker. No second import coordinator, identity registry, scheduler or new table is needed.
An additive membership JSON field records exact adopted domain/user/SCIM IDs, observed group/role
identifiers, policy evidence fingerprint and one or more existing scope references. Root is an
explicit shared scope, never a disposable personal compartment. Store provenance and frozen scope
in existing immutable accepted onboarding evidence before provider configuration.

New shared imports opt into this contract at admission. After bootstrap inspection, a read-only
provider inventory supplies identities and existing scopes. The administrator maps selected accounts
to current eligible organization people, including exactly the chosen owner, reviews broad/root
privileges, and explicitly approves adopting those grants for lifecycle management. Unselected
accounts remain preserved and outside Atlas management. No name/email match alone grants adoption.
Multiple members can share root or the same existing compartment; multiple scopes are supported.

Acceptance rechecks current authority, exact operation revision, inventory fingerprint, domain/child,
unique identities/people, owner eligibility and person reservations. Reserve all adopted participants
atomically with accepted evidence and continuation. The worker revalidates bindings/eligibility and
independently rereads inventory before any setup effect and final publication. Discovery changes
block rather than silently rebasing consent. Historical accepted operations retain their original graph.
Imported owner setup must use the adopted identity; automation/recovery setup remains separate.

## Current operator and contract flow

Only newly accepted **shared** imports carry `import_adoption_contract="import-adoption-1"`.
Individual imports and previously accepted operations retain their original behavior; opening a
tenancy or applying migration 0029 does not adopt any historical account.

After Verify handoff, **Existing users and access** lists independently discovered accounts,
administrator flags, existing scopes and group/domain-role assignment counts. Each account starts
at **Leave unmanaged**. The administrator selects an eligible employee for each account to adopt,
including exactly one existing administrator account for the already chosen accountable owner.
One person cannot map to multiple selected accounts. The explicit full-lifecycle consent and the
ordinary temporary-account cleanup confirmation are required before Start setup.

**Refresh existing users** requests fresh discovery through the same onboarding operation. It does
not accept adoption or silently update an already approved manifest. Changed inventory requires a
new review. The browser supplies only inventory fingerprint, exact account/person choices and consent;
the server selects association IDs, scopes and grants. New members must be included, currently
source-present employees with valid segment accountability, no unresolved absence and no conflicting
person reservation. The owner must satisfy the same domain eligibility with its existing reservation.

The inventory is bounded to 200 accounts, each with 1–50 scopes and at most 100 group and 100 role
identifiers; an accepted manifest has 1–50 members. Duplicate account, SCIM, grant, scope and selected
person identifiers are rejected. Root scope must identify the exact child; other scopes must appear
in the facade's verified compartment inventory. Display names and email addresses are evidence,
never automatic identity-matching authority.

## Source field authority

| Field or record | Implemented source meaning |
| --- | --- |
| `ExistingAccessInventory` | Exact child/domain, completeness and canonical ordering of observed human accounts. Incomplete discovery cannot authorize adoption or prove absence. |
| `ImportAdoption` | Reviewed inventory hash, account/person choices and `lifecycle_confirmed=true`; accepted only with Start setup. |
| `ImportManifest` | Server-assigned association IDs, selected exact identities and the complete reviewed inventory; authenticated against immutable onboarding action evidence on reuse. |
| `otm_tenancy_membership.imported_access` | Nullable `import-adoption-1` provenance containing domain, identity/grants/scopes and initial unselected account IDs. Migration 0029 adds one column and its guards, no new table. Historical rows remain null. |
| Existing membership compartment fields | The first canonical scope is retained for compatibility; the JSON retains all scopes. Root sorts first and does not become a personally owned or disposable compartment. |
| `ImportedAccessSnapshot` / `ImportedAccessCheck` | Frozen active adopted associations and known account IDs, then an independently timestamped comparison in existing immutable required-user check evidence. |

Database guards bind the provenance user to the membership user and prevent replacing accepted
provenance after initial pending admission. Typed application validation supplies the full nested
contract; the SQL JSON guard alone does not validate every nested identity or authorization rule.
No new application configuration field, scheduler, live-provider selection or credential store is
introduced by this slice.

## Removal and drift

Explicit adoption transfers full identity-lifecycle management to Atlas. Adopted identities follow
the SAME checks, transfer and offboarding/user-deletion rules as Atlas-created identities. There is
no preserve-imported-account operating mode. Import approval must explain that later explicit
removal can remove the user and their memberships; adoption itself never resets credentials or
changes existing permissions. Preserve provenance for audit, not as a weaker lifecycle authority.
Shared groups, root/other compartments and resources are never deleted merely because a person is
removed. Unselected accounts stay unmanaged. Transfers preserve exact bindings and scope metadata
when an existing member becomes owner or an owner stays a member.

Extend normal Refresh user data with separate imported-access observations, captured in the existing
immutable check evidence. Freeze membership/context fingerprints and all known managed identities;
perform reads outside database locks and recheck context before publication. Missing users, changed
groups/roles/scope/policy fingerprints and newly discovered unmanaged identities are distinct findings.
Denied/incomplete reads are Unable to verify, never Missing/Matching; read-only checks do not repair.
Record initial unselected users as explicitly unmanaged rather than reporting their mere preservation
as a newly introduced user. New normal Atlas members remain distinguishable from unmanaged additions.

The **Adopted member access** panel displays Not checked, Verified in simulation, Access drift, Unable to
verify or Check out of date, with per-account evidence and a check-operation link. A complete exact
read compares the recorded identity, group/role identifiers, scopes and policy hash. It can report
Missing only for an absent selected account; changed evidence is Different. Initial unselected
accounts are not retroactively adopted. New unmanaged account IDs are shown separately and cause
a drifted result; checks do not offer silent account deletion/adoption or change existing grants.
Current-context evidence expires after the existing 24-hour freshness window. A changed membership
fingerprint or stale capture cannot remain a current Verified in simulation result. These observations remain
separate from automation/recovery presence, privilege, network and credential readiness.

### Transfer privilege evidence: local source follow-up and real-adapter gate

`imported_access.identity` retains **initial adoption provenance**, not a perpetually current grant
baseline. The first local publication above preserved exact binding/scope continuity. A subsequent
source follow-up now implements simulated replacement-owner grants, independent proof and current
expectation resolution. Its [targeted local checkpoint and saved8443 publication](#root-membership-and-owner-promotion-follow-up--17-november-2026) passed with the recorded full-run failures and successful focused retry, not a clean
full-suite milestone. Neither local implementation proves real replacement-owner administration.

The follow-up implements D22's requirement in the simulator to grant and independently read back
full replacement-owner root-resource administration AND the identity-domain administrator role.
An existing recipient's exact domain/SCIM/user identity is read before new admission; no name or
registry role substitutes for this identity proof. Partial or uncertain grants
cannot publish a verified transfer merely because the person became the recorded owner. Retaining a
former shared owner as a member preserves the explicitly accepted access; a member label alone
neither removes administrator grants nor grants them to another person.

Subsequent imported-access checks derive the **current expected** grant set from the initial
provenance plus the existing immutable accepted and independently verified transfer/operation
evidence. Never overwrite initial provenance, trust an arbitrary observation as the new baseline,
or treat every newly observed privilege as an approved transfer. Keep exact identity, target,
operation and generation binding; incomplete evidence remains Unable to verify. Reuse existing
operations, steps and audit rather than introduce another table, coordinator or writable grant head.

The optional `AdoptedIdentity.expected_owner` extension contains the accepted transfer operation
ID and the narrowly authorized expected identity/grant delta. It preserves the original `identity`
instead of overwriting import facts. Before using this expectation, reads authenticate its exact
operation/association/person/child against immutable accepted intent and independently verified
outcome evidence. `compare_imported` uses that authenticated expectation when present, otherwise
the initial adopted identity. Unrelated observed extra grants are never absorbed as expected.

New `FrozenAssociation` fields `owner_administration_required` (false/omitted for historical
intents), `recipient_domain_ocid` and `recipient_scim_id` bind the conditional receipt requirement.
`LifecycleCompletion` and immutable `OrganizationActionOutcome` carry `owner_administrations`;
each `OwnerAdministration` proves the exact association/user/domain, administrator group and domain
role, root policy/group linkage, exact child scope, completeness and both privilege predicates.
The verifier runs before former-owner identity removal and again before registry publication.
Missing, duplicate, partial, foreign or mismatched proof cannot publish ownership or authorize the
outgoing deletion. Historical accepted transfers retain their original frozen contract.

Real privilege changes and provider interpretation remain **Pending**. Required tests must cover
successful full grants becoming expected, failed/partial grants staying unverified, unrelated extra
grants remaining drift, retained former-owner access and replay/concurrent transfer evidence.
Do not enable the real adapter until those requirements are satisfied.

### Shared-root joining and independent fake-provider state — source follow-up

Join shared tenancy can now select the exact existing root compartment as well as verified non-root
compartments. The root binding uses `compartment_ocid=child_ocid` and `parent_compartment_ocid=None`.
Root resource scope is broad, but does not automatically confer identity-domain administration or
make the member an owner. Explicit owner promotion still requires the separate proof above. Shared
groups, root/other compartments and resources are never deleted as personal-member cleanup.

Laptop API/worker composition injects persistent fake-provider `PrivateJsonRecords` under the
private `member-access-inventory` directory. Each exact child/user has scoped hashed record names,
bounded validated reads, existing file locking and atomic writes. Observations and deletion
tombstones survive process restart; registry publication is not the source of provider success.
In-memory state remains available for isolated unit simulation. This directory is not a new SQL
table, application configuration field, OCI inventory or credential store. No SQL column, migration,
SVG/PNG or schema asset change is required by this follow-up.

The membership presentation drops the redundant imported-membership subtitle; exact provenance,
all scopes and full-lifecycle consent remain inspectable. This source UI adjustment does not
weaken adoption/removal authority. Follow-up validation and saved publication are recorded in the
dated follow-up receipt below; the earlier477-test receipt describes the preceding source candidate.

## Qualification

Use synthetic fixtures only. Cover shared root, shared non-root/multiple scopes, exact owner reuse,
no human account creation/reset, duplicate/foreign/protected identities, changed inventory/eligibility,
replay and partial failure, ordinary identity deletion/shared-resource preservation, transfers and
complete/unknown/unmanaged drift. Include restricted-role PostgreSQL/native worker and responsive
Playwright scenarios, backend/frontend 95% complete-source unit gates and independent reviews.
Do not mutate saved8443 or perform live OCI calls while implementing. Actual identity-domain read,
policy completeness/propagation, identity deletion and supported domain variants remain Pending
in the live qualification manifest until separately authorized provider tests establish them.
The current simulator enumerates independently derived synthetic existing accounts; it is not a
discovered real domain inventory or a qualified provider permission model. Network-backed onboarding
must also split provider dispatch from database evidence transactions and qualify uncertain outcomes
before a real adapter can use this composition.

## Source validation and review disposition — 17 November 2026

| Check | Recorded source-candidate result |
| --- | --- |
| Backend unit-only complete-source coverage | 3,242 tests passed; 95.0976% line coverage. |
| Frontend unit-only complete-source coverage | 656 tests passed; 96.97% line coverage. |
| Focused existing PostgreSQL regressions | 73 lifecycle, transfer, notification and presence tests passed. |
| New adoption integration/browser scenarios | Four disposable PostgreSQL cases and one native browser scenario passed. |
| Responsive review | Independent source/responsive review passed at 1280, 390 and 320 pixels. |
| Python/security/publication/documentation checks | Python advisory audit, Bandit, secret scan, publication guard and documentation checks passed. These do not replace the npm audit or live qualification. |
| Final complete required suite | Passed: 477 tests, zero failures/errors/skips, valid test evidence and exit 0. The owned disposable PostgreSQL run built the frontend from current source and included browser integration; no persistent database was used. This does not waive the blocked dependency gate or authorize saved publication. |
| npm dependency advisory audit | Failed after network connectivity was restored: eight high-severity reports trace to the underlying picomatch ReDoS advisory and affected dependent development tools. A dated user acceptance permits the local-development/saved8443 action below; the audit was not clean and the hosted gate was Blocked at this initial checkpoint. The [later exact milestone approval](../reference/frontend-security-exception.md) supersedes only that finding's acceptance scope. No forced downgrade or dependency change was applied. |

Independent Astra design review's material contract findings were addressed. The independent
security review's eligibility finding was fixed, and all three source UI findings were corrected.
Browser review also found and verified two corrections: a direct accessible `aria-label` replaces
an absolutely positioned hidden label that escaped layout bounds, and stored running refresh work
now projects public pending state so progress remains visible. Unit and PostgreSQL regressions
cover the running-to-pending projection; the native browser/responsive checks cover the UI flow.
All nine review/membership/access captures at 1280/390/320 pixels received independent responsive
review. The complete ER table/column name sets were checked against fresh empty-database reflection
(34 tables/439 columns/89 foreign keys); schema-only SVG/PNG were regenerated and visually reviewed.
Independent asset privacy/provenance review precedes any publication-manifest hash update.

These are source/simulator receipts only. No saved update was performed by the validation itself;
the subsequently authorized local deployment is tracked below. No real OCI call or Git
commit/push/PR was performed for this validation. Required hosted evidence remains a completion/merge
gate; the local acceptance below does not change protected-master or hosted scanner requirements.

The restored-connectivity audit supersedes earlier strict-TLS transport failures, not a passing
dependency result. The locked picomatch is 4.0.7. On 17 November, the official
[GHSA-fc5q-39xc-vjpf advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
(CVE-2026-112366) listed versions through 4.0.7 as affected and no patched version. The slice did not
introduce this dependency change; that does not waive the required security gate. Independent
security review confirmed the advisory has no supported patched release. An application-request
untrusted-glob execution path was not established, and no additional blocking application defect
remains after the eligibility correction. The user subsequently accepted the bounded local risk
below; the hosted dependency gate and milestone were blocked at that checkpoint. The later
[exact milestone advisory approval](../reference/frontend-security-exception.md) supersedes that
acceptance limit without changing the earlier audit result or waiving required hosted checks.

### Scoped local-development risk acceptance and follow-up

On 17 November 2026, the user explicitly accepted the current picomatch advisory risk for local
development and requested deployment to the sole saved 8443 application. This permits that local
action only. It is not a passing npm audit, an organization-wide advisory exception, approval of
production deployment, permission to bypass hosted CI/security gates, or authorization for a Git
commit/push/PR. The known advisory, affected locked version and eight audit entries remain recorded.

The `watch-picomatch-security-fix` automation checks weekly on Monday at 09:00 America/New_York
for a supported fix. A future patched dependency update must receive normal testing and independent
reviews. The watch does not automatically deploy updates or waive current dependency checks.

Saved8443 deployment **passed** on 17 November. A verified private PostgreSQL archive (2,909,959
bytes, mode0600) and private configuration/custody copies preceded migration0028→0029 and matched
backend, locked-environment, frontend and worker snapshots. Pre-start fingerprints of all33 existing
data tables' old columns matched exactly; private state/settings/custody hashes were unchanged.
After startup, only Alembic's version marker and the native worker-registration table differed;
protected organization, administrator, tenancy and baseline data remained unchanged. Served index,
JavaScript and CSS hashes matched the qualified asset snapshot, and API/worker publication matched.

Liveness returned200 and an explicit restricted-API-role database probe passed. The local factory
does not compose a readiness callback, so `/health/ready` returned503 as expected; this is recorded
as a local composition limitation, not misreported as a passing readiness endpoint or production
readiness. New shared imports can use adoption; historical membership provenance remains null
without automatic adoption/backfill. No additional persistent review instance or real OCI effect
was introduced. This local publication relies on the scoped user risk acceptance, not a clean npm
audit or permission to bypass normal hosted/merge gates. The weekly Monday09:00 watch remains active.


## Root membership and owner promotion follow-up — 17 November 2026

Backend complete-source unit validation passed 3,274 tests at 95.0648% line coverage; frontend
unit validation passed 657 tests at 96.97%. Targeted PostgreSQL validation passed 28 cases,
and the enhanced import/root/promotion browser scenario passed. Independent security review ran
32 owner-access units successfully; independent design and responsive UI reviews passed.
Documentation, contracts, Ruff, Bandit, secret scanning and publication checks passed.

The complete integration attempt recorded 479 passes and two failures out of 481 tests, without
errors or skips. The broad simulation browser timed out after20 seconds with its second inspection
still queued; its dependent permissions test consequently lacked organization data. An unchanged-source
isolated rerun passed both tests in183.31 seconds, including the complete broad browser lifecycle.
This is a targeted local checkpoint with a successful retry, not a clean full-suite milestone receipt.

The matched saved8443 API, worker and frontend update passed TLS liveness, restricted-role database
probing and served asset hash checks. A validated2,947,226-byte private database backup preceded the
update. Schema remained0029; all33 non-Alembic tables matched before/after installation. After startup,
only native worker registration changed. Protected organization, administrator, tenancy, membership,
baseline and private settings/custody data remained unchanged. Local readiness remains503 because the
local factory has no readiness callback. The existing local-only picomatch acceptance remains scoped;
hosted security gates are unchanged. No Git publication or real OCI mutation occurred.

The legacy simulator lookup for an unseen `otmsim` plus32-hex user identifier synthesizes compatibility
fixture facts. It is synthetic-only and is not independent account-existence evidence. Stored records
and deletion tombstones take precedence; a real adapter must never inherit this fallback. Real OCI
authorization, grant propagation, identity deletion and domain variants remain Pending live qualification.


## Publication candidate review — 17 November 2026

The reviewed source candidate preserves the real-provider qualification boundary above. Fresh
backend validation passed3,274 unit tests at95.0648% complete-source line coverage; frontend
validation passed657 tests at96.97%. Independent application/security, documentation and responsive
reviews found no remaining blocking source or publication finding. Publication and credential
scans passed; schema-only ER assets retain their reviewed hashes. Private runtime inputs, real
employee data, credentials and browser captures are excluded.

The fresh npm audit still fails on GHSA-fc5q-39xc-vjpf in picomatch4.0.7, now reporting ten high
entries including dependents, with no patch reported. The local-development acceptance does not
waive this required hosted gate. Local container verification also remains unqualified: two build
attempts failed on Alpine repository DNS resolution before image/security checks completed. No
scanner, dependency threshold, timeout or protected-branch requirement was weakened. This candidate
is not approved for merge while required checks fail or remain missing. Fresh integration and
hosted-check results must be recorded independently of the older checkpoint receipts.


## Milestone advisory approval and fresh integration update — 17 November 2026

The repository owner subsequently explicitly approved merging with the one existing development-only
picomatch finding. The [exact frontend dependency exception](../reference/frontend-security-exception.md)
supersedes the earlier local-only acceptance for that finding, not the historical failed audits.
`scripts/check_frontend_audit.py` still runs npm audit and checks the complete report: only the
exact high-severity GHSA/CVE root at locked development-only4.0.7, with no available fix, and
development-only dependents whose entire cause graph has that sole root can pass. Other findings,
mixed/rootless graphs, production packages, changed pins/scope/severity, available fixes and
malformed/unavailable evidence remain blocking. The audit is not clean and no general security
job, image-check or protected-master bypass is approved.

Fresh full integration at application source1564f8c passed481 tests with zero failures/errors/skips.
This is a separate new result, not a relabeling of the earlier479/481 attempt or focused two-case
retry. Frontend remains657 units at96.97%. The expanded backend run passed3,301 units at95.0648%, including27 audit-policy tests; the previous
3,274-test result retains its original scope. The actual npm evaluator reported10 accepted findings
and zero blocked findings while retaining the original raw findings. Independent security review
passed all27 policy tests and found no blocking issue with the exact exception.
Local container qualification remains blocked by DNS resolution; hosted container/security checks
must establish the required outcome before merge. Actual audit evaluation and independent review do not imply a clean vulnerability scan; real OCI
qualification is still Pending.
