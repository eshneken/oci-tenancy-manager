# A fixed root rejects a target record labeled for the other environment.
variable "target" {
  description = "Approved production target references; never include credentials."
  type = object({
    environment              = string
    tenancy_ocid             = string
    object_storage_namespace = string
    region                   = optional(string, "us-ashburn-1")
  })
  validation {
    condition     = var.target.environment == "production"
    error_message = "This root accepts only the production environment target record."
  }
}

# Do not silently fall back to a long-lived API signing key or use child/app credentials.
variable "oci_auth" {
  type        = string
  default     = "SecurityToken"
  description = "Authenticated operator SecurityToken, or explicitly qualified resource/instance principal."
  validation {
    condition     = contains(["SecurityToken", "ResourcePrincipal", "InstancePrincipal"], var.oci_auth)
    error_message = "Use SecurityToken, ResourcePrincipal or InstancePrincipal; no APIKey fallback."
  }
}

# The name points to private operator custody; its tokens/keys are not Terraform inputs.
variable "oci_profile" {
  type        = string
  default     = "DEFAULT"
  description = "Nonempty OCI profile name, used only for SecurityToken authentication."
  validation {
    condition     = length(trimspace(var.oci_profile)) > 0 && length(var.oci_profile) <= 128
    error_message = "Provide a nonempty profile name of at most 128 characters."
  }
}

# Canonical private /16 through /20; check enterprise routing overlap before live use.
variable "vcn_cidr" {
  description = "Environment-owned RFC1918 IPv4 network; module validates subdivision bounds."
  type        = string
}

# Only the shared protected release variable supplies this required, IPv4-only list.
variable "app_ingress_allowed_cidrs" {
  description = "Validated OTM_ALLOWED_SOURCE_CIDRS input; no public or empty default."
  type        = set(string)
}

# Nonsecret protected-environment Actions pin; no default/floating version is permitted.
variable "oke_kubernetes_version" {
  description = "OTM_OKE_KUBERNETES_VERSION: exact reviewed vMAJOR.MINOR.PATCH, at most32 characters."
  type        = string
  validation {
    condition     = length(var.oke_kubernetes_version) <= 32 && can(regex("^v[1-9][0-9]*[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)$", var.oke_kubernetes_version))
    error_message = "Provide an exact canonical OKE patch version, not latest or a minor-only value."
  }
}

# Required OCI-managed PostgreSQL major; changes are reviewed infrastructure maintenance.
variable "postgresql_version" {
  description = "OTM_POSTGRESQL_VERSION: two-digit major string, such as 18. Minor versions and upgrade approval are separate."
  type        = string
  validation {
    condition     = can(regex("^[1-9][0-9]$", var.postgresql_version))
    error_message = "Provide the PostgreSQL major version as a two-digit string; service availability is qualified separately."
  }
}

# Pins are supplied by the environment's reviewed qualification, never selected as floating latest.
variable "oke" {
  description = "Pinned OKE release/OS/placements and cost-bounded initial ARM pool configuration."
  type = object({
    # Oracle Linux major version, exactly8 or9; held separately to avoid a silent OS-family jump.
    node_os_major = optional(string, "8")
    # One to three tenancy-specific AD names, verified against live discovery; all fault domains used.
    availability_domains = list(string)
    # Three to nine managed nodes; initial proposal is three, not a live capacity guarantee.
    node_count = optional(number, 3)
    # Integer A1 OCPUs per node, 1-8; defaults are provisional until staging load qualification.
    node_ocpus = optional(number, 2)
    # RAM GiB per node, 8-64 and at most 64GiB/OCPU; default8 keeps the initial pool modest.
    node_memory_gib = optional(number, 8)
    # Boot volume GiB per node, integer50-500; contains OS/images only, not PostgreSQL data.
    boot_volume_gib = optional(number, 50)
    # Integer1-31 pods per node; pod subnet must fit the pool plus one surge node.
    max_pods_per_node = optional(number, 31)
    # Canonical private IPv4 /16-/24 service range; must not overlap the VCN or enterprise routes.
    services_cidr = optional(string, "10.96.0.0/16")
  })
  validation {
    condition     = contains(["8", "9"], var.oke.node_os_major)
    error_message = "Select the reviewed Oracle Linux major, 8 or 9."
  }
  validation {
    condition = (
      length(var.oke.availability_domains) >= 1 && length(var.oke.availability_domains) <= 3 &&
      length(toset(var.oke.availability_domains)) == length(var.oke.availability_domains) &&
      alltrue([for name in var.oke.availability_domains : length(trimspace(name)) > 0])
    )
    error_message = "Provide one to three distinct nonempty approved availability-domain names."
  }
  validation {
    condition = (
      var.oke.node_count == floor(var.oke.node_count) && var.oke.node_count >= 3 && var.oke.node_count <= 9 &&
      var.oke.node_ocpus == floor(var.oke.node_ocpus) && var.oke.node_ocpus >= 1 && var.oke.node_ocpus <= 8 &&
      var.oke.node_memory_gib >= 8 && var.oke.node_memory_gib <= 64 && var.oke.node_memory_gib <= 64 * var.oke.node_ocpus &&
      var.oke.boot_volume_gib == floor(var.oke.boot_volume_gib) && var.oke.boot_volume_gib >= 50 && var.oke.boot_volume_gib <= 500 &&
      var.oke.max_pods_per_node == floor(var.oke.max_pods_per_node) && var.oke.max_pods_per_node >= 1 && var.oke.max_pods_per_node <= 31
    )
    error_message = "Keep the ARM pool within the documented integer node/CPU/disk/pod and RAM bounds."
  }
  validation {
    condition = try(
      can(cidrnetmask(var.oke.services_cidr)) && cidrhost(var.oke.services_cidr, 0) == split("/", var.oke.services_cidr)[0] &&
      tonumber(split("/", var.oke.services_cidr)[1]) >= 16 && tonumber(split("/", var.oke.services_cidr)[1]) <= 24 &&
      can(regex("^(10[.]|172[.](1[6-9]|2[0-9]|3[01])[.]|192[.]168[.])", var.oke.services_cidr)), false
    )
    error_message = "Provide a canonical private IPv4 /16 through /24 service range."
  }
}

