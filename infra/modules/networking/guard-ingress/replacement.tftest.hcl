mock_provider "oci" {
  override_during = apply
  mock_data "oci_core_services" {
    defaults = { services = [{ id = "service-synthetic", cidr_block = "all-synthetic-services-in-oracle-services-network", name = "All SYN Services In Oracle Services Network" }] }
  }
}
variables {
  environment               = "staging"
  compartment_ocid          = "ocid1.compartment.oc1..synthetic"
  vcn_cidr                  = "10.80.0.0/16"
  app_ingress_allowed_cidrs = ["198.51.100.0/24"]
  caddy_ingress_enabled     = true
}
run "seed_mock_ingress" { command = apply }
run "reject_ingress_address_replacement" {
  command = plan
  plan_options { replace = [oci_core_public_ip.ingress[0]] }
}
