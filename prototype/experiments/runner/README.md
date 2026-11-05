# Native runner qualification

This is an isolated compatibility experiment for the accepted Procrastinate direction. It is
separate from both the organization demo and the production backend. Production dependencies,
application models, database migrations and HTTP routes are unchanged by this experiment.

Candidate versions are locked here: **Procrastinate 3.10.0, SQLAlchemy 2.0.54 and psycopg 3.3.6**.
The SQLAlchemy 2.0 family matches the already tested organization stack. No custom connector,
replacement queue, hand-invoked runner stored procedure or psycopg2 integration is introduced.

## Run safely

Requires Python 3.12, Docker and a POSIX host (macOS/Linux). From the repository root:

```sh
uv sync --project prototype/experiments/runner --locked
uv run --project prototype/experiments/runner python prototype/experiments/runner/scripts/run_qualification.py
```

On this Mac, add `<private-local-path>` to PATH if needed. The driver creates a fresh pinned
PostgreSQL 16 container with a random password and loopback port, runs the complete tests, then
removes only its owned container. It does not read the saved lab connection or use OCI.
Missing/invalid/empty test evidence, a skipped test, timeout or test failure fails qualification.
Running database tests directly without the explicit guarded test URL fails rather than skips.

The driver removes inherited libpq target overrides. Connection guards require psycopg 3, the
qualification database/user, nonempty credentials, explicit loopback port and no URL query options;
`hostaddr` is explicit too. A database user/URL match is a guard, not proof of ownership outside this
driver: using the disposable driver is the supported way to run these tests. Nine negative tests
prove rejection before engine construction and no fallback to the saved database.

Pytest runs in its own session/process group. Timeout and error cleanup stop that group, including
ordinary inherited worker descendants; the leader is reaped and stopped orphan descendants are
reaped by the OS. Three no-database sentinel tests verify timeout, early failure and normal completion.
The Docker finally block still executes if report redaction fails. Retained logs and JUnit have the
run's generated credential redacted. Reports stay under ignored `.local-dev/quality/runner-qualification-*`.

## Final result

**29 cases passed:** 12 transaction/acceptance, five native-worker lifecycle, nine target guards
and three no-database process-cleanup cases. No failures, errors, skips or timeout. The final
qualification report is retained under ignored local evidence; the design checkpoint links a
sanitized receipt. This count is separate from production's 62 unit tests.

## What the experiment proves

The synchronous acceptance task uses the native `SyncPsycopgConnector` and
`task.configure(connection=connection.connection.driver_connection).defer(...)` inside
`SQLAlchemy Engine.begin()`. SQLAlchemy owns commit/rollback. Workers use the native async
`PsycopgConnector`; their task bodies can still run synchronous Python/SQLAlchemy code.

The [supported external-connection hook](https://procrastinate.readthedocs.io/en/stable/howto/production/external_connection.html)
permits this ownership model. Tests establish it for the pinned candidate, rather than assuming
that the older psycopg2 SQLAlchemy example applies to psycopg 3.

| Evidence | Required observation |
|---|---|
| One application transaction | Toy operation, audit and native job have identical PostgreSQL row transaction IDs; job payload contains only operation ID |
| Independent visibility | Another connection sees none before commit; a real worker cannot process the uncommitted job |
| Autocommit guard | Reject a misconfigured AUTOCOMMIT connection before the first application write |
| Commit and rollback | After commit all three appear; caller exception, real queue insert constraint error and deferred constraint failure at COMMIT leave none |
| Lost response | Resubmitting the scoped request key returns the original committed operation without a new audit/job |
| Concurrent reuse | Two physical transactions start before competing inserts; same intent has one winner/reference, conflicting intent rejects one submission |
| Request scope | Same key in another actor/workspace is independent; this is a uniqueness test, not authentication |
| Caller process loss | SIGKILL at explicitly signaled boundaries before/after commit leaves all-or-none records; resubmission recovers correctly |
| Known safe retry | Native configured retry handles a deliberately injected no-effect failure |
| Lock/duplicate delivery | Competing native workers respect the same operation lock; the toy SQL effect is recorded once |
| Graceful shutdown | A native long-lived worker receiving SIGTERM waits for its current task to finish |
| Abrupt worker loss | Job remains doing/stalled; a fresh worker alone does not retry it. Native heartbeat-aware discovery plus explicit retry resumes it |
| Effect committed before acknowledgment | A crash in that exact toy SQL window is recovered without repeating the local SQL effect |

The first expanded run used drain mode incorrectly for retry/lock/shutdown tests. In native
`wait=False` mode the worker stops polling when no job is immediately claimable, even if an active
job will later unlock work or request retry. These cases now use `wait=True` and explicit completion/
shutdown checks. Drain mode is retained only where an empty-queue exit is the expected observation.
Assertions were retained; the corrected setup models the accepted long-lived production workers.

The [stalled-job documentation](https://procrastinate.readthedocs.io/en/stable/howto/production/retry_stalled_jobs.html)
requires explicit recovery; worker restart is not enough. The experiment uses short heartbeat timers
only to make tests bounded. They are not production timeout/retry policy. Production stalled recovery
must inspect current operation ownership and reconcile uncertain OCI effects before selecting a retry;
there is no approved blanket retry-all task here.

## Deliberate limits

The `qualification.operation`, `qualification.audit` and `qualification.effect` tables are **toy
fixtures**, not production entities or proposed additions to the ER. The toy audit lacks production
immutability/role controls. Test digest strings only exercise request uniqueness/conflict handling;
production must compute the canonical fingerprint from validated immutable intent and store its
complete evidence. Actor labels are synthetic and provide no SSO or authorization.

The toy effect is local SQL, guarded by row locking and a unique key. It does not prove exactly-once
OCI effects, real provider reconciliation, worker ownership fencing or per-tenancy mutation ordering.
No OCI write, credential rotation, notification or real inspection adapter is executed. The current
production inspection simulator remains independent and is not wired into these toy jobs.

This qualifies candidate mechanics against disposable Docker PostgreSQL 16 with a database owner.
Managed OCI PostgreSQL privileges, migration ownership, runtime grants, pool/load tuning, OKE
shutdown/recovery scheduling, production operation/step models and actual API integration remain
subsequent implementation/pilot work. No production pin or migration is adopted by a passing experiment.
The useful scenarios and native connection pattern will accompany the production implementation.
