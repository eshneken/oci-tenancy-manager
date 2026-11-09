"""Private desired console-network policy without deployment or implicit allow-all behavior."""

import hashlib
import ipaddress
import json
from typing import Annotated

from pydantic import Field, field_validator

from otm.contracts import Contract


# Reject the entire candidate with a fixed diagnostic rather than exposing operational ranges.
def canonical_cidrs(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 64:
        raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS")
    if len(json.dumps(values, ensure_ascii=False).encode("utf-8")) > 4096:
        raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS")
    if any("/" not in value or "%" in value for value in values):
        raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS")
    try:
        networks = {ipaddress.ip_network(value.strip(), strict=True) for value in values}
    except ValueError:
        raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS") from None
    for version in (4, 6):
        collapsed = ipaddress.collapse_addresses(n for n in networks if n.version == version)
        if any(network.prefixlen == 0 for network in collapsed):
            raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS")
    return tuple(
        str(n)
        for n in sorted(networks, key=lambda n: (n.version, int(n.network_address), n.prefixlen))
    )


# Configuration is a desired restriction, never proof that any child has applied it.
class RecoveryConsoleSettings(Contract):
    # ORed canonical IPv4/IPv6 networks, 1–64 entries/4096 serialized bytes; never unrestricted.
    allowed_cidrs: Annotated[tuple[str, ...], Field(min_length=1, max_length=64, repr=False)]

    # TOML/JSON arrays and internal tuples share strict whole-candidate validation.
    @field_validator("allowed_cidrs", mode="before")
    @classmethod
    def validate_networks(cls, value):
        return canonical_cidrs(value)

    # Digest effective unions, so redundant ranges/order cannot fabricate a policy change.
    @property
    def fingerprint(self):
        networks = [ipaddress.ip_network(value) for value in self.allowed_cidrs]
        effective = [
            str(network)
            for version in (4, 6)
            for network in ipaddress.collapse_addresses(n for n in networks if n.version == version)
        ]
        return hashlib.sha256(
            json.dumps({"version": 1, "cidrs": effective}, separators=(",", ":")).encode()
        ).hexdigest()


# GitHub release input is data only; the strict settings loader never consults process env.
def parse_release_cidrs(value):
    if not isinstance(value, str) or len(value.encode("utf-8")) > 4096:
        raise ValueError("INVALID_RECOVERY_CONSOLE_CIDRS")
    return RecoveryConsoleSettings(allowed_cidrs=value.split(","))
