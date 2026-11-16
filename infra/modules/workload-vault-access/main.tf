# Identity is the exact cluster/namespace/service-account tuple, never the node dynamic group.
locals {
  namespace = "otm-${var.environment}"
  readers   = toset(["api", "worker"])
}
# Current source supports reads only. Publication/rotation/deletion grants require later adapters.
resource "oci_identity_policy" "reader" {
  for_each       = local.readers
  compartment_id = var.hosting_compartment_ocid
  name           = "otm-${var.environment}-${each.key}-vault-read"
  description    = "Read only application custody through this exact OKE workload identity"
  statements = [
    "Allow any-user to read secret-family in compartment id ${var.hosting_compartment_ocid} where all {request.principal.type = 'workload', request.principal.cluster_id = '${var.cluster_ocid}', request.principal.namespace = '${local.namespace}', request.principal.service_account = 'otm-${each.key}', target.vault.id = '${var.application_vault_ocid}'}"
  ]
  freeform_tags = { "otm.environment" = var.environment, "otm.component" = "${each.key}-vault-read" }
}
# No secret values, kubeconfig tokens or newly granted identity are returned.
output "access" {
  sensitive = true
  value = {
    environment            = var.environment
    cluster_ocid           = var.cluster_ocid
    namespace              = local.namespace
    application_vault_ocid = var.application_vault_ocid
    service_accounts       = { for role in local.readers : role => "otm-${role}" }
    policy_ocids           = { for role in local.readers : role => oci_identity_policy.reader[role].id }
  }
}
