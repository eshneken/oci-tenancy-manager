"""Schema-check synthetic held bundles and prove strict validation rejects an invalid resource."""

import json
import os
import re
import shutil

# Fixed Docker argv only; no shell or operator settings enter these checks.
import subprocess  # nosec B404
import tempfile
from pathlib import Path
from uuid import uuid4

from docker_test_resources import remove_owned

from otm.kubernetes_release import hosted_bundle

ROOT = Path(__file__).resolve().parents[1]


# Dependabot can update the sole digest-pinned validator image without changing command semantics.
def validator_image(path):
    lines = [
        line
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    ]
    if (
        len(lines) != 1
        or re.fullmatch(
            r"FROM ghcr\.io/yannh/kubeconform:v[0-9]+\.[0-9]+\.[0-9]+@sha256:[0-9a-f]{64}",
            lines[0],
        )
        is None
    ):
        raise ValueError("KUBERNETES_VALIDATOR_PIN_INVALID")
    return lines[0].removeprefix("FROM ")


# Only repository synthetic templates enter the validator; operator settings never become CI logs.
def candidates(directory):
    paths = []
    image = "ghcr.io/example/atlas@sha256:" + "a" * 64
    for environment in ("staging", "production"):
        raw = (
            ROOT / "backend/config" / (environment + ".application.toml")
        ).read_text()
        raw += '\n[recovery_console]\nallowed_cidrs=["198.51.100.0/24"]\n'
        for mode in ("simulated", "oci", "ingress"):
            candidate = raw
            if mode in {"oci", "ingress"}:
                candidate = 'provider_mode="oci"\n' + raw
                candidate += (
                    '\n[oci]\nauth_method="oke_workload_identity"\n'
                    'region="us-ashburn-1"\ntenancy_ocid="ocid1.tenancy.oc1..synthetic"\n'
                )
            options = {}
            if mode == "ingress":
                candidate += '\n[hosted.ingress]\nacme_email="operator@example.test"\n'
                options = {
                    "caddy_image": "ghcr.io/example/caddy@sha256:" + "b" * 64,
                    "ingress_network": {
                        "environment": environment,
                        "compartment_ocid": "ocid1.compartment.oc1..synthetic",
                        "https_allowed_cidrs": ["198.51.100.0/24"],
                        "reserved_ipv4": "203.0.113.80",
                        "edge_subnet_ocid": "ocid1.subnet.oc1.iad.synthetic",
                        "edge_nsg_ocid": "ocid1.networksecuritygroup.oc1.iad.synthetic",
                    },
                }
            bundle = hosted_bundle(candidate, image, environment, **options)
            suffix = "" if mode == "simulated" else "-" + mode
            path = directory / (environment + suffix + ".json")
            path.write_text(json.dumps(bundle))
            path.chmod(0o600)
            paths.append(path.name)
    invalid = next(item for item in bundle["items"] if item["kind"] == "Deployment")
    invalid["spec"]["intentionallyInvalidForNegativeControl"] = True
    path = directory / "invalid.json"
    path.write_text(json.dumps(invalid))
    path.chmod(0o600)
    return paths


# Containers are uniquely owned, unprivileged and removed after success, failure or client timeout.
def validate(directory, paths, image, *, expected_valid, expected_invalid):
    client = shutil.which("docker")
    if client is None:
        raise ValueError("KUBERNETES_VALIDATOR_DOCKER_REQUIRED")
    owner = uuid4().hex
    name = "otm-kubeconform-" + owner
    label = "otm.kubernetes.validation"
    try:
        # Reviewed image pin and owned synthetic paths only; no shell evaluation.
        result = subprocess.run(  # nosec B603
            [
                client,
                "run",
                "--rm",
                "--name",
                name,
                "--label",
                label + "=" + owner,
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/run/otm:rw,noexec,nosuid,size=32m,mode=1777",
                "--env",
                "TMPDIR=/run/otm",
                "--mount",
                "type=bind,src=" + str(directory) + ",dst=/fixtures,readonly",
                image,
                "-strict",
                "-summary",
                "-output",
                "json",
                "-kubernetes-version",
                "1.37.1",
                *["/fixtures/" + name for name in paths],
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        summary = json.loads(result.stdout)["summary"]
        expected = {
            "valid": expected_valid,
            "invalid": expected_invalid,
            "errors": 0,
            "skipped": 0,
        }
        if summary != expected or result.returncode != (1 if expected_invalid else 0):
            raise ValueError("KUBERNETES_SCHEMA_VALIDATION_FAILED")
    finally:
        remove_owned(client, name, label, owner)


# No OCI/kubeconfig access or apply command exists; schema-service failures fail this check closed.
def main():
    try:
        image = validator_image(ROOT / "tools/kubeconform/Dockerfile")
        with tempfile.TemporaryDirectory(prefix="otm-kubernetes-") as temporary:
            directory = Path(temporary)
            paths = candidates(directory)
            validate(directory, paths, image, expected_valid=60, expected_invalid=0)
            validate(
                directory, ["invalid.json"], image, expected_valid=0, expected_invalid=1
            )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ):
        print("KUBERNETES_SCHEMA_CHECK_FAILED")
        return 1
    print(
        "Kubernetes schemas: 60 valid resources; strict invalid-field negative control passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
