# All discovery and resources are mocked, with distinct IDs for exact attachment assertions.
mock_provider "oci" {
  override_during = apply
  mock_resource "oci_containerengine_cluster" { defaults = { id = "cluster-synthetic" } }
  mock_resource "oci_containerengine_node_pool" { defaults = { id = "pool-synthetic", ssh_public_key = "" } }
  mock_data "oci_containerengine_cluster_option" {
    defaults = { kubernetes_versions = ["v1.37.1"], cluster_pod_network_options = [{ cni_type = "OCI_VCN_IP_NATIVE" }] }
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
    kubernetes_version   = "v1.37.1"
    availability_domains = ["synthetic:AD-1", "synthetic:AD-2", "synthetic:AD-3"]
  }
}

# Mock apply creates in-memory test state only; the second run must hit prevent_destroy.
run "seed_mock_cluster" { command = apply }
run "reject_cluster_replacement" {
  command = plan
  plan_options { replace = [oci_containerengine_cluster.app] }
}
