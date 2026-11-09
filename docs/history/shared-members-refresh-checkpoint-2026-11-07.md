# Shared-member entry and single provider refresh — 7 November 2026

[Membership entry](../reference/organization-workflows.md#add-a-member-from-a-shared-tenancy) ·
[Required-user refresh](../reference/required-users-screen.md#consistent-provider-refresh-terminology--7-november-2026)

## Result

Active shared tenancies provide Current members → Add member. The bounded employee chooser
excludes current/unavailable profiles and opens the existing authoritative membership preview
with this child preselected. Continue does not itself grant access. Compartment choice, admission,
worker verification and historical association rules remain unchanged. Individual/inactive/busy
entry-point guards and normal session/authorization boundaries remain intact.

There is one normal acquisition action per section: Refresh costs and Refresh user data. Both
request a fresh asynchronous provider read; local development still uses the simulator. Required
users has no second saved-record refresh button. Pending polling updates the result automatically.
A failed initial/background record load offers Retry loading users, which only retries that read.
Page-level Refresh reloads stored records. User refresh does not repair accounts, enroll access
or verify permissions. No API/schema/grant/dependency or database migration changes.

## Qualification

- Complete backend unit gate: 1,639 pass; 9,341/9,716 lines, 96.1404%, all 139 modules.
- Final complete frontend unit gate: 480 pass; 1,838/1,891 lines, 97.19%, all 37 modules.
- Full disposable PostgreSQL/native worker/SMTP/HTTPS browser suite: all 378 pass in 480.655 seconds,
  zero failures/errors/skips, no aggregate timeout. This full run preceded the final removal of
  the redundant user-record button after the user's clarification.
- Final build after that UI-only simplification: the complete affected native HTTPS browser/worker
  journey passes again (one selected integration case, zero failures/errors/skips). Its existing
  assertions/timeouts remain unchanged; other cases are intentionally deselected in this focused
  repeat, not claimed as another full-suite run. It exercises member selection and exact child
  continuation, actual queued user refresh, persistence and lifecycle regressions.
- Independent documentation, security and UI/UX reviews pass. All nine fresh toolbar/picker/user
  frames at 1280/390/320 pixels were inspected privately; desktop toolbar centers are checked to 1px.
- Contracts, source documentation, Ruff, design predicates/links, publication/credential checks,
  Bandit and both dependency advisory scans pass. No assertions or quality thresholds were relaxed.

## Main preview and manual review

Main 8443 received a paired API/worker/immutable frontend installation after a private custom-format
backup. Exact row counts/content hashes for all 29 preexisting public tables match; no test feed
was loaded into live data. Health, SPA deep links, asset-byte identity and unauthenticated API
refusal pass. Parallel 8444 is healthy with its original asset fingerprint. No live OCI call,
GitHub push/merge or cloud deployment is claimed. Existing live OCI membership/presence cases
remain pending in the manual manifest; these UI entry/label changes add no new provider operation.

Reload main Atlas, open an active shared tenancy and choose Current members → Add member. Search
for an employee, Continue and review the preselected child and compartment before submitting.
Required users now shows only Refresh user data; selecting it requests fresh simulated presence
results. Refresh costs remains the analogous budget-data acquisition action.
