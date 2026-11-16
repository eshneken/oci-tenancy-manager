# Provider identity is explicit and separate from backend authentication and app credentials.
provider "oci" {
  auth                = var.oci_auth
  region              = var.target.region
  tenancy_ocid        = var.target.tenancy_ocid
  config_file_profile = var.oci_auth == "SecurityToken" ? var.oci_profile : null
}

# As in bootstrap, namespace agreement is a sanity check, not principal/compartment authorization.
data "oci_objectstorage_namespace" "target" {
  compartment_id = var.target.tenancy_ocid
  lifecycle {
    postcondition {
      condition     = self.namespace == var.target.object_storage_namespace
      error_message = "The live namespace does not match this environment's approved target."
    }
  }
}

module "network" {
  source                    = "../../../modules/networking"
  environment               = "production"
  compartment_ocid          = var.hosting_compartment_ocid
  vcn_cidr                  = var.vcn_cidr
  app_ingress_allowed_cidrs = var.app_ingress_allowed_cidrs
  smtp_egress               = var.smtp_egress
  caddy_ingress_enabled     = var.caddy_ingress_enabled
  depends_on                = [data.oci_objectstorage_namespace.target]
}

# Keep deployment coordinates out of ordinary output and public CI artifacts.
output "network" {
  description = "Private network bindings for the Enhanced OKE cluster; no app load balancer yet."
  value       = module.network.network
  sensitive   = true
}

# Exact version comes from Actions; image is resolved in staging or bound to its qualified record.
module "oke" {
  source               = "../../../modules/oke"
  environment          = "production"
  tenancy_ocid         = var.target.tenancy_ocid
  compartment_ocid     = var.hosting_compartment_ocid
  network              = module.network.network
  oke                  = merge(var.oke, { kubernetes_version = var.oke_kubernetes_version })
  worker_cloud_init    = var.worker_cloud_init
  qualified_node_image = var.qualified_node_image
}

# Operational endpoints/IDs remain private and contain no kubeconfig token or signing material.
output "cluster" {
  description = "Environment-bound cluster/nodepool deployment references; live qualification pending."
  value       = module.oke.cluster
  sensitive   = true
}

# Database consumes this environment's existing private subnet/NSG and provisioning Vault reference.
module "postgresql" {
  source             = "../../../modules/postgresql"
  environment        = "production"
  compartment_ocid   = var.hosting_compartment_ocid
  postgresql_version = var.postgresql_version
  network            = module.network.network
  administrator      = var.database_administrator
  database           = var.database
}
# No application database login is created or exposed by this source composition.
output "database" {
  value       = module.postgresql.database
  sensitive   = true
  description = "Private PostgreSQL endpoint/CA references; live database recovery and runtime roles unqualified."
}

# Created after the exact cluster is known; security Vault already exists, avoiding a state cycle.
module "workload_vault_access" {
  source                   = "../../../modules/workload-vault-access"
  environment              = "production"
  hosting_compartment_ocid = var.hosting_compartment_ocid
  cluster_ocid             = module.oke.cluster.id
  application_vault_ocid   = var.application_vault_ocid
}
output "workload_vault_access" {
  value       = module.workload_vault_access.access
  sensitive   = true
  description = "Exact workload/Vault IAM references; effective live permissions remain unqualified."
}

# Private input for the offline renderer; never upload actual addresses/NSG IDs as CI artifacts.
output "ingress" {
  value       = module.network.ingress
  sensitive   = true
  description = "Exact firewall/address handoff, null while ingress infrastructure is disabled."
}
