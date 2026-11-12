"""Boundary checks for disposable image qualification and its destructive cleanup guards."""

import importlib.util
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr

SPEC = importlib.util.spec_from_file_location(
    "container_smoke", Path(__file__).resolve().parents[2] / "scripts/run_container_smoke.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


# Reject traversal on either side of the installed-asset hash manifest.
@pytest.mark.parametrize(
    "source,target",
    [("../private", "asset"), ("asset", "../private"), ("/private", "asset"), ("asset", "a\\b")],
)
def test_asset_manifest_rejects_escape(tmp_path, source, target):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        "[tool.hatch.build.targets.wheel.force-include]\n"
        + json.dumps(source)
        + " = "
        + json.dumps(target)
        + "\n"
    )
    with pytest.raises(ValueError, match="UNSAFE_PACKAGE_ASSET"):
        MODULE.expected_assets(tmp_path)


# Refuse cleanup of a container with another owner's label even when its name matches.
def test_cleanup_requires_exact_ownership(monkeypatch):
    calls = []

    # Return a foreign container; any second call would represent unauthorized destruction.
    def run(arguments, **kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(
            arguments, 0, json.dumps([{"Config": {"Labels": {"owner": "foreign"}}}]), ""
        )

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    with pytest.raises(ValueError, match="OWNERSHIP_MISMATCH"):
        MODULE.remove_owned("docker", "candidate", "owner", "expected")
    assert len(calls) == 1


# A Docker daemon failure must not be mistaken for successful removal of an absent resource.
def test_cleanup_does_not_hide_daemon_failure(monkeypatch):
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "daemon unavailable"),
    )
    with pytest.raises(RuntimeError, match="INSPECTION_FAILED"):
        MODULE.remove_owned("docker", "candidate", "owner", "expected")


# Verify real repository assets can be hashed without borrowing private files or editable imports.
def test_actual_asset_manifest():
    assets = MODULE.expected_assets(MODULE.ROOT)
    assert "otm_settings/application.toml" in assets
    assert "otm_migrations/alembic.ini" in assets
    assert all(len(value) == 64 for value in assets.values())


