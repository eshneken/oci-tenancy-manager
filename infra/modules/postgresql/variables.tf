# This label binds composition, not IAM identity; staging and production use separate tenancies.
variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Use staging or production."
  }
}
# Existing hosting compartment, not an application credential or a child-tenancy reference.
variable "compartment_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.compartment_ocid))
    error_message = "Provide the hosting compartment OCID."
  }
}
# Required exact major from OTM_POSTGRESQL_VERSION; no floating/latest or automatic major upgrades.
variable "postgresql_version" {
  type = string
  validation {
    condition     = can(regex("^[1-9][0-9]$", var.postgresql_version))
    error_message = "Provide a two-digit PostgreSQL major string."
  }
}
# Exact network module bindings; this module accepts neither public endpoints nor arbitrary ingress.
variable "network" {
  type = object({
    environment = string
    subnets     = object({ database = object({ id = string }) })
    nsg_ids     = object({ database = string })
  })
  validation {
    condition     = var.network.environment == var.environment && length(var.network.subnets.database.id) > 0 && length(var.network.nsg_ids.database) > 0
    error_message = "Use this environment's database subnet and security group."
  }
}
# References only: provision an approved strong password into Vault separately, never through tfvars.
variable "administrator" {
  type = object({
    # Provisioning administrator, never the API/worker runtime login; SQL role naming subset.
    username = string
    # Existing Vault secret OCID; the provisioning requester needs scoped documented read grants.
    secret_ocid = string
    # Positive integer version string pins provisioning to the reviewed existing secret version.
    secret_version = string
  })
  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.administrator.username)) && !contains(["postgres", "oci_admin", "oci_superuser"], var.administrator.username)
    error_message = "Provide a nonreserved lowercase administrator role name of 1-63 characters."
  }
  validation {
    condition     = can(regex("^ocid1[.]vaultsecret[.][a-z0-9]+[.][a-z0-9-]+[.][a-z0-9]+$", var.administrator.secret_ocid)) && can(regex("^[1-9][0-9]*$", var.administrator.secret_version))
    error_message = "Provide an existing Vault secret OCID and explicit positive integer version; no password input."
  }
}
# Modest initial proposal; capacity changes remain reviewed infrastructure changes, not autoscaling.
variable "database" {
  type = object({
    # Two nodes preserve the proposed primary/HA-replica starting point; permit measured expansion to3.
    instance_count = optional(number, 2)
    # Integer1-8 OCPUs and16-128GB per node; live shape limits additionally checked from discovery.
    ocpus      = optional(number, 1)
    memory_gib = optional(number, 16)
    # Exact UTC windows: daily backupHH:MM and maintenanceDAY HH:MM; operator chooses both explicitly.
    backup_start_utc      = string
    maintenance_start_utc = string
    # Default false blocks accidental major replacement; enable only for approved staged maintenance.
    allow_major_version_upgrade = optional(bool, false)
  })
  validation {
    condition = (
      var.database.instance_count == floor(var.database.instance_count) && var.database.instance_count >= 2 && var.database.instance_count <= 3 &&
      var.database.ocpus == floor(var.database.ocpus) && var.database.ocpus >= 1 && var.database.ocpus <= 8 &&
      var.database.memory_gib == floor(var.database.memory_gib) && var.database.memory_gib >= 16 && var.database.memory_gib <= 128 && var.database.memory_gib <= var.database.ocpus * 64
    )
    error_message = "Use2-3 nodes,1-8 integer OCPUs and16-128GB integer RAM per node, at most64GB/OCPU."
  }
  validation {
    condition     = can(regex("^([01][0-9]|2[0-3]):[0-5][0-9]$", var.database.backup_start_utc)) && can(regex("^(MON|TUE|WED|THU|FRI|SAT|SUN) ([01][0-9]|2[0-3]):[0-5][0-9]$", var.database.maintenance_start_utc))
    error_message = "Specify backup HH:MM and maintenance DAY HH:MM in UTC."
  }
}
