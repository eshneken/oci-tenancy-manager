"""Owned laptop setup boundaries with synthetic custody and mocked external processes."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from otm import local_development as local

PROJECT = Path(__file__).resolve().parents[2]


# Keep all test credentials synthetic and confined to temporary owner-only files.
@pytest.fixture
def local_state():
    return local.LocalState(
        instance_id=uuid4(),
        owner_password="synthetic-owner",
        api_password="synthetic-api",
        database_port=54321,
    )


# Persist exact private credentials while masking representations and refusing unsafe custody.
def test_private_state_and_loopback_environment(tmp_path, local_state, monkeypatch):
    local.write_state(tmp_path, local_state)
    assert local.read_state(tmp_path) == local_state
    assert "synthetic-owner" not in repr(local_state)
    monkeypatch.setenv("PGPASSWORD", "untrusted")
    monkeypatch.setenv("OTM_DATABASE_URL", "untrusted")
    assert "PGPASSWORD" not in local.environment(tmp_path, local_state)
    assert "otm_local_api" in local.database_url(local_state)
    assert "otm_owner" in local.environment(tmp_path, local_state, owner=True)["OTM_DATABASE_URL"]
    with pytest.raises(ValueError, match="LOCAL_SETUP_REQUIRED"):
        local.database_url(local_state.model_copy(update={"database_port": None}))
    path = tmp_path / "state.json"
    path.chmod(0o644)
    with pytest.raises(ValueError, match="PRIVATE_LOCAL_STATE_REQUIRED"):
        local.read_state(tmp_path)
    path.chmod(0o600)
    path.write_bytes(b"x" * 16385)
    with pytest.raises(ValueError, match="INVALID_LOCAL_STATE"):
        local.read_state(tmp_path)


# Reject FIFO/link targets without a blocking read or trusting file permission bits alone.
def test_state_rejects_nonregular_and_links(tmp_path):
    import os

    os.mkfifo(tmp_path / "state.json", 0o600)
    with pytest.raises(ValueError, match="PRIVATE_LOCAL_STATE_REQUIRED"):
        local.read_state(tmp_path)
    (tmp_path / "state.json").unlink()
    (tmp_path / "state.json").symlink_to(tmp_path / "absent")
    with pytest.raises(OSError):
        local.read_state(tmp_path)


# Certificate generation remains local, restrictive and idempotent without a trust-root install.
def test_certificate_setup(tmp_path):
    with patch.object(local, "run") as run:
        local.setup_certificate(tmp_path)
        assert "subjectAltName=DNS:localhost,IP:127.0.0.1" in run.call_args.args[0]
        (tmp_path / "tls.key").write_text("synthetic")
        (tmp_path / "tls.crt").write_text("synthetic")
        local.setup_certificate(tmp_path)
        assert run.call_count == 1
        (tmp_path / "tls.key").unlink()
        (tmp_path / "tls.key").symlink_to(tmp_path / "elsewhere")
        with pytest.raises(ValueError):
            local.setup_certificate(tmp_path)


# Setup preserves the original local namespace and human configuration across repeated runs.
def test_setup_idempotent_and_configurable(tmp_path):
    root = tmp_path / "installation"
    with (
        patch.object(local, "setup_database") as database,
        patch.object(local, "setup_certificate"),
    ):
        local.setup(PROJECT, root, 9443)
        first = local.read_state(root)
        config = (root / "application.toml").read_text()
        assert "https://localhost:9443" in config and str(first.instance_id) in config
        local.setup(PROJECT, root)
        assert local.read_state(root) == first
        assert (root / "application.toml").read_text() == config
        assert database.call_count == 2


# Resolve Docker explicitly and keep subprocess diagnostics captured rather than printing secrets.
def test_process_and_docker_helpers():
    with patch.object(local.shutil, "which", return_value="/no-client"):
        with pytest.raises(ValueError, match="DOCKER_REQUIRED"):
            local.docker()
    with patch.object(local.shutil, "which", return_value=__file__):
        assert local.docker() == __file__
    with patch.object(local.subprocess, "run", return_value=Mock()) as process:
        local.run(["safe"])
        assert process.call_args.kwargs["capture_output"] is True


# Model actual inspect/start/readiness outputs while keeping SQL composition in the real adapter.
@pytest.mark.parametrize("existing,role_exists", [(False, False), (True, True)])
def test_owned_database_setup(tmp_path, local_state, existing, role_exists):
    info = {
        "Config": {"Labels": {"otm.local.instance": str(local_state.instance_id)}},
        "State": {"Running": False},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54321"}]}},
    }
    output = SimpleNamespace(stdout=json.dumps([info]), returncode=0)
    inspect = SimpleNamespace(stdout=output.stdout, returncode=0 if existing else 1)
    engine, connection = Mock(), Mock()
    engine.begin.return_value.__enter__ = Mock(return_value=connection)
    engine.begin.return_value.__exit__ = Mock(return_value=False)
    connection.scalar.return_value = 1 if role_exists else None
    with (
        patch.object(local, "docker", return_value="docker"),
        patch.object(
            local.subprocess,
            "run",
            side_effect=[inspect, SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)],
        ),
        patch.object(local, "run", return_value=output) as run,
        patch.object(local, "maintenance_engine", return_value=engine),
        patch.object(local.command, "upgrade") as migrate,
        patch.object(local.time, "sleep"),
        patch("otm.organization.reviews.initialize_existing_reviews"),
    ):
        assert local.setup_database(tmp_path, local_state, PROJECT).database_port == 54321
        migrate.assert_called_once()
        statements = [call.args[0] for call in connection.exec_driver_sql.call_args_list]
        assert "GRANT UPDATE(id) ON public.otm_administrator TO otm_local_worker" in statements
        assert not any("GRANT UPDATE ON public.otm_administrator" in text for text in statements)
        assert connection.connection.driver_connection.execute.call_count == (
            0 if role_exists else 2
        )
        assert engine.dispose.call_count == 1
        assert any("start" in call.args[0] for call in run.call_args_list)


# Never start or migrate an unowned container, exposed DB port, or unavailable database.
@pytest.mark.parametrize("damage", ["label", "port", "ready"])
def test_database_setup_guards(tmp_path, local_state, damage):
    info = {
        "Config": {
            "Labels": {
                "otm.local.instance": str(local_state.instance_id) if damage != "label" else "other"
            }
        },
        "State": {"Running": True},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "54321"}]}},
    }
    output = SimpleNamespace(stdout=json.dumps([info]), returncode=0)
    with (
        patch.object(local, "docker", return_value="docker"),
        patch.object(
            local.subprocess,
            "run",
            side_effect=[output] + [SimpleNamespace(returncode=1 if damage == "ready" else 0)] * 40,
        ),
        patch.object(local, "run", return_value=output),
        patch.object(local.time, "sleep"),
        pytest.raises(ValueError),
    ):
        local.setup_database(tmp_path, local_state, PROJECT)


# Startup passes only the restricted DB credential, while enrollment is an explicit owner command.
@pytest.mark.parametrize("operation", ["setup", "bootstrap", "reset-local", "start"])
def test_local_commands(tmp_path, local_state, monkeypatch, operation):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    local.write_state(root, local_state)
    (root / "mfa").mkdir(mode=0o700)
    (root / "application.toml").write_text(
        (PROJECT / "backend/config/application.toml").read_text()
    )
    monkeypatch.chdir(PROJECT)
    with (
        patch.object(local, "setup") as setup,
        patch.object(local, "run") as run,
        patch.object(local.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as child,
        patch.object(local.os, "execve") as execute,
    ):
        assert local.main([operation, "--directory", str(root)]) == 0
        if operation == "setup":
            setup.assert_called_once()
        elif operation == "start":
            assert run.call_count == 2
            assert "otm_local_api" in execute.call_args.args[2]["OTM_DATABASE_URL"]
            assert "--no-access-log" in execute.call_args.args[1]
        else:
            assert "otm_owner" in child.call_args.kwargs["env"]["OTM_DATABASE_URL"]
            assert operation in child.call_args.args[0]


# Failed setup remains a fixed diagnostic; private provider details never reach terminal output.
@pytest.mark.parametrize(
    "arguments",
    [["setup", "--port", "1"], ["start", "--directory", "relative"], ["private-marker"]],
)
def test_command_errors_sanitized(arguments, capsys, monkeypatch):
    monkeypatch.chdir(PROJECT)
    assert local.main(arguments) == 1
    output = capsys.readouterr().out
    assert "LOCAL_APPLICATION_COMMAND_FAILED" in output and "private-marker" not in output


# Explicit setup upgrades legacy private state without changing owner/API credentials or issuer.
def test_worker_credential_and_launch(tmp_path, local_state, monkeypatch):
    from pydantic import SecretStr

    state = local_state.model_copy(update={"worker_password": SecretStr("synthetic-worker")})
    local.write_state(tmp_path, state)
    assert local.read_state(tmp_path).worker_password.get_secret_value() == "synthetic-worker"
    assert "otm_local_worker" in local.database_url(state, worker=True)
    assert "OTM_MFA_SECRET_DIRECTORY" not in local.environment(tmp_path, state, worker=True)
    with pytest.raises(ValueError):
        local.database_url(local_state, worker=True)
    with pytest.raises(ValueError):
        local.database_url(state, worker=True, owner=True)
    monkeypatch.chdir(PROJECT)
    tmp_path.chmod(0o700)
    with patch.object(local.os, "execve") as execute:
        assert local.main(["worker", "--directory", str(tmp_path)]) == 0
        assert "otm-simulation-worker" in execute.call_args.args[1]
        assert "otm_local_worker" in execute.call_args.args[2]["OTM_DATABASE_URL"]
