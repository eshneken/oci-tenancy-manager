# Every provider operation is mocked; remote backend initialization is never part of a test.
mock_provider "oci" {
  override_during = plan
  mock_resource "oci_containerengine_cluster" { defaults = { id = "ocid1.cluster.oc1.iad.syntheticstaging" } }
  mock_data "oci_objectstorage_namespace" {
    defaults = { namespace = "syntheticstaging" }
  }
  mock_data "oci_containerengine_cluster_option" {
    defaults = { kubernetes_versions = ["v1.37.1"], cluster_pod_network_options = [{ cni_type = "OCI_VCN_IP_NATIVE" }] }
  }
  mock_data "oci_containerengine_node_pool_option" {
    defaults = { shapes = ["VM.Standard.A1.Flex"], sources = [{ image_id = "ocid1.image.oc1.iad.syntheticarmimage", source_name = "Synthetic OKE ARM", source_type = "IMAGE" }] }
  }
  mock_data "oci_identity_availability_domains" {
    defaults = { availability_domains = [{ name = "synthetic:US-ASHBURN-AD-1", id = "ad-synthetic", compartment_id = "ocid1.tenancy.oc1..synthetic" }] }
  }
  mock_data "oci_core_images" {
    defaults = { images = [{ id = "ocid1.image.oc1.iad.syntheticarmimage", display_name = "Synthetic ARM image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T00:00:00Z" }] }
  }
  mock_data "oci_psql_shapes" {
    defaults = { shape_collection = [{ items = [{
      shape                = "PostgreSQL.VM.Standard.E5.Flex", is_flexible = true,
      shape_ocpu_options   = [{ min = 1, max = 64 }],
      shape_memory_options = [{ min_in_gbs = 16, max_in_gbs = 1024, min_per_ocpu_in_gbs = 1, max_per_ocpu_in_gbs = 64 }]
    }] }] }
  }
  mock_data "oci_psql_default_configurations" {
    defaults = { default_configuration_collection = [{ items = [{
      id    = "configuration-synthetic", db_version = "18", state = "ACTIVE", is_flexible = true,
      shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"]
    }] }] }
  }
  mock_data "oci_psql_db_system_connection_detail" {
    defaults = { primary_db_endpoint = [{ fqdn = "database.example.test", ip_address = "10.80.2.5", port = 5432 }], ca_certificate = "synthetic-ca-metadata" }
  }
  mock_data "oci_core_services" {
    defaults = {
      services = [{ id = "service-synthetic", cidr_block = "all-synthetic-services-in-oracle-services-network", name = "All SYN Services In Oracle Services Network", description = "Synthetic service" }]
    }
  }
}
override_module { target = module.atlas_sso }
override_resource {
  override_during = plan
  target          = oci_identity_group.database_provisioners
  values          = { id = "ocid1.group.oc1..syntheticprovisioners" }
}
override_resource {
  override_during = plan
  target          = oci_vault_secret.database_admin
  values          = { id = "ocid1.vaultsecret.oc1.iad.synthetic" }
}
override_resource {
  override_during = plan
  target          = module.secrets.oci_kms_vault.domain["application-secrets"]
  values          = { id = "ocid1.vault.oc1.iad.syntheticapplication", management_endpoint = "https://management.example.test" }
}
variables {
  identity_domain_url      = "https://idcs-synthetic.identity.oraclecloud.com"
  atlas_sso                = { corporate_idp_id = "dddddddddddddddddddddddddddddddd", callback_url = "https://atlas.example.test/api/auth/sso/callback" }
  hosting_compartment_ocid = "ocid1.compartment.oc1..syntheticstaging"
  database_administrator   = { username = "otm_provisioner" }
  database                 = { backup_start_utc = "02:00", maintenance_start_utc = "SUN 04:00" }
  oke_kubernetes_version   = "v1.37.1"
  postgresql_version       = "18"
  worker_cloud_init        = "#!/bin/bash\n# Synthetic only; no live installation.\ntrue\n"
  target = {
    environment              = "staging"
    tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
    object_storage_namespace = "syntheticstaging"
  }
  oke = {
    availability_domains = ["synthetic:US-ASHBURN-AD-1"]
  }
  vcn_cidr                  = "10.80.0.0/16"
  app_ingress_allowed_cidrs = ["198.51.100.0/24", "203.0.113.7/32"]
}
run "fixed_environment_network" {
  command = plan
  assert {
    condition     = output.cluster.environment == "staging" && output.network.environment == "staging" && output.network.subnets.api.cidr == "10.80.1.0/24" && length(output.network.nsg_ids) == 6
    error_message = "The fixed environment root must compose its own private topology and service groups."
  }
}
run "reject_other_environment" {
  command = plan
  variables {
    target = {
      environment              = "production"
      tenancy_ocid             = "ocid1.tenancy.oc1..syntheticstaging"
      object_storage_namespace = "syntheticstaging"
    }
  }
  expect_failures = [var.target]
}
run "reject_wrong_live_namespace" {
  command = plan
  override_data {
    target = data.oci_objectstorage_namespace.target
    values = { namespace = "wrong-synthetic" }
  }
  expect_failures = [data.oci_objectstorage_namespace.target]
}
run "reject_api_key_fallback" {
  command = plan
  variables { oci_auth = "APIKey" }
  expect_failures = [var.oci_auth]
}
run "explicit_resource_principal" {
  command = plan
  variables { oci_auth = "ResourcePrincipal" }
  assert {
    condition     = output.cluster.environment == "staging" && output.network.environment == "staging"
    error_message = "Explicit authentication must not change target scope."
  }
}

