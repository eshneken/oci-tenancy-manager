# Tests substitute OCI's entire provider; no plan calls real service APIs.
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

# These are security/operability invariants, not a copy of each implementation expression.
run "private_recoverable_standard_bucket" {
  command = plan
  assert {
    condition     = oci_objectstorage_bucket.state.access_type == "NoPublicAccess" && oci_objectstorage_bucket.state.versioning == "Enabled"
    error_message = "Terraform state must never become public or lose its object-version history."
  }
  assert {
    condition     = oci_objectstorage_bucket.state.storage_tier == "Standard"
    error_message = "Active state and lock objects cannot depend on archive retrieval."
  }
  assert {
    condition     = oci_objectstorage_bucket.state.compartment_id == var.target.compartment_ocid && oci_objectstorage_bucket.state.freeform_tags["otm.environment"] == "staging"
    error_message = "The bucket must stay bound to the reviewed compartment/environment."
  }
}

# An accessible but unexpected live namespace is not silently adopted.
run "reject_live_namespace_mismatch" {
  command = plan
  override_data {
    target = data.oci_objectstorage_namespace.target
    values = { namespace = "anothernamespace" }
  }
  expect_failures = [data.oci_objectstorage_namespace.target]
}

run "reject_mislabeled_environment" {
  command = plan
  variables { expected_environment = "production" }
  expect_failures = [var.target]
}

run "reject_wrong_tenancy_resource_type" {
  command = plan
  variables {
    target = {
      environment              = "staging"
      tenancy_ocid             = "ocid1.compartment.oc1..syntheticstaging"
      compartment_ocid         = "ocid1.compartment.oc1..syntheticstaging"
      object_storage_namespace = "syntheticnamespace"
    }
  }
  expect_failures = [var.target]
}

run "reject_wrong_compartment_resource_type" {
  command = plan
  variables {
    target = {
      environment              = "staging"
      tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
      compartment_ocid         = "ocid1.tenancy.oc1..syntheticstaging"
      object_storage_namespace = "syntheticnamespace"
    }
  }
  expect_failures = [var.target]
}

run "reject_namespace_path" {
  command = plan
  variables {
    target = {
      environment              = "staging"
      tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
      compartment_ocid         = "ocid1.compartment.oc1..syntheticstaging"
      object_storage_namespace = "namespace/another"
    }
  }
  expect_failures = [var.target]
}

run "reject_invalid_region" {
  command = plan
  variables {
    target = {
      environment              = "staging"
      tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
      compartment_ocid         = "ocid1.compartment.oc1..syntheticstaging"
      object_storage_namespace = "syntheticnamespace"
      region                   = "not a region"
    }
  }
  expect_failures = [var.target]
}

run "reject_unsafe_name" {
  command = plan
  variables { name_prefix = "../other" }
  expect_failures = [var.name_prefix]
}

run "production_uses_separate_bucket_binding" {
  command = plan
  variables {
    expected_environment = "production"
    target = {
      environment              = "production"
      tenancy_ocid             = "ocid1.tenancy.oc1..syntheticproduction"
      compartment_ocid         = "ocid1.compartment.oc1..syntheticproduction"
      object_storage_namespace = "syntheticproduction"
    }
  }
  override_data {
    target = data.oci_objectstorage_namespace.target
    values = { namespace = "syntheticproduction" }
  }
  assert {
    condition     = output.state_backend.bucket == "otm-production-tfstate" && output.state_backend.namespace == "syntheticproduction"
    error_message = "Production must have its own environment-specific bucket/namespace binding."
  }
}
