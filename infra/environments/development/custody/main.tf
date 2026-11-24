# Custody uses the approved non-production binding and CI's ephemeral identity.
provider "oci" {
  auth         = var.oci_auth
  region       = var.target.region
  tenancy_ocid = var.target.tenancy_ocid
}

# Laptop PostgreSQL needs no managed-DB provisioning Vault, OKE, network or second cloud database.
# Use hyphenated free-form tag keys because OCI rejects periods and spaces.
resource "oci_kms_vault" "application" {
  compartment_id = var.hosting_compartment_ocid
  display_name   = "otm-development-application-secrets"
  vault_type     = "DEFAULT"
  freeform_tags  = { "otm-environment" = "development", "otm-component" = "application-secrets" }
  lifecycle { prevent_destroy = true }
}

# Retain the enrolled HSM key at its existing address until the software key is verified and
# the operator retires it. OCI cannot change an existing key's protection mode.
resource "oci_kms_key" "application" {
  compartment_id           = var.hosting_compartment_ocid
  management_endpoint      = oci_kms_vault.application.management_endpoint
  display_name             = "otm-development-application-secrets"
  protection_mode          = "HSM"
  is_auto_rotation_enabled = false
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  freeform_tags = { "otm-environment" = "development", "otm-component" = "application-secrets" }
  lifecycle { prevent_destroy = true }
}

# New application secrets use the software-protected AES-256 key in the existing Vault.
resource "oci_kms_key" "application_software" {
  compartment_id           = var.hosting_compartment_ocid
  management_endpoint      = oci_kms_vault.application.management_endpoint
  display_name             = "otm-development-application-secrets-software"
  protection_mode          = "SOFTWARE"
  is_auto_rotation_enabled = false
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  freeform_tags = { "otm-environment" = "development", "otm-component" = "application-secrets" }
  lifecycle { prevent_destroy = true }
}

# Reference output is private deployment metadata, not a credential or a staging handoff.
output "custody" {
  sensitive = true
  value = {
    environment      = "development"
    compartment_ocid = var.hosting_compartment_ocid
    vault_ocid       = oci_kms_vault.application.id
    key_ocid         = oci_kms_key.application_software.id
  }
}
