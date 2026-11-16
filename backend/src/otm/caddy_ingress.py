"""Held Caddy ingress manifests and strict HTTP-01 proxy configuration; no issuance or apply."""

import hashlib
import json

from otm.ingress_settings import CaddyNetworkBinding, ingress_hostname

HTTP_NODE_PORT = 31080
HTTPS_NODE_PORT = 31443
HEALTH_NODE_PORT = 32081


# Public HTTP denies by default; Caddy handles only active HTTP-01 tokens.
def caddyfile(settings):
    host = ingress_hostname(settings.hosted.public_origin)
    email = json.dumps(settings.hosted.ingress.acme_email)
    return f"""{{
    admin off
    persist_config off
    auto_https disable_redirects
    http_port 8080
    https_port 8443
    email {email}
    cert_issuer acme {{
        dir https://acme-v02.api.letsencrypt.org/directory
        disable_tlsalpn_challenge
    }}
    servers {{
        protocols h1 h2
    }}
}}
http://:8080 {{
    respond 404
}}
https://{host}:8443 {{
    reverse_proxy http://otm-api:8080 {{
        header_up -Forwarded
        header_up -X-Real-IP
        header_up X-Forwarded-For {{http.request.remote.host}}
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host {{http.request.host}}
    }}
}}
https://:8443 {{
    respond 404
}}
http://:9090 {{
    handle /health/live {{
        respond 200
    }}
    handle /health/ready {{
        reverse_proxy http://otm-api:8080
    }}
    handle {{
        respond 404
    }}
}}
"""


# All references are exact nonsecret settings; only the image caller supplies an immutable digest.
def caddy_resources(settings, image, namespace, network):
    network = CaddyNetworkBinding.model_validate(network)
    if (
        network.environment != settings.environment
        or namespace != "otm-" + settings.environment
        or settings.recovery_console is None
        or set(network.https_allowed_cidrs) != set(settings.recovery_console.allowed_cidrs)
    ):
        raise ValueError("INGRESS_NETWORK_HANDOFF_MISMATCH")
    config = caddyfile(settings)
    digest = hashlib.sha256(config.encode()).hexdigest()
    config_name = "otm-caddy-" + digest[:16]
    labels = {"app.kubernetes.io/name": "otm", "app.kubernetes.io/component": "ingress"}

    # Namespaced release objects retain the same immutable ownership labels as other app roles.
    def metadata(name):
        return {"name": name, "namespace": namespace, "labels": labels}

    resources = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": metadata(config_name),
            "immutable": True,
            "data": {"Caddyfile": config},
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": metadata("otm-ingress"),
            "automountServiceAccountToken": False,
        },
        {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "StorageClass",
            "metadata": {"name": "otm-" + settings.environment + "-caddy-state", "labels": labels},
            "provisioner": "blockvolume.csi.oraclecloud.com",
            "reclaimPolicy": "Retain",
            "volumeBindingMode": "WaitForFirstConsumer",
            "allowVolumeExpansion": True,
            "parameters": {"attachment-type": "paravirtualized"},
        },
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": metadata("otm-caddy-state"),
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": "otm-" + settings.environment + "-caddy-state",
                "resources": {"requests": {"storage": "50Gi"}},
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": metadata("otm-ingress"),
            "spec": {
                "replicas": 0,
                "strategy": {"type": "Recreate"},
                "revisionHistoryLimit": 3,
                "selector": {"matchLabels": labels},
                "template": {
                    "metadata": {
                        "labels": labels,
                        "annotations": {
                            "otm.io/target-replicas": "1",
                            "otm.io/caddy-sha256": digest,
                            "otm.io/activation": "held-hosted-runtime-not-qualified",
                        },
                    },
                    "spec": {
                        "serviceAccountName": "otm-ingress",
                        "automountServiceAccountToken": False,
                        "nodeSelector": {
                            "kubernetes.io/os": "linux",
                            "kubernetes.io/arch": "arm64",
                        },
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 10001,
                            "runAsGroup": 10001,
                            "fsGroup": 10001,
                            "fsGroupChangePolicy": "OnRootMismatch",
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "terminationGracePeriodSeconds": 60,
                        "containers": [
                            {
                                "name": "caddy",
                                "image": image,
                                "command": [
                                    "caddy",
                                    "run",
                                    "--config",
                                    "/etc/otm-caddy/Caddyfile",
                                    "--adapter",
                                    "caddyfile",
                                ],
                                "ports": [
                                    {"name": "http", "containerPort": 8080},
                                    {"name": "https", "containerPort": 8443},
                                ],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                    "limits": {"cpu": "1", "memory": "256Mi"},
                                },
                                "livenessProbe": {
                                    "httpGet": {"path": "/health/live", "port": 9090},
                                    "periodSeconds": 15,
                                },
                                "readinessProbe": {
                                    "timeoutSeconds": 5,
                                    "httpGet": {"path": "/health/ready", "port": 9090},
                                    "periodSeconds": 10,
                                },
                                "volumeMounts": [
                                    {
                                        "name": "settings",
                                        "mountPath": "/etc/otm-caddy",
                                        "readOnly": True,
                                    },
                                    {"name": "state", "mountPath": "/data"},
                                    {"name": "runtime", "mountPath": "/config"},
                                    # Dedicated size-limited pod emptyDir; not host shared /tmp.
                                    {"name": "temporary", "mountPath": "/tmp"},  # nosec B108
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "settings",
                                "configMap": {"name": config_name, "defaultMode": 0o444},
                            },
                            {
                                "name": "state",
                                "persistentVolumeClaim": {"claimName": "otm-caddy-state"},
                            },
                            {"name": "runtime", "emptyDir": {"sizeLimit": "16Mi"}},
                            {"name": "temporary", "emptyDir": {"sizeLimit": "16Mi"}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": metadata("otm-ingress"),
            "spec": {
                "type": "LoadBalancer",
                "externalTrafficPolicy": "Local",
                "healthCheckNodePort": HEALTH_NODE_PORT,
                "ipFamilies": ["IPv4"],
                "ipFamilyPolicy": "SingleStack",
                # Shared listener range; required NSG handoff restricts HTTPS separately.
                "loadBalancerSourceRanges": ["0.0.0.0/0"],
                "selector": labels,
                "ports": [
                    {
                        "name": "http",
                        "port": 80,
                        "targetPort": "http",
                        "nodePort": HTTP_NODE_PORT,
                        "protocol": "TCP",
                    },
                    {
                        "name": "https",
                        "port": 443,
                        "targetPort": "https",
                        "nodePort": HTTPS_NODE_PORT,
                        "protocol": "TCP",
                    },
                ],
            },
        },
    ]

    resources[-1]["metadata"]["annotations"] = {
        "oci.oraclecloud.com/load-balancer-type": "nlb",
        "oci.oraclecloud.com/compartment-id": network.compartment_ocid,
        "oci-network-load-balancer.oraclecloud.com/subnet": network.edge_subnet_ocid,
        "oci-network-load-balancer.oraclecloud.com/oci-network-security-groups": (
            network.edge_nsg_ocid
        ),
        "oci.oraclecloud.com/security-rule-management-mode": "None",
        "oci-network-load-balancer.oraclecloud.com/security-list-management-mode": "None",
        "oci-network-load-balancer.oraclecloud.com/is-preserve-source": "false",
        "oci-network-load-balancer.oraclecloud.com/is-ppv2-enabled": "false",
        "oci.oraclecloud.com/reserved-ips": network.reserved_ipv4,
    }
    return resources
