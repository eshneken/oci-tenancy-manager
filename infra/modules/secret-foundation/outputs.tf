# Private resource references only; operators ingest credentials separately and record exact versions.
output "custody" {
  sensitive   = true
  description = "Environment-bound Vault/key/compartment references; no secret values or effective-IAM guarantee."
  value = {
    environment = var.environment
    domains = { for domain in local.domains : domain => {
      compartment_ocid = var.hosting_compartment_ocid
      vault_ocid       = oci_kms_vault.domain[domain].id
      key_ocid         = oci_kms_key.domain[domain].id
    } }
    database_reader_policy_ocid = oci_identity_policy.database_reader.id
  }
}
