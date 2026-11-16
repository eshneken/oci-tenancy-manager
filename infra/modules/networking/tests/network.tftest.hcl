# Plan-time mocked values allow checking real resource bindings, never just helper locals.
mock_provider "oci" {
  override_during = plan
  mock_resource "oci_core_vcn" {
    defaults = { "id" : "vcn-synthetic", "default_security_list_id" : "list-default-synthetic" }
  }
  mock_resource "oci_core_security_list" {
    defaults = { "id" : "list-closed-synthetic" }
  }
  mock_resource "oci_core_internet_gateway" {
    defaults = { "id" : "igw-synthetic" }
  }
  mock_resource "oci_core_nat_gateway" {
    defaults = { "id" : "nat-synthetic" }
  }
  mock_resource "oci_core_service_gateway" {
    defaults = { "id" : "sgw-synthetic" }
  }
  mock_data "oci_core_services" {
    defaults = {
      services = [{ id = "service-synthetic", cidr_block = "all-synthetic-services-in-oracle-services-network", name = "All SYN Services In Oracle Services Network", description = "Synthetic regional services" }]
    }
  }
}

# Distinct plan-time IDs make an accidental cross-group binding fail the assertions.
override_resource {
  target          = oci_core_network_security_group.app["edge"]
  override_during = plan
  values          = { id = "nsg-edge-synthetic" }
}
override_resource {
  target          = oci_core_network_security_group.app["api"]
  override_during = plan
  values          = { id = "nsg-api-synthetic" }
}
override_resource {
  target          = oci_core_network_security_group.app["nodes"]
  override_during = plan
  values          = { id = "nsg-nodes-synthetic" }
}
override_resource {
  target          = oci_core_network_security_group.app["pods"]
  override_during = plan
  values          = { id = "nsg-pods-synthetic" }
}
override_resource {
  target          = oci_core_network_security_group.app["database"]
  override_during = plan
  values          = { id = "nsg-database-synthetic" }
}
override_resource {
  target          = oci_core_network_security_group.app["deployment"]
  override_during = plan
  values          = { id = "nsg-deployment-synthetic" }
}
override_resource {
  target          = oci_core_route_table.app["edge"]
  override_during = plan
  values          = { id = "route-edge-synthetic" }
}
override_resource {
  target          = oci_core_route_table.app["private"]
  override_during = plan
  values          = { id = "route-private-synthetic" }
}
override_resource {
  target          = oci_core_route_table.app["database"]
  override_during = plan
  values          = { id = "route-database-synthetic" }
}

variables {
  environment               = "staging"
  compartment_ocid          = "ocid1.compartment.oc1..synthetichosting"
  vcn_cidr                  = "10.80.0.0/16"
  app_ingress_allowed_cidrs = ["198.51.100.0/24", "203.0.113.7/32", "203.0.113.8/32"]
}

run "restricted_edge_and_private_service_bindings" {
  command = plan
  assert {
    condition = (
      alltrue([for rule in oci_core_network_security_group_security_rule.https :
        rule.direction == "INGRESS" && rule.protocol == "6" && rule.source_type == "CIDR_BLOCK" &&
        rule.tcp_options[0].destination_port_range[0].min == 443 && rule.tcp_options[0].destination_port_range[0].max == 443 &&
        rule.network_security_group_id == oci_core_network_security_group.app["edge"].id && !rule.stateless
      ]) && toset([for rule in oci_core_network_security_group_security_rule.https : rule.source]) == var.app_ingress_allowed_cidrs
    )
    error_message = "Render exactly the approved HTTPS union, including each individual host, on the edge NSG only."
  }
  assert {
    condition = (
      alltrue([for name, subnet in oci_core_subnet.app :
        subnet.prohibit_public_ip_on_vnic == (!contains(["edge", "api"], name)) && subnet.prohibit_internet_ingress == (!contains(["edge", "api"], name)) &&
        subnet.security_list_ids == toset([oci_core_security_list.closed.id])
      ]) && !oci_core_vcn.app.is_ipv6enabled
    )
    error_message = "All five subnets must explicitly select the deny-all list; only regional edge/API are public, with IPv6 disabled."
  }
  assert {
    condition = (
      length(oci_core_security_list.closed.ingress_security_rules) == 0 && length(oci_core_security_list.closed.egress_security_rules) == 0 &&
      length(oci_core_default_security_list.closed.ingress_security_rules) == 0 && length(oci_core_default_security_list.closed.egress_security_rules) == 0
    )
    error_message = "Neither attached nor default security lists may introduce additive bypass rules."
  }
  assert {
    condition = (
      { for name, subnet in oci_core_subnet.app : name => subnet.cidr_block } == {
        edge = "10.80.0.0/24", api = "10.80.1.0/24", database = "10.80.2.0/24", nodes = "10.80.4.0/22", pods = "10.80.16.0/20"
      }
    )
    error_message = "Subnet allocation must remain deterministic and disjoint within the /16."
  }
  assert {
    condition = (
      oci_core_network_security_group_security_rule.database_ingress.source == oci_core_network_security_group.app["pods"].id &&
      oci_core_network_security_group_security_rule.database_ingress.source_type == "NETWORK_SECURITY_GROUP" &&
      oci_core_network_security_group_security_rule.database_ingress.network_security_group_id == oci_core_network_security_group.app["database"].id &&
      oci_core_network_security_group_security_rule.database_ingress.tcp_options[0].destination_port_range[0].min == 5432 &&
      oci_core_network_security_group_security_rule.database_ingress.tcp_options[0].destination_port_range[0].max == 5432 &&
      oci_core_network_security_group_security_rule.database_egress.network_security_group_id == oci_core_network_security_group.app["pods"].id &&
      oci_core_network_security_group_security_rule.database_egress.destination == oci_core_network_security_group.app["database"].id
    )
    error_message = "PostgreSQL must be scoped between the exact pod/database NSGs, not a CIDR."
  }
}

