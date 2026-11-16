"""Isolated Caddy/HTTP-01/TLS tests; never calls a public CA or saved Atlas."""

import http.client
import json
import os
import re
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from caddy_image_policy import check_latest, evaluate
from run_container_smoke import SCANNER, remove_owned

from otm.caddy_ingress import caddyfile
from otm.local_development import docker
from otm.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
LABEL = "otm.ingress.check"
HOST = "atlas.example.test"


# Only a fixed version+digest manifest may select an upstream ACME test image.
def test_image(path):
    lines = [line for line in path.read_text().splitlines() if line and not line.startswith("#")]
    if (
        len(lines) != 1
        or re.fullmatch(
            r"FROM ghcr.io/letsencrypt/pebble:[0-9]+\.[0-9]+\.[0-9]+@sha256:[0-9a-f]{64}",
            lines[0],
        )
        is None
    ):
        raise ValueError("ACME_TEST_IMAGE_PIN_REQUIRED")
    return lines[0].removeprefix("FROM ")


# Use committed synthetic settings, never local profiles or saved service state.
def synthetic_settings(directory):
    content = (
        (ROOT / "backend/config/staging.application.toml")
        .read_text()
        .replace("https://otm.example.test", "https://" + HOST)
    )
    content += '\n[hosted.ingress]\nacme_email="operator@example.test"\n'
    content += '\n[recovery_console]\nallowed_cidrs=["198.51.100.0/24"]\n'
    path = directory / "application.toml"
    path.write_text(content)
    return load_settings(path)


# A bounded retry waits only for owned local services; required checks never skip on timeout.
def eventually(function, deadline):
    while time.monotonic() < deadline:
        try:
            return function()
        except (
            OSError,
            ValueError,
            RuntimeError,
            http.client.HTTPException,
            AssertionError,
        ):
            time.sleep(0.2)
    raise RuntimeError("CADDY_NATIVE_WAIT_EXHAUSTED")


