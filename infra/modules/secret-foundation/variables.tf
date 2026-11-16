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
# Existing privileged credential-reader group, verified in this environment's tenancy by the operator.
# This grants database administrator secret reads, not secret ingestion/rotation or application access.
variable "database_provisioner_group_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]group[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.database_provisioner_group_ocid))
    error_message = "Provide an approved existing OCI group OCID; policy text/names are not accepted."
  }
}