run "reject_floating_actions_oke_version" {
  command = plan
  variables { oke_kubernetes_version = "latest" }
  expect_failures = [var.oke_kubernetes_version]
}
run "reject_postgres_patch_instead_of_major" {
  command = plan
  variables { postgresql_version = "18.7" }
  expect_failures = [var.postgresql_version]
}
run "reject_floating_postgres_version" {
  command = plan
  variables { postgresql_version = "latest" }
  expect_failures = [var.postgresql_version]
}
run "postgres_major_reaches_private_database" {
  command = plan
  variables { postgresql_version = "17" }
  override_data {
    target = module.postgresql.data.oci_psql_default_configurations.available
    values = { default_configuration_collection = [{ items = [{ id = "configuration-next", db_version = "17", state = "ACTIVE", is_flexible = true, shape = "PostgreSQL", compatible_shapes = ["PostgreSQL.VM.Standard.E5.Flex"] }] }] }
  }
  assert {
    condition     = output.database.requested_version == "17" && output.database.environment == "staging"
    error_message = "The environment's explicit major must reach its own managed database module."
  }
}

run "explicit_hosting_compartment_reaches_all_resources" {
  command = plan
  variables { hosting_compartment_ocid = "ocid1.compartment.oc1..syntheticalternate" }
  assert {
    condition     = output.network.compartment_ocid == var.hosting_compartment_ocid && output.cluster.compartment_ocid == var.hosting_compartment_ocid && output.database.compartment_ocid == var.hosting_compartment_ocid
    error_message = "Every resource group must use the single environment-selected hosting compartment."
  }
}
run "reject_invalid_hosting_compartment" {
  command = plan
  variables { hosting_compartment_ocid = "not-a-compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}

# Scope the role policy to the very cluster and application Vault composed by this root.
run "workload_identity_composition" {
  command = plan
  assert {
    condition     = output.workload_vault_access.cluster_ocid == output.cluster.id && output.workload_vault_access.application_vault_ocid == module.secrets.custody.domains["application-secrets"].vault_ocid && output.workload_vault_access.namespace == "otm-staging"
    error_message = "Runtime Vault IAM must use the exact environment cluster and custody handoff."
  }
}

run "caddy_handoff_composition" {
  command = plan
  variables { caddy_ingress_enabled = true }
  assert {
    condition     = output.ingress.environment == var.target.environment && output.ingress.compartment_ocid == var.hosting_compartment_ocid && output.ingress.https_allowed_cidrs == var.app_ingress_allowed_cidrs
    error_message = "The root must carry this environment's exact source policy and compartment."
  }
}

run "database_password_generated_in_environment_vault" {
  command = plan
  assert {
    condition     = oci_vault_secret.database_admin.enable_auto_generation && one(oci_vault_secret.database_admin.secret_generation_context).generation_type == "PASSPHRASE" && length(oci_vault_secret.database_admin.secret_content) == 0
    error_message = "Provision the database credential in Vault with no Terraform password input."
  }
}
