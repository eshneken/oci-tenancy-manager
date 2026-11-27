# Verify the development bootstrap without reading a local signing profile or contacting OCI.
mock_provider "oci" {
  override_during = plan

  mock_data "oci_identity_domains_app_roles" {
    defaults = {
      total_results = 1
      app_roles = [{
        id           = "cccccccccccccccccccccccccccccccc"
        display_name = "Application Administrator"
        admin_role   = true
        app          = [{ value = "IDCSAppId" }]
      }]
    }
  }

  mock_data "oci_identity_domains_grant" {
    defaults = {
      id              = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      schemas         = ["urn:ietf:params:scim:schemas:oracle:idcs:Grant"]
      grant_mechanism = "ADMINISTRATOR_TO_DYNAMIC_RESOURCE_GROUP"
      app             = [{ value = "IDCSAppId" }]
      grantee         = [{ type = "DynamicResourceGroup", value = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }]
      entitlement     = [{ attribute_name = "appRoles", attribute_value = "cccccccccccccccccccccccccccccccc" }]
    }
  }

  mock_resource "oci_identity_dynamic_group" {
    defaults = {
      id    = "ocid1.dynamicgroup.oc1..synthetic"
      state = "ACTIVE"
    }
  }

  mock_resource "oci_identity_domains_grant" {
    defaults = { id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }
  }

  mock_data "oci_identity_compartment" {
    defaults = { compartment_id = "ocid1.tenancy.oc1..synthetic", name = "otm-development", state = "ACTIVE" }
  }
  mock_resource "oci_identity_compartment" {
    defaults = { id = "ocid1.compartment.oc1..synthetic", state = "ACTIVE" }
  }
  mock_resource "oci_identity_domains_app" {
    defaults = { name = "synthetic-exchange-development" }
  }
  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      display_name   = "Default"
      state          = "ACTIVE"
      url            = "https://idcs-syntheticdevelopment.identity.oraclecloud.com"
    }
  }
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticnamespace" }
  }
}
override_resource {
  target          = oci_identity_compartment.development
  override_during = plan
  values          = { id = "ocid1.compartment.oc1..synthetic", state = "ACTIVE" }
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
  hosting_compartment_ocid    = "ocid1.compartment.oc1..synthetic"
  github_identity_domain_ocid = "ocid1.domain.oc1..synthetic"
  github_repository           = "example/tenancy-manager"
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
    condition     = length(data.oci_identity_group.group_adoption) == 0
    error_message = "A fresh bootstrap must skip the native adoption lookup."
  }
  assert {
    condition     = output.state_backend.bucket == "otm-development-tfstate" && output.state_backend.key == "custody/development/terraform.tfstate"
    error_message = "Development uses its own bucket and custody key."
  }
  assert {
    condition = (
      oci_identity_compartment.development.name == "otm-development" &&
      oci_identity_compartment.development.compartment_id == var.target.tenancy_ocid &&
      !oci_identity_compartment.development.enable_delete &&
      output.environment_binding.compartment_ocid == oci_identity_compartment.development.id
    )
    error_message = "The bootstrap must own the direct development child and bind the backend to it."
  }
}
run "reject_default_profile" {
  command = plan
  variables { oci_profile = "DEFAULT" }
  expect_failures = [var.oci_profile]
}
run "reject_unrelated_compartment" {
  command = plan
  override_resource {
    target          = oci_identity_compartment.development
    override_during = plan
    values          = { id = "ocid1.compartment.oc1..other", state = "ACTIVE" }
  }
  expect_failures = [oci_identity_compartment.development]
}

