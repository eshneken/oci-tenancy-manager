# Return only noncredential service identifiers; kubeconfig/authentication is obtained separately.
output "cluster" {
  description = "Private deployment references; endpoint reachability/auth and workload readiness need live qualification."
  sensitive   = true
  value = {
    environment        = var.environment
    compartment_ocid   = oci_containerengine_cluster.app.compartment_id
    id                 = oci_containerengine_cluster.app.id
    node_pool_id       = oci_containerengine_node_pool.workers.id
    kubernetes_version = oci_containerengine_cluster.app.kubernetes_version
    endpoints          = oci_containerengine_cluster.app.endpoints
    deployment_nsg_id  = var.network.nsg_ids.deployment
    # Promotion consumes this whole selection, not a fresh production 'latest' lookup.
    image_selection = {
      image_ocid         = try(local.selected_image.id, null)
      kubernetes_version = var.oke.kubernetes_version
      architecture       = "AARCH64"
      os_major           = var.oke.node_os_major
    }
  }
}
