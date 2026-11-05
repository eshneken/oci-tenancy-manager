# Manual review: tenancy detail, shared access and onboarding

3 November 2026 · Qualified and installed local refinement · Local simulation only

[Workflow field guide](../reference/organization-workflows.md) ·
[Guided onboarding](../reference/tenancy-onboarding.md) ·
[Override editing](../reference/tenancy-overrides.md)

## Choose a safe review installation

Use a dedicated synthetic local test installation and its own API/worker/database, not an OCI
parent or a saved employee workspace. The separately scoped Atlas Test installation normally uses
https://127.0.0.1:8444; port alone is not proof that its data is disposable. Confirm the installation
and synthetic records before changing anything. Preserve the main instance on 8443 and all existing
lab records. This runbook does not authorize reset, seed, credential extraction, live OCI action or
publication. Sign in privately with an already enrolled administrator; do not paste factors into chat.

Keep the API and its separate foreground worker running. Use the
[parallel-instance guide](parallel-local-instance.md) for installation-specific commands; always
carry that installation's explicit directory. Do not run a default-directory reset to prepare tests.
The failure-injection and old-intent compatibility cases below belong to disposable automated tests,
not manual database edits or hidden production UI controls.

## 1. Tenancy detail and registration timestamp

Open an active synthetic tenancy. Confirm a distinct Overrides section: inherited categories have
an explicit empty state, configured ones list their categories, and Manage overrides opens the
existing editor. An inherited state is not a new verified-health claim. Keep baseline update and
override editing visually separate.

Confirm the redundant top Manage owner & associations shortcut is absent. Open the owner and a
member through their existing names, and check that contextual Transfer owner/Remove member still
reach the appropriate dialog. Do not perform a transfer merely to test the removed shortcut.

In the inventory, hover and keyboard-focus Status. The tooltip shows Created with a UTC timestamp;
Escape dismisses it while focus stays usable. This reads local registered created_at, including
imported tenancies, not an observed OCI creation timestamp. Check narrow layouts without adding a
new permanent date column or losing the status label.

## 2. Assign a shared member to an existing compartment

Choose a synthetic managed employee with valid accountability, an active shared tenancy and no
current association to that child. Start Add to shared tenancy. Select the existing-compartment
option and choose a discovered non-root compartment in that child. Preview the selected exact OCID
and submit once. Follow the queued operation to verified simulation.

The active association must retain the selected compartment binding/name; it must not substitute
a newly generated compartment. The tenancy and unrelated members remain active. Root/foreign/
unknown compartments and stale scope must be rejected by server tests, even if a crafted request
bypasses picker choices. An existing-compartment request cannot also include parent/new-name inputs.

Repeat with a different synthetic employee using the new-compartment option. Choose a discovered
parent and an explicit new name; the returned new compartment has that parent and a distinct bound
OCID. Existing-member assignment must not silently switch to this creation flow.

## 3. Remove shared identity access while retaining resources

From the first test member's association, choose Remove member and review the exact child/member
context. Submit and follow its operation. Completion records the exact association, child and
personal-user receipt, with both required proof fields explicitly true: group memberships removed
and user deleted in simulation. Neither omitted field can default to successful proof. Operation
detail retains two verified steps, remove_member_groups:{association_uuid} and
delete_member_user:{association_uuid}. The registry update and immutable evidence commit together.

The member disappears from current membership; history retains the association/compartment. The
shared tenancy, owner and other members remain. Manual cleanup guidance identifies the retained
compartment and directs its owner to review only the departing user's resources outside the tool.
The shared compartment and other members' resources must remain intact. There is no resource
inventory, resource purge, delete_compartment or cleanup-complete verifier. A missing/mismatched
receipt must leave membership retirement uncommitted in automated negative tests. Do not interpret
a successful local receipt as actual OCI identity deletion.

## 4. New onboarding applies the frozen published baseline

In this isolated installation, publish a synthetic baseline v1 with recognizable policy/quota
statements, whole-unit budget and tags. Create or import a synthetic tenancy through the ordinary
person action. Record the operation's displayed selected version. Acceptance is queued, not active.
Follow the existing simulated handoff and exact cleanup-review steps.

Before starting setup, publish a different v2 in the same isolated workspace. Reopen the pending
operation: it must still display the complete frozen v1 snapshot, and it must apply/read back v1.
New operations admitted afterward select v2; the original operation never silently switches.

Start setup. Version 2 requires a published frozen baseline; missing/unpublished pins or unrelated actions are
invalid, while accepted version 1/absent-version intents keep their compatibility semantics.
New version 2 progress includes initial permanent/required access checks,
configure_baseline for policy/quota/budget/tags, verify_configured_access, then retire_temporary.
Only complete setup activates ownership. Tenancy detail shows the v1 selection and last verified
baseline, with simulation wording. A version link opens that exact publication; later latest links
do not rewrite this result. No tenancy-specific override revision should be invented by onboarding.

## 5. Automated recovery and compatibility review

These cases require controlled provider fakes in the disposable unit/PostgreSQL suites, not manual
changes to a saved installation:

- Fail a category after an earlier category verifies. Partial observation remains, verified baseline/
  timestamp does not advance to a partially verified target, temporary access remains, and retry
  reads matching prior state before skipping writes.
- Let category application pass, then fail final automation or required-access verification. The
  category verification remains truthful, but ownership is still pending and temporary access is
  not retired. Retry resumes the incomplete suffix against the same frozen baseline.
- Supply missing/extra/duplicate/wrong-child/wrong-user removal receipts. No local unmapping or
  success evidence may commit. Include the real transaction rollback case separately from stubs.
- Replay existing/new compartment requests with their original request identity. Omitted/null new
  input retains legacy serialization; changed input with the same key conflicts.
- Resume already accepted onboarding version 1 and absent-version intents. Their historical graph,
  stored hashes and pins stay unchanged; do not retrofit version 2 or claim old setup applied a recipe.

Local source-unit, disposable PostgreSQL/native-worker, HTTPS-browser and independent reviews now
pass. Both saved-runtime upgrades and all 18 table-preservation checks pass. Earlier receipts remain
historical and do not qualify this new source. Real OCI access, managed-object grammar,
Vault custody and network recovery remain outside this local runbook.


## Qualified saved-instance status

Both saved instances are upgraded from 0016 to 0017 without reset or backfill. Private backups are
retained; all old columns/rows across the 18 existing tables have matching fingerprints. Baselines,
accepted pins, overrides and history are preserved. Both API/worker pairs are running and serve
matching per-instance qualified frontend snapshots, rather than the mutable development build.
Current assets/liveness/direct routes return HTTP 200 and private APIs reject unauthenticated reads
with HTTP 401. Reload the open browser page once to load the updated interface.

The 1,002 backend and 266 frontend unit tests pass their separate complete-source coverage gates;
all 1,237 combined backend/PostgreSQL/native-worker/browser cases pass. The additional final native
picker transition/assignment/removal case also passes after the last UI fix. These are local
qualification results; no real OCI, production secret custody or resource-purge action is qualified.


Local qualification and saved-instance receipt (private historical evidence; not distributed).
