# Every operation is mocked; no live backend or authorization is exercised.
mock_provider "oci" {
  override_during = plan
  mock_data "oci_objectstorage_namespace" { defaults = { namespace = "syntheticstaging" } }
  mock_resource "oci_kms_vault" { defaults = { management_endpoint = "https://management.example.test" } }
}
variables {
  hosting_compartment_ocid        = "ocid1.compartment.oc1..syntheticstaging"
  target                          = { environment = "staging", tenancy_ocid = "ocid1.tenancy.oc1..syntheticstaging", object_storage_namespace = "syntheticstaging" }
  database_provisioner_group_ocid = "ocid1.group.oc1..syntheticstagingprovisioners"
}
run "fixed_security_environment" {
  command = plan
  assert {
    condition     = output.custody.environment == "staging" && toset(keys(output.custody.domains)) == toset(["database-provisioning", "application-secrets"])
    error_message = "Use only this environment's custody roots."
  }
}
run "reject_other_environment" {
  command = plan
  variables { target = { environment = "production", tenancy_ocid = "ocid1.tenancy.oc1..syntheticstaging", object_storage_namespace = "syntheticstaging" } }
  expect_failures = [var.target]
}
run "reject_wrong_namespace" {
  command = plan
  override_data {
    target = data.oci_objectstorage_namespace.target
    values = { namespace = "wrong-synthetic" }
  }
  expect_failures = [data.oci_objectstorage_namespace.target]
}
run "reject_api_key_fallback" {
  command = plan
  variables { oci_auth = "APIKey" }
  expect_failures = [var.oci_auth]
}
run "explicit_resource_principal" {
  command = plan
  variables { oci_auth = "ResourcePrincipal" }
  assert {
    condition     = output.custody.environment == "staging"
    error_message = "Explicit authentication must not change target environment."
  }
}

run "explicit_hosting_compartment_reaches_all_resources" {
  command = plan
  variables { hosting_compartment_ocid = "ocid1.compartment.oc1..syntheticalternate" }
  assert {
    condition     = alltrue([for domain in values(output.custody.domains) : domain.compartment_ocid == var.hosting_compartment_ocid])
    error_message = "Every resource group must use the single environment-selected hosting compartment."
  }
}
run "reject_invalid_hosting_compartment" {
  command = plan
  variables { hosting_compartment_ocid = "not-a-compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}
