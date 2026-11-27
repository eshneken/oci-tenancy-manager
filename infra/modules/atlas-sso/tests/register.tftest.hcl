mock_provider "oci" { override_during = apply }
override_resource {
  target          = oci_identity_group.users
  override_during = apply
  values          = { id = "ocid1.group.oc1..synthetic" }
}
override_data {
  target          = data.oci_identity_domains_groups.atlas_users
  override_during = apply
  values = {
    total_results = 1
    groups = [{
      id           = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      ocid         = "ocid1.group.oc1..synthetic"
      display_name = "otm-development-users"
    }]
  }
}
override_module {
  target  = module.atlas_policies
  outputs = { signon_policy_id = "signon", idp_policy_id = "idp" }
}
variables {
  environment         = "development"
  tenancy_ocid        = "ocid1.tenancy.oc1..synthetic"
  identity_domain_url = "https://idcs-synthetic.identity.oraclecloud.com"
  corporate_idp_id    = "dddddddddddddddddddddddddddddddd"
  callback_url        = "https://127.0.0.1:8445/api/auth/sso/callback"
}
run "enable_assigned_sso_client" {
  command = apply
  assert {
    condition = (
      oci_identity_domains_app.atlas_sso.display_name == "otm-sso-development" &&
      oci_identity_domains_app.atlas_sso.active &&
      oci_identity_domains_app.atlas_sso.allow_access_control &&
      oci_identity_domains_app.atlas_sso.login_mechanism == "OIDC" &&
      contains(split(",", oci_identity_domains_app.atlas_sso.attributes), "loginMechanism") &&
      oci_identity_domains_app.atlas_sso.client_type == "confidential" &&
      one(oci_identity_domains_app.atlas_sso.redirect_uris) == "https://127.0.0.1:8445/api/auth/sso/callback" &&
      one(oci_identity_domains_app.atlas_sso.allowed_grants) == "authorization_code" &&
      one(oci_identity_domains_app.atlas_sso.signon_policy).value == module.atlas_policies.signon_policy_id &&
      one(oci_identity_domains_app.atlas_sso.idp_policy).value == module.atlas_policies.idp_policy_id &&
      oci_identity_domains_app.atlas_sso.attributes != "" &&
      !strcontains(lower(oci_identity_domains_app.atlas_sso.attributes), "secret") &&
      oci_identity_domains_grant.atlas_assignment.grant_mechanism == "ADMINISTRATOR_TO_GROUP" &&
      one(oci_identity_domains_grant.atlas_assignment.grantee).type == "Group" &&
      one(oci_identity_domains_grant.atlas_assignment.grantee).value == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    error_message = "Enable the scoped laptop client with its existing group assignment."
  }
}

# OCI may change its projection behavior. Stop before granting if it returns any members.
run "reject_scim_group_member_projection" {
  command = plan
  override_resource {
    target          = oci_identity_group.users
    override_during = plan
    values          = { id = "ocid1.group.oc1..synthetic" }
  }
  override_data {
    target          = data.oci_identity_domains_groups.atlas_users
    override_during = plan
    values = {
      total_results = 1
      groups = [{
        id           = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ocid         = "ocid1.group.oc1..synthetic"
        display_name = "otm-development-users"
        members      = [{ value = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }]
      }]
    }
  }
  expect_failures = [data.oci_identity_domains_groups.atlas_users]
}
