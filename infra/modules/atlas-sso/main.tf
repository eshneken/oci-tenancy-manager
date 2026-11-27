terraform {
  required_providers {
    oci = { source = "oracle/oci", version = "= 9.14.0" }
  }
}

module "atlas_registration" {
  source      = "../application-registration"
  environment = var.environment
}

module "atlas_policies" {
  source              = "../atlas-sign-in-policies"
  environment         = var.environment
  identity_domain_url = var.identity_domain_url
  corporate_idp_id    = var.corporate_idp_id
}

# Native Default-domain group operations never enumerate or replace memberships.
resource "oci_identity_group" "users" {
  compartment_id = var.tenancy_ocid
  name           = module.atlas_registration.group_display_name
  description    = module.atlas_registration.group_description
  lifecycle { prevent_destroy = true }
}

# The assignment API needs the SCIM GUID rather than the native group OCID.
data "oci_identity_domains_groups" "atlas_users" {
  idcs_endpoint = var.identity_domain_url
  group_filter  = "ocid eq \"${oci_identity_group.users.id}\""
  attributes    = "id,ocid,displayName"
  lifecycle {
    postcondition {
      condition = try(
        self.total_results == 1 &&
        one(self.groups).ocid == oci_identity_group.users.id &&
        try(length(one(self.groups).members), 0) == 0 &&
        one(self.groups).display_name == oci_identity_group.users.name &&
        can(regex("^[a-f0-9]{32}$", one(self.groups).id)),
        false
      )
      error_message = "Expected the single managed Atlas group in this identity domain."
    }
  }
}

resource "oci_identity_domains_app" "atlas_sso" {
  idcs_endpoint = var.identity_domain_url
  schemas       = ["urn:ietf:params:scim:schemas:oracle:idcs:App"]
  display_name  = module.atlas_registration.display_name
  description   = module.atlas_registration.description
  based_on_template {
    value = "CustomWebAppTemplateId"
  }

  # Oracle returns clientSecret on default reads. Create, update and refresh must use this projection.
  attributes = "id,ocid,name,displayName,description,schemas,basedOnTemplate,active,allowAccessControl,isLoginTarget,loginMechanism,isOAuthClient,isOAuthResource,allowedGrants,clientType,redirectUris,trustScope,signonPolicy,idpPolicy"
  # OCI requires the target App to be active before it can receive its group assignment.
  active               = true
  allow_access_control = true
  is_login_target      = true
  login_mechanism      = "OIDC"
  is_oauth_client      = true
  is_oauth_resource    = false
  client_type          = "confidential"
  allowed_grants       = ["authorization_code"]
  trust_scope          = "Explicit"
  redirect_uris        = [var.callback_url]
  signon_policy { value = module.atlas_policies.signon_policy_id }
  idp_policy { value = module.atlas_policies.idp_policy_id }

  lifecycle { prevent_destroy = true }
}

# This additional assignment leaves the original app grant and every group membership intact.
resource "oci_identity_domains_grant" "atlas_assignment" {
  idcs_endpoint   = var.identity_domain_url
  schemas         = ["urn:ietf:params:scim:schemas:oracle:idcs:Grant"]
  grant_mechanism = "ADMINISTRATOR_TO_GROUP"
  app { value = oci_identity_domains_app.atlas_sso.id }
  grantee {
    type  = "Group"
    value = one(data.oci_identity_domains_groups.atlas_users.groups).id
  }
  lifecycle { prevent_destroy = true }
}
