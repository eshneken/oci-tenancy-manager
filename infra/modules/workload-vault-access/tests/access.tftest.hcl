# IAM statements are planned synthetically; no live identity or authorization is exercised.
mock_provider "oci" {}
variables {
  environment              = "staging"
  hosting_compartment_ocid = "ocid1.compartment.oc1..syntheticstaging"
  cluster_ocid             = "ocid1.cluster.oc1.iad.synthetic"
  application_vault_ocid   = "ocid1.vault.oc1.iad.syntheticapplication"
}
run "exact_staging_readers" {
  command = plan
  assert {
    condition     = toset(keys(oci_identity_policy.reader)) == toset(["api", "worker"])
    error_message = "No migration, node or wildcard workload should receive Vault permissions."
  }
  assert {
    condition = alltrue([for role in ["api", "worker"] : toset(oci_identity_policy.reader[role].statements) == toset([
      "Allow any-user to read secret-family in compartment id ${var.hosting_compartment_ocid} where all {request.principal.type = 'workload', request.principal.cluster_id = '${var.cluster_ocid}', request.principal.namespace = 'otm-staging', request.principal.service_account = 'otm-${role}', target.vault.id = '${var.application_vault_ocid}'}"
    ])])
    error_message = "Reader grants must bind every identity and target condition, without writes."
  }
}
run "exact_production_namespace" {
  command = plan
  variables { environment = "production" }
  assert {
    condition     = output.access.namespace == "otm-production" && strcontains(oci_identity_policy.reader["api"].statements[0], "namespace = 'otm-production'")
    error_message = "Production IAM must not use staging's namespace."
  }
}
run "reject_local_environment" {
  command = plan
  variables { environment = "local" }
  expect_failures = [var.environment]
}
run "reject_cluster_injection" {
  command = plan
  variables { cluster_ocid = "bad' or anything" }
  expect_failures = [var.cluster_ocid]
}
run "reject_compartment_injection" {
  command = plan
  variables { hosting_compartment_ocid = "bad' compartment" }
  expect_failures = [var.hosting_compartment_ocid]
}
run "reject_wrong_vault_type" {
  command = plan
  variables { application_vault_ocid = "ocid1.compartment.oc1..synthetic" }
  expect_failures = [var.application_vault_ocid]
}
