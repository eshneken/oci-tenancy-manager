"""Render operator-owned worker cloud-init privately without executing or logging its contents."""

import argparse
import base64
import hashlib
import json
import os
import subprocess  # nosec B404
from pathlib import Path


# The reviewed fixed executable/flags parse stdin without execution; scrub startup environment,
# bound size/time and discard private errors. B404/B603 exceptions apply only to this boundary.
def validate_worker_script(value):
    if not isinstance(value, str) or not value.startswith("#!/bin/bash\n") or "\x00" in value:
        raise ValueError("INVALID_WORKER_BOOTSTRAP")
    content = value.encode("utf-8")
    if len(base64.b64encode(content)) > 16384:
        raise ValueError("INVALID_WORKER_BOOTSTRAP")
    result = subprocess.run(  # nosec B603
        ["/bin/bash", "--noprofile", "--norc", "-n"],
        input=content,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "BASH_ENV": "/dev/null", "ENV": "/dev/null"},
        timeout=5,
        check=False,
    )
    if result.returncode:
        raise ValueError("INVALID_WORKER_BOOTSTRAP")
    return content


# Validate before exclusive owner-only creation; secret-bearing tfvars never enter source/artifacts.
def render_worker_inputs(output: Path, value):
    content = validate_worker_script(value)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(json.dumps({"worker_cloud_init": value}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(content).hexdigest()


# Trusted protected-environment jobs supply the secret; only a fingerprint leaves the renderer.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, metavar="PRIVATE_TFVARS_JSON")
    options = parser.parse_args(argv)
    try:
        fingerprint = render_worker_inputs(options.output, os.environ.get("OTM_WORKER_CLOUD_INIT"))
    except Exception:
        print("WORKER_BOOTSTRAP_REJECTED")
        return 1
    print(json.dumps({"worker_bootstrap_sha256": fingerprint}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
