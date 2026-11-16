"""Release orchestration tests use synthetic API/scanner evidence and never publish images."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "build_release", SCRIPTS / "build_application_release.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = SCRIPTS.parent


# Restore CLI umask changes so unrelated permission tests retain their intended fixture modes.
@pytest.fixture(autouse=True)
def preserve_umask():
    previous = os.umask(0o077)
    os.umask(previous)
    try:
        yield
    finally:
        os.umask(previous)


# Zeroed explicit file metadata prevents local owner/time changes and private workspace inclusion.
def test_deployment_bundle_is_deterministic_and_public(tmp_path, monkeypatch):
    first, schema_hash = MODULE.deployment_source()
    assert MODULE.deployment_source() == (first, schema_hash)
    with tarfile.open(fileobj=io.BytesIO(first)) as archive:
        assert set(archive.getnames()) == {*MODULE.BUNDLE_FILES, "application-settings.schema.json"}
        assert all(item.mode == 0o444 and item.uid == 0 and item.mtime == 0 for item in archive)
        schema = json.load(archive.extractfile("application-settings.schema.json"))
        assert schema["title"] == "ApplicationSettings"
    assert len(schema_hash) == 64


# Scanner and SBOM writes are synthetic; every command remains observable without Docker/network.
def scan_fixture(tmp_path, monkeypatch, *, role="application", fault=None):
    findings = [{"VulnerabilityID": "CVE-2099-0001"}] if fault == "vulnerable" else []
    results = [
        {"Class": "os-pkgs", "Type": "alpine", "Vulnerabilities": findings},
        {"Class": "lang-pkgs", "Type": "python-pkg", "Vulnerabilities": []},
    ]
    if fault == "missing_os":
        results.pop(0)
    elif fault == "missing_language":
        results.pop()
    elif fault == "malformed":
        results[0]["Vulnerabilities"] = {}
    elif fault == "nonlist":
        results = {}
    elif fault == "none":
        results = [None]
    if role == "caddy":
        policy = json.loads((ROOT / "tools/caddy/security-exceptions.json").read_text())
        results[1].update(
            {
                "Type": "gobinary",
                "Target": "usr/bin/caddy",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": entry["id"],
                        "PkgName": entry["package"],
                        "InstalledVersion": entry["version"],
                        "Severity": entry["severity"],
                    }
                    for entry in policy["exceptions"]
                ],
            }
        )
        if fault == "caddy_blocked":
            results[1]["Vulnerabilities"][0]["Severity"] = "CRITICAL"
    (tmp_path / (role + "-scan.json")).write_text(json.dumps({"Results": results}))
    sbom = {"bomFormat": "CycloneDX", "components": [{"name": "synthetic"}]}
    if fault == "sbom":
        sbom["components"] = []
    (tmp_path / (role + ".cdx.json")).write_text(json.dumps(sbom))
    runner = Mock(return_value="")
    monkeypatch.setattr(MODULE, "command", runner)
    return runner


# Both scan coverage dimensions and complete inventories are required on the actual release bytes.
@pytest.mark.parametrize(
    "fault",
    [None, "missing_os", "missing_language", "malformed", "nonlist", "none", "vulnerable", "sbom"],
)
def test_application_scanning_is_fail_closed(tmp_path, monkeypatch, fault):
    runner = scan_fixture(tmp_path, monkeypatch, fault=fault)
    if fault:
        with pytest.raises(ValueError, match="RELEASE_(SCAN|IMAGE|SBOM)"):
            MODULE.scan_image("example/image:synthetic", tmp_path, "application")
    else:
        fingerprint, accepted = MODULE.scan_image(
            "example/image:synthetic", tmp_path, "application"
        )
        assert len(fingerprint) == 64 and accepted == ()
        assert not any("--ignore-unfixed" in call.args[0] for call in runner.call_args_list)


# Only the narrow owner-approved Caddy findings can pass, with their identifiers retained.
@pytest.mark.parametrize("fault", [None, "caddy_blocked"])
def test_caddy_scan_exception_scope(tmp_path, monkeypatch, fault):
    scan_fixture(tmp_path, monkeypatch, role="caddy", fault=fault)
    if fault:
        with pytest.raises(ValueError, match="RELEASE_IMAGE_VULNERABILITIES"):
            MODULE.scan_image("example/caddy:synthetic", tmp_path, "caddy")
    else:
        assert len(MODULE.scan_image("example/caddy:synthetic", tmp_path, "caddy")[1]) == 2


# The helper never supplies shell=True, ignores exit status or leaks captured command output.
def test_bounded_commands_fail_without_raw_output(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b" synthetic ", b""))
    monkeypatch.setattr(MODULE.subprocess, "run", run)
    assert MODULE.command(["docker", "version"]) == "synthetic"
    assert run.call_args.kwargs["timeout"] == 600
    assert "shell" not in run.call_args.kwargs
    run.return_value = subprocess.CompletedProcess([], 1, b"untrusted-output", b"details")
    with pytest.raises(ValueError, match="^RELEASE_COMMAND_FAILED$"):
        MODULE.command(["docker", "version"])


# API transport uses verified TLS and a bounded read; fake tokens never reach a network.
def test_github_transport_is_fixed_and_verified(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "synthetic-token")
    opener = Mock(return_value=io.BytesIO(b'{"id":1}'))
    monkeypatch.setattr(MODULE.urllib.request, "urlopen", opener)
    assert MODULE.github_json("/repos/example/atlas/actions/runs/1") == {"id": 1}
    assert opener.call_args.args[0].full_url.startswith("https://api.github.com/repos/")
    assert opener.call_args.kwargs["context"].check_hostname is True
    assert opener.call_args.kwargs["timeout"] == 25


# A publishing job cannot be triggered by PR artifacts or upload its private output directory.
def test_workflow_trust_permissions_and_allowlisted_artifacts():
    workflow = yaml.safe_load((ROOT / ".github/workflows/build-application.yml").read_text())
    assert set(workflow[True]) == {"workflow_run"}
    job = workflow["jobs"]["release"]
    assert job["runs-on"] == "ubuntu-24.04-arm"
    for guard in (
        "conclusion == 'success'",
        "event == 'push'",
        "head_repository.full_name",
        "head_sha == github.sha",
    ):
        assert guard in job["if"]
    assert job["permissions"] == {
        "contents": "read",
        "actions": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
    }
    uploads = [
        step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    paths = uploads[0]["with"]["path"].splitlines()
    assert {Path(path).name for path in paths} == {
        "release.json",
        "deployment-source.tar",
        "application.cdx.json",
        "caddy.cdx.json",
    }
    assert all("*" not in path for path in paths)
    assert sum(step.get("uses", "").startswith("actions/attest@") for step in job["steps"]) == 5
    assert all(
        step["with"]["create-storage-record"] is False
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/attest@")
    )
    assert "environment" not in job
    assert workflow["concurrency"]["cancel-in-progress"] is False


# The complete synthetic API response is reusable without trusting the triggering event's verdict.
def release_environment(tmp_path, monkeypatch):
    repository, source = "example/atlas", "a" * 40
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"workflow_run": {"id": 1, "head_sha": source}}))
    for key, value in {
        "GITHUB_REPOSITORY": repository,
        "GITHUB_SHA": source,
        "GITHUB_RUN_ID": "2",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
    }.items():
        monkeypatch.setenv(key, value)
    names = [
        "Backend unit coverage",
        "Frontend unit coverage",
        "PostgreSQL and Playwright",
        "Security and publication",
        "Documentation and contracts",
    ]
    run = {
        "id": 1,
        "repository": {"full_name": repository},
        "head_repository": {"full_name": repository},
        "head_sha": source,
        "head_branch": "master",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/checkpoint.yml",
    }
    jobs = {
        "total_count": 5,
        "jobs": [{"name": name, "status": "completed", "conclusion": "success"} for name in names],
    }
    return run, jobs


# API run identity and triggering SHA must match; malformed environment cannot select a URL path.
@pytest.mark.parametrize("fault", [None, "repository", "source", "id", "trigger_sha", "api_id"])
def test_authorization_fetches_independent_evidence(tmp_path, monkeypatch, fault):
    run, jobs = release_environment(tmp_path, monkeypatch)
    if fault == "repository":
        monkeypatch.setenv("GITHUB_REPOSITORY", "../other")
    elif fault == "source":
        monkeypatch.setenv("GITHUB_SHA", "not-a-commit")
    elif fault == "api_id":
        run["id"] = 2
    elif fault in {"id", "trigger_sha"}:
        event = json.loads((tmp_path / "event.json").read_text())
        event["workflow_run"]["id" if fault == "id" else "head_sha"] = (
            True if fault == "id" else "b" * 40
        )
        (tmp_path / "event.json").write_text(json.dumps(event))
    api = Mock(side_effect=[run, jobs])
    monkeypatch.setattr(MODULE, "github_json", api)
    if fault:
        with pytest.raises(ValueError, match="RELEASE_"):
            MODULE.authorize()
    else:
        assert MODULE.authorize() == 1
        assert api.call_count == 2
        assert api.call_args.args[0].endswith("/jobs?filter=latest&per_page=100")


# Two successful scans lead to two builds/pushes; failures cannot write a complete descriptor.
@pytest.mark.parametrize("fault", [None, "architecture", "scan", "registry", "contract"])
def test_build_once_and_failure_boundaries(tmp_path, monkeypatch, fault):
    release_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(MODULE, "check_latest", lambda: "v2.11.9")
    monkeypatch.setattr(MODULE, "export_source", lambda output, source: ROOT)
    calls = []
    metadata = {
        "schema_revision": MODULE.ScriptDirectory.from_config(
            MODULE.migration_configuration()
        ).get_current_head(),
        "settings_schema_sha256": MODULE.deployment_source()[1],
    }
    monkeypatch.setattr(
        MODULE, "installed_contract", lambda tag: {} if fault == "contract" else metadata
    )

    # Each synthetic Docker result supplies only the minimum evidence for the next boundary.
    def docker(arguments):
        calls.append(arguments)
        if "{{.Os}}/{{.Architecture}}" in arguments:
            return "linux/amd64" if fault == "architecture" else "linux/arm64"
        if "{{json .RepoDigests}}" in arguments:
            name = arguments[-1].rsplit(":", 1)[0]
            return json.dumps([] if fault == "registry" else [name + "@sha256:" + "b" * 64])
        return ""

    # A failed actual-image scan stops before publishing that image.
    def scan(tag, output, role):
        if fault == "scan":
            raise ValueError("RELEASE_IMAGE_VULNERABILITIES")
        return "c" * 64, ()

    monkeypatch.setattr(MODULE, "command", docker)
    monkeypatch.setattr(MODULE, "scan_image", scan)
    output = tmp_path / "release"
    if fault:
        with pytest.raises(ValueError, match="RELEASE_"):
            MODULE.build(output, 1)
        assert not (output / "release.json").exists()
        if fault in {"architecture", "scan", "contract"}:
            assert not any(arguments[1] == "push" for arguments in calls)
    else:
        assert MODULE.build(output, 1) == "aaaaaaaaaaaa-2-1"
        assert sum(arguments[1] == "build" for arguments in calls) == 2
        assert sum(arguments[1] == "push" for arguments in calls) == 2
        item = MODULE.ReleaseCandidate.model_validate_json((output / "release.json").read_bytes())
        assert item.source_sha == "a" * 40 and item.platform == "linux/arm64"
        assert item.deployment_source_sha256 == MODULE.digest(
            (output / "deployment-source.tar").read_bytes()
        )
        assert "application_digest=sha256:" in (tmp_path / "outputs").read_text()


# CLI rejection reveals no token/raw API response and never continues to a publisher.
def test_cli_rejection_and_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["release", "--output", str(tmp_path / "release")])
    publisher = Mock(return_value="synthetic-release-id")
    monkeypatch.setattr(MODULE, "build", publisher)
    monkeypatch.setattr(MODULE, "authorize", Mock(side_effect=ValueError("private-detail")))
    assert MODULE.main() == 1 and publisher.call_count == 0
    assert capsys.readouterr().out == "APPLICATION_RELEASE_REJECTED\n"
    monkeypatch.setattr(MODULE, "authorize", lambda: 1)
    assert MODULE.main() == 0 and publisher.call_count == 1


# Use real Git in a disposable repository to prove untracked private files never enter source.
def test_committed_export_excludes_local_files(tmp_path, monkeypatch):
    repo, output = tmp_path / "repo", tmp_path / "output"
    repo.mkdir()
    output.mkdir()

    # Only fixed commands in this owned throwaway repository may create its synthetic commit.
    def git(arguments):
        return subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True).stdout

    git(["init"])
    (repo / "public.txt").write_text("synthetic public source")
    git(["add", "public.txt"])
    git(
        [
            "-c",
            "user.name=Synthetic Fixture",
            "-c",
            "user.email=fixture@example.test",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Synthetic source",
        ]
    )
    (repo / "private.txt").write_text("synthetic untracked canary")
    source = git(["rev-parse", "HEAD"]).decode().strip()
    monkeypatch.setattr(MODULE, "command", lambda arguments: git(arguments[1:]))
    context = MODULE.export_source(output, source)
    assert {path.name for path in context.iterdir()} == {"public.txt"}


# Metadata comes from the exact installed image under a networkless, credentialless invocation.
def test_installed_contract_probe_is_inert(monkeypatch):
    runner = Mock(return_value='{"schema_revision":"synthetic","settings_schema_sha256":"example"}')
    monkeypatch.setattr(MODULE, "command", runner)
    assert MODULE.installed_contract("example/image:synthetic")["schema_revision"] == "synthetic"
    arguments = runner.call_args.args[0]
    assert arguments[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "--read-only" in arguments and "--env" not in arguments
    assert "/opt/venv/bin/python" in arguments
