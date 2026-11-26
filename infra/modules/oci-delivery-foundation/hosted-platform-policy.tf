# The operator must explicitly authorize a hosted policy writer in bootstrap.
variable "allow_runtime_policy_writes" {
  description = "Allow this hosted workflow to create and update only its three named reader policies. OCI cannot enforce the contents of the submitted statements."
  type        = bool
  default     = false
  nullable    = false

  validation {
    condition = !var.allow_runtime_policy_writes || (
      contains(["staging", "production"], var.environment) && var.storage_policy != null
    )
    error_message = "Runtime policy writes require a hosted environment with an approved hosting compartment."
  }
}

locals {
  # Authorize the protected environment workflow independently of its backend and domain grants.
  hosted_scope          = "in compartment otm-${var.environment} where all {${local.workflow_subject}"
  database_admin_secret = "target.secret.name = 'otm-${var.environment}-database-admin'"
  application_policy_names = [
    "otm-${var.environment}-database-provisioning-read",
    "otm-${var.environment}-api-vault-read",
    "otm-${var.environment}-worker-vault-read",
  ]
  application_policy_targets = join(", ", [for name in local.application_policy_names : "target.policy.name = '${name}'"])
  # OCI name-based location includes descendants. Match the exact compartment for IAM operations.
  application_policy_scope = var.storage_policy == null ? null : "${local.hosted_scope}, target.compartment.id = '${var.storage_policy.compartment_ocid}', any {${local.application_policy_targets}}"

  # Group the exact networking operations by purpose so each OCI statement remains readable.
  hosted_network_operation_groups = [
    [
      "CreateVcn", "UpdateVcn", "AddVcnCidr", "ModifyVcnCidr", "RemoveVcnCidr",
      "CreateSecurityList", "UpdateSecurityList",
      "CreateSubnet", "UpdateSubnet",
    ],
    [
      "CreateInternetGateway", "UpdateInternetGateway",
      "CreateNatGateway", "UpdateNatGateway",
      "CreateServiceGateway", "UpdateServiceGateway",
      "CreateRouteTable", "UpdateRouteTable",
      "CreatePublicIp", "UpdatePublicIp",
    ],
    [
      "CreateNetworkSecurityGroup", "UpdateNetworkSecurityGroup",
      "AddNetworkSecurityGroupSecurityRules", "UpdateNetworkSecurityGroupSecurityRules", "RemoveNetworkSecurityGroupSecurityRules",
    ],
    [
      "CreateCluster", "UpdateClusterEndpointConfig",
      "CreateNodePool", "UpdateNodePool",
      "CreateDbSystem", "UpdateDbSystem", "PatchDbSystem",
    ],
  ]
  hosted_network_statements = [
    for operations in local.hosted_network_operation_groups :
    "Allow any-user to manage virtual-network-family ${local.hosted_scope}, any {${join(", ", [for operation in operations : "request.operation = '${operation}'"])}}}"
  ]
}

