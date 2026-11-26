# The endpoint comes from the same protected environment setting used for federation.
variable "identity_domain_url" {
  description = "HTTPS origin of the production OCI identity domain."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^https://idcs-[a-z0-9]+[.]identity[.]oraclecloud[.]com$", var.identity_domain_url))
    error_message = "Supply the exact OCI identity-domain HTTPS origin."
  }
}

# Only the upstream corporate IdP is an external sign-in dependency.
variable "atlas_sso" {
  description = "Immutable SCIM GUID of the upstream corporate IdP in the selected domain."
  type = object({
    # Existing corporate SAML provider used for both routing and sign-on enforcement.
    corporate_idp_id = string
    # Exact registered HTTPS callback at the hosted installation.
    callback_url = string
  })
  nullable = false
  validation {
    condition     = can(regex("^[a-f0-9]{32}$", var.atlas_sso.corporate_idp_id))
    error_message = "Supply the verified upstream corporate identity-provider GUID."
  }
}

module "atlas_sso" {
  source              = "../../../modules/atlas-sso"
  environment         = var.target.environment
  tenancy_ocid        = var.target.tenancy_ocid
  identity_domain_url = var.identity_domain_url
  corporate_idp_id    = var.atlas_sso.corporate_idp_id
  callback_url        = var.atlas_sso.callback_url
}
