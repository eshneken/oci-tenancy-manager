# Only a mocked provider runs: no OCI calls or credentials, including during plan.
mock_provider "oci" {
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticstaging" }
  }
}

variables {
  hosting_compartment_ocid = "ocid1.compartment.oc1..syntheticstaging"
  target = {
    environment              = "staging"
    tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
    object_storage_namespace = "syntheticstaging"
  }
}

run "fixed_environment_and_backend" {
  command = plan
  assert {
    condition     = output.environment_binding.environment == "staging" && output.state_backend.bucket == "otm-staging-tfstate"
    error_message = "This root must retain its own environment and bucket."
  }
  assert {
    condition     = output.state_backend.region == "us-ashburn-1" && output.state_backend.namespace == "syntheticstaging" && output.state_backend.key == "platform/staging/terraform.tfstate"
    error_message = "Backend references must remain bound to the reviewed target."
  }
}

run "reject_other_environment_record" {
  command = plan
  variables {
    target = {
      environment              = "production"
      tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
      object_storage_namespace = "syntheticstaging"
    }
  }
  expect_failures = [var.target]
}

run "reject_api_key_fallback" {
  command = plan
  variables { oci_auth = "APIKey" }
  expect_failures = [var.oci_auth]
}

run "reject_empty_profile" {
  command = plan
  variables { oci_profile = " " }
  expect_failures = [var.oci_profile]
}

run "explicit_resource_principal" {
  command = plan
  variables { oci_auth = "ResourcePrincipal" }
  assert {
    condition     = output.environment_binding.environment == "staging"
    error_message = "An explicit auth selection must not change the environment."
  }
}

run "explicit_hosting_compartment_reaches_all_resources" {
  command = plan
  variables { hosting_compartment_ocid = "ocid1.compartment.oc1..syntheticalternate" }
  assert {
    condition     = output.environment_binding.compartment_ocid == var.hosting_compartment_ocid
    error_message = "Every resource group must use the single environment-selected hosting compartment."
  }
}
run "reject_invalid_hosting_compartment" {
  command = plan
  variables { hosting_compartment_ocid = "not-a-compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}
