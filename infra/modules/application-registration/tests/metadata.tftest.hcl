# Verify the exact metadata independently of OCI credentials and state.
run "development" {
  command = plan
  variables { environment = "development" }

  assert {
    condition     = output.display_name == "otm-application-development" && output.description == "Corporate single sign-on for OCI Tenancy Manager."
    error_message = "Development must use the standard display name and neutral description."
  }

  assert {
    condition     = output.group_display_name == "otm-development-users" && output.group_description == "Users assigned to corporate sign-in for OCI Tenancy Manager."
    error_message = "The development assignment group must use the standard name and neutral description."
  }
}

run "staging" {
  command = plan
  variables { environment = "staging" }

  assert {
    condition     = output.display_name == "otm-application-staging" && output.description == run.development.description
    error_message = "Staging must have its own app name and the shared description."
  }

  assert {
    condition     = output.group_display_name == "otm-staging-users" && output.group_description == run.development.group_description
    error_message = "The staging assignment group must use the standard name and neutral description."
  }
}

run "production" {
  command = plan
  variables { environment = "production" }

  assert {
    condition     = output.display_name == "otm-application-production" && output.description == run.development.description
    error_message = "Production must have its own app name and the shared description."
  }

  assert {
    condition     = output.group_display_name == "otm-production-users" && output.group_description == run.development.group_description
    error_message = "The production assignment group must use the standard name and neutral description."
  }
}

# Reject ad hoc labels so the display name cannot drift from the environment convention.
run "unexpected_environment" {
  command = plan
  variables { environment = "preview" }

  expect_failures = [var.environment]
}
