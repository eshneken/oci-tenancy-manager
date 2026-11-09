# Automation administrator assignments

The Required users panel distinguishes the automation account's existence from two required
administrator assignments: membership in the exact built-in Administrators group, and an
Identity Domain Administrator role grant in the captured domain application. Checks are simulated
until the real provider is qualified. They do not certify all effective privileges, API signing,
password readiness, console login or recovery-account permissions.

## Read and display contract

Refresh user data uses the existing authenticated asynchronous required-user check. Both assignment
families are read without holding database locks; ordinary page reads only project stored results.
Complete, authorized, supported reads yield Verified in simulation or Missing or disabled for each
assignment. Denied, incomplete, unsupported, wrong-resource, failed or missing legacy captures yield
Unable to verify. Explicit direct user grants and grants via the captured built-in group are supported;
unresolved indirect membership is unverified. No name matching, arbitrary policy interpretation,
repair, fallback credentials or automatic privilege escalation is introduced.

Assignment results retain their own checked timestamp. The footer displays its UTC date as the
assignment-check operation link, alongside the presence-check date after all badges. Full timestamps
remain in hover titles and time metadata; they are unchanged in storage.
After 24 hours they show Check out of date. A replaced automation connection/identity invalidates
old proof; harmless registry metadata edits preserve compatible results. Presence stays independent.
Inventory links missing/outdated assignments to the same tenancy detail evidence. These links are
status indicators, not new actionable navigation badges or repair buttons.

## Fields and persistence

No tables or migrations are added. Existing immutable onboarding outcome JSON retains
`required_users.automation_administrator`:

- `binding`: exact `domain_ocid`, automation `scim_resource_id`, built-in `group_id`,
  domain `application_id` and administrator `role_id`. Group/application/role IDs are SCIM references,
  not OCI IAM group OCIDs or display labels.
- `facts`: the independently observed binding, `authorized`, `complete`, `supported`, `builtin_group`,
  `group_enabled`, `role_enabled`, `user_enabled`, `group_members`, `role_users`, `role_groups`.
  Each assignment collection is bounded at 2,048 IDs; complete pagination is mandatory. An adapter
  exceeding supported coverage must report incomplete rather than truncate and certify absence.

Existing `required_user_check_outcome` JSON retains optional `administrator_access`: exact read
`context` and automation `target`, `checked_at`, and `result.group` / `result.domain_role`
(verified, missing, unknown). The existing user-presence row references this immutable audit event;
there is no duplicate status table. Attempt, connection, workspace/child/domain/subject and
30-second read-window fences apply before publication. Superseded/late results cannot remain positive.

The detail API exposes `users[automation].administrator_access`; inventory exposes
`required_users.administrator_access`. Both use `AdministratorAccessView`:
`group`, `domain_role` (not_checked, verified, missing, unknown), `stale`, `checked_at`, `operation_id`.
Positive/negative claims require dated provenance. Raw assignment lists and provider errors are not
exposed in APIs, Operations summaries or audit exports. Omitted legacy capture/evidence stays omitted
in historical hashes. It is never backfilled from existing users or current desired settings.

## Local review

Create or import a new simulated tenancy and finish setup. Open its tenancy detail, then Refresh
user data. Automation should show Present plus two Verified in simulation assignment results.
Navigate away and reload: the dated results persist. Recovery permissions remain Not checked;
its separately implemented console policy controls are unchanged. Existing tenancies lacking the
new capture show Unable to verify after a refresh. Refresh does not configure assignments.

Missing, disabled, denied, partial, substituted and late-read scenarios are exercised through
independent unit fixtures and disposable PostgreSQL tests, not a product fault-injection control.
Real group/role discovery, complete pagination and actual API behavior remain manual qualification
items in the [real OCI test manifest](../how-to/real-oci-test-manifest.md).

The [9 November qualification receipt](../history/automation-assignments-ui-checkpoint-2026-11-09.md) records complete gates, independent reviews and preserved local previews.
