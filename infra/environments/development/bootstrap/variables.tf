# A fixed root rejects a target record labeled for the other environment.
variable "target" {
  description = "Approved development target references; never include credentials."
  type = object({
    # Fixed environment label for this root.
    environment = string
    # Non-production root tenancy expected by the operator or federated identity.
    tenancy_ocid = string
    # Object Storage namespace checked against the tenancy during bootstrap.
    object_storage_namespace = string
    # Explicit OCI region for resources and their state bucket.
    region = string
  })
  validation {
    condition     = var.target.environment == "development"
    error_message = "This root accepts only the development environment target record."
  }
}

# Named ~/.oci/config profile used by the local Terraform operator; no browser authentication.
variable "oci_profile" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", var.oci_profile)) && lower(var.oci_profile) != "default"
    error_message = "Select an explicit named development API-key profile, never DEFAULT."
  }
}

# Existing compartment adoption can pin its verified immutable OCID. A new bootstrap omits it.
variable "hosting_compartment_ocid" {
  description = "Optional expected OCID of the adopted development compartment."
  type        = string
  default     = null
  validation {
    condition     = var.hosting_compartment_ocid == null ? true : length(var.hosting_compartment_ocid) <= 255 && can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
    error_message = "Provide the selected environment's existing hosting compartment OCID, at most 255 characters."
  }
}

# Every policy statement matches this non-production identity-domain OCID (at most 255 characters).
# Verify the domain against the GitHub trust and tenancy before supplying this private identifier.
variable "github_identity_domain_ocid" {
  type = string
  validation {
    condition     = length(var.github_identity_domain_ocid) <= 255 && can(regex("^ocid1[.]domain[.]oc1[.][a-z0-9-]*[.][a-z0-9]+$", var.github_identity_domain_ocid))
    error_message = "Provide the verified OCI identity domain OCID, at most 255 characters."
  }
}

# GitHub owner/repository (at most 140 characters) used to bind IAM to the master workflow.
# Limit it to GitHub name characters so the value cannot alter the policy expression.
variable "github_repository" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}$", var.github_repository))
    error_message = "Provide the workflow's GitHub owner/repository without a URL, ref, or wildcard."
  }
}

# Opt in after verifying the Default domain and the laptop's public signing key.
variable "local_app_iam" {
  description = "Optional development laptop identity, public key and enrollment IAM policy."
  type = object({
    # Exact root domain OCID. Never accept a name, wildcard, or free-form policy fragment.
    domain_ocid = string
    # RSA public key in PEM format. The laptop's private key stays in its named OCI profile.
    signing_public_key_pem = string
    # Include the explicit user-create permission only after separate review.
    create_federated_users = optional(bool, false)
  })
  default = null
  validation {
    condition = var.local_app_iam == null ? true : (
      can(regex("^ocid1[.]domain[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", var.local_app_iam.domain_ocid)) &&
      can(regex("^-----BEGIN PUBLIC KEY-----\\n[A-Za-z0-9+/=\\n]+\\n-----END PUBLIC KEY-----$", trimspace(var.local_app_iam.signing_public_key_pem)))
    )
    error_message = "Supply the verified non-production domain OCID and an RSA public signing key in PEM format."
  }
}
