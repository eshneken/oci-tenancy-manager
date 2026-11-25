# Exercise the proposed Identity Domains policy without a live signer or OCI access.
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
  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      display_name   = "Default"
      state          = "ACTIVE"
    }
  }
  mock_data "oci_identity_group" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
    }
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

override_data {
  target = data.oci_identity_group.local_app_writer[0]
  values = {
    name           = "otm-development-localapp"
    compartment_id = "ocid1.tenancy.oc1..synthetic"
    state          = "ACTIVE"
  }
}

override_data {
  target = data.oci_identity_group.local_app_assignment[0]
  values = {
    name           = "otm-development-users"
    compartment_id = "ocid1.tenancy.oc1..synthetic"
    state          = "ACTIVE"
  }
}

run "defaults_do_not_grant_laptop_permissions" {
  command = plan
  assert {
    condition     = length(oci_identity_policy.local_app) == 0
    error_message = "An existing bootstrap must not acquire a laptop writer grant by default."
  }
}

run "laptop_membership_policy_targets_only_the_selected_group" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid           = "ocid1.domain.oc1..synthetic"
      writer_group_ocid     = "ocid1.group.oc1..writer"
      assignment_group_ocid = "ocid1.group.oc1..assignment"
    }
  }
  assert {
    condition = (
      oci_identity_policy.local_app[0].name == "otm-development-localapp" &&
      oci_identity_policy.local_app[0].compartment_id == var.target.tenancy_ocid &&
      length(oci_identity_policy.local_app[0].statements) == 2 &&
      alltrue([for statement in oci_identity_policy.local_app[0].statements :
        startswith(statement, "Allow group Default/otm-development-localapp to ") &&
        (strcontains(statement, "target.resource.domain.name = 'Default'") || contains([
          "Allow group Default/otm-development-localapp to inspect users in tenancy",
        ], statement) || (strcontains(statement, " to use ") || strcontains(statement, " to use groups ")))
      ])
    )
    error_message = "Every grant must use the selected signer group. Only native inspection and membership may omit the domain."
  }
  assert {
    condition = one([for statement in oci_identity_policy.local_app[0].statements :
      statement if strcontains(statement, " to use users ")
    ]) == "Allow group Default/otm-development-localapp to use users in tenancy"
    error_message = "User update permission is scoped to the selected tenancy."
  }
  assert {
    condition = (
      length([for statement in oci_identity_policy.local_app[0].statements :
        statement if strcontains(statement, " to use groups ")
      ]) == 1 &&
      alltrue([for statement in oci_identity_policy.local_app[0].statements :
        !strcontains(statement, "request.operation") &&
        !strcontains(statement, "target.group")
        if strcontains(statement, " to use groups ")
      ]) &&
      alltrue([for statement in oci_identity_policy.local_app[0].statements :
        !strcontains(statement, "CreateUser") && !strcontains(statement, "DELETE") &&
        !strcontains(statement, "request.permission") &&
        !strcontains(statement, "organizations-")
      ])
    )
    error_message = "Group updates must stay scoped to the verified assignment group and domain."
  }
}

run "user_creation_requires_an_explicit_opt_in" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid            = "ocid1.domain.oc1..synthetic"
      writer_group_ocid      = "ocid1.group.oc1..writer"
      assignment_group_ocid  = "ocid1.group.oc1..assignment"
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

run "writer_and_assignment_groups_must_be_distinct" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid           = "ocid1.domain.oc1..synthetic"
      writer_group_ocid     = "ocid1.group.oc1..writer"
      assignment_group_ocid = "ocid1.group.oc1..writer"
    }
  }
  expect_failures = [var.local_app_iam]
}

run "wrong_assignment_group_is_rejected" {
  command = plan
  variables {
    local_app_iam = {
      domain_ocid           = "ocid1.domain.oc1..synthetic"
      writer_group_ocid     = "ocid1.group.oc1..writer"
      assignment_group_ocid = "ocid1.group.oc1..assignment"
    }
  }
  override_data {
    target = data.oci_identity_group.local_app_assignment[0]
    values = {
      name           = "otm-staging-users"
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
    }
  }
  expect_failures = [data.oci_identity_group.local_app_assignment]
}