# Reject a source symlink that would admit a private file outside the declared backend tree.
def test_asset_manifest_rejects_symlink(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (tmp_path / "private.txt").write_text("synthetic private canary")
    (backend / "asset").symlink_to(tmp_path / "private.txt")
    (backend / "pyproject.toml").write_text(
        '[tool.hatch.build.targets.wheel.force-include]\n"asset" = "package/asset"\n'
    )
    with pytest.raises(ValueError, match="UNSAFE_PACKAGE_ASSET"):
        MODULE.expected_assets(tmp_path)


# Remove only the exact owned resource and keep every destructive subprocess bounded.
def test_cleanup_removes_owned_container(monkeypatch):
    calls = []

    # Supply the matching ownership proof, then record the exact requested removal.
    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(
            arguments, 0, json.dumps([{"Config": {"Labels": {"owner": "expected"}}}]), ""
        )

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    MODULE.remove_owned("docker", "candidate", "owner", "expected")
    assert calls[1][0] == ["docker", "rm", "--force", "candidate"]
    assert all(call[1]["timeout"] == 30 for call in calls)


# An already absent owned test name is harmless and must not trigger a removal command.
def test_cleanup_tolerates_missing_container(monkeypatch):
    calls = []

    # Mimic Docker's specific not-found result without converting general failures into success.
    def run(arguments, **kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 1, "[]", "error: no such object: candidate")

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    MODULE.remove_owned("docker", "candidate", "owner", "expected")
    assert len(calls) == 1


# Keep Docker, database credentials and filesystem observations inside one synthetic boundary.
@pytest.fixture
def smoke_boundary(tmp_path, monkeypatch):
    original_umask = MODULE.os.umask(0o077)
    MODULE.os.umask(original_umask)

    # Execute the real orchestrator while external tools supply controlled protocol outcomes.
    def exercise(fault):
        project = tmp_path / fault
        backend = project / "backend"
        backend.mkdir(parents=True)
        (project / ".dockerignore").write_text("**\n")
        (backend / "asset").write_text("synthetic packaged asset\n")
        manifest = '[tool.hatch.build.targets.wheel.force-include]\n"asset" = "package/asset"\n'
        if fault == "empty_manifest":
            manifest = "[tool.hatch.build.targets.wheel.force-include]\n"
        elif fault == "missing_manifest":
            manifest = "[project]\nname = 'synthetic'\n"
        elif fault == "missing_asset":
            (backend / "asset").unlink()
        (backend / "pyproject.toml").write_text(manifest)
        identity = UUID("00000000-0000-4000-8000-000000000001")
        state = SimpleNamespace(
            instance_id=identity,
            database_port=54321,
            owner_password=SecretStr("synthetic-owner"),
            api_password=SecretStr("synthetic-api"),
            worker_password=SecretStr("synthetic-worker"),
        )
        calls = []
        scanned = False
        connection = SimpleNamespace(
            connection=SimpleNamespace(driver_connection=SimpleNamespace(execute=lambda _: None)),
            exec_driver_sql=lambda _: None,
        )
        engine = SimpleNamespace(begin=lambda: nullcontext(connection), dispose=lambda: None)

        # Persist only an empty canary so real finally logic can find its disposable database.
        def setup(_project, root):
            root.mkdir()
            (root / "state.json").write_text("{}")

        # Model Docker's external result protocol without launching containers or reading host data.
        def run(arguments, **kwargs):
            nonlocal scanned
            calls.append(arguments)
            code, stdout, stderr = 0, b"", b""
            if arguments[1] == "inspect" or arguments[1:3] == ["image", "inspect"]:
                owner = (
                    "foreign"
                    if fault == "foreign_image" and arguments[1] == "image"
                    else identity.hex
                )
                stdout = json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "otm.container.smoke": owner,
                                    "otm.local.instance": str(identity),
                                }
                            }
                        }
                    ]
                ).encode()
            elif arguments[1] == "build" and "--output" in arguments:
                if fault == "command_timeout":
                    raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])
                output = Path(arguments[arguments.index("--output") + 1].split("dest=", 1)[1])
                for name in (
                    "backend/src/otm/example.py",
                    "backend/config/application.toml",
                    "frontend/public/branding-assets/example.txt",
                ):
                    path = output / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("synthetic filtered input")
            elif arguments[1] == "run":
                if MODULE.SCANNER in arguments:
                    scanned = True
                    report = {"Results": [{"Class": "os-pkgs"}, {"Class": "lang-pkgs"}]}
                    if fault == "missing_os":
                        report["Results"] = [{"Class": "lang-pkgs"}]
                    elif fault == "missing_language":
                        report["Results"] = [{"Class": "os-pkgs"}]
                    directory = next((project / ".local-dev/quality").glob("container-*"))
                    if fault != "missing_report":
                        (directory / "image-scan.json").write_text(
                            "invalid json" if fault == "malformed_report" else json.dumps(report)
                        )
                    code = 1 if fault == "scanner_exit" else 0
                elif "/probe.py" in arguments or "/runtime_probe.py" in arguments:
                    failed = (fault == "installed_probe" and "/probe.py" in arguments) or (
                        fault == "native_probe" and "/runtime_probe.py" in arguments
                    )
                    stdout = json.dumps({"status": "fail" if failed else "pass"}).encode()
                elif "cleanup-sessions" in arguments:
                    stdout = b'{"deleted":0,"batches":1,"batch_limit_reached":false}'
                else:
                    code, stderr = 1, b"KeyError: 'OTM_APPLICATION_CONFIG'"
            elif arguments[1] == "rm" and scanned and fault == "cleanup_failure":
                raise subprocess.CalledProcessError(1, arguments)
            if kwargs.get("text"):
                stdout, stderr = stdout.decode(), stderr.decode()
            return subprocess.CompletedProcess(arguments, code, stdout, stderr)

        monkeypatch.setattr(MODULE, "ROOT", project)
        monkeypatch.setattr(MODULE, "uuid4", lambda: identity)
        monkeypatch.setattr(MODULE, "docker", lambda: "synthetic-docker")
        monkeypatch.setattr(MODULE, "setup", setup)
        monkeypatch.setattr(MODULE, "read_state", lambda _: state)
        monkeypatch.setattr(MODULE, "maintenance_engine", lambda *_: engine)
        monkeypatch.setattr(MODULE.subprocess, "run", run)
        if fault == "budget_expired":
            clock = iter((0, 601))
            monkeypatch.setattr(MODULE, "time", SimpleNamespace(monotonic=lambda: next(clock, 601)))
        result = MODULE.main()
        directory = next((project / ".local-dev/quality").glob("container-*"))
        summary = json.loads((directory / "summary.json").read_text())
        assert result == 1 and summary["status"] == "fail"
        assert summary["saved_instance_used"] is False
        assert any(command[1] == "inspect" for command in calls)
        return summary, calls

    try:
        yield exercise
    finally:
        MODULE.os.umask(original_umask)


