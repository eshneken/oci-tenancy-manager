# Only a mocked provider runs: no OCI calls or credentials, including during plan.
mock_provider "oci" {
  override_during = plan

  mock_data "oci_identity_compartment" {
    defaults = { compartment_id = "ocid1.tenancy.oc1..syntheticstaging", name = "otm-staging", state = "ACTIVE" }
  }
  mock_resource "oci_identity_compartment" {
    defaults = { id = "ocid1.compartment.oc1..syntheticstaging", state = "ACTIVE" }
  }
  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..syntheticstaging"
      state          = "ACTIVE"
      display_name   = "Default"
      url            = "https://idcs-syntheticstaging.identity.oraclecloud.com"
    }
  }
  mock_resource "oci_identity_domains_app" {
    defaults = { name = "synthetic-exchange-staging" }
  }
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticstaging" }
  }
}
override_resource {
  target          = oci_identity_compartment.hosting
  override_during = plan
  values          = { id = "ocid1.compartment.oc1..syntheticstaging", state = "ACTIVE" }
}


override_resource {
  target          = module.delivery.oci_identity_domains_app.exchange
  override_during = plan
  values          = { name = "synthetic-exchange-staging" }
}

override_data {
  target          = module.delivery.data.oci_identity_domain.selected
  override_during = plan
  values = {
    compartment_id = "ocid1.tenancy.oc1..syntheticstaging"
    state          = "ACTIVE"
    display_name   = "Default"
    url            = "https://idcs-syntheticstaging.identity.oraclecloud.com"
  }
}

mock_provider "github" {}
mock_provider "external" {}
override_module {
  target = module.github_environment
}
variables {
  github_environment = {
    reviewer_user_ids  = [1003]
    settings_file      = "synthetic.json"
    kubernetes_version = "v1.34.1"
    postgresql_version = "16"
  }
  github_delivery = {
    exchange_write_response_qualified = true
    identity_domain_ocid              = "ocid1.domain.oc1..syntheticstaging"
    repository                        = "example/tenancy-manager"
    repository_id                     = "1001"
    repository_owner_id               = "1002"
  }
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
    condition     = output.state_backend.region == "us-ashburn-1" && output.state_backend.key == "infrastructure/staging/terraform.tfstate"
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
  assert {
    condition = (
      output.environment_binding.compartment_ocid == oci_identity_compartment.hosting.id &&
      oci_identity_compartment.hosting.name == "otm-staging" &&
      oci_identity_compartment.hosting.compartment_id == var.target.tenancy_ocid &&
      !oci_identity_compartment.hosting.enable_delete
    )
    error_message = "Every resource group must use the single environment-selected hosting compartment."
  }
}
run "reject_invalid_hosting_compartment" {
  command = plan
  variables { hosting_compartment_ocid = "not-a-compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}

run "connects_environment_delivery" {
  command = plan

  variables {
    github_delivery = {
      exchange_write_response_qualified = true
      identity_domain_ocid              = "ocid1.domain.oc1..syntheticstaging"
      repository                        = "example/tenancy-manager"
      repository_id                     = "1001"
      repository_owner_id               = "1002"
    }
  }

  assert {
    condition     = output.github_exchange_client_id == "synthetic-exchange-staging" && output.identity_domain_url == "https://idcs-syntheticstaging.identity.oraclecloud.com"
    error_message = "Expose only the fixed environment's exchange client ID for protected handoff."
  }
}

run "reject_dispatch_until_client_bound_exchange" {
  command = plan
  variables {
    github_environment = {
      settings_file = "synthetic.json", reviewer_user_ids = [1003], plan_enabled = true
    }
  }
  expect_failures = [var.github_environment]
}

# Reject a pinned sibling before Terraform can propose renaming it into the environment.
run "reject_unrelated_compartment_adoption" {
  command = plan
  override_data {
    target          = data.oci_identity_compartment.adoption[0]
    override_during = plan
    values          = { name = "unrelated", state = "ACTIVE" }
  }
  expect_failures = [data.oci_identity_compartment.adoption]
}
