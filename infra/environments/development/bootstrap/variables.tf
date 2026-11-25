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

# Operator-supplied OCID for the existing top-level development compartment.
# Syntax does not establish tenancy ownership or permission; independently verify both before apply.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = length(var.hosting_compartment_ocid) <= 255 && can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
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

# Opt in only after verifying these private OCI identities and approving the root attachment.
variable "local_app_iam" {
  description = "Optional development laptop IAM enrollment scope; null adds no policy."
  type = object({
    # Exact root domain OCID. Never accept a display name, wildcard, or free-form policy fragment.
    domain_ocid = string
    # OCI group OCID for the development laptop principal.
    writer_group_ocid = string
    # OCI group OCID for development Atlas assignment, distinct from the signer group.
    assignment_group_ocid = string
    # Include the explicit user-create permission only after separate review.
    create_federated_users = optional(bool, false)
  })
  default = null
  validation {
    condition = var.local_app_iam == null ? true : (
      can(regex("^ocid1[.]domain[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", var.local_app_iam.domain_ocid)) &&
      alltrue([for ocid in [var.local_app_iam.writer_group_ocid, var.local_app_iam.assignment_group_ocid] :
        can(regex("^ocid1[.]group[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", ocid))
      ]) &&
      var.local_app_iam.writer_group_ocid != var.local_app_iam.assignment_group_ocid
    )
    error_message = "Provide the exact non-prod domain and two distinct group OCIDs."
  }
}