run "routes_separate_internet_and_database" {
  command = plan
  assert {
    condition = (
      length(oci_core_route_table.app["database"].route_rules) == 1 && alltrue([
        for rule in oci_core_route_table.app["database"].route_rules : rule.destination_type == "SERVICE_CIDR_BLOCK" && rule.network_entity_id == oci_core_service_gateway.regional.id
      ]) && oci_core_subnet.app["database"].route_table_id == oci_core_route_table.app["database"].id
    )
    error_message = "Database routing must have no internet/NAT default."
  }
  assert {
    condition = (
      length(oci_core_route_table.app["private"].route_rules) == 2 && anytrue([
        for rule in oci_core_route_table.app["private"].route_rules : rule.destination == "0.0.0.0/0" && rule.network_entity_id == oci_core_nat_gateway.private.id
      ]) && alltrue([for rule in oci_core_route_table.app["edge"].route_rules : rule.network_entity_id == oci_core_internet_gateway.edge.id])
    )
    error_message = "Edge/API use IGW; node/pod default egress must use NAT."
  }
}

run "smallest_supported_network" {
  command = plan
  variables { vcn_cidr = "10.90.0.0/20" }
  assert {
    condition = (
      { for name, subnet in oci_core_subnet.app : name => subnet.cidr_block } == {
        edge = "10.90.0.0/28", api = "10.90.0.16/28", database = "10.90.0.32/28", nodes = "10.90.0.64/26", pods = "10.90.1.0/24"
      }
    )
    error_message = "The /20 boundary must keep all regional subnets disjoint and within the VCN."
  }
}

