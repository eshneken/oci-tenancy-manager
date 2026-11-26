# Bind auth and scope explicitly; the namespace read is not proof of principal isolation.
provider "oci" {
  auth                = "APIKey"
  region              = var.target.region
  tenancy_ocid        = var.target.tenancy_ocid
  config_file_profile = var.oci_profile
}

# Own the development compartment without allowing the provider to delete it.
data "oci_identity_compartment" "adoption" {
  count = var.hosting_compartment_ocid == null ? 0 : 1
  id    = var.hosting_compartment_ocid
  lifecycle {
    postcondition {
      condition     = self.compartment_id == var.target.tenancy_ocid && self.name == "otm-development" && self.state == "ACTIVE"
      error_message = "Adoption requires the existing active environment compartment at the tenancy root."
    }
  }
}

# An existing-compartment input requests adoption; a fresh installation omits it.
import {
  for_each = var.hosting_compartment_ocid == null ? {} : { existing = var.hosting_compartment_ocid }
  to       = oci_identity_compartment.development
  id       = each.value
}

resource "oci_identity_compartment" "development" {
  depends_on     = [data.oci_identity_compartment.adoption]
  compartment_id = var.target.tenancy_ocid
  name           = "otm-development"
  description    = "OCI Tenancy Manager development compartment"
  enable_delete  = false

  lifecycle {
    prevent_destroy = true
    postcondition {
      condition = self.state == "ACTIVE" && (
        var.hosting_compartment_ocid == null || self.id == var.hosting_compartment_ocid
      )
      error_message = "Expected the active development compartment and its approved OCID when supplied."
    }
  }
}

module "state" {
  source               = "../../../modules/state-bootstrap"
  expected_environment = "development"
  target               = merge(var.target, { compartment_ocid = oci_identity_compartment.development.id })
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
