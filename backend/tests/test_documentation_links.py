"""Documentation checks must validate the publishable tree and its maintained section index."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/documentation_links.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("documentation_links", SCRIPT)
assert spec is not None and spec.loader is not None
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


# A private file existing locally cannot satisfy a link in a public README.
def test_links_require_candidate_membership_and_include_image_assets(tmp_path):
    (tmp_path / "README.md").write_text("[private](private.md)\n![image](image.png)\n")
    (tmp_path / "private.md").write_text("# Private")
    with patch.object(links, "candidates", return_value=[Path("README.md")]):
        _, count, errors = links.check_links(tmp_path)
    assert count == 2 and len(errors) == 2
    assert any("private.md" in item for item in errors)
    assert any("image.png" in item for item in errors)


# HTML assets, percent-decoded names and duplicate Markdown headings resolve correctly.
def test_html_assets_and_duplicate_anchors(tmp_path):
    (tmp_path / "README.md").write_text("# Same\n# Same\n[duplicate](#same-1)\n")
    (tmp_path / "page.html").write_text('<img src="image%20one.png"><a href="/app">App</a>')
    (tmp_path / "image one.png").write_bytes(b"synthetic")
    with patch.object(
        links,
        "candidates",
        return_value=[Path(p) for p in ["README.md", "page.html", "image one.png"]],
    ):
        _, count, errors = links.check_links(tmp_path)
    assert count == 2 and errors == []


# Every published documentation section must be reachable from the top-level table of contents.
def test_index_covers_new_sections(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("[How-to](how-to/README.md)")
    inventory = [Path(p) for p in ["docs/README.md", "docs/how-to/README.md", "docs/new/page.md"]]
    with patch.object(links, "candidates", return_value=inventory):
        assert links.check_index(tmp_path) == ["docs/README.md: missing section new"]
        (docs / "README.md").write_text("[How-to](how-to/README.md)\n[New](new/)")
        assert links.check_index(tmp_path) == []
