# Presence-only connection checkpoint — 6 November 2026

[Complete fields and implemented ER](../reference/user-presence-connections.md) ·
[Accepted simplification](../decisions/design-decisions.md#presence-only-simplification--6-november-2026) ·
[Pending live OCI cases](../how-to/real-oci-test-manifest.md)

The first read-only presence capability now uses canonical identity bindings and a single automation
connection revision. Assignment/profile tables and separate credential/context generation heads are
deferred until privilege checks and repairs. Internal message version 2 rejects their obsolete fields;
there were no public version 1 presence clients or stored presence observations to migrate.

Migration 0024 adds one 14-column simulated-connection table with scoped canonical identity and source
references. Fresh accepted v3 onboarding explicitly selects the capability; missing markers stay
excluded from historical serialization. Capture evidence, three identity mappings and the connection
commit in one savepoint before temporary cleanup. Insert interruption rolls them all back and the
normal setup retry succeeds. Existing completed captures are never materialized by reads or replay.

Canonical identity retirement precedes connection retirement in the same verified termination
transaction. Both existing deletion entry points are covered, and denied initiation preserves the
connection. API access is SELECT only; worker writes are restricted to insertion and retirement
columns. Database guards reject altered source/domain/signer facts, an unaccepted in-memory marker,
immutable updates, deletion and truncation. Reviewed owner-only local reset includes the new table.

The wheel includes the frozen SQL, migration module and matching hash manifest. All 14 fields and
relations are documented in Mermaid and the reference. No real credential, healthy access, privilege
profile, live SDK call, check worker/API/result, scheduler, repair or new UI control is introduced.
Required users still says Not checked. The next checkpoint must resolve/recheck current connection,
lifecycle, canonical bindings, provider selection and admin entitlement around read acquisition.

| Final local qualification | Result |
| --- | --- |
| Backend unit-only complete-source gate | 1,477 pass; 8,846/9,204 lines, 96.1104%; 132 source files |
| Frontend unit-only complete-source gate | 433 pass; 1,743/1,789 lines, 97.42%; 35 source files |
| Complete disposable PostgreSQL/native worker/HTTPS browser gate | 1,823 pass; zero failures, errors or skips; no timeout; 399.76 seconds |
| Focused connection/binding/identity PostgreSQL suite | 32 pass, including every guard case and exact forged-insert diagnostics |
| Purpose comments, Ruff, links and authoritative schemas | Pass; 327 Python files, 74 public schemas |
| Packaged migration inspection | Wheel SQL/version bytes and manifest hashes match source |
| Privacy, secrets, static security, Python/npm advisory audits | Pass; no leaks or reported known vulnerabilities |
| Independent documentation/security reviews | Pass, including final test-consolidation review |

The first full run exceeded the existing 420-second limit and is discarded as incomplete evidence.
The final suite reuses ten repeated onboarding setups while still checking every original negative
case in its own rolled-back transaction/savepoint with the same assertions. The limit, application
behavior, source guards and coverage thresholds were not changed. A fresh complete run above passed.

The main saved preview was privately backed up and upgraded as one API/worker/frontend release.
Every pre-existing row and column in 27 tables was preserved; only the new connection table was
added. Its 14 fields were confirmed and it contains no invented historical rows. Matching immutable
frontend assets, deep-link reload and the unauthenticated API boundary were verified. Administrator
credentials, MFA, settings and current organization were retained. The saved runbook instance is
unchanged. Backups, raw evidence and screenshots remain private local artifacts.

This is a local source/preview checkpoint, not hosted CI or real OCI qualification. UI code is
unchanged; native browser regressions pass. No new screen action needs manual testing yet. The field
guide includes an optional read-only pgAdmin query for fresh simulated setup; all live connection,
credential/signing and later presence-check qualification remains Pending in the manual manifest.
