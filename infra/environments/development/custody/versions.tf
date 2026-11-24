# Laptop development owns no hosted platform; this state contains only its independent custody.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.13.0"
    }
  }
  # The development bucket is bootstrapped separately. The custody state key is fixed.
  backend "oci" {
    key  = "custody/development/terraform.tfstate"
    auth = "ResourcePrincipal"
  }
}
