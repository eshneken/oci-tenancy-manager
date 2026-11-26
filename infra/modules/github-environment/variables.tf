# Fixed deployment environment controls the workflow input contract and environment resource name.
variable "environment" {
  type     = string
  nullable = false
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Choose a supported OTM environment."
  }
}

# Exact owner/repository pair must also select the root provider owner to constrain all writes.
variable "repository" {
  type     = string
  nullable = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9-]{1,39}/[a-zA-Z0-9_.-]{1,100}$", var.repository))
    error_message = "Specify the exact GitHub owner/repository."
  }
}

# Match the numeric repository identity pinned by the OCI token-exchange trust.
variable "repository_id" {
  type     = string
  nullable = false
}

# Full CI target coordinates come from the same operator bootstrap that owns remote state.
variable "target" {
  type = object({
    environment              = string
    tenancy_ocid             = string
    object_storage_namespace = string
    region                   = string
  })
}

# Private bootstrap references drive an exact, credential-filtered OCI application lookup.
variable "exchange_app_id" {
  type      = string
  sensitive = true
}

# Expected immutable OAuth client identifier verified against the scoped GetApp response.
variable "exchange_client_name" {
  type      = string
  sensitive = true
}

# Trusted HTTPS identity-domain origin verified by the operator root's OCI domain lookup.
variable "identity_domain_url" {
  type      = string
  sensitive = true
}

# Managed hosting compartment from the same bootstrap determines state-bucket placement.
variable "hosting_compartment_ocid" {
  type = string
}

# Explicit local OCI CLI profile identifies the bootstrap operator during secret sealing.
variable "oci_profile" {
  type = string
}

# Match the root's approved operator authentication scheme for the single GetApp call.
variable "oci_auth" {
  type = string
}

# Private GitHub environment controls. Sensitive configuration file contents never enter HCL.
variable "controls" {
  type = object({
    # GitHub integer user IDs allowed to review a deployment; the combined reviewer limit is six.
    reviewer_user_ids = optional(set(number), [])
    # GitHub integer team IDs with deployment approval; at least one user or team is required.
    reviewer_team_ids = optional(set(number), [])
    # Require a different approver when enabled; the laptop pilot permits the same operator.
    prevent_self_review = optional(bool, false)
    # Filename of owner-only deployment configuration under the checkout's ignored .local-dev.
    settings_file = string
    # Increment this positive integer when rotating the exchange credential's sealed delivery.
    secret_revision = optional(number, 1)
    # Permit read-only GitHub plans after bootstrap qualification.
    plan_enabled = optional(bool, false)
    # Permit gated GitHub apply of an approved saved plan only during an authorized rollout.
    apply_enabled = optional(bool, false)
    # Hosted OKE version in vX.Y.Z format, set only for the two hosted environments.
    kubernetes_version = optional(string)
    # Hosted PostgreSQL two-digit major, set only for the two hosted environments.
    postgresql_version = optional(string)
  })
  nullable = false
  validation {
    condition = (
      length(var.controls.reviewer_user_ids) + length(var.controls.reviewer_team_ids) >= 1 &&
      length(var.controls.reviewer_user_ids) + length(var.controls.reviewer_team_ids) <= 6 &&
      alltrue([for id in concat(tolist(var.controls.reviewer_user_ids), tolist(var.controls.reviewer_team_ids)) : id > 0 && id == floor(id)]) &&
      var.controls.secret_revision >= 1 && var.controls.secret_revision == floor(var.controls.secret_revision) &&
      (!var.controls.apply_enabled || var.controls.plan_enabled) &&
      can(regex("^[a-zA-Z0-9][a-zA-Z0-9._-]{0,126}[.]json$", var.controls.settings_file))
    )
    error_message = "Provide 1–6 GitHub reviewers, a private JSON filename, a positive rotation revision, and enable plan before apply."
  }
}
