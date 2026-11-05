"""Application configuration and bounded housekeeping contracts without database access."""

import json
import os
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError
from test_admission_service import NOW

from otm.auth.cleanup import cleanup_sessions
from otm.maintenance import cleanup_cronjob, main, maintenance_engine
from otm.settings import ApplicationSettings, ConfigurationError, load_settings, session_lifetime

CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"
IMAGE = "registry.example.test/otm@sha256:" + "a" * 64


# Load the real application file so tests do not maintain a second set of operational defaults.
@pytest.fixture
def app_settings():
    return load_settings(CONFIG)


# Verify approved defaults and server-selected deadlines without extending preexisting sessions.
def test_defaults_and_configurable_new_session_lifetime(app_settings):
    assert app_settings.sessions.idle_timeout_seconds == 1800
    assert app_settings.sessions.absolute_timeout_seconds == 28800
    lifetime = session_lifetime(NOW, app_settings.sessions)
    assert lifetime.expires_at == NOW + timedelta(hours=8)
    changed = app_settings.sessions.model_copy(
        update={"idle_timeout_seconds": 60, "absolute_timeout_seconds": 120}
    )
    other = session_lifetime(NOW, changed)
    assert other.expires_at == NOW + timedelta(seconds=120) and other.idle_timeout_seconds == 60
    assert lifetime.expires_at == NOW + timedelta(hours=8)


# Reject contradictory, untyped, unknown and unsafe operational values rather than guessing.
@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "version_bool",
        "secret",
        "idle_zero",
        "idle_bool",
        "idle_gt_absolute",
        "batch",
        "hour",
        "minute",
        "runs",
    ],
)
def test_invalid_settings_fail_closed(app_settings, damage):
    values = app_settings.model_dump()
    if damage == "version":
        values["schema_version"] = 2
    elif damage == "version_bool":
        values["schema_version"] = True
    elif damage == "secret":
        values["password"] = "private-example"
    elif damage == "idle_zero":
        values["sessions"]["idle_timeout_seconds"] = 0
    elif damage == "idle_bool":
        values["sessions"]["idle_timeout_seconds"] = True
    elif damage == "idle_gt_absolute":
        values["sessions"]["idle_timeout_seconds"] = 100000
    else:
        values["sessions"]["cleanup"][
            {
                "batch": "batch_size",
                "hour": "hour_utc",
                "minute": "minute_utc",
                "runs": "max_batches",
            }[damage]
        ] = -1
    with pytest.raises(ValidationError):
        ApplicationSettings.model_validate(values)


# Bound the file parser and keep accidental secrets out of fixed configuration diagnostics.
@pytest.mark.parametrize(
    "contents", [None, b"[sessions", b"password='private-example'", b"x" * 65537, b"\xff"]
)
def test_configuration_file_failures_are_sanitized(tmp_path, contents):
    path = tmp_path / "application.toml"
    if contents is not None:
        path.write_bytes(contents)
    with pytest.raises(ConfigurationError, match="^INVALID_APPLICATION_SETTINGS$") as error:
        load_settings(path)
    assert error.value.__suppress_context__


# A naive timestamp must not acquire a deployment timezone during session issuance.
def test_deadlines_require_server_utc(app_settings):
    with pytest.raises(ValidationError):
        session_lifetime(NOW.replace(tzinfo=None), app_settings.sessions)


# Stop after a non-full batch and report only the work cap, not proof that no locked rows remain.
@pytest.mark.parametrize(
    "counts,deleted,batches,more", [([2], 2, 1, False), ([3, 1], 4, 2, False), ([3, 3], 6, 2, True)]
)
def test_housekeeping_bounds_each_run(app_settings, counts, deleted, batches, more):
    settings = app_settings.sessions.cleanup.model_copy(update={"batch_size": 3, "max_batches": 2})
    repository = Mock(purge_expired=Mock(side_effect=counts))
    result = cleanup_sessions(repository, settings, lambda: NOW)
    assert result.model_dump() == {
        "deleted": deleted,
        "batches": batches,
        "batch_limit_reached": more,
    }
    assert repository.purge_expired.call_count == batches
    repository.purge_expired.assert_called_with(NOW, 3)


# A malformed repository result cannot manufacture a passing cleanup receipt.
@pytest.mark.parametrize("count", [-1, 501, True, "1"])
def test_cleanup_rejects_invalid_adapter_counts(app_settings, count):
    with pytest.raises(ValueError, match="INVALID_SESSION_CLEANUP_COUNT"):
        cleanup_sessions(
            Mock(purge_expired=Mock(return_value=count)), app_settings.sessions.cleanup, lambda: NOW
        )


