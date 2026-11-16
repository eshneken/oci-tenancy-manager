# Fixed caller identity is a labeling guard, not evidence of live IAM authorization.
variable "environment" {
  description = "Fixed staging or production environment selected by the calling root."
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Select staging or production."
  }
}

# Existing hosting compartment; independently verify ancestry and the actual principal.
variable "compartment_ocid" {
  description = "Dedicated hosting compartment OCID; no parent/child credentials are accepted."
  type        = string
  validation {
    condition     = can(regex("^ocid1[.]compartment[.][a-z0-9]+[.][.][a-z0-9]+$", var.compartment_ocid))
    error_message = "Provide the existing hosting compartment OCID."
  }
}

# Reserve nonoverlapping private space after checking corporate/peered network routes.
variable "vcn_cidr" {
  description = "Canonical RFC1918 IPv4 VCN CIDR, prefix /16 through /20; no default."
  type        = string
  validation {
    condition = try(
      can(cidrnetmask(var.vcn_cidr)) && cidrhost(var.vcn_cidr, 0) == split("/", var.vcn_cidr)[0] &&
      tonumber(split("/", var.vcn_cidr)[1]) >= 16 && tonumber(split("/", var.vcn_cidr)[1]) <= 20 &&
      can(regex("^(10[.]|172[.](1[6-9]|2[0-9]|3[01])[.]|192[.]168[.])", var.vcn_cidr)), false
    )
    error_message = "Provide a canonical RFC1918 IPv4 /16 through /20, with no host bits."
  }
}

# Render only from OTM_ALLOWED_SOURCE_CIDRS; first hosted topology deliberately has no IPv6.
variable "app_ingress_allowed_cidrs" {
  description = "Required 1-64 canonical IPv4 source networks, <=4096 serialized bytes, ORed for TCP443 only."
  type        = set(string)
  validation {
    condition     = length(var.app_ingress_allowed_cidrs) >= 1 && length(var.app_ingress_allowed_cidrs) <= 64 && length(jsonencode(var.app_ingress_allowed_cidrs)) <= 4096
    error_message = "Provide a nonempty bounded source allowlist."
  }
  validation {
    condition = alltrue([for cidr in var.app_ingress_allowed_cidrs : try(
      can(cidrnetmask(cidr)) && cidrhost(cidr, 0) == split("/", cidr)[0] && tonumber(split("/", cidr)[1]) > 0,
      false
    )])
    error_message = "Every app source must be a canonical IPv4 CIDR, including /32 for a single host; IPv6 and /0 are not enabled."
  }
  # Count only networks not contained in a larger member, detecting unrestricted unions
  # without overcounting overlaps. Keep this inline to avoid a validation/local dependency cycle.
  validation {
    condition = sum(concat([0], [
      for cidr in var.app_ingress_allowed_cidrs : try(pow(2, 32 - tonumber(split("/", cidr)[1])), 0)
      if !anytrue([for parent in var.app_ingress_allowed_cidrs : try(
        tonumber(split("/", parent)[1]) < tonumber(split("/", cidr)[1]) &&
        cidrhost(parent, 0) == cidrhost("${split("/", cidr)[0]}/${split("/", parent)[1]}", 0), false
      )])
    ])) < pow(2, 32)
    error_message = "The effective source union must not allow all IPv4 addresses."
  }
}

# Optional explicit relay; null adds no relay rule. Existing OCI/CNI grants remain additive.
variable "smtp_egress" {
  description = "Approved SMTP relay IPv4 destinations and exact TLS port465/587; null creates no extra rules."
  type = object({
    cidrs = set(string)
    port  = number
  })
  default = null
  validation {
    condition = var.smtp_egress == null ? true : (
      contains([465, 587], var.smtp_egress.port) &&
      length(var.smtp_egress.cidrs) >= 1 && length(var.smtp_egress.cidrs) <= 64 &&
      length(jsonencode(var.smtp_egress.cidrs)) <= 4096
    )
    error_message = "Provide 1-64 bounded relay IPv4 CIDRs and explicit TLS port465 or587, or null."
  }
  validation {
    condition = var.smtp_egress == null ? true : alltrue([for cidr in var.smtp_egress.cidrs : try(
      can(cidrnetmask(cidr)) && cidrhost(cidr, 0) == split("/", cidr)[0] && tonumber(split("/", cidr)[1]) > 0,
      false
    )])
    error_message = "Relay destinations must be canonical IPv4 CIDRs; no IPv6, DNS names, host bits or/0."
  }
  # Detect unrestricted unions without counting overlapping ranges twice, as for inbound sources.
  validation {
    condition = var.smtp_egress == null ? true : sum(concat([0], [
      for cidr in var.smtp_egress.cidrs : try(pow(2, 32 - tonumber(split("/", cidr)[1])), 0)
      if !anytrue([for parent in var.smtp_egress.cidrs : try(
        tonumber(split("/", parent)[1]) < tonumber(split("/", cidr)[1]) &&
        cidrhost(parent, 0) == cidrhost("${split("/", cidr)[0]}/${split("/", parent)[1]}", 0), false
      )])
    ])) < pow(2, 32)
    error_message = "The effective relay destination union must not cover all IPv4 addresses."
  }
}

# Explicit infrastructure choice; false creates no public HTTP listener rules or reserved address.
variable "caddy_ingress_enabled" {
  type        = bool
  default     = false
  description = "Enable the approved HTTP-01/public80 and source-restricted443 Caddy network handoff."
}
