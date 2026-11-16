"""Build/scan/publish one native ARM64 candidate; no OCI access or deployment authority."""

import argparse
import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import tarfile
import urllib.request
from pathlib import Path

import certifi
from alembic.script import ScriptDirectory
from caddy_image_policy import check_latest, evaluate
from run_container_smoke import SCANNER

from otm.artifact_release import (
    BUNDLE_FILES,
    ReleaseCandidate,
    ReleaseImage,
    validate_checkpoint,
)
from otm.hosted_database import migration_configuration
from otm.settings import ApplicationSettings

ROOT = Path(__file__).resolve().parents[1]


# Standard SHA256 is shared by bundle/SBOM identities; no private file is passed to this helper.
def digest(data):
    return hashlib.sha256(data).hexdigest()


# Zeroed archive metadata makes deployment source independent of local timestamps and ownership.
def deployment_source(root=ROOT):
    schema = json.dumps(
        ApplicationSettings.model_json_schema(), sort_keys=True
    ).encode()
    files = {name: (root / name).read_bytes() for name in BUNDLE_FILES}
    files["application-settings.schema.json"] = schema
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o444
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue(), digest(schema)


# Only a fixed GitHub API endpoint and token from Actions are used; never accept arbitrary URLs.
def github_json(path):
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "User-Agent": "otm-release-build",
        },
    )
    with urllib.request.urlopen(
        request, context=ssl.create_default_context(cafile=certifi.where()), timeout=25
    ) as response:
        return json.loads(response.read(2097152))


# Require trusted push evidence from the current master SHA; never consume PR/cache artifacts.
def authorize():
    repository, source = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    if (
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,38}/[a-z0-9][a-z0-9._-]{0,99}", repository)
        is None
    ):
        raise ValueError("RELEASE_REPOSITORY_INVALID")
    if re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise ValueError("RELEASE_SOURCE_INVALID")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    trigger = event["workflow_run"]
    run_id = trigger["id"]
    if type(run_id) is not int or run_id < 1:
        raise ValueError("RELEASE_RUN_INVALID")
    run = github_json(f"/repos/{repository}/actions/runs/{run_id}")
    jobs = github_json(
        f"/repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
    )
    if run["id"] != run_id or trigger["head_sha"] != source:
        raise ValueError("RELEASE_TRIGGER_MISMATCH")
    return validate_checkpoint(run, jobs, repository=repository, source_sha=source)


# Fixed argv only; errors have a bounded stage label rather than raw subprocess/environment output.
def command(arguments):
    result = subprocess.run(arguments, capture_output=True, check=False, timeout=600)
    if result.returncode:
        raise ValueError("RELEASE_COMMAND_FAILED")
    return result.stdout.decode().strip()


# Scan exact local bytes; Caddy has narrow exceptions, while the app has none.
def scan_image(tag, output, role):
    archive = output / (role + ".tar")
    command(["docker", "save", "--output", str(archive), tag])
    base = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:mode=1777",
        "--mount",
        f"type=bind,src={output},dst=/scan",
        SCANNER,
        "image",
        "--cache-dir",
        "/scan/cache",
        "--input",
        f"/scan/{role}.tar",
    ]
    command(
        [
            *base,
            "--scanners",
            "vuln",
            "--severity",
            "HIGH,CRITICAL",
            "--format",
            "json",
            "--output",
            f"/scan/{role}-scan.json",
            "--exit-code",
            "0",
        ]
    )
    report = json.loads((output / (role + "-scan.json")).read_text())
    results = report.get("Results")
    if (
        not isinstance(results, list)
        or any(not isinstance(result, dict) for result in results)
        or not {"os-pkgs", "lang-pkgs"}.issubset(
            {result.get("Class") for result in results}
        )
    ):
        raise ValueError("RELEASE_SCAN_COVERAGE_REQUIRED")
    for result in results:
        findings = result.get("Vulnerabilities")
        if findings is not None and (
            not isinstance(findings, list)
            or any(not isinstance(item, dict) for item in findings)
        ):
            raise ValueError("RELEASE_SCAN_FINDINGS_INVALID")
    if role == "caddy":
        policy = evaluate(report)
        if policy["blocked"]:
            raise ValueError("RELEASE_IMAGE_VULNERABILITIES")
        accepted = tuple(sorted({entry["id"] for entry in policy["accepted"]}))
    else:
        if any(result.get("Vulnerabilities") for result in results):
            raise ValueError("RELEASE_IMAGE_VULNERABILITIES")
        accepted = ()
    sbom = output / (role + ".cdx.json")
    command([*base, "--format", "cyclonedx", "--output", "/scan/" + sbom.name])
    inventory = json.loads(sbom.read_text())
    if inventory.get("bomFormat") != "CycloneDX" or not inventory.get("components"):
        raise ValueError("RELEASE_SBOM_REQUIRED")
    return digest(sbom.read_bytes()), accepted


