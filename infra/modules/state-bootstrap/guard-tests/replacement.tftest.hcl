# The checker expects this file to fail at the replacement plan, not during setup.
# Mock apply creates only in-memory Terraform test state; OCI is never contacted.
mock_provider "oci" {
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticnamespace" }
  }
}

variables {
  expected_environment = "staging"
  target = {
    environment              = "staging"
    tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
    compartment_ocid         = "ocid1.compartment.oc1..syntheticstaging"
    object_storage_namespace = "syntheticnamespace"
  }
}

run "seed_mock_bucket" {
  command = apply
}

run "reject_bucket_replacement" {
  command = plan
  # Force the destructive plan explicitly; provider mocks do not reproduce SDK plan modifiers.
  plan_options { replace = [oci_objectstorage_bucket.state] }
}
