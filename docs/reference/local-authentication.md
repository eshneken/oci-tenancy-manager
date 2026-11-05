# Local recovery authentication

29 October 2026 · D58 B implementation checkpoint

[Backend setup](../../backend/README.md) · [Administrator grants](administrators.md)
· [Session/request guards](authentication.md) · [Application settings](application-settings.md)
· [Accepted local recovery design](../engineering-design/19-administrator-provisioning.md)

## Scope and explicit composition

The backend implements interactive operator bootstrap/reset and password-plus-TOTP local sign-in.
This is the application's protected recovery administrator, separate from recovery users inside OCI
child tenancies. Its fixed username is `recovery-admin`; the durable identity is its installation-local
issuer and opaque grant UUID subject, not the username, email or employee-feed membership.

The default `create_app()` remains health-only. Supplying session authority and browser settings
adds the existing session/activity/logout routes. Supplying `LocalLogin` as an additional dependency
explicitly adds `POST /api/auth/local/sign-in`. Configuration parsing alone creates no administrator,
credential, route or session. The separate [local application launcher](local-application.md) explicitly
composes these dependencies and serves the React sign-in/administrator screens over laptop HTTPS.
Corporate SSO is neither called nor used as a fallback in local authentication.

The implementation uses the existing six application tables. Frozen migration
`0006_local_authentication` expands the closed audit-kind constraint; it adds no table. Apply reviewed
migrations through the existing operator-controlled migration path before enrollment or sign-in.
The preserved organization prototype and its database are separate.

## Settings and identity scope

`[local_auth]` is optional and defaults to `None` when absent. Its six fields are all required when
the section is supplied. Existing strict version/unknown-key validation still applies.

| Setting | Meaning and bounds |
| --- | --- |
| `workspace_id` | Exact server-selected installation workspace: 1–256 nonblank characters. Login input cannot select another workspace. |
| `issuer` | Stable installation-local namespace: 1–256 nonblank characters. Select it before bootstrap and retain it; it must remain distinct from corporate namespaces. |
| `max_failures` | Failures in a counting window before cooldown: integer 1–20; sample value 5. |
| `failure_window_seconds` | Shared failed-attempt window: integer 30–3,600 seconds; sample value 300. |
| `cooldown_seconds` | Shared temporary cooldown: integer 1–300 seconds; sample value 60. Rejected attempts during cooldown do not extend it. |
| `max_password_workers` | Simultaneous password checks per API process: integer 1–4; sample value 2. This is not a deployment-wide or per-IP limiter. |

The sample file's workspace and issuer are examples, not account provisioning. Changing either after
bootstrap is not an identity migration; reset retains the protected grant identity. Deployment must
keep the configured namespace and its session/current-grant authority composition consistent.
Roll consumers when settings change. Newly issued sessions use the configured idle/absolute policy;
existing rows retain their issued limits. Changing local throttle policy affects subsequent checks
against shared stored counters and does not silently clear an existing cooldown.

Password values, verifiers, TOTP seeds and database credentials do not belong in TOML. The secret
directory is an explicit operator argument/dependency outside these settings. Operator database
access uses separately supplied `OTM_DATABASE_URL` and, for remote TLS, `OTM_DATABASE_CA_FILE`.
The explicit connection loader rejects URL query overrides and libpq `PG*` environment options;
remote connections require certificate verification, with the existing loopback-only development
exception. No saved development connection is selected automatically.

## Laptop secret custody

`DirectorySecrets` is an explicitly selected **laptop-only** adapter. It is not an OCI Vault adapter
or an automatic fallback when production secret custody fails. The caller must precreate an absolute
secret directory owned by the running user with mode `0700`. Keep it outside versioned/exported
artifacts. No path component may be a symlink, and `..` components are refused.

Each enrollment/reset writes a new randomly named seed file using descriptor-relative traversal,
exclusive creation and `O_NOFOLLOW`; files have mode `0600`. File and directory writes are flushed
with `fsync`. The returned `local-secret:<opaque-id>:<SHA-256-content-digest>` reference names that exact version. The adapter
never overwrites an earlier reference and provides no deletion operation.

Reads verify the content digest as well as a regular file, effective-user ownership, exact `0600` permissions, one hard link and
bounded valid seed contents. Directory traversal again rejects symlinks. This immutable-version
interface prevents the application from replacing a stored version; it is not an operating-system
immutability or cryptographic tamper-proof guarantee against the file owner.

The database stores the password verifier and opaque TOTP reference, never the TOTP seed. Production
must qualify independently usable OCI Vault/operator custody before this local filesystem adapter
could be replaced for deployment. Secret references and enrollment material must not enter ordinary
administrator views, exports, retained screenshots or logs.

## Interactive operator bootstrap and reset

