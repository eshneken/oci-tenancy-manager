# Read service-supported shapes and configurations; never guess a configuration ID or fallback major.
data "oci_psql_shapes" "available" {
  compartment_id = var.compartment_ocid
}
data "oci_psql_default_configurations" "available" {
  state = "ACTIVE"
}
locals {
  shape  = "PostgreSQL.VM.Standard.E5.Flex"
  shapes = [for shape in flatten([for collection in data.oci_psql_shapes.available.shape_collection : collection.items]) : shape if shape.shape == local.shape && shape.is_flexible]
  configurations = [for config in flatten([for collection in data.oci_psql_default_configurations.available.default_configuration_collection : collection.items]) : config if(
    config.state == "ACTIVE" && config.is_flexible && split(".", config.db_version)[0] == var.postgresql_version &&
    (contains(config.compatible_shapes, local.shape) || config.shape == local.shape)
  )]
  selected_shape         = try(one(local.shapes), null)
  selected_configuration = try(one(local.configurations), null)
  shape_fits = try(
    var.database.ocpus >= local.selected_shape.shape_ocpu_options[0].min && var.database.ocpus <= local.selected_shape.shape_ocpu_options[0].max &&
    var.database.memory_gib >= local.selected_shape.shape_memory_options[0].min_in_gbs && var.database.memory_gib <= local.selected_shape.shape_memory_options[0].max_in_gbs &&
    var.database.memory_gib >= var.database.ocpus * local.selected_shape.shape_memory_options[0].min_per_ocpu_in_gbs &&
    var.database.memory_gib <= var.database.ocpus * local.selected_shape.shape_memory_options[0].max_per_ocpu_in_gbs,
    false
  )
}

# Managed regional storage scales independently; no container/PVC or fixed data-disk allocation.
# Credentials are Vault references only. There is no secret-content data source or plaintext input.
resource "oci_psql_db_system" "app" {
  compartment_id              = var.compartment_ocid
  display_name                = "otm-${var.environment}"
  db_version                  = var.postgresql_version
  shape                       = local.shape
  instance_count              = var.database.instance_count
  instance_ocpu_count         = var.database.ocpus
  instance_memory_size_in_gbs = var.database.memory_gib
  config_id                   = try(local.selected_configuration.id, "")
  allow_major_version_upgrade = var.database.allow_major_version_upgrade
  freeform_tags               = { "otm.environment" = var.environment, "otm.component" = "postgresql" }
  credentials {
    username = var.administrator.username
    password_details {
      password_type  = "VAULT_SECRET"
      secret_id      = var.administrator.secret_ocid
      secret_version = var.administrator.secret_version
    }
  }
  network_details {
    subnet_id                  = var.network.subnets.database.id
    nsg_ids                    = [var.network.nsg_ids.database]
    is_reader_endpoint_enabled = false
  }
  storage_details {
    system_type           = "OCI_OPTIMIZED_STORAGE"
    is_regionally_durable = true
    iops                  = "75000"
  }
  management_policy {
    maintenance_window_start = "${var.database.maintenance_start_utc}:00Z"
    backup_policy {
      kind           = "DAILY"
      backup_start   = "${var.database.backup_start_utc}:00Z"
      retention_days = 35
    }
    pitr_policy {
      kind         = "STANDARD"
      restore_days = 35
    }
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = length(local.shapes) == 1 && local.shape_fits
      error_message = "The exact E5 Flex shape and requested per-node resources must be supported in this region."
    }
    precondition {
      condition     = length(local.configurations) == 1
      error_message = "Require exactly one active flexible default configuration compatible with the selected PostgreSQL major and shape."
    }
  }
}

# Retrieve only private connection coordinates and CA material after creation; no login credentials.
data "oci_psql_db_system_connection_detail" "app" {
  db_system_id = oci_psql_db_system.app.id
}
