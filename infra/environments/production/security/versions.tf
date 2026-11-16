# Both isolated roots use the exact same reviewed toolchain.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.13.0"
    }
  }
  # Security state has its own fixed remote key; never share platform or bootstrap state.
  backend "oci" {
    key  = "security/production/terraform.tfstate"
    auth = "SecurityToken"
  }
}
