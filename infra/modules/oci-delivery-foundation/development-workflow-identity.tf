locals {
  development_workflow_group_name = "otm-development-github-identity"
  development_workflow_enabled    = var.development_workflow_dynamic_group != null
  development_workflow_existing   = try(var.development_workflow_dynamic_group.existing, null)
  development_workflow_rule       = local.development_workflow_enabled ? "resource.id = '${var.development_workflow_dynamic_group.principal_ocid}'" : null
  development_workflow_group_guid = !local.development_workflow_enabled ? null : (
    local.development_workflow_existing == null ?
    one(one(data.oci_identity_domains_dynamic_resource_groups.fresh_development_workflow).dynamic_resource_groups).id :
    one(data.oci_identity_domains_dynamic_resource_group.development_workflow).id
  )
  application_administrator_role  = "Application Administrator"
  application_administrator_app   = "IDCSAppId"
  application_administrator_grant = "ADMINISTRATOR_TO_DYNAMIC_RESOURCE_GROUP"
}

# A unique, administrative AppRole in the selected Default domain supplies the exact entitlement.
data "oci_identity_domains_app_roles" "application_administrator" {
  count           = local.development_workflow_enabled ? 1 : 0
  idcs_endpoint   = local.domain_url
  app_role_filter = "displayName eq \"${local.application_administrator_role}\""
  app_role_count  = 2
  attributes      = "id,displayName,adminRole,app"

  lifecycle {
    postcondition {
      condition = try(
        self.total_results == 1 &&
        one(self.app_roles).display_name == local.application_administrator_role &&
        one(self.app_roles).admin_role &&
        can(regex("^[0-9a-f]{32}$", one(self.app_roles).id)) &&
        one(one(self.app_roles).app).value == local.application_administrator_app,
        false
      )
      error_message = "Expected the unique Application Administrator role and its app in the selected identity domain."
    }
  }
}

# Verify an existing group and role grant independently before the bootstrap can adopt them.
data "oci_identity_domains_dynamic_resource_group" "development_workflow" {
  count                     = local.development_workflow_existing == null ? 0 : 1
  dynamic_resource_group_id = local.development_workflow_existing.group_id
  idcs_endpoint             = local.domain_url
  attributes                = "id,ocid,displayName,matchingRule,domainOcid,tenancyOcid,deleteInProgress"

  lifecycle {
    postcondition {
      condition = (
        self.id == local.development_workflow_existing.group_id &&
        can(regex("^ocid1[.]dynamicgroup[.]oc1[.][a-z0-9-]*[.][a-z0-9]{1,220}$", self.ocid)) &&
        self.display_name == local.development_workflow_group_name &&
        self.domain_ocid == var.identity_domain_ocid &&
        self.tenancy_ocid == var.tenancy_ocid &&
        self.delete_in_progress != true &&
        self.matching_rule == local.development_workflow_rule
      )
      error_message = "Expected the existing Default-domain development workflow group with its exact exchanged-principal rule."
    }
  }
}

# Resolve the SCIM GUID after creating a native Default-domain group. Filter on the new immutable
# native OCID so the role can only be assigned to that group.
data "oci_identity_domains_dynamic_resource_groups" "fresh_development_workflow" {
  count                         = local.development_workflow_enabled && local.development_workflow_existing == null ? 1 : 0
  idcs_endpoint                 = local.domain_url
  dynamic_resource_group_filter = "ocid eq \"${oci_identity_dynamic_group.development_workflow[0].id}\""
  dynamic_resource_group_count  = 2
  attributes                    = "id,ocid,displayName,matchingRule,domainOcid,tenancyOcid,deleteInProgress"

  lifecycle {
    postcondition {
      condition = try(
        self.total_results == 1 &&
        can(regex("^[0-9a-f]{32}$", one(self.dynamic_resource_groups).id)) &&
        one(self.dynamic_resource_groups).ocid == oci_identity_dynamic_group.development_workflow[0].id &&
        one(self.dynamic_resource_groups).display_name == local.development_workflow_group_name &&
        one(self.dynamic_resource_groups).domain_ocid == var.identity_domain_ocid &&
        one(self.dynamic_resource_groups).tenancy_ocid == var.tenancy_ocid &&
        one(self.dynamic_resource_groups).delete_in_progress != true &&
        one(self.dynamic_resource_groups).matching_rule == local.development_workflow_rule,
        false
      )
      error_message = "Expected the SCIM identity of the exact newly created native development workflow group."
    }
  }
}

