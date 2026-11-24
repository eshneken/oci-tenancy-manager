# Verify the development bootstrap without reading a local signing profile or contacting OCI.
mock_provider "oci" {
  mock_data "oci_identity_compartment" {
    defaults = {
      name           = "otm-development"
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
    }
  }
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticnamespace" }
  }
}
variables {
  oci_profile              = "SYNTHETIC_DEVELOPMENT"
  hosting_compartment_ocid = "ocid1.compartment.oc1..synthetic"
  target = {
    environment              = "development"
    tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
    object_storage_namespace = "syntheticnamespace"
    region                   = "us-ashburn-1"
  }
}
run "development_backend_is_separate" {
  command = plan
  assert {
    condition     = output.state_backend.bucket == "otm-development-tfstate" && output.state_backend.key == "custody/development/terraform.tfstate"
    error_message = "Development uses its own bucket and custody key."
  }
}
run "reject_default_profile" {
  command = plan
  variables { oci_profile = "DEFAULT" }
  expect_failures = [var.oci_profile]
}
run "reject_unrelated_compartment" {
  command = plan
  override_data {
    target = data.oci_identity_compartment.development
    values = { name = "other-compartment" }
  }
  expect_failures = [data.oci_identity_compartment.development]
}
