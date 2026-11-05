# Parallel Atlas Test instance

Your existing organization stays at **[Atlas — localhost:8443](https://localhost:8443)**.
The separate **[Atlas Test — 127.0.0.1:8444](https://127.0.0.1:8444)** is prepared for the
[organization manual runbook](organization-mapping-runbook.md).

| | Current environment | Runbook environment |
| --- | --- | --- |
| Browser address | `https://localhost:8443` | `https://127.0.0.1:8444` |
| Installation directory | `.local-dev/application` | `.local-dev/runbook` |
| Visible name | Atlas | Atlas Test |
| Database | Existing organization, unchanged | Separate PostgreSQL container, initially empty |
| Administrator/MFA | Existing enrollment | Separate enrollment required |
| Workspace | Existing configured workspace | `runbook-lab` |
| Source data | Your existing organization | Six synthetic `example.test` CSVs |

The test API and simulation worker are already running. Database credentials, local issuer, TLS key,
MFA custody and settings are separate. No employee data or credentials were copied from the current
installation. Both use the same application source/build; this isolates data and settings, not code
versions. All OCI operations remain simulated.

## 1. Enroll the test administrator privately

Run these commands yourself in Terminal:

```sh
cd "<repository-root>"
uv run --project backend otm-local bootstrap --directory "$PWD/.local-dev/runbook"
```

Choose a strong password and enroll the **new** TOTP seed in your authenticator, labeling it
**Atlas Test**. Enter the requested code in that same private terminal. Do not paste passwords,
seeds or codes into chat or save terminal output. This command targets only Atlas Test; your current
administrator is unchanged. Enrollment refuses a second bootstrap.

A private convenience shortcut is also available under
`.local-dev/runbook/Enroll Atlas Test.command`; opening it in Terminal runs the same targeted command
without capturing its output. It does not bypass enrollment.

## 2. Open Atlas Test and start the runbook

Open **https://127.0.0.1:8444**. On first use you may need to accept its local self-signed certificate
warning after verifying this exact loopback address. No machine-wide certificate trust was installed.
Sign in as `recovery-admin` using the test password and a **fresh** code from Atlas Test's factor;
the enrollment code cannot immediately be reused for login.

Use the exact host **127.0.0.1** for testing and **localhost** for your current app. Host-only cookies
are separate between these names; ports alone would not separate them. You can keep both open in
the same browser without replacing each other's login. Do not substitute `localhost:8444`.

The test organization starts empty. A synthetic source policy is ready; save the Root/Alpha/Beta
mappings in the runbook before the first CSV. You do not need to reset first. The runbook links all
six files and gives increasing as-of times and expected results.

## 3. Reset only the test organization for another run

Finish or cancel all unsettled tenancy operations first. From the project directory:

```sh
uv run --project backend otm-local reset-organization --directory "$PWD/.local-dev/runbook" --confirm-reset-organization
```

This deliberately clears the eight organization/tenancy test tables **in Atlas Test only**.
It preserves that instance's administrator/MFA, sessions, operations and immutable audit history.
There is no undo. Refresh Atlas Test and save Organization Mapping again before importing.
The test source-policy file remains available. Your current instance is not selected by this command.

**Never omit `--directory`** when following this guide. The CLI defaults to the original
`.local-dev/application`. The screen's reset instructions use a placeholder installation path;
replace it with this explicit runbook path rather than using a default command. The screen itself
does not execute a reset. Current application settings were not modified to enable this test reset;
it is enabled separately in Atlas Test.

## 4. Start the test instance after a reboot

The database container/data and private enrollment persist. From the repository root, first run the
idempotent setup for this directory if Docker or its container was stopped:

```sh
uv run --project backend otm-local setup --directory "$PWD/.local-dev/runbook" --port 8444
```

It preserves existing test credentials, settings and data. Then, in one Terminal:

```sh
uv run --project backend otm-local start --directory "$PWD/.local-dev/runbook"
```

And in a second Terminal:

```sh
uv run --project backend otm-local worker --directory "$PWD/.local-dev/runbook"
```

Do not start duplicate API/worker processes while the ones prepared here are still running.
For these foreground commands, Ctrl-C stops only the corresponding process. To stop/restart the
currently backgrounded installation, ask to stop/restart **Atlas Test on8444** explicitly. Its owned
process IDs are recorded privately in `.local-dev/runbook/runtime.json`; broad process-name kills
could stop both environments. The earlier current-instance restart helper is now scoped to its
application TLS path and recorded worker, not every OTM process.

The test installation's private files/logs live under `.local-dev/runbook`, outside public assets
and ignored by Git. Keep them private. No additional dependency, migration or OCI connection is needed.
