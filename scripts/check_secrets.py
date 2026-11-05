"""Scan Git candidates without local environments, secrets or private evidence."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from publication_guard import candidates

ROOT = Path(__file__).resolve().parents[1]


# A temporary projection makes credential scanning match the files that would be published.
def main() -> int:
    tool = ROOT / ".local-dev/tools/gitleaks/8.30.1/gitleaks"
    if not tool.is_file():
        print("Install the pinned security tool with scripts/install_security_tools.py first.")
        return 1
    with tempfile.TemporaryDirectory(prefix="otm-secret-candidates-") as directory:
        projection = Path(directory) / "tree"
        projection.mkdir()
        report = Path(directory) / "report.json"
        paths = candidates(ROOT)
        for relative in paths:
            source = ROOT / relative
            if source.is_symlink() or relative.is_absolute() or ".." in relative.parts:
                print("Unsafe Git candidate: scan refused.")
                return 1
            destination = projection / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        result = subprocess.run(
            [
                str(tool),
                "dir",
                str(projection),
                "--redact",
                "--no-banner",
                "--config",
                str(ROOT / ".gitleaks.toml"),
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ],
            check=False,
        )
        # Report actionable locations without disclosing matched lines, secrets or context.
        if result.returncode and report.is_file():
            for finding in json.loads(report.read_text()):
                location = Path(finding["File"]).relative_to(projection)
                print(f"{location}:{finding['StartLine']}:{finding['RuleID']}")
        print(f"Credential scan inspected {len(paths)} Git candidates; exit={result.returncode}.")
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
