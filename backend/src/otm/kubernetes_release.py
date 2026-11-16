"""Offline, disabled hosted workload bundle; it performs no Kubernetes or OCI operations."""

import argparse
import hashlib
import json
import os
import re
import tomllib
from pathlib import Path

from otm.caddy_ingress import caddy_resources
from otm.release_validation import validate_release_settings
from otm.settings import ApplicationSettings

# Full Vault/OCI launch composition is not yet qualified. Keep accidentally scaled preview
# workloads fail-closed instead of inheriting the image's laptop-only default command.
# Both hosted environments have the same intended topology; preview replicas remain zero.
TARGET_REPLICAS = {"api": 2, "worker": 2}
HELD_COMMAND = ["python", "-c", "raise SystemExit('OTM_HOSTED_RUNTIME_NOT_QUALIFIED')"]


# Namespaced objects use fixed role names; environment identity comes from trusted release input.
def metadata(name, namespace, component):
    return {
        "name": name,
        "namespace": namespace,
        "labels": {
            "app.kubernetes.io/name": "otm",
            "app.kubernetes.io/component": component,
            "app.kubernetes.io/managed-by": "otm-release",
        },
    }


# Processes share one image; only explicitly selected OCI readers receive a projected token.
def pod_spec(image, settings_name, role, workload_region=None):
    resources = {
        "api": ({"cpu": "250m", "memory": "512Mi"}, {"cpu": "1500m", "memory": "1Gi"}),
        "worker": ({"cpu": "500m", "memory": "512Mi"}, {"cpu": "2", "memory": "1Gi"}),
        "migration": ({"cpu": "250m", "memory": "256Mi"}, {"cpu": "1", "memory": "512Mi"}),
    }
    request, limit = resources[role]
    container = {
        "name": role,
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "command": list(HELD_COMMAND),
        "env": [
            {"name": "OTM_APPLICATION_CONFIG", "value": "/etc/otm/application.toml"},
            {"name": "TMPDIR", "value": "/run/otm"},
            {"name": "OTM_DATABASE_CA_FILE", "value": "/etc/otm-ca/ca.crt"},
            {
                "name": "OTM_DATABASE_URL",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": f"otm-{role}-database",
                        "key": "url",
                        "optional": False,
                    }
                },
            },
        ],
        "resources": {"requests": request, "limits": limit},
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        },
        "volumeMounts": [
            {"name": "settings", "mountPath": "/etc/otm", "readOnly": True},
            {"name": "database-ca", "mountPath": "/etc/otm-ca", "readOnly": True},
            {"name": "temporary", "mountPath": "/run/otm"},
        ],
    }
    if role == "api":
        container["ports"] = [{"name": "http", "containerPort": 8080}]
        # Liveness is process-only. Hosted readiness mechanics exist but require live qualification
        # before activation; never substitute the liveness endpoint for database readiness.
        container["startupProbe"] = {
            "httpGet": {"path": "/health/live", "port": "http"},
            "periodSeconds": 5,
            "failureThreshold": 30,
        }
        container["livenessProbe"] = {
            "httpGet": {"path": "/health/live", "port": "http"},
            "periodSeconds": 15,
            "timeoutSeconds": 2,
            "failureThreshold": 3,
        }
        container["readinessProbe"] = {
            "httpGet": {"path": "/health/ready", "port": "http"},
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 3,
        }
    spec = {
        "serviceAccountName": "otm-" + role,
        "automountServiceAccountToken": False,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "runAsGroup": 10001,
            "fsGroup": 10001,
            "fsGroupChangePolicy": "OnRootMismatch",
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "nodeSelector": {"kubernetes.io/os": "linux", "kubernetes.io/arch": "arm64"},
        "terminationGracePeriodSeconds": 300 if role == "worker" else 120,
        "containers": [container],
        "volumes": [
            {"name": "settings", "configMap": {"name": settings_name, "defaultMode": 0o444}},
            {"name": "database-ca", "configMap": {"name": "otm-database-ca", "defaultMode": 0o444}},
            {"name": "temporary", "emptyDir": {"sizeLimit": "64Mi"}},
        ],
    }

    if workload_region is not None and role in {"api", "worker"}:
        container["env"].append({"name": "OCI_RESOURCE_PRINCIPAL_REGION", "value": workload_region})
        container["volumeMounts"].append(
            {
                "name": "oci-workload-identity",
                "mountPath": "/var/run/secrets/kubernetes.io/serviceaccount",
                "readOnly": True,
            }
        )
        # Kubelet rotates the bound token; mount the directory, never a subPath copy.
        # Select the API server's default audience; OKE acceptance still needs live qualification.
        spec["volumes"].append(
            {
                "name": "oci-workload-identity",
                "projected": {
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
                },
            }
        )
    return spec


# Require immutable qualified runtime images, never a mutable tag or arbitrary command.
def pinned_image(image):
    if (
        not isinstance(image, str)
        or len(image) > 255
        or re.fullmatch(
            r"[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]{1,5})?"
            r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}",
            image,
        )
        is None
    ):
        raise ValueError("KUBERNETES_PINNED_IMAGE_REQUIRED")
    return image


