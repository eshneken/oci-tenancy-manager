# All discovery and resources are mocked, with distinct IDs for exact attachment assertions.
mock_provider "oci" {
  override_during = plan
  mock_resource "oci_containerengine_cluster" { defaults = { id = "cluster-synthetic" } }
  mock_resource "oci_containerengine_node_pool" { defaults = { id = "pool-synthetic", ssh_public_key = "" } }
  mock_data "oci_containerengine_cluster_option" {
    defaults = { kubernetes_versions = ["v1.37.0"], cluster_pod_network_options = [{ cni_type = "OCI_VCN_IP_NATIVE" }] }
  }
  mock_data "oci_containerengine_node_pool_option" {
    defaults = { shapes = ["VM.Standard.A1.Flex"], sources = [{ image_id = "ocid1.image.oc1.iad.syntheticarmimage", source_name = "Synthetic ARM image", source_type = "IMAGE" }] }
  }
  mock_data "oci_core_images" {
    defaults = { images = [{ id = "ocid1.image.oc1.iad.syntheticarmimage", display_name = "Synthetic ARM image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T00:00:00Z" }] }
  }
  mock_data "oci_identity_availability_domains" {
    defaults = {
      availability_domains = [
        { name = "synthetic:AD-1", id = "ad-one", compartment_id = "ocid1.tenancy.oc1..synthetic" },
        { name = "synthetic:AD-2", id = "ad-two", compartment_id = "ocid1.tenancy.oc1..synthetic" },
        { name = "synthetic:AD-3", id = "ad-three", compartment_id = "ocid1.tenancy.oc1..synthetic" }
      ]
    }
  }
}

variables {
  worker_cloud_init = "#!/bin/bash\n# Synthetic only; no live installation.\ntrue\n"
  environment       = "staging"
  tenancy_ocid      = "ocid1.tenancy.oc1..synthetic"
  compartment_ocid  = "ocid1.compartment.oc1..synthetichosting"
  network = {
    environment = "staging", vcn_id = "vcn-synthetic", vcn_cidr = "10.80.0.0/16"
    subnets = {
      api  = { id = "subnet-api", cidr = "10.80.1.0/24" }, nodes = { id = "subnet-nodes", cidr = "10.80.4.0/22" },
      pods = { id = "subnet-pods", cidr = "10.80.16.0/20" }, edge = { id = "subnet-edge", cidr = "10.80.0.0/24" }
    }
    nsg_ids = { api = "nsg-api", nodes = "nsg-nodes", pods = "nsg-pods", deployment = "nsg-deployment" }
  }
  oke = {
    kubernetes_version   = "v1.37.0"
    availability_domains = ["synthetic:AD-1", "synthetic:AD-2", "synthetic:AD-3"]
  }
}

run "enhanced_public_api_and_private_arm_attachments" {
  command = plan
  assert {
    condition = (
      oci_containerengine_cluster.app.type == "ENHANCED_CLUSTER" &&
      oci_containerengine_cluster.app.endpoint_config[0].is_public_ip_enabled &&
      oci_containerengine_cluster.app.endpoint_config[0].subnet_id == "subnet-api" &&
      toset(oci_containerengine_cluster.app.endpoint_config[0].nsg_ids) == toset(["nsg-api", "nsg-deployment"]) &&
      oci_containerengine_cluster.app.cluster_pod_network_options[0].cni_type == "OCI_VCN_IP_NATIVE" &&
      toset(oci_containerengine_cluster.app.options[0].ip_families) == toset(["IPv4"]) &&
      toset(oci_containerengine_cluster.app.options[0].service_lb_subnet_ids) == toset(["subnet-edge"])
    )
    error_message = "Attach only the reviewed public control endpoint and native IPv4 CNI; keep management and app edge distinct."
  }
  assert {
    condition = (
      oci_containerengine_node_pool.workers.node_shape == "VM.Standard.A1.Flex" &&
      toset(oci_containerengine_node_pool.workers.node_config_details[0].nsg_ids) == toset(["nsg-nodes"]) &&
      alltrue([for placement in oci_containerengine_node_pool.workers.node_config_details[0].placement_configs : placement.subnet_id == "subnet-nodes" && toset(placement.fault_domains) == toset(["FAULT-DOMAIN-1", "FAULT-DOMAIN-2", "FAULT-DOMAIN-3"])]) &&
      toset([for placement in oci_containerengine_node_pool.workers.node_config_details[0].placement_configs : placement.availability_domain]) == toset(var.oke.availability_domains) &&
      toset(oci_containerengine_node_pool.workers.node_config_details[0].node_pool_pod_network_option_details[0].pod_nsg_ids) == toset(["nsg-pods"]) &&
      toset(oci_containerengine_node_pool.workers.node_config_details[0].node_pool_pod_network_option_details[0].pod_subnet_ids) == toset(["subnet-pods"])
    )
    error_message = "Node/pod VNICs and AD/fault-domain placement must use exact private network bindings."
  }
}

