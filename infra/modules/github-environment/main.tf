terraform {
  required_version = "= 1.15.5"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "= 6.13.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "= 2.3.5"
    }
  }
}

locals {
  repository_name = split("/", var.repository)[1]
  secret_names = setunion(
    toset(["OTM_INFRASTRUCTURE_INPUTS_JSON", "OTM_INFRA_IDENTITY_DOMAIN_URL", "OTM_INFRA_CLIENT_ID", "OTM_INFRA_CLIENT_SECRET", "OTM_HOSTING_COMPARTMENT_OCID"]),
    var.environment == "development" ? toset([]) : toset(["OTM_ALLOWED_SOURCE_CIDRS", "OTM_WORKER_CLOUD_INIT"])
  )
}

# A repository renamed/transferred since bootstrap must never receive environment credentials by name.
data "github_repository" "bound" {
  full_name = var.repository
  lifecycle {
    postcondition {
      condition     = self.full_name == var.repository && tostring(self.repo_id) == var.repository_id
      error_message = "The GitHub repository must match the exact full name and numeric identity pinned in its OCI trust."
    }
  }
}

# Match protected master exactly. Local operator credentials administer these GitHub controls.
resource "github_repository_environment" "deployment" {
  repository          = data.github_repository.bound.name
  environment         = var.environment
  can_admins_bypass   = false
  prevent_self_review = var.controls.prevent_self_review
  reviewers {
    users = var.controls.reviewer_user_ids
    teams = var.controls.reviewer_team_ids
  }
  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
  lifecycle { prevent_destroy = true }
}

resource "github_repository_environment_deployment_policy" "master" {
  repository     = local.repository_name
  environment    = github_repository_environment.deployment.environment
  branch_pattern = "master"
  lifecycle { prevent_destroy = true }
}

# Refuse pre-existing wildcard branch rules or tags before sending workflow secrets.
data "github_repository_environment_deployment_policies" "bound" {
  repository  = local.repository_name
  environment = github_repository_environment.deployment.environment
  depends_on  = [github_repository_environment_deployment_policy.master]
  lifecycle {
    postcondition {
      condition     = length(self.policies) == 1 && alltrue([for p in self.policies : p.type == "branch" && p.pattern == "master"])
      error_message = "The environment must permit only the master branch and no tags."
    }
  }
}

data "github_actions_environment_public_key" "deployment" {
  repository  = local.repository_name
  environment = github_repository_environment.deployment.environment
}

# Only resource identities and a private configuration filename enter the external provider's query.
# The helper reads the generated credential in memory and returns GitHub-sealed ciphertext only.
data "external" "envelopes" {
  program = ["uv", "run", "--locked", "--project", path.module, "python", "-I", "${path.module}/seal_inputs.py"]
  query = {
    repository       = var.repository
    environment      = var.environment
    key_id           = data.github_actions_environment_public_key.deployment.key_id
    public_key       = data.github_actions_environment_public_key.deployment.key
    app_id           = var.exchange_app_id
    client_id        = var.exchange_client_name
    domain_url       = var.identity_domain_url
    compartment_ocid = var.hosting_compartment_ocid
    target           = jsonencode(var.target)
    oci_profile      = var.oci_profile
    oci_auth         = var.oci_auth
    settings_file    = var.controls.settings_file
  }
  depends_on = [data.github_repository_environment_deployment_policies.bound]
}

# Sealing uses a new nonce each time. Reuse the current envelopes until a bound input, public key
# or operator rotation generation changes. On replacement Terraform captures newly sealed inputs.
resource "terraform_data" "envelopes" {
  input = sensitive(data.external.envelopes.result)
  triggers_replace = [
    var.controls.secret_revision,
    data.github_actions_environment_public_key.deployment.key_id,
    data.external.envelopes.result["input_digest"],
  ]
  lifecycle { ignore_changes = [input] }
}

resource "github_actions_environment_secret" "workflow" {
  for_each        = local.secret_names
  repository      = local.repository_name
  environment     = github_repository_environment.deployment.environment
  secret_name     = each.key
  key_id          = data.github_actions_environment_public_key.deployment.key_id
  value_encrypted = terraform_data.envelopes.output[each.key]
}

# Apply remains held unless explicitly enabled. Both flags are protected-environment variables.
resource "github_actions_environment_variable" "workflow" {
  for_each = merge({
    OTM_INFRASTRUCTURE_ENABLED       = tostring(var.controls.plan_enabled)
    OTM_INFRASTRUCTURE_APPLY_ENABLED = tostring(var.controls.apply_enabled)
    }, var.environment == "development" ? {} : {
    OTM_OKE_KUBERNETES_VERSION = var.controls.kubernetes_version
    OTM_POSTGRESQL_VERSION     = var.controls.postgresql_version
  })
  repository    = local.repository_name
  environment   = github_repository_environment.deployment.environment
  variable_name = each.key
  value         = each.value
  depends_on    = [github_actions_environment_secret.workflow]

  lifecycle {
    precondition {
      condition = var.environment == "development" || (
        can(regex("^v[1-9][0-9]*[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)$", var.controls.kubernetes_version)) &&
        can(regex("^[1-9][0-9]$", var.controls.postgresql_version))
      )
      error_message = "Hosted environments require exact approved Kubernetes and PostgreSQL versions."
    }
  }
}
