# Verify the development bootstrap without reading a local signing profile or contacting OCI.
mock_provider "oci" {
  mock_data "oci_identity_compartment" {
    defaults = {
      name           = "otm-development"
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
    }
  }
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticnamespace" }
  }
}
variables {
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
    condition     = output.state_backend.bucket == "otm-development-tfstate" && output.state_backend.key == "custody/development/terraform.tfstate"
    error_message = "Development uses its own bucket and custody key."
  }
}
run "reject_default_profile" {
  command = plan
  variables { oci_profile = "DEFAULT" }
  expect_failures = [var.oci_profile]
}
run "reject_unrelated_compartment" {
  command = plan
  override_data {
    target = data.oci_identity_compartment.development
    values = { name = "other-compartment" }
  }
  expect_failures = [data.oci_identity_compartment.development]
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
        strcontains(statement, "in compartment id ${var.hosting_compartment_ocid}") &&
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
