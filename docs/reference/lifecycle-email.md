# Lifecycle email and environment contact routing

4 November 2026 · Locally qualified; saved instances upgraded without changing existing rows

[Accepted environment policy](../engineering-design/21-environment-email-policy.md) ·
[D49/D50 notice rules](../engineering-design/15-collection-and-operational-events.md) ·
[Settings](application-settings.md) · [Responsibility](responsibility.md) ·
[Implemented outbox ER](../architecture/diagrams/lifecycle-email-implemented.mmd) ·
[Local capture/runbook](../how-to/lifecycle-email-runbook.md)

The ER has matching [SVG](../architecture/diagrams/lifecycle-email-implemented.svg),
[PNG](../architecture/diagrams/lifecycle-email-implemented.png) and
[Excalidraw annotation scene](../architecture/diagrams/lifecycle-email-implemented.excalidraw) artifacts.
The scene contains the ER as one image, not separately editable table cells; edit the Mermaid
source to change schema fields and rerender.

## What this slice implements

Durable create/import administrator-action and known-failure notices go to the current responsible
administrator only. A lifecycle transaction freezes a notice and native delivery job together.
Viewing/polling, ordinary progress and successful completion do not send mail; unchanged human
attention does not manufacture another notice on every retry. Other diagnostics, security findings,
Slack, spend alerts and a generic composer are outside this slice. No owner/manager/designee/all-
admin recipient fallback is introduced.

The app records original and effective contact separately. Local/staging external delivery needs
an explicit operator test destination; canonical employee/manager email identifiers, SSO keys,
usernames and tenancy ownership stay unchanged. Production rejects any testing section/override
and blocks unresolved real responsible contact. Local recovery email remains null; explicit test
routing can supply delivery without inventing an administrator mailbox.

This is actual application SMTP delivery, initially qualified through local capture. It is not OCI
activation email: child creation, identity invitation, real recovery contacts and Vault/production
SMTP still require provider qualification. Contact builders define the required guarded seam; they
are not proof a real OCI adapter is integrated.

## Routing, previews and legacy data

MailPolicy.route preserves the original contact and can build a read-only preview even without a
local override. That preview does not authorize egress. MailPolicy.guard/guard_address reject every
local/staging externally email-capable path without the required test destination, including a
nonnull real original address. Staging requires the override even when notifications are disabled.
Production startup rejects the entire testing section, including an empty section, not just an
active override value.

New OrganizationIntent.email_contacts is a frozen EmailContacts snapshot. It is optional and omitted
when null, preserving raw historical payloads and reconstructed typed responsibility-proof hashes.
Legacy local non-delivering simulation retains compatibility; the live email-contact builders do
not infer a missing historical route. New configured contact admission and worker dispatch guard
the exact frozen routes against the current environment fingerprint; changed routing blocks old
work rather than retargeting it. There is no per-request override or recipient-edit UI.

The contact builder keeps login username distinct from primary/recovery email. identity_contacts
returns use_email_as_username=false with both contact addresses guarded. activation_address requires
the frozen activation route; validate_contacts checks applicable owner/people routes before an
email-capable phase. Arbitrary imported contacts or provider spontaneous/manual messages cannot be
intercepted. Actual OCI adapters must qualify existing-contact behavior before such mutations; no
unrelated user/contact sweep or global email-gateway guarantee is claimed.

### Labels and original activation custody

Authenticated GET /api/email-policy returns only environment, redirected and effective_test_email;
it exposes no SMTP endpoint, secret reference or credentials. The global nonproduction banner
describes NEW application delivery and explicitly preserves previous activation evidence.

Create preview/setup labels the effective route Activation / bootstrap email. Import labels it
Bootstrap contact email, without implying another activation. Both show Original contact separately.
The manual bootstrap checklist uses the recorded effective address when available and keeps the
bootstrap username distinct. Original-null/legacy rows remain explicit rather than invented. The
create activation block displays effective Activation delivery and separate Original administrator
contact; OnboardingView.administrator_email remains original. Previously recorded contacts are not
rewritten by a settings change or responsibility takeover.

Owner invitation email is a frozen provider-contact route, not an extra D50 SMTP recipient. The
local facade issues no actual owner invitation. No new OCI activation email is sent by the local
lifecycle facade. Application lifecycle notices
can nevertheless reach the configured capture service; the UI must not say that no email of any
kind is sent.

## Outbox and remote acceptance

A notice freezes the exact operation/typed-intent context, responsible subject/grant revision,
original/effective route, environment policy hash, SMTP profile hash, application origin and human
attention state. Dispatch repeats live grant/contact, responsibility, original intent, attention
state/stage, policy/destination and transport/origin checks. Known-unsent stale context can be
superseded; accepted/uncertain submission keeps its original recipient and history. No takeover or
policy edit recalls a message or proves it was unsent.

