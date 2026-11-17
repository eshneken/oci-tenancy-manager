# Hosted Atlas administration

13 November 2026 · Design-stage operator runbooks · Not yet qualified for live execution

[Documentation home](../README.md) · [How-to index](README.md) ·
[Environment/release contract](../engineering-design/24-environments-and-promotion.md)

These procedures describe the intended staging/production operations. The held infrastructure
plan/review/apply workflows are implemented as source; live qualification remains pending. Application
deployment workflows, hosted maintenance controls and environment links still need implementation and qualification.
Before go-live, replace proposed entry-point names with actual links and tested instructions, and
have an administrator other than the author complete each procedure in staging. If a referenced
control is missing, stop; do not invent a CLI, edit database rows or bypass a protection rule.

## Choose the procedure

| What is changing? | Use this procedure |
| --- | --- |
| Application/API/frontend/worker code or its packaged dependencies | [Application update](#application-update--the-normal-release-path) |
| OKE/node images, PostgreSQL engine, capacity, networking or platform access | [Infrastructure update](#infrastructure-update) |
| Both, with a compatibility or ordering dependency | [Combined infrastructure-and-application update](#combined-infrastructure-and-application-update) |
| An existing supported application setting or schedule only | [Settings-only update](#settings-only-update) |
| Verify or take a recovery copy | [Backup operations](#backup-operations) |
| Recover lost/corrupted database state | [Restore operations](#restore-operations) |

After initial setup, application promotion is the normal release path. Routine application updates
do not run Terraform or upgrade the database engine. Infrastructure stays version-controlled and
receives deliberate maintenance, including security/network changes when necessary; infrequent
changes do not mean platform patching can be skipped. A new application schema migration uses the
application path unless it also requires an infrastructure/engine change.

## Before any change

A release ID identifies one build; an image digest is its immutable content fingerprint. Point-in-time
recovery (PITR) restores database state to a selected past timestamp. The 15-minute recovery point
objective (RPO) bounds acceptable lost committed data; the four-hour recovery time objective (RTO)
measures return to usable application service, not merely database startup.

1. Identify the change owner and choose **staging** or **production**. Open the correct GitHub
   Environment and OCI tenancy in `us-ashburn-1`. Compare the parent, cluster, namespace and database
   identities with the protected environment record. Do not rely on a similar resource name.
2. Record the installed release/configuration and platform versions, desired versions/release ID,
   purpose, maintenance impact, acceptance checks and the point at which you will stop or recover.
   Keep private resource IDs and operational evidence in the restricted change record.
3. Verify the required CI/security checks and access. Staging qualification comes first; production
   requires the named human approval. Never obtain production credentials from a staging job.
4. Check alerts, database recovery-window freshness, recent backups and queue health. Resolve or
   explicitly own urgent credential work before downtime. Downtime never extends a disclosed
   recovery password's original deadline; arrange independent operator closure if necessary.
5. Confirm no conflicting infrastructure/application/settings change is running. Do not cancel an
   active apply, migration or worker drain just to get your change started sooner.

**Stop on:** wrong target, missing approval/evidence, incompatible version, unexplained destructive
plan, failed backup/recovery readiness, unsafe credential deadline or unknown provider effect.
Do not repeatedly click Run to resolve an uncertain operation. Inspect its actual state first.

## Application update — the normal release path

1. Select an approved protected-master source revision with passing required checks. The
   [qualified publisher](application-releases.md) follows the exact successful master-push Checkpoint
   automatically. Select only its completed trusted candidate and manually run the read-only hosted
   verifier; its integrity result does not establish staging acceptance or deployment.
   Record the release ID and immutable image/public-source identities. Do not use `latest`.
   The deployment steps below remain proposed; OCI and durable-custody qualification remain Pending.
2. Run `deploy-staging.yml` for that release ID. Check that the selected target is staging and that
   email goes only to its approved test destination. The workflow validates compatibility, applies
   any reviewed migrations once, drains old workers safely and deploys the candidate.
3. Confirm the running image/platform identity matches the selected release. Verify sign-in,
   Tenancies/Organization views, database and worker readiness, applicable end-to-end journeys,
   required users/configuration/cost acquisition, notifications and scheduled-work health. Use only
   approved disposable staging children for mutating tests. Complete manual acceptance linked to
   this release where required by the change/test manifest.
4. If staging fails, stop. Repair in source, build a new candidate and repeat staging. Do not patch
   a running staging container and treat the old build as qualified.
5. Run `promote-production.yml`, selecting the staging-qualified release ID. Review the release,
   staging acceptance, current security scan, production settings and migration/rollback impact.
   Obtain production approval. Promotion uses the same tested image and bundle, without rebuild.
6. Confirm production readiness, installed digest/configuration/schema and worker/queue health.
   Verify sign-in and safe read-only checks. Do not replay destructive staging test scenarios
   against real production children as a smoke test. Record completion and monitor after rollout.

**If unsuccessful:** stop further promotion and inspect deployment/migration state. If the current
schema/settings remain compatible, use the controlled production path to restore the previous
staging-qualified image. A partial migration or unknown external effect requires investigation,
not automatic down-migration, database rewind or job replay. Use restore only for a separate
approved data-recovery incident.

## Schema-changing application release

Approved V1 policy — 13 November 2026: allow a brief maintenance window when an application
release changes the database schema. Releases without schema changes may use the normal rolling
application-update flow. Rehearse the same sequence in staging before production promotion.

1. Compare the installed schema with the exact candidate's bundled Alembic head. Review migration
   impact, backup health and the recovery decision before scheduling the window.
2. Close normal application admission and pause scheduled work admission. Gracefully drain API and
   worker activity before running the migration; investigate unfinished operations rather than
   killing workers or replaying external effects blindly.
3. Run one migration Job from the exact staging-qualified release, using the migration role.
   Runtime pods never perform DDL. The migration advisory lock prevents competing runners.
4. If migration fails, keep the maintenance window open and inspect the database state. Do not
   automatically downgrade the schema, restore a backup or start incompatible old pods.
5. Start the matching API and workers. Confirm exact-schema readiness, authentication, queue
   processing and safe read-only smoke checks. Reopen admission and schedules only after checks
   pass, then record the release and maintenance completion.

These are deployment requirements, not evidence of an installed maintenance switch or delivery
workflow. The hosted activation/staging rehearsal remains pending. Old API images fail readiness
once their bundled schema differs; rolling back an image is safe only when its schema is compatible.

## Infrastructure update

1. Select the platform change, supported upgrade path and maintenance window. Pin the proposed
   versions/images in reviewed Terraform source. Confirm the installed application, ARM images,
   add-ons, database roles/extensions and Procrastinate are compatible. Keep the application image
   unchanged so you can test the platform change independently.
2. Run `infra-staging.yml` in plan mode. Review every creation, replacement and deletion, state
   target, capacity/placement and effect on the database, networking and keys. Any unexplained
   replacement/deletion is a stop. Take the approved pre-change backup for high-risk DB work and
   verify it is usable; ensure quotas/capacity allow recovery and rolling-node surge.
3. Use the [reviewed-plan apply procedure](infrastructure-plans.md#apply-staging-test-explicitly-then-review-production)
   with the staging producer run and privately reviewed binary hash. Each plan allows one attempt;
   investigate failures and create/review a fresh plan rather than retrying it. For OKE, validate the supported version-skew/upgrade path,
   upgrade the control plane, then cycle/upgrade managed workers using the qualified approach.
   Updating a node-pool version alone is not proof all existing nodes were upgraded. Recheck all
   nodes, add-ons, workload placement and surviving capacity, with IMDSv1 still disabled.
4. For PostgreSQL engine updates, use the supported service operation for that source/target
   version and current configuration. A major upgrade is a separate rehearsed maintenance change,
   not a blind `db_version` edit or assumed zero-downtime patch. Validate required extensions,
   roles, native queue functions, TLS, migration state, row/history integrity and backup/PITR
   health. Do not copy destructive extension-removal SQL from a generic guide without review.
5. Complete staging acceptance on the upgraded platform, including relevant worker concurrency,
   connection/failover and restore checks. Record the actual platform versions and application
   digest tested. Stop if the target topology or behavior was not exercised.
6. Run `infra-production.yml` in plan mode using the same tested source/provider locks but
   production's own state and approved values. Review/approve this production plan and maintenance
   impact; never apply a staging plan to production. Re-plan/re-review if its inputs/state change.
   The consumer requires the same-source/component successful staging apply, explicit manual test
   confirmation, shared-field parity and qualified ARM image; no automated test proof is verified.
7. Obtain production Environment approval and apply its exact reviewed plan once through the same
   procedure. On uncertain failure keep the attempt marker, investigate actual effects/state and
   repair native failed-backend recovery state only through authorized manual handling.
   Confirm the installed versions and repeat safe production health,
   backup, deadline and capacity checks. Record completion. Do not build an application image
   merely because infrastructure changed.

**If unsuccessful:** inspect the provider work request and actual running versions before retrying.
An OKE control-plane upgrade cannot simply be downgraded; a PostgreSQL major-version upgrade must
not be treated as reversible by editing Terraform back. Use the qualified forward repair or
replacement/restore procedure appropriate to the failed step. Preserve the original database and
backups until the recovery decision is reviewed. Never assume restoring Terraform state reverses
cloud effects.

Official procedures to recheck for the selected versions: [OKE control plane](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengupgradingk8smasternode.htm),
[managed worker nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengupgradingworkernodes.htm),
[OKE upgrade precautions](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Upgrade-best-practices.htm),
[PostgreSQL major upgrades](https://docs.oracle.com/en-us/iaas/Content/postgresql/upgrades.htm).

## Combined infrastructure-and-application update

1. Write the exact order before starting: current application/platform, each intermediate state,
   final application/platform, required migrations and a stop/recovery decision after each step.
   Do not assume infrastructure-first is always safe.
2. If the existing app works on the new platform, qualify infrastructure first, then the new app.
   Otherwise, qualify a bridge application release that supports both old and new platforms,
   followed by the platform change and final app. If no compatible sequence exists, design and
   rehearse a maintenance/cutover plan before production approval.
3. Execute the complete sequence in staging using the separate infrastructure and application
   workflows. Check readiness and acceptance at each intermediate state. Record each candidate
   digest, platform/configuration revision, plan and migration result.
4. Obtain production approval for the tested sequence. Apply separate production plans and promote
   the exact staging-tested application releases in that order, stopping at the agreed checkpoints.
   Do not let independent queued workflows interleave or skip an intermediate compatibility check.
5. Perform the final safe production checks and record all installed versions. If any checkpoint
   fails, stop at that stage's recovery decision; do not blindly roll back every component together.

## Settings-only update

1. Record the installed image and current configuration revision. Review the proposed nonsecret
   setting/schedule change against that image's schema. If a new setting needs new code, complete
   an application release first. Preserve the previous compatible profile for recovery.
2. Run `deploy-settings-staging.yml`. Verify the configuration revision actually loaded by API and
   worker pods, regenerated schedules and affected behavior. Complete staging acceptance against
   this exact configuration revision and installed image.
3. Run `promote-settings-production.yml` using the staging-qualified configuration revision and
   independently validated production profile. Obtain approval and keep the installed image.
   Never copy staging email/tenancy/secret bindings to production.
4. Confirm production API and workers report the approved effective nonsecret configuration
   revision, all required consumers have rolled successfully, schedules have their intended timing
   and relevant readiness/behavior checks pass. Recheck environment routing and credential deadlines.
   Record the installed image/configuration pair and result without exposing secret values.

**If unsuccessful:** stop conflicting settings changes, inspect which consumers loaded the new
revision and reapply the previous compatible reviewed profile through the controlled deployment
path. Verify API/workers/schedules again. Settings rollback does not rewind existing sessions,
the database or OCI state, or resolve an unknown external effect automatically.

## Backup operations

1. In the correct OCI tenancy/region, open the PostgreSQL DB system and verify its identity.
   Check the approved automatic-backup and PITR policy against the
   [backup proposal](../engineering-design/06-platform-and-delivery.md#ashburn-v1-backup-policy-proposal--13-november-2026).
   Confirm successful recent backups and the actual recoverable time window; a backup name alone
   does not prove the 15-minute RPO can be met.
2. For a manual checkpoint, select **Create backup**, the intended restricted compartment and
   explicit expiry from the approved policy. Record its private reference and wait for the backup
   to become usable/ACTIVE. An accepted request is not a completed backup. Do not start the risky
   change if the required checkpoint fails or recoverability/key access is uncertain.
3. Check independent monitoring, retention/expiry, recovery-window freshness and backup/WAL/cost
   growth. Investigate failures; do not silently shorten retention or delete the last verified
   recovery source to meet a storage allowance. Avoid accumulating unexpired manual checkpoints.
4. Keep backup data, keys and sensitive logs out of the repository, chat and CI artifacts. Only
   authorized recovery operators perform reviewed deletion. A healthy HA replica is not a backup.

See [OCI backup creation](https://docs.oracle.com/en-us/iaas/Content/postgresql/create-backup.htm).
Repeat a restore drill before go-live, at the approved periodic cadence and after material changes.

## Restore operations

For a **drill**, use only the explicitly owned isolated test/recovery installation; do not stop a
healthy production system. For a **real incident**, follow the fencing and reconciliation requirements
of the [canonical manual restore procedure](../engineering-design/17-recovery-and-release.md#manual-database-restore-runbook).
Production-data drills stay in a restricted production recovery compartment, not staging.

1. Record the incident/decision time, affected installation and recovery owner. Identify the last
   good timestamp and actual recovery-window endpoint; calculate the possible committed-data loss.
   Preserve backup and key access and confirm quota/capacity for the new database. A target miss
   is reported honestly rather than hidden by changing the clock.
2. For an incident, stop/fence the original API, workers, mail dispatcher and schedules; prove old
   processes cannot mutate resources. Configure replacement maintenance/read-only mode outside
   restored DB state before startup. Independently own outstanding credential-closure deadlines.
3. Use the approved OCI PITR/backup restore procedure. PITR creates a new DB system, so verify its
   identity, private network/TLS endpoint, roles, schema and compatible application/queue version.
   Do not point a normal active deployment at the restored DB before holds are in place.
4. Invalidate restored app sessions and require fresh authentication/current entitlement. Inspect
   restored nonterminal operations, notifications and recent provider effects. Keep work held until
   reconciled with current OCI and Vault; a DB restore does not reverse either. Recovery passwords
   resolve Vault CURRENT under existing rules; API signing keys retain exact-version verification.
5. Validate read-only application behavior, histories, target bindings, backup/monitoring state and
   recorded reconciliation. Unknown effects remain held. An administrator explicitly approves the
   reviewed resumption of mutations; no bulk replay of restored jobs or emails is permitted.
6. Record when usable application service returned, not just when the database became ACTIVE.
   Compare with the 15-minute RPO/four-hour RTO targets. Resume owned schedules/work gradually and
   monitor. Preserve the original system until approved cleanup. For a drill, remove only the
   explicitly owned drill resources after review and retain restricted evidence.

V1 covers recovery in Ashburn, not complete region loss. Do not treat this as a second-region DR
runbook or promise that regional-placement backups can simply be copied elsewhere later.

## Keep these procedures usable

Every workflow, approval, migration, platform-version or recovery-control change must update the
relevant runbook in the same milestone. Before production qualification, add actual workflow links,
exact inputs, expected result screens/commands, how to find the installed release and failure
diagnostics, and owner/escalation contacts in private environment records. Have a second operator
walk through them without undocumented help. Record unfinished steps as unqualified, not passed.
Add observed timing, downtime and restore evidence to the restricted operational record and update
the [live qualification manifest](real-oci-test-manifest.md). This document does not itself authorize
cloud changes or certify that the proposed operations are implemented.
