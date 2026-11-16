# Exercise lifecycle replacement rejection with mocked OCI only.
mock_provider "oci" {
  override_during = apply
  mock_resource "oci_kms_vault" {
    defaults = { management_endpoint = "https://management.example.test" }
  }
}
variables {
  oci_profile              = "ATLAS_DEV"
  tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
  hosting_compartment_ocid = "ocid1.compartment.oc1..development"
  region                   = "us-ashburn-1"
}
run "seed_mock_vault" { command = apply }
run "reject_vault_replacement" {
  command = plan
  plan_options { replace = [oci_kms_vault.application] }
}
