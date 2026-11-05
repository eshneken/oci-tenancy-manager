"""Inspect the exact proposed Git tree without printing private values or following symlinks."""

import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAILBOX = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@([A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63})"
)
PRIVATE_HOME = re.compile(r"(?:/Users/|/home/)[A-Za-z0-9._-]+/")
PRIVATE_PARTS = {".local-dev", ".venv", "node_modules", ".gstack", "design-evidence"}


# Allow reserved documentation domains only; production contacts belong in private runtime data.
def synthetic_domain(domain: str) -> bool:
    return domain.lower() in {
        "example.com",
        "example.org",
        "example.net",
    } or domain.lower().endswith(
        (
            ".test",
            ".example",
            ".invalid",
            ".localhost",
            ".example.com",
            ".example.org",
            ".example.net",
        )
    )


# Include force-added ignored files as well as every nonignored untracked file, NUL-safely.
def candidates(root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root
    )
    return sorted({Path(item.decode()) for item in output.split(b"\0") if item})


# Return location/rule identifiers only: errors must never echo the private matched content.
def inspect_file(root: Path, relative: Path, assets: dict[str, str]) -> list[str]:
    label = relative.as_posix()
    if relative.is_absolute() or ".." in relative.parts:
        return ["candidate:unsafe-path"]
    path = root / relative
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
        return [f"{label}:symlink"]
    if (
        PRIVATE_PARTS.intersection(relative.parts)
        or relative.parts[0] == "reference"
        or (relative.name.startswith(".env") and relative.name != ".env.example")
    ):
        return [f"{label}:private-runtime-path"]
    if (
        relative.as_posix().startswith(("prototype/evidence/", "prototype/data/"))
        and relative.as_posix() != "prototype/data/README.md"
    ):
        return [f"{label}:private-input-or-evidence"]
    if relative.suffix.lower() in {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".dump",
        ".backup",
        ".sqlite",
        ".sqlite3",
        ".db",
    }:
        return [f"{label}:credential-or-export-file"]
    try:
        content = path.read_bytes()
    except OSError:
        return [f"{label}:unreadable-candidate"]
    findings = []
    reviewed_types = {
        ".csv",
        ".png",
        ".jpg",
        ".jpeg",
        ".ico",
        ".webp",
        ".svg",
        ".excalidraw",
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        ".zip",
        ".gz",
        ".tar",
    }
    if (relative.suffix.lower() in reviewed_types or b"\x00" in content) and (
        assets.get(label) != hashlib.sha256(content).hexdigest()
    ):
        findings.append(f"{label}:unreviewed-data-or-visual-asset")
    if relative.suffix.lower() == ".csv":
        try:
            rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), strict=True))
            if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
                findings.append(f"{label}:malformed-csv")
        except (UnicodeError, csv.Error):
            findings.append(f"{label}:malformed-csv")
        if assets.get(label) != hashlib.sha256(content).hexdigest():
            findings.append(f"{label}:unreviewed-data-asset")
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        if assets.get(label) != hashlib.sha256(content).hexdigest():
            findings.append(f"{label}:unreviewed-binary-asset")
        return findings
    for number, line in enumerate(text.splitlines(), 1):
        # The bundled third-party license retains legally required upstream attribution.
        if label != "backend/migrations/sql/procrastinate-LICENSE.md" and any(
            not synthetic_domain(match[1]) for match in MAILBOX.finditer(line) if "@" in line
        ):
            findings.append(f"{label}:{number}:non-synthetic-email")
        if PRIVATE_HOME.search(line) or ("file:" + "///") in line:
            findings.append(f"{label}:{number}:private-machine-path")
    return findings


# Apply a reviewed asset manifest to the full tree, independently of credential scanning.
def check(root: Path) -> list[str]:
    manifest = json.loads((root / "scripts/publication-assets.json").read_text())
    assets = manifest["assets"]
    return [finding for path in candidates(root) for finding in inspect_file(root, path, assets)]


# Fail closed on unreadable inputs; never turn a scanner error into publication approval.
def main() -> int:
    try:
        findings = check(ROOT)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        print("Publication inspection failed: invalid input or Git inventory.")
        return 1
    for finding in findings:
        print(finding)
    print(json.dumps({"status": "fail" if findings else "pass", "findings": len(findings)}))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
