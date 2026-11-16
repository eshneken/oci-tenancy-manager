"""Extract a staging image selection into a private production Terraform input; no OCI calls."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


# Reject duplicate fields instead of accepting a last-value interpretation of handoff evidence.
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("INVALID_IMAGE_HANDOFF")
        result[key] = value
    return result


# Consume only a bounded cluster output and preserve the exact compatible selection in a new file.
# This validates input binding, not staging acceptance or trusted workflow provenance.
def render_image_handoff(source: Path, output: Path, version: str, os_major: str, region: str):
    with source.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("INVALID_IMAGE_HANDOFF")
    cluster = json.loads(raw, object_pairs_hook=unique_object)
    if (
        not isinstance(cluster, dict)
        or cluster.get("environment") != "staging"
        or not isinstance(version, str)
        or len(version) > 32
        or re.fullmatch(r"v[1-9][0-9]*\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version) is None
        or os_major not in ("8", "9")
        or region != "us-ashburn-1"
        or cluster.get("kubernetes_version") != version
    ):
        raise ValueError("INVALID_IMAGE_HANDOFF")
    selection = cluster.get("image_selection")
    if (
        not isinstance(selection, dict)
        or set(selection) != {"image_ocid", "kubernetes_version", "architecture", "os_major"}
        or selection.get("kubernetes_version") != version
        or selection.get("architecture") != "AARCH64"
        or selection.get("os_major") != os_major
        or not isinstance(selection.get("image_ocid"), str)
        or len(selection["image_ocid"]) > 255
        or re.fullmatch(r"ocid1\.image\.oc1\.iad\.[a-z0-9]+", selection["image_ocid"]) is None
    ):
        raise ValueError("INVALID_IMAGE_HANDOFF")
    content = json.dumps({"qualified_node_image": selection}, sort_keys=True).encode() + b"\n"
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(content).hexdigest()


# Read version from the selected environment; print only a digest or a non-disclosing fixed error.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-cluster-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    # Explicit OS family and region must match the reviewed target; no cross-region substitution.
    parser.add_argument("--os-major", choices=("8", "9"), required=True)
    parser.add_argument("--region", choices=("us-ashburn-1",), required=True)
    options = parser.parse_args(argv)
    try:
        digest = render_image_handoff(
            options.staging_cluster_output,
            options.output,
            os.environ.get("OTM_OKE_KUBERNETES_VERSION"),
            options.os_major,
            options.region,
        )
    except Exception:
        print("IMAGE_HANDOFF_REJECTED")
        return 1
    print(json.dumps({"image_handoff_sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
