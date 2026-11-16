"""Render the selected environment's existing hosting compartment as a private Terraform input."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


# Validate a reference only; OCI tenancy ownership and effective IAM require independent checks.
def render_hosting_input(output: Path, value):
    if (
        not isinstance(value, str)
        or len(value) > 255
        or re.fullmatch(r"ocid1\.compartment\.[a-z0-9]+\.[a-z0-9-]*\.[a-z0-9]+", value) is None
    ):
        raise ValueError("INVALID_HOSTING_COMPARTMENT")
    content = json.dumps({"hosting_compartment_ocid": value}, sort_keys=True).encode() + b"\n"
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(content).hexdigest()


# Protected-environment input is data, never evaluated shell text; no default target is allowed.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        digest = render_hosting_input(
            options.output, os.environ.get("OTM_HOSTING_COMPARTMENT_OCID")
        )
    except Exception:
        print("HOSTING_INPUT_REJECTED")
        return 1
    print(json.dumps({"hosting_input_sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
