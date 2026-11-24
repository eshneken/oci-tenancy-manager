# This label is fixed by the environment root, not a substitute for IAM authorization.
variable "expected_environment" {
  type        = string
  description = "Fixed development, staging or production label selected by the calling root."
  validation {
    condition     = contains(["development", "staging", "production"], var.expected_environment)
    error_message = "The environment must be development, staging or production."
  }
}

# Explicit noncredential coordinates must be checked against the actual OCI target.
variable "target" {
  description = "Private environment binding; namespace must match the selected tenancy."
  type = object({
    environment              = string
    tenancy_ocid             = string
    compartment_ocid         = string
    object_storage_namespace = string
    region                   = optional(string, "us-ashburn-1")
  })
  validation {
    condition     = var.target.environment == var.expected_environment
    error_message = "The target record does not belong to this environment root."
  }
  validation {
    condition     = can(regex("^ocid1[.]tenancy[.][a-z0-9]+[.][.][a-z0-9]+$", var.target.tenancy_ocid))
    error_message = "Provide a tenancy OCID, not another resource identifier."
  }
  validation {
    condition     = can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][.][a-z0-9]+$", var.target.compartment_ocid))
    error_message = "Provide the dedicated existing state compartment OCID."
  }
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$", var.target.object_storage_namespace))
    error_message = "Provide one nonempty namespace without whitespace or path components."
  }
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]+-[0-9]+$", var.target.region))
    error_message = "Provide an explicit OCI region; the initial target is us-ashburn-1."
  }
}

# Internal resource naming is independent of the display application's branding.
variable "name_prefix" {
  type        = string
  default     = "otm"
  description = "Lowercase 3-24 character prefix; starts with a letter and ends alphanumeric."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.name_prefix))
    error_message = "Use a safe lowercase 3-24 character prefix."
  }
}
