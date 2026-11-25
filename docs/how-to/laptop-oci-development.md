# Laptop development against non-production OCI

Approved 14 November 2026: continue running Atlas/API/workers and Rancher PostgreSQL on the laptop,
while real OCI adapters use a dedicated named API-key profile in `~/.oci/config`. Hosted staging and
production use OKE workload identity. No browser login or session-token flow is required for laptop
development. These are explicit selections, not fallback authentication methods.

## Resources and ownership

The non-production tenancy has sibling **development** and **staging** compartments. Each environment
keeps one compartment, without further application subcompartments. Development needs only its own
application Vault and software-protected key and managed test children; its database/queue, MFA custody and application
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
permissions on these files. The 14 November source checkpoint used synthetic profiles.

`platform_identity(settings)` validates the complete application profile, selects the exact named
section, checks its tenancy and region, and constructs a real SDK API-key signer. Only known signer
fields reach the SDK; profile-controlled endpoints, debug logging, session tokens and alternate auth
selectors are rejected. Config/profile/key failures return only `OCI_AUTHENTICATION_UNAVAILABLE`;
there is no browser prompt, DEFAULT profile, instance-principal or simulator fallback.

`configured_vault_reader(settings, scope)` uses that identity with the same guarded reader used by
OKE. Vault region must agree before private files are read. The local platform profile is for its
approved Vault/parent operations; child calls still use each registered child's automation credential.
An application admin login and a platform SDK identity are separate authorities.

## Development laptop enrollment policy

The optional `local_app_iam` input in
`infra/environments/development/bootstrap` uses the existing private bootstrap state. Supply the
Default domain OCID, the `otm-development-localapp` writer group OCID, and the distinct
`otm-development-users` app group OCID in a private variable file. Verify the three live
references and the writer's actual group membership. Leaving the input unset adds no policy.
Keep the input in subsequent bootstrap plans once the policy is managed in state.

The policy is attached to the non-production root because the domain is there. Terraform verifies
the named writer and assignment groups against their configured OCIDs. The dedicated pilot signer
has `use groups` and `use users` throughout the tenancy, including updates. Keep that credential
private to this laptop and review its broader effective authority independently of Atlas. Atlas
checks the named development app group and its exact GUID before using `AddUserToGroup` or
`RemoveUserFromGroup`, and rejects incomplete or mismatched provider responses.

Keep `create_federated_users` false until separately qualifying the optional user-create grant.
The draft grant limits the operation to the selected domain. Atlas supplies the federated-only,
notification-suppressed request. Review effective permissions against unrelated groups, user
updates and credentials. Parent organization operations, including child tenancy creation and
deletion, require separate permission and operation qualification.

## Development custody through GitHub Actions

