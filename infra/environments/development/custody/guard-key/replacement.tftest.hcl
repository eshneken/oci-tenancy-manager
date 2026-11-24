# Exercise lifecycle replacement rejection with mocked OCI only.
mock_provider "oci" {
  override_during = apply
  mock_resource "oci_kms_vault" {
    defaults = { management_endpoint = "https://management.example.test" }
  }
}
variables {
  oci_auth                 = "ResourcePrincipal"
  hosting_compartment_ocid = "ocid1.compartment.oc1..development"
  target = {
    environment              = "development"
    tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
    object_storage_namespace = "syntheticnamespace"
    region                   = "us-ashburn-1"
  }
}
run "seed_mock_key" { command = apply }
run "reject_key_replacement" {
  command = plan
  plan_options { replace = [oci_kms_key.application] }
}
