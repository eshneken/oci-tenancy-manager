# Region-scoped reads resolve a compatible image without substituting a different version/shape.
data "oci_containerengine_cluster_option" "supported" {
  cluster_option_id              = "all"
  compartment_id                 = var.compartment_ocid
  should_list_all_patch_versions = true
  lifecycle {
    postcondition {
      condition     = contains(self.kubernetes_versions, var.oke.kubernetes_version) && contains([for option in self.cluster_pod_network_options : option.cni_type], "OCI_VCN_IP_NATIVE")
      error_message = "The pinned Kubernetes patch and VCN-native CNI must be available in this region."
    }
  }
}

data "oci_containerengine_node_pool_option" "supported" {
  node_pool_option_id            = "all"
  compartment_id                 = var.compartment_ocid
  node_pool_k8s_version          = var.oke.kubernetes_version
  node_pool_os_arch              = "AARCH64"
  should_list_all_patch_versions = true
  lifecycle {
    postcondition {
      condition     = contains(self.shapes, "VM.Standard.A1.Flex") && length([for source in self.sources : source.image_id if source.source_type == "IMAGE"]) > 0
      error_message = "A1 and at least one image source must be available for the selected Kubernetes version and ARM architecture."
    }
  }
}

data "oci_identity_availability_domains" "hosting" {
  compartment_id = var.tenancy_ocid
  lifecycle {
    postcondition {
      condition     = alltrue([for name in var.oke.availability_domains : contains([for ad in self.availability_domains : ad.name], name)])
      error_message = "Every placement must name an availability domain in the selected hosting tenancy/region."
    }
  }
}

locals {
  name = "otm-${var.environment}"
  tags = { "otm-environment" = var.environment, "otm-component" = "oke" }
}

# Enhanced is mandatory for future workload identity. Only the control endpoint is public;
# source restrictions live in the exact attached API/deployment NSGs, with no default public rule.
resource "oci_containerengine_cluster" "app" {
  compartment_id     = var.compartment_ocid
  name               = local.name
  kubernetes_version = var.oke.kubernetes_version
  vcn_id             = var.network.vcn_id
  type               = "ENHANCED_CLUSTER"
  freeform_tags      = local.tags
  cluster_pod_network_options { cni_type = "OCI_VCN_IP_NATIVE" }
  endpoint_config {
    is_public_ip_enabled = true
    subnet_id            = var.network.subnets.api.id
    nsg_ids              = [var.network.nsg_ids.api, var.network.nsg_ids.deployment]
  }
  options {
    ip_families           = ["IPv4"]
    service_lb_subnet_ids = [var.network.subnets.edge.id]
    kubernetes_network_config { services_cidr = var.oke.services_cidr }
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = length(local.selected_candidates) == 1 && length(local.eligible_images) == length(local.image_rows_by_id)
      error_message = "Image resolution requires exactly one newest compatible image, or the exact still-compatible staging selection."
    }
    precondition {
      condition = try(
        cidrhost("${split("/", var.oke.services_cidr)[0]}/${min(tonumber(split("/", var.oke.services_cidr)[1]), tonumber(split("/", var.network.vcn_cidr)[1]))}", 0) !=
        cidrhost("${split("/", var.network.vcn_cidr)[0]}/${min(tonumber(split("/", var.oke.services_cidr)[1]), tonumber(split("/", var.network.vcn_cidr)[1]))}", 0), false
      )
      error_message = "Kubernetes service and VCN address ranges must not overlap."
    }
  }
  # Reject unavailable pins/placements before creating the control plane, not after it exists.
  depends_on = [data.oci_containerengine_cluster_option.supported, data.oci_containerengine_node_pool_option.supported, data.oci_identity_availability_domains.hosting]
}

# No SSH key/arbitrary metadata inputs. The documented OKE metadata flag disables IMDSv1 at launch,
# rather than attempting an unsafe corrective update after a node has already been created.
resource "oci_containerengine_node_pool" "workers" {
  compartment_id     = var.compartment_ocid
  cluster_id         = oci_containerengine_cluster.app.id
  name               = "${local.name}-arm"
  kubernetes_version = var.oke.kubernetes_version
  node_shape         = "VM.Standard.A1.Flex"
  freeform_tags      = local.tags
  # Sensitive marks both script and derived base64 private in normal plans, not encrypted in state.
  node_metadata = {
    "areLegacyImdsEndpointsDisabled" = "true"
    "user_data"                      = base64encode(var.worker_cloud_init)
  }
  node_shape_config {
    ocpus         = var.oke.node_ocpus
    memory_in_gbs = var.oke.node_memory_gib
  }
  node_source_details {
    source_type             = "IMAGE"
    image_id                = try(local.selected_image.id, "")
    boot_volume_size_in_gbs = tostring(var.oke.boot_volume_gib)
  }
  node_config_details {
    size                                = var.oke.node_count
    nsg_ids                             = [var.network.nsg_ids.nodes]
    is_pv_encryption_in_transit_enabled = true
    node_pool_pod_network_option_details {
      cni_type          = "OCI_VCN_IP_NATIVE"
      max_pods_per_node = var.oke.max_pods_per_node
      pod_subnet_ids    = [var.network.subnets.pods.id]
      pod_nsg_ids       = [var.network.nsg_ids.pods]
    }
    dynamic "placement_configs" {
      for_each = toset(var.oke.availability_domains)
      content {
        availability_domain = placement_configs.value
        subnet_id           = var.network.subnets.nodes.id
        fault_domains       = ["FAULT-DOMAIN-1", "FAULT-DOMAIN-2", "FAULT-DOMAIN-3"]
      }
    }
  }
  node_pool_cycling_details {
    is_node_cycling_enabled = true
    cycle_modes             = ["INSTANCE_REPLACE"]
    maximum_surge           = "1"
    maximum_unavailable     = "0"
  }
  node_eviction_node_pool_settings {
    eviction_grace_duration              = "PT30M"
    is_force_action_after_grace_duration = false
    is_force_delete_after_grace_duration = false
  }
  lifecycle {
    precondition {
      condition     = (var.oke.node_count + 1) * (var.oke.max_pods_per_node + 1) <= pow(2, 32 - tonumber(split("/", var.network.subnets.pods.cidr)[1])) - 3
      error_message = "The pod subnet must fit every node plus one surge node, including per-node reserved addressing."
    }
  }
}
