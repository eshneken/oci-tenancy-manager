# Verify the opt-in on synthetic compartments without obtaining any OCI credentials.
mock_provider "oci" {
  override_during = plan

  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      display_name   = "Default"
      state          = "ACTIVE"
      url            = "https://idcs-synthetic.identity.oraclecloud.com"
    }
  }
}

variables {
  exchange_write_response_qualified = true
  environment                       = "production"
  tenancy_ocid                      = "ocid1.tenancy.oc1..synthetic"
  identity_domain_ocid              = "ocid1.domain.oc1..synthetic"
  github = {
    repository          = "example/tenancy-manager"
    repository_id       = "1001"
    repository_owner_id = "1002"
  }
  storage_policy = {
    compartment_ocid = "ocid1.compartment.oc1..syntheticproduction"
    bucket_name      = "otm-production-tfstate"
    state_key        = "infrastructure/production/terraform.tfstate"
  }
}

run "reader_policies_are_read_only_by_default" {
  command = plan

  assert {
    condition = [
      for statement in oci_identity_policy.workflow_platform[0].statements :
      statement if strcontains(statement, " policies ")
      ] == [
      "Allow any-user to inspect policies in compartment otm-production where all {request.principal.type = 'identityfederateddomainapp', request.principal.domain.id = 'ocid1.domain.oc1..synthetic', request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-production.yml@refs/heads/master', request.principal.ext_environment = 'production', target.compartment.id = 'ocid1.compartment.oc1..syntheticproduction', any {target.policy.name = 'otm-production-database-provisioning-read', target.policy.name = 'otm-production-api-vault-read', target.policy.name = 'otm-production-worker-vault-read'}, request.operation = 'GetPolicy'}"
    ]
    error_message = "The default grant must only refresh the three named policies in the exact production compartment."
  }
}

run "approved_writes_are_bound_to_exact_staging_policies" {
  command = plan

  variables {
    environment                 = "staging"
    allow_runtime_policy_writes = true
    storage_policy = {
      compartment_ocid = "ocid1.compartment.oc1..syntheticstaging"
      bucket_name      = "otm-staging-tfstate"
      state_key        = "infrastructure/staging/terraform.tfstate"
    }
  }

  assert {
    condition = (
      oci_identity_policy.workflow_platform[0].compartment_id == var.storage_policy.compartment_ocid &&
      [
        for statement in oci_identity_policy.workflow_platform[0].statements :
        statement if strcontains(statement, " policies ")
        ] == [
        "Allow any-user to inspect policies in compartment otm-staging where all {request.principal.type = 'identityfederateddomainapp', request.principal.domain.id = 'ocid1.domain.oc1..synthetic', request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-staging.yml@refs/heads/master', request.principal.ext_environment = 'staging', target.compartment.id = 'ocid1.compartment.oc1..syntheticstaging', any {target.policy.name = 'otm-staging-database-provisioning-read', target.policy.name = 'otm-staging-api-vault-read', target.policy.name = 'otm-staging-worker-vault-read'}, request.operation = 'GetPolicy'}",
        "Allow any-user to manage policies in compartment otm-staging where all {request.principal.type = 'identityfederateddomainapp', request.principal.domain.id = 'ocid1.domain.oc1..synthetic', request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-staging.yml@refs/heads/master', request.principal.ext_environment = 'staging', target.compartment.id = 'ocid1.compartment.oc1..syntheticstaging', any {target.policy.name = 'otm-staging-database-provisioning-read', target.policy.name = 'otm-staging-api-vault-read', target.policy.name = 'otm-staging-worker-vault-read'}, request.operation = 'CreatePolicy', request.permission = 'POLICY_CREATE'}",
        "Allow any-user to manage policies in compartment otm-staging where all {request.principal.type = 'identityfederateddomainapp', request.principal.domain.id = 'ocid1.domain.oc1..synthetic', request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-staging.yml@refs/heads/master', request.principal.ext_environment = 'staging', target.compartment.id = 'ocid1.compartment.oc1..syntheticstaging', any {target.policy.name = 'otm-staging-database-provisioning-read', target.policy.name = 'otm-staging-api-vault-read', target.policy.name = 'otm-staging-worker-vault-read'}, request.operation = 'UpdatePolicy', request.permission = 'POLICY_UPDATE'}"
      ]
    )
    error_message = "An approved writer may get, create, or update only the three named policies in the exact hosted compartment."
  }
}

run "development_cannot_enable_hosted_policy_writes" {
  command = plan

  variables {
    environment                 = "development"
    allow_runtime_policy_writes = true
    storage_policy              = null
  }

  expect_failures = [var.allow_runtime_policy_writes]
}
