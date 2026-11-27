terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.14.0"
    }
  }
}

data "oci_identity_domain" "selected" {
  domain_id = var.identity_domain_ocid

  lifecycle {
    postcondition {
      condition = (
        self.compartment_id == var.tenancy_ocid &&
        self.state == "ACTIVE" &&
        self.display_name == local.identity_domain_name &&
        can(regex("^https://idcs-[a-z0-9]+[.]identity[.]oraclecloud[.]com(:443)?$", trimsuffix(self.url, "/")))
      )
      error_message = "Expected the active Default identity domain at the selected tenancy root."
    }
  }
}

locals {
  identity_domain_name = "Default"
  # OCI can report the default HTTPS port; downstream endpoints use a canonical origin.
  domain_url    = trimsuffix(trimsuffix(data.oci_identity_domain.selected.url, "/"), ":443")
  display_name  = "otm-github-${var.environment}"
  exchange_name = var.existing_exchange == null ? oci_identity_domains_app.exchange[0].name : var.existing_exchange.name
  exchange_id   = var.existing_exchange == null ? oci_identity_domains_app.exchange[0].id : var.existing_exchange.id

  # Request metadata only. Native creation requires separate evidence that OCI honors this projection
  # on write responses with the pinned provider. Import uses an unprojected initial read.
  client_attributes = "id,name,displayName,description,schemas,basedOnTemplate,active,allowAccessControl,isLoginTarget,isOAuthClient,isOAuthResource,allowedGrants,clientType,trustScope,allowedScopes,appRoles,grantedAppRoles"
}

# Native ownership is restricted to qualified fresh clients. Legacy development reads metadata only.
resource "oci_identity_domains_app" "exchange" {
  count                = var.existing_exchange == null ? 1 : 0
  idcs_endpoint        = local.domain_url
  schemas              = ["urn:ietf:params:scim:schemas:oracle:idcs:App"]
  attributes           = local.client_attributes
  display_name         = local.display_name
  description          = "Confidential token-exchange client for the protected OTM ${var.environment} infrastructure workflow."
  active               = var.trust_active
  allow_access_control = false
  is_login_target      = false
  is_oauth_client      = true
  is_oauth_resource    = false
  allowed_grants       = ["client_credentials"]
  client_type          = "confidential"
  trust_scope          = "Explicit"

  based_on_template {
    value = "CustomWebAppTemplateId"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# The non-production domain has a single GitHub issuer trust, owned by development.
# The provider's independent audience/client lists cannot bind a staging client to a staging JWT.
resource "oci_identity_domains_identity_propagation_trust" "github" {
  count                  = var.environment == "staging" ? 0 : 1
  idcs_endpoint          = local.domain_url
  schemas                = ["urn:ietf:params:scim:schemas:oracle:idcs:IdentityPropagationTrust"]
  name                   = local.display_name
  type                   = "JWT"
  issuer                 = "https://token.actions.githubusercontent.com"
  public_key_endpoint    = "https://token.actions.githubusercontent.com/.well-known/jwks"
  active                 = var.trust_active
  allow_impersonation    = true
  subject_type           = "Resource"
  impersonating_resource = "githubactions"
  oauth_clients          = [local.exchange_name]
  client_claim_name      = "aud"
  client_claim_values    = ["otm-infrastructure-${var.environment}"]
  claim_propagations     = ["ext_workflow_ref", "ext_environment"]

  claim_validations {
    name  = "repository_id"
    value = var.github.repository_id
  }
  claim_validations {
    name  = "repository_owner_id"
    value = var.github.repository_owner_id
  }
  claim_validations {
    name  = "environment"
    value = var.environment
  }
  claim_validations {
    name  = "ref"
    value = "refs/heads/master"
  }
  claim_validations {
    name  = "workflow_ref"
    value = local.workflow_ref
  }

  lifecycle {
    prevent_destroy = true
  }
}

# The owner imports this singleton before any apply because the provider uses ReplaceSettings.
resource "oci_identity_domains_setting" "signing_keys" {
  count                      = var.owns_domain_settings ? 1 : 0
  idcs_endpoint              = local.domain_url
  schemas                    = ["urn:ietf:params:scim:schemas:oracle:idcs:Settings"]
  setting_id                 = "Settings"
  csr_access                 = var.settings_csr_access
  signing_cert_public_access = true

  lifecycle {
    prevent_destroy = true
    # The locked provider imports the canonical Settings ID but leaves this ForceNew input unset.
    # Its Update path uses the imported ID. Keep every actual Settings attribute in the diff.
    ignore_changes = [setting_id]
  }
}

output "exchange_client_name" {
  description = "OAuth client ID for the protected GitHub environment."
  value       = local.exchange_name
  sensitive   = true
}

output "identity_domain_url" {
  description = "Verified identity-domain HTTPS origin for the protected GitHub environment."
  sensitive   = true
  value       = local.domain_url
}

output "exchange_app_id" {
  description = "Exact exchange App SCIM GUID for the operator's separate credential handoff."
  sensitive   = true
  value       = local.exchange_id
}
