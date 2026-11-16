# Secret inventory, naming and version cleanup

The approved V1 cleanup policy protects working and in-progress credentials, schedules obsolete
versions for deletion, and monitors version capacity. This reference distinguishes implemented pure
logic/simulator behavior from the OCI/worker/deployment integration that remains pending.

## Inventory and storage

All resources in an environment use its single existing hosting compartment. Staging/production
remain separate tenancies, Vaults and credentials. See the [Vault foundation](../how-to/vault-foundation.md).

| Credential/material | Custody and lifecycle |
| --- | --- |
| Child automation private PEM | One stable application-Vault secret per managed automation credential; new versions during the existing maximum-30-day key lifecycle |
| Child recovery password | One stable application-Vault secret per tenancy; rotate four hours after the first authorized disclosure, not on every retry |
| Bootstrap private PEM | Temporary secret per create/import operation; retain until permanent access and bootstrap removal are verified |
| Initial PostgreSQL administrator password | Database-provisioning Vault; not a runtime login |
| Runtime database and migration credentials | Application Vault, per actual login; migration/runtime authority remains separate |
| Local OTM recovery administrator TOTP seed | Protected independent secret custody; distinct from MFA-exempt child recovery users |
| SMTP password | Application secret when authenticated SMTP is configured |
| Parent/hosting API signing key | Only where static credentials are explicitly configured instead of qualified workload identity |
| SSO client secret or signing key | Conditional on the chosen federation flow; never exposed to the SPA |
| Registry credentials / TLS private key | Conditional on registry/certificate integration; selected service or protected runtime custody |
| Private worker cloud-init / installer access URL | Per-environment GitHub secret OTM_WORKER_CLOUD_INIT; not public source or an ordinary TOML setting |

OTM stores its local recovery-administrator password hash in PostgreSQL, not retrievable plaintext.
Owner/member console passwords and their MFA seeds are not OTM-managed secrets. Public PEMs, UUIDs,
secret OCIDs, fingerprints and client IDs are references/public material, not credential contents.
KMS HSM master-key versions have their own custody/rotation procedure; they are not secret versions
and must never be pruned by this cleanup policy. GitHub/OKE short-lived identity tokens avoid static
keys where qualified; OCI federation does not automatically provide Docker-registry authentication.

