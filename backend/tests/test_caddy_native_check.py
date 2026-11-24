"""Native ingress checks require exact test trust, bounded waits and a pinned ACME fixture."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "caddy_native_check", SCRIPTS / "check_caddy_ingress.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# A mutable/unreviewed fixture image cannot select the isolated ACME authority used by CI.
def test_acme_fixture_pin_rejects_mutability(tmp_path):
    actual = MODULE.test_image(MODULE.ROOT / "tools/pebble/Dockerfile")
    assert actual.startswith("ghcr.io/letsencrypt/pebble:2.") and "@sha256:" in actual
    candidate = tmp_path / "Dockerfile"
    for invalid in (
        "FROM ghcr.io/letsencrypt/pebble:latest",
        "FROM ghcr.io/letsencrypt/pebble:2.10.3",
        "FROM other/pebble:2.10.3@sha256:" + "a" * 64,
        "FROM ghcr.io/letsencrypt/pebble:2.10.3@sha256:" + "a" * 64 + "\nRUN echo changed",
    ):
        candidate.write_text(invalid)
        with pytest.raises(ValueError, match="ACME_TEST_IMAGE_PIN_REQUIRED"):
            MODULE.test_image(candidate)


# CI must build from committed synthetic profiles, never local settings or saved review secrets.
def test_native_settings_are_synthetic_and_fixed(tmp_path):
    settings = MODULE.synthetic_settings(tmp_path)
    assert settings.hosted.public_origin == "https://atlas.example.test"
    assert settings.hosted.ingress.acme_email == "operator@example.test"
    assert settings.recovery_console.allowed_cidrs == ("198.51.100.0/24",)
    assert settings.provider_mode == "simulated"


# Startup races retry within their original deadline, while an exhausted retry remains a failure.
def test_local_retry_is_bounded_and_required(monkeypatch):
    monkeypatch.setattr(MODULE.time, "sleep", lambda duration: None)
    clock = Mock(side_effect=[0, 1, 2, 3])
    monkeypatch.setattr(MODULE.time, "monotonic", clock)
    action = Mock(side_effect=[RuntimeError("not ready"), True])
    assert MODULE.eventually(action, 3) is True
    assert action.call_count == 2
    with pytest.raises(RuntimeError, match="CADDY_NATIVE_WAIT_EXHAUSTED"):
        MODULE.eventually(Mock(side_effect=AssertionError), 3)


# Fresh CI jobs have no ignored artifact parent; startup must create private output before Docker.
def test_native_check_creates_artifact_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)

    # Stop at the first external boundary after proving private artifact initialization completed.
    def stop_before_docker():
        parent = tmp_path / ".local-dev/quality"
        assert parent.is_dir()
        directories = list(parent.iterdir())
        assert len(directories) == 1 and directories[0].is_dir()
        assert directories[0].stat().st_mode & 0o777 == 0o700
        raise RuntimeError("STOP_BEFORE_DOCKER")

    monkeypatch.setattr(MODULE, "docker", stop_before_docker)
    previous_mask = MODULE.os.umask(0o077)
    try:
        with pytest.raises(RuntimeError, match="STOP_BEFORE_DOCKER"):
            MODULE.main()
    finally:
        MODULE.os.umask(previous_mask)


# Linux bind mounts retain runner ownership; fixture consumers must not depend on root DAC bypass.
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_fixture_containers_use_runner_identity_without_relaxing_permissions(
    tmp_path, monkeypatch, cleanup_fails
):
    from types import SimpleNamespace

    original_root = MODULE.ROOT
    (tmp_path / "Dockerfile").write_bytes((original_root / "Dockerfile").read_bytes())
    pin = tmp_path / "tools/pebble/Dockerfile"
    pin.parent.mkdir(parents=True)
    pin.write_bytes((original_root / "tools/pebble/Dockerfile").read_bytes())
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "docker", lambda: "docker")
    monkeypatch.setattr(MODULE, "check_latest", lambda: "v2.11.9")
    removed = []

    # A failed first container removal still allows the other ownership checks and cleanup.
    def remove_owned(client, name, label, owner, *, kind="container", log_path=None):
        removed.append(kind)
        if cleanup_fails and len(removed) == 1:
            raise RuntimeError("SIMULATED_DOCKER_CLEANUP_FAILURE")
        return True

    monkeypatch.setattr(MODULE, "remove_owned", remove_owned)
    monkeypatch.setattr(MODULE.os, "getuid", lambda: 1001)
    monkeypatch.setattr(MODULE.os, "getgid", lambda: 1001)
    calls = []
    labels = {}

    # Capture real startup argv and stop at the CA boundary before any certificate or network probe.
    def command(arguments, **kwargs):
        calls.append(arguments)
        if "--label" in arguments:
            key, value = arguments[arguments.index("--label") + 1].split("=", 1)
            labels[key] = value
        if "inspect" in arguments:
            import json

            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{"Labels": labels, "Config": {"Labels": labels}}]).encode(),
                stderr=b"",
            )
        if arguments[0] == "openssl":
            for flag in ("-keyout", "-out"):
                Path(arguments[arguments.index(flag) + 1]).write_text("synthetic fixture")
        if "--network-alias" in arguments:
            alias = arguments[arguments.index("--network-alias") + 1]
            if alias == "pebble":
                raise RuntimeError("STOP_AFTER_CA_START")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(MODULE.subprocess, "run", command)
    previous_mask = MODULE.os.umask(0o077)
    try:
        assert MODULE.main() == 1
    finally:
        MODULE.os.umask(previous_mask)
    fixtures = {
        args[args.index("--network-alias") + 1]: args for args in calls if "--network-alias" in args
    }
    assert set(fixtures) == {"otm-api", "pebble"}
    for arguments in fixtures.values():
        assert "--user" in arguments
        assert arguments[arguments.index("--user") + 1] == "1001:1001"
        assert arguments[arguments.index("--cap-drop") + 1] == "ALL"
        assert "--read-only" in arguments
        assert "no-new-privileges" in arguments
    directory = next((tmp_path / ".local-dev/quality").iterdir())
    assert removed == ["container", "container", "volume", "network", "image"]
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "server.key").stat().st_mode & 0o777 == 0o600