# Refresh the three reader policies by default. Opting into writes allows the workflow
# to set the statement bodies of those policies, including privileges within the compartment.
resource "oci_identity_policy" "workflow_platform" {
  count          = var.environment == "development" || var.storage_policy == null ? 0 : 1
  compartment_id = var.storage_policy.compartment_ocid
  name           = "otm-${var.environment}-github-platform"
  description    = "Provision environment infrastructure from the protected GitHub workflow"

  statements = concat(local.hosted_network_statements, [
    "Allow any-user to inspect compartments ${local.hosted_scope}, any {request.operation = 'GetCompartment', request.operation = 'ListAvailabilityDomains', request.operation = 'ListFaultDomains'}}",
    "Allow any-user to read virtual-network-family ${local.hosted_scope}}",

    # OKE uses instance-family authorization during managed node pool operations. The workflow
    # cannot call the underlying Compute mutation APIs directly through this grant.
    "Allow any-user to manage instance-family ${local.hosted_scope}, any {request.operation = 'CreateNodePool', request.operation = 'UpdateNodePool'}}",
    "Allow any-user to inspect instances ${local.hosted_scope}, request.operation = 'GetNodePoolOptions'}",
    "Allow any-user to read instance-images ${local.hosted_scope}, request.operation = 'ListImages'}",
    "Allow any-user to read clusters ${local.hosted_scope}, any {request.operation = 'GetCluster', request.operation = 'GetClusterOptions', request.operation = 'GetWorkRequest', request.operation = 'ListWorkRequestErrors'}}",
    "Allow any-user to manage clusters ${local.hosted_scope}, any {request.operation = 'CreateCluster', request.operation = 'UpdateCluster', request.operation = 'UpdateClusterEndpointConfig'}}",
    "Allow any-user to read cluster-node-pools ${local.hosted_scope}, any {request.operation = 'GetNodePool', request.operation = 'GetWorkRequest', request.operation = 'ListWorkRequestErrors'}}",
    "Allow any-user to manage cluster-node-pools ${local.hosted_scope}, any {request.operation = 'CreateNodePool', request.operation = 'UpdateNodePool'}}",
    "Allow any-user to read cluster-work-requests ${local.hosted_scope}, any {request.operation = 'GetWorkRequest', request.operation = 'ListWorkRequestErrors'}}",

    "Allow any-user to read postgres-db-systems ${local.hosted_scope}, any {request.operation = 'GetDbSystem', request.operation = 'GetConnectionDetails'}}",
    "Allow any-user to manage postgres-db-systems ${local.hosted_scope}, any {request.operation = 'CreateDbSystem', request.operation = 'UpdateDbSystem', request.operation = 'PatchDbSystem', request.operation = 'UpdateManagementPolicy'}}",
    "Allow any-user to read postgres-configurations ${local.hosted_scope}, any {request.operation = 'ListDefaultConfigurations', request.operation = 'GetDefaultConfiguration', request.operation = 'GetConfiguration'}}",
    "Allow any-user to read postgres-work-requests ${local.hosted_scope}, any {request.operation = 'GetWorkRequest', request.operation = 'ListWorkRequestErrors'}}",

    "Allow any-user to read vaults ${local.hosted_scope}, request.operation = 'GetVault'}",
    "Allow any-user to manage vaults ${local.hosted_scope}, all {request.operation = 'CreateVault', request.permission = 'VAULT_CREATE'}}",
    "Allow any-user to read keys ${local.hosted_scope}, request.operation = 'GetKey'}",
    "Allow any-user to use vaults ${local.hosted_scope}, all {request.operation = 'CreateKey', request.permission = 'VAULT_CREATE_KEY'}}",
    "Allow any-user to manage keys ${local.hosted_scope}, all {request.operation = 'CreateKey', request.permission = 'KEY_CREATE'}}",

    # CreateSecret requires encrypt and decrypt authorization on the key. Bind them to the
    # control-plane CreateSecret request so they cannot be used for standalone cryptography.
    "Allow any-user to use vaults ${local.hosted_scope}, all {request.operation = 'CreateSecret', request.permission = 'VAULT_CREATE_SECRET'}}",
    "Allow any-user to use keys ${local.hosted_scope}, request.operation = 'CreateSecret', any {request.permission = 'KEY_ENCRYPT', request.permission = 'KEY_DECRYPT'}}",
    "Allow any-user to manage secrets ${local.hosted_scope}, ${local.database_admin_secret}, request.operation = 'CreateSecret', request.permission = 'SECRET_CREATE'}",
    "Allow any-user to read secrets ${local.hosted_scope}, ${local.database_admin_secret}, request.operation = 'GetSecret'}",
    # Qualify the service-linked authorization in staging before allowing PostgreSQL creation.
    "Allow any-user to read secret-bundles ${local.hosted_scope}, ${local.database_admin_secret}, request.operation = 'CreateDbSystem'}",

    "Allow any-user to inspect policies ${local.application_policy_scope}, request.operation = 'GetPolicy'}",
    ], var.allow_runtime_policy_writes ? [
    "Allow any-user to manage policies ${local.application_policy_scope}, request.operation = 'CreatePolicy', request.permission = 'POLICY_CREATE'}",
    "Allow any-user to manage policies ${local.application_policy_scope}, request.operation = 'UpdatePolicy', request.permission = 'POLICY_UPDATE'}",
  ] : [])

  lifecycle {
    prevent_destroy = true
  }
}
