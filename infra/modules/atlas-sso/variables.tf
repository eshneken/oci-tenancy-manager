# Deployment label validated by the common registration module.
variable "environment" { type = string }
# Native groups are owned by this tenancy's Default domain.
variable "tenancy_ocid" { type = string }
# Upstream corporate SAML provider registered in this domain.
variable "corporate_idp_id" { type = string }
# Exact identity domain origin used by this environment's protected workflow.
variable "identity_domain_url" {
  type = string
  validation {
    condition     = can(regex("^https://idcs-[a-z0-9]+[.]identity[.]oraclecloud[.]com$", var.identity_domain_url))
    error_message = "Supply the verified OCI HTTPS identity domain origin."
  }
}
# Hosted callbacks require a DNS hostname and the backend's fixed callback path.
variable "callback_url" {
  type = string
  validation {
    condition = var.environment == "development" ? (
      var.callback_url == "https://127.0.0.1:8445/api/auth/sso/callback"
    ) : can(regex("^https://[a-z0-9-]+([.][a-z0-9-]+)+/api/auth/sso/callback$", var.callback_url))
    error_message = "Supply the exact HTTPS installation callback."
  }
}