The commands below are the current laptop/file-custody composition. The accepted cloud target is
[the separate operator-pod procedure](#cloud-operator-target); the current CLI is not a Vault-backed
cloud entrypoint. `reset-local` refers to the OTM-local identity, even when that identity is deployed
in OCI.

Install the backend and migrate its schema first. From the repository root, invoke one of:

```sh
uv run --project backend otm-admin bootstrap --config backend/config/application.toml --secret-directory /absolute/private/mfa-directory
uv run --project backend otm-admin reset-local --config backend/config/application.toml --secret-directory /absolute/private/mfa-directory
```

These commands require a real interactive stdin/stdout terminal, explicit local-auth settings,
private seed directory and operator database credentials. They accept no password/seed/code argument.
Do not supply factor values on a command line. The CLI uses fixed diagnostic codes rather than
reflecting invalid argument values or raw SQL exceptions.

The operator path first checks the actual database role's membership in the grant table's owning
role and reads `session_user` for audit attribution. An arbitrary actor label is not operator authority.
It checks whether bootstrap/reset is appropriate before prompting or staging material. Bootstrap
refuses an existing recovery principal; reset requires an existing one.

The flow then:

1. Prompts twice for a new password without terminal echo. It accepts 15–128 characters and at most
   512 UTF-8 bytes, preserving whitespace and Unicode without trimming or truncation.
2. Hashes with Argon2id using 65,536 KiB (64 MiB), three passes and one lane. The maintained library
   generates the salt and stores the encoded verifier; no reusable password is stored.
3. Generates a new random TOTP seed and writes its immutable secret version. It displays the seed
   only in the interactive enrollment terminal so the operator can enroll an authenticator. Do not
   record/share that terminal or save its output as an ordinary build artifact.
4. Prompts without echo for a current authenticator code and verifies it. The enrollment code's
   matching time step is consumed when the credential is committed; that code cannot immediately
   be reused to sign in.
5. Rechecks real operator authority and expected protected-grant state inside the enrollment
   transaction. Bootstrap inserts the grant/credential and audit together. Reset locks the same
   protected row, preserves its identity, changes authorization revision, replaces verifier/reference,
   clears throttle state, revokes affected sessions and appends reset evidence in one commit.

Success returns only initialized/reset status and administrator UUID after commit. Enrollment creates
no browser session; normal sign-in still requires both factors. Concurrent bootstrap contenders are
resolved by the unique protected-grant constraint, not an upsert that overwrites the winner. A reset
using stale expected grant state fails rather than replacing newer credentials.

A failed or interrupted enrollment may leave a staged secret file. The command does **not** delete
it automatically, including after an uncertain commit, and reset retains the old seed version.
Before any manual cleanup, an operator must inspect the committed grant/credential reference and
resolve uncertainty: either old or newly staged material could back the usable account. There is no
automatic secret garbage collector or reset journal in this slice.

## Guarded sign-in API

With the explicit dependencies composed, `POST /api/auth/local/sign-in` accepts one closed JSON
object containing `username`, `password` and `totp_code`. There is no client-selected issuer,
workspace, administrator ID, role, session lifetime or redirect. Username input is bounded to 64
characters, password input to 128 characters/512 UTF-8 bytes, and the TOTP code to six ASCII digits.
The HTTP handler requires `application/json`, bounds the body to 4,096 bytes and sanitizes validation
errors instead of reflecting factor values or framework validation details.

The sign-in exception waives only the requirement to already have an authenticated session. HTTPS,
exact Host, single exact Origin and `X-OTM-Request: 1` remain mandatory, including for a first login.
Arbitrary forwarded headers are not trusted. No permissive CORS middleware is added. The same browser
boundary makes responses non-cacheable and applies the existing response-security headers.

`LocalLogin` reads a current grant/credential snapshot and releases its database connection before
password hashing or secret retrieval. An unknown username uses a dummy Argon2id verifier. Failed
password/username/TOTP checks produce generic 401 `LOCAL_AUTHENTICATION_FAILED`; secret/storage
unavailability and capacity exhaustion produce fixed 503 `LOCAL_AUTHENTICATION_UNAVAILABLE`.
Neither a response nor an exception discloses whether an attempted username exists.

## Replay, cooldown and atomic issuance

PyOTP verifies six-digit codes on 30-second steps, allowing the previous, current or next step.
When the same six-digit value happens to match multiple adjacent counters, the implementation takes
the **greatest matching step**. It accepts only a step greater than the credential's last consumed
step; choosing an older matching counter cannot permit a second session from that collision.

After password work, a short transaction locks the protected grant and credential row. It rechecks
active status, exact configured issuer, unchanged authorization revision, password verifier and seed
reference. It verifies TOTP against the current consumed step under those locks. Reset races or
concurrent use of the same code cannot rely on an earlier snapshot to issue a session.

Failed attempts share credential-row counters across processes. When the protected principal exists,
unknown-username attempts also use that shared failure path. A new/expired window starts at one;
reaching the configured threshold sets a cooldown. Attempts during cooldown still fail generically
and do not extend it. A later attempt after cooldown starts a fresh window. A successful login clears
these counters. This shared rejection policy is checked in the final transaction; it does not remove
the need for ingress/IP controls or bound all expensive work before that transaction.

Password work is separately limited by a nonblocking per-process semaphore. Capacity exhaustion
fails unavailable, rather than waiting without bound. Each worker can require about 64 MiB for its
Argon2 computation; `max_password_workers` must fit process/pod memory, and multiple processes each
have their own capacity. The dummy verifier is generated when constructing the login service.
An ingress/IP rate limiter and production resource/concurrency qualification remain future work.

A successful transaction advances the consumed TOTP step, clears failures, inserts a new session
with an independently random 32-byte URL-safe handle, and appends required success audit. Only the
handle's SHA-256 digest is stored. A valid old presented handle for the same workspace/identity is
revoked in that transaction; it is never reused as the new session token. Pinned idle/absolute limits
and exact grant UUID/revision come from trusted server state.

Only after commit does the response set `__Host-otm_session`: Secure, HttpOnly, SameSite=Lax, Path=/,
no Domain, with the issued absolute max-age. The JSON body contains only workspace, optional display
name and expiry. No token, password, seed, verifier or TOTP code is returned in JSON. A failed audit or
commit cannot yield a success cookie. A lost success response may leave a committed session and
consumed code; retrying requires a fresh eligible code, not assuming the old code is reusable.

## Evidence, roles and remaining qualification

Migration 0006 enables `administrator_bootstrapped`, `local_credentials_reset`,
`local_sign_in_succeeded`, `local_sign_in_failed` and `session_logged_out`, in addition to existing `administrator_revoked`.
Each has a scoped administrator target and no fake OCI operation. Closed `local-auth-1` data carries
outcome, optional session UUID and optional authorization revision. Passwords, attempted usernames,
OTP codes, seeds and raw request bodies are excluded. Bootstrap/reset identify the verified database
operator principal; sign-in success identifies the recovery principal, not a proven individual human.
Failures use an unauthenticated actor and are recorded only for the first counted failure and cooldown
entry, not every rejected request. Missing principal/custody and pre-transaction failures do not imply
that a failure audit row was persisted.

Operator bootstrap/reset require the separately privileged owner-role boundary. The intended API
role reads credential material server-side and updates only replay/throttle bookkeeping; it must not
replace password verifiers/seed references, bootstrap a protected identity or perform schema changes.
Deployment of that restricted API role remains qualification work; shipping the CLI in the same
image does not grant an API connection operator authority. Ordinary administrator add/regrant
remain separate slices; guarded directory/revoke endpoints now back the local UI.
Logout performs first handle revocation and `session_logged_out` audit atomically, without an IdP
or current-role dependency. Unknown/already revoked handles remain idempotent with no duplicate
event. If audit or COMMIT fails, the browser cookie is cleared but the response is unavailable;
server-side revocation is not falsely reported successful. Required SQL role privileges include
scoped grant/session SELECT, session revoked_at UPDATE and audit INSERT.

This implements local backend authentication, not production deployment readiness. OCI Vault custody,
corporate SSO, ingress/IP limiting, production API-role/managed PostgreSQL qualification, OKE/TLS/proxy
composition and production frontend delivery remain future gates. The local React application is
implemented separately. Unit decisions and HTTP mocks cannot prove
SQL replay exclusion, transaction rollback, role separation or concurrent issuance. Disposable real
PostgreSQL scenarios must qualify those properties; in-progress tests are not reported here as results.

## Cloud operator target

The user accepted [temporary Kubernetes operator pods](../engineering-design/19-administrator-provisioning.md#accepted-cloud-operator-procedure--30-october-2026)
for cloud bootstrap/reset. The infrastructure slice must supply an approved digest-pinned operator
image, interactive TTY, independently authorized `kubectl` RBAC, separate operator database authority
and the production OCI Vault adapter. API workload identity and an OTM session are not sufficient
operator authority. The Kubernetes/operator recovery path must remain usable during app/corporate
SSO outage, with authentication and network controls retained.

Current `otm-admin` requires `--secret-directory` and creates `DirectorySecrets`; that implementation
is for laptop custody. A reviewed cloud operator composition must select qualified Vault custody
before cloud use. No production seed-file mount or automatic fallback to the directory adapter is
assumed. There is no new cloud command/flag or deployed pod implied by this guide.

The interactive proof, one-time bootstrap refusal and reset transaction remain unchanged. Prompt
password/confirmation and TOTP proof without echo; show enrollment only in the private terminal.
Factors never enter YAML, arguments, logs, Terraform state, CI output or retained terminal/browser
captures. Retain nonsecret verified execution context without claiming a shared database principal
proves a human. Remove the temporary pod after completion/approved abandonment; uncertain commit
still requires inspection of exact committed secret references before any secret-version cleanup.

[Infrastructure acceptance](../engineering-design/18-database-ci-and-build-order.md#infrastructure-slice-cloud-administrator-bootstrapreset)
covers RBAC/ordinary-API denial, repeated bootstrap, explicit reset and session invalidation,
app/SSO-outage recovery, unavailable DB/Vault, secret redaction and pod cleanup. These remain cloud
qualification tests, not executed results or permission to deploy.
