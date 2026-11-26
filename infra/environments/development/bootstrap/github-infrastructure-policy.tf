# OCI maps exchanged tokens to identityfederateddomainapp principals. The trust must propagate
# workflow_ref and environment so IAM can bind every grant to the development workflow.
locals {
  github_workflow_ref         = "${var.github_repository}/.github/workflows/infra-development.yml@refs/heads/master"
  github_infrastructure_scope = "in compartment ${oci_identity_compartment.development.name} where all {request.principal.type = 'identityfederateddomainapp', request.principal.domain.id = '${var.github_identity_domain_ocid}', request.principal.ext_workflow_ref = '${local.github_workflow_ref}', request.principal.ext_environment = 'development'"
  github_state_bucket         = "target.bucket.name = 'otm-development-tfstate'"
  github_state_object         = "target.object.name = 'custody/development/terraform.tfstate'"
  github_lock_object          = "target.object.name = 'custody/development/terraform.tfstate.lock'"
  # Match the custody prefix and a permitted suffix. Exclude artifacts beside the run directories.
  github_plan_root     = "infrastructure-plans/development/custody"
  github_plan_prefix   = "target.object.name = '${local.github_plan_root}/*', target.object.name != '${local.github_plan_root}/plan.tar', target.object.name != '${local.github_plan_root}/apply-attempt.json', target.object.name != '${local.github_plan_root}/errored.tfstate'"
  github_plan_archive  = "target.object.name = '*/plan.tar'"
  github_plan_recovery = "any {target.object.name = '*/apply-attempt.json', target.object.name = '*/errored.tfstate'}"
}

# The operator bootstrap owns CI permissions. The workflow has no IAM administration authority.
resource "oci_identity_policy" "github_infrastructure" {
  compartment_id = oci_identity_compartment.development.id
  # OCI policy names are immutable. Keep this name aligned with the live bootstrap policy.
  name        = "otm-development-github-infrastructure"
  description = "Development Vault, key, state and reviewed plan access for GitHub Actions"
  statements = [
    "Allow any-user to read vaults ${local.github_infrastructure_scope}}",
    "Allow any-user to read keys ${local.github_infrastructure_scope}}",
    "Allow any-user to read buckets ${local.github_infrastructure_scope}, ${local.github_state_bucket}, request.operation = 'GetBucket'}",
    "Allow any-user to inspect objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, request.operation = 'ListObjects'}",
    "Allow any-user to read objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, ${local.github_state_object}, any {request.operation = 'HeadObject', request.operation = 'GetObject'}}",
    # Only the exact lock object can be deleted. Archive writes are create-only, and
    # Actions uses a conditional write to its run-specific path.
    "Allow any-user to manage objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, ${local.github_lock_object}, any {all {request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'}, all {request.operation = 'GetObject', request.permission = 'OBJECT_READ'}, all {request.operation = 'DeleteObject', request.permission = 'OBJECT_DELETE'}}}",
    "Allow any-user to manage objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, ${local.github_plan_prefix}, ${local.github_plan_archive}, request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'}",
    # Initial apply can create a Vault and key without any permission to use or delete the key.
    "Allow any-user to manage vaults ${local.github_infrastructure_scope}, request.operation = 'CreateVault', request.permission = 'VAULT_CREATE'}",
    "Allow any-user to use vaults ${local.github_infrastructure_scope}, request.operation = 'CreateKey', request.permission = 'VAULT_CREATE_KEY'}",
    "Allow any-user to manage keys ${local.github_infrastructure_scope}, request.operation = 'CreateKey', request.permission = 'KEY_CREATE'}",
    "Allow any-user to manage objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, ${local.github_state_object}, request.operation = 'PutObject', any {request.permission = 'OBJECT_CREATE', request.permission = 'OBJECT_OVERWRITE'}}",
    "Allow any-user to read objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, ${local.github_plan_prefix}, ${local.github_plan_archive}, request.operation = 'GetObject', request.permission = 'OBJECT_READ'}",
    "Allow any-user to manage objects ${local.github_infrastructure_scope}, ${local.github_state_bucket}, ${local.github_plan_prefix}, ${local.github_plan_recovery}, request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'}",
  ]

  lifecycle {
    prevent_destroy = true
  }
}