For 250 managed child tenancies, the normal child inventory is approximately 500 stable secrets
plus platform credentials and temporary onboarding secrets. Oracle's current paid default is
5,000 secrets per hosting tenancy/region across its Vaults, not a separate 5,000 allowance per Vault.
Check the actual tenancy limits and other usage. [OCI limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

## Stable names, exact bindings

`managed_secret_name()` generates:

| Pattern | Length with full UUID |
| --- | --- |
| otm-&lt;tenancy UUID&gt;-automation-key | 55 |
| otm-&lt;tenancy UUID&gt;-recovery-password | 58 |
| otm-&lt;operation UUID&gt;-bootstrap-key | 54 |

Use immutable OTM tenancy UUIDs for permanent credentials and the originating operation UUID for
bootstrap. Fixed suffixes and lowercase UUIDs avoid employee PII, mutable names and unsafe characters.
Generated names stay below OTM's conservative 64-character application ceiling. This is **not a
claim that OCI's service maximum is 64**: character compatibility is documented, while the exact
service length boundary still needs qualification. [OCI secret name rules](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/vault/secret/create-base64.html).
The current helper is not yet wired to the real Vault creation adapter. Exact stored secret OCID,
credential/tenancy binding and caller authorization remain authoritative; do not rediscover by name
as a fallback after a binding failure. Rotations reuse the stable secret object and create versions.

## Retention and deletion policy

The owner approved **keep the newest five versions** on 13 November 2026. This replaces the earlier
historical-retirement proof and SQL evidence-projection approach; those experimental modules/tests
have been removed. No audit-history reconstruction, retirement ledger or new cleanup table is needed.

1. Keep the newest **five unscheduled versions**, ordered by provider version number rather than
   listing order. Already scheduled versions do not count toward the five retained for normal use.
2. Always preserve CURRENT, PREVIOUS, PENDING and exact versions still involved in an unfinished
   operation, even if this temporarily retains more than five. Five is a retention target, not a
   reason to delete a protected credential. Keep normal retrieval on the established CURRENT path.
3. Skip the entire secret while rotation is unresolved/failed, execution is paused, or its current
   state is unclear. The existing per-tenancy rotation serialization must cover cleanup as well.
   Read current state directly; do not reconstruct proof from historical audit records.
4. Schedule only older, unpinned versions labeled exactly DEPRECATED. Require complete inventory,
   the exact registered secret binding and a current conditional-write revision. Unknown labels,
   missing pinned versions, missing/duplicate CURRENT, duplicate PREVIOUS or a protected version
   already scheduled for deletion hold cleanup. Never guess a provider version from a local counter.
5. Use a deletion delay of **86,700 seconds: one day plus five minutes**. Scheduling is not immediate
   purge; OCI performs irreversible deletion after the requested time. Preserve existing pending
   deletion deadlines on retry. [OCI deletion rules](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/delete-secret-version.htm).
6. Run cleanup after successful rotation and retry missed work through the daily sweep. A Kubernetes
   CronJob triggers bounded Procrastinate work; normal workers perform effects. Log the version
   numbers scheduled and any failures using existing operation/audit records. A cleanup failure does
   not reverse or misreport a successful rotation.

Oracle's paid default allows 30 versions in active use and 30 pending deletion per secret. Both pools
remain counted until inventory confirms actual purge; DEPRECATED versions are not free slots.
Monitor warning/critical counts at 20/25, and stop new-version admission if either pool reaches its
qualified limit. Alert on cleanup failures or unclear state rather than deleting protected versions.
[OCI limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

This policy covers the two permanent child secrets: automation keys and recovery passwords.
Bootstrap whole-secret disposal is separate after permanent access and temporary-account cleanup
verify. Database/TOTP/SSO/SMTP/registry and KMS key versions remain outside this routine. Historical
metadata remains indefinitely; secret contents do not. Restore follows the approved paused manual
procedure; there is no additional cleanup reconciliation journal.

## Decision contract fields

These are internal metadata contracts, not browser commands or new SQL entities.

| Contract / fields | Meaning |
| --- | --- |
| Binding: workspace_id, credential_id, secret_reference, purpose | Exact registered string workspace, credential UUID, secret reference and managed purpose; no credential content |
| Version: number, stages, deletion_at | Positive provider version number, observed labels and optional scheduled deletion time |
| Inventory: binding, revision, complete, versions | Exact target, conditional-write token and complete paginated metadata with unique version numbers |
| State: binding, protected_versions, rotation_resolved | Current trusted host state under existing rotation serialization. Unresolved rotation holds cleanup; pins are additive to the five retained versions. No retired-version evidence set |
| Policy: keep_versions | Default5; integer1-25, below active_limit. Keep this many newest unscheduled versions plus protected versions |
| Policy: deletion_delay_seconds | Default86700; integer86400-2592000, independent of key/password rotation deadlines |
| Policy: active_limit, pending_limit | Default30 each; integer3-1024 and above the configured warning/critical thresholds. Qualify actual tenancy limits |
| Policy: warning_count, critical_count | Default20/25; strictly ordered below both limits. The pure planner sends no emails |
| Plan: binding, revision, held | Exact snapshot scope/token and safety hold; an empty/held plan schedules nothing |
| Plan: active_count, pending_count, pressure | Current quota counts, null for partial inventory; pressure is unknown/ok/warning/critical, independently of a safety hold |
| Plan: can_create_version | Snapshot capacity/state eligibility, not a reservation or permission to stage a credential |
| Plan: schedule_versions, deletion_at | Eligible oldest-first numbers capped by remaining pending capacity, plus proposed schedule time |
| Run: state, scheduled_versions, pressure | complete/held/conflict/unavailable/unverified, versions independently read back as scheduled, and last pressure. complete means this batch finished, not hard deletion or fleet-wide compliance |

## Implemented now

| Component | Status |
| --- | --- |
| Metadata facade/contracts | providers/secret_versions.py; exact bindings, complete observations and conditional version scheduling |
| Keep-five planner and stable UUID names | tenancies/secret_cleanup.py; no database/provider effects |
| Metadata simulator | providers/secret_versions_simulator.py; explicit registrations, conditional writes, delayed purge and capacity checks |
| Guarded executor | tenancies/secret_cleanup_engine.py; current-state checks and safe replay under a supplied rotation scope |
| Focused tests | tests/test_secret_cleanup.py and tests/test_secret_cleanup_engine.py; retention, protected exceptions, unresolved holds, quotas, concurrency and retry/readback cases |
| Runtime integration | Pending: real OCI adapter, existing worker/reservation integration, settings binding, audit/email wiring and hosted schedule |

```sh
uv run --project backend pytest -q backend/tests/test_secret_cleanup.py backend/tests/test_secret_cleanup_engine.py
```

## Guarded execution and record compatibility

The executor uses a supplied `CleanupAuthority.serialized(binding)` scope and a small
`CleanupStateReader.snapshot()` returning current pins and resolved rotation state. Production
composition must reuse the tenancy's existing rotation reservation/serialization, honor execution
pauses and release its reservation on exit. The interface alone is not a deployed lock. Do not hold
a SQL transaction open across SDK calls or introduce another historical-proof subsystem.

Each bounded candidate gets a fresh inventory/state check and a conditional provider request,
followed by independent metadata readback. Conflicts stop the batch; ambiguous writes remain
unverified until a later retry observes their result. Replays do not reschedule pending versions or
extend deadlines. Raw provider exception text and secret contents never enter results.

Saved simulators currently use opaque operation-derived version references. They remain unchanged;
there is no migration or synthetic conversion to numeric Vault versions. The real adapter must use
OCI's exact version identities, not the local recovery table's `version_number` sequence. No new
SQL current-reference or retirement-proof projection is retained for this policy.

## Pinned development slices

| Follow-up | Required implementation / acceptance |
| --- | --- |
| OCI custody adapter | Exact registered Vault/region/secret guards, complete pagination, numeric version identity, conditional scheduling and normalized errors; qualify name length/stages/quotas/delay/purge |
| Worker/rotation integration | Reuse existing per-tenancy reservation and current unresolved-operation state; run keep-five cleanup after successful rotation; record scheduling/failures in existing audit; capacity checks before new material |
| Daily sweep/settings | application.toml retention/delay settings, bounded durable retry sweep and pressure/failure notices through existing notifications; no new daemon/table/history reconstruction |
| Hosted schedule | Daily digest-pinned Kubernetes CronJob triggers workers; qualify duplicates, missed runs, IAM, shutdown/restore pause and monitoring |
| Other secret lifecycles | Separate bootstrap whole-secret cleanup and platform-consumer procedures; never sweep arbitrary Vault contents |

All live-only cases remain Pending in the
[manual test manifest](../how-to/real-oci-test-manifest.md#secret-version-retention-and-cleanup).
No running Atlas, saved credentials, database schema or live OCI resource changes are part of this
source simplification. Complete milestone validation remains required before a PR.


## Keep-five qualification — 13 November 2026

All 95 focused planner/simulator/executor cases passed. The complete backend unit-only suite passed
2,603 tests with zero failures/errors/skips and 95.25% complete-source line coverage across 188 files.
Inline-purpose checks across 443 Python files, focused Ruff/Bandit, documentation/contracts,
publication, credential scanning and whitespace checks passed. Independent security and
code-documentation reviews passed. No frontend, database schema, saved app or live OCI effect changed.
No full application integration run was performed for this metadata-only simplification; normal full
milestone gates and future worker/PostgreSQL/live qualification remain required before those pieces
are declared complete. The superseded experimental SQL tests were removed with their unused modules;
existing credential, rotation, onboarding and database regression coverage remains in place.


## Read-only OCI retrieval source — 14 November 2026

The [Vault reader](vault-retrieval.md) now implements guarded CURRENT and exact-version text reads using OKE identity. It does not implement secret creation, version publication, cleanup writes or credential-service integration. Existing keep-five cleanup policy is unchanged.


## Caddy certificate/account custody — HTTP-01 source follow-up

[Implemented held Caddy state](../engineering-design/25-https-ingress-and-certificates.md#availability-and-persistent-state) uses a separate 50 Gi ReadWriteOnce claim and retained CSI StorageClass for certificate keys and ACME account/lock state, separately per environment. StorageClass bootstrap belongs to infrastructure authority. No DNS API credential is needed for the selected HTTP-01 path; no Vault secret type or cleanup executor is added. Native local restart/renewal tests pass; two exact official-image DoS exceptions are now owner-approved under the [continuous-update policy](caddy-security-exceptions.md), with targeted policy/native checks passing and two accepted/zero blocked findings. Live encryption, nonroot CSI ownership, placement and restricted backup/restore remain Pending; retention alone is not backup. Never log, commit or share the state across environments.