The worker commits sending/attempt identity before SMTP and rechecks before egress. Network I/O
runs outside database transactions. Exact attempt identity prevents a late/duplicate return from
rewriting another outcome. A crash/replayed sending row becomes unknown and is not automatically
resent. SMTP DATA acceptance is the boundary: sent means the server accepted the message, not that
the recipient opened it or a downstream inbox delivered it.

| Delivery state | Meaning |
| --- | --- |
| pending | Durable known-unsent intent, initially queued or waiting for a bounded rejection retry. |
| blocked | Missing/changed route, contact, authority or delivery profile prevents submission; no fallback recipient. |
| sending | Attempt identity durably committed; SMTP may be in flight. |
| sent | Known SMTP acceptance; no automatic resend or guarantee of inbox delivery. |
| failed | Bounded known-rejection attempts exhausted. |
| unknown | Possible acceptance or interrupted sending; no blind retry. |
| superseded | Known-unsent context no longer applies; old immutable intent remains. |

Known rejection/unavailability uses native delayed deferral (30 seconds) with at most three attempts.
There is no generic native automatic retry, sleep loop, UI Resend or reconciliation button. Unknown/
sent/failed/superseded heads are terminal under ordinary DML. Current SMTP envelopes are one plain-
text message, no HTML/attachments/custom headers. They include operation/stage and a guarded
application-origin operation link; activation URLs, credentials, key material and raw provider errors
are excluded. Notices with no historical/test origin keep UUID/sign-in guidance; new hosted
enabled composition requires an origin, and local composition supplies its canonical origin. No
older message is rewritten merely to add a link. Production transport needs injected secret custody; no Vault adapter is qualified.

## Complete route, notification and read-field map

Closed Python models/generated schemas remain authoritative. New source contracts are still under
validation; no old raw intent or audit row is rewritten to manufacture these fields.

| Model | Every field | Authority/bounds |
| --- | --- | --- |
| EmailRoute (5) | original_email, effective_email, environment, policy_hash, redirected | Nullable original/effective single mailbox; local/staging/production; canonical policy fingerprint; explicit redirection fact. Guarded at egress, not permission from a preview. |
| EmailContacts (3) | activation, owner, people | Frozen initiating-admin activation/bootstrap route, owner route and stable-person-UUID → route map. Contact identity never replaces canonical employee matching. |
| MailPolicy (2) | environment, email_override | Derived operator policy; local default preserves offline startup, staging requires one address, production forbids override. |
| EmailPolicyView (3) | environment, redirected, effective_test_email | Authenticated administrative context only; no connection/credential settings. |
| IdentityContactRequest (4) | username, primary_email, recovery_email, use_email_as_username | Distinct bounded login identity and guarded effective contact addresses; builder returns false for email-as-username. Actual SDK behavior remains unqualified. |
| NotificationIntent (19) | contract_version, operation_id, operation_revision, intent_event_id, intent_hash, responsible_subject, administrator_id, authorization_revision, original_recipient, delivery_recipient, route, delivery_profile_hash, application_origin, event, operation_state, stage, wait_reason, safe_code, created_at | lifecycle-email-1; immutable responsible recipient/typed original context, policy/profile and application-link origin. action_required/terminal_failure; waiting/needs_attention/failed. Nullable original contact and diagnostics; safe_code is not a raw server error. |
| Envelope (4) | notification_id, recipient, subject, body | One mailbox, subject 1–160 characters, body 1–4,096; immutable notification ID becomes Message-ID. |
| DeliveryResult (2) | state, safe_code | accepted/rejected/uncertain with closed SMTP_ACCEPTED/SMTP_REJECTED/SMTP_UNAVAILABLE/SMTP_OUTCOME_UNKNOWN codes. |
| NotificationSummary (11) | id, state, event, recipient, original_recipient, created_at, updated_at, redirected, last_attempt_at, attempts, safe_code | Safe operation-detail metadata, no message body/credentials; attempts 0–3, last-attempt time nullable. |
| NotificationEvidence (6) | contract_version, notification_id, intent_hash, state, attempts, safe_code | email-delivery-1 immutable state evidence; no copied mailbox/message payload. |

Additional existing DTO changes:

- OrganizationIntent.email_contacts defaults null and is excluded when null; canonical typed hashes
  of legacy takeover proofs retain their previous serialization. Original activation_email remains.
- PersonWorkflow.email_contacts and OnboardingView.email_contacts are nullable read projections of
  preview/frozen contact evidence. They add no SQL identity columns.
- OperationDetail.notifications defaults to an empty tuple; returns up to 100 scoped retained notice
  summaries, newest first. This display limit does not delete history or expose SMTP credentials.

## Fifteen-column outbox, one new table

Forward migration 0020_email_delivery adds otm_notification_outbox to the 19-table application, for
20 tables. It extends the audit email_delivery kind; no second task engine, SMTP state service,
per-recipient table or mutable employee directory is added.

