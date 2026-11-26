# Enable only after explicit approval of the workflow's ability to set policy statements.
variable "allow_runtime_policy_writes" {
  description = "Authorize the hosted workflow to create and update the three named application reader policies in its compartment."
  type        = bool
  default     = false
  nullable    = false
}
