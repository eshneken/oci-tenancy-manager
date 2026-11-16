"""Synthetic trust-boundary cases never contact GitHub, a registry or OCI."""

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest
from test_artifact_release import candidate, checkpoint

from otm import release_verification as verify
from otm.artifact_release import BUNDLE_FILES, ReleaseCandidate


# Build a bounded public release with reproducible hashes and no real deployment/employee data.
def release_files(tmp_path):
    schema = b'{"title":"SyntheticSettings"}'
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in (*BUNDLE_FILES, "application-settings.schema.json"):
            content = schema if name.endswith(".schema.json") else b"synthetic public source"
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    bundle = stream.getvalue()
    inventory = {"bomFormat": "CycloneDX", "components": [{"name": "synthetic"}]}
    sbom = json.dumps(inventory).encode()
    raw = candidate().model_dump()
    raw.update(
        deployment_source_sha256=verify.sha256(bundle), settings_schema_sha256=verify.sha256(schema)
    )
    for role in ("application", "caddy"):
        raw[role]["sbom_sha256"] = verify.sha256(sbom)
    item = ReleaseCandidate.model_validate(raw)
    files = {
        "release.json": item.canonical_bytes(),
        "deployment-source.tar": bundle,
        "application.cdx.json": sbom,
        "caddy.cdx.json": sbom,
    }
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    return item, inventory, files


# Emulate only output from a successful gh cryptographic verifier, with exact signed run identity.
def attestation(item, digest, predicate, inventory=None):
    return [
        {
            "verificationResult": {
                "signature": {
                    "certificate": {
                        "runInvocationURI": f"https://github.com/{item.repository}/actions/runs/{item.build_run_id}/attempts/{item.build_attempt}"
                    }
                },
                "statement": {
                    "subject": [{"digest": {"sha256": digest}}],
                    "predicateType": predicate,
                    "predicate": inventory or {"buildDefinition": {}},
                },
            }
        }
    ]


# Observe every trusted CLI call; substitution exists only in tests, never the runtime interface.
def github_fixture(tmp_path, monkeypatch):
    item, inventory, files = release_files(tmp_path)
    run, jobs = checkpoint()
    build = {
        **run,
        "id": 2,
        "run_attempt": 1,
        "event": "workflow_run",
        "path": verify.BUILD_WORKFLOW,
    }
    calls = []

    # Supply independent build/checkpoint metadata and exact subject-specific verified statements.
    def fake(arguments):
        calls.append(arguments)
        if arguments == ["--version"]:
            return b"gh version 2.104.0 (2026-11-12)\n"
        if arguments[0] == "api":
            return json.dumps(
                jobs
                if "/jobs?" in arguments[-1]
                else build
                if arguments[-1].endswith("/2/attempts/1")
                else run
            ).encode()
        subject = arguments[2]
        predicate = arguments[arguments.index("--predicate-type") + 1]
        digest = (
            item.application.digest[7:]
            if subject.startswith("oci://")
            else verify.sha256(Path(subject).read_bytes())
        )
        return json.dumps(
            attestation(item, digest, predicate, inventory if predicate == verify.SBOM else None)
        ).encode()

    monkeypatch.setattr(verify, "gh", fake)
    return item, inventory, files, calls, build, run, jobs


# End-to-end orchestration binds six standard attestations, with no deployment or acceptance claim.
def test_verified_release_is_integrity_only(tmp_path, monkeypatch):
    item, _, _, calls, *_ = github_fixture(tmp_path, monkeypatch)
    report = verify.verify_release(tmp_path, repository=item.repository, run_id=2)
    assert report == {
        "status": "integrity_verified",
        "release_id": item.release_id,
        "fingerprint": item.fingerprint,
        "repository": item.repository,
        "source_sha": item.source_sha,
        "build_run_id": 2,
        "build_attempt": 1,
        "staging_acceptance": "not_evaluated",
        "deployment": "not_performed",
    }
    checks = [call for call in calls if call[0] == "attestation"]
    assert len(checks) == 6
    for call in checks:
        assert call[call.index("--repo") + 1] == item.repository
        assert (
            call[call.index("--signer-workflow") + 1]
            == item.repository + "/" + verify.BUILD_WORKFLOW
        )
        assert call[call.index("--source-digest") + 1] == item.source_sha
        assert call[call.index("--signer-digest") + 1] == item.source_sha
        assert call[call.index("--source-ref") + 1] == "refs/heads/master"
        assert "--deny-self-hosted-runners" in call
        assert "--bundle" not in call and "--bundle-from-oci" not in call


