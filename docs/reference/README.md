# Implemented application reference

These guides describe the current local application, its public fields and durable boundaries.
OCI/provider effects are simulated unless a guide explicitly records otherwise; production design
is in [the engineering chapters](../engineering-design/README.md).

- [Refresh all tenancy data: fleet scope, progress and replay limits](fleet-refresh.md) — targeted local qualification PASS; saved publication PASS.


- [Application administrator grants and revocation](administrators.md)
- [Internal operation admission](admission.md)
- [Application settings and session cleanup](application-settings.md)
- [Audit History read directory](audit-history.md)
- [Session verification and request authorization](authentication.md)
- [Baseline authoring and publication history](baseline-authoring.md)
- [Configuration drift: read-only on-demand checks](configuration-drift.md)
- [Selected configuration repair](configuration-repair.md), including
  [all-category/override qualification](configuration-repair.md#all-category-repair-qualification--6-november-2026)
- [Baseline updates for existing tenancies](configuration-updates.md)
- [Provider contracts and simulator layout](provider-layout.md)
- [Required users: identities and manual simulated presence](required-users-screen.md)
- [Required users summary in Tenancies Status](required-users-summary.md) — locally qualified, main preview updated
- [Manual presence check API, storage and authority](user-presence-checks.md)
- [Canonical managed identity bindings](managed-object-bindings.md)
- [Required-user presence boundary and responsive tenancy cards](required-user-presence.md)
- [Internal tenancy inspection](inspection.md)
- [Lifecycle email and environment contact routing](lifecycle-email.md), including [all supported lifecycle action/failure notices](lifecycle-email.md#lifecycle-notice-parity--6-november-2026)
- [Run the local application](local-application.md)
- [Local recovery authentication](local-authentication.md)
- [Read-only Operations list and detail](operations.md)
- [Organization intake and reconciliation domain](organization-domain.md)
- [Organization Mapping implementation and operator guide](organization-mapping.md), including [root manager names](organization-mapping.md#root-manager-display-name)
- [Organization directory and CSV intake](organization-screens.md)
- [Production organization snapshot storage](organization-storage.md)
- [Organization reviews and tenancy workflows](organization-workflows.md), including [fresh directory return and destructive consent](organization-workflows.md#destructive-consent-and-directory-return-correction--source-checkpoint) — qualified locally; live OCI remains pending
- [Guided onboarding responsibility takeover](responsibility.md)
- [Submit and run a simulated inspection](simulation.md)
- [Delete an individual or shared tenancy](tenancy-deletion.md)
- [Guided tenancy onboarding](tenancy-onboarding.md), including [permanent-user capture](tenancy-onboarding.md#permanent-user-capture--6-november-2026)
- [Tenancy overrides and staged baseline reviews](tenancy-overrides.md)
- [Durable simulated inspection worker](worker.md)

Python models and validators are authoritative for implemented contracts. Generated JSON schemas
remain under backend/contracts/, with TypeScript generated for the frontend. Frozen migrations
establish actual database fields; diagrams explain relationships rather than adding a second schema.

- [Current-month cost visibility and financial field dictionary](cost-visibility.md)

Audit history includes strict cost-worker identity projection and shared directory/CSV validation; see [audit reference](audit-history.md).

- [Simulated user-presence connections and full field map](user-presence-connections.md)

Normal-directory onboarding without provisioning: [Keep in organization without a tenancy](organization-workflows.md#keep-in-organization-without-a-tenancy).

Shared-tenancy [Add member](organization-workflows.md#add-a-member-from-a-shared-tenancy) and [provider refresh terminology](required-users-screen.md#consistent-provider-refresh-terminology--7-november-2026).

Compact create/import help: [Collapsed OCI operator checklist](tenancy-onboarding.md#collapsed-oci-operator-checklist).

Owner retention, verified identity removal and manual cleanup: [explicit former-owner disposition](organization-workflows.md#explicit-former-owner-disposition--7-november-2026).

Stored costs and required-user observations survive unrelated membership changes; see the retained-result
sections in [cost visibility](cost-visibility.md#retained-results-after-membership-changes--7-november-2026)
and [presence checks](user-presence-checks.md#retained-results-after-membership-changes--7-november-2026).

- [Confirmed missing required-user email: incidents, routing, fields and delivery](required-user-alerts.md)

- [Recovery console checks](recovery-console-verification.md): private settings, exact setup capture and qualified independent policy/presence UI; custody/rotation remain pending.

- [Required-user administrator assignments](administrator-assignments.md): separate exact group/role checks and persistent detail/inventory results.

- [Repair approved recovery networks](recovery-network-repair.md): exact conditional perimeter update, consent, private evidence and manual steps; local qualification/main publication pass, live OCI pending.

- [Recovery-network repair qualification](../history/recovery-network-repair-checkpoint-2026-11-09.md): final local gates and main-only preservation.

- [Recovery-password custody and original-window rotation](recovery-password-access.md) — implemented source subset; actual fields and pending live boundaries; checkpoint receipt records qualification/install status.

Current source [Operations check-section mapping](operations.md#recorded-required-user-check-sections--source-follow-up) and [access mini-panel](required-users-screen.md#access-mini-panel-and-exact-check-destinations--source-follow-up) have separately recorded combined follow-up validation and preserved main installation.

- [Recovery-password Operations progress](operations.md#recovery-password-operation-progress): immutable original-window projection and safe status panel; installed with separately recorded full-run and final-copy targeted evidence.

- [Operation return URL field map](operations.md#context-sensitive-return-navigation--source-follow-up): closed frontend-only returnTo routes; targeted navigation checks and preserved main installation pass; no full native rerun.

- [Automation signing-key inventory and observed age](automation-signing-keys.md): exact public metadata, legacy omission and current/historical age basis; targeted local checkpoint qualified and installed; live enforcement pending.

- [Managed signing-key rotation](signing-key-rotation.md): all 17 candidate head columns and existing JSON/outbox fields; targeted local qualification/saved installation PASS; full-suite/PR/live Pending.

- [Signing rotation targeted qualification/install status](../history/signing-key-rotation-checkpoint-2026-11-10.md): targeted local qualification and preserved installation PASS; full-suite/PR/live remain separate.

Operations now supports [type/state/search filtering](operations.md#operation-type-filtering--10-november-2026) without changing workspace-wide action counts.

- [Create/import public bootstrap key and candidate-password refinement](tenancy-onboarding.md#public-bootstrap-handoff--12-november-2026) — current bundle targeted qualification PASS; saved publication PASS.
