# Read the explicit tenancy namespace; a similar resource name must not select another target.
data "oci_objectstorage_namespace" "target" {
  compartment_id = var.target.tenancy_ocid
  lifecycle {
    postcondition {
      condition     = self.namespace == var.target.object_storage_namespace
      error_message = "The live namespace does not match the approved environment target record."
    }
  }
}

# No retention lock: Terraform must update state and delete its transient lock normally.
# Versioning and prevent_destroy reduce accidental loss; privileged deletion remains an IAM concern.
resource "oci_objectstorage_bucket" "state" {
  compartment_id = var.target.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.target.namespace
  name           = "${var.name_prefix}-${var.expected_environment}-tfstate"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Enabled"
  # OCI free-form tag keys cannot contain periods or spaces.
  freeform_tags = {
    "otm-environment" = var.expected_environment
    "otm-component"   = "terraform-state"
  }
  lifecycle {
    prevent_destroy = true
  }
}
