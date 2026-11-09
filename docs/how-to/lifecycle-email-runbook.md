# Local review: lifecycle email and environment routing

4 November 2026 · Locally qualified and installed in the saved review instances

[Runtime field guide](../reference/lifecycle-email.md) ·
[Environment decision](../engineering-design/21-environment-email-policy.md) ·
[Private local application](../reference/local-application.md)

## Scope and installation choice

Use local SMTP capture, never an employee mailbox, for this review. The test destination is
capture@otm.test. Current saved application/lab data, credentials, baseline pins and history must be
preserved. A port does not establish ownership; confirm the intended installation's directory and
nonsecret instance ID before starting/reusing a capture container. This runbook does not authorize
reset, account creation, real OCI actions, internet email or repository publication.

Mailpit is a local capture service, not an OCI activation emulator or production SMTP qualification.
The digest-pinned Compose file publishes SMTP/UI on 127.0.0.1 only and configures no SMTP relay. It
uses an ordinary Docker bridge so published ports work; it is not a network-egress firewall. Do not
add forwarding/relay settings or expose its UI on another interface. Captures are ephemeral and
bounded; do not copy private messages or live employee information into repository evidence.

## 1. Start a capture instance deliberately

From the project root, replace the installation-ID placeholder with the intended installation's
nonsecret UUID. Do not print the private state file to obtain it or paste credentials into chat.
Choose noncolliding ports and a distinct Compose project for each installation. Main uses SMTP
1025/UI 8025; the separate test instance uses SMTP 1026/UI 8026.

```sh
export OTM_MAIL_INSTANCE="REPLACE_WITH_OWNED_INSTALLATION_UUID"
export OTM_MAIL_SMTP_PORT="1025"
export OTM_MAIL_UI_PORT="8025"
docker compose --project-name "otm-mail-${OTM_MAIL_INSTANCE}" --file backend/dev/mailpit.compose.yaml up --detach
```

For the test installation, select its own UUID and change both ports to 1026/8026. Open only the
matching loopback capture UI, normally http://127.0.0.1:8025 or http://127.0.0.1:8026. Do not reuse
another installation's capture just because its port responds. The fixed image, owner label,
nonroot user, read-only filesystem, dropped capabilities and resource bounds come from the reviewed
Compose file; this command does not configure an outbound relay.

## 2. Review and merge private nonsecret settings

The packaged default application.toml deliberately leaves notifications disabled through defaults.
Merge the following values into the selected installation's private application.toml; do not
replace its sessions/local_auth/workspace/issuer/branding sections with this fragment. Root-level
environment belongs before table headers. Use the matching SMTP port for the intended instance.

```toml
environment = "local"

[testing]
email_override = "capture@otm.test"

[notifications]
enabled = true
smtp_host = "127.0.0.1"
smtp_port = 1025
sender_email = "no-reply@otm.test"
tls_mode = "local"
```

No username/password reference is needed for this local capture. The existing local_server
public_origin supplies the operation-link origin; an explicit conflicting application_origin is
invalid. Hosted SMTP is different: enable only after TLS, application origin and injected secret
custody are qualified. Never put a password in TOML or switch staging/production to local TLS mode.

Validate and restart the API and its separately running worker through the approved installation
procedure, preserving the stable qualified frontend snapshot. A settings-file edit alone does not
atomically recompose running transports. Current worker routing/connection changes must fail closed
until the reviewed API/worker profiles are restarted consistently. Do not run a default-directory
setup/reset to make the settings take effect.

## 3. Review contact evidence before accepting work

Sign in normally. The global nonproduction banner says NEW application delivery uses the configured
test destination while stored identities and prior activation contacts remain unchanged. Employee
name/email/manager/SSO keys must remain canonical. For create, review Activation / bootstrap email;
for import, review Bootstrap contact email without implying a second activation. The owner contact
is separate. Effective contacts all use capture@otm.test, while Original contact remains real or
Not configured for the email-less local recovery administrator.

The manual bootstrap instructions must use the recorded effective contact and a distinct username.
Do not actually create a user or change a real imported tenancy during this local review. Legacy
email_contacts=null views keep their old contact evidence; the current banner does not rewrite them.
A route preview without an override is not permission to send: missing local test routing must block
email-capable acceptance rather than deliver to an original employee address.

## 4. Observe a durable lifecycle notice

Use synthetic permitted create/import work in an isolated review installation. Deletion,
shared-membership, ownership transfer and offboarding use the same delivery panel when their
execution requires review or fails. Routine success remains silent. Only durable
administrator-action/known-failure states produce lifecycle notices, to the current responsible
administrator; ordinary view/poll/progress/success must not send. Do not invent a second saved admin
to test takeover. Multi-admin/creator-revocation scenarios belong to prepared disposable fixtures.

The API acceptance/worker lifecycle transaction stages one frozen outbox intent and a UUID-only
native delivery job. The separate worker sends outside database transactions. Open the operation's
notification list and the matching capture UI. Compare frozen original/effective recipient, test
redirection, attempt count/time, state and sanitized diagnostic. Mail includes a guarded application
link to that operation, not an activation URL, password, private key or raw provider error.

Sent means SMTP accepted the message; it does not prove inbox delivery or that an administrator
read it. Reopening/polling the same attention state should retain one notice. Application lifecycle
mail in capture does not imply the local facade sent an OCI activation/invitation email.

