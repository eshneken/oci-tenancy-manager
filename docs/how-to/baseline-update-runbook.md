# Manual check: baseline updates

Use the local Atlas app. OCI execution is simulated: these steps change local baseline assignments
and simulated observations, not cloud resources. Keep the current organization; no workspace reset
is needed. For repeatable experiments use the separate runbook instance at
[https://127.0.0.1:8444](https://127.0.0.1:8444). The main instance remains
[https://localhost:8443](https://localhost:8443).

## 1. Check exact versions and return context

Open an active tenancy. Its Selected baseline is a link with the version number. Open it, verify
spacing above the headline, then choose Back to tenancy. Opening a version from Configuration
instead should offer Back to baselines. An onboarding link from an operation should offer Back to
operation; the same panel opened on a tenancy should return to that tenancy.

On a create/import form, enter values and inspect its Version link. Back to create/import tenancy,
browser Back and browser Forward should retain the form values. Cancel without starting work.

## 2. Publish a later recipe

Under Configuration choose New baseline, make an identifiable change such as a whole-unit monthly
budget, save, then Publish. It automatically becomes latest for subsequent create/import operations.
Existing tenancy selections and already-accepted onboarding operations remain unchanged by
publication alone. Older versions remain read-only.

## 3. Update one tenancy

Open an active tenancy on an older version. Choose Update to baseline vN. The confirmation shows
that exact target version and one ready tenancy. Inspect the recipe and return without leaving the
confirmation. Cancel first: the selected version must remain unchanged.

Reopen and Start update. This queues work; progress is separate from acceptance. Once all four
managed categories match, the selected and last verified version both show vN with an explicit
simulation qualifier. The update action disappears until there is more work. The selected-version
link and last-verification link remain usable.

A tenancy with latest selected but no complete simulated verification offers Apply baseline vN.
This does not imply its earlier required-access onboarding checks proved full recipe application.

## 4. Update the remaining fleet

Under Configuration choose Update existing tenancies. The confirmation shows the ready count and
any exceptions. Pending onboarding is excluded and retains its original recipe. Every displayed
exception must clear before Start update is enabled; the tool cannot silently update just a ready
subset. Cancel changes nothing.

Start and watch per-tenancy progress. Reload the page: the accepted operation remains accessible
from the URL. View operation history opens recorded results; Open baseline update there returns to
the actionable progress screen. Current selection and verified results can be inspected on each child.

## 5. Inspect history

Audit history shows acceptance, each child verification/failure and any responsible-admin retries.
Version links return to audit history. The original accepted baseline and targets do not change when
a later version is published. Successful children remain successful when another child fails.
Retry incomplete updates is offered only when supported and authorized; it never replays verified
children. Unsupported historical failures do not create navigation badges.

Failure injection, revoked authority, stale previews, partial category persistence, queue/audit
rollback and maximum Unicode inputs are covered by automated tests against disposable PostgreSQL.
Avoid changing database rows or runtime permissions in either saved instance to simulate them.

[Complete field/transaction reference](../reference/configuration-updates.md) ·
[Test matrix](../engineering-test-plan.md#baseline-only-asynchronous-update-regression-matrix)

## Completion and compact inventory checks

After an individual update succeeds, its update/progress panel should disappear; selected and
verified fields retain the result. There is no completed Refresh progress button. If a later baseline
is published, the update action reappears. In the tenancy inventory inspect Status: the assigned
version is clickable and returns to the inventory, Latest distinguishes latest selection (green only when verified), and an older
assignment links to its tenancy for updating. A completed operation link shows its UTC date only.

After bulk success choose Acknowledge. The list disappears, history remains in Operations/Audit,
and Configuration shows the green idle indicator if no further update is needed. Reload: the list
stays dismissed. Opening that operation's progress URL intentionally shows its historical receipt
again. Acknowledge must not appear for unfinished/blocked work. Audit targets should show affected
employee/tenancy names alongside the operation link, with registered tenancy links usable.