run "github_policy_is_scoped" {
  command = plan
  assert {
    condition     = oci_identity_policy.github_infrastructure.name == "otm-development-github-infrastructure"
    error_message = "The bootstrap must use the live GitHub infrastructure policy name."
  }
  assert {
    condition = (
      oci_identity_policy.github_infrastructure.compartment_id == var.hosting_compartment_ocid &&
      length(oci_identity_policy.github_infrastructure.statements) == 13 &&
      alltrue([for statement in oci_identity_policy.github_infrastructure.statements :
        strcontains(statement, "in compartment otm-development where") &&
        strcontains(statement, "request.principal.type = 'identityfederateddomainapp'") &&
        strcontains(statement, "request.principal.domain.id = '${var.github_identity_domain_ocid}'") &&
        strcontains(statement, "request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-development.yml@refs/heads/master'") &&
        strcontains(statement, "request.principal.ext_environment = 'development'")
      ])
    )
    error_message = "Every grant must match the federated principal type, domain, exact development workflow, environment, and compartment."
  }
  assert {
    condition = (
      length([for statement in oci_identity_policy.github_infrastructure.statements :
      statement if strcontains(statement, "'OBJECT_DELETE'")]) == 1 &&
      alltrue([for statement in oci_identity_policy.github_infrastructure.statements :
        strcontains(statement, "terraform.tfstate.lock") if strcontains(statement, "'OBJECT_DELETE'")
      ])
    )
    error_message = "The exact Terraform lock is the only object this policy can delete."
  }
  assert {
    condition = (
      length([for statement in oci_identity_policy.github_infrastructure.statements :
        statement if strcontains(statement, "target.object.name = '*/plan.tar'")
      ]) == 2 &&
      length([for statement in oci_identity_policy.github_infrastructure.statements :
        statement if strcontains(statement, "any {target.object.name = '*/apply-attempt.json', target.object.name = '*/errored.tfstate'}")
      ]) == 1 &&
      alltrue([for statement in oci_identity_policy.github_infrastructure.statements :
        strcontains(statement, "target.object.name = 'infrastructure-plans/development/custody/*'") &&
        strcontains(statement, "target.object.name != 'infrastructure-plans/development/custody/plan.tar'") &&
        strcontains(statement, "target.object.name != 'infrastructure-plans/development/custody/apply-attempt.json'") &&
        strcontains(statement, "target.object.name != 'infrastructure-plans/development/custody/errored.tfstate'") &&
        strcontains(statement, "target.bucket.name = 'otm-development-tfstate'") &&
        (strcontains(statement, "request.operation = 'PutObject', request.permission = 'OBJECT_CREATE'") ||
        strcontains(statement, "request.operation = 'GetObject', request.permission = 'OBJECT_READ'")) &&
        !strcontains(statement, "'OBJECT_OVERWRITE'") &&
        !strcontains(statement, "'OBJECT_DELETE'")
        if strcontains(statement, "plan.tar") || strcontains(statement, "apply-attempt.json") || strcontains(statement, "errored.tfstate")
      ])
    )
    error_message = "Saved plans and recovery artifacts require both the development prefix and permitted suffix, with no overwrite or delete."
  }
}