## 5. Recovery and negative scenarios use disposable fixtures

Do not edit saved outbox or operation records. The automated synthetic PostgreSQL/native-worker/
SMTP/browser fixtures cover these conditions:

- Known pre-submission rejection/unavailability retries at 30 seconds up to three attempts; no
  generic native automatic retry. Attempts/evidence/job deferral commit atomically.
- Possible DATA acceptance, transport-contract exception, crash/replayed sending or late return
  becomes Unknown; no blind resend or UI Resend shortcut. Preserve original recipients/context.
- Policy/destination, SMTP profile/origin, responsible subject/grant/contact or lifecycle context
  changes before egress block/supersede known-unsent work. No silent retargeting or duplicate
  accepted/uncertain submission; replacing responsibility is not message recall.
- Local missing override with a nonnull real original, production testing/override, missing staging
  override, header injection and unresolved production contact deny delivery with no fallback.
- Two distinct user identities keep distinct usernames/canonical emails while sharing the one test
  contact. Legacy raw intent/request and typed responsibility hashes remain unchanged.
- Wrong workspace/foreign notice, malformed hashes, terminal/immutable-intent update and delete/
  truncate attempts fail. Owned test organization reset preserves outbox/operation/audit and refuses
  pending/sending email; it is not a cleanup command for notification history.

## 6. Exercise both offline release paths

The tracked hosted templates intentionally omit operational recovery-console networks. Validating
those templates directly is expected to return RELEASE_SETTINGS_REJECTED. First supply the approved
comma-separated CIDRs through the protected operator environment variable
`OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS`, then render private candidates as described in the
[recovery-console guide](../reference/recovery-console-verification.md#private-candidate-rendering).
Never put actual ranges in commands, repository files, logs or CI artifacts.

These offline commands require no OCI/Vault/SMTP credentials and perform no deployment. Use unused
output filenames: the renderer exclusively creates owner-only files and refuses existing paths.
The expected environment comes from the trusted deployment target, not the candidate itself.

```sh
umask 077
mkdir -p .local-dev/release-candidates
uv run --project backend otm-validate-release --config backend/config/staging.application.toml --expected-environment staging --release-kind configuration --render-recovery-console-from-env .local-dev/release-candidates/staging.application.toml
uv run --project backend otm-validate-release --config backend/config/production.application.toml --expected-environment production --release-kind configuration --render-recovery-console-from-env .local-dev/release-candidates/production.application.toml
uv run --project backend otm-validate-release --config .local-dev/release-candidates/staging.application.toml --expected-environment staging --release-kind application
uv run --project backend otm-validate-release --config .local-dev/release-candidates/staging.application.toml --expected-environment staging --release-kind configuration
uv run --project backend otm-validate-release --config .local-dev/release-candidates/production.application.toml --expected-environment production --release-kind application
uv run --project backend otm-validate-release --config .local-dev/release-candidates/production.application.toml --expected-environment production --release-kind configuration
```

Examples intentionally keep hosted notifications disabled and contain synthetic placeholders; a
passing parse is not deployable credentials or proof that an SMTP endpoint exists. Negative tests
use temporary copies to reject expected-environment mismatch, any production testing section,
missing staging override, hosted local_server, enabled hosted local TLS and missing hosted
application origin. Do not temporarily weaken a live production file to run a negative probe.

The application and configuration deployment paths must each run this gate before delivery/OCI
credentials or apply, with their proper candidate/deployed-compatible schema and normal environment
lock. Hosted checkpoint CI is established. OCI application/configuration delivery pipelines remain
implementation work; this runbook does not install or qualify a hosted deployment.

## Remaining qualification

Capture proves local SMTP knowledge/routing only. Production injected secret loading is not a
qualified Vault adapter. Before any live pilot, test multiple distinct usernames in the SAME shared
tenancy/domain with this one test mailbox and verify contact uniqueness/invitation/recovery. A
domain rejection must remain blocked, never fall back to employee email or invent an alias. No real OCI activation/invitation/recovery or imported-contact behavior is
qualified; arbitrary spontaneous/manual OCI messages remain outside interception. Record final
source-unit/PostgreSQL/native-worker/capture/browser, independent reviews and preserved-data saved
upgrades are recorded in the final local checkpoint below. This is a local installation, not a live OCI qualification.


## Final local checkpoint — 4 November 2026

See the validation record (private historical evidence; not distributed). The 1,421-test full suite passed with no failures/errors/skips; separate backend/frontend unit coverage exceeds 95%. Reviews are complete. Both saved local instances are on 0020 with every existing row preserved, and use separate loopback capture mailboxes. Hosted CI wiring, live OCI contacts and production secret/SMTP qualification remain later work. Earlier source-checkpoint pending labels above describe the pre-qualification snapshot.


## Additional lifecycle notices

The [parity reference](../reference/lifecycle-email.md#lifecycle-notice-parity--6-november-2026)
uses the same responsible-only routing and outbox. There is no new saved-preview failure switch
or reason to damage a tenancy merely to generate a notice. For a single email-less recovery
admin, missing test routing records a blocked notice rather than sending to another person.
With the deliberate local capture configuration above, an accepted notice can use the test
mailbox without inventing an original address. Normal successful deletion/membership work does
not email. Negative cases are exercised automatically in disposable fixtures; live provider
failures and staging isolation remain on the manual manifest.
