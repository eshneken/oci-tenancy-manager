# Laptop development owns no hosted platform; this state contains only its independent custody.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.13.0"
    }
  }
  # Set an absolute private path with -backend-config before applying; never use staging state.
  backend "local" {}
}