# Pin images, isolate credentials and derive schedule from the same validated settings file.
def test_daily_job_matches_configuration_and_least_privilege(app_settings):
    modified = deepcopy(app_settings.model_dump())
    modified["sessions"]["cleanup"].update(hour_utc=4, minute_utc=15)
    manifest = cleanup_cronjob(ApplicationSettings.model_validate(modified), IMAGE)
    assert (
        manifest["spec"]["schedule"] == "15 4 * * *" and manifest["spec"]["timeZone"] == "Etc/UTC"
    )
    assert manifest["spec"]["concurrencyPolicy"] == "Forbid"
    pod = manifest["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False and pod["securityContext"]["runAsNonRoot"]
    assert "secretKeyRef" in pod["containers"][0]["env"][0]["valueFrom"]
    assert pod["containers"][0]["image"] == IMAGE


# Do not produce a production job against a mutable tag or credential-bearing image string.
@pytest.mark.parametrize(
    "image", ["registry/otm:latest", "https://example.test/image", IMAGE + "\n", ""]
)
def test_renderer_requires_digest_pinning(app_settings, image):
    with pytest.raises(ValueError, match="PINNED_MAINTENANCE_IMAGE_REQUIRED"):
        cleanup_cronjob(app_settings, image)


# Reject libpq environment redirects before SQLAlchemy can construct any target connection.
def test_maintenance_rejects_environment_redirection(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "other.example.test")
    with patch("otm.maintenance.create_engine") as create:
        with pytest.raises(ValueError, match="LIBPQ_ENVIRONMENT"):
            maintenance_engine("postgresql+psycopg://u:p@localhost:5432/test", None)
    create.assert_not_called()


# Do not use saved defaults or URL query parameters capable of overriding target or TLS.
@pytest.mark.parametrize(
    "url,ca",
    [
        ("sqlite:///example", None),
        ("postgresql+psycopg://u:p@localhost/test", None),
        ("postgresql+psycopg://u:p@localhost:5432/test?host=other", None),
        ("postgresql+psycopg://u:p@database.example.test:5432/test", None),
    ],
)
def test_maintenance_target_validation(url, ca, monkeypatch):
    for key in list(os.environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
    with patch("otm.maintenance.create_engine") as create:
        with pytest.raises(ValueError):
            maintenance_engine(url, ca)
    create.assert_not_called()


# Verify TLS and explicit loopback connection options without connecting to real databases.
@pytest.mark.parametrize(
    "host,ca,sslmode",
    [
        ("localhost", None, "disable"),
        ("::1", None, "disable"),
        ("database.example.test", "/example/ca.crt", "verify-full"),
    ],
)
def test_maintenance_connection_options(host, ca, sslmode, monkeypatch):
    for key in list(os.environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
    authority = "[::1]" if host == "::1" else host
    with patch("otm.maintenance.create_engine") as create:
        maintenance_engine(f"postgresql+psycopg://u:p@{authority}:5432/test", ca)
    options = create.call_args.kwargs["connect_args"]
    assert options["sslmode"] == sslmode and create.call_args.kwargs["hide_parameters"]
    assert options["gssencmode"] == "disable"
    assert options.get("sslrootcert") == ca


# Rendering needs no database credential or live cluster and emits only references.
def test_cli_render_without_database(capsys):
    assert main(["render-session-cleanup", "--config", str(CONFIG), "--image", IMAGE]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "CronJob"


# Command failure never prints the connection string or a raw driver exception.
def test_cli_sanitizes_failure_and_disposes_engine(capsys, app_settings):
    engine = Mock()
    with (
        patch("otm.maintenance.maintenance_engine", return_value=engine),
        patch("otm.maintenance.cleanup_sessions", side_effect=RuntimeError("private-example")),
    ):
        assert main(["cleanup-sessions", "--config", str(CONFIG)]) == 1
    assert json.loads(capsys.readouterr().out) == {"code": "SESSION_MAINTENANCE_FAILED"}
    engine.dispose.assert_called_once()


# Report aggregate successful work while always releasing the owned connection pool.
def test_cli_cleanup_success(capsys):
    from otm.auth.cleanup import CleanupResult

    engine = Mock()
    with (
        patch("otm.maintenance.maintenance_engine", return_value=engine),
        patch(
            "otm.maintenance.cleanup_sessions",
            return_value=CleanupResult(deleted=2, batches=1, batch_limit_reached=False),
        ),
    ):
        assert main(["cleanup-sessions", "--config", str(CONFIG)]) == 0
    assert json.loads(capsys.readouterr().out)["deleted"] == 2
    engine.dispose.assert_called_once()
