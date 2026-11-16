# Provider effects remain mock-only, including compartments/IAM. IDs stay synthetic and distinct.
mock_provider "oci" {
  override_during = apply
  mock_resource "oci_kms_vault" {
    defaults = { management_endpoint = "https://management.example.test" }
  }
}
variables {
  environment                     = "staging"
  hosting_compartment_ocid        = "ocid1.compartment.oc1..synthetichosting"
  database_provisioner_group_ocid = "ocid1.group.oc1..syntheticprovisioners"
}
run "seed_mock_vault" { command = apply }
run "reject_vault_replacement" {
  command = plan
  plan_options { replace = [oci_kms_vault.domain["database-provisioning"]] }
}