# Forks, unrelated workflows, attempts and nonterminal publications cannot supply candidates.
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 3),
        ("id", True),
        ("run_attempt", 2),
        ("run_attempt", True),
        ("repository", {"full_name": "fork/atlas"}),
        ("head_repository", {"full_name": "fork/atlas"}),
        ("head_sha", "f" * 40),
        ("head_branch", "feature"),
        ("event", "push"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("path", ".github/workflows/untrusted.yml"),
    ],
)
def test_build_substitution_rejected(tmp_path, monkeypatch, field, value):
    item, *_, build, _, _ = github_fixture(tmp_path, monkeypatch)
    build[field] = value
    with pytest.raises(ValueError, match="RELEASE_BUILD_UNTRUSTED"):
        verify.verify_release(tmp_path, repository=item.repository, run_id=2)


# Bind signed statements to the exact run/attempt, subject, predicate and SBOM content.
@pytest.mark.parametrize(
    "fault", ["empty", "mapping", "run", "attempt", "subject", "predicate", "inventory"]
)
def test_wrong_attestation_context_rejected(fault):
    item = candidate()
    inventory = {"bomFormat": "CycloneDX", "components": [{"name": "synthetic"}]}
    result = attestation(item, "b" * 64, verify.SBOM, inventory)
    if fault == "empty":
        result = []
    elif fault == "mapping":
        result = {}
    elif fault in {"run", "attempt"}:
        result[0]["verificationResult"]["signature"]["certificate"]["runInvocationURI"] += "/wrong"
    elif fault == "subject":
        result[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] = "e" * 64
    elif fault == "predicate":
        result[0]["verificationResult"]["statement"]["predicateType"] = verify.PROVENANCE
    else:
        result[0]["verificationResult"]["statement"]["predicate"] = {}
    with pytest.raises(ValueError, match="RELEASE_ATTESTATION"):
        verify.validate_attestation(
            result, item, digest="b" * 64, predicate_type=verify.SBOM, inventory=inventory
        )


# Metadata, inventory and archive tampering fails before an integrity report is issued.
@pytest.mark.parametrize(
    "fault",
    ["extra", "missing", "symlink", "canonical", "source", "inventory", "sbom_hash", "checkpoint"],
)
def test_public_candidate_tampering_rejected(tmp_path, monkeypatch, fault):
    item, _, files, _, _, run, _ = github_fixture(tmp_path, monkeypatch)
    if fault == "extra":
        (tmp_path / "unexpected.txt").write_text("unexpected")
    elif fault == "missing":
        (tmp_path / "caddy.cdx.json").unlink()
    elif fault == "symlink":
        target = tmp_path / "application.cdx.json"
        target.unlink()
        target.symlink_to(tmp_path / "caddy.cdx.json")
    elif fault == "canonical":
        (tmp_path / "release.json").write_bytes(files["release.json"] + b"\n")
    elif fault == "source":
        (tmp_path / "deployment-source.tar").write_bytes(b"changed")
    elif fault == "inventory":
        (tmp_path / "application.cdx.json").write_text('{"bomFormat":"SPDX"}')
    elif fault == "sbom_hash":
        (tmp_path / "application.cdx.json").write_text(
            '{"bomFormat":"CycloneDX","components":["changed"]}'
        )
    else:
        run["id"] = 3
    with pytest.raises((ValueError, OSError)):
        verify.verify_release(tmp_path, repository=item.repository, run_id=2)


