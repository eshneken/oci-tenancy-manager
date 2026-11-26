# Use the environment as the audience and release-workflow namespace.
variable "environment" {
  description = "Fixed Atlas environment label for the checked-out workflow."
  type        = string
  nullable    = false

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Select development, staging, or production."
  }
}

# Keep the OCI principal's tenancy independent of user-supplied domain metadata.
variable "tenancy_ocid" {
  description = "Approved tenancy containing the hosting compartment and identity domain."
  type        = string
  nullable    = false
}

variable "identity_domain_ocid" {
  description = "Exact environment identity domain OCID used by the workload principal."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ocid1[.]domain[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", var.identity_domain_ocid))
    error_message = "Supply the verified OCI identity-domain OCID."
  }
}

# Numeric IDs establish ownership across repository renames. The path scopes the actual workflow.
variable "github" {
  description = "Approved GitHub owner/repository and immutable repository and owner IDs."
  type = object({
    repository          = string
    repository_id       = string
    repository_owner_id = string
  })
  nullable = false

  validation {
    condition = (
      can(regex("^[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}$", var.github.repository)) &&
      can(regex("^[1-9][0-9]{0,19}$", var.github.repository_id)) &&
      can(regex("^[1-9][0-9]{0,19}$", var.github.repository_owner_id))
    )
    error_message = "Provide the exact GitHub repository path and its positive numeric repository and owner IDs."
  }
}

variable "trust_active" {
  description = "Enable the exchange trust and any inline client only after a separately reviewed rollout."
  type        = bool
  default     = false
  nullable    = false

  validation {
    condition     = var.environment != "staging" || !var.trust_active
    error_message = "Staging GitHub exchange is blocked until OCI can bind its client and assertion independently of development."
  }

}

variable "owns_domain_settings" {
  description = "Whether this operator bootstrap owns the verified domain Settings singleton."
  type        = bool
  default     = false
  nullable    = false

  validation {
    condition     = !var.owns_domain_settings || var.environment != "staging"
    error_message = "Staging shares the non-production domain Settings owned by development."
  }
}

# This field is required by the provider even though signing key publication is independent.
variable "settings_csr_access" {
  description = "Current Settings csrAccess value to preserve during adoption."
  type        = string
  default     = "none"
  nullable    = false
}

variable "storage_policy" {
  description = "Optional exact hosting compartment and bucket for workflow state and plan artifact IAM."
  type = object({
    compartment_ocid = string
    bucket_name      = string
    state_key        = string
  })
  default = null

  validation {
    condition = var.storage_policy == null ? true : (
      can(regex("^ocid1[.]compartment[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", var.storage_policy.compartment_ocid)) &&
      var.storage_policy.bucket_name == "otm-${var.environment}-tfstate" &&
      var.storage_policy.state_key == "${var.environment == "development" ? "custody" : "infrastructure"}/${var.environment}/terraform.tfstate"
    )
    error_message = "Workflow IAM requires the selected environment's exact compartment, state bucket, and state key."
  }
}

# Only a verified legacy development binding bypasses the native App resource. Import reads an
# unprojected default response in the released provider and can put a client secret into state.
variable "existing_exchange" {
  type    = object({ id = string, name = string })
  default = null
  validation {
    condition = var.existing_exchange == null ? true : (
      var.environment == "development" && var.trust_active &&
      can(regex("^[0-9a-f]{32}$", var.existing_exchange.id)) &&
      length(var.existing_exchange.name) > 0
    )
    error_message = "The existing exchange app requires a verified active development binding."
  }
}

# Prove that this released provider omits both secret and hash on create/update before native writes.
variable "exchange_write_response_qualified" {
  type     = bool
  default  = false
  nullable = false
  validation {
    condition     = var.existing_exchange != null || var.exchange_write_response_qualified
    error_message = "New exchange clients require a separately verified secret-free OCI write response."
  }
}