The approved development target is a compartment named `otm-development`, directly under the non-production
tenancy. The laptop profile remains private and is used for laptop SDK calls and approved operator
bootstrap. After local bootstrap, [Development infrastructure](../engineering-design/26-administrator-sso.md#development-terraform-ownership)
is the single Terraform build for all development resources. It uses temporary federated
credentials. This procedure covers its current Vault and software key scope. Atlas SSO adoption
will extend the same root and state after provider qualification.

1. **Verify the target before requesting approval.** Independently check the named profile's
   principal, tenancy, region, namespace, and the exact compartment name, OCID and parent. Create
   the compartment only after approval. The shared Actions renderer currently accepts
   `us-ashburn-1`; verify the selected deployment region before configuring trust.
2. **Bootstrap state with separately approved operator authority.** Use
   `infra/environments/development/bootstrap` with an explicit absolute owner-only local backend
   path and private tfvars. Supply `oci_profile`, `hosting_compartment_ocid`, and a `target` object
   containing `environment = "development"`, `tenancy_ocid`, `object_storage_namespace` and
   `region`. Supply `github_identity_domain_ocid` and `github_repository` in a separate private
   `github-policy.tfvars.json` after verifying the domain, tenancy, and GitHub owner/repository
   against the trust.
   Bootstrap checks the compartment name, active state and root parent before bucket creation.
   Preserve the bootstrap state privately. With `OTM_DEV_BOOTSTRAP_DIR` set to the absolute,
   owner-only directory containing the private `bootstrap.tfvars.json`, prepare and inspect a plan
   from the repo root:

   ```sh
   terraform -chdir=infra/environments/development/bootstrap init \
     -backend-config="path=${OTM_DEV_BOOTSTRAP_DIR}/bootstrap.tfstate"
   terraform -chdir=infra/environments/development/bootstrap plan \
     -var-file="${OTM_DEV_BOOTSTRAP_DIR}/bootstrap.tfvars.json" \
     -var-file="${OTM_DEV_BOOTSTRAP_DIR}/github-policy.tfvars.json" \
     -out="${OTM_DEV_BOOTSTRAP_DIR}/bootstrap.tfplan"
   terraform -chdir=infra/environments/development/bootstrap show \
     "${OTM_DEV_BOOTSTRAP_DIR}/bootstrap.tfplan"
   ```

   A fresh bootstrap plan includes a private, versioned Standard bucket named
   `otm-development-tfstate` and the scoped GitHub IAM policy. Review both before approving any
   creates. The custody workflow uses `custody/development/terraform.tfstate`. If custody was ever applied with the older local
   backend, stop and review state migration before initializing the new backend. Bootstrap also
   owns the `otm-development-github-infrastructure` policy as `oci_identity_policy.github_infrastructure`. To adopt an existing
   policy, verify its identity and statements, back up the current private local state, then run
   `terraform import` against the initialized bootstrap backend with both private variable files
   and the existing policy OCID. Require a zero-change plan once the imported policy's live
   statements match the source. Review and approve any scope correction as a separate IAM update.
   OCI policy names are immutable. Replacing a policy requires separate approval.
3. **Configure the protected `development` GitHub Environment.** Both dispatches require
   human review. Allow only protected `master` and disable administrator bypass. Qualify one
   restricted token-exchange client and exact OIDC claims for this environment and workflow,
   with audience `otm-infrastructure-development`. Configure propagation of `ext_workflow_ref`
   and `ext_environment` from the signed GitHub claims so IAM can match the exact job using
   OCI's `identityfederateddomainapp` principal type. During plan qualification, verify that the
   exchanged credentials resolve to the intended domain and workflow and can read the designated
   private bucket. Use the named laptop key only on the laptop.
4. **Store the scoped configuration in the environment.** Set
   `OTM_INFRA_IDENTITY_DOMAIN_URL`, `OTM_INFRA_CLIENT_ID`, `OTM_INFRA_CLIENT_SECRET`,
   `OTM_HOSTING_COMPARTMENT_OCID` and `OTM_CUSTODY_INPUTS_JSON` as environment secrets.
   The JSON has only the `target` object from step 2. The approved policy includes initial Vault
   and key creation in development. Both dispatches share that OCI authority. The planning command
   does not apply the plan. GitHub review, separate apply enablement, and the exact saved-plan check
   govern apply. This policy grants no application-secret, cross-environment, or trust-administration
   access. Verify that effective access is denied. Set `OTM_INFRASTRUCTURE_ENABLED=true` only after
   approval and setup validation.
   Leave `OTM_INFRASTRUCTURE_APPLY_ENABLED` off until the first apply is separately approved.
5. **Review the exact plan privately.** In **Actions → Development infrastructure** on `master`,
   select `plan`. The plan can write a lock and a saved plan object in the development bucket.
   Approve the live dispatch separately. For the retired development HSM key, the Terraform
   `removed` block prevents recreation and uses `destroy = false` so it leaves the OCI deletion
   schedule in effect. While the old address is still in state, require one state-only `forget`
   with zero creates, updates, deletes, or replacements. If the old address is already absent,
   require a no-op plan. Check that the Vault and software key both have no-op actions.
   The existing reviewed-apply command rejects receipts containing `forget`. Keep apply held
   and reconcile that state entry separately before a future deployment if it remains tracked.
   Terraform does not write application secret values. The separate
   apply dispatch takes the successful plan run ID and reviewed SHA-256 and rejects any delete
   or replacement. Confirm the exact reviewed effects before approving apply. An interrupted
   apply requires state reconciliation and a fresh plan.

See the [shared plan and apply procedure](infrastructure-plans.md) for saved-plan custody and
recovery. Development creates no hosted network, compute, database, or child tenancy.

## What is implemented and what comes next

The [isolated OCI laptop launcher](../reference/local-application.md#local-oci-provider-development)
already supports the [8445 corporate identity pilot](../reference/corporate-sso.md), using its own
database and private configuration. The launcher can enable scoped administrator enrollment
and reads the pilot's client secret from owner-only local custody. The simulator API and
worker launchers reject OCI mode.

Compose and qualify the remaining real OCI service adapters and non-production parent/child
flows on 8445. Keep the saved 8443 demo on its simulator configuration.

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

## Development custody workflow validation

The development workflow and bootstrap source passed independent documentation and security
review. The security review identified the need to verify exact compartment placement. The
bootstrap now requires OCI readback of the active compartment name and its direct root parent
before planning the bucket, and the reviewer verified the guard and its negative mock test.

The targeted infrastructure workflow tests passed 201 cases. The complete backend unit gate
passed 3,321 cases at 95.0685% line coverage. Terraform passed 168 mock cases and eight expected
replacement rejections. GitHub environment activation, live federation, remote state locking,
and Vault/key apply remain pending separate qualification and approval.

The first approved bucket apply was rejected because OCI free-form tag keys cannot contain
periods. A read-only bucket lookup and the local Terraform state confirmed that no bucket was
created. The state module and development Vault and key now use hyphenated tag keys. The revised
plan contained only one private versioned bucket creation. On 24 November 2026, the approved
laptop apply succeeded. OCI readback confirmed the Standard bucket in the intended development
compartment, with public access disabled and versioning enabled. The owner-only local bootstrap
state contains exactly that bucket.