# Validate the environment independently of TOML and render only immutable, explicitly held source.
def hosted_bundle(raw_settings, image, environment, *, caddy_image=None, ingress_network=None):
    if not isinstance(raw_settings, str) or len(raw_settings.encode()) > 524288:
        raise ValueError("KUBERNETES_SETTINGS_INVALID")
    if environment not in {"staging", "production"}:
        raise ValueError("KUBERNETES_ENVIRONMENT_INVALID")
    pinned_image(image)
    settings = ApplicationSettings.model_validate(tomllib.loads(raw_settings))
    validate_release_settings(settings, environment, "application")
    checksum = hashlib.sha256(raw_settings.encode()).hexdigest()
    namespace = "otm-" + environment
    settings_name = "otm-settings-" + checksum[:16]
    release_hash = hashlib.sha256(
        (environment + "\n" + image + "\n" + checksum).encode()
    ).hexdigest()
    annotations = {
        "otm.io/settings-sha256": checksum,
        "otm.io/release-sha256": release_hash,
        "otm.io/activation": "held-hosted-runtime-not-qualified",
    }
    objects = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": metadata(settings_name, namespace, "settings"),
            "immutable": True,
            "data": {"application.toml": raw_settings},
        }
    ]
    for role in ("api", "worker", "migration"):
        objects.append(
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": metadata("otm-" + role, namespace, role),
                "automountServiceAccountToken": False,
            }
        )
        labels = {"app.kubernetes.io/name": "otm", "app.kubernetes.io/component": role}
        template = {
            "metadata": {"labels": labels, "annotations": dict(annotations)},
            "spec": pod_spec(
                image,
                settings_name,
                role,
                settings.oci.region if settings.provider_mode == "oci" else None,
            ),
        }
        if role == "migration":
            template["spec"]["restartPolicy"] = "Never"
            objects.append(
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "metadata": metadata("otm-migrate-" + release_hash[:16], namespace, role),
                    "spec": {
                        "suspend": True,
                        "parallelism": 1,
                        "completions": 1,
                        "backoffLimit": 0,
                        "activeDeadlineSeconds": 600,
                        "template": template,
                    },
                }
            )
        else:
            template["metadata"]["annotations"]["otm.io/target-replicas"] = str(
                TARGET_REPLICAS[role]
            )
            strategy = (
                {"type": "Recreate"}
                if role == "worker"
                else {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0},
                }
            )
            objects.append(
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": metadata("otm-" + role, namespace, role),
                    "spec": {
                        "replicas": 0,
                        "revisionHistoryLimit": 3,
                        "progressDeadlineSeconds": 600,
                        "selector": {"matchLabels": labels},
                        "strategy": strategy,
                        "template": template,
                    },
                }
            )
    objects.append(
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": metadata("otm-api", namespace, "api"),
            "spec": {
                "type": "ClusterIP",
                "selector": {"app.kubernetes.io/name": "otm", "app.kubernetes.io/component": "api"},
                "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
            },
        }
    )
    if settings.hosted is not None and settings.hosted.ingress is not None:
        objects.extend(
            caddy_resources(settings, pinned_image(caddy_image), namespace, ingress_network)
        )
    elif caddy_image is not None or ingress_network is not None:
        raise ValueError("INGRESS_SETTINGS_REQUIRED")
    return {"apiVersion": "v1", "kind": "List", "items": objects}


# Create only a new private output file; do not follow symlinks or echo environment configuration.
def write_bundle(config, output, image, environment, *, caddy_image=None, ingress_network=None):
    with config.open("rb") as stream:
        raw = stream.read(524289)
    if len(raw) > 524288:
        raise ValueError("KUBERNETES_SETTINGS_INVALID")
    bundle = hosted_bundle(
        raw.decode(), image, environment, caddy_image=caddy_image, ingress_network=ingress_network
    )
    content = (json.dumps(bundle, sort_keys=True, indent=2) + "\n").encode()
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(content).hexdigest()


# Render review artifacts only; do not access kubectl, cloud services or secret stores.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-environment", choices=["staging", "production"], required=True)
    parser.add_argument("--caddy-image")
    parser.add_argument("--ingress-network", type=Path)
    options = parser.parse_args(argv)
    try:
        network = None
        if options.ingress_network is not None:
            with options.ingress_network.open("rb") as stream:
                content = stream.read(16385)
            if len(content) > 16384:
                raise ValueError("INGRESS_NETWORK_TOO_LARGE")
            network = json.loads(content)
        digest = write_bundle(
            options.config,
            options.output,
            options.image,
            options.expected_environment,
            caddy_image=options.caddy_image,
            ingress_network=network,
        )
    except Exception:
        print("KUBERNETES_BUNDLE_REJECTED")
        return 1
    print(json.dumps({"bundle_sha256": digest, "activation": "held"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
