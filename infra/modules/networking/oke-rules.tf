# Every internal link has a matching stateful egress/ingress rule between exact peer groups.
# All-protocol rules are restricted to the VCN-native CNI participants, never a whole VCN CIDR.
locals {
  oke_links = {
    nodes_api      = { from = "nodes", to = "api", protocol = "6", port = 6443 }
    nodes_control  = { from = "nodes", to = "api", protocol = "6", port = 12250 }
    pods_api       = { from = "pods", to = "api", protocol = "6", port = 6443 }
    pods_control   = { from = "pods", to = "api", protocol = "6", port = 12250 }
    api_kubelet    = { from = "api", to = "nodes", protocol = "6", port = 10250 }
    api_pods       = { from = "api", to = "pods", protocol = "all", port = 0 }
    nodes_internal = { from = "nodes", to = "nodes", protocol = "all", port = 0 }
    nodes_pods     = { from = "nodes", to = "pods", protocol = "all", port = 0 }
    pods_nodes     = { from = "pods", to = "nodes", protocol = "all", port = 0 }
    pods_internal  = { from = "pods", to = "pods", protocol = "all", port = 0 }
  }
}

resource "oci_core_network_security_group_security_rule" "oke_ingress" {
  for_each                  = local.oke_links
  network_security_group_id = oci_core_network_security_group.app[each.value.to].id
  direction                 = "INGRESS"
  source                    = oci_core_network_security_group.app[each.value.from].id
  source_type               = "NETWORK_SECURITY_GROUP"
  protocol                  = each.value.protocol
  stateless                 = false
  description               = "OKE ${each.key}"
  dynamic "tcp_options" {
    for_each = each.value.protocol == "6" ? [each.value.port] : []
    content {
      destination_port_range {
        min = tcp_options.value
        max = tcp_options.value
      }
    }
  }
}

resource "oci_core_network_security_group_security_rule" "oke_egress" {
  for_each                  = local.oke_links
  network_security_group_id = oci_core_network_security_group.app[each.value.from].id
  direction                 = "EGRESS"
  destination               = oci_core_network_security_group.app[each.value.to].id
  destination_type          = "NETWORK_SECURITY_GROUP"
  protocol                  = each.value.protocol
  stateless                 = false
  description               = "OKE ${each.key}"
  dynamic "tcp_options" {
    for_each = each.value.protocol == "6" ? [each.value.port] : []
    content {
      destination_port_range {
        min = tcp_options.value
        max = tcp_options.value
      }
    }
  }
}

# The existing human allowlist is reused; GitHub ranges never enter this rule or app/recovery input.
resource "oci_core_network_security_group_security_rule" "kubernetes_clients" {
  for_each                  = var.app_ingress_allowed_cidrs
  network_security_group_id = oci_core_network_security_group.app["api"].id
  direction                 = "INGRESS"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  protocol                  = "6"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 6443
      max = 6443
    }
  }
}

# API needs HTTPS to regional OCI; nodes/pods additionally need the documented OKE service ports.
resource "oci_core_network_security_group_security_rule" "oke_services" {
  for_each                  = toset(["api", "nodes", "pods"])
  network_security_group_id = oci_core_network_security_group.app[each.key].id
  direction                 = "EGRESS"
  destination               = local.service.cidr_block
  destination_type          = "SERVICE_CIDR_BLOCK"
  protocol                  = "6"
  stateless                 = false
  dynamic "tcp_options" {
    for_each = each.key == "api" ? [443] : []
    content {
      destination_port_range {
        min = tcp_options.value
        max = tcp_options.value
      }
    }
  }
}

# NAT egress supports HTTPS registries/provider APIs without public node or pod addresses.
resource "oci_core_network_security_group_security_rule" "https_egress" {
  for_each                  = toset(["nodes", "pods"])
  network_security_group_id = oci_core_network_security_group.app[each.key].id
  direction                 = "EGRESS"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  protocol                  = "6"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# Record resolver intent; OCI does not enforce NSG filtering for link-local/metadata traffic.
resource "oci_core_network_security_group_security_rule" "dns" {
  for_each                  = { for pair in setproduct(["api", "nodes", "pods"], ["6", "17"]) : "${pair[0]}-${pair[1]}" => { group = pair[0], protocol = pair[1] } }
  network_security_group_id = oci_core_network_security_group.app[each.value.group].id
  direction                 = "EGRESS"
  destination               = "169.254.169.254/32"
  destination_type          = "CIDR_BLOCK"
  protocol                  = each.value.protocol
  stateless                 = false
  dynamic "tcp_options" {
    for_each = each.value.protocol == "6" ? [53] : []
    content {
      destination_port_range {
        min = tcp_options.value
        max = tcp_options.value
      }
    }
  }
  dynamic "udp_options" {
    for_each = each.value.protocol == "17" ? [53] : []
    content {
      destination_port_range {
        min = udp_options.value
        max = udp_options.value
      }
    }
  }
}

# Only fragmentation-needed ICMP is admitted globally for path MTU discovery, not general ICMP
# or TCP. Return traffic for all stateful application connections is tracked by OCI.
resource "oci_core_network_security_group_security_rule" "path_mtu" {
  for_each                  = { for pair in setproduct(["api", "nodes", "pods"], ["INGRESS", "EGRESS"]) : "${pair[0]}-${pair[1]}" => { group = pair[0], direction = pair[1] } }
  network_security_group_id = oci_core_network_security_group.app[each.value.group].id
  direction                 = each.value.direction
  source                    = each.value.direction == "INGRESS" ? "0.0.0.0/0" : null
  source_type               = each.value.direction == "INGRESS" ? "CIDR_BLOCK" : null
  destination               = each.value.direction == "EGRESS" ? "0.0.0.0/0" : null
  destination_type          = each.value.direction == "EGRESS" ? "CIDR_BLOCK" : null
  protocol                  = "1"
  stateless                 = false
  icmp_options {
    type = 3
    code = 4
  }
}

# SMTP is outbound from the shared workload pod NSG, only to approved relay addresses/one port.
# Stateful replies need no new inbound rule; this is not per-API/worker Kubernetes isolation.
resource "oci_core_network_security_group_security_rule" "smtp_egress" {
  for_each                  = var.smtp_egress == null ? toset([]) : var.smtp_egress.cidrs
  network_security_group_id = oci_core_network_security_group.app["pods"].id
  direction                 = "EGRESS"
  destination               = each.value
  destination_type          = "CIDR_BLOCK"
  protocol                  = "6"
  stateless                 = false
  description               = "Approved outbound SMTP relay only"
  tcp_options {
    destination_port_range {
      min = var.smtp_egress.port
      max = var.smtp_egress.port
    }
  }
}
