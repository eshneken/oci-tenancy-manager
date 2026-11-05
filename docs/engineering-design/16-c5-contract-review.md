# 16: financial and email contract review

25 October 2026 | C5 technical review checkpoint | Design examples only; live qualification pending

[Design hub](README.md) · [Collection and notification behavior](15-collection-and-operational-events.md) ·
[Production model](11-production-data-model.md) · [Platform handoff](06-platform-and-delivery.md)

## Purpose and authority

The approved Tenancies dashboard and D41–D50 decisions remain unchanged. This chapter makes the
behind-screen contracts reviewable with closed message shapes, same-response field checks and
explicit counterexamples. It does not implement collection, transactions, authorization, email or
OCI access. There are no new application tables, relational columns, migrations or runtime dependencies.

The handwritten schema is a **design artifact**, consistent with C2. Under D11, the future Python
application models own generated OpenAPI/CLI types; these examples become acceptance inputs to those
models. Do not maintain a second handwritten production schema alongside Pydantic.

| Artifact | Use |
|---|---|
| [Closed JSON Schema](../contracts/c5-collection-delivery.schema.json) | Budget request/result, coherent snapshot, guarded selection, captured email intent/result and responsibility-routing cases |
| [Synthetic examples](../contracts/c5-collection-delivery-examples.json) | Independent expected outcomes plus shape-valid semantic and shape-invalid negative controls |
| [Reference checker](../../scripts/check_c5_contracts.py) | Reproducible, pure design predicates; no application runtime imports |
| Validation receipt (private historical evidence; not distributed) | Counts, exact artifact hashes and explicit limits |
| [Provider field inventory](../contracts/oci-provider-call-inventory.json) | Pinned SDK 2.188.0 field/source inspection, including Budget; not a service qualification or application dependency pin |

Reproduce from the repository root:

```bash
uv run --no-project scripts/check_c5_contracts.py --receipt docs/design-evidence/c5-contract-checks-2026-10-28.json
uv run python scripts/check_design_docs.py
uv run python scripts/check_inline_docs.py
```

The script declares `jsonschema==4.25.1` in PEP 723 metadata. `--no-project` isolates that tool dependency
from the application's `prototype/pyproject.toml` and `prototype/uv.lock`. Schema references resolve from two explicitly
registered local files, including the existing C2 Context definition; the checker does not fetch
remote schemas. It is not a live simulator, provider mock implementation or substitute for database tests.

## One child, one response, one snapshot

The request captures workspace, registered child, operation/attempt generations, access-context
identity/generation, exact budget binding/OCID, desired configuration generation, source-policy
revision, scope hash and expected cycle/timezone. Its payload contains only `budget_id`; callers
cannot supply an endpoint, arbitrary SDK kwargs, credential material or a replacement target.

The observed response echoes the exact request receipt and captures child-root owner/targets, budget
OCID, monthly-processing facts, money fields, computation time, retrieval time and safe provider
correlation. Each published budget/actual/forecast/computation field must equal its counterpart from
that same response. No previous forecast or desired override value may be substituted. Forecast
means the complete cycle-end estimate, never actual plus forecast. Valid zero and negative spend
adjustments remain values. Null forecast does not prevent independently qualified actual display.

Unobservable reads have no snapshot. An ambiguous access-denied/not-found result is not proof of
Missing. Timeout/authorization failure is acquisition failure; unsupported normalization is data
unqualified. Optional absent forecast or old calculations do not become D48 acquisition-failure emails.

### Money, currency and presentation

The normalized wire examples use nullable canonical decimal strings with exactly four fractional
places, within `numeric(20,4)`. JSON numbers, non-finite strings, scientific notation, excess scale
and overflow are rejected. Budgets are nonnegative; actual/forecast allow signed adjustments.
This deliberately bounds the normalized contract; it **does not prove** SDK floats preserve transport
precision. The real adapter must qualify conversion using recorded transport/source evidence. Until
that policy is qualified, excess or uncertain precision fails closed rather than silently rounding.

Budget has no currency property. Currency, minor units and provenance come from the trusted,
versioned qualified rate-card profile; null qualification never defaults to USD. Example USD/JPY/KWD
profiles are synthetic tests, not approval of a billing currency for the organization.

