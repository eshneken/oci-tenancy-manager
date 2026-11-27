# Apply-phase mocks let SCIM resolve the GUID only after native group creation.
mock_provider "oci" {
  override_during = apply

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

  mock_resource "oci_identity_dynamic_group" {
    defaults = {
      id    = "ocid1.dynamicgroup.oc1..synthetic"
      state = "ACTIVE"
    }
  }

  mock_data "oci_identity_domains_dynamic_resource_groups" {
    defaults = {
      total_results = 1
      dynamic_resource_groups = [{
        id            = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ocid          = "ocid1.dynamicgroup.oc1..synthetic"
        display_name  = "otm-development-github-identity"
        domain_ocid   = "ocid1.domain.oc1..synthetic"
        tenancy_ocid  = "ocid1.tenancy.oc1..synthetic"
        matching_rule = "resource.id = 'ocid1.identityfederateddomainapp.oc1..synthetic'"
      }]
    }
  }

  mock_data "oci_identity_domain" {
    defaults = {
      compartment_id = "ocid1.tenancy.oc1..synthetic"
      state          = "ACTIVE"
      display_name   = "Default"
      url            = "https://idcs-synthetic.identity.oraclecloud.com:443/"
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

run "fresh_development_workflow_owns_exact_group_and_role" {
  command = apply

  variables {
    development_workflow_dynamic_group = {
      principal_ocid = "ocid1.identityfederateddomainapp.oc1..synthetic"
      create_fresh   = true
    }
  }

  assert {
    condition = (
      length(data.oci_identity_domains_dynamic_resource_group.development_workflow) == 0 &&
      length(data.oci_identity_domains_grant.development_application_administrator) == 0 &&
      oci_identity_dynamic_group.development_workflow[0].name == "otm-development-github-identity" &&
      oci_identity_dynamic_group.development_workflow[0].matching_rule == "resource.id = 'ocid1.identityfederateddomainapp.oc1..synthetic'" &&
      oci_identity_domains_grant.development_application_administrator[0].grant_mechanism == "ADMINISTRATOR_TO_DYNAMIC_RESOURCE_GROUP" &&
      one(oci_identity_domains_grant.development_application_administrator[0].grantee).value == one(data.oci_identity_domains_dynamic_resource_groups.fresh_development_workflow[0].dynamic_resource_groups).id &&
      one(oci_identity_domains_grant.development_application_administrator[0].grantee).type == "DynamicResourceGroup" &&
      one(oci_identity_domains_grant.development_application_administrator[0].app).value == "IDCSAppId" &&
      one(oci_identity_domains_grant.development_application_administrator[0].entitlement).attribute_name == "appRoles" &&
      one(oci_identity_domains_grant.development_application_administrator[0].entitlement).attribute_value == "cccccccccccccccccccccccccccccccc"
    )
    error_message = "Explicit fresh creation can only register the exact development principal and its selected built-in role."
  }
}
