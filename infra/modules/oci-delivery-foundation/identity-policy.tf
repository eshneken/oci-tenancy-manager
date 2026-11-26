# Domain resources reside at the tenancy root. An environment compartment policy cannot grant
# access above its attachment. The principal is the exchanged resource, not a named user group.
locals {
  workflow_subject = "request.principal.type = 'identityfederateddomainapp', request.principal.domain.id = '${var.identity_domain_ocid}', request.principal.ext_workflow_ref = '${local.workflow_ref}', request.principal.ext_environment = '${var.environment}'"
  group_names = concat(
    ["otm-${var.environment}-users"],
    var.environment == "development" ? [] : ["otm-${var.environment}-database-provisioners"]
  )
  # Native CreateGroup and GetGroup support target.group.name. A collection read does not.
  named_groups = [for name in local.group_names : "target.group.name = '${name}'"]
  group_target = length(local.named_groups) == 1 ? one(local.named_groups) : "any {${join(", ", local.named_groups)}}"
}

resource "oci_identity_policy" "github_identity" {
  compartment_id = var.tenancy_ocid
  name           = "otm-${var.environment}-github-identity"
  description    = "Manage environment-owned identity groups from the protected infrastructure workflow"
  statements = [
    "Allow any-user to manage groups in tenancy where all {${local.workflow_subject}, target.resource.domain.name = 'Default', ${local.group_target}, any {request.operation = 'CreateGroup', request.operation = 'GetGroup', request.operation = 'UpdateGroup'}}",
    "Allow any-user to inspect groups in tenancy where all {${local.workflow_subject}, target.resource.domain.name = 'Default', request.operation = 'ListGroups'}",
  ]
  lifecycle { prevent_destroy = true }
}
