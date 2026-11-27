# Lock the tested CLI/provider; updates require a reviewed source and checksum change.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.14.0"
    }
  }
}