# A committed archive excludes local/untracked files before Docker's additional deny-default filter.
def export_source(output, source):
    archive_path = output / "committed-source.tar"
    command(["git", "archive", "--format=tar", "--output", str(archive_path), source])
    context = output / "source"
    context.mkdir()
    with tarfile.open(archive_path) as archive:
        archive.extractall(context, filter="data")
    return context


# Probe the installed package without networking, credentials, a database or a listening server.
def installed_contract(tag):
    code = (
        "import hashlib,json; from alembic.script import ScriptDirectory; "
        "from otm.hosted_database import migration_configuration; "
        "from otm.settings import ApplicationSettings; "
        "print(json.dumps({'schema_revision':ScriptDirectory.from_config("
        "migration_configuration()).get_current_head(),'settings_schema_sha256':hashlib.sha256("
        "json.dumps(ApplicationSettings.model_json_schema(),sort_keys=True).encode()).hexdigest()}))"
    )
    return json.loads(
        command(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                tag,
                "/opt/venv/bin/python",
                "-c",
                code,
            ]
        )
    )


# Build once locally, scan those bytes, then push and bind their immutable registry digests.
def build(output, checkpoint):
    check_latest()
    repository = os.environ["GITHUB_REPOSITORY"]
    source = os.environ["GITHUB_SHA"]
    run_id, attempt = (
        int(os.environ["GITHUB_RUN_ID"]),
        int(os.environ["GITHUB_RUN_ATTEMPT"]),
    )
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    source_root = export_source(output, source)
    bundle, settings_hash = deployment_source(source_root)
    (output / "deployment-source.tar").write_bytes(bundle)
    identities, accepted = {}, ()
    expected_contract = {
        "schema_revision": ScriptDirectory.from_config(
            migration_configuration()
        ).get_current_head(),
        "settings_schema_sha256": settings_hash,
    }
    for role, context, dockerfile, suffix in (
        ("application", ".", "Dockerfile", ""),
        ("caddy", "tools/caddy", "tools/caddy/Dockerfile", "-caddy"),
    ):
        name = "ghcr.io/" + repository + suffix
        tag = f"{name}:build-{run_id}-{attempt}"
        command(
            [
                "docker",
                "build",
                "--pull",
                "--platform",
                "linux/arm64",
                "--label",
                "org.opencontainers.image.source=https://github.com/" + repository,
                "--label",
                "org.opencontainers.image.revision=" + source,
                "--file",
                str(source_root / dockerfile),
                "--tag",
                tag,
                str(source_root / context),
            ]
        )
        architecture = command(
            ["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", tag]
        )
        if architecture != "linux/arm64":
            raise ValueError("RELEASE_ARM64_REQUIRED")
        if role == "application" and installed_contract(tag) != expected_contract:
            raise ValueError("RELEASE_INSTALLED_CONTRACT_MISMATCH")
        sbom_hash, findings = scan_image(tag, output, role)
        if role == "caddy":
            accepted = findings
        # Scan before publishing; a later failure leaves no complete candidate.
        command(["docker", "push", tag])
        references = json.loads(
            command(
                ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag]
            )
        )
        matching = [
            ref.removeprefix(name + "@")
            for ref in references
            if ref.startswith(name + "@")
        ]
        if len(matching) != 1:
            raise ValueError("RELEASE_REGISTRY_DIGEST_REQUIRED")
        identities[role] = ReleaseImage(
            repository=name, digest=matching[0], sbom_sha256=sbom_hash
        )
    candidate = ReleaseCandidate(
        repository=repository,
        source_sha=source,
        checkpoint_run_id=checkpoint,
        build_run_id=run_id,
        build_attempt=attempt,
        application=identities["application"],
        caddy=identities["caddy"],
        deployment_source_sha256=digest(bundle),
        schema_revision=expected_contract["schema_revision"],
        settings_schema_sha256=settings_hash,
        accepted_caddy_cves=accepted,
    )
    (output / "release.json").write_bytes(candidate.canonical_bytes())
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        for role in ("application", "caddy"):
            stream.write(f"{role}_name={identities[role].repository}\n")
            stream.write(f"{role}_digest={identities[role].digest}\n")
        stream.write("release_id=" + candidate.release_id + "\n")
    return candidate.release_id


# No caller supplies a successful Checkpoint ID: Actions evidence is fetched and checked first.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    os.umask(0o077)
    try:
        checkpoint = authorize()
        print(build(options.output.resolve(), checkpoint))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("APPLICATION_RELEASE_REJECTED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
