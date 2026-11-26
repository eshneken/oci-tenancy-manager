# Different prefix sizes leave deterministic disjoint ranges for regional subnets.
locals {
  name = "otm-${var.environment}"
  tags = { "otm-environment" = var.environment, "otm-component" = "networking" }
  subnets = {
    edge     = { cidr = cidrsubnet(var.vcn_cidr, 8, 0), route = "edge" }
    api      = { cidr = cidrsubnet(var.vcn_cidr, 8, 1), route = "edge" }
    nodes    = { cidr = cidrsubnet(var.vcn_cidr, 6, 1), route = "private" }
    pods     = { cidr = cidrsubnet(var.vcn_cidr, 4, 1), route = "private" }
    database = { cidr = cidrsubnet(var.vcn_cidr, 8, 2), route = "database" }
  }
}

resource "oci_core_vcn" "app" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = local.name
  dns_label      = "otm${var.environment}"
  is_ipv6enabled = false
  freeform_tags  = local.tags
}

# Replace OCI's implicit default SSH/egress rules with an explicit deny-all list. Subnets also
# select the separate empty list below, avoiding accidental inherited additive permissions.
resource "oci_core_default_security_list" "closed" {
  manage_default_resource_id = oci_core_vcn.app.default_security_list_id
  display_name               = "${local.name}-unused-default-deny"
  # No ingress/egress blocks: the provider's noncomputed rule sets are deliberately empty.
}

resource "oci_core_security_list" "closed" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${local.name}-subnet-deny"
  # No ingress/egress blocks: all access is granted explicitly by service NSGs.
  freeform_tags = local.tags
}

resource "oci_core_internet_gateway" "edge" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${local.name}-edge"
  enabled        = true
  freeform_tags  = local.tags
}

resource "oci_core_nat_gateway" "private" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${local.name}-egress"
  block_traffic  = false
  freeform_tags  = local.tags
}

# Discover exactly one region-local Oracle Services Network prefix; never hardcode region IDs.
data "oci_core_services" "regional" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
  lifecycle {
    postcondition {
      condition     = length(self.services) == 1
      error_message = "The region must expose exactly one all-services gateway target."
    }
  }
}

locals {
  service = one(data.oci_core_services.regional.services)
}

resource "oci_core_service_gateway" "regional" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${local.name}-services"
  freeform_tags  = local.tags
  services { service_id = local.service.id }
}

# Edge and the restricted public API use IGW only; no service route on public subnets.
# Database has no NAT/default internet route; only private nodes/pods use NAT.
resource "oci_core_route_table" "app" {
  for_each       = toset(["edge", "private", "database"])
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${local.name}-${each.key}"
  freeform_tags  = local.tags
  dynamic "route_rules" {
    for_each = each.key == "database" ? [] : [each.key]
    content {
      destination       = "0.0.0.0/0"
      destination_type  = "CIDR_BLOCK"
      network_entity_id = each.key == "edge" ? oci_core_internet_gateway.edge.id : oci_core_nat_gateway.private.id
    }
  }
  dynamic "route_rules" {
    for_each = each.key == "edge" ? [] : [each.key]
    content {
      destination       = local.service.cidr_block
      destination_type  = "SERVICE_CIDR_BLOCK"
      network_entity_id = oci_core_service_gateway.regional.id
    }
  }
}

resource "oci_core_subnet" "app" {
  for_each                   = local.subnets
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.app.id
  cidr_block                 = each.value.cidr
  display_name               = "${local.name}-${each.key}"
  dns_label                  = each.key
  route_table_id             = oci_core_route_table.app[each.value.route].id
  security_list_ids          = [oci_core_security_list.closed.id]
  prohibit_public_ip_on_vnic = !contains(["edge", "api"], each.key)
  prohibit_internet_ingress  = !contains(["edge", "api"], each.key)
  freeform_tags              = local.tags
}

# OKE attaches API/deployment, node and pod groups to their exact service VNICs. Deployment
# remains empty until an owned CI admission flow adds only its temporary /32 and TCP6443.
resource "oci_core_network_security_group" "app" {
  for_each       = toset(["edge", "api", "nodes", "pods", "database", "deployment"])
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${local.name}-${each.key}"
  freeform_tags  = local.tags
}

resource "oci_core_network_security_group_security_rule" "https" {
  for_each                  = var.app_ingress_allowed_cidrs
  network_security_group_id = oci_core_network_security_group.app["edge"].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  description               = "Approved app source; UI and API HTTPS only"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# PostgreSQL accepts only the future workload pod NSG, never public/VPN/whole-VCN sources.
resource "oci_core_network_security_group_security_rule" "database_ingress" {
  network_security_group_id = oci_core_network_security_group.app["database"].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.app["pods"].id
  source_type               = "NETWORK_SECURITY_GROUP"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 5432
      max = 5432
    }
  }
}

resource "oci_core_network_security_group_security_rule" "database_egress" {
  network_security_group_id = oci_core_network_security_group.app["pods"].id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.app["database"].id
  destination_type          = "NETWORK_SECURITY_GROUP"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 5432
      max = 5432
    }
  }
}
