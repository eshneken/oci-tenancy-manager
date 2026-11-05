"""Publication regressions use synthetic secrets and disposable local Git inventories."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/publication_guard.py"
spec = importlib.util.spec_from_file_location("publication_guard", SCRIPT)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


# Exercise HTML/JSON leaks, malformed data, credential paths and safe diagnostics.
@pytest.mark.parametrize(
    "name,content,rule",
    [
        ("sample.html", "<p>sample@" + "private-corp.invalidorg</p>", "non-synthetic-email"),
        (
            "sample.json",
            json.dumps({"path": "/home/" + "private-person/project"}),
            "private-machine-path",
        ),
        ("sample.csv", "a,b\n1\n", "malformed-csv"),
        ("sample.png", b"\x89PNG\xff", "unreviewed-binary-asset"),
        ("credential.pem", "synthetic", "credential-or-export-file"),
        ("export.sqlite", b"SQLite format 3\x00", "credential-or-export-file"),
        ("unreviewed.pdf", "%PDF synthetic text", "unreviewed-data-or-visual-asset"),
        ("unreviewed.xlsx", "readable synthetic data", "unreviewed-data-or-visual-asset"),
        ("unreviewed.json", b"data\x00", "unreviewed-data-or-visual-asset"),
        ("prototype/evidence/report.md", "private", "private-input-or-evidence"),
        ("prototype/data/source.json", "{}", "private-input-or-evidence"),
        (".local-dev/export.json", "{}", "private-runtime-path"),
    ],
)
def test_private_candidates_fail_without_echoing_values(tmp_path, name, content, rule):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    findings = guard.inspect_file(tmp_path, Path(name), {})
    assert any(rule in item for item in findings)
    assert all("private-person" not in item and "private-corp" not in item for item in findings)


# A reviewed synthetic CSV passes while any modified data requires new review.
def test_reviewed_asset_hash_and_reserved_domains(tmp_path):
    content = b"name,email\nExample,user@example.test\n"
    (tmp_path / "fixture.csv").write_bytes(content)
    assets = {"fixture.csv": guard.hashlib.sha256(content).hexdigest()}
    assert guard.inspect_file(tmp_path, Path("fixture.csv"), assets) == []
    assert guard.inspect_file(tmp_path, Path("fixture.csv"), {})
    assert guard.synthetic_domain("sub.example.org")
    assert not guard.synthetic_domain("example.org.attacker.invalidorg")


# Symlinks and parent traversal cannot read outside the candidate tree.
def test_links_and_parent_traversal_are_rejected(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path / "not-read")
    assert guard.inspect_file(tmp_path, Path("link"), {}) == ["link:symlink"]
    assert guard.inspect_file(tmp_path, Path("../outside"), {}) == ["candidate:unsafe-path"]


# Force-added ignored inputs remain visible to the gate, including paths with spaces.
def test_git_inventory_includes_forced_ignored_and_untracked(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".local-dev/\n")
    private = tmp_path / ".local-dev"
    private.mkdir()
    (private / "feed.csv").write_text("a,b\n1,2\n")
    (tmp_path / "space name.md").write_text("Synthetic documentation")
    subprocess.run(["git", "add", "-f", ".local-dev/feed.csv"], cwd=tmp_path, check=True)
    paths = guard.candidates(tmp_path)
    assert Path(".local-dev/feed.csv") in paths
    assert Path("space name.md") in paths
    assert guard.inspect_file(tmp_path, Path(".local-dev/feed.csv"), {})
