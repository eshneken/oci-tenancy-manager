# Vault custody and database-reader IAM foundation

**Composed Terraform source; hosted live qualification pending.** The staging and production
infrastructure roots compose two Vaults, software-protected keys, database-reader IAM and an
OCI-generated PostgreSQL provisioning secret in one plan. Neither hosted deployment is authorized.

## One hosting compartment, two Vaults per environment

| Domain | Purpose | Authority added by this slice |
| --- | --- | --- |
| `database-provisioning` | Initial PostgreSQL administrator credential; privileged provisioning/recovery custody | Approved existing provisioning group can read secret-family and Vault metadata only in this Vault |
| `application-secrets` | Future runtime database credentials and managed parent/child credential custody | No application or provisioning-group grant is added yet |

`infra/modules/secret-foundation` creates two DEFAULT shared Vaults and a separate software-protected
AES-256 master key for each, all in the existing hosting compartment selected through
`OTM_HOSTING_COMPARTMENT_OCID`. It creates **no child compartments**. Vault/key `prevent_destroy`
guards remain. The module does not read secret bundles or export master keys. Vault generates the
initial PostgreSQL password within each composed hosted root.
Check that the effective workload policies omit key export access. For a hosted root with an
existing HSM key, stop and review a separate migration before applying a software-key plan. OCI
makes the protection mode immutable, and the Terraform lifecycle guards block replacement.

Exact Vault-ID conditions provide the IAM scope inside the shared compartment. Separate Vault
names alone are not an authorization boundary; both reader policy statements must retain the
condition targeting the database-provisioning Vault. OCI documents a
[Vault-filtered secret-family read policy](https://docs.oracle.com/en-us/iaas/database-management/doc/additional-permissions-required-use-database-management-external-databases.html).
Live secret/bundle/version read and denial tests remain required; do not remove the condition to
make a missing permission work.

The default shared Vault tier avoids allocating a dedicated virtual-private HSM partition. Actual
key usage, quotas, cost and availability still require live qualification. Automatic KMS master-key
rotation is explicitly disabled here: [Oracle documents automatic rotation as a virtual-private Vault feature](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/tasks_tasks_managingkeys_topic_edit_auto_key_rotation.htm).
Shared-Vault keys require an owned manual key-version rotation procedure and qualification before
go-live. This is separate from OTM's child signing-key/password rotation jobs. Preserve old key
versions needed to decrypt retained secrets; never assume rotating a key rewrites every stored secret.

## Composed hosting design

The staging and production roots each declare an `oci_vault_secret` in their database-provisioning
Vault using provider 9.13.0's `enable_auto_generation` and `secret_generation_context`. The
configured `DBAAS_DEFAULT_PASSWORD` template generates a 30-character passphrase inside OCI.
The PostgreSQL module receives the secret OCID and explicit initial version `1`. Terraform receives
metadata and does not read the password payload. Review the effective permissions, supported
constraints and initial version readiness before live use.
[OCI Vault secret resource](https://registry.terraform.io/providers/oracle/oci/9.13.0/docs/resources/vault_secret)

Review Vault, key, secret and database changes together through the
[environment plan and apply](infrastructure-plans.md#one-infrastructure-plan-and-apply-per-environment).
The root owns the provisioning group and read policy. Verify the workflow requester's effective
Vault/key and PostgreSQL permissions, including the correct secret/version and the denied scope
for unrelated identities. Keep all private metadata and saved plans out of public artifacts.

If old `security/<environment>/terraform.tfstate` or `platform/<environment>/terraform.tfstate`
contains resources, reconcile state ownership and IDs in a separately reviewed migration before
using the composed key. Preserve prior credentials and verify no unintended resource or password
replacement.

## Exact IAM limits

The policy is attached to the existing hosting compartment and grants the supplied group `read
secret-family` and `read vaults` in that compartment, each with the exact condition
`where target.vault.id = '<database-provisioning Vault OCID>'`. Neither grant covers the other Vault.
These are the requester-side permissions documented in
[OCI PostgreSQL policies](https://docs.oracle.com/en-us/iaas/Content/postgresql/policies.htm).
Secret-family read includes access to secret contents: this group is privileged credential custody,
not an ordinary application or UI-administrator group.

There are no write/delete/move grants, no direct key-decrypt grant, no tenancy-wide grant, no
application-secret grant, and no invented PostgreSQL service principal. Provisioning group membership and effective authority for deployment, service-side secret creation,
and key use require separate qualification. The reader policy itself grants read authority.

OCI policies are additive. Existing tenancy/ancestor grants may already confer broader authority;
these source statements cannot prove effective isolation. Live negative tests must check application
workloads cannot read initial database credentials and that provisioning readers cannot mutate/delete
secrets or read application-Vault secrets through other grants. Future OKE workload policies must
bind exact cluster, namespace and service account, with no node/parent credential fallback.

## Protection and qualification

Vault/key loss or access revocation can make dependent secrets and recovery unusable. Terraform
replacement guards do not block direct OCI administration, key disable/deletion, configuration removal,
or a privileged change that removes the guard. Preserve private state and key-version custody and
verify actual backup/recovery dependencies. This foundation does not automatically back up Vaults,
provide cross-region DR or repair lost keys after a database restore.

Run `bash scripts/check_infrastructure.sh` without OCI credentials. The native configuration
suites use mock providers and `init -backend=false`. Tests check exact policy text, distinct custody
domains, software key/Vault bindings, invalid input rejection and fixed roots. Two additional negative
journeys require mock setup followed by the exact protected resource's lifecycle rejection for Vault
and key replacement. They do not evaluate OCI's effective IAM or decrypt real secrets.

Follow the [pending live Vault/IAM qualification](real-oci-test-manifest.md#vault-custody-foundation)
for actual group/policy scope, generated-secret readiness and read denial, key rotation/decryption, state controls
and PostgreSQL provisioning. Full required application/milestone checks still precede the combined
PR; source checks are not a deployed service or production security qualification.


## Application retrieval source follow-up — 14 November 2026

The [read-only OCI adapter](../reference/vault-retrieval.md) now supplies scoped metadata/bundle reads with explicit OKE identity. [Terraform workload IAM and token mounts](oke-workload-identity.md) now exist as source; networking, deployment qualification and actual service integration remain pending; the reader does not broaden the provisioning group policy or activate workloads.
