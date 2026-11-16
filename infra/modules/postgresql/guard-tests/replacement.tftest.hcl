# Native mocks inspect real provider schemas without secrets, OCI credentials or service calls.
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
run "seed_mock_database" { command = apply }
run "reject_database_replacement" {
  command = plan
  plan_options { replace = [oci_psql_db_system.app] }
}
