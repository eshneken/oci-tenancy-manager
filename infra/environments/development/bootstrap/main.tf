# Bind auth and scope explicitly; the namespace read is not proof of principal isolation.
provider "oci" {
  auth                = "APIKey"
  region              = var.target.region
  tenancy_ocid        = var.target.tenancy_ocid
  config_file_profile = var.oci_profile
}

# Confirm the approved child of the non-production root before the bucket can be created.
data "oci_identity_compartment" "development" {
  id = var.hosting_compartment_ocid
  lifecycle {
    postcondition {
      condition     = self.name == "otm-development" && self.compartment_id == var.target.tenancy_ocid && self.state == "ACTIVE"
      error_message = "Expected the active otm-development compartment directly under the selected tenancy."
    }
  }
}

module "state" {
  source               = "../../../modules/state-bootstrap"
  expected_environment = "development"
  target               = merge(var.target, { compartment_ocid = var.hosting_compartment_ocid })
  depends_on           = [data.oci_identity_compartment.development]
}

# Keep deployment names private in ordinary output.
output "state_backend" {
  description = "Later custody backend coordinates; bootstrap migration is separate."
  sensitive   = true
  value       = module.state.state_backend
}

output "environment_binding" {
  description = "Explicit environment/tenancy/compartment for independent operator checks."
  sensitive   = true
  value       = module.state.environment_binding
}
