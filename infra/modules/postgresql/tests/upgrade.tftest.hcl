# Mocks validate request fields; OCI custom-diff upgrade/replacement logic needs live qualification.
mock_provider "oci" {
  override_during = apply
  mock_data "oci_psql_shapes" {
    defaults = { shape_collection = [{ items = [{
      shape                = "PostgreSQL.VM.Standard.E5.Flex", is_flexible = true,
      shape_ocpu_options   = [{ min = 1, max = 64 }],
      shape_memory_options = [{ min_in_gbs = 16, max_in_gbs = 1024, min_per_ocpu_in_gbs = 1, max_per_ocpu_in_gbs = 64 }]
    }] }] }
  }
  mock_data "oci_psql_default_configurations" {
    defaults = { default_configuration_collection = [{ items = [{
      id    = "configuration-synthetic", db_version = "16", state = "ACTIVE", is_flexible = true,
      shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"]
    }] }] }
  }
  mock_data "oci_psql_db_system_connection_detail" {
    defaults = { primary_db_endpoint = [{ fqdn = "database.example.test", ip_address = "10.80.2.5", port = 5432 }], ca_certificate = "synthetic-ca-metadata" }
  }
}
variables {
  environment        = "staging"
  compartment_ocid   = "ocid1.compartment.oc1..synthetichosting"
  postgresql_version = "16"
  network            = { environment = "staging", subnets = { database = { id = "subnet-database" } }, nsg_ids = { database = "nsg-database" } }
  administrator      = { username = "otm_provisioner", secret_ocid = "ocid1.vaultsecret.oc1.iad.synthetic", secret_version = "1" }
  database           = { backup_start_utc = "02:00", maintenance_start_utc = "SUN 04:00" }
}
run "seed_mock_upgrade" { command = apply }
run "reviewed_major_upgrade_inputs" {
  command = plan
  variables {
    postgresql_version = "18"
    database           = { backup_start_utc = "02:00", maintenance_start_utc = "SUN 04:00", allow_major_version_upgrade = true }
  }
  override_data {
    target = data.oci_psql_default_configurations.available
    values = { default_configuration_collection = [{ items = [{ id = "configuration-next", db_version = "18", state = "ACTIVE", is_flexible = true, shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"] }] }] }
  }
  assert {
    condition     = oci_psql_db_system.app.db_version == "18" && oci_psql_db_system.app.config_id == "configuration-next" && oci_psql_db_system.app.allow_major_version_upgrade
    error_message = "Explicit upgrade request must include the selected target configuration and opt-in."
  }
}
