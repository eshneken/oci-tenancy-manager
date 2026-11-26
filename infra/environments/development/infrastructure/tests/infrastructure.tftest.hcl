# Mock-only plans; no local OCI profile, cloud identity, remote backend or API is used.
mock_provider "oci" {
  override_during = plan
}
override_resource {
  override_during = plan
  target          = oci_kms_key.application_software
  values          = { id = "ocid1.key.oc1.iad.syntheticsoftware" }
}
override_module { target = module.atlas_sso }
variables {
  identity_domain_url = "https://idcs-synthetic.identity.oraclecloud.com"
  atlas_sso = {
    corporate_idp_id = "dddddddddddddddddddddddddddddddd"
  }
  oci_auth                 = "ResourcePrincipal"
  hosting_compartment_ocid = "ocid1.compartment.oc1..development"
  target = {
    environment              = "development"
    tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
    object_storage_namespace = "syntheticnamespace"
    region                   = "us-ashburn-1"
  }
}
run "isolated_development_infrastructure" {
  command = plan
  assert {
    condition     = oci_kms_vault.application.compartment_id == var.hosting_compartment_ocid && oci_kms_key.application_software.compartment_id == var.hosting_compartment_ocid
    error_message = "Development infrastructure must use only its explicit compartment."
  }
  assert {
    condition     = oci_kms_vault.application.vault_type == "DEFAULT" && oci_kms_key.application_software.protection_mode == "SOFTWARE" && oci_kms_key.application_software.key_shape[0].algorithm == "AES" && oci_kms_key.application_software.key_shape[0].length == 32 && !oci_kms_key.application_software.is_auto_rotation_enabled
    error_message = "Use the shared Vault and software-protected AES-256 policy without unsupported automatic rotation."
  }
  assert {
    condition     = output.custody.key_ocid == oci_kms_key.application_software.id
    error_message = "Select the software-protected key for application custody."
  }
  assert {
    condition     = oci_kms_vault.application.freeform_tags["otm-environment"] == "development"
    error_message = "Development must not be labeled staging."
  }
  assert {
    condition     = alltrue([for key in concat(keys(oci_kms_vault.application.freeform_tags), keys(oci_kms_key.application_software.freeform_tags)) : can(regex("^[A-Za-z0-9-]+$", key))])
    error_message = "Vault and key tag keys must use OCI-compatible names."
  }
}
run "reject_api_key_auth" {
  command = plan
  variables { oci_auth = "APIKey" }
  expect_failures = [var.oci_auth]
}
run "reject_compartment_injection" {
  command = plan
  variables { hosting_compartment_ocid = "bad' compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}
run "reject_staging_target" {
  command = plan
  variables {
    target = {
      environment              = "staging"
      tenancy_ocid             = "ocid1.tenancy.oc1..synthetic"
      object_storage_namespace = "syntheticnamespace"
      region                   = "us-ashburn-1"
    }
  }
  expect_failures = [var.target]
}
