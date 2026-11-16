# Mask private coordinates in normal output; sensitive is not state encryption.
# These describe the later platform backend, not a successful bootstrap-state migration.
output "state_backend" {
  description = "OCI backend coordinates only; authentication is configured independently."
  sensitive   = true
  value = {
    bucket    = oci_objectstorage_bucket.state.name
    namespace = oci_objectstorage_bucket.state.namespace
    region    = var.target.region
    key       = "platform/${var.expected_environment}/terraform.tfstate"
  }
}

# Operator verification still checks the live principal, compartment ownership and permissions.
output "environment_binding" {
  description = "Fixed environment and selected target references; no credentials."
  sensitive   = true
  value = {
    environment      = var.expected_environment
    tenancy_ocid     = var.target.tenancy_ocid
    compartment_ocid = var.target.compartment_ocid
  }
}
