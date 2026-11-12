"""Boundary checks for disposable image qualification and its destructive cleanup guards."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "container_smoke", Path(__file__).resolve().parents[2] / "scripts/run_container_smoke.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# Reject traversal on either side of the installed-asset hash manifest.
@pytest.mark.parametrize(
    "source,target",
    [("../private", "asset"), ("asset", "../private"), ("/private", "asset"), ("asset", "a\\b")],
)
def test_asset_manifest_rejects_escape(tmp_path, source, target):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        "[tool.hatch.build.targets.wheel.force-include]\n"
        + json.dumps(source)
        + " = "
        + json.dumps(target)
        + "\n"
    )
    with pytest.raises(ValueError, match="UNSAFE_PACKAGE_ASSET"):
        MODULE.expected_assets(tmp_path)


# Refuse cleanup of a container with another owner's label even when its name matches.
def test_cleanup_requires_exact_ownership(monkeypatch):
    calls = []

    # Return a foreign container; any second call would represent unauthorized destruction.
    def run(arguments, **kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(
            arguments, 0, json.dumps([{"Config": {"Labels": {"owner": "foreign"}}}]), ""
        )

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    with pytest.raises(ValueError, match="OWNERSHIP_MISMATCH"):
        MODULE.remove_owned("docker", "candidate", "owner", "expected")
    assert len(calls) == 1


# A Docker daemon failure must not be mistaken for successful removal of an absent resource.
def test_cleanup_does_not_hide_daemon_failure(monkeypatch):
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "daemon unavailable"),
    )
    with pytest.raises(RuntimeError, match="INSPECTION_FAILED"):
        MODULE.remove_owned("docker", "candidate", "owner", "expected")


# Verify real repository assets can be hashed without borrowing private files or editable imports.
def test_actual_asset_manifest():
    assets = MODULE.expected_assets(MODULE.ROOT)
    assert "otm_settings/application.toml" in assets
    assert "otm_migrations/alembic.ini" in assets
    assert all(len(value) == 64 for value in assets.values())


# Reject a source symlink that would admit a private file outside the declared backend tree.
def test_asset_manifest_rejects_symlink(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (tmp_path / "private.txt").write_text("synthetic private canary")
    (backend / "asset").symlink_to(tmp_path / "private.txt")
    (backend / "pyproject.toml").write_text(
        '[tool.hatch.build.targets.wheel.force-include]\n"asset" = "package/asset"\n'
    )
    with pytest.raises(ValueError, match="UNSAFE_PACKAGE_ASSET"):
        MODULE.expected_assets(tmp_path)


# Remove only the exact owned resource and keep every destructive subprocess bounded.
def test_cleanup_removes_owned_container(monkeypatch):
    calls = []

    # Supply the matching ownership proof, then record the exact requested removal.
    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(
            arguments, 0, json.dumps([{"Config": {"Labels": {"owner": "expected"}}}]), ""
        )

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    MODULE.remove_owned("docker", "candidate", "owner", "expected")
    assert calls[1][0] == ["docker", "rm", "--force", "candidate"]
    assert all(call[1]["timeout"] == 30 for call in calls)


# An already absent owned test name is harmless and must not trigger a removal command.
def test_cleanup_tolerates_missing_container(monkeypatch):
    calls = []

    # Mimic Docker's specific not-found result without converting general failures into success.
    def run(arguments, **kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 1, "[]", "error: no such object: candidate")

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    MODULE.remove_owned("docker", "candidate", "owner", "expected")
    assert len(calls) == 1
