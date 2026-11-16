# Provider identity is explicit and separate from backend authentication and app credentials.
provider "oci" {
  auth                = var.oci_auth
  region              = var.target.region
  tenancy_ocid        = var.target.tenancy_ocid
  config_file_profile = var.oci_auth == "SecurityToken" ? var.oci_profile : null
}

# As in bootstrap, namespace agreement is a sanity check, not principal/compartment authorization.
data "oci_objectstorage_namespace" "target" {
  compartment_id = var.target.tenancy_ocid
  lifecycle {
    postcondition {
      condition     = self.namespace == var.target.object_storage_namespace
      error_message = "The live namespace does not match this environment's approved target."
    }
  }
}

module "secrets" {
  source                          = "../../../modules/secret-foundation"
  environment                     = "staging"
  hosting_compartment_ocid        = var.hosting_compartment_ocid
  database_provisioner_group_ocid = var.database_provisioner_group_ocid
  depends_on                      = [data.oci_objectstorage_namespace.target]
}
# No secret content is exposed or shared through Terraform remote-state reads.
output "custody" {
  value       = module.secrets.custody
  sensitive   = true
  description = "Private environment-bound compartment/Vault/key references for separately approved ingestion."
}
