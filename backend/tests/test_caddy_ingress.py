"""Public HTTP-01 ingress is coupled to the exact firewall handoff and trusted origin."""

import json
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from otm.caddy_ingress import caddy_resources, caddyfile
from otm.ingress_settings import CaddyIngressSettings, CaddyNetworkBinding, ingress_hostname
from otm.kubernetes_release import hosted_bundle, main
from otm.settings import ApplicationSettings

CONFIG = Path(__file__).resolve().parents[1] / "config"
IMAGE = "ghcr.io/example/atlas@sha256:" + "a" * 64
CADDY = "ghcr.io/example/caddy@sha256:" + "b" * 64


# Every source input is synthetic; no live origin, address, API profile or certificate is used.
def candidate(environment="staging"):
    raw = (CONFIG / (environment + ".application.toml")).read_text()
    raw += '\n[recovery_console]\nallowed_cidrs=["198.51.100.0/24"]\n'
    raw += '\n[hosted.ingress]\nacme_email="operator@example.test"\n'
    network = {
        "environment": environment,
        "compartment_ocid": "ocid1.compartment.oc1..synthetic",
        "https_allowed_cidrs": ["198.51.100.0/24"],
        "reserved_ipv4": "203.0.113.80",
        "edge_subnet_ocid": "ocid1.subnet.oc1.iad.synthetic",
        "edge_nsg_ocid": "ocid1.networksecuritygroup.oc1.iad.synthetic",
    }
    return raw, network


# The only public proxy path is HTTPS; HTTP, admin and certificate policy have fixed boundaries.
def test_caddy_configuration():
    raw, _ = candidate()
    text = caddyfile(ApplicationSettings.model_validate(tomllib.loads(raw)))
    assert "admin off" in text and "auto_https disable_redirects" in text
    assert "persist_config off" in text and "disable_tlsalpn_challenge" in text
    assert "dir https://acme-v02.api.letsencrypt.org/directory" in text
    http = text.split("http://:8080 {")[1].split("}")[0]
    assert http.strip() == "respond 404"
    assert "on_demand" not in text and "dns " not in text
    assert "header_up -Forwarded" in text and "header_up -X-Real-IP" in text
    assert "header_up X-Forwarded-Proto https" in text
    assert "http://otm-api:8080" in text


# Both hosted targets bind a single source-NAT NLB and only the exact private backend NodePorts.
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_ingress_bundle_contract(environment):
    raw, network = candidate(environment)
    bundle = hosted_bundle(raw, IMAGE, environment, caddy_image=CADDY, ingress_network=network)
    assert len(bundle["items"]) == 14
    service = next(
        item
        for item in bundle["items"]
        if item["kind"] == "Service" and item["metadata"]["name"] == "otm-ingress"
    )
    assert service["metadata"]["annotations"] == {
        "oci.oraclecloud.com/load-balancer-type": "nlb",
        "oci.oraclecloud.com/compartment-id": network["compartment_ocid"],
        "oci-network-load-balancer.oraclecloud.com/subnet": network["edge_subnet_ocid"],
        "oci-network-load-balancer.oraclecloud.com/oci-network-security-groups": network[
            "edge_nsg_ocid"
        ],
        "oci.oraclecloud.com/security-rule-management-mode": "None",
        "oci-network-load-balancer.oraclecloud.com/security-list-management-mode": "None",
        "oci-network-load-balancer.oraclecloud.com/is-preserve-source": "false",
        "oci-network-load-balancer.oraclecloud.com/is-ppv2-enabled": "false",
        "oci.oraclecloud.com/reserved-ips": "203.0.113.80",
    }
    spec = service["spec"]
    assert spec["type"] == "LoadBalancer" and spec["externalTrafficPolicy"] == "Local"
    assert spec["loadBalancerSourceRanges"] == ["0.0.0.0/0"]
    assert spec["healthCheckNodePort"] == 32081
    assert [(item["port"], item["nodePort"]) for item in spec["ports"]] == [
        (80, 31080),
        (443, 31443),
    ]
    deployment = next(
        item
        for item in bundle["items"]
        if item["kind"] == "Deployment" and item["metadata"]["name"] == "otm-ingress"
    )
    assert deployment["spec"]["replicas"] == 0 and deployment["spec"]["strategy"] == {
        "type": "Recreate"
    }
    pod = deployment["spec"]["template"]["spec"]
    assert (
        pod["serviceAccountName"] == "otm-ingress" and pod["automountServiceAccountToken"] is False
    )
    assert pod["securityContext"]["runAsNonRoot"] is True
    container = pod["containers"][0]
    assert container["image"] == CADDY
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert "env" not in container
    assert all("secret" not in volume and "projected" not in volume for volume in pod["volumes"])
    assert all(port["containerPort"] not in {2019, 9090} for port in container["ports"])
    claim = next(item for item in bundle["items"] if item["kind"] == "PersistentVolumeClaim")
    assert claim["spec"]["resources"]["requests"]["storage"] == "50Gi"
    storage = next(item for item in bundle["items"] if item["kind"] == "StorageClass")
    assert (
        storage["reclaimPolicy"] == "Retain"
        and storage["volumeBindingMode"] == "WaitForFirstConsumer"
    )
    assert not any(
        item["kind"] in {"NetworkPolicy", "Ingress", "Secret", "ClusterRoleBinding"}
        for item in bundle["items"]
    )


