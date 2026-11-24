# Separate Vaults organize custody; exact Vault-ID IAM conditions restrict reads in one compartment.
locals {
  domains = toset(["database-provisioning", "application-secrets"])
}
# DEFAULT is the shared Vault tier, not a dedicated virtual-private HSM allocation.
resource "oci_kms_vault" "domain" {
  for_each       = local.domains
  compartment_id = var.hosting_compartment_ocid
  display_name   = "otm-${var.environment}-${each.key}"
  vault_type     = "DEFAULT"
  freeform_tags  = { "otm-environment" = var.environment, "otm-component" = each.key }
  lifecycle { prevent_destroy = true }
}
# One software-protected AES-256 master key per domain. OCI generates the key material; Terraform
# does not export it.
# No secret resource/content or password generation is part of Terraform.
resource "oci_kms_key" "domain" {
  for_each            = local.domains
  compartment_id      = var.hosting_compartment_ocid
  management_endpoint = oci_kms_vault.domain[each.key].management_endpoint
  display_name        = "otm-${var.environment}-${each.key}"
  protection_mode     = "SOFTWARE"
  # Automatic KMS rotation is a private-vault feature; shared-vault keys use owned manual rotation.
  is_auto_rotation_enabled = false
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  freeform_tags = { "otm-environment" = var.environment, "otm-component" = each.key }
  lifecycle { prevent_destroy = true }
}
# Only existing DB provisioning readers gain this narrowly scoped authority. This does not grant
# Terraform deployment, secret writes/deletion, application access or a speculative service principal.
resource "oci_identity_policy" "database_reader" {
  compartment_id = var.hosting_compartment_ocid
  name           = "otm-${var.environment}-database-provisioning-read"
  description    = "Read initial database provisioning secrets only in the designated Vault"
  statements = [
    "Allow group id ${var.database_provisioner_group_ocid} to read secret-family in compartment id ${var.hosting_compartment_ocid} where target.vault.id = '${oci_kms_vault.domain["database-provisioning"].id}'",
    "Allow group id ${var.database_provisioner_group_ocid} to read vaults in compartment id ${var.hosting_compartment_ocid} where target.vault.id = '${oci_kms_vault.domain["database-provisioning"].id}'",
  ]
  freeform_tags = { "otm-environment" = var.environment, "otm-component" = "database-provisioning" }
}
