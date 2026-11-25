terraform {
  required_version = "= 1.15.5"
}

# Select one deployment name for the integrated app without carrying an OCI identifier or secret.
variable "environment" {
  type        = string
  description = "Atlas deployment environment whose integrated application metadata is requested."
  nullable    = false

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

# Use the same app naming pattern as the infrastructure workload clients.
output "display_name" {
  value       = "otm-application-${var.environment}"
  description = "Display name for the environment's OCI integrated application."
}

# Keep the console description stable across activation and endpoint changes.
output "description" {
  value       = "Corporate single sign-on for OCI Tenancy Manager."
  description = "Public description for the environment's OCI integrated application."
}

# Give each environment an app-only assignment group with a stable public name.
output "group_display_name" {
  value       = "otm-${var.environment}-users"
  description = "Display name for the environment's OCI integrated application assignment group."
}

# Describe the user group by its purpose rather than its deployment details.
output "group_description" {
  value       = "Users assigned to corporate sign-in for OCI Tenancy Manager."
  description = "Public description for the environment's OCI integrated application assignment group."
}
