# Fixed environment label is a composition check, not proof of the authenticated principal's tenancy.
variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Use staging or production."
  }
}
# All Vaults, keys and policies stay in the existing application hosting compartment; no children.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
    error_message = "Provide the existing hosting compartment OCID."
  }
}
# Canonical group owned in this environment's Default domain. Exact equality fences policy text.
variable "database_provisioner_group_name" {
  type = string
  validation {
    condition     = var.database_provisioner_group_name == "otm-${var.environment}-database-provisioners"
    error_message = "Supply this environment's managed database provisioner group name."
  }
}
