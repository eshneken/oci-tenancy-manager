# Bind auth and scope explicitly; the namespace read is not proof of principal isolation.
provider "oci" {
  auth                = var.oci_auth
  region              = var.target.region
  tenancy_ocid        = var.target.tenancy_ocid
  config_file_profile = var.oci_auth == "SecurityToken" ? var.oci_profile : null
}

module "state" {
  source               = "../../../modules/state-bootstrap"
  expected_environment = "staging"
  target               = merge(var.target, { compartment_ocid = var.hosting_compartment_ocid })
}

# Keep deployment names private in ordinary output.
output "state_backend" {
  description = "Later platform backend coordinates; bootstrap migration is separate."
  sensitive   = true
  value       = module.state.state_backend
}

output "environment_binding" {
  description = "Explicit environment/tenancy/compartment for independent operator checks."
  sensitive   = true
  value       = module.state.environment_binding
}
