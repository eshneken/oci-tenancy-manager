# No live client, signer, or IAM calls are used to verify federation and policy shape.
mock_provider "oci" {
  override_during = plan

  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
      display_name   = "Default"
      url            = "https://idcs-synthetic.identity.oraclecloud.com/"
    }
  }

  mock_resource "oci_identity_domains_app" {
    defaults = { name = "synthetic-exchange-client" }
  }
}

variables {
  exchange_write_response_qualified = true
  environment                       = "development"
  tenancy_ocid                      = "ocid1.tenancy.oc1..synthetic"
  identity_domain_ocid              = "ocid1.domain.oc1..synthetic"
  github = {
    repository          = "example/tenancy-manager"
    repository_id       = "1001"
    repository_owner_id = "1002"
  }
}

run "development_binds_exact_workflow_claims" {
  command = plan

  variables {
    owns_domain_settings = true
  }

  assert {
    condition = (
      oci_identity_domains_app.exchange[0].display_name == "otm-github-development" &&
      oci_identity_domains_app.exchange[0].idcs_endpoint == "https://idcs-synthetic.identity.oraclecloud.com" &&
      !oci_identity_domains_app.exchange[0].active &&
      !oci_identity_domains_app.exchange[0].is_login_target &&
      oci_identity_domains_app.exchange[0].is_oauth_client &&
      !oci_identity_domains_app.exchange[0].is_oauth_resource &&
      oci_identity_domains_app.exchange[0].client_type == "confidential" &&
      oci_identity_domains_app.exchange[0].trust_scope == "Explicit" &&
      toset(oci_identity_domains_app.exchange[0].allowed_grants) == toset(["client_credentials"]) &&
      !strcontains(lower(oci_identity_domains_app.exchange[0].attributes), "clientsecret")
    )
    error_message = "Configure only the projected, restricted confidential exchange client."
  }

  assert {
    condition = (
      oci_identity_domains_identity_propagation_trust.github[0].issuer == "https://token.actions.githubusercontent.com" &&
      oci_identity_domains_identity_propagation_trust.github[0].public_key_endpoint == "https://token.actions.githubusercontent.com/.well-known/jwks" &&
      !oci_identity_domains_identity_propagation_trust.github[0].active &&
      oci_identity_domains_identity_propagation_trust.github[0].subject_type == "Resource" &&
      oci_identity_domains_identity_propagation_trust.github[0].impersonating_resource == "githubactions" &&
      toset(oci_identity_domains_identity_propagation_trust.github[0].oauth_clients) == toset(["synthetic-exchange-client"]) &&
      oci_identity_domains_identity_propagation_trust.github[0].client_claim_name == "aud" &&
      toset(oci_identity_domains_identity_propagation_trust.github[0].client_claim_values) == toset(["otm-infrastructure-development"]) &&
      toset(oci_identity_domains_identity_propagation_trust.github[0].claim_propagations) == toset(["ext_workflow_ref", "ext_environment"]) &&
      tomap({ for claim in oci_identity_domains_identity_propagation_trust.github[0].claim_validations : claim.name => claim.value }) == tomap({
        repository_id       = "1001"
        repository_owner_id = "1002"
        environment         = "development"
        ref                 = "refs/heads/master"
        workflow_ref        = "example/tenancy-manager/.github/workflows/infra-development.yml@refs/heads/master"
      })
    )
    error_message = "Bind exactly the approved issuer, audience, application, claims, and propagations."
  }

  assert {
    condition = (
      length(oci_identity_policy.github_identity.statements) == 2 &&
      strcontains(oci_identity_policy.github_identity.statements[0], "target.resource.domain.name = 'Default', target.group.name = 'otm-development-users'") &&
      !strcontains(oci_identity_policy.github_identity.statements[0], "any {target.group.name") &&
      !strcontains(oci_identity_policy.github_identity.statements[1], "target.group.name")
    )
    error_message = "Use a direct group name for the singleton development rule and keep list access separate."
  }

  assert {
    condition = (
      length(oci_identity_domains_setting.signing_keys) == 1 &&
      oci_identity_domains_setting.signing_keys[0].setting_id == "Settings" &&
      oci_identity_domains_setting.signing_keys[0].signing_cert_public_access &&
      oci_identity_domains_setting.signing_keys[0].csr_access == "none" &&
      length(oci_identity_policy.workflow_storage) == 0 &&
      length(oci_identity_policy.workflow_platform) == 0
    )
    error_message = "Development owns non-production Settings and retains its existing bootstrap IAM policy."
  }
}

