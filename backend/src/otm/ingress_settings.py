"""Nonsecret HTTP-01 ingress references; no DNS changes, certificates or cloud calls."""

import ipaddress
import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from otm.contracts import Contract, canonical_https_origin
from otm.email_policy import mailbox
from otm.recovery_console import canonical_cidrs


# Keep certificate authority validation explicit; only the selected HTTP-01 flow is supported.
class CaddyIngressSettings(Contract):
    # ACME operator contact mailbox,1–254 characters; no placeholder/env/config substitution syntax.
    acme_email: Annotated[str, Field(min_length=1, max_length=254, repr=False)]

    # Caddyfile uses a quoted mailbox; reject its placeholder syntax even inside quoted strings.
    @field_validator("acme_email")
    @classmethod
    def safe_email(cls, value):
        mailbox(value)
        if any(character in value for character in "{}$"):
            raise ValueError("INGRESS_ACME_CONTACT_INVALID")
        return value


# Private Terraform handoff binds the public Service to reviewed firewall and address resources.
class CaddyNetworkBinding(Contract):
    # Exact hosted environment; compared independently with the requested bundle target.
    environment: Annotated[str, Field(pattern=r"^(staging|production)$")]
    # Exact existing hosting compartment from the same network handoff.
    compartment_ocid: Annotated[
        str, Field(pattern=r"^ocid1\.compartment\.oc[0-9]+\.[a-z0-9.-]{1,220}$")
    ]
    # Shared human HTTPS list:1–64 canonical IPv4 networks, never unrestricted.
    https_allowed_cidrs: tuple[str, ...]
    # Exact reserved public IPv4 address from the environment network handoff, not a DNS record.
    reserved_ipv4: Annotated[str, Field(min_length=7, max_length=15)]
    # Exact public edge subnet; bounded OCID syntax prevents arbitrary annotation/config injection.
    edge_subnet_ocid: Annotated[str, Field(pattern=r"^ocid1\.subnet\.oc[0-9]+\.[a-z0-9.-]{1,220}$")]
    # Exact Terraform-managed edge NSG; public Service rendering requires this firewall binding.
    edge_nsg_ocid: Annotated[
        str, Field(pattern=r"^ocid1\.networksecuritygroup\.oc[0-9]+\.[a-z0-9.-]{1,220}$")
    ]

    # Exact set must agree with the app's source policy before a public Service can render.
    @field_validator("https_allowed_cidrs", mode="before")
    @classmethod
    def source_networks(cls, values):
        result = canonical_cidrs(values)
        if any(":" in value for value in result):
            raise ValueError("INGRESS_IPV4_ALLOWLIST_REQUIRED")
        return result

    # Permit documentation ranges for offline fixtures, but never private/local/multicast targets.
    @field_validator("reserved_ipv4")
    @classmethod
    def public_ipv4(cls, value):
        address = ipaddress.IPv4Address(value)
        if str(address) != value or any(
            address in ipaddress.IPv4Network(network)
            for network in (
                "0.0.0.0/8",
                "10.0.0.0/8",
                "127.0.0.0/8",
                "169.254.0.0/16",
                "172.16.0.0/12",
                "192.168.0.0/16",
                "224.0.0.0/3",
            )
        ):
            raise ValueError("INGRESS_PUBLIC_IPV4_REQUIRED")
        return value


# One explicit canonical DNS hostname, never an IP, wildcard, URL port or runtime placeholder.
def ingress_hostname(origin):
    parsed = urlsplit(canonical_https_origin(origin))
    host = parsed.hostname
    if parsed.port is not None or host is None or len(host) > 253 or host.endswith("."):
        raise ValueError("INGRESS_DNS_HOST_REQUIRED")
    if "." not in host or any(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None
        for label in host.split(".")
    ):
        raise ValueError("INGRESS_DNS_HOST_REQUIRED")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValueError("INGRESS_DNS_HOST_REQUIRED")
