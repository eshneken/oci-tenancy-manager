"""Keep update automation bound to the exact digest-pinned scanner used by local/CI checks."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "container_updates", ROOT / "scripts/run_container_smoke.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# Missing digests, extra instructions and unrelated images cannot select the scanner executable.
@pytest.mark.parametrize(
    "content",
    [
        "FROM aquasec/trivy:0.76.2\n",
        "FROM unrelated/image:1.2.3@sha256:" + "a" * 64,
        "FROM aquasec/trivy:0.76.2@sha256:" + "a" * 64 + "\nRUN echo unreviewed\n",
        "FROM aquasec/trivy:latest@sha256:" + "a" * 64,
        "",
    ],
)
def test_scanner_manifest_rejects_unpinned_or_extra_instructions(tmp_path, content):
    manifest = tmp_path / "Dockerfile"
    manifest.write_text(content)
    with pytest.raises(ValueError, match="INVALID_SCANNER_MANIFEST"):
        MODULE.scanner_image(manifest)


# A reviewed version/digest change is consumed without a second hardcoded Python scanner pin.
def test_scanner_manifest_accepts_updated_pin(tmp_path):
    manifest = tmp_path / "Dockerfile"
    image = "aquasec/trivy:0.77.1@sha256:" + "a" * 64
    manifest.write_text("# synthetic upstream pin\nFROM " + image + "\n")
    assert MODULE.scanner_image(manifest) == image
    assert MODULE.SCANNER == MODULE.scanner_image(ROOT / "tools/trivy/Dockerfile")


# Dependabot must discover the scanner and app image manifests while limiting update PR noise.
def test_update_configuration_covers_actual_manifests():
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    assert config["version"] == 2
    updates = {entry["package-ecosystem"]: entry for entry in config["updates"]}
    docker = updates["docker"]
    assert set(docker["directories"]) == {"/", "/tools/trivy"}
    for directory in docker["directories"]:
        assert (ROOT / directory.lstrip("/") / "Dockerfile").is_file()
    assert updates["github-actions"]["directory"] == "/"
    for entry in updates.values():
        assert entry["schedule"]["interval"] == "weekly"
        assert entry["open-pull-requests-limit"] == 1
        assert any(group["patterns"] == ["*"] for group in entry["groups"].values())
    python = next(item for item in docker["ignore"] if item["dependency-name"] == "python")
    assert set(python["update-types"]) == {
        "version-update:semver-major",
        "version-update:semver-minor",
    }
