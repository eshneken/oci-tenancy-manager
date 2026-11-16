# Both isolated roots use the exact same reviewed toolchain.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.13.0"
    }
  }
  # Platform state uses its own private remote backend configuration, never bootstrap state.
  backend "oci" {
    key  = "platform/production/terraform.tfstate"
    auth = "SecurityToken"
  }
}
