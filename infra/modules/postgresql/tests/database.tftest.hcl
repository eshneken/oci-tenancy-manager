# Native mocks inspect real provider schemas without secrets, OCI credentials or service calls.
mock_provider "oci" {
  override_during = plan
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
run "private_ha_backup_and_vault_reference" {
  command = plan
  assert {
    condition = (
      oci_psql_db_system.app.db_version == "16" && oci_psql_db_system.app.instance_count == 2 &&
      oci_psql_db_system.app.instance_ocpu_count == 1 && oci_psql_db_system.app.instance_memory_size_in_gbs == 16 &&
      oci_psql_db_system.app.config_id == "configuration-synthetic" && !oci_psql_db_system.app.allow_major_version_upgrade &&
      oci_psql_db_system.app.network_details[0].subnet_id == "subnet-database" &&
      toset(oci_psql_db_system.app.network_details[0].nsg_ids) == toset(["nsg-database"]) &&
      !oci_psql_db_system.app.network_details[0].is_reader_endpoint_enabled &&
      oci_psql_db_system.app.storage_details[0].is_regionally_durable && oci_psql_db_system.app.storage_details[0].iops == "75000" &&
      oci_psql_db_system.app.credentials[0].password_details[0].password_type == "VAULT_SECRET" &&
      oci_psql_db_system.app.credentials[0].password_details[0].secret_id == var.administrator.secret_ocid &&
      oci_psql_db_system.app.credentials[0].password_details[0].secret_version == "1"
    )
    error_message = "Use exact private network/configuration, modest HA sizing and pinned Vault references only."
  }
  assert {
    condition = (
      oci_psql_db_system.app.management_policy[0].backup_policy[0].kind == "DAILY" &&
      oci_psql_db_system.app.management_policy[0].backup_policy[0].retention_days == 35 &&
      oci_psql_db_system.app.management_policy[0].backup_policy[0].backup_start == "02:00:00Z" &&
      oci_psql_db_system.app.management_policy[0].maintenance_window_start == "SUN 04:00:00Z" &&
      oci_psql_db_system.app.management_policy[0].pitr_policy[0].kind == "STANDARD" &&
      oci_psql_db_system.app.management_policy[0].pitr_policy[0].restore_days == 35
    )
    error_message = "Keep daily backups and35-day PITR explicit, with provider-compatible UTC windows."
  }
}
run "reject_cross_environment_network" {
  command = plan
  variables { network = { environment = "production", subnets = { database = { id = "other" } }, nsg_ids = { database = "other" } } }
  expect_failures = [var.network]
}
run "reject_invalid_environment" {
  command = plan
  variables {
    environment = "preview"
    network     = { environment = "preview", subnets = { database = { id = "db" } }, nsg_ids = { database = "db" } }
  }
  expect_failures = [var.environment]
}
run "reject_plaintext_in_secret_reference" {
  command = plan
  variables { administrator = { username = "otm_provisioner", secret_ocid = "not-a-secret-ocid", secret_version = "1" } }
  expect_failures = [var.administrator]
}
run "reject_unpinned_secret_version" {
  command = plan
  variables { administrator = { username = "otm_provisioner", secret_ocid = "ocid1.vaultsecret.oc1.iad.synthetic", secret_version = "CURRENT" } }
  expect_failures = [var.administrator]
}
run "reject_reserved_administrator" {
  command = plan
  variables { administrator = { username = "postgres", secret_ocid = "ocid1.vaultsecret.oc1.iad.synthetic", secret_version = "1" } }
  expect_failures = [var.administrator]
}
run "reject_single_node" {
  command = plan
  variables { database = { instance_count = 1, backup_start_utc = "02:00", maintenance_start_utc = "SUN 04:00" } }
  expect_failures = [var.database]
}
run "reject_oversized_resources" {
  command = plan
  variables { database = { ocpus = 9, backup_start_utc = "02:00", maintenance_start_utc = "SUN 04:00" } }
  expect_failures = [var.database]
}
run "reject_invalid_windows" {
  command = plan
  variables { database = { backup_start_utc = "25:00", maintenance_start_utc = "Sunday 04:00" } }
  expect_failures = [var.database]
}
run "reject_unavailable_shape" {
  command = plan
  override_data {
    target = data.oci_psql_shapes.available
    values = { shape_collection = [{ items = [] }] }
  }
  expect_failures = [oci_psql_db_system.app]
}
run "reject_service_resource_limits" {
  command = plan
  override_data {
    target = data.oci_psql_shapes.available
    values = { shape_collection = [{ items = [{ shape = "PostgreSQL.VM.Standard.E5.Flex", is_flexible = true, shape_ocpu_options = [{ min = 2, max = 64 }], shape_memory_options = [{ min_in_gbs = 16, max_in_gbs = 1024, min_per_ocpu_in_gbs = 1, max_per_ocpu_in_gbs = 64 }] }] }] }
  }
  expect_failures = [oci_psql_db_system.app]
}
run "reject_unavailable_configuration" {
  command = plan
  override_data {
    target = data.oci_psql_default_configurations.available
    values = { default_configuration_collection = [{ items = [] }] }
  }
  expect_failures = [oci_psql_db_system.app]
}
run "reject_incompatible_configuration" {
  command = plan
  override_data {
    target = data.oci_psql_default_configurations.available
    values = { default_configuration_collection = [{ items = [{ id = "configuration-other", db_version = "17", state = "ACTIVE", is_flexible = true, shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"] }] }] }
  }
  expect_failures = [oci_psql_db_system.app]
}
run "reject_ambiguous_configuration" {
  command = plan
  override_data {
    target = data.oci_psql_default_configurations.available
    values = { default_configuration_collection = [{ items = [
      { id = "configuration-one", db_version = "16", state = "ACTIVE", is_flexible = true, shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"] },
      { id = "configuration-two", db_version = "16", state = "ACTIVE", is_flexible = true, shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"] }
    ] }] }
  }
  expect_failures = [oci_psql_db_system.app]
}
run "explicit_reviewed_upgrade_opt_in" {
  command = plan
  variables { database = { backup_start_utc = "02:00", maintenance_start_utc = "SUN 04:00", allow_major_version_upgrade = true } }
  assert {
    condition     = oci_psql_db_system.app.allow_major_version_upgrade
    error_message = "Approved upgrade opt-in must reach the provider without an implicit fallback."
  }
}
