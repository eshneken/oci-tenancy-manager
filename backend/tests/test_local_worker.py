"""Local worker process composition, credential separation and queue namespace contracts."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.engine import make_url

from otm import local_worker
from otm.settings import load_settings
from otm.storage.enqueue import workspace_queue

CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"


# Supply explicit environment inputs without creating a database, native pool or human account.
@pytest.fixture
def worker_environment(monkeypatch, tmp_path):
    for key, value in {
        "OTM_APPLICATION_CONFIG": str(CONFIG),
        "OTM_SANDBOX_CONFIG": str(tmp_path / "simulation.json"),
        "OTM_DATABASE_URL": "synthetic",
    }.items():
        monkeypatch.setenv(key, value)
    return load_settings(CONFIG)


# The validated DB target feeds both adapters, and available-work draining never broadens the queue.
@pytest.mark.parametrize("host,once", [("127.0.0.1", False), ("localhost", True)])
def test_worker_composition(worker_environment, host, once):
    engine = Mock(url=make_url("postgresql+psycopg://synthetic:fixture@" + host + ":54321/test"))
    native = Mock()
    with (
        patch.object(local_worker, "load_sandbox"),
        patch.object(local_worker, "maintenance_engine", return_value=engine),
        patch.object(local_worker, "require_runtime_role") as require,
        patch.object(local_worker.procrastinate, "PsycopgConnector") as connector,
        patch.object(local_worker.procrastinate, "App", return_value=native),
        patch.object(local_worker, "register_inspection_task") as register,
        patch.object(local_worker, "register_organization_task") as lifecycle,
        patch("otm.operations.runner.register_presence_task") as presence,
    ):
        local_worker.run_worker(once=once)
        require.assert_called_once_with(engine)
        assert "hostaddr=127.0.0.1" in connector.call_args.kwargs["conninfo"]
        expected = workspace_queue(worker_environment.local_auth.workspace_id)
        assert native.run_worker.call_args.kwargs["queues"] == [expected]
        assert native.run_worker.call_args.kwargs["wait"] is not once
        assert register.call_args.kwargs["queue"] == expected
        assignment_worker = presence.call_args.args[1]
        from otm.providers.administrator_access_simulator import simulated_administrator_inspection

        assert (
            assignment_worker.administrator_inspection_factory is simulated_administrator_inspection
        )
        workflow = lifecycle.call_args.args[1]
        assert callable(workflow.facade.recovery_console_loader)
        from otm.recovery_console import parse_release_cidrs

        changed = parse_release_cidrs("198.51.100.0/24")
        with patch.object(
            local_worker,
            "load_settings",
            return_value=worker_environment.model_copy(update={"recovery_console": changed}),
        ):
            assert workflow.facade.recovery_console_loader() == changed
        worker = register.call_args.args[1]
        assert worker.clock().tzinfo is not None
        engine.dispose.assert_called_once()


# IPv6 and remote targets are refused before consuming any job or opening a second native pool.
@pytest.mark.parametrize("host", ["::1", "remote.example.test"])
def test_worker_rejects_other_targets(worker_environment, host):
    engine = Mock()
    engine.url = Mock(host=host)
    with (
        patch.object(local_worker, "load_sandbox"),
        patch.object(local_worker, "maintenance_engine", return_value=engine),
        pytest.raises(ValueError, match="LOOPBACK_DATABASE_REQUIRED"),
    ):
        local_worker.run_worker()
    engine.dispose.assert_called_once()


# Missing local policy fails before a pool is opened, independent of app availability.
@pytest.mark.parametrize("field", ["local_auth", "local_server"])
def test_worker_requires_explicit_settings(worker_environment, field):
    with (
        patch.object(
            local_worker,
            "load_settings",
            return_value=worker_environment.model_copy(update={field: None}),
        ),
        pytest.raises(ValueError, match="EXPLICIT_LOCAL_CONFIGURATION_REQUIRED"),
    ):
        local_worker.run_worker()


# Process failures and accidentally supplied private arguments yield only fixed diagnostics.
@pytest.mark.parametrize("failure", [None, RuntimeError("private-marker"), KeyboardInterrupt()])
def test_worker_cli_sanitization(failure, capsys):
    with patch.object(local_worker, "run_worker", side_effect=failure) as run:
        assert local_worker.main(["--once"]) == (1 if isinstance(failure, RuntimeError) else 0)
        run.assert_called_once_with(once=True)
    assert "private-marker" not in capsys.readouterr().out
    assert local_worker.main(["private-marker"]) == 1
    assert "private-marker" not in capsys.readouterr().out


# Enabled mail registers an ID-only consumer and fences old SMTP settings before any socket opens.
def test_worker_email_composition_and_reload_fence(worker_environment):
    from otm.email_policy import EmailPolicyBlocked
    from otm.settings import NotificationSettings, TestingSettings

    settings = worker_environment.model_copy(
        update={
            "notifications": NotificationSettings(enabled=True),
            "testing": TestingSettings(email_override="capture@otm.test"),
        }
    )
    engine = Mock(url=make_url("postgresql+psycopg://synthetic:fixture@127.0.0.1:54321/test"))
    native = Mock()
    with (
        patch.object(local_worker, "load_settings", return_value=settings) as load,
        patch.object(local_worker, "load_sandbox"),
        patch.object(local_worker, "maintenance_engine", return_value=engine),
        patch.object(local_worker, "require_runtime_role"),
        patch.object(local_worker.procrastinate, "PsycopgConnector"),
        patch.object(local_worker.procrastinate, "App", return_value=native),
        patch.object(local_worker, "register_organization_task") as register,
        patch.object(local_worker, "register_notification_task") as mail,
    ):
        local_worker.run_worker(once=True)
        delivery = mail.call_args.args[1]
        workflow = register.call_args.args[1]
        assert workflow.notifications is not None
        assert delivery.application_origin == settings.local_server.public_origin
        assert workflow.mail_policy_loader().email_override == "capture@otm.test"
        load.return_value = settings.model_copy(
            update={"notifications": settings.notifications.model_copy(update={"smtp_port": 2525})}
        )
        with pytest.raises(EmailPolicyBlocked, match="EMAIL_TRANSPORT_CHANGED"):
            delivery.policy_loader()
