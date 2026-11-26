# The operator verifies the exact environment, domain and GitHub identifiers before enabling this module.
variable "github_delivery" {
  description = "Immutable GitHub identity, exact OCI domain and rollout settings for staging workload federation."
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
    # Must remain false until shared-domain staging federation is qualified.
    trust_active = optional(bool, false)
  })
  nullable = false
}

module "delivery" {
  source                            = "../../../modules/oci-delivery-foundation"
  allow_runtime_policy_writes       = var.allow_runtime_policy_writes
  environment                       = "staging"
  tenancy_ocid                      = var.target.tenancy_ocid
  identity_domain_ocid              = var.github_delivery.identity_domain_ocid
  trust_active                      = var.github_delivery.trust_active
  exchange_write_response_qualified = var.github_delivery.exchange_write_response_qualified

  # Staging uses the shared Settings owned by development.
  owns_domain_settings = false
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
  description = "Staging GitHub exchange client ID for the protected environment."
  sensitive   = true
  value       = module.delivery.exchange_client_name
}

output "identity_domain_url" {
  description = "Verified staging identity-domain origin for the protected GitHub environment."
  sensitive   = true
  value       = module.delivery.identity_domain_url
}

output "github_exchange_app_id" {
  description = "Exact GitHub exchange App SCIM GUID for the separate operator credential handoff."
  sensitive   = true
  value       = module.delivery.exchange_app_id
}
