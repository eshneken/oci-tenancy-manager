# Terraform state bootstrap

**Implemented bootstrap source; hosted live execution pending.** The local bootstrap roots
declare each compartment, private state bucket and OCI GitHub delivery foundation. Development
and production own their respective domain settings. Staging uses the setting shared with
development. The GitHub Environment controls and protected inputs also have a Terraform module;
verify the configured repository support and credential handoff independently.

For an existing compartment, verify the exact OCID and review adoption before any apply. No
live change is authorized by these instructions. Use the [infrastructure runbook](infrastructure-plans.md)
for the separate environment workflow.

## Before any live command

1. Confirm the approved environment, tenancy, region, intended hosting compartment and
   Object Storage namespace through OCI. Verify the authenticated principal's actual tenancy,
   effective permissions and compartment ancestry independently. An OCID pattern or environment
   string is not proof. Staging and production must not share principals or state paths.
2. Use an approved short-lived operator SecurityToken profile for this first bootstrap. The root
   also supports explicitly selected ResourcePrincipal or InstancePrincipal for later qualified
   execution; it never selects these automatically. Do not pass tokens, private keys or passwords
   through Terraform inputs or record them in plans, chat or repository files.
3. Install the exact CLI version and run `bash scripts/check_infrastructure.sh` from the repository
   root. This is safe without OCI credentials: all provider effects in those tests are mocked.
4. Create an operator-only directory outside the checkout, set `umask 077` and verify directory
   permissions. Give staging and production separate absolute paths. Copy only the selected
   root's `terraform.tfvars.example` to a private `target.tfvars` there, then replace its synthetic
   coordinates and profile with the approved values. Keep provider metadata, plans, state and state
   backups there too. Exclude all of this from cloud-synced/public folders and CI artifacts.

## GitHub exchange client rollout

For the existing development exchange, set `github_delivery.existing_exchange_app_id` to the
exact active App's 32-character lowercase hexadecimal SCIM GUID. Supply its verified GitHub issuer trust's GUID as `github_delivery.existing_trust_id`. The bootstrap declares a no-op adoption for the matching active trust. Inspect the plan and reject any trust mutation during adoption. Set `trust_active = true`
and keep `exchange_write_response_qualified = false`. The bootstrap verifies the active
development client through a read-only metadata projection. The trust and GitHub input
delivery use that verified identity. This transition leaves the App itself outside Terraform
resource state and preserves the existing client without replacing it.

Do not use the stock OCI provider's `terraform import` or an import block for an existing
live confidential App. Provider 9.13.0 can read its default credential-bearing response
before applying the configured attribute projection. For a fresh exchange client, set
`github_delivery.exchange_write_response_qualified = true` only after isolated verification
that the pinned provider's create and update responses exclude the client secret and its
hash from plans and state. Start a fresh client inactive and review any activation separately.

Development owns the GitHub issuer trust in the shared non-production identity domain.
Staging declares no second trust for that issuer. Both `github_environment.plan_enabled`
and `apply_enabled` and the staging `github_delivery.trust_active` must remain false.
Qualify a design that binds each staging assertion to its intended staging client before
changing these gates. Production uses a separate identity domain and remains held pending
its own qualifications.

## OCI IAM names and Identity Domains permissions

Use the checked top-level `otm-<environment>` name in the policy location. Use the exact group,
policy, bucket, or secret name where the OCI operation supports it. The hosted reader-policy
grant also pins `target.compartment.id`. Compartment names are unique only among siblings, and
the location includes descendants. An identical leaf name could therefore match another
compartment. Vault and OKE cluster bindings also use OCIDs that identify the exact resource.
[OCI compartment naming](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm) ·
[Vault policy variables](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/keypolicyreference.htm)