# Every resource is UUID-owned and cleaned only after label verification; logs remain private.
def main():
    os.umask(0o077)
    artifact_root = ROOT / ".local-dev/quality"
    artifact_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="caddy-", dir=artifact_root))
    owner = uuid4().hex
    client = docker()
    prefix = "otm-ingress-" + owner
    network, volume, image = prefix + "-net", prefix + "-state", "otm-caddy:" + owner
    names = {role: prefix + "-" + role for role in ("caddy", "ca", "backend", "scanner", "adapt")}
    containers, owned_network, owned_volume, owned_image = [], False, False, False
    deadline = time.monotonic() + 300
    stage, passed = "latest-release", False
    latest_verified = None
    protocol_passed = False
    scan_policy = {"accepted": [], "blocked": []}
    try:
        latest_verified = check_latest()
        stage = "build"

        # Captured fixed argv never carries key material; all logs and test TLS state are private.
        def command(arguments, *, input=None):
            remaining = max(1, int(deadline - time.monotonic()))
            result = subprocess.run(
                arguments,
                input=input,
                capture_output=True,
                check=False,
                timeout=remaining,
            )
            with (directory / "commands.log").open("ab") as stream:
                stream.write(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("CADDY_NATIVE_COMMAND_FAILED")
            return result.stdout

        # Container names are fixed by our UUID, never supplied by a browser or operator artifact.
        def start(role, arguments):
            name = names[role]
            containers.append(name)
            # Private Linux mounts retain runner ownership; root has no DAC bypass here.
            fixture_user = (
                ["--user", f"{os.getuid()}:{os.getgid()}"] if role in {"backend", "ca"} else []
            )
            return command(
                [
                    client,
                    "run",
                    "--detach",
                    "--name",
                    name,
                    "--label",
                    LABEL + "=" + owner,
                    *fixture_user,
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--network",
                    network,
                ]
                + arguments
            )

        # Requests execute inside the internal network; no test server publishes a host port.
        def probe(
            role,
            container_port,
            path,
            *,
            method="GET",
            headers=None,
            context=None,
            host=HOST,
        ):
            target = {"ca": "pebble", "backend": "otm-api", "caddy": HOST}[role]
            body = {
                "target": target,
                "port": container_port,
                "path": path,
                "method": method,
                "tls": context is not None,
                "ca": "server.crt" if role == "ca" else "issuance-root.crt",
                "sni": host,
                "headers": {"Host": host, **(headers or {})},
            }
            return json.loads(
                command(
                    [
                        client,
                        "exec",
                        "--interactive",
                        names["backend"],
                        "python",
                        "/probe.py",
                        "request",
                    ],
                    input=json.dumps(body).encode(),
                )
            )

        # Positive probes fail closed on TLS errors; negative TLS probes inspect the explicit error.
        def request(role, container_port, path, **kwargs):
            result = probe(role, container_port, path, **kwargs)
            if result.get("tls_error"):
                raise ValueError("NATIVE_TLS_VERIFICATION_FAILED")
            return result["status"], result["body"].encode(), result["headers"]

        command(
            [
                client,
                "build",
                "--pull",
                "--label",
                LABEL + "=" + owner,
                "--tag",
                image,
                str(ROOT / "tools/caddy"),
            ]
        )
        owned_image = True
        command(
            [
                client,
                "network",
                "create",
                "--internal",
                "--label",
                LABEL + "=" + owner,
                network,
            ]
        )
        owned_network = True
        command([client, "volume", "create", "--label", LABEL + "=" + owner, volume])
        owned_volume = True
        python_image = re.findall(
            r"^FROM (python:[^ ]+)", (ROOT / "Dockerfile").read_text(), re.MULTILINE
        )[0]
        if "@sha256:" not in python_image:
            raise ValueError("NATIVE_PYTHON_PIN_REQUIRED")
        trust = directory / "trust"
        trust.mkdir(mode=0o755)
        start(
            "backend",
            [
                "--network-alias",
                "otm-api",
                "--mount",
                "type=bind,src="
                + str(ROOT / "scripts/caddy_probe_backend.py")
                + ",dst=/probe.py,readonly",
                "--mount",
                "type=bind,src=" + str(trust) + ",dst=/test-trust,readonly",
                python_image,
                "python",
                "/probe.py",
            ],
        )
        stage = "test-ca"
        # The test CA transport uses its own generated self-signed certificate, trusted only here.
        key, cert = directory / "server.key", directory / "server.crt"
        command(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "2",
                "-subj",
                "/CN=pebble",
                "-addext",
                "subjectAltName=DNS:pebble,DNS:localhost",
            ]
        )
        cert.chmod(0o644)
        (trust / "server.crt").write_bytes(cert.read_bytes())
        (trust / "server.crt").chmod(0o644)
        ca_config = directory / "pebble.json"
        ca_config.write_text(
            json.dumps(
                {
                    "pebble": {
                        "listenAddress": "0.0.0.0:14000",
                        "managementListenAddress": "0.0.0.0:15000",
                        "certificate": "/test/server.crt",
                        "privateKey": "/test/server.key",
                        "httpPort": 8080,
                        "tlsPort": 8443,
                        "externalAccountBindingRequired": False,
                        "profiles": {
                            "default": {
                                "description": "Disposable native test",
                                "validityPeriod": 120,
                            }
                        },
                        "retryAfter": {"authz": 1, "order": 1},
                    }
                }
            )
        )
        start(
            "ca",
            [
                "--network-alias",
                "pebble",
                "--env",
                "PEBBLE_VA_NOSLEEP=1",
                "--mount",
                "type=bind,src=" + str(directory) + ",dst=/test,readonly",
                test_image(ROOT / "tools/pebble/Dockerfile"),
                "-config",
                "/test/pebble.json",
                "-strict",
            ],
        )
        tls_context = ssl.create_default_context(cafile=str(cert))

        # Pebble publishes its random issuance root over the independently verified test transport.
        def get_root():
            status, body, _ = request(
                "ca", 15000, "/roots/0", context=tls_context, host="localhost"
            )
            assert status == 200 and b"BEGIN CERTIFICATE" in body
            return body

        root = eventually(get_root, min(deadline, time.monotonic() + 30))
        root_path = trust / "issuance-root.crt"
        root_path.write_bytes(root)
        root_path.chmod(0o644)
        app_context = ssl.create_default_context(cafile=str(root_path))
        stage = "config-validation"
        config_path = directory / "Caddyfile"
        config_path.write_text(caddyfile(synthetic_settings(directory)))
        config_path.chmod(0o644)
        # Native adapter validates production syntax with network access disabled.
        adapt_name = names["adapt"]
        containers.append(adapt_name)
        adapted = command(
            [
                client,
                "run",
                "--name",
                adapt_name,
                "--label",
                LABEL + "=" + owner,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                "type=bind,src=" + str(config_path) + ",dst=/etc/Caddyfile,readonly",
                image,
                "caddy",
                "adapt",
                "--config",
                "/etc/Caddyfile",
                "--adapter",
                "caddyfile",
            ]
        )
        config = json.loads(adapted)
        # Only this fixture changes issuer trust and renewal timing; app code remains unchanged.
        automation = config["apps"]["tls"]["automation"]
        automation["renew_interval"] = "2s"
        for policy in automation["policies"]:
            policy["renewal_window_ratio"] = 0.5
            for issuer in policy["issuers"]:
                issuer["ca"] = "https://pebble:14000/dir"
                issuer["test_ca"] = "https://pebble:14000/dir"
                issuer["trusted_roots_pem_files"] = ["/etc/pebble-ca.crt"]
        assert "letsencrypt.org" not in json.dumps(config) and "zerossl.com" not in json.dumps(
            config
        )
        native_config = directory / "caddy.json"
        native_config.write_text(json.dumps(config))
        native_config.chmod(0o644)
        start(
            "caddy",
            [
                "--network-alias",
                HOST,
                "--mount",
                "type=bind,src=" + str(native_config) + ",dst=/etc/caddy.json,readonly",
                "--mount",
                "type=bind,src=" + str(cert) + ",dst=/etc/pebble-ca.crt,readonly",
                "--mount",
                "type=volume,src=" + volume + ",dst=/data",
                "--tmpfs",
                "/config:uid=10001,gid=10001,mode=0700",
                "--tmpfs",
                "/tmp:uid=10001,gid=10001,mode=0700",
                image,
                "caddy",
                "run",
                "--config",
                "/etc/caddy.json",
            ],
        )
        stage = "http01-issuance-and-proxy"

        # Issuance succeeds only if Pebble actually retrieves the active HTTP-01 response.
        def issued():
            status, body, _ = request(
                "caddy",
                8443,
                "/api/probe",
                context=app_context,
                headers={
                    "X-Forwarded-For": "attacker",
                    "X-Forwarded-Proto": "http",
                    "X-Forwarded-Host": "attacker.example.test",
                    "Forwarded": "for=attacker",
                },
            )
            assert status == 200
            headers = {key.lower(): value for key, value in json.loads(body)["headers"].items()}
            assert headers["x-forwarded-proto"] == "https"
            assert "attacker" not in headers["x-forwarded-for"]
            assert headers["x-forwarded-host"] == HOST and "forwarded" not in headers
            return True

        eventually(issued, min(deadline, time.monotonic() + 60))
        # Record independent upstream evidence before probing public paths/methods/headers.
        before = json.loads(request("backend", 8080, "/counter")[1])["count"]
        for method in ("GET", "HEAD", "POST", "PUT", "OPTIONS"):
            for path in (
                "/",
                "/login",
                "/api/probe",
                "/health/ready",
                "/config/",
                "/.well-known/acme-challenge/not-active",
            ):
                status, _, headers = request("caddy", 8080, path, method=method)
                assert status == 404 and not any(
                    key.lower() == "location" for key, value in headers
                )
        assert request("caddy", 8080, "/", headers={"Host": "unknown.example.test"})[0] == 404
        assert (
            request(
                "caddy",
                8443,
                "/api/probe",
                context=app_context,
                headers={"Host": "unknown.example.test"},
            )[0]
            == 404
        )
        assert json.loads(request("backend", 8080, "/counter")[1])["count"] == before
        assert (
            probe("caddy", 8443, "/", context=app_context, host="unknown.example.test").get(
                "tls_error"
            )
            is True
        )
        assert probe("caddy", 2019, "/", method="PORT_CLOSED").get("port_closed") is True
        stage = "persistence"

        # Compare the verified leaf certificate across a real process restart and persistent volume.
        def certificate():
            result = probe("caddy", 8443, "/", method="CERTIFICATE", context=app_context)
            assert "certificate" in result
            return result["certificate"]

        previous = certificate()
        command([client, "restart", names["caddy"]])
        assert eventually(certificate, min(deadline, time.monotonic() + 30)) == previous
        # A real issued certificate is short-lived only in this CA; observe an actual renewal.
        stage = "renewal"

        # Require a different trusted leaf, not merely a successful readiness response.
        def renewed():
            assert certificate() != previous
            return True

        eventually(renewed, min(deadline, time.monotonic() + 100))
        issued()
        protocol_passed = True
        stage = "image-scan"
        archive = directory / "image.tar"
        command([client, "save", "--output", str(archive), image])
        scanner = names["scanner"]
        containers.append(scanner)
        command(
            [
                client,
                "run",
                "--name",
                scanner,
                "--label",
                LABEL + "=" + owner,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--tmpfs",
                "/tmp:mode=1777",
                "--mount",
                "type=bind,src=" + str(directory) + ",dst=/scan",
                SCANNER,
                "image",
                "--cache-dir",
                "/scan/cache",
                "--scanners",
                "vuln",
                "--severity",
                "HIGH,CRITICAL",
                "--format",
                "json",
                "--output",
                "/scan/image-scan.json",
                "--exit-code",
                "0",
                "--input",
                "/scan/image.tar",
            ]
        )
        report = json.loads((directory / "image-scan.json").read_text())
        # Scanner errors still fail command(); evaluate all returned findings without ignoring them.
        scan_policy = evaluate(report)
        assert not scan_policy["blocked"]
        passed = True
    except (
        OSError,
        ValueError,
        RuntimeError,
        AssertionError,
        KeyError,
        subprocess.SubprocessError,
    ):
        pass
    finally:
        # Capture private diagnostics, then verify ownership before deleting test resources.
        for name in reversed(containers):
            result = subprocess.run(
                [client, "logs", name], capture_output=True, check=False, timeout=10
            )
            (directory / (name + ".log")).write_bytes(result.stdout + result.stderr)
            remove_owned(client, name, LABEL, owner)
        for kind, name, owned in (
            ("volume", volume, owned_volume),
            ("network", network, owned_network),
            ("image", image, owned_image),
        ):
            if owned:
                record = json.loads(
                    subprocess.run(
                        [client, kind, "inspect", name],
                        capture_output=True,
                        check=True,
                        timeout=15,
                    ).stdout
                )[0]
                labels = record["Config"]["Labels"] if kind == "image" else record["Labels"]
                if labels.get(LABEL) != owner:
                    raise RuntimeError("CADDY_RESOURCE_OWNERSHIP_MISMATCH")
                subprocess.run(
                    [client, kind, "rm", name],
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
    summary = {
        "status": "pass" if passed else "fail",
        "stage": "complete" if passed else stage,
        "artifacts": str(directory.relative_to(ROOT)),
        "saved_instance_used": False,
        "protocol_checks_passed": protocol_passed,
        "image_scan_passed": passed,
        "image_findings": scan_policy,
        "latest_official_release": latest_verified,
    }
    (directory / "summary.json").write_text(json.dumps(summary) + "\n")
    print(json.dumps(summary))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
