# Keep the laptop principal separate from the group that grants access to the application.
data "oci_identity_group" "local_app_writer" {
  count    = var.local_app_iam == null ? 0 : 1
  group_id = var.local_app_iam.writer_group_ocid

  lifecycle {
    postcondition {
      condition     = self.name == "otm-development-localapp" && self.compartment_id == var.target.tenancy_ocid && self.state == "ACTIVE"
      error_message = "Expected the active development laptop writer group in the selected tenancy."
    }
  }
}

data "oci_identity_group" "local_app_assignment" {
  count    = var.local_app_iam == null ? 0 : 1
  group_id = var.local_app_iam.assignment_group_ocid

  lifecycle {
    postcondition {
      condition     = self.name == "otm-development-users" && self.compartment_id == var.target.tenancy_ocid && self.state == "ACTIVE"
      error_message = "Expected the active development Atlas application group in the selected tenancy."
    }
  }
}

data "oci_identity_domain" "local_app_domain" {
  count     = var.local_app_iam == null ? 0 : 1
  domain_id = var.local_app_iam.domain_ocid

  lifecycle {
    postcondition {
      condition     = self.compartment_id == var.target.tenancy_ocid && self.display_name == "Default" && self.state == "ACTIVE"
      error_message = "Expected the active Default identity domain at the selected tenancy root."
    }
  }
}

locals {
  # Write names in IAM while verifying each existing resource by its OCID.
  local_app_subject = var.local_app_iam == null ? null : "Allow group ${data.oci_identity_domain.local_app_domain[0].display_name}/${data.oci_identity_group.local_app_writer[0].name}"
  local_app_domain  = var.local_app_iam == null ? null : "target.resource.domain.name = '${data.oci_identity_domain.local_app_domain[0].display_name}'"
  local_app_group   = var.local_app_iam == null ? null : "target.group.name = '${data.oci_identity_group.local_app_assignment[0].name}'"
}

# Identity Domains resources belong to the root domain, not to the development compartment.
# This opt-in policy requires live membership authorization qualification before enabling enrollment.
resource "oci_identity_policy" "local_app" {
  count          = var.local_app_iam == null ? 0 : 1
  compartment_id = var.target.tenancy_ocid
  name           = "otm-development-localapp"
  description    = "Identity domain access for development administrator enrollment"
  statements = concat([
    # The approved pilot grants permit group and user updates across the tenancy.
    # Atlas validates the exact user and group for its own membership operations.
    "${local.local_app_subject} to use groups in tenancy",
    "${local.local_app_subject} to use users in tenancy",
    ], var.local_app_iam.create_federated_users ? [
    # OCI limits the operation. Atlas validates the federated-only and no-notification payload.
    "${local.local_app_subject} to manage users in tenancy where all {${local.local_app_domain}, request.operation = 'CreateUser'}",
  ] : [])
  depends_on = [
    data.oci_identity_compartment.development,
    data.oci_identity_domain.local_app_domain,
    data.oci_identity_group.local_app_writer,
    data.oci_identity_group.local_app_assignment,
  ]
}
