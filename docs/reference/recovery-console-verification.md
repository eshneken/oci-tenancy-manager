# Recovery console policy foundation

7 November 2026 · Qualified local onboarding/check UI; main preview published; live OCI and credential flows pending

[Selected design](../engineering-design/22-credential-security-lifecycles.md) ·
[Application settings](application-settings.md) · [Required-user checks](user-presence-checks.md) ·
[Final checkpoint receipt](../history/recovery-policy-ui-checkpoint-2026-11-07.md)

## Current UI checkpoint

Local create/import admissions pin the desired recovery-console fingerprint when configured. The
explicit simulator configures a recovery-only allow-inside/deny-outside pair and captures complete
producer rule/perimeter facts before temporary cleanup. Capture validation checks exact domain/user,
owned resource references, MFA action and network boundary. Startup-cached policy is insufficient:
setup/capture/cleanup recheck the current operator-owned desired fingerprint and reject stale work.
A recreated identity cannot inherit the old exact-user selectors or an old policy proof; a full
recreation/repair workflow remains later work.

**Refresh user data** now reads presence and recovery policy in one asynchronous operation, with
independent results. Provider reads run outside database transactions. A complete authorized policy
read can confirm drift while both users remain Present. Incomplete/denied/unqualified policy reads
remain Unable to verify. A changed loaded desired-policy fingerprint immediately stales old policy evidence; they do not discard
otherwise compatible presence results or apply any provider updates. Expired/future/changed-subject
proof cannot appear current. Missing desired configuration or legacy capture establishes no policy
readiness. GET/page navigation reads retained evidence only, and separate refreshes do not backfill
historical configuration.

The Recovery user card shows **Console MFA exemption**, **Approved-network restriction**, dated
policy evidence and a link to its operation. Presence has its own explicitly named timestamp/link.
Inventory links confirmed recovery-policy drift or out-of-date evidence to this same card. No CIDRs,
raw rule lists or passwords appear in these public projections. Verified in simulation describes
only the selected local fixture; it never grants password disclosure or claims live console access.

The read-only checkpoint is now followed by [perimeter-only recovery-network repair](recovery-network-repair.md),
locally qualified with preserved main-preview publication in the [final receipt](../history/recovery-network-repair-checkpoint-2026-11-09.md). Real OCI remains pending.
Refresh remains read-only. [Password custody/disclosure and original-window rotation](recovery-password-access.md)
are locally qualified in the [password receipt](../history/recovery-password-checkpoint-2026-11-09.md).
Fleet distribution, broader repairs, real Vault/provider behavior and API-key retirement remain pending.
Configuration Drift continues to describe baseline-managed root objects; recovery console controls
have their own independent Required users projection rather than being counted as root-policy drift.

## What exists

The strict loader now accepts optional `recovery_console.allowed_cidrs`. It has no default ranges.
Omission leaves unrelated local application functions available and establishes no recovery readiness.
Hosted application/configuration release validation requires an explicit valid policy. Public hosted
TOML templates intentionally omit operational networks; render a private candidate before validating
those templates as release inputs.

Validation accepts 1–64 canonicalized IPv4/IPv6 CIDRs and caps serialized input at4096 bytes. It trims,
deduplicates and sorts, rejects malformed values, missing CIDR syntax, scoped IPv6, host bits, empty
entries and `/0`. It also collapses each address family's union to reject split unrestricted ranges.
Every element must pass; validation never partially accepts or silently widens a list. Desired
fingerprints describe effective unions, so order/duplicates/redundant subsets do not imply a change.
The model representation and fixed configuration diagnostics do not expose configured networks.

## Private candidate rendering

The existing release validator has an optional `--render-recovery-console-from-env PRIVATE_OUTPUT`
argument. It consumes `OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS` as data, validates the complete target
settings, renders TOML from the validated model and exclusively creates an owner-only0600 file.
Existing files and symlinks are refused. Invalid input or mismatched target creates no candidate.
The command reports fingerprints/environment/routing facts, never CIDRs. It does not modify a deployed
file, acquire OCI credentials, rebuild an image, roll processes or propagate anything to children.

From a private operator environment, use the existing release entry point with `--config`,
`--expected-environment`, `--release-kind` and the new output argument. Supply the comma-separated
input through the protected process environment; do not put operational ranges in shell commands,
repository files, logs, screenshots or CI artifacts. The supplied installation-specific private file
remains untouched. No environment override was added to the runtime loader.

Protected GitHub Environment variables, target-image validation, release locking, reviewed candidate
fingerprint confirmation, ConfigMap rollout and per-child enforcement are still implementation work.
There is no deployed configuration-release workflow to claim complete or a new competing settings UI.
A rendered desired fingerprint does not certify any child's applied configuration.

## Provider boundary

`providers/recovery_console.py` owns closed contracts, the read-only Protocol, exact read/time wrapper
and conservative evaluator. `providers/recovery_console_simulator.py` owns an explicitly selected
fixture implementation. Neither imports OCI SDKs, performs writes or selects a fallback provider.

Provider facts must explicitly prove authorization, completeness, application assignment and rule-shape
support. Rules are supplied in fully normalized first-match order, with resolved selector membership,
actions, group and perimeter references. Unsupported predicates, duplicate IDs, partial pages or wrong
scope cannot certify a boundary. The recognizer accepts only the qualified recovery-only pair:

