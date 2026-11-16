"""Offline private Terraform allowlist rendering; never initialize a backend or call OCI."""

import argparse
import ipaddress
import json
import os
from pathlib import Path

from otm.recovery_console import parse_release_cidrs


# Reuse the console's strict union parser, then reject unsupported IPv6 before creating any file.
def render_network_inputs(output: Path, value: str):
    policy = parse_release_cidrs(value)
    if any(ipaddress.ip_network(cidr).version != 4 for cidr in policy.allowed_cidrs):
        raise ValueError("APP_INGRESS_IPV4_REQUIRED")
    content = json.dumps({"app_ingress_allowed_cidrs": policy.allowed_cidrs}, sort_keys=True)
    # Exclusive owner-only creation preserves valid candidates and refuses symlink destinations.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return policy


# The release job passes the environment value as data; receipts expose only count and digest.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, metavar="PRIVATE_TFVARS_JSON")
    options = parser.parse_args(argv)
    try:
        policy = render_network_inputs(options.output, os.environ.get("OTM_ALLOWED_SOURCE_CIDRS"))
    except Exception:
        print("NETWORK_INPUTS_REJECTED")
        return 1
    print(
        json.dumps(
            {
                "allowed_source_count": len(policy.allowed_cidrs),
                "source_fingerprint": policy.fingerprint,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
