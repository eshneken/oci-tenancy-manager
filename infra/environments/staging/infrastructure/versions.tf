# Both isolated roots use the exact same reviewed toolchain.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.14.0"
    }
  }
  # Environment infrastructure state uses its own private remote backend configuration, never bootstrap state.
  backend "oci" {
    key  = "infrastructure/staging/terraform.tfstate"
    auth = "SecurityToken"
  }
}