# Neither absence nor incorrect firewall/port/source binding may create the public Service.
@pytest.mark.parametrize(
    "fault",
    ["missing", "environment", "sources", "edge_nsg", "subnet", "compartment", "extra", "ipv6"],
)
def test_invalid_network_handoff(fault):
    raw, network = candidate()
    if fault == "missing":
        network = None
    elif fault == "environment":
        network["environment"] = "production"
    elif fault == "sources":
        network["https_allowed_cidrs"] = ["192.0.2.0/24"]
    elif fault == "edge_nsg":
        network["edge_nsg_ocid"] = ""
    elif fault == "subnet":
        network["edge_subnet_ocid"] = "bad' override"
    elif fault == "compartment":
        network["compartment_ocid"] = "bad"
    elif fault == "ipv6":
        network["https_allowed_cidrs"] = ["2001:db8::/64"]
    else:
        network["annotation_override"] = "All"
    with pytest.raises(ValueError):
        hosted_bundle(raw, IMAGE, "staging", caddy_image=CADDY, ingress_network=network)


# Public origin must be a canonical single DNS hostname, with no port/wildcard/header interpolation.
@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1",
        "https://[::1]",
        "https://example.test:8443",
        "https://example.test.",
        "https://*.example.test",
        "https://localhost",
        "http://example.test",
        "https://example.test/path",
        "https://" + "a" * 254 + ".test",
    ],
)
def test_bad_ingress_hostnames(origin):
    with pytest.raises(ValueError):
        ingress_hostname(origin)


# ACME contact placeholders cannot interpolate environment secrets into Caddy configuration.
@pytest.mark.parametrize("email", ["bad", "operator\nadmin@example.test", "{$FOO}@example.test"])
def test_bad_acme_contacts(email):
    with pytest.raises(ValueError):
        CaddyIngressSettings(acme_email=email)


# Reserved IP syntax is bounded while local/private/multicast addresses are rejected.
@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.1.2",
        "169.254.169.254",
        "172.16.1.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "not-ip",
    ],
)
def test_bad_reserved_addresses(address):
    _, network = candidate()
    network["reserved_ipv4"] = address
    with pytest.raises(ValueError):
        CaddyNetworkBinding.model_validate(network)


# Image/hand-off options cannot silently apply when the ingress settings are absent.
@pytest.mark.parametrize("extra", ["image", "network"])
def test_orphaned_ingress_inputs_rejected(extra):
    raw, network = candidate()
    raw = raw.split("\n[hosted.ingress]")[0]
    kwargs = {"caddy_image": CADDY} if extra == "image" else {"ingress_network": network}
    with pytest.raises(ValueError):
        hosted_bundle(raw, IMAGE, "staging", **kwargs)


# Mutable or missing proxy images cannot bypass the immutable application-image contract.
@pytest.mark.parametrize("image", [None, "caddy:latest", "caddy:2.11.9"])
def test_pinned_proxy_image_required(image):
    raw, network = candidate()
    with pytest.raises(ValueError):
        hosted_bundle(raw, IMAGE, "staging", caddy_image=image, ingress_network=network)


# A mismatch in namespace cannot move otherwise valid role resources to another deployment.
def test_namespace_binding_guard():
    raw, network = candidate()
    with pytest.raises(ValueError):
        caddy_resources(
            ApplicationSettings.model_validate(tomllib.loads(raw)), CADDY, "otm-other", network
        )


# Ingress cannot be selected without the shared IPv4 source policy.
@pytest.mark.parametrize("policy", [None, {"allowed_cidrs": ["2001:db8::/64"]}])
def test_ingress_requires_ipv4_policy(policy):
    raw, _ = candidate()
    data = tomllib.loads(raw)
    data["recovery_console"] = policy
    with pytest.raises(ValidationError):
        ApplicationSettings.model_validate(data)


# CLI reads only a bounded private handoff and reports hashes rather than operational addresses.
def test_cli_ingress_handoff(tmp_path, capsys):
    raw, network = candidate()
    config = tmp_path / "application.toml"
    config.write_text(raw)
    handoff = tmp_path / "network.json"
    handoff.write_text(json.dumps(network))
    output = tmp_path / "bundle.json"
    arguments = [
        "--config",
        str(config),
        "--output",
        str(output),
        "--image",
        IMAGE,
        "--expected-environment",
        "staging",
        "--caddy-image",
        CADDY,
        "--ingress-network",
        str(handoff),
    ]
    assert main(arguments) == 0
    assert network["reserved_ipv4"] not in capsys.readouterr().out
    assert len(json.loads(output.read_text())["items"]) == 14
    handoff.write_text("x" * 16385)
    assert main(arguments) == 1
    assert capsys.readouterr().out.strip() == "KUBERNETES_BUNDLE_REJECTED"
