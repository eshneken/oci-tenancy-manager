module "atlas_registration" {
  source      = "../../../modules/application-registration"
  environment = var.target.environment
}

# The endpoint comes from the same protected environment setting used for federation.
variable "identity_domain_url" {
  description = "HTTPS origin of the non-production OCI identity domain."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^https://idcs-[a-z0-9]+[.]identity[.]oraclecloud[.]com$", var.identity_domain_url))
    error_message = "Supply the exact OCI identity-domain HTTPS origin."
  }
}

# Immutable SCIM IDs select the existing assignment group and previously qualified policies.
variable "atlas_sso" {
  description = "Development group, sign-on policy and identity-provider policy SCIM GUIDs."
  type = object({
    # Existing development app-only group. Its members remain managed by Atlas.
    assignment_group_id = string
    # Sign-on policy enforcing the Oracle-only authentication and reauthentication rules.
    signon_policy_id = string
    # Identity-provider routing policy offering corporate SSO to this client.
    idp_policy_id = string
  })
  nullable = false
  validation {
    condition     = alltrue([for id in values(var.atlas_sso) : can(regex("^[a-f0-9]{32}$", id))])
    error_message = "Supply the three verified 32-character development SCIM GUIDs."
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
  attributes           = "id,ocid,name,displayName,description,schemas,basedOnTemplate,active,allowAccessControl,isLoginTarget,isOAuthClient,isOAuthResource,allowedGrants,clientType,redirectUris,trustScope,signonPolicy,idpPolicy"
  active               = false
  allow_access_control = true
  is_login_target      = true
  is_oauth_client      = true
  is_oauth_resource    = false
  client_type          = "confidential"
  allowed_grants       = ["authorization_code"]
  trust_scope          = "Explicit"
  redirect_uris        = ["https://127.0.0.1:8445/api/auth/sso/callback"]
  signon_policy { value = var.atlas_sso.signon_policy_id }
  idp_policy { value = var.atlas_sso.idp_policy_id }

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
    value = var.atlas_sso.assignment_group_id
  }
  lifecycle { prevent_destroy = true }
}
