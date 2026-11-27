# Verify that the development signer and policy are independent of Atlas group creation.
mock_provider "oci" {
  override_during = plan

  mock_resource "oci_identity_compartment" {
    defaults = { id = "ocid1.compartment.oc1..synthetic", state = "ACTIVE" }
  }
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticnamespace" }
  }
  mock_resource "oci_identity_domains_app" {
    defaults = { name = "synthetic-exchange-development" }
  }
  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      display_name   = "Default"
      url            = "https://idcs-syntheticdevelopment.identity.oraclecloud.com"
      state          = "ACTIVE"
    }
  }
  mock_resource "oci_identity_user" {
    defaults = { id = "ocid1.user.oc1..syntheticsigner" }
  }
  mock_resource "oci_identity_group" {
    defaults = { id = "ocid1.group.oc1..syntheticwriter" }
  }
}

mock_provider "github" {}
mock_provider "external" {
  override_during = plan

  mock_data "external" {
    defaults = { result = { ocid = "" } }
  }
}
override_module {
  target = module.github_environment
}
# Exercise the mandatory Settings import without calling OCI.
override_resource {
  target          = module.delivery.oci_identity_domains_setting.signing_keys[0]
  override_during = plan
  values = {
    id                         = "Settings"
    csr_access                 = "none"
    signing_cert_public_access = true
  }
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
    trust_active                      = false
    repository_id                     = "1001"
    repository_owner_id               = "1002"
  }
  oci_profile                 = "SYNTHETIC_DEVELOPMENT"
  github_identity_domain_ocid = "ocid1.domain.oc1..synthetic"
  github_repository           = "example/tenancy-manager"
  target = {
    environment              = "development"
    tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
    object_storage_namespace = "syntheticnamespace"
    region                   = "us-ashburn-1"
  }
}

run "defaults_do_not_grant_laptop_permissions" {
  command = plan
  assert {
    condition = (
      length(oci_identity_user.local_app) == 0 &&
      length(oci_identity_group.local_app_writer) == 0 &&
      length(oci_identity_user_group_membership.local_app) == 0 &&
      length(oci_identity_api_key.local_app) == 0 &&
      length(oci_identity_policy.local_app) == 0
    )
    error_message = "A bootstrap creates the development signer, attachment, key, and policy only when requested."
  }
}

run "laptop_signer_preserves_the_approved_policy" {
  command = plan

  variables {
    local_app_iam = {
      domain_ocid            = "ocid1.domain.oc1..synthetic"
      signing_public_key_pem = "-----BEGIN PUBLIC KEY-----\nU1lOVEhFVElD\n-----END PUBLIC KEY-----"
    }
  }

  assert {
    condition = (
      oci_identity_user.local_app[0].name == "otm-development-localapp" &&
      oci_identity_user.local_app[0].compartment_id == var.target.tenancy_ocid &&
      oci_identity_group.local_app_writer[0].name == "otm-development-localapp" &&
      oci_identity_group.local_app_writer[0].compartment_id == var.target.tenancy_ocid &&
      oci_identity_user_group_membership.local_app[0].user_id == oci_identity_user.local_app[0].id &&
      oci_identity_user_group_membership.local_app[0].group_id == oci_identity_group.local_app_writer[0].id &&
      oci_identity_api_key.local_app[0].user_id == oci_identity_user.local_app[0].id &&
      trimspace(oci_identity_api_key.local_app[0].key_value) == var.local_app_iam.signing_public_key_pem
    )
    error_message = "The bootstrap must attach the named signer to its own root group and upload only its public key."
  }

  assert {
    condition = (
      oci_identity_policy.local_app[0].name == "otm-development-localapp" &&
      oci_identity_policy.local_app[0].compartment_id == var.target.tenancy_ocid &&
      toset(oci_identity_policy.local_app[0].statements) == toset([
        "Allow group Default/otm-development-localapp to use groups in tenancy",
        "Allow group Default/otm-development-localapp to use users in tenancy",
      ])
    )
    error_message = "Preserve the two approved membership permissions on the verified signer group."
  }
}

run "user_creation_requires_an_explicit_opt_in" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid            = "ocid1.domain.oc1..synthetic"
      signing_public_key_pem = "-----BEGIN PUBLIC KEY-----\nU1lOVEhFVElD\n-----END PUBLIC KEY-----"
      create_federated_users = true
    }
  }
  assert {
    condition = one([for statement in oci_identity_policy.local_app[0].statements :
      statement if strcontains(statement, "to manage users")
    ]) == "Allow group Default/otm-development-localapp to manage users in tenancy where all {target.resource.domain.name = 'Default', request.operation = 'CreateUser'}"
    error_message = "The extra user grant must be limited to the one domain and the create operation."
  }
}

run "reject_private_key_material" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid            = "ocid1.domain.oc1..synthetic"
      signing_public_key_pem = "not a public key"
    }
  }
  expect_failures = [var.local_app_iam]
}

run "reject_unrelated_domain" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid            = "ocid1.domain.oc1..unrelated"
      signing_public_key_pem = "-----BEGIN PUBLIC KEY-----\nU1lOVEhFVElD\n-----END PUBLIC KEY-----"
    }
  }
  override_data {
    target = data.oci_identity_domain.local_app_domain[0]
    values = {
      compartment_id = "ocid1.tenancy.oc1..unrelated"
      display_name   = "Default"
      url            = "https://idcs-syntheticdevelopment.identity.oraclecloud.com"
      state          = "ACTIVE"
    }
  }
  expect_failures = [data.oci_identity_domain.local_app_domain]
}