# Private operator-owned cloud-init; no default or arbitrary node metadata override.
variable "worker_cloud_init" {
  description = "Operator-approved plain Bash cloud-init from OTM_WORKER_CLOUD_INIT secret; base64 size <=16384 bytes. Retain OKE bootstrap."
  type        = string
  sensitive   = true
  nullable    = false
  # This validates format/size only; private review and live sensor/bootstrap checks remain required.
  validation {
    condition     = startswith(var.worker_cloud_init, "#!/bin/bash\n") && !strcontains(var.worker_cloud_init, "\u0000") && length(base64encode(var.worker_cloud_init)) <= 16384
    error_message = "Provide approved plain Bash cloud-init with a /bin/bash shebang, no NULs and base64 size <=16384 bytes."
  }
}


# This is a pin bound to a qualified staging selection; the release pipeline must verify provenance.
variable "qualified_node_image" {
  description = "Optional staging image record; mandatory for production, never a manual Actions image-ID variable."
  type = object({
    image_ocid         = string
    kubernetes_version = string
    architecture       = string
    os_major           = string
  })
  default = null
  validation {
    condition     = var.qualified_node_image != null
    error_message = "Production requires the exact image selection qualified in staging."
  }
  validation {
    condition = var.qualified_node_image == null ? true : (
      can(regex("^ocid1[.]image[.][a-z0-9]+[.][a-z0-9-]+[.][a-z0-9]+$", var.qualified_node_image.image_ocid)) &&
      var.qualified_node_image.kubernetes_version == var.oke_kubernetes_version &&
      var.qualified_node_image.architecture == "AARCH64" && var.qualified_node_image.os_major == var.oke.node_os_major
    )
    error_message = "The staging image record must match the selected version, A1 architecture and OS major."
  }
}

# References only: provision an approved strong password into Vault separately, never through tfvars.
variable "database_administrator" {
  type = object({
    # Provisioning administrator, never the API/worker runtime login; SQL role naming subset.
    username = string
    # Existing Vault secret OCID; the provisioning requester needs scoped documented read grants.
    secret_ocid = string
    # Positive integer version string pins provisioning to the reviewed existing secret version.
    secret_version = string
  })
  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.database_administrator.username)) && !contains(["postgres", "oci_admin", "oci_superuser"], var.database_administrator.username)
    error_message = "Provide a nonreserved lowercase administrator role name of 1-63 characters."
  }
  validation {
    condition     = can(regex("^ocid1[.]vaultsecret[.][a-z0-9]+[.][a-z0-9-]+[.][a-z0-9]+$", var.database_administrator.secret_ocid)) && can(regex("^[1-9][0-9]*$", var.database_administrator.secret_version))
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

# Required OTM_HOSTING_COMPARTMENT_OCID from this environment; one existing compartment, no children.
# Syntax does not establish tenancy ownership or permission; independently verify both before apply.
variable "hosting_compartment_ocid" {
  type = string
  validation {
    condition     = length(var.hosting_compartment_ocid) <= 255 && can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][a-z0-9-]*[.][a-z0-9]+$", var.hosting_compartment_ocid))
    error_message = "Provide the selected environment's existing hosting compartment OCID, at most255 characters."
  }
}

# Required exact application Vault reference from this environment's security-root handoff.
variable "application_vault_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1[.]vault[.]oc[0-9]+[.][a-z0-9.-]{1,220}$", var.application_vault_ocid))
    error_message = "Provide this environment's application Vault OCID."
  }
}

# Optional approved relay destinations/port; the network module validates the complete bounded set.
variable "smtp_egress" {
  type = object({
    cidrs = set(string)
    port  = number
  })
  default     = null
  description = "Explicit outbound SMTP CIDRs and TLS port465/587; null creates no additional relay rule."
}

# Source enablement only; the Caddy workload still starts held at zero replicas.
variable "caddy_ingress_enabled" {
  type        = bool
  default     = false
  description = "Enable the approved HTTP-01/public80 and source-restricted443 network source."
}
