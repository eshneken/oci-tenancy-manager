"""Build and qualify a local image using only owned disposable containers and synthetic inputs."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path, PurePosixPath
from uuid import uuid4

from docker_test_resources import remove_owned
from psycopg import sql
from sqlalchemy.engine import make_url

from otm.local_development import database_url, docker, read_state, setup
from otm.maintenance import maintenance_engine

ROOT = Path(__file__).resolve().parents[1]


# Read the one digest-pinned upstream scanner dependency that Dependabot can update natively.
def scanner_image(manifest):
    lines = [
        line.strip()
        for line in manifest.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(lines) != 1:
        raise ValueError("INVALID_SCANNER_MANIFEST")
    match = re.fullmatch(
        r"FROM (aquasec/trivy:[0-9]+[.][0-9]+[.][0-9]+@sha256:[0-9a-f]{64})", lines[0]
    )
    if match is None:
        raise ValueError("INVALID_SCANNER_MANIFEST")
    return match.group(1)


SCANNER = scanner_image(ROOT / "tools/trivy/Dockerfile")


# Read only the regular report emitted inside the scanner's dedicated mount.
def read_scan_report(directory):
    report = directory / "image-scan.json"
    if report.is_symlink() or not report.is_file():
        raise ValueError("IMAGE_SCAN_REPORT_REQUIRED")
    return json.loads(report.read_text())


# Reject asset paths outside their declared source/package trees before reading checkout content.
def expected_assets(root):
    project = tomllib.loads((root / "backend/pyproject.toml").read_text())
    manifest = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    result = {}
    for source, target in manifest.items():
        for value in (source, target):
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or "\\" in value:
                raise ValueError("UNSAFE_PACKAGE_ASSET")
        candidate = (root / "backend" / source).resolve()
        if not candidate.is_relative_to((root / "backend").resolve()):
            raise ValueError("UNSAFE_PACKAGE_ASSET")
        result[target] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if not result:
        raise ValueError("MISSING_PACKAGE_ASSETS")
    return result


# Drop the scratch files in this run's private directory after the scanner is gone.
def remove_scan_inputs(directory):
    try:
        (directory / "image.tar").unlink(missing_ok=True)
    finally:
        try:
            shutil.rmtree(directory / "cache")
        except FileNotFoundError:
            pass


# Test Docker's actual context filtering, including nested canaries, without copying private data.
def context_check(client, directory, command):
    context, output = directory / "context", directory / "filtered"
    context.mkdir()
    shutil.copy2(ROOT / ".dockerignore", context / ".dockerignore")
    allowed = [
        "backend/src/otm/example.py",
        "backend/config/application.toml",
        "frontend/public/branding-assets/example.txt",
    ]
    forbidden = [
        ".env",
        ".git/private",
        ".aws/credentials",
        ".local-dev/feed.csv",
        "prototype/feed.csv",
        "backend/config/private.toml",
        "backend/private.csv",
        "backend/src/private.csv",
        "frontend/private.csv",
        "backend/.venv/private",
        "backend/src/otm/private.pem",
        "frontend/src/.env.local",
        "frontend/public/.local-dev/private.csv",
        "private.csv",
    ]
    for name in allowed + forbidden:
        path = context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic container-context canary\n")
    command(
        [
            client,
            "build",
            "--file",
            "-",
            "--output",
            "type=local,dest=" + str(output),
            str(context),
        ],
        input=b"FROM scratch\nCOPY . /\n",
    )
    if not all((output / name).is_file() for name in allowed):
        raise RuntimeError("REQUIRED_BUILD_INPUT_EXCLUDED")
    if any((output / name).exists() for name in forbidden):
        raise RuntimeError("PRIVATE_BUILD_INPUT_INCLUDED")


# Share a ten-minute Docker-command budget; failures never print credentials or raw Docker logs.
def main():
    os.umask(0o077)
    (ROOT / ".local-dev/quality").mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="container-", dir=ROOT / ".local-dev/quality"))
    owner = uuid4().hex
    image, container = "otm-smoke:" + owner, "otm-container-" + owner
    client = docker()
    deadline = time.monotonic() + 600
    stage = "build-context"
    state = None
    scan = directory / "scan"
    build_attempted = False
    passed = False
    try:
        # Commands own bounded logs; stdin/env carry only synthetic temporary test credentials.
        def command(arguments, *, input=None, env=None, check=True):
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                raise RuntimeError("CONTAINER_COMMAND_BUDGET_EXHAUSTED")
            result = subprocess.run(
                arguments, input=input, env=env, capture_output=True, timeout=remaining, check=False
            )
            with (directory / "commands.log").open("ab") as log:
                log.write(result.stdout + result.stderr)
            if check and result.returncode:
                raise RuntimeError("CONTAINER_COMMAND_FAILED")
            return result

        context_check(client, directory, command)
        stage = "image-build"
        build_attempted = True
        command(
            [
                client,
                "build",
                "--pull",
                "--no-cache",
                "--label",
                "otm.container.smoke=" + owner,
                "--tag",
                image,
                str(ROOT),
            ]
        )
        stage = "installed-image"
        flags = [
            client,
            "run",
            "--name",
            container,
            "--label",
            "otm.container.smoke=" + owner,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            "none",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
        ]
        result = command(
            flags
            + [
                "--interactive",
                "--mount",
                "type=bind,src="
                + str(ROOT / "scripts/container_probe.py")
                + ",dst=/probe.py,readonly",
                image,
                "python",
                "/probe.py",
            ],
            input=json.dumps(expected_assets(ROOT)).encode(),
        )
        observed = json.loads(result.stdout)
        if observed.get("status") != "pass":
            raise RuntimeError("CONTAINER_PROBE_FAILED")
        remove_owned(client, container, "otm.container.smoke", owner)
        stage = "explicit-configuration"
        # The default full API cannot silently invent credentials or use the saved laptop profile.
        result = command(flags + [image], check=False)
        if result.returncode == 0 or b"KeyError: 'OTM_APPLICATION_CONFIG'" not in result.stderr:
            raise RuntimeError("UNCONFIGURED_API_GUARD_NOT_VERIFIED")
        remove_owned(client, container, "otm.container.smoke", owner)
        stage = "disposable-database"
        root = directory / "application"
        try:
            setup(ROOT, root)
        finally:
            # Capture the disposable identity before running any image probes or scanner.
            if (root / "state.json").is_file():
                state = read_state(root)
        name = "otm-local-" + state.instance_id.hex[:12]
        # Housekeeping uses a dedicated least-privilege login, never the API or database owner.
        engine = maintenance_engine(database_url(state, owner=True), None)
        try:
            with engine.begin() as connection:
                connection.connection.driver_connection.execute(
                    sql.SQL("CREATE ROLE otm_container_sweeper LOGIN PASSWORD {}").format(
                        sql.Literal(state.api_password.get_secret_value())
                    )
                )
                connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_container_sweeper")
                connection.exec_driver_sql(
                    "GRANT SELECT(id,expires_at,last_seen_at,idle_timeout_seconds,revoked_at), "
                    "UPDATE(id), DELETE ON public.otm_admin_session TO otm_container_sweeper"
                )
        finally:
            engine.dispose()
        environment = {
            **os.environ,
            "OTM_DATABASE_URL": make_url(database_url(state))
            .set(port=5432, username="otm_container_sweeper")
            .render_as_string(hide_password=False),
        }
        result = command(
            [
                client,
                "run",
                "--name",
                container,
                "--label",
                "otm.container.smoke=" + owner,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--network",
                "container:" + name,
                "--env",
                "OTM_DATABASE_URL",
                image,
                "otm-maintenance",
                "cleanup-sessions",
                "--config",
                "/opt/venv/lib/python3.12/site-packages/otm_settings/application.toml",
            ],
            env=environment,
        )
        if json.loads(result.stdout) != {"deleted": 0, "batches": 1, "batch_limit_reached": False}:
            raise RuntimeError("CONTAINER_DATABASE_PROBE_FAILED")
        remove_owned(client, container, "otm.container.smoke", owner)
        stage = "native-runtime"
        environment.update(
            OTM_DATABASE_URL=make_url(database_url(state))
            .set(port=5432)
            .render_as_string(hide_password=False),
            OTM_WORKER_DATABASE_URL=make_url(database_url(state, worker=True))
            .set(port=5432)
            .render_as_string(hide_password=False),
        )
        result = command(
            [
                client,
                "run",
                "--name",
                container,
                "--label",
                "otm.container.smoke=" + owner,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=128m",
                "--network",
                "container:" + name,
                "--env",
                "OTM_DATABASE_URL",
                "--env",
                "OTM_WORKER_DATABASE_URL",
                "--mount",
                "type=bind,src="
                + str(ROOT / "scripts/container_runtime_probe.py")
                + ",dst=/runtime_probe.py,readonly",
                image,
                "python",
                "/runtime_probe.py",
            ],
            env=environment,
        )
        if json.loads(result.stdout).get("status") != "pass":
            raise RuntimeError("NATIVE_RUNTIME_PROBE_FAILED")
        remove_owned(client, container, "otm.container.smoke", owner)
        stage = "image-security"
        # Give the scanner write access only to its own inputs and outputs.
        scan.mkdir()
        archive = scan / "image.tar"
        command([client, "save", "--output", str(archive), image])
        command(
            [
                client,
                "run",
                "--name",
                container,
                "--label",
                "otm.container.smoke=" + owner,
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:mode=1777",
                "--mount",
                "type=bind,src=" + str(scan) + ",dst=/scan",
                SCANNER,
                "image",
                "--cache-dir",
                "/scan/cache",
                "--scanners",
                "vuln",
                "--severity",
                "HIGH,CRITICAL",
                "--format",
                "json",
                "--output",
                "/scan/image-scan.json",
                "--exit-code",
                "1",
                "--input",
                "/scan/image.tar",
            ]
        )
        report = read_scan_report(scan)
        targets = {item.get("Class") for item in report.get("Results", [])}
        if not {"os-pkgs", "lang-pkgs"}.issubset(targets):
            raise RuntimeError("IMAGE_SCAN_COVERAGE_MISSING")
        passed = True
    except Exception:
        pass
    finally:
        scanner_stopped = False
        try:
            remove_owned(client, container, "otm.container.smoke", owner)
            scanner_stopped = True
        except Exception:
            stage, passed = "cleanup", False
        # Setup can leave an owned database even if provisioning failed.
        try:
            if state is not None:
                remove_owned(
                    client,
                    "otm-local-" + state.instance_id.hex[:12],
                    "otm.local.instance",
                    str(state.instance_id),
                )
        except Exception:
            stage, passed = "cleanup", False
        try:
            if build_attempted:
                remove_owned(client, image, "otm.container.smoke", owner, kind="image")
        except Exception:
            stage, passed = "cleanup", False
        if scanner_stopped:
            try:
                remove_scan_inputs(scan)
            except OSError:
                stage, passed = "cleanup", False
    result = {
        "status": "pass" if passed else "fail",
        "stage": "complete" if passed else stage,
        "artifacts": str(directory.relative_to(ROOT)),
        "saved_instance_used": False,
    }
    (directory / "summary.json").write_text(json.dumps(result) + "\n")
    print(json.dumps(result))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
