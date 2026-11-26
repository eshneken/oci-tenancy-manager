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

# Own the service identity and signer group in the verified Default domain.
resource "oci_identity_user" "local_app" {
  count          = var.local_app_iam == null ? 0 : 1
  compartment_id = var.target.tenancy_ocid
  name           = "otm-development-localapp"
  description    = "Identity for development administrator enrollment"
  depends_on     = [data.oci_identity_domain.local_app_domain]

  lifecycle {
    prevent_destroy = true
    # The adopted account's description is unset. New accounts receive the description above.
    ignore_changes = [description]
  }
}

resource "oci_identity_group" "local_app_writer" {
  count          = var.local_app_iam == null ? 0 : 1
  compartment_id = var.target.tenancy_ocid
  name           = "otm-development-localapp"
  description    = "Group mapped to OTM permissions for local laptop development & testing"
  depends_on     = [data.oci_identity_domain.local_app_domain]

  lifecycle {
    prevent_destroy = true
  }
}

# The service identity gains only its dedicated writer group from this bootstrap.
resource "oci_identity_user_group_membership" "local_app" {
  count    = var.local_app_iam == null ? 0 : 1
  user_id  = oci_identity_user.local_app[0].id
  group_id = oci_identity_group.local_app_writer[0].id

  lifecycle {
    prevent_destroy = true
  }
}

# OCI stores the uploaded public key; the private key is never an input or resource.
resource "oci_identity_api_key" "local_app" {
  count     = var.local_app_iam == null ? 0 : 1
  user_id   = oci_identity_user.local_app[0].id
  key_value = "${trimspace(var.local_app_iam.signing_public_key_pem)}\n"

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  # The Atlas assignment group is owned by CI and is not a dependency of bootstrap.
  local_app_subject = var.local_app_iam == null ? null : "Allow group ${data.oci_identity_domain.local_app_domain[0].display_name}/${oci_identity_group.local_app_writer[0].name}"
  local_app_domain  = var.local_app_iam == null ? null : "target.resource.domain.name = '${data.oci_identity_domain.local_app_domain[0].display_name}'"
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
  lifecycle {
    prevent_destroy = true
  }
}
