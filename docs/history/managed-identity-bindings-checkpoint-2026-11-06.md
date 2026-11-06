# Canonical managed identity bindings — 6 November 2026

[Complete implemented field guide](../reference/managed-object-bindings.md) ·
[Rendered ER](../architecture/diagrams/managed-identities-implemented.svg) ·
[Pending real OCI manifest](../how-to/real-oci-test-manifest.md)

Migration 0023 adds the first 18-column canonical binding subset. Fresh version 3 onboarding retains
one observed domain reference and distinct managed automation/recovery users, with exact OCI/SCIM
identities and immutable source/operation provenance. Six verified setup prerequisites are required;
presence alone cannot establish management ownership. Capture and all three rows precede temporary
cleanup in the same simulation transaction. Insert interruption rolls back the binding set and
blocks cleanup; retry and identical replay preserve exact identity semantics.

Verified termination initiation retires local management while retaining creation/source history.
Failed initiation preserves mappings. API credentials have read-only table access; workers have
insertion and three retirement columns only, with database guards protecting identity/provenance.
The reviewed local reset includes binding rows while preserving administrator, operation and audit
history. Its exact-name guard checks cover rollback and successful cleanup; the installed-role test
reuses the existing owned runtime rather than creating another environment.

| Local qualification | Result |
| --- | --- |
| Backend unit-only complete 130-source inventory | 1,445 pass; 8,727/9,085 lines, 96.0594% |
| Frontend unit-only complete 34-source inventory | 424 pass; 1,729/1,775 lines, 97.40% |
| Complete disposable PostgreSQL/native worker/HTTPS Playwright gate | 1,775 pass; zero failures, errors or skips; no timeout |
| Focused binding/onboarding/installed-role checks before final full run | Pass |
| Independently selected reset/cancellation/role checks | Three pass |
| Current schemas, purpose comments, Ruff, links and publication guard | Pass; 73 public schemas unchanged; 320 Python purpose-comment files |
| Secret/static scans and Python/npm advisory audits | Pass; zero leaks or reported known vulnerabilities |
| Independent documentation and security review | Pass, including diagram provenance/hash review and test-hygiene follow-up |

All 18 fields appear in the reference and implemented Mermaid ER. SVG/PNG were rendered and inspected;
the Excalidraw export contains an image for annotation rather than editable entity cells. Its three
visual hashes are explicitly reviewed in the publication asset manifest.

An active binding is a current identity mapping, not healthy access. It may exist while a child is
pending after cleanup failure. No assignment/context/credential heads, signing/admin/MFA readiness,
repair/disclosure permission or new Access UI is fabricated. Historical v1/v2 and already-captured v3
operations remain unbound without deliberate fresh qualification; there is no GET/startup backfill.
Configuration-object storage remains unchanged. No credential material or real OCI SDK dependency
is added, no live OCI calls are made, and every live-only qualification case remains Pending.

Saved review instances and their data remain unchanged. This is a local source checkpoint, not
hosted CI, deployment, real-provider certification or a completed Required users screen. The next
integration must connect appropriate current authority/assignment heads before composing checks.

Final migration-only formatting removed generated trailing whitespace without changing SQL tokens.
The updated frozen digest passed 22 fresh PostgreSQL binding and installed reset/role
tests; the full native/browser result above is reused for the unchanged application behavior.