run "launch_security_and_reviewed_pins" {
  command = plan
  assert {
    condition = (
      oci_containerengine_node_pool.workers.node_metadata["areLegacyImdsEndpointsDisabled"] == "true" &&
      base64decode(oci_containerengine_node_pool.workers.node_metadata["user_data"]) == var.worker_cloud_init &&
      length(oci_containerengine_node_pool.workers.node_metadata) == 2 &&
      oci_containerengine_node_pool.workers.ssh_public_key == "" &&
      oci_containerengine_node_pool.workers.node_config_details[0].is_pv_encryption_in_transit_enabled &&
      oci_containerengine_cluster.app.kubernetes_version == "v1.37.0" && oci_containerengine_node_pool.workers.kubernetes_version == "v1.37.0" &&
      oci_containerengine_node_pool.workers.node_source_details[0].image_id == "ocid1.image.oc1.iad.syntheticarmimage" &&
      data.oci_containerengine_node_pool_option.supported.node_pool_os_arch == "AARCH64" &&
      data.oci_containerengine_node_pool_option.supported.node_pool_k8s_version == "v1.37.0"
    )
    error_message = "Disable IMDSv1 at launch, omit human SSH keys, encrypt attachments and use only the exact ARM/version pins."
  }
  assert {
    condition = (
      oci_containerengine_node_pool.workers.node_config_details[0].size == 3 &&
      oci_containerengine_node_pool.workers.node_shape_config[0].ocpus == 2 && oci_containerengine_node_pool.workers.node_shape_config[0].memory_in_gbs == 8 &&
      oci_containerengine_node_pool.workers.node_source_details[0].boot_volume_size_in_gbs == "50" &&
      oci_containerengine_node_pool.workers.node_pool_cycling_details[0].maximum_surge == "1" &&
      oci_containerengine_node_pool.workers.node_pool_cycling_details[0].maximum_unavailable == "0" &&
      toset(oci_containerengine_node_pool.workers.node_pool_cycling_details[0].cycle_modes) == toset(["INSTANCE_REPLACE"]) &&
      !oci_containerengine_node_pool.workers.node_eviction_node_pool_settings[0].is_force_delete_after_grace_duration &&
      !oci_containerengine_node_pool.workers.node_eviction_node_pool_settings[0].is_force_action_after_grace_duration
    )
    error_message = "Keep modest initial capacity, one-node surge and non-forced drain behavior."
  }
}

run "reject_floating_version" {
  command = plan
  variables { oke = merge(var.oke, { kubernetes_version = "latest" }) }
  expect_failures = [var.oke]
}
run "reject_unapproved_os_major" {
  command = plan
  variables { oke = merge(var.oke, { node_os_major = "10" }) }
  expect_failures = [var.oke]
}
run "reject_insufficient_node_count" {
  command = plan
  variables { oke = merge(var.oke, { node_count = 1 }) }
  expect_failures = [var.oke]
}
run "reject_duplicate_placements" {
  command = plan
  variables { oke = merge(var.oke, { availability_domains = ["synthetic:AD-1", "synthetic:AD-1"] }) }
  expect_failures = [var.oke]
}
run "reject_wrong_network_environment" {
  command = plan
  variables { network = merge(var.network, { environment = "production" }) }
  expect_failures = [var.network]
}
run "reject_service_vcn_overlap" {
  command = plan
  variables { oke = merge(var.oke, { services_cidr = "10.80.0.0/16" }) }
  expect_failures = [oci_containerengine_cluster.app]
}
run "reject_pod_subnet_without_surge_capacity" {
  command = plan
  variables { network = merge(var.network, { subnets = merge(var.network.subnets, { pods = { id = "subnet-pods", cidr = "10.80.16.0/28" } }) }) }
  expect_failures = [oci_containerengine_node_pool.workers]
}
run "reject_unavailable_patch" {
  command = plan
  override_data {
    target = data.oci_containerengine_cluster_option.supported
    values = { kubernetes_versions = ["v1.35.2"], cluster_pod_network_options = [{ cni_type = "OCI_VCN_IP_NATIVE" }] }
  }
  expect_failures = [data.oci_containerengine_cluster_option.supported]
}
run "reject_unavailable_native_cni" {
  command = plan
  override_data {
    target = data.oci_containerengine_cluster_option.supported
    values = { kubernetes_versions = ["v1.37.0"], cluster_pod_network_options = [{ cni_type = "FLANNEL_OVERLAY" }] }
  }
  expect_failures = [data.oci_containerengine_cluster_option.supported]
}
run "reject_unavailable_a1_shape" {
  command = plan
  override_data {
    target = data.oci_containerengine_node_pool_option.supported
    values = { shapes = ["VM.Standard.E5.Flex"], sources = [{ image_id = "ocid1.image.oc1.iad.syntheticarmimage", source_name = "Synthetic ARM", source_type = "IMAGE" }] }
  }
  expect_failures = [data.oci_containerengine_node_pool_option.supported]
}
run "reject_image_outside_qualified_options" {
  command = plan
  override_data {
    target = data.oci_containerengine_node_pool_option.supported
    values = { shapes = ["VM.Standard.A1.Flex"], sources = [{ image_id = "ocid1.image.oc1.iad.anotherimage", source_name = "Another image", source_type = "IMAGE" }] }
  }
  expect_failures = [oci_containerengine_cluster.app]
}
run "reject_unknown_availability_domain" {
  command = plan
  variables { oke = merge(var.oke, { availability_domains = ["synthetic:OTHER-AD"] }) }
  expect_failures = [data.oci_identity_availability_domains.hosting]
}

run "reject_missing_shell_header" {
  command = plan
  variables { worker_cloud_init = "echo invalid" }
  expect_failures = [var.worker_cloud_init]
}
run "reject_oversized_worker_script" {
  command = plan
  variables { worker_cloud_init = "#!/bin/bash\n#${join("", [for index in range(0, 1024) : "synthetic-padding"])}" }
  expect_failures = [var.worker_cloud_init]
}