# Empty archives, extra paths, links, duplicate members and altered schemas never reach extraction.
@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "traversal",
        "link",
        "duplicate",
        "oversized",
        "schema_hash",
        "schema_type",
    ],
)
def test_archive_scope_and_schema(tmp_path, fault):
    item, _, _ = release_files(tmp_path)
    output = io.BytesIO()
    schema = b"[]" if fault == "schema_type" else b'{"title":"SyntheticSettings"}'
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        names = list(BUNDLE_FILES) + ["application-settings.schema.json"]
        if fault == "missing":
            names.pop(0)
        elif fault in {"extra", "traversal"}:
            names.append("unexpected" if fault == "extra" else "../unexpected")
        elif fault == "duplicate":
            names.append(names[0])
        for name in names:
            member = tarfile.TarInfo(name)
            content = schema if name.endswith(".schema.json") else b"source"
            if fault == "link" and name == names[0]:
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/untrusted"
                archive.addfile(member)
            elif fault == "oversized" and name == names[0]:
                member.size = verify.MAX_BYTES + 1
                archive.fileobj.write(member.tobuf())
                break
            else:
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
    data = output.getvalue()
    raw = item.model_dump()
    raw["deployment_source_sha256"] = verify.sha256(data)
    if fault == "schema_type":
        raw["settings_schema_sha256"] = verify.sha256(schema)
    elif fault == "schema_hash":
        raw["settings_schema_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="RELEASE_(SOURCE_MEMBERS|SETTINGS)"):
        verify.validate_source(data, ReleaseCandidate.model_validate(raw))


# Repository/run selectors cannot supply option injection, booleans or an unbounded API path.
@pytest.mark.parametrize(
    "repository,run_id",
    [
        ("--evil", 2),
        ("example/..", 2),
        ("example/atlas", 0),
        ("example/atlas", True),
        ("example/atlas", "2"),
    ],
)
def test_invalid_selectors(tmp_path, repository, run_id):
    with pytest.raises(ValueError):
        verify.verify_release(tmp_path, repository=repository, run_id=run_id)


# The ref-case policy fix is mandatory; missing or older CLIs fail rather than weakening flags.
@pytest.mark.parametrize("version", [b"unknown", b"gh version 2.101.0", b"gh version 1.999.0"])
def test_cli_version_gate(tmp_path, monkeypatch, version):
    monkeypatch.setattr(verify, "gh", lambda _: version)
    with pytest.raises(ValueError, match="CLI_UPGRADE_REQUIRED"):
        verify.verify_release(tmp_path, repository="example/atlas", run_id=2)


# Ambiguous keys and oversized/nonregular public files cannot enter metadata processing.
def test_strict_file_and_json_boundaries(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="DUPLICATE_JSON"):
        verify.parse_json('{"id":1,"id":2}')
    target = tmp_path / "public"
    target.write_bytes(b"12345")
    monkeypatch.setattr(verify, "MAX_BYTES", 4)
    with pytest.raises(ValueError, match="TOO_LARGE"):
        verify.read_public_file(target)
    target.unlink()
    os.mkfifo(target)
    with pytest.raises(ValueError, match="REGULAR_FILE"):
        verify.read_public_file(target)


# Only fixed argv reaches gh; failures, excessive output and timeouts expose no raw diagnostics.
@pytest.mark.parametrize("fault", [None, "failure", "oversized", "timeout"])
def test_gh_process_boundary(tmp_path, monkeypatch, fault):
    executable = tmp_path / "gh"
    executable.write_text("synthetic executable; never run")
    executable.chmod(0o700)
    monkeypatch.setattr(verify.shutil, "which", lambda _: str(executable))
    calls = []

    # Substitute the process while retaining real private temporary output handles.
    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        if fault == "timeout":
            raise subprocess.TimeoutExpired(arguments, 120)
        kwargs["stdout"].write(b"12345" if fault == "oversized" else b"{}")
        kwargs["stderr"].write(b"synthetic private diagnostic")
        return subprocess.CompletedProcess(arguments, 1 if fault == "failure" else 0)

    monkeypatch.setattr(verify.subprocess, "run", run)
    monkeypatch.setattr(verify, "MAX_BYTES", 4)
    if fault:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)):
            verify.gh(["--version"])
    else:
        assert verify.gh(["--version"]) == b"{}"
    assert calls[0][0] == [str(executable), "--version"]
    assert calls[0][1]["timeout"] == 120 and calls[0][1]["shell"] is False


# CLI failures have stable nonsecret messages; success remains explicit about missing acceptance.
def test_cli_success_failure_and_no_pass_flag(tmp_path, monkeypatch, capsys):
    item, *_ = github_fixture(tmp_path, monkeypatch)
    arguments = ["--directory", str(tmp_path), "--repository", item.repository, "--run-id", "2"]
    assert verify.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "integrity_verified"
    (tmp_path / "release.json").write_text("not JSON: synthetic confidential diagnostic")
    assert verify.main(arguments) == 1
    result = capsys.readouterr().out
    assert "confidential" not in result and json.loads(result)["status"] == "fail"
    with pytest.raises(SystemExit):
        verify.main([*arguments, "--verified", "true"])


# Even hash-bound inventories must identify CycloneDX and a nonempty list of component objects.
@pytest.mark.parametrize(
    "inventory",
    [
        [],
        {},
        {"bomFormat": "SPDX", "components": [{}]},
        {"bomFormat": "CycloneDX", "components": []},
        {"bomFormat": "CycloneDX", "components": "bad"},
        {"bomFormat": "CycloneDX", "components": ["bad"]},
    ],
)
def test_invalid_bound_sbom_rejected(tmp_path, monkeypatch, inventory):
    item, *_ = github_fixture(tmp_path, monkeypatch)
    data = json.dumps(inventory).encode()
    raw = item.model_dump()
    raw["application"]["sbom_sha256"] = verify.sha256(data)
    updated = ReleaseCandidate.model_validate(raw)
    (tmp_path / "release.json").write_bytes(updated.canonical_bytes())
    (tmp_path / "application.cdx.json").write_bytes(data)
    with pytest.raises(ValueError, match="RELEASE_SBOM_MISMATCH"):
        verify.verify_release(tmp_path, repository=item.repository, run_id=2)


# Missing, relative or nonexistent CLI resolutions fail before any process can run.
@pytest.mark.parametrize("resolved", [None, "./gh", "/no-such-synthetic-tool/gh"])
def test_gh_requires_existing_absolute_binary(monkeypatch, resolved):
    monkeypatch.setattr(verify.shutil, "which", lambda _: resolved)
    with pytest.raises(ValueError, match="RELEASE_GITHUB_CLI_UNAVAILABLE"):
        verify.gh(["--version"])
