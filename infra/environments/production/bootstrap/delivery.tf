# The operator verifies the exact environment, domain and GitHub identifiers before enabling this module.
variable "github_delivery" {
  description = "Immutable GitHub identity, exact OCI domain and rollout settings for production workload federation."
  type = object({
    # Root Default domain used for the verified OCI exchange.
    identity_domain_ocid = string
    # Approved owner/repository path used in exact workflow claim checks.
    repository = string
    # Immutable repository ID from GitHub.
    repository_id = string
    # Immutable repository owner ID from GitHub.
    repository_owner_id = string
    # Enable fresh client creation only after verifying credential-free provider write responses.
    exchange_write_response_qualified = optional(bool, false)
    # Keep false until the production exchange and its activation have been approved.
    trust_active = optional(bool, false)
    # Match the domain’s existing CSR setting so signing-key adoption preserves it.
    settings_csr_access = optional(string, "none")
  })
  nullable = false
}

module "delivery" {
  source                            = "../../../modules/oci-delivery-foundation"
  allow_runtime_policy_writes       = var.allow_runtime_policy_writes
  environment                       = "production"
  tenancy_ocid                      = var.target.tenancy_ocid
  identity_domain_ocid              = var.github_delivery.identity_domain_ocid
  trust_active                      = var.github_delivery.trust_active
  exchange_write_response_qualified = var.github_delivery.exchange_write_response_qualified

  # Production owns its separate identity-domain Settings. Import before applying.
  owns_domain_settings = true
  settings_csr_access  = var.github_delivery.settings_csr_access
  github = {
    repository          = var.github_delivery.repository
    repository_id       = var.github_delivery.repository_id
    repository_owner_id = var.github_delivery.repository_owner_id
  }
  storage_policy = {
    compartment_ocid = oci_identity_compartment.hosting.id
    bucket_name      = nonsensitive(module.state.state_backend.bucket)
    state_key        = nonsensitive(module.state.state_backend.key)
  }
}

output "github_exchange_client_id" {
  description = "Production GitHub exchange client ID for the protected environment."
  sensitive   = true
  value       = module.delivery.exchange_client_name
}

output "identity_domain_url" {
  description = "Verified production identity-domain origin for the protected GitHub environment."
  sensitive   = true
  value       = module.delivery.identity_domain_url
}

output "github_exchange_app_id" {
  description = "Exact GitHub exchange App SCIM GUID for the separate operator credential handoff."
  sensitive   = true
  value       = module.delivery.exchange_app_id
}

# Settings already exists in every identity domain. Adopt the singleton before
# planning changes so the provider cannot take its create-via-ReplaceSettings path.
import {
  to = module.delivery.oci_identity_domains_setting.signing_keys[0]
  id = "idcsEndpoint/${nonsensitive(module.delivery.identity_domain_url)}/settings/Settings"
}
