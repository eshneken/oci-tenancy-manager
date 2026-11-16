# Fixed labels are an input guard; IAM independently constrains the real hosting identity.
variable "environment" {
  description = "Fixed staging or production environment selected by the platform root."
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Select staging or production."
  }
}

# Region-local discovery must use the intended hosting tenancy, not a managed child.
variable "tenancy_ocid" {
  description = "Hosting tenancy OCID for availability-domain discovery; syntax is not authorization."
  type        = string
  validation {
    condition     = can(regex("^ocid1[.]tenancy[.][a-z0-9]+[.][.][a-z0-9]+$", var.tenancy_ocid))
    error_message = "Provide the hosting tenancy OCID."
  }
}

# All cluster/node resources stay in the reviewed existing hosting compartment.
variable "compartment_ocid" {
  description = "Existing hosting compartment OCID; independently verify tenancy ancestry."
  type        = string
  validation {
    condition     = can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][.][a-z0-9]+$", var.compartment_ocid))
    error_message = "Provide the hosting compartment OCID."
  }
}

# Only the network module supplies these exact VNIC/subnet bindings; operational IDs are private.
variable "network" {
  description = "Environment-bound network output; includes VCN CIDR for service/pod capacity guards."
  type = object({
    environment = string
    vcn_id      = string
    vcn_cidr    = string
    subnets     = map(object({ id = string, cidr = string }))
    nsg_ids     = map(string)
  })
  validation {
    condition     = var.network.environment == var.environment
    error_message = "Network bindings must belong to this environment."
  }
  validation {
    condition = alltrue([for key in ["api", "nodes", "pods", "edge"] : contains(keys(var.network.subnets), key)]) && alltrue([
      for key in ["api", "nodes", "pods", "deployment"] : contains(keys(var.network.nsg_ids), key)
    ])
    error_message = "Provide the required API/node/pod/edge subnets and API/node/pod/deployment NSGs."
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

# Pins are supplied by the environment's reviewed qualification, never selected as floating latest.
variable "oke" {
  description = "Pinned OKE release/OS/placements and cost-bounded initial ARM pool configuration."
  type = object({
    # Exact vMAJOR.MINOR.PATCH, explicitly qualified as GA in the target region before deployment.
    kubernetes_version = string
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
    condition     = length(var.oke.kubernetes_version) <= 32 && can(regex("^v[1-9][0-9]*[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)$", var.oke.kubernetes_version)) && contains(["8", "9"], var.oke.node_os_major)
    error_message = "Pin an exact Kubernetes patch and supported Oracle Linux major (8 or 9)."
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
    condition     = var.environment != "production" || var.qualified_node_image != null
    error_message = "Production requires the exact image selection qualified in staging."
  }
  validation {
    condition = var.qualified_node_image == null ? true : (
      can(regex("^ocid1[.]image[.][a-z0-9]+[.][a-z0-9-]+[.][a-z0-9]+$", var.qualified_node_image.image_ocid)) &&
      var.qualified_node_image.kubernetes_version == var.oke.kubernetes_version &&
      var.qualified_node_image.architecture == "AARCH64" && var.qualified_node_image.os_major == var.oke.node_os_major
    )
    error_message = "The staging image record must match the selected version, A1 architecture and OS major."
  }
}
