# Laptop development against non-production OCI

Approved 14 November 2026: continue running Atlas/API/workers and Rancher PostgreSQL on the laptop,
while real OCI adapters use a dedicated named API-key profile in `~/.oci/config`. Hosted staging and
production use OKE workload identity. No browser login or session-token flow is required for laptop
development. These are explicit selections, not fallback authentication methods.

## Resources and ownership

The non-production tenancy has sibling **development** and **staging** compartments. Each environment
keeps one compartment, without further application subcompartments. Development needs only its own
application Vault/HSM key and managed test children; its database/queue, MFA custody and application
processes remain local. Staging retains the full OKE/managed PostgreSQL platform and its separate
application and database-provisioning Vaults. Production remains in a separate tenancy.

Development and staging children come from the same non-production parent. Each instance's own
PostgreSQL inventory is authoritative for the children it manages. There is no global child registry,
new cross-environment collision service or additional environment-label approval gate. Existing
registered-target, parent/child, credential-binding and destructive-action checks remain unchanged.
Use separate test children in normal operation and do not intentionally import one child into both
instances. Baselines, operations and credentials remain independent through their databases and Vaults.
Tags/names are useful labels, not a new authorization mechanism.

## Explicit application settings

The public `backend/config/development-oci.application.toml` is a synthetic template, not an active
configuration. Relevant fields are:

```toml
environment = "local"
provider_mode = "oci"

[testing]
email_override = "developer@example.test"

[oci]
auth_method = "api_key_profile"
region = "us-ashburn-1"
tenancy_ocid = "ocid1.tenancy.oc1..synthetic"
config_file = "~/.oci/config"
profile = "ATLAS_DEV"
```

Keep actual OCIDs and private operator settings outside version control. The email override is
mandatory for laptop OCI mode even when SMTP is disabled: OCI-generated activation/contact messages
must also reach the testing administrator, not the employee represented in organization data.
`environment="local"` selects the laptop execution profile; `provider_mode` independently selects
simulated versus real OCI effects. Existing local installations default to `simulated` with no OCI
configuration and continue unchanged. A development OCI profile is not a hosted staging release.

Hosted candidates select `auth_method="oke_workload_identity"` without `config_file` or `profile`.
API-key authentication in staging/production, OKE authentication in local mode, OCI settings in
simulated mode and OCI mode without settings are rejected before constructing clients.

## Named OCI profile

Once the tenancy and development user/IAM grants are available, register that user's API public key
with OCI and put a complete `[ATLAS_DEV]` API-key section in the private OCI configuration file.
The section must explicitly provide `user`, `tenancy`, `fingerprint`, `key_file` and `region`.
An optional `pass_phrase` supports an encrypted PEM. It must not rely on credentials inherited from
`[DEFAULT]`. Other profiles may coexist in the same file and are not selected by Atlas.

Use an absolute or `~/` path to the config and private key. Files must be current-user-owned,
regular, nonempty, no larger than 64 KiB, single-linked, and inaccessible to group/others; use mode
0600. Symlink leaves, relative paths and `..` traversal are rejected. Atlas never writes or fixes
permissions on these files. No real `~/.oci` file was needed or inspected during implementation.

`platform_identity(settings)` validates the complete application profile, selects the exact named
section, checks its tenancy and region, and constructs a real SDK API-key signer. Only known signer
fields reach the SDK; profile-controlled endpoints, debug logging, session tokens and alternate auth
selectors are rejected. Config/profile/key failures return only `OCI_AUTHENTICATION_UNAVAILABLE`;
there is no browser prompt, DEFAULT profile, instance-principal or simulator fallback.

`configured_vault_reader(settings, scope)` uses that identity with the same guarded reader used by
OKE. Vault region must agree before private files are read. The local platform profile is for its
approved Vault/parent operations; child calls still use each registered child's automation credential.
An application admin login and a platform SDK identity are separate authorities.

## Minimal development custody with Terraform

`infra/environments/development/custody` creates one shared Vault and HSM AES256 key in the explicit
existing development compartment. It creates no OKE, managed database, network, compartments,
secret contents, IAM grants or hosted GitHub deployment environment. Vault/key replacement is guarded.
The root is local-operator-only with explicit `APIKey` and a named profile from `~/.oci/config`.

Before applying, verify the intended principal, tenancy and compartment and effective IAM grants.
Supply private variables `oci_profile`, `tenancy_ocid`, `hosting_compartment_ocid` and `region`.
Initialize the local backend with an explicit absolute private state path through `-backend-config`;
never reuse staging state or use a shared/default state location. Review the plan before applying.
Keep state/backups outside the checkout with owner-only permissions. This is not a workflow invocation
or authorization to provision cloud resources now. The Terraform provider uses its own profile loader;
Atlas's additional private-file/profile checks are not claimed for Terraform.

## What is implemented and what comes next

Implemented: strict settings, named API-key signer, OKE selection, shared Vault-reader composition,
synthetic regressions and mock-tested minimal development custody source. No real profile, OCIDs,
private keys or resources are configured. The existing simulator API/worker launchers explicitly
refuse OCI mode rather than silently running simulated mutations under a real-OCI profile.

Next: compose the full live OCI service adapters and laptop launcher, provide private Vault references
and effective IAM, and qualify the non-production parent/child flows. Until then, copying the example
over the saved demo config will not make the UI live against OCI; leave saved 8443 unchanged.

Live profile signing/permissions, Vault reads/writes, activation email redirection and independent
local/staging inventories belong in the [manual qualification manifest](real-oci-test-manifest.md#laptop-api-key-development).

Official references: [OCI SDK configuration profiles](https://docs.oracle.com/en-us/iaas/tools/python/latest/configuration.html)
and [API signing keys](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm).

## Source validation receipt — 14 November 2026

The complete backend unit gate passed 2,798 cases, no failures/errors/skips, with 95.37% complete-source
line coverage across 195 modules. All 96 focused platform-auth/Vault cases passed. Four disposable
TLS PostgreSQL compatibility cases passed; Rancher's Docker CLI must be available on the test
command's PATH. The full mock-only infrastructure gate passed 141 cases and seven exact replacement
rejection guards, including the development Vault/key. No provider API or Terraform apply was used.

Inline-purpose, Ruff, Bandit, documentation/link, publication, credential and whitespace checks
passed. Independent documentation/security reviews passed. No UI changed; the full integration/
Playwright suite remains a milestone/PR gate. No saved 8443 code/configuration was published or
changed for this slice, and its health endpoint remained successful. Actual OCI IAM/profile and
full live service composition remain pending.