Use exact Decimal comparisons before presentation. Normally show the qualified currency's minor
units. If ordinary display rounding would hide a difference against the budget, this reference
contract expands that row's monetary precision to four places. For example, 100.0001 over 100.0000
must not look like two identical 100.00 values with an unexplained overrun. This is an engineering
presentation rule to carry into the generated client, not a redesign of the approved dashboard.
JavaScript Number conversion must not silently lose the contract's decimal precision. Equal values
remain neutral; actual above budget is red and forecast above budget independently amber.

### Monthly scope and freshness

The exact response supplies a sanitized `cycle_facts` block: `reset_period`,
`processing_period_type`, `budget_processing_period_start_offset`, `start_date`, `end_date`.
These are real fields in the pinned [Oracle Budget model source](https://github.com/oracle/oci-python-sdk/blob/df5a803743d2560ec37ef5d1e437d5978ef7d33a/src/oci/budget/models/budget.py).
`start_date`/`end_date` are one-time-budget facts, **not** returned monthly spend-cycle boundaries.
No fictional provider period or currency field is introduced. The normalized names/grouping are
adapter-owned safe projections, not a raw SDK serialization.

The bounded reference profile covers MONTHLY reset, MONTH processing, day 1 offset, no one-time dates,
and UTC. It checks the observed facts against trusted qualified profile/evidence, then derives the
calendar-month interval from the provider computation timestamp. Copying requested expected bounds
is insufficient. Changed offset, INVOICE, SINGLE_USE, unknown reset or absent qualification cannot
produce usable current-cycle amounts under this profile. Such facts may remain explicitly unverified.
Different calendar/offset/invoice profiles require their own reviewed derivation and pilot evidence;
this fixture does not mandate a fleet-wide UTC/default processing setting or certify OCI reset behavior.

Prior-cycle evidence remains prior, including after a recent read. Missing computation time remains
unknown. Source and retrieval age are independent. The example freshness deadline is the earlier
of computation plus source-age limit and retrieval plus retrieval-age limit. The illustrated 12h/24h
limits are **test inputs**, not accepted production SLAs or claims about OCI recomputation cadence.
Only OTM retrieval time appears in the approved list tooltip; internal computation facts remain.

## Guarded selection and retained values

Before selecting any observation, match current workspace/child, execution/intent fences, authorized
source context/generation, budget binding/generation, configuration generation, policy, scope and
cycle/timezone. Obsolete work remains evidence and cannot update the selected current value.

Prior observations must match the requested workspace and child even when the new read failed.
Retaining or ordering prior values additionally requires the same access context/generation, binding,
source policy, scope, provider target, expected cycle and timezone. A failed read with only incompatible
prior evidence is unavailable, not a current retained value. A newer calculation from an obsolete
context cannot block the first valid current-context read. Ordinary signer-version rotation within
one context does not invent a new source domain.

Within a compatible domain, a late older computation cannot replace a newer one; equal computation
times prefer later retrieval. A coherent newer partial snapshot never borrows an old forecast. The
same collection with identical facts is a no-op; conflicting facts for one collection are rejected.
These are selection predicates, **not proof of database concurrency**. The implementation must apply
them under C2 recovery/generation fences and real constraints/transactions, with race/crash tests.
Retained facts keep their original age and latest acquisition-failure condition.

## Captured email intent and responsible administrator

D47 limits V1 dispatch to email. D48 cost-read failure notices occur once per scoped episode after
bounded retry exhaustion. D49 lifecycle notices are for administrator action or known terminal
failure only. D50 routes lifecycle notices **only to the currently responsible administrator**,
initially the initiator, with explicit audited takeover. No all-admin fallback or owner copies.
Other required notice families preserve their existing recipient rules.

An immutable intent captures source event, notice/episode, operation/responsibility revision,
recipients, template/safe payload and delivery context. Before actual dispatch, recheck live
responsibility and entitlement. Changed/unavailable responsibility blocks a known-unsent stale intent;
viewing an operation is not takeover. An explicit correction creates new source/notification IDs and
submission key, linked through `supersedes_notification_id`; it never edits old recipients.

Delivery context retains policy, service/account namespace, sender, adapter contract, credential
reference/version and submission key. Authorized credential rotation may change the credential
version for a new attempt within the same original context. The trusted attempt context is an input
to these examples, not evidence that the checker authorized a real credential.

Per-recipient outcomes must partition the captured recipient list exactly once. Accepted is distinct
from delivered; provider acceptance cannot set `delivered_at`. Confirmed delivery needs supporting
correlation. Rejected, partial and unknown outcomes remain explicit. An uncertain submission stays
in the original provider namespace for reconciliation; takeover/current policy cannot bypass that
uncertainty or cause a blind duplicate send. Already accepted mail cannot be recalled by reassignment.
The checker does not simulate SMTP, prove inbox delivery or validate a live provider's idempotency.

## Field-to-model map

| Contract field or structure | Canonical proposed storage / authority |
|---|---|
| `Source`, closed request and expected cycle | `otm_financial_collection` source/context/binding/configuration fields and versioned `request_parameters` |
| C2 `context`, attempt/signer generation | Existing `otm_operation`, `otm_operation_step` and immutable `audit_event.data` attempt envelope |
| Provider root owner/targets and budget OCID | `otm_financial_observation` existing observed scope/binding fields; copied from exact acquisition |
| Same-response budget, actual, forecast and timestamps | Existing `otm_financial_observation` amount/time/availability fields, unique collection |
| `cycle_facts`, `observed_cycle_facts`, qualification evidence | Typed `period_evidence` JSON: response processing/reset facts, profile/evidence reference and derivation; not five new relational columns |
| `period_evidence_event_id` | Projection of the existing `period_evidence` evidence reference; no extra UUID column |
| `currency_minor_units`, `qualified_cycle_facts`, age limits | Resolved versioned runtime/source profile; minor units are a projection, not another observed currency or new DB column |
| `currency_policy_revision`, `currency_evidence_event_id` | Existing observation currency provenance plus qualified source-policy authority |
| `live_source`, `previous`, `as_of` | Trusted reference-test inputs; live collection/binding/runtime joins, previous immutable observation and server time in production; not client authorization assertions |
| `EmailIntent` routing/responsibility, `channel` | Existing `notification_outbox` fields plus immutable `audit_event.data` trigger/routing evidence |
| `delivery_context`, `authorized_attempt_context` | Captured nonsecret event/attempt evidence, plus trusted authorized runtime resolution; original provider namespace retained |
| `supersedes_notification_id` | Typed existing audit/outbox source-event evidence linking old and replacement intents; no mutable rewrite or new column |
| Recipient partition / delivery outcomes | Existing outbox outcome/times/provider reference projection plus append-only attempt evidence |
| D48 episode and D49 attention identity | Existing C2 operation/step plus typed audit source-event contracts and command/outbox uniqueness, as detailed in chapter15 |

The proposed application inventory remains **28 tables: 10 existing plus 18 additions**. Typed JSON
payloads still need production model validation/versioning and any queried expressions/indexes at C6.
No ER column is added merely to store a transient test fixture or a derived presentation value.

## Review result and remaining gates

The recorded receipt covers 49 positive examples and 43 rejection controls. Independent documentation
review found and helped close three gaps: failed-read prior scope, obsolete-context ordering/retention,
and same-response monthly-processing verification. The reviewer found no further material issue in
that bounded re-review. This is not a blanket application/security certification.

| Area | Evidence now | Required later evidence |
|---|---|---|
| Closed shapes / targeted semantics | Executed schema/examples/reference predicates | Production Python model parity, generated-client compatibility, invalid API inputs |
| Publication and one initial notice | Reference scope/order/identity cases | Real PostgreSQL uniqueness, locks, competing worker/restore, crash-before/after-commit and runner qualification |
| Budget acquisition | Pinned provider field review, coherent synthetic observations | Real child permissions, endpoint, root scope, no-alert-budget calculations, precision, rate-card currency, reset/cycle and native forecast behavior |
| Email routing and outcomes | Frozen audience/context, partition and correction controls | Organization-approved sender/service, current SSO entitlement, partial/timeout/bounce correlation and restore reconciliation |
| Approved screens | Existing D45 browser evidence and D46 approval retained | Production frontend/API queries, independent sorts, responsiveness and decimal display parity |

C5's technical contract pack is ready for handoff review. Live dependencies remain explicit gates;
C1–C4 are not retroactively marked complete. C6 now turns the package into deployment/recovery
contracts, physical migration/index/privilege plans, CI gates and dependency-ordered work packages.


The bounded [public static-contract receipt](../contracts/receipts/c5-contract-checks-2026-10-28.json)
is retained for reproducible validation. Other dated raw evidence remains private and is not a
required checkout artifact; static contracts do not qualify live OCI or SMTP behavior.