run "staging_owns_exact_storage_only" {
  command = plan

  variables {
    environment = "staging"
    storage_policy = {
      compartment_ocid = "ocid1.compartment.oc1..syntheticstaging"
      bucket_name      = "otm-staging-tfstate"
      state_key        = "infrastructure/staging/terraform.tfstate"
    }
  }

  assert {
    condition = (
      length(oci_identity_domains_setting.signing_keys) == 0 &&
      length(oci_identity_domains_identity_propagation_trust.github) == 0 &&
      !oci_identity_domains_app.exchange[0].active &&
      oci_identity_domains_app.exchange[0].display_name == "otm-github-staging" &&
      oci_identity_policy.workflow_storage[0].name == "otm-staging-github-infrastructure" &&
      oci_identity_policy.workflow_storage[0].compartment_id == var.storage_policy.compartment_ocid &&
      length(oci_identity_policy.workflow_storage[0].statements) == 8 &&
      alltrue([for statement in oci_identity_policy.workflow_storage[0].statements :
        strcontains(statement, "in compartment otm-staging") &&
        strcontains(statement, "request.principal.type = 'identityfederateddomainapp'") &&
        strcontains(statement, "request.principal.domain.id = 'ocid1.domain.oc1..synthetic'") &&
        strcontains(statement, "request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-staging.yml@refs/heads/master'") &&
        strcontains(statement, "request.principal.ext_environment = 'staging'") &&
        strcontains(statement, "target.bucket.name = 'otm-staging-tfstate'")
      ])
    )
    error_message = "Staging reuses shared Settings and may only access its verified workflow storage."
  }

  assert {
    condition = (
      length([for statement in oci_identity_policy.workflow_storage[0].statements :
        statement if strcontains(statement, "request.operation = 'DeleteObject'")
      ]) == 1 &&
      alltrue([for statement in oci_identity_policy.workflow_storage[0].statements :
        strcontains(statement, "target.object.name = 'infrastructure/staging/terraform.tfstate.lock'") if strcontains(statement, "request.operation = 'DeleteObject'")
      ]) &&
      alltrue([for statement in oci_identity_policy.workflow_storage[0].statements :
        strcontains(statement, "infrastructure-plans/staging/infrastructure/") && !strcontains(statement, "OBJECT_OVERWRITE")
        if strcontains(statement, "plan.tar")
      ])
    )
    error_message = "Only the exact lock may be removed, and saved plans cannot be overwritten."
  }
  assert {
    condition = (
      oci_identity_policy.workflow_platform[0].name == "otm-staging-github-platform" &&
      oci_identity_policy.workflow_platform[0].compartment_id == var.storage_policy.compartment_ocid &&
      length(oci_identity_policy.workflow_platform[0].statements) <= 50 &&
      alltrue([for statement in oci_identity_policy.workflow_platform[0].statements :
        strcontains(statement, "in compartment otm-staging") &&
        strcontains(statement, "request.principal.type = 'identityfederateddomainapp'") &&
        strcontains(statement, "request.principal.domain.id = 'ocid1.domain.oc1..synthetic'") &&
        strcontains(statement, "request.principal.ext_workflow_ref = 'example/tenancy-manager/.github/workflows/infra-staging.yml@refs/heads/master'") &&
        strcontains(statement, "request.principal.ext_environment = 'staging'") &&
        !strcontains(statement, " in tenancy") &&
        !strcontains(statement, "manage all-resources") &&
        !strcontains(statement, "manage policies") &&
        !strcontains(statement, "UpdatePolicy") &&
        !strcontains(statement, "CreatePolicy") &&
        !strcontains(statement, "DeletePolicy") &&
        !strcontains(statement, "LaunchInstance") &&
        !strcontains(statement, "GetSecretBundle") &&
        !strcontains(statement, "terraform.tfstate") &&
        !strcontains(statement, "target.bucket.name")
      ])
    )
    error_message = "Every platform grant must stay bound to this workflow and compartment, without direct IAM mutation, compute launch, or secret-bundle fetch."
  }

  assert {
    condition = (
      alltrue([for operation in ["CreateVcn", "CreateCluster", "CreateNodePool", "CreateDbSystem", "CreateVault", "CreateKey", "CreateSecret"] :
        anytrue([for statement in oci_identity_policy.workflow_platform[0].statements : strcontains(statement, "request.operation = '${operation}'")])
      ]) &&
      one([for statement in oci_identity_policy.workflow_platform[0].statements : statement if strcontains(statement, "manage secrets")]) ==
      "Allow any-user to manage secrets in compartment otm-staging where all {${local.workflow_subject}, target.secret.name = 'otm-staging-database-admin', request.operation = 'CreateSecret', request.permission = 'SECRET_CREATE'}" &&
      one([for statement in oci_identity_policy.workflow_platform[0].statements : statement if strcontains(statement, "inspect policies")]) ==
      "Allow any-user to inspect policies in compartment otm-staging where all {${local.workflow_subject}, target.compartment.id = 'ocid1.compartment.oc1..syntheticstaging', any {target.policy.name = 'otm-staging-database-provisioning-read', target.policy.name = 'otm-staging-api-vault-read', target.policy.name = 'otm-staging-worker-vault-read'}, request.operation = 'GetPolicy'}"
    )
    error_message = "Permit platform creation, one initial named secret, and only exact preapproved runtime policy refreshes."
  }

}

