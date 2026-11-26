# Provider effects remain mock-only; Vaults/keys/IAM share the existing hosting compartment.
mock_provider "oci" {
  override_during = apply
  mock_resource "oci_kms_vault" {
    defaults = { management_endpoint = "https://management.example.test" }
  }
}
variables {
  environment                     = "staging"
  hosting_compartment_ocid        = "ocid1.compartment.oc1..synthetichosting"
  database_provisioner_group_name = "otm-staging-database-provisioners"
}
run "separate_shared_software_custody_domains" {
  command = apply
  assert {
    condition = (
      oci_kms_vault.domain["database-provisioning"].id != oci_kms_vault.domain["application-secrets"].id && length(oci_kms_vault.domain) == 2 && length(oci_kms_key.domain) == 2 &&
      alltrue([for domain, vault in oci_kms_vault.domain : vault.vault_type == "DEFAULT" && vault.compartment_id == var.hosting_compartment_ocid]) &&
      alltrue([for domain, key in oci_kms_key.domain : key.compartment_id == var.hosting_compartment_ocid && key.management_endpoint == oci_kms_vault.domain[domain].management_endpoint && key.protection_mode == "SOFTWARE" && key.key_shape[0].algorithm == "AES" && key.key_shape[0].length == 32 && !key.is_auto_rotation_enabled])
    )
    error_message = "Keep distinct shared Vaults and software-protected AES-256 keys in the single existing compartment, with no exported secrets."
  }
}
run "credential_read_policy_is_exactly_database_scoped" {
  command = plan
  assert {
    condition = oci_identity_policy.database_reader.compartment_id == var.hosting_compartment_ocid && oci_identity_policy.database_reader.statements == tolist([
      "Allow group Default/otm-staging-database-provisioners to read secret-family in compartment otm-${var.environment} where target.vault.id = '${oci_kms_vault.domain["database-provisioning"].id}'",
      "Allow group Default/otm-staging-database-provisioners to read vaults in compartment otm-${var.environment} where target.vault.id = '${oci_kms_vault.domain["database-provisioning"].id}'",
    ])
    error_message = "Only the exact DB Vault may be read in the shared compartment; no unconditioned, app, write or tenancy-wide grants."
  }
}
run "reject_group_name_or_policy_injection" {
  command = plan
  variables { database_provisioner_group_name = "Operators to manage all-resources in tenancy" }
  expect_failures = [var.database_provisioner_group_name]
}
run "reject_missing_reader" {
  command = plan
  variables { database_provisioner_group_name = "" }
  expect_failures = [var.database_provisioner_group_name]
}
run "reject_bad_parent" {
  command = plan
  variables { hosting_compartment_ocid = "not-a-compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}
run "reject_unknown_environment" {
  command = plan
  variables {
    environment                     = "preview"
    database_provisioner_group_name = "otm-preview-database-provisioners"
  }
  expect_failures = [var.environment]
}
run "production_names_and_references_stay_bound" {
  command = plan
  variables {
    environment                     = "production"
    database_provisioner_group_name = "otm-production-database-provisioners"
  }
  assert {
    condition     = output.custody.environment == "production" && oci_kms_vault.domain["database-provisioning"].display_name == "otm-production-database-provisioning" && oci_kms_vault.domain["application-secrets"].display_name == "otm-production-application-secrets" && alltrue([for domain in values(output.custody.domains) : domain.compartment_ocid == var.hosting_compartment_ocid])
    error_message = "Environment labels must drive all resource names and private output bindings."
  }
}