1. The first matching enabled rule allows exactly the bound recovery identity from the bound perimeter
   without MFA.
2. The next matching enabled rule denies exactly that identity from every source before broader rules.

Earlier broad matches, disabled/incorrect rules and expanded selectors produce drift. An MFA-only
change remains separate from a network-only change. Denied/incomplete/unsupported/wrong-scope facts
produce Unable to verify. Adapter exceptions and invalid clocks/capture windows use fixed safe errors;
reads exceeding30 seconds cannot verify policy. No password or real console login is involved.

The desired fingerprint covers only the approved CIDR union. The separate observed fingerprint covers
the complete normalized domain/application/policy, enablement/assignment, ordered rules/selectors,
MFA actions and perimeter union. Changed rule ordering or MFA cannot retain the same applied evidence
merely because the networks stayed unchanged. Safe results carry hashes/control states only, not CIDRs.
A persisted consumer must additionally bind the result to the exact target/context/capture instant and
current desired revision; this internal result alone is not a durable readiness grant.

## Remaining coherent milestone

| Internal slice | State / completion evidence required |
|---|---|
| Strict settings/private renderer and typed policy evaluator | Implemented and qualified with the complete UI checkpoint |
| Exact setup/import plus current policy observations | Implemented in explicit simulator; legacy stays unverified, replacement identities cannot inherit old proof; full recreation writer pending |
| UI/manual refresh and recovery-policy drift | Implemented alongside independent presence, with safe inventory links; complete integration and responsive visual qualification passed |
| Guarded repair and policy propagation | Perimeter-only conditional repair passes local qualification and preserved main publication; real OCI, broader repairs and fleet propagation remain pending. |
| Password custody, disclosure and scheduled four-hour rotation | Locally qualified and installed in main8443; original-attempt4h, CURRENT and unknown holds are preserved. Real OCI/Vault remains pending; dedicated Operations progress follow-up has its own receipt status. |
| Thirty-day automation-key retirement | Pending, retained in this milestone plan; creation-based age, independent signer verification, bounded drain and verified old-key removal |
| UI checkpoint qualification | Passed:402 complete integration cases, independent reviews and main-only preserved publication; live OCI qualification still pending |

The [current 9 November cadence](../engineering-test-plan.md#current-local-cadence-and-integration-budget--9-november-2026)
uses relevant targeted UI checks and reserves complete 900-second-budget integration for milestone/PR
checkpoints or justified explicit/cross-cutting validation. Both complete-source unit gates remain
required at UI checkpoints; every CI build retains all required suites. The [final checkpoint receipt](../history/recovery-policy-ui-checkpoint-2026-11-07.md) records the qualified
main8443 publication with29 preexisting tables preserved; parallel8444 remains unchanged. No hosted
configuration or OCI resources are changed.

Real rule normalization/ordering/assignment, IPv4/IPv6 egress, safe updates, password reconciliation,
Vault operations and API-key signer interoperability remain in the
[manual qualification manifest](../how-to/real-oci-test-manifest.md#credential-security-lifecycles).
Simulator tests are not live-provider qualification.

## Historical foundation-only verification receipt — 7 November 2026

This earlier library-only receipt predates the UI composition above; its unchanged-UI statements
describe that historical step only. It is not the final UI checkpoint qualification.

Backend complete-source unit gate: **1805 passed**, zero failures/errors/skips,
**9843/10222 lines (96.2923%)** across145 modules. The107 focused recovery/release/email cases are
included in that total, not additive. Frontend source is unchanged; its complete-source gate remains
**490 passed**, **1858/1911 lines (97.22%)** across38 modules. Ruff, above-declaration documentation,
design links, publication guard and credential scan pass. Independent documentation/security reviews
pass after correcting the observed-policy hash and requiring explicit supported-rule proof.

No production UI changed, so a responsive UI review is not claimed for this library-only step.
At that earlier foundation step, integration/UI qualification was pending. The current checkpoint
above now records their completion; real provider qualification remains pending.
No dependencies, schema/migrations, hosted settings, saved previews or live data were changed.


## Retained data and compatibility

No table or migration is added. Existing immutable onboarding audit evidence stores optional
`OnboardingUsers.recovery_console`: exact application/policy/perimeter/group/allow-rule/deny-rule IDs,
recovery SCIM ID and bounded normalized producer facts. Facts include private operational CIDRs and
complete ordered rule selectors/actions/enablement/MFA evidence. This is private database/backup data,
not a public DTO or diagnostic payload. Public onboarding, Operations, audit/CSV and required-user
projections continue explicit safe-field allowlists; no entire source model is serialized there.

`OrganizationIntent.recovery_console_fingerprint` records only the accepted desired union hash.
`PresenceSnapshot.recovery_console_fingerprint` similarly pins the check's current desired revision.
`PresenceCheckEvidence.recovery_console` stores a separate safe `RecoveryConsoleCheck`, including exact
read context, subject, check time and validated control result. The existing check row points to its
immutable outcome; its two presence-result entries retain their original meaning. Optional absent
fields are omitted from historical serialization so old intent/evidence hashes and replay remain valid.
The shared `RecoveryConsoleView` drives detail and inventory from the same checked evidence.
