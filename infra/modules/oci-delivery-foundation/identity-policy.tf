# Approve this only after reviewing the full reach of OCI's domain management permission.
variable "identity_app_management_environments" {
  description = "Environments whose protected workflows may manage this shared identity domain. Includes access beyond the Atlas application."
  type        = set(string)
  default     = []
  nullable    = false

  validation {
    condition     = length(setsubtract(var.identity_app_management_environments, toset(local.identity_policy_environments))) == 0
    error_message = "Only the bootstrap owner can enable domain management for an environment in that domain."
  }
}

# Only existing development adoption adds a native group-OCID read.
variable "development_group_adoption_ocid" {
  description = "Operator-verified native OCID of the adopted development Atlas group."
  type        = string
  default     = null

  validation {
    condition = var.development_group_adoption_ocid == null ? true : (
      var.environment == "development" &&
      can(regex("^ocid1[.]group[.]oc1[.][.][a-z0-9]{1,220}$", var.development_group_adoption_ocid))
    )
    error_message = "The native group read pin is only for an existing development group adoption."
  }
}

# The named workflow principal is an explicit opt-in for development group and role ownership.
variable "development_workflow_dynamic_group" {
  description = "Exact approved exchanged development principal and optional existing group and role-grant SCIM GUIDs for migration."
  type = object({
    # Exact exchanged principal bound by the group's single resource.id matching rule.
    principal_ocid = string
    # A fresh creation must be deliberate. Omitted or obsolete import inputs must fail closed.
    create_fresh = optional(bool, false)
    # Supply both immutable SCIM GUIDs for an existing named subject and role assignment.
    existing = optional(object({
      # Lowercase 32-hex SCIM GUID of the exact dynamic-group policy subject.
      group_id = string
      # Lowercase 32-hex SCIM GUID of the existing Application Administrator assignment.
      grant_id = string
    }))
  })
  default = null

  validation {
    condition = var.development_workflow_dynamic_group == null ? true : (
      var.environment == "development" &&
      can(regex("^ocid1[.]identityfederateddomainapp[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", var.development_workflow_dynamic_group.principal_ocid)) &&
      var.development_workflow_dynamic_group.create_fresh == (var.development_workflow_dynamic_group.existing == null) &&
      (var.development_workflow_dynamic_group.existing == null ? true :
        can(regex("^[0-9a-f]{32}$", var.development_workflow_dynamic_group.existing.group_id)) &&
        can(regex("^[0-9a-f]{32}$", var.development_workflow_dynamic_group.existing.grant_id))
      )
    )
    error_message = "Only development may opt in with an exact exchanged principal OCID and either both adoption GUIDs or explicit fresh creation."
  }
}

locals {
  workflow_refs = {
    for environment in ["development", "staging", "production"] :
    environment => "${var.github.repository}/.github/workflows/infra-${environment}.yml@refs/heads/master"
  }
  named_workflow = {
    for environment in keys(local.workflow_refs) :
    environment => environment == "development" && var.development_workflow_dynamic_group != null
  }
  workflow_grantees = {
    for environment, named in local.named_workflow :
    environment => named ? "dynamic-group ${local.identity_domain_name}/${oci_identity_dynamic_group.development_workflow[0].name}" : "any-user"
  }
  # Retain the proven exchanged-principal domain claim unless the verified group identifies it.
  workflow_subjects = {
    for environment, workflow_ref in local.workflow_refs :
    environment => join(", ", concat(
      ["request.principal.type = 'identityfederateddomainapp'"],
      local.named_workflow[environment] ? [] : ["request.principal.domain.id = '${var.identity_domain_ocid}'"],
      [
        "request.principal.ext_workflow_ref = '${workflow_ref}'",
        "request.principal.ext_environment = '${environment}'",
      ],
    ))
  }
  workflow_ref     = local.workflow_refs[var.environment]
  workflow_grantee = local.workflow_grantees[var.environment]
  workflow_subject = local.workflow_subjects[var.environment]

  # Development and staging share a domain. Production has its own domain and root policy.
  identity_policy_environments = (
    var.environment == "development" ? ["development", "staging"] :
    var.environment == "production" ? ["production"] : []
  )

  # Native CreateGroup and GetGroup support target.group.name. A collection read does not.
  group_targets = {
    for environment in local.identity_policy_environments :
    environment => (
      environment == "development" ? "target.group.name = 'otm-development-users'" :
      "any {target.group.name = 'otm-${environment}-users', target.group.name = 'otm-${environment}-database-provisioners'}"
    )
  }

  group_list_condition = "target.resource.domain.name = '${local.identity_domain_name}', request.operation = 'ListGroups'"
  # The adoption GetGroup request did not authorize with domain and group names alone.
  group_inspect_targets = {
    for environment in local.identity_policy_environments :
    environment => (
      environment == "development" && var.development_group_adoption_ocid != null ?
      "any {all {${local.group_list_condition}}, all {target.group.name = 'otm-development-users', target.group.id = '${var.development_group_adoption_ocid}', request.operation = 'GetGroup'}}" :
      local.group_list_condition
    )
  }
}

# The domain owner's bootstrap attaches the sole native identity policy to the tenancy root.
# Each statement pairs one workflow with only its environment's group names.
resource "oci_identity_policy" "github_identity" {
  count          = length(local.identity_policy_environments) == 0 ? 0 : 1
  compartment_id = var.tenancy_ocid
  name           = "otm-github-identity"
  description    = "Manage environment groups and provide optional domain administration for integrated applications"
  statements = concat(
    flatten([
      for environment in local.identity_policy_environments : [
        "Allow ${local.workflow_grantees[environment]} to manage groups in tenancy where all {${local.workflow_subjects[environment]}, target.resource.domain.name = '${local.identity_domain_name}', ${local.group_targets[environment]}, any {request.operation = 'CreateGroup', request.operation = 'GetGroup', request.operation = 'UpdateGroup'}}",
        "Allow ${local.workflow_grantees[environment]} to inspect groups in tenancy where all {${local.workflow_subjects[environment]}, ${local.group_inspect_targets[environment]}}",
      ]
    ]),
    [
      # Oracle documents domain management for App administration. This also authorizes other
      # operations in the selected domain. CreateDomain has no target domain ID.
      for environment in local.identity_policy_environments :
      "Allow ${local.workflow_grantees[environment]} to manage domains in tenancy where all {${local.workflow_subjects[environment]}, target.domain.name = '${local.identity_domain_name}', target.domain.id = '${var.identity_domain_ocid}'}"
      if contains(var.identity_app_management_environments, environment)
    ]
  )
  depends_on = [data.oci_identity_domain.selected]

  lifecycle { prevent_destroy = true }
}

output "workflow_policy_authorization" {
  description = "The matched OCI grantee and exact workflow conditions for the environment compartment policy."
  value = {
    grantee    = local.workflow_grantee
    conditions = local.workflow_subject
  }
}
