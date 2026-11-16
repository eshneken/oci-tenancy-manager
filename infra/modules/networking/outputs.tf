# These IDs are private composition inputs, not an endpoint/connectivity qualification receipt.
output "network" {
  description = "VCN, regional subnet and NSG IDs for subsequent OKE/PostgreSQL resource composition."
  sensitive   = true
  value = {
    environment      = var.environment
    compartment_ocid = oci_core_vcn.app.compartment_id
    vcn_id           = oci_core_vcn.app.id
    vcn_cidr         = var.vcn_cidr
    subnets          = { for key, subnet in oci_core_subnet.app : key => { id = subnet.id, cidr = subnet.cidr_block } }
    nsg_ids          = { for key, group in oci_core_network_security_group.app : key => group.id }
  }
  # OKE must not start bootstrapping against half-installed ingress/egress rules.
  depends_on = [
    oci_core_network_security_group_security_rule.https,
    oci_core_network_security_group_security_rule.kubernetes_clients,
    oci_core_network_security_group_security_rule.oke_ingress,
    oci_core_network_security_group_security_rule.oke_egress,
    oci_core_network_security_group_security_rule.oke_services,
    oci_core_network_security_group_security_rule.https_egress,
    oci_core_network_security_group_security_rule.dns,
    oci_core_network_security_group_security_rule.smtp_egress,
    oci_core_network_security_group_security_rule.path_mtu,
    oci_core_network_security_group_security_rule.database_ingress,
    oci_core_network_security_group_security_rule.database_egress,
  ]
}
