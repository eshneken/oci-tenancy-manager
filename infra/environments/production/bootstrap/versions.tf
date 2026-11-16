# Both isolated roots use the exact same reviewed toolchain.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.13.0"
    }
  }
  # Bucket creation precedes remote state. Operators must select an explicit private local path.
  # Subsequent migration is separate reviewed work; never initialize a second state for this bucket.
  backend "local" {}
}
