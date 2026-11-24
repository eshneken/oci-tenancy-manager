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

# Named ~/.oci/config profile used by the local Terraform operator; no browser authentication.
variable "oci_profile" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", var.oci_profile)) && lower(var.oci_profile) != "default"
    error_message = "Select an explicit named development API-key profile, never DEFAULT."
  }
}

# Operator-supplied OCID for the existing top-level development compartment.
# Syntax does not establish tenancy ownership or permission; independently verify both before apply.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = length(var.hosting_compartment_ocid) <= 255 && can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
    error_message = "Provide the selected environment's existing hosting compartment OCID, at most 255 characters."
  }
}