data "oci_identity_domains_grant" "development_application_administrator" {
  count         = local.development_workflow_existing == null ? 0 : 1
  grant_id      = local.development_workflow_existing.grant_id
  idcs_endpoint = local.domain_url
  attributes    = "id,schemas,app,grantee,entitlement,grantMechanism"

  lifecycle {
    postcondition {
      condition = try(
        self.id == local.development_workflow_existing.grant_id &&
        self.schemas == tolist(["urn:ietf:params:scim:schemas:oracle:idcs:Grant"]) &&
        self.grant_mechanism == local.application_administrator_grant &&
        one(self.grantee).type == "DynamicResourceGroup" &&
        one(self.grantee).value == one(data.oci_identity_domains_dynamic_resource_group.development_workflow).id &&
        one(self.app).value == one(one(data.oci_identity_domains_app_roles.application_administrator[0].app_roles).app).value &&
        one(self.entitlement).attribute_name == "appRoles" &&
        one(self.entitlement).attribute_value == one(data.oci_identity_domains_app_roles.application_administrator[0].app_roles).id,
        false
      )
      error_message = "Expected the existing exact Application Administrator grant to the verified development workflow group."
    }
  }
}

resource "oci_identity_dynamic_group" "development_workflow" {
  count          = local.development_workflow_enabled ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = local.development_workflow_group_name
  description    = "Development infrastructure workflow identity"
  matching_rule  = local.development_workflow_rule

  depends_on = [data.oci_identity_domains_dynamic_resource_group.development_workflow]

  lifecycle {
    prevent_destroy = true
    postcondition {
      condition = (
        self.compartment_id == var.tenancy_ocid &&
        self.state == "ACTIVE" &&
        self.name == local.development_workflow_group_name &&
        self.matching_rule == local.development_workflow_rule &&
        (local.development_workflow_existing == null ? true : self.id == one(data.oci_identity_domains_dynamic_resource_group.development_workflow).ocid)
      )
      error_message = "The managed dynamic group must match the exact development principal in the selected domain."
    }
  }
}

resource "oci_identity_domains_grant" "development_application_administrator" {
  count = local.development_workflow_enabled ? 1 : 0
  # In the pinned provider attributes is ForceNew and the importer does not populate it.
  # Use a separate projected data read to verify the existing grant without replacing it.
  idcs_endpoint   = local.domain_url
  schemas         = ["urn:ietf:params:scim:schemas:oracle:idcs:Grant"]
  grant_mechanism = local.application_administrator_grant
  app {
    value = one(one(data.oci_identity_domains_app_roles.application_administrator[0].app_roles).app).value
  }
  grantee {
    type  = "DynamicResourceGroup"
    value = local.development_workflow_group_guid
  }
  entitlement {
    attribute_name  = "appRoles"
    attribute_value = one(data.oci_identity_domains_app_roles.application_administrator[0].app_roles).id
  }

  depends_on = [
    data.oci_identity_domains_grant.development_application_administrator,
    oci_identity_dynamic_group.development_workflow,
  ]

  lifecycle {
    prevent_destroy = true
    postcondition {
      condition = try(
        (local.development_workflow_existing == null ? true : self.id == local.development_workflow_existing.grant_id) &&
        self.grant_mechanism == local.application_administrator_grant &&
        one(self.grantee).type == "DynamicResourceGroup" &&
        one(self.grantee).value == local.development_workflow_group_guid &&
        one(self.app).value == one(one(data.oci_identity_domains_app_roles.application_administrator[0].app_roles).app).value &&
        one(self.entitlement).attribute_name == "appRoles" &&
        one(self.entitlement).attribute_value == one(data.oci_identity_domains_app_roles.application_administrator[0].app_roles).id,
        false
      )
      error_message = "The managed grant must assign only Application Administrator to the development workflow group."
    }
  }
}

output "development_workflow_adoption_group_ocid" {
  description = "Verified native OCID of the operator-selected development dynamic group for import."
  value       = one(data.oci_identity_domains_dynamic_resource_group.development_workflow[*].ocid)
}
