# Operations discovery and directory alignment checkpoint

10 November 2026 · Targeted UI checkpoint qualified and installed; full-suite/PR qualification remains separate

The Operations type filter combines exact supported kind with state/literal search, resets page 1
on changes, preserves detail/back context in the authenticated cache and clears all three filters
together. Count/page use the same bound predicates; the menu's actionable badge remains workspace-wide.
Tenancies and Organization use the same vertically centered desktop toolbar and stacked mobile layout.
Unresolved signing-key rows now direct review instead of saying that no action is needed.

No migration, table, credential, provider write, operation behavior or saved-data repair is introduced.
The [reference](../reference/operations.md#operation-type-filtering--10-november-2026) maps the only new
public field, `OperationQuery.kind`, and read-only manual review steps. The
[accepted worker sizing](../engineering-design/06-platform-and-delivery.md#accepted-initial-worker-sizing--10-november-2026)
is design-only: local one slot unchanged; staging one slot and production two one-slot workers target require qualification in
the [live manifest](../how-to/real-oci-test-manifest.md#initial-multi-worker-production-qualification).
Password native queue priority documentation is corrected to actual 100; scheduling code is unchanged.

## Validation accounting

- Backend complete-source unit-only gate: **2,333 passed**,12,633/13,287 lines, **95.0779%**,174 source files;
  `backend/.local-dev/quality/unit-si9gm9jw/summary.json`.
- Frontend complete-source unit-only gate: **639 passed**,2,104/2,167 lines, **97.09%**,44 source files.
- Six targeted disposable PostgreSQL/native HTTPS/browser cases PASS at
  `.local-dev/quality/backend-postgres-e5d2oauu/summary.json`: exact kind count/page/state/search,
  foreign scope, read-only snapshots, native filtering and retained navigation.
- Following responsive fixes, a separate native HTTPS/browser run PASS at
  `.local-dev/quality/backend-postgres-1zmeduyz/summary.json`: usable search width, longest open menu,
  keyboard Escape/focus and 1280/900/390/320 layout. Earlier screen findings are fixed.
- Final additive directory-alignment native HTTPS/browser run PASS at
  `.local-dev/quality/backend-postgres-t5ywbaqj/summary.json`. Measures actual textbox/link/checkbox-label
  centers on both directories; captures 1280/900/390/320 views alongside the full filter journey.
  Earlier `zlrqiovq` measured the label-plus-input container and is not the final alignment evidence.
- Independent security, documentation and final responsive UI review PASS. Some directory captures
  contain loading rows; visual review covers controls/layout, while data behavior is covered separately
  by the native/SQL tests.
- Static contracts/build, Ruff, declared purpose comments, documentation links, publication/privacy
  and credential scans pass for the filter checkpoint. No dependency lockfile changed.

These are targeted UI-checkpoint checks, **not** a complete integration/full-suite/PR qualification.
Final publication must use paired immutable backend/assets/worker after independent reviews,
private backup/catalog validation and exact existing-row/settings preservation. No additional
persistent app, real OCI call, private employee fixture or actual restore drill is authorized here.


## Sole saved preview publication

The existing **https://localhost:8443** instance now serves matched immutable backend/assets/worker
snapshots. The established private backup/preservation procedure confirms all **33 existing public
tables preserved**, `new_tables=[]`, private application settings and connection-file contents
unchanged, and API/worker started. The backup catalog was validated; this is not an actual restore
drill. No second saved instance, new migration, employee-row repair or live OCI call occurred.

This is a local checkpoint within the current coherent milestone, not a new PR or full-suite claim.
