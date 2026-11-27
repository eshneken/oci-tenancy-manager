# Preserve the active development exchange client while qualifying future Terraform creation.
variable "github_delivery" {
  description = "Immutable GitHub identity and rollout settings for development workload federation."
  type = object({
    # Immutable repository ID from GitHub.
    repository_id = string
    # Immutable repository owner ID from GitHub.
    repository_owner_id = string
    # Enable fresh client creation only after verifying credential-free provider write responses.
    exchange_write_response_qualified = optional(bool, false)
    # Set the existing development client GUID for a metadata-only reference.
    existing_exchange_app_id = optional(string)
    # Pin the verified active trust for a no-op import alongside the existing client reference.
    existing_trust_id = optional(string)
    # Keep true for the existing active development trust during adoption.
    trust_active = bool
    # Match the domain’s existing CSR setting so signing-key adoption preserves it.
    settings_csr_access = optional(string, "none")
  })
  nullable = false
  validation {
    condition = var.github_delivery.existing_exchange_app_id == null ? (
      var.github_delivery.exchange_write_response_qualified && var.github_delivery.existing_trust_id == null
      ) : (
      can(regex("^[0-9a-f]{32}$", var.github_delivery.existing_exchange_app_id)) &&
      can(regex("^[0-9a-f]{32}$", var.github_delivery.existing_trust_id)) &&
      var.github_delivery.trust_active && !var.github_delivery.exchange_write_response_qualified
    )
    error_message = "Select the active existing development App by exact SCIM GUID, or explicitly qualify a fresh client's OCI write responses."
  }
}

# Optional domain-wide App administration. Set only for independently approved workflow environments.
variable "identity_app_management_environments" {
  description = "Protected environments authorized to manage their shared identity domain for application provisioning."
  type        = set(string)
  default     = []
  nullable    = false
}

# Opt in only after independently verifying the exact development workflow principal.
variable "github_workflow_dynamic_group" {
  description = "Approved development workflow principal for the named dynamic group and its Application Administrator role. Include both existing GUIDs to adopt."
  type = object({
    # Immutable development principal matched by the group's only rule.
    principal_ocid = string
    # Create a new group and role grant only when neither already exists.
    create_fresh = optional(bool, false)
    # Supply both SCIM IDs when the bootstrap must adopt the existing group and grant.
    existing = optional(object({
      # Lowercase 32-hex SCIM GUID of the verified Default-domain dynamic group.
      group_id = string
      # Lowercase 32-hex SCIM GUID of that group's Application Administrator grant.
      grant_id = string
    }))
  })
  default = null
}

# Adopt the two exact existing bindings before considering any managed-resource change.
import {
  for_each = try(var.github_workflow_dynamic_group.existing == null, true) ? {} : { development = var.github_workflow_dynamic_group.existing }
  to       = module.delivery.oci_identity_dynamic_group.development_workflow[0]
  id       = module.delivery.development_workflow_adoption_group_ocid
}

import {
  for_each = try(var.github_workflow_dynamic_group.existing == null, true) ? {} : { development = var.github_workflow_dynamic_group.existing }
  to       = module.delivery.oci_identity_domains_grant.development_application_administrator[0]
  id       = "idcsEndpoint/${nonsensitive(module.delivery.identity_domain_url)}/grants/${each.value.grant_id}"
}

module "delivery" {
  source                               = "../../../modules/oci-delivery-foundation"
  environment                          = "development"
  tenancy_ocid                         = var.target.tenancy_ocid
  development_group_adoption_ocid      = one(data.oci_identity_group.group_adoption[*].id)
  development_workflow_dynamic_group   = var.github_workflow_dynamic_group
  identity_app_management_environments = var.identity_app_management_environments
  identity_domain_ocid                 = var.github_identity_domain_ocid
  trust_active                         = var.github_delivery.trust_active
  exchange_write_response_qualified    = var.github_delivery.exchange_write_response_qualified

  existing_exchange = var.github_delivery.existing_exchange_app_id == null ? null : {
    id   = var.github_delivery.existing_exchange_app_id
    name = data.external.exchange_metadata[0].result["name"]
  }

  # Development owns the shared non-production Settings. Import before applying.
  owns_domain_settings = true
  settings_csr_access  = var.github_delivery.settings_csr_access
  github = {
    repository          = var.github_repository
    repository_id       = var.github_delivery.repository_id
    repository_owner_id = var.github_delivery.repository_owner_id
  }
}

output "github_exchange_client_id" {
  description = "Development GitHub exchange client ID for the protected environment."
  sensitive   = true
  value       = module.delivery.exchange_client_name
}

output "identity_domain_url" {
  description = "Verified development identity-domain origin for the protected GitHub environment."
  sensitive   = true
  value       = module.delivery.identity_domain_url
}

output "github_exchange_app_id" {
  description = "Exact GitHub exchange App SCIM GUID for the separate operator credential handoff."
  sensitive   = true
  value       = module.delivery.exchange_app_id
}

# Import the deployed issuer trust by immutable ID before evaluating any resource update.
import {
  for_each = var.github_delivery.existing_trust_id == null ? {} : { development = var.github_delivery.existing_trust_id }
  to       = module.delivery.oci_identity_domains_identity_propagation_trust.github[0]
  id       = "idcsEndpoint/${nonsensitive(module.delivery.identity_domain_url)}/identityPropagationTrusts/${each.value}"
}

# Settings already exists in every identity domain. Adopt the singleton before
# planning changes so the provider cannot take its create-via-ReplaceSettings path.
import {
  to = module.delivery.oci_identity_domains_setting.signing_keys[0]
  id = "idcsEndpoint/${nonsensitive(module.delivery.identity_domain_url)}/settings/Settings"
}


# Read only explicitly projected metadata. OCI provider import performs an unprojected first
# GetApp; retaining the already-working identity avoids any exposure or resource replacement.
data "external" "exchange_metadata" {
  count = var.github_delivery.existing_exchange_app_id == null ? 0 : 1
  program = ["uv", "run", "--locked", "--project", "${path.module}/../../../modules/github-environment", "python", "-I",
  "${path.module}/../../../modules/github-environment/seal_inputs.py", "--development-exchange-metadata"]
  query = {
    environment = "development"
    domain_url  = module.delivery.identity_domain_url
    app_id      = var.github_delivery.existing_exchange_app_id
    oci_profile = var.oci_profile
    oci_auth    = "APIKey"
  }
}


# Keep the policy and workflow adoption pins aligned through the same owner-only settings file.
data "external" "group_adoption_pin" {
  program = ["uv", "run", "--locked", "--project", "${path.module}/../../../modules/github-environment", "python", "-I",
  "${path.module}/../../../modules/github-environment/seal_inputs.py", "--development-group-adoption-pin"]
  query = { settings_file = var.github_environment.settings_file }
}

# The native IAM read resolves one Default-domain group without returning membership.
data "oci_identity_group" "group_adoption" {
  count    = data.external.group_adoption_pin.result["ocid"] == "" ? 0 : 1
  group_id = data.external.group_adoption_pin.result["ocid"]

  lifecycle {
    postcondition {
      condition = (
        self.id == data.external.group_adoption_pin.result["ocid"] &&
        self.name == "otm-development-users" &&
        self.compartment_id == var.target.tenancy_ocid &&
        self.state == "ACTIVE"
      )
      error_message = "Expected the active native development Atlas group in the selected tenancy."
    }
  }
}
