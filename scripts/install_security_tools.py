"""Install the pinned Gitleaks release into ignored local tooling, without shell installers."""

import hashlib
import io
import json
import platform
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Verify the archive against both the pinned digest and official checksum manifest.
def main() -> None:
    metadata = json.loads((ROOT / "scripts/security-tools.json").read_text())["gitleaks"]
    architecture = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}.get(
        platform.machine().lower(), "unsupported"
    )
    target = platform.system().lower() + "_" + architecture
    if target not in metadata["assets"]:
        raise SystemExit("No pinned Gitleaks asset for this platform")
    asset = metadata["assets"][target]
    with urllib.request.urlopen(metadata["checksums_url"], timeout=60) as response:
        checksums = response.read().decode("utf-8")
    matches = [
        line.split()[0] for line in checksums.splitlines() if line.split()[-1:] == [asset["asset"]]
    ]
    if matches != [asset["sha256"]]:
        raise SystemExit("Official checksum manifest differs from the reviewed tool pin")
    with urllib.request.urlopen(asset["url"], timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != asset["sha256"]:
        raise SystemExit("Gitleaks archive checksum verification failed")
    # Extract only the named regular executable: never unpack arbitrary archive paths or symlinks.
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = [entry for entry in bundle.getmembers() if entry.name == "gitleaks"]
        if len(members) != 1 or not members[0].isfile():
            raise SystemExit("Release archive lacks the expected regular executable")
        executable = bundle.extractfile(members[0])
        if executable is None:
            raise SystemExit("Cannot read release executable")
        binary = executable.read()
    directory = ROOT / ".local-dev/tools/gitleaks" / metadata["version"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gitleaks"
    path.write_bytes(binary)
    path.chmod(0o700)
    subprocess.run([str(path), "version"], check=True)
    provenance = {
        "version": metadata["version"],
        "asset_url": asset["url"],
        "archive_sha256": asset["sha256"],
        "executable_sha256": hashlib.sha256(binary).hexdigest(),
        "checksums_url": metadata["checksums_url"],
    }
    (directory / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Installed verified local tool: " + str(path.relative_to(ROOT)))


if __name__ == "__main__":
    main()