run "reject_empty_sources" {
  command = plan
  variables { app_ingress_allowed_cidrs = [] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_unrestricted_source" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_split_unrestricted_union" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["0.0.0.0/1", "128.0.0.0/1"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "allow_redundant_restricted_union" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["0.0.0.0/1", "0.0.0.0/2", "64.0.0.0/2", "203.0.113.7/32"] }
  assert {
    condition = (
      length(oci_core_network_security_group_security_rule.https) == 4
    )
    error_message = "Overlapping restricted networks must not be mistaken for a universal union."
  }
}

run "reject_noncanonical_source" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["198.51.100.7/24"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_bare_host" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["203.0.113.7"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_ipv6_until_enabled" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["2001:db8::7/128"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_oversized_list" {
  command = plan
  variables { app_ingress_allowed_cidrs = [for host in range(1, 66) : "203.0.113.${host}/32"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_nonprivate_vcn" {
  command = plan
  variables { vcn_cidr = "198.51.0.0/16" }
  expect_failures = [var.vcn_cidr]
}

run "reject_undersized_vcn" {
  command = plan
  variables { vcn_cidr = "10.80.0.0/21" }
  expect_failures = [var.vcn_cidr]
}

run "reject_vcn_host_bits" {
  command = plan
  variables { vcn_cidr = "10.80.1.0/16" }
  expect_failures = [var.vcn_cidr]
}

run "reject_wrong_compartment_type" {
  command = plan
  variables { compartment_ocid = "ocid1.tenancy.oc1..synthetic" }
  expect_failures = [var.compartment_ocid]
}

run "reject_missing_service_gateway_target" {
  command = plan
  override_data {
    target = data.oci_core_services.regional
    values = { services = [] }
  }
  expect_failures = [data.oci_core_services.regional]
}

run "reject_ambiguous_service_gateway_target" {
  command = plan
  override_data {
    target = data.oci_core_services.regional
    values = {
      services = [
        { id = "service-one", cidr_block = "synthetic-one", name = "All ONE Services In Oracle Services Network", description = "One" },
        { id = "service-two", cidr_block = "synthetic-two", name = "All TWO Services In Oracle Services Network", description = "Two" }
      ]
    }
  }
  expect_failures = [data.oci_core_services.regional]
}

run "reject_mixed_valid_and_malformed_sources" {
  command = plan
  variables { app_ingress_allowed_cidrs = ["198.51.100.0/24", "not-a-network"] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_source_byte_limit" {
  command = plan
  variables { app_ingress_allowed_cidrs = [join("", [for index in range(0, 1024) : "invalid"])] }
  expect_failures = [var.app_ingress_allowed_cidrs]
}

run "reject_oversized_vcn" {
  command = plan
  variables { vcn_cidr = "10.80.0.0/15" }
  expect_failures = [var.vcn_cidr]
}

# These assertions inspect rendered traffic policy and exact VNIC group identities independently
# of the implementation's helper map; changing both directions incorrectly must still fail.
run "public_api_only_authorized_humans_on_6443" {
  command = plan
  assert {
    condition = (
      toset([for rule in oci_core_network_security_group_security_rule.kubernetes_clients : rule.source]) == var.app_ingress_allowed_cidrs &&
      alltrue([for rule in oci_core_network_security_group_security_rule.kubernetes_clients : rule.network_security_group_id == "nsg-api-synthetic" && rule.source_type == "CIDR_BLOCK" && rule.protocol == "6" && rule.direction == "INGRESS" && !rule.stateless && rule.tcp_options[0].destination_port_range[0].min == 6443 && rule.tcp_options[0].destination_port_range[0].max == 6443]) &&
      oci_core_subnet.app["api"].route_table_id == "route-edge-synthetic" &&
      !oci_core_subnet.app["api"].prohibit_public_ip_on_vnic && !oci_core_subnet.app["api"].prohibit_internet_ingress
    )
    error_message = "Only the exact human list may reach public TCP6443; no GitHub range or control-port fallback."
  }
}

run "exact_vcn_native_internal_matrix" {
  command = plan
  assert {
    condition = (
      { for key, rule in oci_core_network_security_group_security_rule.oke_ingress : key => "${rule.source}|${rule.network_security_group_id}|${rule.protocol}|${try(rule.tcp_options[0].destination_port_range[0].min, 0)}" } == {
        nodes_api      = "nsg-nodes-synthetic|nsg-api-synthetic|6|6443", nodes_control = "nsg-nodes-synthetic|nsg-api-synthetic|6|12250",
        pods_api       = "nsg-pods-synthetic|nsg-api-synthetic|6|6443", pods_control = "nsg-pods-synthetic|nsg-api-synthetic|6|12250",
        api_kubelet    = "nsg-api-synthetic|nsg-nodes-synthetic|6|10250", api_pods = "nsg-api-synthetic|nsg-pods-synthetic|all|0",
        nodes_internal = "nsg-nodes-synthetic|nsg-nodes-synthetic|all|0", nodes_pods = "nsg-nodes-synthetic|nsg-pods-synthetic|all|0",
        pods_nodes     = "nsg-pods-synthetic|nsg-nodes-synthetic|all|0", pods_internal = "nsg-pods-synthetic|nsg-pods-synthetic|all|0"
        } && alltrue([for key, rule in oci_core_network_security_group_security_rule.oke_ingress :
          rule.source_type == "NETWORK_SECURITY_GROUP" && rule.direction == "INGRESS" && !rule.stateless &&
          oci_core_network_security_group_security_rule.oke_egress[key].destination == rule.network_security_group_id &&
          oci_core_network_security_group_security_rule.oke_egress[key].network_security_group_id == rule.source &&
          oci_core_network_security_group_security_rule.oke_egress[key].destination_type == "NETWORK_SECURITY_GROUP" &&
          oci_core_network_security_group_security_rule.oke_egress[key].protocol == rule.protocol &&
          oci_core_network_security_group_security_rule.oke_egress[key].direction == "EGRESS" && !oci_core_network_security_group_security_rule.oke_egress[key].stateless &&
          try(rule.tcp_options[0].destination_port_range[0].max, 0) == try(rule.tcp_options[0].destination_port_range[0].min, 0) &&
          try(oci_core_network_security_group_security_rule.oke_egress[key].tcp_options[0].destination_port_range[0].min, 0) == try(rule.tcp_options[0].destination_port_range[0].min, 0) &&
          try(oci_core_network_security_group_security_rule.oke_egress[key].tcp_options[0].destination_port_range[0].max, 0) == try(rule.tcp_options[0].destination_port_range[0].max, 0)
      ])
    )
    error_message = "Every internal connection must match the reviewed port/protocol/peer matrix in both directions."
  }
}

run "dns_service_egress_and_limited_path_mtu" {
  command = plan
  assert {
    condition = (
      length(oci_core_network_security_group_security_rule.dns) == 6 && alltrue([for rule in oci_core_network_security_group_security_rule.dns :
        rule.direction == "EGRESS" && rule.destination == "169.254.169.254/32" && rule.destination_type == "CIDR_BLOCK" && !rule.stateless &&
        (rule.protocol == "6" ? rule.tcp_options[0].destination_port_range[0].min == 53 && rule.tcp_options[0].destination_port_range[0].max == 53 : rule.protocol == "17" && rule.udp_options[0].destination_port_range[0].min == 53 && rule.udp_options[0].destination_port_range[0].max == 53)
      ]) && length(oci_core_network_security_group_security_rule.path_mtu) == 6 && alltrue([for rule in oci_core_network_security_group_security_rule.path_mtu : rule.protocol == "1" && rule.icmp_options[0].type == 3 && rule.icmp_options[0].code == 4 && !rule.stateless])
    )
    error_message = "DNS is only TCP/UDP53 to OCI resolver; the global ICMP exception is only type3/code4."
  }
  assert {
    condition = (
      alltrue([for rule in oci_core_network_security_group_security_rule.https_egress : rule.direction == "EGRESS" && rule.destination == "0.0.0.0/0" && rule.protocol == "6" && rule.tcp_options[0].destination_port_range[0].min == 443 && rule.tcp_options[0].destination_port_range[0].max == 443]) &&
      alltrue([for rule in oci_core_network_security_group_security_rule.oke_services : rule.direction == "EGRESS" && rule.destination_type == "SERVICE_CIDR_BLOCK" && rule.destination == "all-synthetic-services-in-oracle-services-network" && rule.protocol == "6"]) &&
      oci_core_network_security_group_security_rule.oke_services["api"].tcp_options[0].destination_port_range[0].min == 443 &&
      oci_core_network_security_group_security_rule.oke_services["api"].tcp_options[0].destination_port_range[0].max == 443
    )
    error_message = "Internet egress remains HTTPS and Oracle service egress stays restricted to the discovered regional prefix."
  }
}

run "smtp_has_no_extra_rules_by_default" {
  command = plan
  assert {
    condition     = length(oci_core_network_security_group_security_rule.smtp_egress) == 0
    error_message = "No relay input must create no new SMTP access."
  }
}
run "smtp_exact_relay_only" {
  command = plan
  variables { smtp_egress = { cidrs = ["192.0.2.80/32", "198.51.100.64/28"], port = 587 } }
  assert {
    condition = (
      toset(keys(oci_core_network_security_group_security_rule.smtp_egress)) == toset(["192.0.2.80/32", "198.51.100.64/28"]) &&
      alltrue([for destination, rule in oci_core_network_security_group_security_rule.smtp_egress : rule.network_security_group_id == "nsg-pods-synthetic" && rule.direction == "EGRESS" && rule.protocol == "6" && !rule.stateless && rule.destination_type == "CIDR_BLOCK" && rule.destination == destination && rule.tcp_options[0].destination_port_range[0].min == 587 && rule.tcp_options[0].destination_port_range[0].max == 587])
    )
    error_message = "Relay-specific rules must use the exact workload pod NSG, approved destinations and port."
  }
}
run "smtp_implicit_tls_port" {
  command = plan
  variables { smtp_egress = { cidrs = ["192.0.2.80/32"], port = 465 } }
  assert {
    condition     = oci_core_network_security_group_security_rule.smtp_egress["192.0.2.80/32"].tcp_options[0].destination_port_range[0].min == 465
    error_message = "The explicitly selected implicit-TLS relay port must be used."
  }
}
run "reject_smtp_cleartext_port" {
  command = plan
  variables { smtp_egress = { cidrs = ["192.0.2.80/32"], port = 25 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_public_default" {
  command = plan
  variables { smtp_egress = { cidrs = ["0.0.0.0/0"], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_unrestricted_union" {
  command = plan
  variables { smtp_egress = { cidrs = ["0.0.0.0/1", "128.0.0.0/1"], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_host_bits" {
  command = plan
  variables { smtp_egress = { cidrs = ["192.0.2.81/24"], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_ipv6" {
  command = plan
  variables { smtp_egress = { cidrs = ["2001:db8::/64"], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_missing_destinations" {
  command = plan
  variables { smtp_egress = { cidrs = [], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_destination_count" {
  command = plan
  variables { smtp_egress = { cidrs = [for index in range(65) : "192.0.2.${index}/32"], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "reject_smtp_destination_bytes" {
  command = plan
  variables { smtp_egress = { cidrs = [join("", [for index in range(1024) : "invalid"])], port = 587 } }
  expect_failures = [var.smtp_egress]
}
run "smtp_overlapping_destinations_are_bounded" {
  command = plan
  variables { smtp_egress = { cidrs = ["192.0.2.0/24", "192.0.2.80/32"], port = 587 } }
  assert {
    condition     = length(oci_core_network_security_group_security_rule.smtp_egress) == 2
    error_message = "Overlap must not inflate effective-union accounting or change configured destinations."
  }
}

# Default preview has no ACME edge/backends/address, preventing accidental public listener setup.
run "caddy_network_closed_until_selected" {
  command = plan
  assert {
    condition     = length(oci_core_network_security_group_security_rule.acme_http) == 0 && length(oci_core_network_security_group_security_rule.caddy_backend_ingress) == 0 && length(oci_core_public_ip.ingress) == 0 && output.ingress == null
    error_message = "Unselected ingress must create no ACME/backend/address resources."
  }
}
run "http01_exact_edge_and_backends" {
  override_resource {
    target          = oci_core_subnet.app["edge"]
    override_during = plan
    values          = { id = "subnet-edge-synthetic" }
  }
  command = plan
  variables { caddy_ingress_enabled = true }
  override_resource {
    target          = oci_core_public_ip.ingress[0]
    override_during = plan
    values          = { ip_address = "203.0.113.80" }
  }
  assert {
    condition     = oci_core_network_security_group_security_rule.acme_http[0].source == "0.0.0.0/0" && oci_core_network_security_group_security_rule.acme_http[0].network_security_group_id == "nsg-edge-synthetic" && oci_core_network_security_group_security_rule.acme_http[0].tcp_options[0].destination_port_range[0].min == 80 && oci_core_network_security_group_security_rule.acme_http[0].tcp_options[0].destination_port_range[0].max == 80
    error_message = "Only the HTTP-01 frontend port may be public."
  }
  assert {
    condition     = toset(keys(oci_core_network_security_group_security_rule.https)) == var.app_ingress_allowed_cidrs && alltrue([for rule in oci_core_network_security_group_security_rule.https : rule.source_type == "CIDR_BLOCK" && rule.tcp_options[0].destination_port_range[0].min == 443 && rule.tcp_options[0].destination_port_range[0].max == 443])
    error_message = "HTTPS must retain the exact human source union, never inherit public HTTP admission."
  }
  assert {
    condition     = toset(keys(oci_core_network_security_group_security_rule.caddy_backend_ingress)) == toset(["31080", "31443", "32081"]) && alltrue([for port, rule in oci_core_network_security_group_security_rule.caddy_backend_ingress : rule.source == "nsg-edge-synthetic" && rule.source_type == "NETWORK_SECURITY_GROUP" && rule.network_security_group_id == "nsg-nodes-synthetic" && rule.protocol == "6" && !rule.stateless && rule.tcp_options[0].destination_port_range[0].min == tonumber(port) && rule.tcp_options[0].destination_port_range[0].max == tonumber(port) && oci_core_network_security_group_security_rule.caddy_backend_egress[port].destination == "nsg-nodes-synthetic" && oci_core_network_security_group_security_rule.caddy_backend_egress[port].network_security_group_id == "nsg-edge-synthetic"])
    error_message = "Use exact paired edge/node ports; never open the whole NodePort range."
  }
  assert {
    condition     = output.ingress.environment == var.environment && output.ingress.reserved_ipv4 == "203.0.113.80" && output.ingress.edge_nsg_ocid == "nsg-edge-synthetic" && output.ingress.edge_subnet_ocid == oci_core_subnet.app["edge"].id && output.ingress.https_allowed_cidrs == var.app_ingress_allowed_cidrs
    error_message = "Renderer handoff must carry the exact reviewed firewall and stable address."
  }
}
