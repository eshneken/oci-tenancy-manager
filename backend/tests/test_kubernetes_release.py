"""Offline hosted bundles must isolate credentials and remain unconditionally disabled."""

import hashlib
import json
import stat
from copy import deepcopy
from pathlib import Path

import pytest

from otm.kubernetes_release import HELD_COMMAND, hosted_bundle, main, write_bundle

CONFIG = Path(__file__).resolve().parents[1] / "config"
IMAGE = "ghcr.io/example/atlas@sha256:" + "a" * 64
NETWORK = '\n[recovery_console]\nallowed_cidrs = ["198.51.100.0/24"]\n'


# Public synthetic hosted templates gain only a documentation-network restriction for test inputs.
def settings(environment="staging"):
    return (CONFIG / (environment + ".application.toml")).read_text() + NETWORK


# Select exactly one object by kind/name to reject missing or duplicated resource definitions.
def resource(bundle, kind, name):
    matches = [
        item
        for item in bundle["items"]
        if item["kind"] == kind and item["metadata"]["name"] == name
    ]
    assert len(matches) == 1
    return matches[0]


# Identify all pod templates, including a separately owned and suspended migration Job.
def pods(bundle):
    return [
        item["spec"]["template"]
        for item in bundle["items"]
        if item["kind"] in {"Deployment", "Job"}
    ]


# Previews cannot run local defaults, expose a public endpoint or start migrations.
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_bundle_is_disabled_and_isolated(environment):
    raw = settings(environment)
    bundle = hosted_bundle(raw, IMAGE, environment)
    assert bundle["apiVersion"] == "v1" and bundle["kind"] == "List"
    assert len(bundle["items"]) == 8
    assert all(item["metadata"]["namespace"] == "otm-" + environment for item in bundle["items"])
    assert not any(
        item["kind"] in {"Secret", "Ingress", "RoleBinding", "ClusterRoleBinding"}
        for item in bundle["items"]
    )
    for role in ("api", "worker"):
        deployment = resource(bundle, "Deployment", "otm-" + role)
        assert deployment["spec"]["replicas"] == 0
        assert (
            deployment["spec"]["selector"]["matchLabels"]
            == deployment["spec"]["template"]["metadata"]["labels"]
        )
    assert resource(bundle, "Deployment", "otm-api")["spec"]["strategy"]["rollingUpdate"] == {
        "maxSurge": 1,
        "maxUnavailable": 0,
    }
    assert resource(bundle, "Deployment", "otm-worker")["spec"]["strategy"] == {"type": "Recreate"}
    job = next(item for item in bundle["items"] if item["kind"] == "Job")
    assert job["spec"]["suspend"] is True and job["spec"]["backoffLimit"] == 0
    assert job["spec"]["parallelism"] == job["spec"]["completions"] == 1
    assert job["spec"]["activeDeadlineSeconds"] == 600
    service = resource(bundle, "Service", "otm-api")
    assert service["spec"]["type"] == "ClusterIP" and "externalIPs" not in service["spec"]
    assert not any(item["kind"] == "NetworkPolicy" for item in bundle["items"])
    for pod in pods(bundle):
        spec = pod["spec"]
        assert spec["automountServiceAccountToken"] is False
        assert spec["nodeSelector"] == {"kubernetes.io/os": "linux", "kubernetes.io/arch": "arm64"}
        assert spec["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "runAsGroup": 10001,
            "fsGroup": 10001,
            "fsGroupChangePolicy": "OnRootMismatch",
            "seccompProfile": {"type": "RuntimeDefault"},
        }
        (container,) = spec["containers"]
        assert container["image"] == IMAGE and container["command"] == HELD_COMMAND
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        }
        role = container["name"]
        assert spec["serviceAccountName"] == "otm-" + role
        env = {item["name"]: item for item in container["env"]}
        assert env["OTM_DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {
            "name": f"otm-{role}-database",
            "key": "url",
            "optional": False,
        }
        assert "value" not in env["OTM_DATABASE_URL"]
        assert spec["terminationGracePeriodSeconds"] == (300 if role == "worker" else 120)
        assert all(
            mount.get("readOnly") is True
            for mount in container["volumeMounts"]
            if mount["name"] != "temporary"
        )
        assert container["resources"]["requests"] and container["resources"]["limits"]
        account = resource(bundle, "ServiceAccount", "otm-" + role)
        assert account["automountServiceAccountToken"] is False
        if role == "api":
            assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
            assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
        else:
            assert "ports" not in container and "readinessProbe" not in container


