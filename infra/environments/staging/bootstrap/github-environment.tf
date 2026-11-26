# The operator supplies a GitHub credential through GITHUB_TOKEN.
provider "github" {
  owner = split("/", var.github_delivery.repository)[0]
}

variable "github_environment" {
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
    condition     = !var.github_environment.plan_enabled && !var.github_environment.apply_enabled
    error_message = "Staging workflow dispatch is held until a client-bound federation design has been qualified."
  }
}

module "github_environment" {
  source                   = "../../../modules/github-environment"
  environment              = "staging"
  repository               = var.github_delivery.repository
  repository_id            = var.github_delivery.repository_id
  controls                 = var.github_environment
  target                   = var.target
  hosting_compartment_ocid = oci_identity_compartment.hosting.id
  exchange_app_id          = module.delivery.exchange_app_id
  exchange_client_name     = module.delivery.exchange_client_name
  identity_domain_url      = module.delivery.identity_domain_url
  oci_profile              = var.oci_profile
  oci_auth                 = var.oci_auth
}
