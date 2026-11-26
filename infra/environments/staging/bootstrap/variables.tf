# A fixed root rejects a target record labeled for the other environment.
variable "target" {
  description = "Approved staging target references; never include credentials."
  type = object({
    environment              = string
    tenancy_ocid             = string
    object_storage_namespace = string
    region                   = optional(string, "us-ashburn-1")
  })
  validation {
    condition     = var.target.environment == "staging"
    error_message = "This root accepts only the staging environment target record."
  }
}

# Do not silently fall back to a long-lived API signing key or use child/app credentials.
variable "oci_auth" {
  type        = string
  default     = "SecurityToken"
  description = "Authenticated operator SecurityToken, or explicitly qualified resource/instance principal."
  validation {
    condition     = contains(["SecurityToken", "ResourcePrincipal", "InstancePrincipal"], var.oci_auth)
    error_message = "Use SecurityToken, ResourcePrincipal or InstancePrincipal; no APIKey fallback."
  }
}

# The name points to private operator custody; its tokens/keys are not Terraform inputs.
variable "oci_profile" {
  type        = string
  default     = "DEFAULT"
  description = "Nonempty OCI profile name, used only for SecurityToken authentication."
  validation {
    condition     = length(trimspace(var.oci_profile)) > 0 && length(var.oci_profile) <= 128
    error_message = "Provide a nonempty profile name of at most 128 characters."
  }
}

# Pin the existing compartment on adoption. A fresh bootstrap can omit this reference.
variable "hosting_compartment_ocid" {
  description = "Optional expected OCID of the adopted hosting compartment."
  type        = string
  default     = null

  validation {
    condition     = var.hosting_compartment_ocid == null ? true : length(var.hosting_compartment_ocid) <= 255 && can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
    error_message = "Provide the selected environment's existing hosting compartment OCID, at most 255 characters."
  }
}
