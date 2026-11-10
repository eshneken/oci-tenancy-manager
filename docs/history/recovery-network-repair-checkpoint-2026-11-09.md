# Recovery-network repair checkpoint — 9 November 2026

Local simulated source, UI and complete integration qualification pass. The main saved preview is
published; real OCI remains unqualified. [Scope, fields and manual steps](../reference/recovery-network-repair.md).

The flow previews and explicitly confirms replacement of one existing owned recovery perimeter's
networks. Exact-user MFA exemption and all policy rules stay unchanged. Before-state comes from a
fresh sealed check, not immutable setup facts; ownership/binding provenance remains independently
pinned. Conditional-write authority and its compare token are durable before possible dispatch.
Independent readback is required, and unknown effects remain held without automatic write retry.
No assignment repair, identity recreation, password access or fleet update is added.

## Final qualification

- Backend unit-only: **1,938 passed**, **10,484/10,936 lines (95.8669%)**, all 153 source modules.
- Frontend unit-only: **537 passed**, **1,934/1,990 lines (97.18%)**, all 39 source modules.
- Final complete disposable PostgreSQL/native-worker/SMTP/HTTPS-Playwright suite: **430 passed**,
  zero failures/errors/skips/timeouts. Evidence is valid; no persistent database was used, and the
  frontend was built from the current source. The 634-file source inventory matched the immutable
  qualification manifest.
- Tests cover independent externally edited network facts after refresh, unrefreshed third states,
  changed before-state/compare token, consent, exact scope, denied authority, late contexts,
  unknown writes, persisted applied capture and independent follow-up checks. Actual desktop/mobile
  UI screens and guarded dialogs passed independent UX review; security review passed.
- Static/style/documentation, generated contracts, publication/credential scanner (zero findings),
  Bandit and wheel packaging with the exact frozen 0026 migration passed. Documentation validation
  reported 152 documents and 2069 links before this final receipt/index reconciliation; the final
  documentation check passes 153 documents and 2086 links with zero errors. Dependencies
  did not change; no fresh dependency-audit claim is made for this checkpoint.

Earlier browser-selector failures and passing 427-case runs before the final backend before-state
correction are historical diagnostics, not qualification of the final source. The complete 430-case
run is authoritative; focused and earlier suites are not additive.

## Preserved main publication

Main 8443 received matching API/worker and five qualified immutable frontend assets. A private custom
PostgreSQL backup was verified with its restore listing. Complete row hashes of all 29 preexisting
public tables were preserved, with zero new tables. Migration 0026 changes existing CHECK constraints
only: the OTM application-table count remains 25, excluding separately owned queue tables.

Hashes of the private application settings, saved state, database connection notes and simulator
configuration were unchanged. No artificial drift, feed replay, organization reset, credential
operation or settings change was used to create a main-preview demonstration. Paired process,
SPA-route and authentication checks passed. Parallel 8444's database stayed unchanged; no parallel
runtime or settings edit was made.

## Qualification boundary and local review

The saved main snapshot supports the UI; the disposable-workspace desired-change/refresh/preview/
acknowledgment/repair/readback procedure is in the [manual runbook](../reference/recovery-network-repair.md#manual-local-checkpoint-runbook).
A healthy saved child does not need a repair button, and legacy/unverified captures are not silently
upgraded. Do not modify main settings or introduce fake policy drift to demonstrate the flow.

The documented Oracle conditional perimeter API surface is not live permission/sign-in qualification.
All [real OCI repair cases](../how-to/real-oci-test-manifest.md#recovery-network-repair-qualification)
remain Pending. Password custody/disclosure/four-hour rotation, 30-day API-key retirement, fleet
propagation and broader identity/assignment repairs remain subsequent work. No live OCI action or
Git commit/push is established by this local receipt; those require their own evidence.