run "production_owns_its_settings" {
  command = plan

  variables {
    environment          = "production"
    identity_domain_ocid = "ocid1.domain.oc1..syntheticproduction"
    owns_domain_settings = true
    storage_policy = {
      compartment_ocid = "ocid1.compartment.oc1..syntheticproduction"
      bucket_name      = "otm-production-tfstate"
      state_key        = "infrastructure/production/terraform.tfstate"
    }
  }

  assert {
    condition = (
      data.oci_identity_domain.selected.domain_id == var.identity_domain_ocid &&
      oci_identity_domains_app.exchange[0].display_name == "otm-github-production" &&
      length(oci_identity_domains_identity_propagation_trust.github) == 1 &&
      one(oci_identity_domains_identity_propagation_trust.github[0].client_claim_values) == "otm-infrastructure-production" &&
      oci_identity_policy.workflow_platform[0].name == "otm-production-github-platform" &&
      alltrue([for statement in oci_identity_policy.workflow_platform[0].statements : strcontains(statement, "request.principal.ext_environment = 'production'") && strcontains(statement, "in compartment otm-production")]) &&
      length(oci_identity_domains_setting.signing_keys) == 1 &&
      oci_identity_domains_setting.signing_keys[0].signing_cert_public_access
    )
    error_message = "Production manages Settings in its own approved identity domain."
  }
}

run "staging_cannot_own_shared_settings" {
  command = plan

  variables {
    environment          = "staging"
    owns_domain_settings = true
  }

  expect_failures = [var.owns_domain_settings]
}

run "reject_non_default_domain" {
  command = plan

  override_data {
    target = data.oci_identity_domain.selected
    values = { display_name = "Unrelated" }
  }

  expect_failures = [data.oci_identity_domain.selected]
}

run "reject_staging_exchange_activation" {
  command = plan

  variables {
    environment  = "staging"
    trust_active = true
  }

  expect_failures = [var.trust_active]
}

run "preserve_existing_working_exchange" {
  command = plan
  variables {
    existing_exchange                 = { id = "11111111111111111111111111111111", name = "synthetic-existing" }
    trust_active                      = true
    exchange_write_response_qualified = false
  }
  assert {
    condition     = length(oci_identity_domains_app.exchange) == 0 && oci_identity_domains_identity_propagation_trust.github[0].active && toset(oci_identity_domains_identity_propagation_trust.github[0].oauth_clients) == toset(["synthetic-existing"])
    error_message = "An active legacy client must have zero native App resources and preserve its trust binding."
  }
}

run "refuse_unqualified_fresh_app" {
  command = plan
  variables { exchange_write_response_qualified = false }
  expect_failures = [var.exchange_write_response_qualified]
}
