terraform {
  required_version = "= 1.15.5"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.13.0"
    }
  }
}

# The owning root supplies the Identity Domains origin for the selected environment.
variable "identity_domain_url" {
  description = "HTTPS origin of the OCI identity domain that owns the client and provider."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^https://idcs-[a-z0-9]+[.]identity[.]oraclecloud[.]com$", var.identity_domain_url))
    error_message = "Supply the exact OCI identity-domain HTTPS origin."
  }
}

# The approved upstream SAML provider remains under domain administration.
variable "corporate_idp_id" {
  description = "Immutable SCIM identifier of the approved upstream corporate SAML provider in this domain."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-f0-9]{32}$", var.corporate_idp_id))
    error_message = "Supply the upstream provider's 32-character SCIM identifier."
  }
}

# Development and staging share a domain, so each environment has distinct policy names.
variable "environment" {
  description = "Atlas environment whose client will bind these policies."
  type        = string
  nullable    = false

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

locals {
  prefix       = "otm-${var.environment}"
  upstream_ids = jsonencode([var.corporate_idp_id])

  # These are the pilot's SCIM conditions and rule returns. The allow case must precede denial.
  rules = {
    discover = {
      name        = "idp-discovery"
      policy_type = "IdentityProvider"
      attribute   = "operation"
      operator    = "eq"
      value       = "IDP Discovery"
      returns = [
        { name = "userChoice", value = "false" },
        { name = "LocalIDPs", value = "[]" },
        { name = "SamlIDPs", value = local.upstream_ids },
        { name = "SocialIDPs", value = "[]" },
        { name = "X509IDPs", value = "[]" },
      ]
    }
    allow = {
      name        = "sign-on-allow-corporate"
      policy_type = "SignOn"
      attribute   = "subject.authenticatedBy"
      operator    = "in"
      value       = local.upstream_ids
      returns = [
        { name = "effect", value = "ALLOW" },
        { name = "reAuthenticate", value = "true" },
        { name = "authenticationFactor", value = "IDP" },
      ]
    }
    deny = {
      name        = "sign-on-deny-other"
      policy_type = "SignOn"
      attribute   = "target.action"
      operator    = "eq"
      value       = jsonencode("Login")
      returns     = [{ name = "effect", value = "DENY" }]
    }
  }
}

resource "oci_identity_domains_condition" "atlas" {
  for_each = local.rules

  idcs_endpoint   = var.identity_domain_url
  schemas         = ["urn:ietf:params:scim:schemas:oracle:idcs:Condition"]
  name            = "${local.prefix}-${each.value.name}-condition"
  attribute_name  = each.value.attribute
  operator        = each.value.operator
  attribute_value = each.value.value
}

resource "oci_identity_domains_rule" "atlas" {
  for_each = local.rules

  idcs_endpoint = var.identity_domain_url
  schemas       = ["urn:ietf:params:scim:schemas:oracle:idcs:Rule"]
  name          = "${local.prefix}-${each.value.name}"

  # The provider requires the deprecated string. OCI's pilot uses only the Condition resource.
  condition = ""
  condition_group {
    type  = "Condition"
    value = oci_identity_domains_condition.atlas[each.key].id
  }
  policy_type {
    value = each.value.policy_type
  }
  dynamic "return" {
    for_each = each.value.returns
    iterator = response
    content {
      name  = response.value.name
      value = response.value.value
    }
  }
}

# The caller attaches this policy only to its own Atlas App.
resource "oci_identity_domains_policy" "idp" {
  idcs_endpoint = var.identity_domain_url
  schemas       = ["urn:ietf:params:scim:schemas:oracle:idcs:Policy"]
  name          = "${local.prefix}-idp"
  description   = "Selects the corporate identity provider for application sign-in."
  active        = true

  # Policy rules are returned only when requested explicitly.
  attributes = "id,schemas,name,description,active,policyType,rules"
  policy_type {
    value = "IdentityProvider"
  }
  rules {
    sequence = 1
    value    = oci_identity_domains_rule.atlas["discover"].id
  }
}

# Require a fresh corporate sign-in before the catch-all login denial can take effect.
resource "oci_identity_domains_policy" "signon" {
  idcs_endpoint = var.identity_domain_url
  schemas       = ["urn:ietf:params:scim:schemas:oracle:idcs:Policy"]
  name          = "${local.prefix}-sign-on"
  description   = "Requires corporate reauthentication for application sign-in."
  active        = true

  attributes = "id,schemas,name,description,active,policyType,rules"
  policy_type {
    value = "SignOn"
  }
  rules {
    sequence = 1
    value    = oci_identity_domains_rule.atlas["allow"].id
  }
  rules {
    sequence = 2
    value    = oci_identity_domains_rule.atlas["deny"].id
  }
}

output "idp_policy_id" {
  description = "SCIM identifier for the Atlas client identity-provider policy binding."
  value       = oci_identity_domains_policy.idp.id
}

output "signon_policy_id" {
  description = "SCIM identifier for the Atlas client sign-on policy binding."
  value       = oci_identity_domains_policy.signon.id
}
