"""Validate nonsecret protected-environment version inputs into private Terraform candidates."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


# Validate strict syntax; live region support, image compatibility and upgrades are separate.
def render_platform_versions(output: Path, kubernetes_version, postgresql_version):
    if (
        not isinstance(kubernetes_version, str)
        or len(kubernetes_version) > 32
        or re.fullmatch(r"v[1-9][0-9]*\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", kubernetes_version)
        is None
        or not isinstance(postgresql_version, str)
        or re.fullmatch(r"[1-9][0-9]", postgresql_version) is None
    ):
        raise ValueError("INVALID_PLATFORM_VERSIONS")
    content = json.dumps(
        {"oke_kubernetes_version": kubernetes_version, "postgresql_version": postgresql_version},
        sort_keys=True,
    ).encode()
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(content).hexdigest()


# Require both variables from the selected environment; no local or 'latest' fallback.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, metavar="PRIVATE_TFVARS_JSON")
    options = parser.parse_args(argv)
    try:
        fingerprint = render_platform_versions(
            options.output,
            os.environ.get("OTM_OKE_KUBERNETES_VERSION"),
            os.environ.get("OTM_POSTGRESQL_VERSION"),
        )
    except Exception:
        print("PLATFORM_VERSIONS_REJECTED")
        return 1
    print(json.dumps({"platform_versions_sha256": fingerprint}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
