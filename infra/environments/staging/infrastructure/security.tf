# This environment owns its database provisioning group; no external group handoff.
resource "oci_identity_group" "database_provisioners" {
  compartment_id = var.target.tenancy_ocid
  name           = "otm-${var.target.environment}-database-provisioners"
  description    = "Read initial database provisioning secrets for OCI Tenancy Manager."
  lifecycle { prevent_destroy = true }
}

module "secrets" {
  source                          = "../../../modules/secret-foundation"
  environment                     = "staging"
  hosting_compartment_ocid        = var.hosting_compartment_ocid
  database_provisioner_group_name = oci_identity_group.database_provisioners.name
  depends_on                      = [data.oci_objectstorage_namespace.target]
}
# No secret content is exposed or shared through Terraform remote-state reads.
output "custody" {
  value       = module.secrets.custody
  sensitive   = true
  description = "Private environment-bound compartment/Vault/key references used by the environment infrastructure."
}

# Vault generates the initial password internally. Terraform receives only secret metadata.
resource "oci_vault_secret" "database_admin" {
  compartment_id         = var.hosting_compartment_ocid
  secret_name            = "otm-${var.target.environment}-database-admin"
  vault_id               = module.secrets.custody.domains["database-provisioning"].vault_ocid
  key_id                 = module.secrets.custody.domains["database-provisioning"].key_ocid
  enable_auto_generation = true
  secret_generation_context {
    generation_type     = "PASSPHRASE"
    generation_template = "DBAAS_DEFAULT_PASSWORD"
    passphrase_length   = 30
  }
  lifecycle { prevent_destroy = true }
}
