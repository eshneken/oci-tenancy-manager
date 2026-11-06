# Provider contracts and simulators

The current application explicitly composes simulated providers. This refactor changes Python file
locations only: no live OCI calls, dependencies, migrations, operation-state changes or saved-review
server updates. Existing inspection contracts and the `TenancyInspection` validation wrapper remain
unchanged.

| Contract and shared boundary types | Concrete local implementation |
| --- | --- |
| `backend/src/otm/providers/lifecycle.py` — `LifecycleFacade`, lifecycle results/errors | `lifecycle_simulator.py` — `SimulatedLifecycleFacade` |
| `backend/src/otm/providers/configuration.py` — `ConfigurationFacade`, recipe/scope helpers | `configuration_simulator.py` — `SimulatedConfigurationFacade` |
| `backend/src/otm/providers/budget.py` — `BudgetFacade`, normalized read error | `budget_simulator.py` — `SimulatedBudgetFacade` |
| `backend/src/otm/providers/baseline.py` — `BaselineQualifier`, normalized publication error | `baseline_simulator.py` — `SimulatedBaselineQualifier` |

Existing shared DTOs stay in their domain contract modules, including financial results and managed
configuration observations. Contract modules never import simulators. `local_server.py` and
`local_worker.py` choose concrete implementations explicitly; the lifecycle and budget simulators
reuse the configuration simulator's synthetic guards through simulator-only imports. There is no
registry, forwarding compatibility layer or automatic fallback.

`require_configuration_target` checks configured parent/organization scope and excludes the parent
itself. It is a shared scope check, not discovery, credential validation or proof of child membership.
The simulator additionally requires a synthetic child OCID. Existing credential bindings, exact object
identities, observation completeness checks and normalized error codes remain enforced.

`desired_objects` remains a pure recipe helper; `configure_target` remains shared orchestration
that calls injected apply/readback capabilities. Neither imports a concrete implementation. To preserve existing stored observations and hashes, the recipe still generates deterministic
`otmsim` object identities. This recipe is **not qualified for real OCI identity allocation**; a future
adapter must establish real bindings separately and must not import a simulator. No empty OCI adapter
files or OCI SDK dependency are introduced here.

Boundary regressions verify clean imports without credentials or concrete implementations and the
shared/synthetic target distinction. Existing lifecycle, publication, configuration, drift, budget,
PostgreSQL and Playwright suites continue to qualify the unchanged local behavior. The
[required coverage and merge gates](../engineering-test-plan.md#d53-required-test-and-merge-gates)
apply to both contract and simulator files. See the
[accepted file-layout decision](../engineering-design/02-operations-and-provider.md#provider-contract-and-implementation-files--5-november-2026)
and [reference index](README.md).


The [required-user presence capability](required-user-presence.md) follows the existing inspection pattern: neutral contracts, a result-validation wrapper and a separate explicit simulator. The later [manual check worker](user-presence-checks.md) selects that simulator explicitly from authenticated producer facts, with no live adapter or fallback.


`LifecycleFacade.capture_onboarding_users` now returns the shared `OnboardingUsers` readback contract;
its concrete synthetic implementation remains in `lifecycle_simulator.py`. The
[version 3 onboarding capture](tenancy-onboarding.md#permanent-user-capture--6-november-2026)
uses these facts as immutable provenance, not an access-health observation or credential binding.


Fresh onboarding capture now also creates [canonical identity mappings](managed-object-bindings.md)
through the neutral storage boundary. Simulated provider identities remain synthetic; storage does
not import a simulator, infer names or generate OCI IDs. Presence worker/UI composition still waits
for real assignment and authority heads.

## Manual presence checks — 6 November 2026 source checkpoint

The [manual check implementation](user-presence-checks.md) now connects the selected simulated
connection and exact bound automation/recovery identities to explicit authenticated Check now,
existing native operations/worker/audit and independent dated presence results. This supersedes
no-check/no-result/no-UI statements from the preceding foundation only for this presence-only path.
The [screen map](required-users-screen.md) has 22 effective display fields; Permissions remains
Not checked. Legacy unbound/unconfigured children cannot check. Simulation reconstructs authenticated
producer fixtures and does not verify live OCI. Assignments/profiles are deferred until separately
needed for privileges/repair; no credential IDs are fabricated. Daily scheduling, emails, credential
custody, readiness and repair remain outside this checkpoint. Local simulation qualification and the main-preview upgrade pass; the parallel preview is unchanged. [Final receipt](../history/manual-presence-checkpoint-2026-11-06.md).