# Value: protects=missing assets fail qualification; fails_when=empty or unavailable assets pass;
# why_new=existing manifest tests cover valid/escaping paths; seam=none;
# no_claim=Docker and database are synthetic external boundaries, not installed-image proof.
@pytest.mark.parametrize("fault", ["empty_manifest", "missing_manifest", "missing_asset"])
def test_qualification_rejects_unavailable_assets(smoke_boundary, fault):
    summary, calls = smoke_boundary(fault)
    assert summary["stage"] == "installed-image"
    assert not any(MODULE.SCANNER in command for command in calls)


# Value: protects=scan failures and incomplete evidence cannot qualify an image;
# fails_when=failed or absent scans become green;
# why_new=real scan exercises only successful verdict;
# seam=none; no_claim=controlled scanner responses do not establish real advisory detection.
@pytest.mark.parametrize(
    "fault",
    ["scanner_exit", "missing_report", "malformed_report", "missing_os", "missing_language"],
)
def test_qualification_rejects_failed_or_incomplete_scan(smoke_boundary, fault):
    summary, calls = smoke_boundary(fault)
    assert summary["stage"] == "image-security"
    assert any(MODULE.SCANNER in command for command in calls)
    assert any(command[1:3] == ["image", "rm"] for command in calls)


# Value: protects=non-pass installed/native probes block qualification;
# fails_when=probe rejection is ignored; why_new=actual probes currently execute their passing path;
# seam=none; no_claim=synthetic tool results do not verify runtime compatibility.
@pytest.mark.parametrize(
    "fault,stage", [("installed_probe", "installed-image"), ("native_probe", "native-runtime")]
)
def test_qualification_rejects_nonpass_probe(smoke_boundary, fault, stage):
    summary, calls = smoke_boundary(fault)
    assert summary["stage"] == stage
    assert not any(MODULE.SCANNER in command for command in calls)


# Value: protects=expired budgets and command timeouts fail and attempt owned cleanup;
# fails_when=timeout is swallowed into success;
# why_new=successful Docker smoke never expires its budget;
# seam=none; no_claim=clock and subprocess boundaries are synthetic, not Docker timing proof.
@pytest.mark.parametrize("fault", ["budget_expired", "command_timeout"])
def test_qualification_rejects_command_expiry(smoke_boundary, fault):
    summary, calls = smoke_boundary(fault)
    assert summary["stage"] == "build-context"
    assert not any("--tag" in command for command in calls)


# Value: protects=cleanup failure or foreign image ownership prevents a passing verdict;
# fails_when=successful probes override failed cleanup;
# why_new=helper ownership tests omit main verdict;
# seam=none; no_claim=owned labels and tool failures are synthetic; no real resource is removed.
@pytest.mark.parametrize("fault", ["cleanup_failure", "foreign_image"])
def test_qualification_rejects_cleanup_failure(smoke_boundary, fault):
    summary, calls = smoke_boundary(fault)
    assert summary["stage"] == "cleanup"
    assert any(MODULE.SCANNER in command for command in calls)
    assert not any(command[1:3] == ["image", "rm"] for command in calls)