# Settings revisions have independent immutable names and rollout checksums without changing image.
def test_configuration_revision_changes_bundle_identity():
    raw = settings()
    before = hosted_bundle(raw, IMAGE, "staging")
    after = hosted_bundle(raw + "\n# new reviewed revision\n", IMAGE, "staging")
    assert hosted_bundle(raw, IMAGE, "staging") == before
    first = next(item for item in before["items"] if item["kind"] == "ConfigMap")
    second = next(item for item in after["items"] if item["kind"] == "ConfigMap")
    assert first["immutable"] is True and first["data"] == {"application.toml": raw}
    assert first["metadata"]["name"] != second["metadata"]["name"]
    for old, new in zip(pods(before), pods(after), strict=True):
        assert (
            old["metadata"]["annotations"]["otm.io/settings-sha256"]
            == hashlib.sha256(raw.encode()).hexdigest()
        )
        assert old["metadata"]["annotations"] != new["metadata"]["annotations"]
        assert old["spec"]["containers"][0]["image"] == new["spec"]["containers"][0]["image"]
        mounted = next(v for v in new["spec"]["volumes"] if v["name"] == "settings")
        assert mounted["configMap"]["name"] == second["metadata"]["name"]


# Release identity changes with the tested digest; tags and mutable latest names are rejected.
def test_image_changes_release_identity():
    before = hosted_bundle(settings(), IMAGE, "staging")
    after = hosted_bundle(settings(), IMAGE.replace("a" * 64, "b" * 64), "staging")
    assert (
        pods(before)[0]["metadata"]["annotations"]["otm.io/release-sha256"]
        != pods(after)[0]["metadata"]["annotations"]["otm.io/release-sha256"]
    )


# Whole-candidate validation happens before file creation or any infrastructure authority exists.
@pytest.mark.parametrize(
    "image",
    [
        None,
        "latest",
        "atlas:1",
        IMAGE + "\n",
        IMAGE.upper(),
        "../atlas@sha256:" + "a" * 64,
        "x" * 256,
    ],
)
def test_invalid_image_rejected(image):
    with pytest.raises(ValueError, match="KUBERNETES_PINNED_IMAGE_REQUIRED"):
        hosted_bundle(settings(), image, "staging")


# An independently selected target cannot accept another environment or laptop-only settings.
@pytest.mark.parametrize("environment", ["local", "STAGING", None])
def test_unsupported_environment_rejected(environment):
    with pytest.raises(ValueError, match="KUBERNETES_ENVIRONMENT_INVALID"):
        hosted_bundle(settings(), IMAGE, environment)


# Hosted configuration gates retain their existing email, CIDR and local-server protections.
@pytest.mark.parametrize(
    "fault", ["target", "cidrs", "local", "malformed", "extra", "oversized", "type"]
)
def test_invalid_settings_rejected(fault):
    raw = settings()
    environment = "staging"
    if fault == "target":
        environment = "production"
    elif fault == "cidrs":
        raw = raw[: raw.index("[recovery_console]")]
    elif fault == "local":
        raw += '\n[local_server]\npublic_origin = "https://localhost:8443"\n'
    elif fault == "malformed":
        raw += "\n[broken"
    elif fault == "extra":
        raw += '\n[unrecognized]\npassword = "synthetic-not-a-credential"\n'
    elif fault == "oversized":
        raw = "#" * 524289
    else:
        raw = None
    with pytest.raises(ValueError):
        hosted_bundle(raw, IMAGE, environment)