run "github_compartment_policy_uses_verified_named_subject" {
  command = plan

  variables {
    github_workflow_dynamic_group = {
      principal_ocid = "ocid1.identityfederateddomainapp.oc1..synthetic"
      existing = {
        group_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        grant_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      }
    }
  }

  override_data {
    target          = module.delivery.data.oci_identity_domains_dynamic_resource_group.development_workflow[0]
    override_during = plan
    values = {
      id            = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      ocid          = "ocid1.dynamicgroup.oc1..synthetic"
      display_name  = "otm-development-github-identity"
      domain_ocid   = "ocid1.domain.oc1..synthetic"
      tenancy_ocid  = "ocid1.tenancy.oc1..synthetic"
      matching_rule = "resource.id = 'ocid1.identityfederateddomainapp.oc1..synthetic'"
    }
  }

  override_resource {
    target          = module.delivery.oci_identity_dynamic_group.development_workflow[0]
    override_during = plan
    values = {
      id             = "ocid1.dynamicgroup.oc1..synthetic"
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      name           = "otm-development-github-identity"
      description    = "Development infrastructure workflow identity"
      state          = "ACTIVE"
      matching_rule  = "resource.id = 'ocid1.identityfederateddomainapp.oc1..synthetic'"
    }
  }

  override_resource {
    target          = module.delivery.oci_identity_domains_grant.development_application_administrator[0]
    override_during = plan
    values = {
      id              = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      idcs_endpoint   = "https://idcs-syntheticdevelopment.identity.oraclecloud.com"
      schemas         = ["urn:ietf:params:scim:schemas:oracle:idcs:Grant"]
      grant_mechanism = "ADMINISTRATOR_TO_DYNAMIC_RESOURCE_GROUP"
      app             = { value = "IDCSAppId" }
      grantee         = { type = "DynamicResourceGroup", value = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
      entitlement     = { attribute_name = "appRoles", attribute_value = "cccccccccccccccccccccccccccccccc" }
    }
  }

  assert {
    condition = (
      length(oci_identity_policy.github_infrastructure.statements) == 13 &&
      alltrue([for statement in oci_identity_policy.github_infrastructure.statements :
        startswith(statement, "Allow dynamic-group Default/otm-development-github-identity to ") &&
        strcontains(statement, "in compartment otm-development where") &&
        strcontains(statement, "request.principal.type = 'identityfederateddomainapp'") &&
        strcontains(statement, "request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-development.yml@refs/heads/master'") &&
        strcontains(statement, "request.principal.ext_environment = 'development'") &&
        !strcontains(statement, "request.principal.domain.id")
      ])
    )
    error_message = "Use the verified named development grantee on every existing compartment statement, preserving the exact claims and resource scope."
  }
}

run "reject_non_domain_reference" {
  command = plan
  variables { github_identity_domain_ocid = "ocid1.tenancy.oc1..synthetic" }
  expect_failures = [var.github_identity_domain_ocid]
}

run "reject_github_repository_wildcard" {
  command = plan
  variables { github_repository = "example/*" }
  expect_failures = [var.github_repository]
}

run "preserve_working_development_exchange" {
  command = plan
  variables {
    github_delivery = {
      repository_id            = "1001", repository_owner_id = "1002",
      existing_trust_id        = "22222222222222222222222222222222", trust_active = true
      existing_exchange_app_id = "11111111111111111111111111111111"
    }
  }
  override_resource {
    target          = module.delivery.oci_identity_domains_identity_propagation_trust.github[0]
    override_during = plan
    values          = { id = "22222222222222222222222222222222" }
  }
  override_data {
    target          = data.external.exchange_metadata[0]
    override_during = plan
    values          = { result = { id = "11111111111111111111111111111111", name = "synthetic-existing" } }
  }
  assert {
    condition     = output.github_exchange_client_id == "synthetic-existing" && output.github_exchange_app_id == "11111111111111111111111111111111"
    error_message = "Only projected immutable metadata should supply the exact working client."
  }
}

# A working exchange client must keep the existing trust instead of creating a second issuer.
run "reject_existing_client_without_trust_pin" {
  command = plan
  variables {
    github_delivery = {
      repository_id            = "1001"
      repository_owner_id      = "1002"
      existing_exchange_app_id = "11111111111111111111111111111111"
      trust_active             = true
    }
  }
  expect_failures = [var.github_delivery]
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

run "verify_existing_native_adoption_group" {
  command = plan

  override_data {
    target          = data.external.group_adoption_pin
    override_during = plan
    values          = { result = { ocid = "ocid1.group.oc1..atlasadoption" } }
  }

  override_data {
    target          = data.oci_identity_group.group_adoption[0]
    override_during = plan
    values = {
      id             = "ocid1.group.oc1..atlasadoption"
      name           = "otm-development-users"
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
    }
  }

  assert {
    condition     = one(data.oci_identity_group.group_adoption).group_id == data.external.group_adoption_pin.result["ocid"]
    error_message = "The operator must read the same exact native group the workflow adopts."
  }
}

run "reject_adoption_group_in_unrelated_tenancy" {
  command = plan

  override_data {
    target          = data.external.group_adoption_pin
    override_during = plan
    values          = { result = { ocid = "ocid1.group.oc1..atlasadoption" } }
  }

  override_data {
    target          = data.oci_identity_group.group_adoption[0]
    override_during = plan
    values = {
      id             = "ocid1.group.oc1..atlasadoption"
      name           = "otm-development-users"
      compartment_id = "ocid1.tenancy.oc1..unrelated"
      state          = "ACTIVE"
    }
  }

  expect_failures = [data.oci_identity_group.group_adoption]
}
