# Private deployment references support hostname-verified TLS; runtime roles/secrets follow separately.
output "database" {
  sensitive   = true
  description = "Private database references, not a recovery/HA readiness guarantee or runtime credentials."
  value = {
    environment       = var.environment
    compartment_ocid  = oci_psql_db_system.app.compartment_id
    id                = oci_psql_db_system.app.id
    requested_version = var.postgresql_version
    configuration_id  = oci_psql_db_system.app.config_id
    primary_endpoint  = data.oci_psql_db_system_connection_detail.app.primary_db_endpoint
    ca_certificate    = data.oci_psql_db_system_connection_detail.app.ca_certificate
  }
}
