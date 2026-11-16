# Only hosted release environments use workload identity; laptop development uses an API key.
variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Select staging or production."
  }
}
# Existing hosting compartment; the exact Vault condition further bounds inherited IAM scope.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]compartment[.]oc[0-9]+[.][a-z0-9.-]{1,220}$", var.hosting_compartment_ocid))
    error_message = "Provide the existing hosting compartment OCID."
  }
}
# Exact Enhanced OKE cluster identity; token claims and IAM enforcement still require qualification.
variable "cluster_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]cluster[.]oc[0-9]+[.][a-z0-9.-]{1,220}$", var.cluster_ocid))
    error_message = "Provide this environment's OKE cluster OCID."
  }
}
# Exact application Vault from the security-root handoff, not the DB-provisioning Vault.
variable "application_vault_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]vault[.]oc[0-9]+[.][a-z0-9.-]{1,220}$", var.application_vault_ocid))
    error_message = "Provide the application Vault OCID."
  }
}