| Column | Persisted authority |
| --- | --- |
| id | UUID notification identity, stable across attempts and Message-ID. |
| workspace_id | Verified application scope; part of parent operation FK/uniqueness. |
| operation_id | Exact same-workspace existing lifecycle operation. |
| transition_key | Canonical hash of human state/responsibility/route/profile; deduplicates unchanged attention. |
| intent | Closed immutable NotificationIntent JSON; routes/contacts cannot be edited in place. |
| intent_hash | Canonical SHA-256 of original intent JSON; validated before use. |
| state | Seven closed delivery knowledge states above. |
| attempts | Bounded 0–3 count, advanced only for a new committed sending attempt. |
| attempt_id | Nullable before first attempt; new UUID per attempt, used for exact result CAS. |
| last_attempt_at | Nullable UTC attempt time, present with an attempt identity/count. |
| next_attempt_at | Nullable UTC eligibility for known-rejection retry, not a new notice episode. |
| sent_at | Nonnull only for known sent state; not an inbox-open timestamp. |
| safe_code | Nullable fixed operational diagnostic, no raw SMTP text. |
| created_at | Immutable UTC notice acceptance time. |
| updated_at | Monotonic mutable head time; never rewrites original acceptance. |

Scoped FK and unique workspace/operation/transition retain one notice per accepted attention context.
Database guards preserve original identity/route/hash/time, enforce bounded attempts/transitions and
prevent ordinary DELETE/TRUNCATE; head updates append email_delivery audit in the same transaction.
Audit actor is the validated Email worker, not the human recipient. Privileged DB owners remain
outside ordinary immutable DML protection. Owned local organization test reset preserves outbox
with operations/audit and blocks pending/sending email; it is not a message-history cleanup command.

## Operator configuration and independent release checks

Settings add environment (default local), optional testing.email_override and notifications policy.
The packaged local sample intentionally keeps its existing 18 explicit keys/offline behavior;
notifications.enabled defaults false. See the [settings field table](application-settings.md) for
all new defaults/constraints and the [runbook](../how-to/lifecycle-email-runbook.md) for
merging an explicit local capture configuration without overwriting identity/session settings.
Staging/production samples are nonsecret examples, not deployable SMTP credentials.

Both application/configuration release paths run otm-validate-release with independently trusted
--expected-environment and --release-kind application|configuration before delivery/OCI credentials
or apply. The offline validator rejects profile mismatch, unsafe production testing, missing staging
route, hosted local_server and enabled cleartext hosted SMTP; it prints only sanitized fixed errors
or environment/release kind/settings hash/email-policy hash/redirection metadata. Configuration
release validates with the deployed compatible application; application release uses its candidate.
No GitHub workflow, hosted deployment or publishing is installed by these local scripts.

API/worker composition must use the same environment/profile. Routing is checked fresh before
external work; The local worker compares fresh notifications/local_server settings to its startup composition;
SMTP/profile/origin changes fence old queued work and require coordinated restart to activate the
reviewed transport. A file edit does not atomically update all running
consumers or recall in-flight mail. Production secret loading is injected by reference and remains
Vault/runtime qualification; passwords never belong in TOML, intents, UI or artifacts.

## Qualification status

Source/unit tests, disposable PostgreSQL/native-worker/real capture/browser, independent
security/UI/documentation reviews and preserved-data saved upgrades passed; see the final local checkpoint below. Local Mailpit capture
can prove SMTP acceptance and routing without real employee delivery; it does not prove internet
SMTP, production Vault or any OCI-generated activation/invitation/recovery behavior. No live OCI
adapter, global interception of manual/spontaneous OCI mail or production release is claimed.


### Required same-tenancy identity qualification

Before live use, create multiple distinct users in the same shared tenancy/domain using distinct
usernames and the same configured test contact. Verify actual email uniqueness, invitation and
recovery behavior. Rejection must fail closed, never fall back to employee contacts or invent aliases.
[Oracle documents separate username/email input](https://docs.oracle.com/en-us/iaas/Content/Identity/users/create-user-accounts.htm);
that does not establish duplicate-contact acceptance.


## Final local checkpoint — 4 November 2026

See the validation record (private historical evidence; not distributed). The 1,421-test full suite passed with no failures/errors/skips; separate backend/frontend unit coverage exceeds 95%. Reviews are complete. Both saved local instances are on 0020 with every existing row preserved, and use separate loopback capture mailboxes. Hosted CI wiring, live OCI contacts and production secret/SMTP qualification remain later work. Earlier source-checkpoint pending labels above describe the pre-qualification snapshot.


## Audit delivery filter — 5 November 2026

Source/UI refinement; validation pending. Existing email_delivery audit evidence has its own
Email delivery category/filter, separate from Operations in Audit History and matching CSV export.
All categories retains every authorized event. The operation-detail notification panel and retained
delivery state/history are unchanged; no new message, recipient change or retry is triggered by
filtering. Category is derived at read time, with no migration or audit rewrite.