# Output is private, deterministic and non-overwriting, with no operational data printed by CLI.
def test_private_cli_round_trip(tmp_path, capsys):
    source, output = tmp_path / "source.toml", tmp_path / "bundle.json"
    source.write_text(settings())
    args = [
        "--config",
        str(source),
        "--output",
        str(output),
        "--image",
        IMAGE,
        "--expected-environment",
        "staging",
    ]
    assert main(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "activation": "held",
        "bundle_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == hosted_bundle(settings(), IMAGE, "staging")
    original = output.read_bytes()
    assert main(args) == 1 and capsys.readouterr().out == "KUBERNETES_BUNDLE_REJECTED\n"
    assert output.read_bytes() == original


# Existing files/symlinks are preserved, and oversized/invalid candidates leave no output artifact.
def test_failed_write_preserves_files(tmp_path):
    source, target, alias = tmp_path / "input.toml", tmp_path / "target", tmp_path / "alias"
    source.write_text(settings())
    target.write_text("preserve")
    alias.symlink_to(target)
    with pytest.raises(FileExistsError):
        write_bundle(source, alias, IMAGE, "staging")
    assert target.read_text() == "preserve"
    source.write_text("#" * 524289)
    with pytest.raises(ValueError):
        write_bundle(source, tmp_path / "absent", IMAGE, "staging")
    assert not (tmp_path / "absent").exists()


# Staging exercises the exact production workload shape; only isolated identities/settings differ.
def test_staging_production_workload_parity():
    staging = hosted_bundle(settings("staging"), IMAGE, "staging")
    production = hosted_bundle(settings("production"), IMAGE, "production")
    for role in ("api", "worker"):
        before = resource(staging, "Deployment", "otm-" + role)
        after = resource(production, "Deployment", "otm-" + role)
        assert before["spec"]["strategy"] == after["spec"]["strategy"]
        assert (
            before["spec"]["template"]["metadata"]["annotations"]["otm.io/target-replicas"] == "2"
        )
        assert after["spec"]["template"]["metadata"]["annotations"]["otm.io/target-replicas"] == "2"
    for before, after in zip(pods(staging), pods(production), strict=True):
        left, right = deepcopy(before["spec"]), deepcopy(after["spec"])
        for spec in (left, right):
            next(volume for volume in spec["volumes"] if volume["name"] == "settings")["configMap"][
                "name"
            ] = "environment-specific-settings"
        assert left == right


# Explicit OCI mode mounts a rotating bound token/CA only in API/worker pods; migration needs none.
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_explicit_workload_identity_projection(environment):
    raw = 'provider_mode="oci"\n' + settings(environment)
    raw += (
        '\n[oci]\nauth_method="oke_workload_identity"\n'
        'region="us-ashburn-1"\ntenancy_ocid="ocid1.tenancy.oc1..synthetic"\n'
    )
    bundle = hosted_bundle(raw, IMAGE, environment)
    for pod in pods(bundle):
        spec = pod["spec"]
        container = spec["containers"][0]
        role = container["name"]
        volumes = {volume["name"]: volume for volume in spec["volumes"]}
        mounts = {mount["name"]: mount for mount in container["volumeMounts"]}
        env = {item["name"]: item for item in container["env"]}
        assert spec["automountServiceAccountToken"] is False
        assert container["command"] == HELD_COMMAND
        if role == "migration":
            assert "oci-workload-identity" not in volumes
            assert "OCI_RESOURCE_PRINCIPAL_REGION" not in env
            continue
        assert env["OCI_RESOURCE_PRINCIPAL_REGION"]["value"] == "us-ashburn-1"
        assert mounts["oci-workload-identity"] == {
            "name": "oci-workload-identity",
            "mountPath": "/var/run/secrets/kubernetes.io/serviceaccount",
            "readOnly": True,
        }
        assert volumes["oci-workload-identity"]["projected"] == {
            "defaultMode": 0o440,
            "sources": [
                {"serviceAccountToken": {"path": "token", "expirationSeconds": 3600}},
                {
                    "configMap": {
                        "name": "kube-root-ca.crt",
                        "items": [{"key": "ca.crt", "path": "ca.crt"}],
                    }
                },
            ],
        }
    assert not any(item["kind"] == "NetworkPolicy" for item in bundle["items"])


# Offline profiles never acquire a projected token merely because OCI support is installed.
def test_simulated_bundle_has_no_identity_projection():
    for pod in pods(hosted_bundle(settings(), IMAGE, "staging")):
        assert all(volume["name"] != "oci-workload-identity" for volume in pod["spec"]["volumes"])
