"""Protected version pins remain data-only; rendering does not authenticate or upgrade services."""

import json
import runpy
import stat
from pathlib import Path

import pytest

from otm.platform_version_release import main, render_platform_versions


# Both versions stay strings; exact canonical values are preserved in an owner-only candidate.
def test_private_version_render(tmp_path):
    output = tmp_path / "versions.tfvars.json"
    digest = render_platform_versions(output, "v1.37.0", "16")
    assert json.loads(output.read_text()) == {
        "oke_kubernetes_version": "v1.37.0",
        "postgresql_version": "16",
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert len(digest) == 64


# Missing, floating, minor-only, injection, padded and oversized pins cannot create a partial file.
@pytest.mark.parametrize(
    "oke, postgres",
    [
        (None, "16"),
        ("latest", "16"),
        ("v1.36", "16"),
        ("1.37.0", "16"),
        ("v01.37.0", "16"),
        ("v1.036.4", "16"),
        ("v1.36.04", "16"),
        ("v1.37.0;false", "16"),
        ("v1.36." + "1" * 30, "16"),
        ("v1.37.0", None),
        ("v1.37.0", "latest"),
        ("v1.37.0", "16.4"),
        ("v1.37.0", "016"),
        ("v1.37.0", 16),
        ("v1.37.0", "16\n"),
    ],
)
def test_invalid_versions_never_create_candidate(tmp_path, oke, postgres):
    output = tmp_path / "versions.tfvars.json"
    with pytest.raises(ValueError, match="^INVALID_PLATFORM_VERSIONS$"):
        render_platform_versions(output, oke, postgres)
    assert not output.exists()


# Existing candidates and symlinks are never overwritten even by otherwise valid pins.
def test_preserve_existing_candidate(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("preserve")
    alias = tmp_path / "alias.json"
    alias.symlink_to(output)
    for destination in (output, alias):
        with pytest.raises(FileExistsError):
            render_platform_versions(destination, "v1.37.0", "16")
    assert output.read_text() == "preserve"


# The CLI reads both environment variables and returns only a digest or a fixed failure.
def test_cli_and_missing_variable(tmp_path, monkeypatch, capsys):
    output = tmp_path / "versions.tfvars.json"
    monkeypatch.setenv("OTM_OKE_KUBERNETES_VERSION", "v1.37.0")
    monkeypatch.setenv("OTM_POSTGRESQL_VERSION", "16")
    assert main(["--output", str(output)]) == 0
    assert list(json.loads(capsys.readouterr().out)) == ["platform_versions_sha256"]
    monkeypatch.delenv("OTM_POSTGRESQL_VERSION")
    assert main(["--output", str(tmp_path / "missing.json")]) == 1
    assert capsys.readouterr().out == "PLATFORM_VERSIONS_REJECTED\n"


# Exercise the documented module invocation independently of a deployment workflow or OCI access.
def test_module_entrypoint(tmp_path, monkeypatch, capsys):
    import otm.platform_version_release

    output = tmp_path / "versions.tfvars.json"
    monkeypatch.setenv("OTM_OKE_KUBERNETES_VERSION", "v1.37.0")
    monkeypatch.setenv("OTM_POSTGRESQL_VERSION", "16")
    monkeypatch.setattr("sys.argv", ["otm.platform_version_release", "--output", str(output)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(otm.platform_version_release.__file__)), run_name="__main__")
    assert result.value.code == 0 and output.exists()
    assert "platform_versions_sha256" in capsys.readouterr().out
