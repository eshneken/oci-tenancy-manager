# Mock-only plans; no local OCI profile, cloud identity, remote backend or API is used.
mock_provider "oci" {}
variables {
  oci_profile              = "ATLAS_DEV"
  tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
  hosting_compartment_ocid = "ocid1.compartment.oc1..development"
  region                   = "us-ashburn-1"
}
run "isolated_laptop_custody" {
  command = plan
  assert {
    condition     = oci_kms_vault.application.compartment_id == var.hosting_compartment_ocid && oci_kms_key.application.compartment_id == var.hosting_compartment_ocid
    error_message = "Development custody must use only its explicit compartment."
  }
  assert {
    condition     = oci_kms_vault.application.vault_type == "DEFAULT" && oci_kms_key.application.protection_mode == "HSM" && oci_kms_key.application.key_shape[0].length == 32 && !oci_kms_key.application.is_auto_rotation_enabled
    error_message = "Use the shared Vault/HSM AES256 policy without unsupported automatic rotation."
  }
  assert {
    condition     = oci_kms_vault.application.freeform_tags["otm.environment"] == "development"
    error_message = "Development must not be labeled staging."
  }
}
run "reject_default_profile" {
  command = plan
  variables { oci_profile = "DEFAULT" }
  expect_failures = [var.oci_profile]
}
run "reject_compartment_injection" {
  command = plan
  variables { hosting_compartment_ocid = "bad' compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}
run "reject_wrong_tenancy_type" {
  command = plan
  variables { tenancy_ocid = "ocid1.compartment.oc1..synthetic" }
  expect_failures = [var.tenancy_ocid]
}
