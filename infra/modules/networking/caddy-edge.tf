# HTTP-01 needs public80. HTTPS remains governed solely by the existing human CIDR rules.
resource "oci_core_network_security_group_security_rule" "acme_http" {
  count                     = var.caddy_ingress_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app["edge"].id
  direction                 = "INGRESS"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  protocol                  = "6"
  stateless                 = false
  description               = "HTTP-01 challenge listener; Caddy rejects other HTTP requests"
  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

# Source NAT is explicit on the NLB; external traffic reaches exact private NodePorts via edge NSG.
# Existing CNI rules still allow trusted internal peers and are not narrowed by these additions.
locals {
  caddy_backend_ports = var.caddy_ingress_enabled ? toset(["31080", "31443", "32081"]) : toset([])
}
resource "oci_core_network_security_group_security_rule" "caddy_backend_ingress" {
  for_each                  = local.caddy_backend_ports
  network_security_group_id = oci_core_network_security_group.app["nodes"].id
  direction                 = "INGRESS"
  source                    = oci_core_network_security_group.app["edge"].id
  source_type               = "NETWORK_SECURITY_GROUP"
  protocol                  = "6"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = tonumber(each.key)
      max = tonumber(each.key)
    }
  }
}
resource "oci_core_network_security_group_security_rule" "caddy_backend_egress" {
  for_each                  = local.caddy_backend_ports
  network_security_group_id = oci_core_network_security_group.app["edge"].id
  direction                 = "EGRESS"
  destination               = oci_core_network_security_group.app["nodes"].id
  destination_type          = "NETWORK_SECURITY_GROUP"
  protocol                  = "6"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = tonumber(each.key)
      max = tonumber(each.key)
    }
  }
}

# Stable public IPv4 keeps external DNS independent of Service recreation; no OCI DNS zone.
resource "oci_core_public_ip" "ingress" {
  count          = var.caddy_ingress_enabled ? 1 : 0
  compartment_id = var.compartment_ocid
  lifetime       = "RESERVED"
  display_name   = "${local.name}-caddy"
  freeform_tags  = local.tags
  lifecycle { prevent_destroy = true }
}

# Private release input; compare the human source set with application recovery-console settings.
output "ingress" {
  sensitive = true
  value = var.caddy_ingress_enabled ? {
    environment         = var.environment
    compartment_ocid    = var.compartment_ocid
    https_allowed_cidrs = var.app_ingress_allowed_cidrs
    reserved_ipv4       = oci_core_public_ip.ingress[0].ip_address
    edge_subnet_ocid    = oci_core_subnet.app["edge"].id
    edge_nsg_ocid       = oci_core_network_security_group.app["edge"].id
  } : null
  depends_on = [
    oci_core_network_security_group_security_rule.acme_http,
    oci_core_network_security_group_security_rule.https,
    oci_core_network_security_group_security_rule.caddy_backend_ingress,
    oci_core_network_security_group_security_rule.caddy_backend_egress,
  ]
}
