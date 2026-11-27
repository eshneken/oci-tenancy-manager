# Both isolated roots use the exact same reviewed toolchain.
terraform {
  required_version = "= 1.15.5"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "= 6.13.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "= 2.3.5"
    }
    oci = {
      source  = "oracle/oci"
      version = "= 9.14.0"
    }
  }
  # Bucket creation precedes remote state. Operators must select an explicit private local path.
  # Subsequent migration is separate reviewed work; never initialize a second state for this bucket.
  backend "local" {}
}
