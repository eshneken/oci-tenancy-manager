# 21: environment email routing and release guards

4 November 2026 · User-approved requirement · Locally qualified; hosted/provider qualification remains separate

[Design hub](README.md) · [Lifecycle notices and D50](15-collection-and-operational-events.md) ·
[Independent application/configuration releases](18-database-ci-and-build-order.md#application-and-configuration-deployment-paths) ·
[Canonical test policy](../engineering-test-plan.md)

## Keep identity and outbound routing separate

Employee email remains the canonical organization identifier. Feed records, manager references,
stable person/tenancy relationships, SSO issuer/subject and login identities are not rewritten to a
test mailbox. The environment email override is an operator-owned delivery/contact policy, not an
organization transformation, employee alias, UI control or permission to impersonate another user.

Each local/staging environment uses one explicitly configured test destination for actual external
email delivery and OTM-supplied email contacts. No default employee, creator, owner, manager,
designee or administrator address is used when the required test destination is missing. Missing
test routing blocks email-capable external work rather than falling back to canonical addresses.
Read-only/non-delivering application work is not permission to send mail without this check.

Production rejects test override destinations and test-routing bypasses. It resolves the appropriate
verified real contact under the normal recipient rules. A missing responsible-admin contact remains
blocked, with no all-admin fallback. Profile/target selection must be validated against an independent
trusted expected deployment environment; a file cannot authorize its own staging/production identity.
Exact settings/CLI/API field names belong to the forthcoming runtime contract, not this decision.

| Environment | Delivery/contact requirement | Failure behavior |
| --- | --- | --- |
| Local | One explicit test destination for any externally email-capable operation; canonical identities unchanged. | Missing route cannot fall back to employee email. The local recovery administrator's original contact remains null. |
| Staging | Required explicit test destination validated before delivery/OCI credentials and deployment. | Reject missing/invalid/mismatched environment routing. No real recipient fallback. |
| Production | No test override or bypass; verified normal contacts and current entitlement. | Reject unsafe startup/release configuration; unresolved contact blocks delivery. |

## Cover OCI-generated messages as well as SMTP

Redirecting only the tool's SMTP recipient is insufficient. Before an email-capable provider call,
all OTM-controlled contact/delivery inputs must follow the same environment policy. This includes
child-creation administrator/activation contact, user invitation/contact fields, recovery contact
and equivalent provider notification targets. To/CC/BCC and any human reply/recovery contact are
subject to the same no-real-employee-fallback rule. Approved service sender/transport identity is
separately configured; do not derive it from an employee or introduce an implicit human reply path.

Account usernames and contact emails have different purposes. Preserve distinct identity keys; use
a separately qualified username/contact mapping rather than changing every engineer's identity to
the shared destination. Test multiple distinct users sharing the one override destination. If the
provider conflates username with delivery, imposes contact uniqueness or sends through a field OTM
cannot safely control, qualify that path or block it. Do not invent per-person address rewriting or
claim a field label alone proves messages cannot reach a real person.

A provider adapter must classify which inputs or existing contacts can trigger mail for each
capability. Imported tenancies may already contain real employee contacts. Inspect/verify relevant
contact behavior before an email-capable mutation; merely overriding one supplied field is not
proof that existing recovery/invitation recipients are safe. Unsupported visibility or uncontrolled
notification behavior blocks that mutation in a protected test environment. This does not authorize
sweeping or silently changing unrelated imported identities/contacts.

OTM cannot intercept arbitrary OCI spontaneous service mail, existing subscriptions or manual
Console/CLI actions outside its controlled calls. The override protects configured OTM-controlled
paths; it is not an organization-wide mail gateway. Document unsupported paths and keep them blocked
until qualified rather than claiming every Oracle-generated message is intercepted.

## Freeze intended and effective contact evidence

At acceptance, capture the canonical original contact, effective destination/contact, environment
policy version/fingerprint and relevant operation/routing context as immutable evidence. Original
contact can be null: the laptop recovery administrator has no verified mailbox. An explicit local
test route may deliver to its configured destination while preserving original=null; it must not
backfill that mailbox into employee/administrator/SSO identity. Production has no such test-route
escape and blocks an unresolved real responsible contact.

Immediately before dispatch, revalidate the trusted environment, current profile and destination
against the accepted policy fingerprint and frozen route. A changed environment policy/destination
blocks old queued work; it never silently retargets it. A corrected request requires explicit new
reviewed routing evidence where supported. Previous activation mailbox/contact evidence remains
immutable, including the effective contact already supplied to OCI. Do not recreate a child or
blindly resend to make a new override apply after an uncertain/accepted request.

Accepted/uncertain SMTP or OCI submissions retain their actual original context. A policy change or
responsibility takeover cannot recall a message, erase delivery history or justify a blind duplicate.
D47/D49/D50 reconciliation and explicit known-unsent supersession remain separate from policy drift.

Legacy raw intent and audit hashes, request digests and previously captured responsibility-proof
hashes must remain readable and unchanged. New optional routing evidence must not alter historical
canonical serialization merely by loading old data. Preserve an absent field in old payloads or use
a separate immutable route event; do not rewrite old intent or manufacture a historical route.
Parser compatibility is not authorization to send legacy email-capable work without proven current
safety. Old local non-delivering workflows retain their qualified semantics.

## Initial notification scope and subsequent parity

The first email delivery slice covers durable administrator action/known failure notices for
create/import, to the current responsible administrator only under D49/D50. It does not send mail
for viewing, ordinary progress, successful completion or every unrelated diagnostic. Responsibility
changes are not automatic all-admin mail. Canonical recipient selection and effective environment
redirection are separate facts, both retained in evidence.

This does not reintroduce security-findings/audit-user workflows, Slack, spend-based email, drift
repair or a generic notification composer. Other required future notice families retain their
accepted recipient rules; the same environment email safety policy must apply when implemented.
Real staged OCI contact behavior remains provider qualification, even when SMTP tests pass.

The [6 November lifecycle parity implementation](../reference/lifecycle-email.md#lifecycle-notice-parity--6-november-2026)
adds deletion, shared-membership, ownership and offboarding using the same existing outbox and
recipient rules. Guided handoff/takeover authority is unchanged; the broader scope concerns
notification loading only. No new storage, setting, fallback or routine-success email is added.

## Both release paths independently enforce the policy

The application and configuration deployment paths each validate the complete candidate email
policy against a trusted expected environment. Neither may rely on a previous run of the other
pipeline. A settings-only update cannot bypass the policy merely because the image digest stays
the same. A new image cannot self-select a less restrictive environment through its sample file.

| Path | Required gate before email/OCI delivery credentials or deployment |
| --- | --- |
| Application release | Validate candidate application/settings compatibility and environment policy against the trusted deployment target, then promote the reviewed immutable image/configuration together. |
| Configuration release | Validate with the currently deployed compatible application's strict settings/route schema and trusted target; preserve the existing image digest and normal deployment lock. |

The gate must be executable offline without SMTP, OCI, Vault or deployment credentials. Reject
unknown settings, invalid/contradictory profile, required missing staging destination, any production
override/bypass and a claimed environment differing from the trusted expected value. Standalone
validation and negative tests are required before hosted CI exists. This design does not install
GitHub Actions, publish repository content, obtain cloud credentials or deploy a live environment.

API and worker must load a consistent policy fingerprint. Readiness/release verification must catch
configuration drift between them before external work is enabled. Serialize changes through the
existing environment deployment lock and roll consumers; do not assume mounted-file updates or a
mixed-version rollout atomically changes all in-flight actions. Old queued routes fail closed after
a policy change; accepted/uncertain actions require their existing reconciliation.

## Required qualification matrix

- Canonical employee/manager/SSO identifiers unchanged; multiple distinct account usernames remain
  distinct while all test contact/delivery fields use the single configured destination.
- SMTP and every email-capable child/user/recovery provider input: safe local/staging redirection,
  original-null evidence, missing-destination denial and no employee fallback.
- Production startup and both independent release paths: reject override/bypass, untrusted profile
  mismatch and invalid configuration before obtaining delivery/OCI credentials or deploying.
- API/worker fingerprint mismatch, profile/destination change after acceptance, queued replay,
  legacy raw/typed responsibility hash compatibility and immutable prior activation contact.
- Imported real contacts, uncontrolled provider notifications and insufficient inspection: no
  email-capable mutation until the actual path is qualified.
- Responsible-admin-only notice selection, no fallback, durable deduplication/known-unsent handling,
  uncertain/accepted delivery retention, sanitized diagnostics and no secret/activation-link leakage.

Source field dictionaries and persistence/ER are now linked in the source checkpoint below;
actual final qualification evidence is pending. This accepted requirement is not a claim that SMTP delivery, environment guards,
CI enforcement or OCI contact qualification has already shipped.


## Source contract checkpoint — 4 November 2026

Local qualification passed; see the final validation checkpoint below. [Lifecycle email runtime](../reference/lifecycle-email.md)
now maps MailPolicy/EmailRoute/EmailContacts, ten new settings leaves, guarded provider-contact
builders, the outbox and delivery worker. [The 15-column ER](../architecture/diagrams/lifecycle-email-implemented.mmd)
adds one table (20 application tables) with immutable routing and bounded mutable delivery head.
The standalone otm-validate-release implements independent expected-environment/release-kind checks;
actual hosted CI is not installed. The original 18-key local sample remains offline by default.

[Local capture/runbook](../how-to/lifecycle-email-runbook.md) uses per-instance loopback Mailpit,
no relay configured, on an ordinary Docker bridge. It is not a network-egress firewall. SMTP
acceptance/unknown states, staged attention deduplication, legacy hash compatibility and production
secret/provider qualification remain explicit in the runtime guide. Saved upgrade and gate evidence are recorded in the final local checkpoint.


Live qualification must include multiple distinct usernames in the SAME shared tenancy/domain
with one test mailbox, checking contact uniqueness and invitation/recovery behavior. Separate
username/contact fields alone do not establish acceptance. Failure stays blocked with no employee
fallback; no extra alias feature is selected.


## Final local checkpoint — 4 November 2026

See the validation record (private historical evidence; not distributed). The 1,421-test full suite passed with no failures/errors/skips; separate backend/frontend unit coverage exceeds 95%. Reviews are complete. Both saved local instances are on 0020 with every existing row preserved, and use separate loopback capture mailboxes. Hosted CI wiring, live OCI contacts and production secret/SMTP qualification remain later work. Earlier source-checkpoint pending labels above describe the pre-qualification snapshot.


## Delivery-history visibility refinement — 5 November 2026

Source refinement, validation pending. Audit History separates Email delivery (email_delivery) from
Operations, using existing immutable delivery events and shared directory/export category mapping.
Operation-detail delivery remains available. No route/policy fingerprint, contact, outbox transition
or actual delivery behavior changes; this introduces no database column/migration or audit rewrite.
