"""Read-only release verification using GitHub's standard cryptographic attestation verifier."""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat

# Standard CLI execution uses fixed argv without a shell or credential arguments.
import subprocess  # nosec B404
import tarfile
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

from otm.artifact_release import BUNDLE_FILES, ReleaseCandidate, Repository, validate_checkpoint

PROVENANCE = "https://slsa.dev/provenance/v1"
SBOM = "https://cyclonedx.org/bom"
BUILD_WORKFLOW = ".github/workflows/build-application.yml"
RELEASE_FILES = ("release.json", "deployment-source.tar", "application.cdx.json", "caddy.cdx.json")
# Read/parsed inputs and CLI responses are capped at 16 MiB; subprocess output first uses disk.
MAX_BYTES = 16 * 1024 * 1024


# Standard hashes identify public bytes without including their contents in output.
def sha256(data):
    return hashlib.sha256(data).hexdigest()


# Duplicate JSON keys are ambiguous at a signature/metadata boundary and fail closed.
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("RELEASE_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


# Use identical strict JSON parsing for local files and trusted CLI response structures.
def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_object)


# Read one regular file without following a final-component symlink or blocking on a FIFO.
def read_public_file(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("RELEASE_REGULAR_FILE_REQUIRED")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("RELEASE_INPUT_TOO_LARGE")
    return data


# Allow only public deployment-source members; links, duplicates and PAX headers are rejected.
def validate_source(data, candidate):
    if sha256(data) != candidate.deployment_source_sha256:
        raise ValueError("RELEASE_SOURCE_HASH_MISMATCH")
    expected = {*BUNDLE_FILES, "application-settings.schema.json"}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive:
            if (
                member.name not in expected
                or member.name in seen
                or not member.isfile()
                or member.pax_headers
                or member.size > MAX_BYTES
            ):
                raise ValueError("RELEASE_SOURCE_MEMBERS_INVALID")
            seen.add(member.name)
            if member.name == "application-settings.schema.json":
                schema = archive.extractfile(member).read(MAX_BYTES + 1)
                if sha256(schema) != candidate.settings_schema_sha256:
                    raise ValueError("RELEASE_SETTINGS_HASH_MISMATCH")
                if not isinstance(parse_json(schema), dict):
                    raise ValueError("RELEASE_SETTINGS_SCHEMA_INVALID")
    if seen != expected:
        raise ValueError("RELEASE_SOURCE_MEMBERS_INVALID")


# Authenticate publication metadata before downloading anything from the selected GitHub run.
def validate_publishing_run(run, *, repository, run_id):
    source, attempt = run.get("head_sha"), run.get("run_attempt")
    if (
        type(run_id) is not int
        or run_id < 1
        or run.get("id") != run_id
        or type(run.get("id")) is not int
        or type(attempt) is not int
        or attempt < 1
        or not isinstance(source, str)
        or re.fullmatch(r"[0-9a-f]{40}", source) is None
        or run.get("repository", {}).get("full_name") != repository
        or run.get("head_repository", {}).get("full_name") != repository
        or run.get("head_branch") != "master"
        or run.get("event") != "workflow_run"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("path") != BUILD_WORKFLOW
    ):
        raise ValueError("RELEASE_BUILD_UNTRUSTED")
    return source, attempt


# Bind the independently authenticated attempt to the exact descriptor being verified.
def validate_build(run, candidate, *, repository, run_id):
    source, attempt = validate_publishing_run(run, repository=repository, run_id=run_id)
    if (
        candidate.repository != repository
        or candidate.build_run_id != run_id
        or attempt != candidate.build_attempt
        or source != candidate.source_sha
    ):
        raise ValueError("RELEASE_BUILD_UNTRUSTED")


# Enforce exact run/attempt and subject on already cryptographically verified GitHub CLI output.
# This helper never authenticates caller-provided JSON; only verify_release supplies its input.
def validate_attestation(results, candidate, *, digest, predicate_type, inventory=None):
    invocation = (
        f"https://github.com/{candidate.repository}/actions/runs/{candidate.build_run_id}"
        f"/attempts/{candidate.build_attempt}"
    )
    if not isinstance(results, list) or not results:
        raise ValueError("RELEASE_ATTESTATION_REQUIRED")
    for entry in results:
        verified = entry.get("verificationResult", {})
        certificate = verified.get("signature", {}).get("certificate", {})
        statement = verified.get("statement", {})
        if (
            certificate.get("runInvocationURI") == invocation
            and statement.get("predicateType") == predicate_type
            and any(
                subject.get("digest") == {"sha256": digest}
                for subject in statement.get("subject", [])
            )
            and (inventory is None or statement.get("predicate") == inventory)
        ):
            return
    raise ValueError("RELEASE_ATTESTATION_SCOPE_MISMATCH")


# Fixed argv with bounded time and private captured output; never print raw CLI/network diagnostics.
def gh(arguments):
    executable = shutil.which("gh")
    if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
        raise ValueError("RELEASE_GITHUB_CLI_UNAVAILABLE")
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        # Only internal validated argv reaches this absolute CLI; no shell or raw diagnostics.
        result = subprocess.run(  # nosec B603
            [executable, *arguments],
            stdout=output,
            stderr=errors,
            timeout=120,
            check=False,
            shell=False,
        )
        if result.returncode:
            raise ValueError("RELEASE_GITHUB_VERIFICATION_FAILED")
        output.seek(0)
        data = output.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("RELEASE_GITHUB_RESPONSE_TOO_LARGE")
    return data


# Require patched native verification/download behavior before consuming any remote artifact.
def require_github_cli():
    version = re.match(rb"gh version (\d+)\.(\d+)\.(\d+)\b", gh(["--version"]))
    if not version or tuple(map(int, version.groups())) < (2, 102, 0):
        raise ValueError("RELEASE_GITHUB_CLI_UPGRADE_REQUIRED")


# Download only the exact successful run/attempt artifact into a fresh private disposable directory.
# Native gh handles extraction; no downloaded code is executed and all four files are reverified.
def verify_run(*, repository, run_id):
    repository = TypeAdapter(Repository).validate_python(repository)
    if type(run_id) is not int or run_id < 1:
        raise ValueError("RELEASE_RUN_INVALID")
    require_github_cli()
    run = parse_json(
        gh(["api", "--hostname", "github.com", f"/repos/{repository}/actions/runs/{run_id}"])
    )
    source, attempt = validate_publishing_run(run, repository=repository, run_id=run_id)
    name = f"application-release-{source[:12]}-{run_id}-{attempt}"
    with tempfile.TemporaryDirectory(prefix="otm-download-release-") as work:
        gh(
            [
                "run",
                "download",
                str(run_id),
                "--repo",
                "github.com/" + repository,
                "--name",
                name,
                "--dir",
                work,
            ]
        )
        report = verify_release(work, repository=repository, run_id=run_id)
        if report["source_sha"] != source or report["build_attempt"] != attempt:
            raise ValueError("RELEASE_DOWNLOAD_BINDING_MISMATCH")
        return report


# Online GitHub API identity and standard Sigstore checks precede any successful integrity report.
def verify_release(directory, *, repository, run_id):
    repository = TypeAdapter(Repository).validate_python(repository)
    if type(run_id) is not int or run_id < 1:
        raise ValueError("RELEASE_RUN_INVALID")
    require_github_cli()
    directory = Path(directory)
    if {path.name for path in directory.iterdir()} != set(RELEASE_FILES):
        raise ValueError("RELEASE_PUBLIC_FILES_REQUIRED")
    # Freeze the public bytes once; verification must not reread a changing downloaded directory.
    files = {name: read_public_file(directory / name) for name in RELEASE_FILES}
    parse_json(files["release.json"])  # Check duplicate keys before strict JSON-mode tuple parsing.
    candidate = ReleaseCandidate.model_validate_json(files["release.json"])
    if files["release.json"] != candidate.canonical_bytes():
        raise ValueError("RELEASE_DESCRIPTOR_NOT_CANONICAL")
    base = f"/repos/{repository}/actions/runs/"
    # Preserve immutable publishing attempts; Checkpoint retains the existing latest-success gate.
    run = parse_json(
        gh(
            [
                "api",
                "--hostname",
                "github.com",
                base + str(run_id) + "/attempts/" + str(candidate.build_attempt),
            ]
        )
    )
    validate_build(run, candidate, repository=repository, run_id=run_id)
    checkpoint = parse_json(
        gh(["api", "--hostname", "github.com", base + str(candidate.checkpoint_run_id)])
    )
    jobs = parse_json(
        gh(
            [
                "api",
                "--hostname",
                "github.com",
                base + str(candidate.checkpoint_run_id) + "/jobs?filter=latest&per_page=100",
            ]
        )
    )
    if (
        validate_checkpoint(
            checkpoint, jobs, repository=repository, source_sha=candidate.source_sha
        )
        != candidate.checkpoint_run_id
    ):
        raise ValueError("RELEASE_CHECKPOINT_ID_MISMATCH")
    validate_source(files["deployment-source.tar"], candidate)
    inventories = {}
    for role in ("application", "caddy"):
        image = getattr(candidate, role)
        content = files[role + ".cdx.json"]
        inventory = parse_json(content)
        components = inventory.get("components") if isinstance(inventory, dict) else None
        if (
            not isinstance(inventory, dict)
            or sha256(content) != image.sbom_sha256
            or inventory.get("bomFormat") != "CycloneDX"
            or not isinstance(components, list)
            or not components
            or any(not isinstance(component, dict) for component in components)
        ):
            raise ValueError("RELEASE_SBOM_MISMATCH")
        inventories[role] = inventory
    # gh authenticates the repository, exact workflow/ref/SHA and GitHub-hosted runner.
    # Private copies bind verification to parsed bytes without executing archive contents.
    with tempfile.TemporaryDirectory(prefix="otm-verify-release-") as work:
        subjects = []
        for name in ("release.json", "deployment-source.tar"):
            path = Path(work) / name
            path.write_bytes(files[name])
            subjects.append((str(path), sha256(files[name]), PROVENANCE, None))
        for role in ("application", "caddy"):
            image = getattr(candidate, role)
            uri = "oci://" + image.repository + "@" + image.digest
            subjects.extend(
                (
                    (uri, image.digest[7:], PROVENANCE, None),
                    (uri, image.digest[7:], SBOM, inventories[role]),
                )
            )
        for subject, digest, predicate, inventory in subjects:
            result = parse_json(
                gh(
                    [
                        "attestation",
                        "verify",
                        subject,
                        "--hostname",
                        "github.com",
                        "--repo",
                        repository,
                        "--signer-workflow",
                        repository + "/" + BUILD_WORKFLOW,
                        "--signer-digest",
                        candidate.source_sha,
                        "--source-digest",
                        candidate.source_sha,
                        "--source-ref",
                        "refs/heads/master",
                        "--deny-self-hosted-runners",
                        "--predicate-type",
                        predicate,
                        "--format",
                        "json",
                    ]
                )
            )
            validate_attestation(
                result, candidate, digest=digest, predicate_type=predicate, inventory=inventory
            )
    return {
        "status": "integrity_verified",
        "release_id": candidate.release_id,
        "fingerprint": candidate.fingerprint,
        "repository": repository,
        "source_sha": candidate.source_sha,
        "build_run_id": run_id,
        "build_attempt": candidate.build_attempt,
        "staging_acceptance": "not_evaluated",
        "deployment": "not_performed",
    }


# Require public files and independently selected repository/run; never accept a pass flag.
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify release provenance without deploying or granting staging acceptance."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--directory", type=Path, help="Verify four already-downloaded public files")
    mode.add_argument(
        "--download",
        action="store_true",
        help="Download and verify the run’s current successful publishing attempt",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    arguments = parser.parse_args(argv)
    try:
        report = (
            verify_run(repository=arguments.repository, run_id=arguments.run_id)
            if arguments.download
            else verify_release(
                arguments.directory, repository=arguments.repository, run_id=arguments.run_id
            )
        )
    except (
        ValueError,
        OSError,
        TypeError,
        KeyError,
        AttributeError,
        tarfile.TarError,
        subprocess.SubprocessError,
        RecursionError,
    ):
        print(
            json.dumps(
                {
                    "status": "fail",
                    "code": "RELEASE_VERIFICATION_FAILED",
                    "guidance": (
                        "Check public files, successful build identity, GitHub/registry access "
                        "and gh version; no unsigned fallback is permitted."
                    ),
                }
            )
        )
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0