Workflows without a [verified named subject](#named-development-workflow-subject) use
`request.principal.domain.id` alongside the exact workflow and environment claims.
Oracle documents `request.domain.name` as a general principal variable. Its equivalence
for this token exchange still needs qualification. Keep the separate
`target.resource.domain.name = 'Default'` condition on the native group create/update and
list grants. The existing development adoption read uses the separate exact point-read
condition below. A group list request has no target group name.
[OCI general variables](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/policyreference_topic-General_Variables_for_All_Requests.htm) ·
[OCI IAM policy variables and permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/iampolicyreference.htm)

### Domain-owned GitHub identity policy

Attach `otm-github-identity` at the tenancy root because the native identity groups live
there. The development bootstrap owns the policy for the shared non-production domain,
including the development and staging statements. The staging bootstrap has no copy.
Production bootstrap owns a separate policy with the same name in the production tenancy.
Environment compartment policies continue to own the respective state and infrastructure access.

Each statement binds the federated principal to the verified domain, exact protected workflow
and matching environment claim. The development workflow's create and update
grants target only `Default/otm-development-users`. Each hosted workflow's native grants target its own
`otm-<environment>-users` and `otm-<environment>-database-provisioners` native groups in
the Default domain. Each workflow has a separate Default-domain `ListGroups` statement
because that operation has no target group name. Staging's statements preserve its exact
workflow/group pairing and do not lift the federation and dispatch holds.

For development adoption, the `inspect groups` statement also allows `GetGroup` when both
`target.group.name` and `target.group.id` match the exact existing group. The bootstrap uses
the same `atlas_sso.adopt_group_ocid` in the operator's protected settings as the workflow.
Verify the native group metadata against the approved binding. Member information is outside
that check. Variants requiring the target domain name or target domain OCID with the group
name did not authorize the point read with this workflow principal. The adopted group
condition preserves the verified principal binding, workflow and environment claims, leaves
create/update and staging grants as before, and requires no additional policy statement.

This is evidence for a point read of the existing group. A fresh group's first read without
an operator-verified OCID and the workflow's SCIM writes for App, Grant, Condition, Rule and
Policy remain unqualified. Keep apply disabled until the exact development deployment is
authorized and hosted qualifications are complete.

The domain-owner bootstrap's `identity_app_management_environments` opt-in defaults to an empty
set. It adds a `manage domains` grant for each selected workflow using the same principal,
workflow and environment bindings. The target is pinned by both its `Default` name and
its OCID. OCI omits the target OCID for `CreateDomain`, so this condition also excludes domain
creation. [OCI domain policy variables](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/iampolicyreference.htm)

The complete non-production proposal sets `["development", "staging"]` in the development
bootstrap. This prepares both workflow grants in one policy. Staging dispatch and token
exchange remain held until its client-bound federation is qualified. Production controls
its own opt-in independently.

Oracle documents application management for members of a group granted `manage domains`.
That documentation does not establish equivalent authorization for an exchanged Resource Principal
Session Token. The candidate permission is domain-wide and can affect applications beyond Atlas.
Oracle also lists native domain lifecycle privileges under `manage domains`. Review the exact
effective scope, including domain lifecycle operations, unrelated apps, the GitHub exchange client,
and upstream federation, before any live opt-in. Verify the required SCIM reads and operations with
the actual workflow principal. The saved-plan consumer independently gates the
[bounded development App activation](laptop-oci-development.md#development-atlas-browser-client-activation).
[Oracle application management](https://docs.oracle.com/en-us/iaas/Content/Identity/applications/overview.htm) ·
[OCI IAM policy variables and permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/iampolicyreference.htm) ·
[Identity Domains AppRole permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/RequiredRolePerEndpointExt.htm)

### Named development workflow subject

Development can opt in to the readable `dynamic-group Default/otm-development-github-identity`
subject on both `otm-github-identity` and `otm-development-github-infrastructure`.
The operator bootstrap owns that group and its Application Administrator assignment when enabled.
Its input defaults to the existing principal-domain OCID policy form.
[OCI IAM subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm)

Independently verify the protected workflow's exchanged `principal_ocid`. In the private
development bootstrap inputs, configure `github_workflow_dynamic_group` with that value and an
`existing` object containing both `group_id` and `grant_id`, which are SCIM GUIDs. Migrate an
earlier flat `group_id` into `existing` before planning. The source's import blocks adopt
both addresses. Require an import-only plan for these existing resources. A new setup needs
explicit `create_fresh = true` in place of `existing`. Leave the option unset if the exact
exchanged principal is unavailable.

The bootstrap looks up the single Application Administrator AppRole in the selected Default
domain and validates its administrative flag and `IDCSAppId` owner. Projected adoption reads
check the group's GUID, native OCID, name, domain, tenancy, and full
`resource.id = '<principal OCID>'` rule. Terraform owns the group through native IAM because
the Identity Domains resource import omits the matching rule. A fresh group is resolved to its
SCIM GUID by the exact native OCID. The Grant must exclusively bind that GUID to the verified
App and AppRole. Terraform blocks replacement and deletion of both managed resources.
The grant's stock-provider import uses its default response because changing the projection
would force replacement. Keep bootstrap plans and state in private custody.

The named subject applies only to the development workflow. Its principal type, protected
workflow ref, environment claim, operations and target conditions still apply. Dynamic-group
membership supplies the principal binding in this mode, so effective access depends on the
group retaining its exact matching rule. Reverify the rule after an approved group or principal
change. Staging and production use their existing principal-domain OCID bindings. Qualify the
actual exchanged GitHub principal against the named subject with an authorized read-only
plan and confirm denial outside the intended scope before relying on the new statements in
another setup. The existing development workflow's named-policy plan succeeded with all 13
managed resources unchanged. The scoped bootstrap adopted the existing group and grant
with two imports and zero OCI resource actions. Its scoped follow-up plan had zero imports
and zero OCI resource actions. Other bootstrap resources were outside that verification.
Obtain approval before applying later policy or ownership changes.

### Temporary development Application Administrator

The activation and follow-up used an **Application Administrator** domain role assigned to
the dynamic group that matched the exact development GitHub exchange principal. This domain
role can manage apps beyond Atlas. The development group and role remain in place for
operational plans after restoring the role re-established `GetCondition` access. Manage
the binding through the [operator bootstrap adoption](#named-development-workflow-subject).
Once adopted, retire a role or group only through
a separately reviewed Terraform change that explicitly addresses the resource's deletion
guard. Verify the resulting role removal and preserve a group still used as the
[named IAM policy subject](#named-development-workflow-subject). Reconcile state and OCI
effects before retrying a failed plan or apply.
Keep 8445 runtime configuration, the existing pilot, staging and production outside this change.
[Oracle dynamic group domain role assignment](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/assign-domain-role.htm) ·
[Oracle administrator role scope](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm)

## Hosted reader-policy writes

The staging and production bootstrap option `allow_runtime_policy_writes` defaults to `false`.
The default authorizes the protected GitHub workflow to refresh its three reader policies.
Creating or updating those policies in the hosted workflow requires setting the option to `true`
in the selected environment's private bootstrap inputs and separately approving that bootstrap
policy change.

When enabled, the grant permits `CreatePolicy` and `UpdatePolicy` for the exact
`otm-<environment>-database-provisioning-read`, `otm-<environment>-api-vault-read` and
`otm-<environment>-worker-vault-read` names in the verified hosting compartment. OCI can scope
policy names and operations, but does not restrict the statement bodies. The workflow could use
those three policies to grant its principal additional permissions within the hosting compartment.
Review this authority before approval. Verify the expected policy statements and denial of writes
to unrelated names, other compartments, and tenancy-root policies before enabling the hosted apply.
[OCI IAM policy variables and permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/iampolicyreference.htm)

## GitHub Environment and protected inputs

Set each root's `github_environment` controls. Provide one to six user or team reviewer IDs
in total and decide whether to prevent self-review. Terraform retains the `master` deployment
restriction. The five Checkpoint checks and protected-branch rules remain in force. Apply still
requires a separate enable flag and the exact digest of the privately reviewed plan. Keep
`plan_enabled` and `apply_enabled` false until the corresponding qualifications pass.
Hosted roots also require the approved exact Kubernetes patch and PostgreSQL major.

The [development maintenance window](laptop-oci-development.md#development-infrastructure-through-github-actions)
temporarily removes the development Environment reviewer for plan and apply. Restore the prior
Environment configuration at the end of the window. Bootstrap reviewer defaults and hosted
Environment protections remain in force.

Set `settings_file` to a JSON filename under the checkout's ignored `.local-dev` directory.
Use one owner-only regular file per environment, mode `0600`, at most 256,000 bytes. For development,
the file contains only an `inputs` object with the development `atlas_sso` fields. For staging and
production, it also contains top-level `allowed_source_cidrs` and `worker_cloud_init` strings.
Place the remaining [workflow inputs](../reference/infrastructure-plans.md#inputs) under
`inputs`. Bootstrap inserts the verified target automatically. Keep credentials out of that file.

Use an operator `GITHUB_TOKEN` authorized to administer the repository and write its environment
settings, plus `uv`, Python and the OCI CLI. Bootstrap validates the exact `master` deployment
rule before reading inputs. It reads the exact OCI exchange client credential through the
approved operator profile. The pinned Python helper seals input bytes against the GitHub
Environment's returned public key. Terraform writes the encrypted envelopes to GitHub. The
plaintext exchange credential stays out of Terraform variables, plans and state. Keep the
bootstrap state and saved plan private because they contain encrypted inputs and metadata.

Reconcile any existing GitHub environment, `master` deployment rule, variables and secrets with
their intended Terraform addresses before changing them. Review current protections and reserve
approval for expected changes only. Increase `secret_revision` after rotating the exchange
credential so Terraform delivers new ciphertext. Live credential handoff, trust, effective IAM
and access denials still require qualification.

## Review the foundation — operator-reviewed commands

The following is a template for **staging only**, not a command executed during development.
Replace the private directory before use. Run from the repository root. Do not point the production
root at staging inputs, or reuse either environment's initialized backend directory.

```sh
umask 077
export OTM_BOOTSTRAP_DIR=/absolute/private/path/otm-staging-bootstrap
export TF_DATA_DIR="$OTM_BOOTSTRAP_DIR/provider-data"

terraform -chdir=infra/environments/staging/bootstrap init \
  -input=false -lockfile=readonly \
  -backend-config="path=$OTM_BOOTSTRAP_DIR/bootstrap.tfstate"

terraform -chdir=infra/environments/staging/bootstrap plan \
  -input=false -var-file="$OTM_BOOTSTRAP_DIR/target.tfvars" \
  -out="$OTM_BOOTSTRAP_DIR/bootstrap.tfplan"

terraform -chdir=infra/environments/staging/bootstrap show \
  "$OTM_BOOTSTRAP_DIR/bootstrap.tfplan"
```

1. Inspect the plan locally. Review the exact compartment, private versioned bucket, delivery
   client/trust, IAM and any domain setting within the stated owner. Compute and database are
   outside bootstrap. Require no unexpected deletion or replacement, and verify the account
   independently. Keep raw plan output private.
2. Once approved, apply that **exact saved plan**, without re-planning under different inputs:

   ```sh
   terraform -chdir=infra/environments/staging/bootstrap apply \
     -input=false "$OTM_BOOTSTRAP_DIR/bootstrap.tfplan"
   ```

3. Verify the actual bucket's scope, private access, versioning and encryption in OCI. Securely
   preserve the local bootstrap state and backup. If creation is interrupted, inspect that state
   and OCI before retrying; do not discard state and try a second independent creation.
4. Record only sanitized revision/result evidence in the manifest. Keep identifiers, plans,
   state and credentials private. Remove expired plan files through the approved private-file
   handling process. Production repeats this procedure with its own root, inputs, paths,
   credentials and approval after staging qualification.

## What this does not finish

The bootstrap state's local backend must remain protected. The output key
is `infrastructure/<environment>/terraform.tfstate` for staging and production, and
`custody/development/terraform.tfstate` for development. Keep local bootstrap state separate.
Qualify backend initialization, locks and recovery, and review any prior hosted
[split-state migration](infrastructure-plans.md#one-time-setup-in-each-hosted-environment) before
enabling the composed workflow.

Before using hosted Terraform delivery, qualify remote locking with competing writers, least-privilege
access, version recovery, loss of local bootstrap state, interrupted initialization and state-bucket
deletion protections. Do not use retention locks on mutable state/lock objects. Terraform's
`prevent_destroy` cannot stop privileged direct OCI deletion or resource removal from configuration.

These open cases remain [Pending in the live manifest](real-oci-test-manifest.md#terraform-state-bootstrap).
Do not infer remote-backend or recovery qualification from the mocked tests or bucket creation.
