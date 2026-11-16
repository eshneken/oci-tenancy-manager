# Named ~/.oci/config profile used by the local Terraform operator; no browser authentication.
variable "oci_profile" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", var.oci_profile)) && lower(var.oci_profile) != "default"
    error_message = "Select an explicit named development API-key profile, never DEFAULT."
  }
}
# Existing non-production platform tenancy; staging may share this parent but not this state/Vault.
variable "tenancy_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]tenancy[.]oc[0-9]+[.][a-z0-9.-]{1,220}$", var.tenancy_ocid))
    error_message = "Provide the intended non-production tenancy OCID."
  }
}
# Existing development compartment, a sibling of staging; do not install into staging's compartment.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]compartment[.]oc[0-9]+[.][a-z0-9.-]{1,220}$", var.hosting_compartment_ocid))
    error_message = "Provide the existing development compartment OCID."
  }
}
# Full region name, explicit to avoid a default-location lookup or wrong-region Vault creation.
variable "region" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,61}[0-9]$", var.region))
    error_message = "Provide an OCI region name."
  }
}
