# Implemented application reference

These guides describe the current local application, its public fields and durable boundaries.
OCI/provider effects are simulated unless a guide explicitly records otherwise; production design
is in [the engineering chapters](../engineering-design/README.md).

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
- [Required-user presence boundary: internal foundation](required-user-presence.md)
- [Internal tenancy inspection](inspection.md)
- [Lifecycle email and environment contact routing](lifecycle-email.md)
- [Run the local application](local-application.md)
- [Local recovery authentication](local-authentication.md)
- [Read-only Operations list and detail](operations.md)
- [Organization intake and reconciliation domain](organization-domain.md)
- [Organization Mapping implementation and operator guide](organization-mapping.md), including [root manager names](organization-mapping.md#root-manager-display-name)
- [Organization directory and CSV intake](organization-screens.md)
- [Production organization snapshot storage](organization-storage.md)
- [Organization reviews and tenancy workflows](organization-workflows.md)
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
