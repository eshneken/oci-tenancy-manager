"""Check local documentation links against the publishable Git inventory, never private files."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from publication_guard import candidates


# Reproduce GitHub heading IDs, including duplicate suffixes, for Markdown destinations.
def anchors(path: Path) -> set[str]:
    result = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+)$", path.read_text(), re.MULTILINE):
        slug = re.sub(r"\s", "-", re.sub(r"[^\w\- ]", "", heading.lower()))
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(slug if count == 0 else f"{slug}-{count}")
    return result


# Require each referenced local asset to belong to the proposed tree, not merely exist locally.
def check_links(root: Path) -> tuple[list[Path], int, list[str]]:
    inventory = {path.as_posix() for path in candidates(root)}
    documents = sorted(root / path for path in inventory if path.endswith((".md", ".html")))
    errors = []
    links = 0
    for file in documents:
        text = file.read_text()
        if file.suffix == ".md":
            targets = re.findall(r"!?\[[^\]]+\]\(([^)]+)\)", text)
        else:
            targets = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', text)
        for target in targets:
            target = target.strip("<>")
            parsed = urlsplit(target)
            if (
                parsed.scheme
                or parsed.netloc
                or target.startswith(("data:", "javascript:"))
                or (file.suffix == ".html" and target.startswith("/"))
            ):
                continue
            destination = (file.parent / unquote(parsed.path)).resolve() if parsed.path else file
            try:
                relative = destination.relative_to(root.resolve()).as_posix()
            except ValueError:
                errors.append(f"{file.relative_to(root)}: outside-tree link")
                continue
            links += 1
            if relative not in inventory and not any(
                item.startswith(relative.rstrip("/") + "/") for item in inventory
            ):
                errors.append(f"{file.relative_to(root)}: unpublished/missing {target}")
            elif (
                parsed.fragment
                and destination.suffix == ".md"
                and destination.is_file()
                and unquote(parsed.fragment) not in anchors(destination)
            ):
                errors.append(f"{file.relative_to(root)}: missing anchor {target}")
    return documents, links, errors


# Keep the user-facing documentation table of contents aligned with published sections.
def check_index(root: Path) -> list[str]:
    inventory = {p.as_posix() for p in candidates(root)}
    sections = {
        p.split("/")[1] for p in inventory if p.startswith("docs/") and len(p.split("/")) > 2
    }
    index = root / "docs/README.md"
    if not index.is_file():
        return ["docs/README.md: required documentation table of contents missing"]
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", index.read_text())
    included = {
        urlsplit(target.strip("<>")).path.removeprefix("./").split("/")[0] for target in targets
    }
    return [f"docs/README.md: missing section {section}" for section in sorted(sections - included)]
