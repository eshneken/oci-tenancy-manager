# A fixed root rejects a target record labeled for the other environment.
variable "target" {
  description = "Approved development target references; never include credentials."
  type = object({
    # Fixed environment label for this root.
    environment = string
    # Non-production root tenancy expected by the operator or federated identity.
    tenancy_ocid = string
    # Object Storage namespace checked against the tenancy during bootstrap.
    object_storage_namespace = string
    # Explicit OCI region for resources and their state bucket.
    region = string
  })
  validation {
    condition     = var.target.environment == "development"
    error_message = "This root accepts only the development environment target record."
  }
}

# CI receives an ephemeral resource principal for both the provider and state backend.
variable "oci_auth" {
  type = string
  validation {
    condition     = var.oci_auth == "ResourcePrincipal"
    error_message = "Development custody CI requires ResourcePrincipal."
  }
}

# Required OTM_HOSTING_COMPARTMENT_OCID from this environment; one existing compartment, no children.
# Syntax does not establish tenancy ownership or permission; independently verify both before apply.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = length(var.hosting_compartment_ocid) <= 255 && can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
    error_message = "Provide the selected environment's existing hosting compartment OCID, at most 255 characters."
  }
}
