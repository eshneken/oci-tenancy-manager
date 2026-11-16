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
