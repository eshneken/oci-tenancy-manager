locals {
  # Bind the OCI authorization path to the same verified workflow and identity-domain claims.
  storage_scope = var.storage_policy == null ? null : join(", ", [
    "in compartment otm-${var.environment} where all {request.principal.type = 'identityfederateddomainapp'",
    "request.principal.domain.id = '${var.identity_domain_ocid}'",
    "request.principal.ext_workflow_ref = '${local.workflow_ref}'",
    "request.principal.ext_environment = '${var.environment}'",
    "target.bucket.name = '${var.storage_policy.bucket_name}'",
  ])
  state_object = var.storage_policy == null ? null : "target.object.name = '${var.storage_policy.state_key}'"
  lock_object  = var.storage_policy == null ? null : "target.object.name = '${var.storage_policy.state_key}.lock'"
  plan_root    = "infrastructure-plans/${var.environment}/infrastructure"
  plan_prefix  = "target.object.name = '${local.plan_root}/*', target.object.name != '${local.plan_root}/plan.tar', target.object.name != '${local.plan_root}/apply-attempt.json', target.object.name != '${local.plan_root}/errored.tfstate'"
  plan_archive = "target.object.name = '*/plan.tar'"
  recovery     = "any {target.object.name = '*/apply-attempt.json', target.object.name = '*/errored.tfstate'}"
}

# Hosted workflow storage is qualified separately from resource management in the target.
resource "oci_identity_policy" "workflow_storage" {
  count          = var.storage_policy == null ? 0 : 1
  compartment_id = var.storage_policy.compartment_ocid
  name           = "otm-${var.environment}-github-infrastructure"
  description    = "Terraform state and reviewed plan storage for the infrastructure workflow"
  statements = [
    "Allow any-user to read buckets ${local.storage_scope}, request.operation = 'GetBucket'}",
    "Allow any-user to inspect objects ${local.storage_scope}, request.operation = 'ListObjects'}",
    "Allow any-user to read objects ${local.storage_scope}, ${local.state_object}, any {request.operation = 'HeadObject', request.operation = 'GetObject'}}",
    "Allow any-user to manage objects ${local.storage_scope}, ${local.state_object}, request.operation = 'PutObject', any {request.permission = 'OBJECT_CREATE', request.permission = 'OBJECT_OVERWRITE'}}",
    "Allow any-user to manage objects ${local.storage_scope}, ${local.lock_object}, any {all {request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'}, all {request.operation = 'GetObject', request.permission = 'OBJECT_READ'}, all {request.operation = 'DeleteObject', request.permission = 'OBJECT_DELETE'}}}",
    "Allow any-user to manage objects ${local.storage_scope}, ${local.plan_prefix}, ${local.plan_archive}, request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'}",
    "Allow any-user to read objects ${local.storage_scope}, ${local.plan_prefix}, ${local.plan_archive}, request.operation = 'GetObject', request.permission = 'OBJECT_READ'}",
    "Allow any-user to manage objects ${local.storage_scope}, ${local.plan_prefix}, ${local.recovery}, request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'}",
  ]

  lifecycle {
    prevent_destroy = true
  }
}
