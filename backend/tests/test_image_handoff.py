"""Synthetic image handoffs preserve exact selection without exporting private cluster metadata."""

import hashlib
import json
import runpy
import stat
from pathlib import Path

import pytest

from otm.image_handoff import main, render_image_handoff


# Model the documented single Terraform cluster output, including unrelated private coordinates.
@pytest.fixture
def cluster():
    return {
        "environment": "staging",
        "kubernetes_version": "v1.37.1",
        "endpoints": {"private_endpoint": "synthetic-private-endpoint"},
        "image_selection": {
            "image_ocid": "ocid1.image.oc1.iad.syntheticarmimage",
            "kubernetes_version": "v1.37.1",
            "architecture": "AARCH64",
            "os_major": "8",
        },
    }


# Export only the approved Terraform input, with exact byte digest and owner-only file permissions.
def test_selection_only_private_handoff(tmp_path, cluster):
    source = tmp_path / "cluster.json"
    source.write_text(json.dumps(cluster))
    output = tmp_path / "qualified.tfvars.json"
    digest = render_image_handoff(source, output, "v1.37.1", "8", "us-ashburn-1")
    assert json.loads(output.read_bytes()) == {"qualified_node_image": cluster["image_selection"]}
    assert "synthetic-private-endpoint" not in output.read_text()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()


# Reject incorrect provenance bindings and malformed records before creating any candidate.
@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "production"),
        ("environment", None),
        ("kubernetes_version", "v1.37.0"),
        ("image_selection", None),
        ("image_selection", []),
        ("image_ocid", "ocid1.image.oc1.phx.otherregion"),
        ("image_ocid", "ocid1.image.oc1.iad." + "a" * 256),
        ("image_ocid", None),
        ("image_ocid", "$(false)"),
        ("architecture", "X86_64"),
        ("os_major", "9"),
        ("selection_version", "v1.37.0"),
        ("unexpected", "private-field"),
    ],
)
def test_reject_invalid_record(tmp_path, cluster, field, value):
    if field in ("environment", "kubernetes_version", "image_selection"):
        cluster[field] = value
    else:
        cluster["image_selection"][
            "kubernetes_version" if field == "selection_version" else field
        ] = value
    source = tmp_path / "source.json"
    source.write_text(json.dumps(cluster))
    output = tmp_path / "output.json"
    with pytest.raises(ValueError):
        render_image_handoff(source, output, "v1.37.1", "8", "us-ashburn-1")
    assert not output.exists()


# Expected target values are validated independently of otherwise well-formed staging evidence.
@pytest.mark.parametrize(
    "version,os_major,region",
    [
        (None, "8", "us-ashburn-1"),
        ("latest", "8", "us-ashburn-1"),
        ("v1.036.4", "8", "us-ashburn-1"),
        ("v1.36." + "1" * 30, "8", "us-ashburn-1"),
        ("v1.37.1", "10", "us-ashburn-1"),
        ("v1.37.1", "8", "us-phoenix-1"),
    ],
)
def test_reject_invalid_expected_target(tmp_path, cluster, version, os_major, region):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(cluster))
    with pytest.raises(ValueError):
        render_image_handoff(source, tmp_path / "output.json", version, os_major, region)


# Whole-state wrappers, malformed JSON, duplicate fields and oversized input are not cluster output.
@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "not-json",
        '{"environment":"staging","environment":"staging"}',
        '{"cluster":{"value":{}}}',
        " " * 65537,
    ],
)
def test_reject_invalid_document(tmp_path, raw):
    source = tmp_path / "source.json"
    source.write_text(raw)
    with pytest.raises(ValueError):
        render_image_handoff(source, tmp_path / "output.json", "v1.37.1", "8", "us-ashburn-1")


# An accepted OS9 target preserves that explicitly approved family without changing the image ID.
def test_os9_selection(tmp_path, cluster):
    cluster["image_selection"]["os_major"] = "9"
    source = tmp_path / "source.json"
    source.write_text(json.dumps(cluster))
    output = tmp_path / "output.json"
    render_image_handoff(source, output, "v1.37.1", "9", "us-ashburn-1")
    assert json.loads(output.read_text())["qualified_node_image"]["os_major"] == "9"


# Preserve existing candidate files and symlink targets when re-running accepted evidence.
def test_existing_candidate_preserved(tmp_path, cluster):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(cluster))
    existing = tmp_path / "existing.json"
    existing.write_text("keep")
    link = tmp_path / "alias.json"
    link.symlink_to(existing)
    for output in (existing, link):
        with pytest.raises(FileExistsError):
            render_image_handoff(source, output, "v1.37.1", "8", "us-ashburn-1")
    assert existing.read_text() == "keep"


# CLI failures never echo private source content, endpoints, file paths or parser diagnostics.
def test_cli_success_and_safe_failure(tmp_path, cluster, monkeypatch, capsys):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(cluster))
    output = tmp_path / "output.json"
    args = [
        "--staging-cluster-output",
        str(source),
        "--output",
        str(output),
        "--os-major",
        "8",
        "--region",
        "us-ashburn-1",
    ]
    monkeypatch.setenv("OTM_OKE_KUBERNETES_VERSION", "v1.37.1")
    assert main(args) == 0
    assert list(json.loads(capsys.readouterr().out)) == ["image_handoff_sha256"]
    monkeypatch.delenv("OTM_OKE_KUBERNETES_VERSION")
    assert main(args) == 1
    assert capsys.readouterr().out == "IMAGE_HANDOFF_REJECTED\n"


# Exercise the operator module invocation rather than relying only on direct helper calls.
def test_module_entrypoint(tmp_path, cluster, monkeypatch, capsys):
    import otm.image_handoff

    source = tmp_path / "source.json"
    source.write_text(json.dumps(cluster))
    monkeypatch.setenv("OTM_OKE_KUBERNETES_VERSION", "v1.37.1")
    monkeypatch.setattr(
        "sys.argv",
        [
            "otm.image_handoff",
            "--staging-cluster-output",
            str(source),
            "--output",
            str(tmp_path / "output.json"),
            "--os-major",
            "8",
            "--region",
            "us-ashburn-1",
        ],
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(otm.image_handoff.__file__)), run_name="__main__")
    assert result.value.code == 0
    assert "image_handoff_sha256" in capsys.readouterr().out
