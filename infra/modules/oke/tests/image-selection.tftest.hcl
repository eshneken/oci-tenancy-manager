# All discovery and resources are mocked, with distinct IDs for exact attachment assertions.
mock_provider "oci" {
  override_during = plan
  mock_resource "oci_containerengine_cluster" { defaults = { id = "cluster-synthetic" } }
  mock_resource "oci_containerengine_node_pool" { defaults = { id = "pool-synthetic", ssh_public_key = "" } }
  mock_data "oci_containerengine_cluster_option" {
    defaults = { kubernetes_versions = ["v1.37.0"], cluster_pod_network_options = [{ cni_type = "OCI_VCN_IP_NATIVE" }] }
  }
  mock_data "oci_containerengine_node_pool_option" {
    defaults = { shapes = ["VM.Standard.A1.Flex"], sources = [{ image_id = "ocid1.image.oc1.iad.syntheticarmimage", source_name = "Old ARM image", source_type = "IMAGE" }, { image_id = "ocid1.image.oc1.iad.newarmimage", source_name = "New ARM image", source_type = "IMAGE" }] }
  }
  mock_data "oci_core_images" {
    defaults = { images = [{ id = "ocid1.image.oc1.iad.syntheticarmimage", display_name = "Old image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" }, { id = "ocid1.image.oc1.iad.newarmimage", display_name = "New image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T09:30:00-01:00" }] }
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

run "newest_compatible_image_uses_real_time_and_explicit_filters" {
  command = plan
  assert {
    condition = (
      oci_containerengine_node_pool.workers.node_source_details[0].image_id == "ocid1.image.oc1.iad.newarmimage" &&
      data.oci_containerengine_node_pool_option.supported.node_pool_os_arch == "AARCH64" &&
      data.oci_containerengine_node_pool_option.supported.node_pool_k8s_version == "v1.37.0" &&
      data.oci_core_images.node.shape == "VM.Standard.A1.Flex" && data.oci_core_images.node.operating_system_version == "8" &&
      output.cluster.image_selection.architecture == "AARCH64" && output.cluster.image_selection.kubernetes_version == "v1.37.0"
    )
    error_message = "Resolve newest by actual timestamp from the version/ARM/shape/OS intersection, not lexical time/name/order."
  }
}

run "qualified_production_retains_older_staging_image" {
  command = plan
  variables {
    environment          = "production"
    network              = merge(var.network, { environment = "production" })
    qualified_node_image = { image_ocid = "ocid1.image.oc1.iad.syntheticarmimage", kubernetes_version = "v1.37.0", architecture = "AARCH64", os_major = "8" }
  }
  assert {
    condition     = oci_containerengine_node_pool.workers.node_source_details[0].image_id == "ocid1.image.oc1.iad.syntheticarmimage"
    error_message = "A newer catalog entry must not replace the exact staging-qualified production image."
  }
}

run "reject_production_without_staging_selection" {
  command = plan
  variables {
    environment = "production"
    network     = merge(var.network, { environment = "production" })
  }
  expect_failures = [var.qualified_node_image]
}

run "reject_staging_record_wrong_version" {
  command = plan
  variables { qualified_node_image = { image_ocid = "ocid1.image.oc1.iad.syntheticarmimage", kubernetes_version = "v1.35.2", architecture = "AARCH64", os_major = "8" } }
  expect_failures = [var.qualified_node_image]
}

run "reject_staging_record_wrong_chipset" {
  command = plan
  variables { qualified_node_image = { image_ocid = "ocid1.image.oc1.iad.syntheticarmimage", kubernetes_version = "v1.37.0", architecture = "X86_64", os_major = "8" } }
  expect_failures = [var.qualified_node_image]
}

run "reject_staging_record_wrong_os" {
  command = plan
  variables { qualified_node_image = { image_ocid = "ocid1.image.oc1.iad.syntheticarmimage", kubernetes_version = "v1.37.0", architecture = "AARCH64", os_major = "9" } }
  expect_failures = [var.qualified_node_image]
}

run "reject_staging_image_no_longer_eligible" {
  command = plan
  variables { qualified_node_image = { image_ocid = "ocid1.image.oc1.iad.missingarmimage", kubernetes_version = "v1.37.0", architecture = "AARCH64", os_major = "8" } }
  expect_failures = [oci_containerengine_cluster.app]
}

run "reject_empty_catalog" {
  command = plan
  override_data {
    target = data.oci_core_images.node
    values = { images = [] }
  }
  expect_failures = [oci_containerengine_cluster.app]
}

run "reject_wrong_os_image_without_fallback" {
  command = plan
  override_data {
    target = data.oci_core_images.node
    values = { images = [{ id = "ocid1.image.oc1.iad.newarmimage", display_name = "Wrong OS", operating_system = "Oracle Linux", operating_system_version = "9", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" }] }
  }
  expect_failures = [oci_containerengine_cluster.app]
}

run "reject_non_image_sources" {
  command = plan
  override_data {
    target = data.oci_containerengine_node_pool_option.supported
    values = { shapes = ["VM.Standard.A1.Flex"], sources = [{ image_id = "ocid1.image.oc1.iad.newarmimage", source_name = "Not an image source", source_type = "INSTANCE_CONFIGURATION" }] }
  }
  expect_failures = [data.oci_containerengine_node_pool_option.supported]
}

run "reject_equally_new_distinct_images" {
  command = plan
  override_data {
    target = data.oci_core_images.node
    values = { images = [
      { id = "ocid1.image.oc1.iad.newarmimage", display_name = "New image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" },
      { id = "ocid1.image.oc1.iad.syntheticarmimage", display_name = "Other image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T11:00:00+01:00" }
    ] }
  }
  expect_failures = [oci_containerengine_cluster.app]
}

run "reject_malformed_eligible_timestamp" {
  command = plan
  override_data {
    target = data.oci_core_images.node
    values = { images = [
      { id = "ocid1.image.oc1.iad.newarmimage", display_name = "Valid image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" },
      { id = "ocid1.image.oc1.iad.syntheticarmimage", display_name = "Corrupt timestamp", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "not-a-time" }
    ] }
  }
  expect_failures = [oci_containerengine_cluster.app]
}

run "deduplicate_identical_image_id" {
  command = plan
  override_data {
    target = data.oci_core_images.node
    values = { images = [
      { id = "ocid1.image.oc1.iad.newarmimage", display_name = "Same image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" },
      { id = "ocid1.image.oc1.iad.newarmimage", display_name = "Same image", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" }
    ] }
  }
  assert {
    condition     = oci_containerengine_node_pool.workers.node_source_details[0].image_id == "ocid1.image.oc1.iad.newarmimage"
    error_message = "Repeated identical rows must not fabricate image ambiguity."
  }
}

run "reject_conflicting_duplicate_timestamp" {
  command = plan
  override_data {
    target = data.oci_core_images.node
    values = { images = [
      { id = "ocid1.image.oc1.iad.newarmimage", display_name = "Same ID", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T10:00:00Z" },
      { id = "ocid1.image.oc1.iad.newarmimage", display_name = "Conflicting ID", operating_system = "Oracle Linux", operating_system_version = "8", state = "AVAILABLE", time_created = "2026-11-13T11:00:00Z" }
    ] }
  }
  expect_failures = [oci_containerengine_cluster.app]
}

