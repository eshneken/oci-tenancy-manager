# Isolate the protected deployment and encrypted delivery contract from both external services.
mock_provider "github" {
  override_during = plan
  mock_data "github_repository" {
    defaults = { name = "tenancy-manager", full_name = "example/tenancy-manager", repo_id = 1001 }
  }
  mock_data "github_actions_environment_public_key" {
    defaults = { key = "synthetic-public-key", key_id = "12345" }
  }
  mock_data "github_repository_environment_deployment_policies" {
    defaults = { policies = [{ type = "branch", pattern = "master" }] }
  }
}
mock_provider "external" {
  override_during = plan
  mock_data "external" {
    defaults = {
      result = {
        input_digest                   = "synthetic-fingerprint"
        OTM_INFRASTRUCTURE_INPUTS_JSON = "c3ludGhldGlj"
        OTM_INFRA_IDENTITY_DOMAIN_URL  = "c3ludGhldGlj"
        OTM_INFRA_CLIENT_ID            = "c3ludGhldGlj"
        OTM_INFRA_CLIENT_SECRET        = "c3ludGhldGlj"
        OTM_HOSTING_COMPARTMENT_OCID   = "c3ludGhldGlj"
        OTM_ALLOWED_SOURCE_CIDRS       = "c3ludGhldGlj"
        OTM_WORKER_CLOUD_INIT          = "c3ludGhldGlj"
      }
    }
  }
}
variables {
  environment              = "development"
  repository               = "example/tenancy-manager"
  repository_id            = "1001"
  exchange_app_id          = "syntheticapp"
  exchange_client_name     = "syntheticexchange"
  identity_domain_url      = "https://idcs-synthetic.identity.oraclecloud.com"
  hosting_compartment_ocid = "ocid1.compartment.oc1..synthetic"
  oci_profile              = "SYNTHETIC"
  oci_auth                 = "APIKey"
  target = {
    environment  = "development", region = "us-ashburn-1",
    tenancy_ocid = "ocid1.tenancy.oc1..synthetic", object_storage_namespace = "synthetic"
  }
  controls = { settings_file = "synthetic.json", reviewer_user_ids = [101] }
}
run "protect_development_and_deliver_only_sealed_values" {
  command = apply
  assert {
    condition = (
      !github_repository_environment.deployment.can_admins_bypass &&
      !github_repository_environment.deployment.prevent_self_review &&
      contains(one(github_repository_environment.deployment.reviewers).users, 101) &&
      one(github_repository_environment.deployment.deployment_branch_policy).custom_branch_policies &&
      github_repository_environment_deployment_policy.master.branch_pattern == "master" &&
      length(github_actions_environment_secret.workflow) == 5 &&
      alltrue([for s in github_actions_environment_secret.workflow : s.key_id == "12345" && s.value_encrypted == "c3ludGhldGlj"]) &&
      alltrue([for v in github_actions_environment_variable.workflow : v.value == "false"])
    )
    error_message = "Development requires protected master, encrypted delivery and both gates held."
  }
}
run "deliver_hosted_inputs" {
  command = plan
  variables {
    environment = "production"
    controls = {
      settings_file      = "synthetic.json", reviewer_team_ids = [102], prevent_self_review = true,
      kubernetes_version = "v1.34.1", postgresql_version = "16"
    }
  }
  assert {
    condition = (
      github_repository_environment.deployment.prevent_self_review &&
      length(github_actions_environment_secret.workflow) == 7 &&
      contains(keys(github_actions_environment_secret.workflow), "OTM_WORKER_CLOUD_INIT") &&
      github_actions_environment_variable.workflow["OTM_POSTGRESQL_VERSION"].value == "16"
    )
    error_message = "Hosted deployments require both extra secrets and selected versions."
  }
}
run "reject_unprotected_environment" {
  command = plan
  variables {
    controls = { settings_file = "synthetic.json" }
  }
  expect_failures = [var.controls]
}
run "reject_unbound_apply" {
  command = plan
  variables {
    controls = { settings_file = "synthetic.json", reviewer_user_ids = [101], apply_enabled = true }
  }
  expect_failures = [var.controls]
}
