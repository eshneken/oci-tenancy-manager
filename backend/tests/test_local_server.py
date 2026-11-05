"""Explicit local composition and lifecycle without real credentials or a database."""

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from otm import local_server
from otm.settings import load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"


# Reject incomplete, remote and publicly nested MFA custody before opening a database pool.
@pytest.mark.parametrize("damage", ["auth", "server", "origin", "custody"])
def test_local_factory_guards(tmp_path, monkeypatch, damage):
    settings = load_settings(CONFIG)
    if damage == "auth":
        settings = settings.model_copy(update={"local_auth": None})
    elif damage == "server":
        settings = settings.model_copy(update={"local_server": None})
    elif damage == "origin":
        settings = settings.model_copy(
            update={
                "local_server": settings.local_server.model_copy(
                    update={"public_origin": "https://remote.example.test"}
                )
            }
        )
    monkeypatch.setenv("OTM_APPLICATION_CONFIG", str(CONFIG))
    monkeypatch.setenv(
        "OTM_MFA_SECRET_DIRECTORY",
        str(tmp_path / "public/secret" if damage == "custody" else tmp_path / "secret"),
    )
    monkeypatch.setenv("OTM_FRONTEND_DIST", str(tmp_path / "public"))
    with (
        patch.object(local_server, "load_settings", return_value=settings),
        pytest.raises(ValueError),
    ):
        local_server.create_local_application()


# Compose real session/login services around explicit adapters and dispose the pool on shutdown.
def test_local_factory_lifespan(tmp_path, monkeypatch):
    public, custody = tmp_path / "public", tmp_path / "private"
    public.mkdir()
    (public / "assets").mkdir()
    (public / "branding-assets").mkdir()
    for name in ("atlas-wordmark.png", "atlas-icon.png"):
        (public / "branding-assets" / name).write_bytes(b"synthetic raster fixture")
    (public / "index.html").write_text("<main>OTM</main>")
    custody.mkdir(mode=0o700)
    monkeypatch.setenv("OTM_APPLICATION_CONFIG", str(CONFIG))
    monkeypatch.setenv("OTM_MFA_SECRET_DIRECTORY", str(custody))
    monkeypatch.setenv("OTM_FRONTEND_DIST", str(public))
    monkeypatch.setenv("OTM_DATABASE_URL", "synthetic-test-url")
    connection = Mock()
    connection.scalar.return_value = False
    engine = Mock(connect=Mock(return_value=nullcontext(connection)))
    with patch.object(local_server, "maintenance_engine", return_value=engine):
        app = local_server.create_local_application()
        with TestClient(app, base_url="https://localhost:8443") as client:
            assert client.get("/login").status_code == 200
            assert client.get("/api/branding").json()["display_name"] == "Atlas"
            assert client.get("/api/administrators").status_code == 401
        assert engine.dispose.call_count == 1


# Owner/elevated or indeterminate DB roles fail closed and release the pool before routes exist.
@pytest.mark.parametrize("unsafe", [True, None])
def test_factory_refuses_operator_role(tmp_path, monkeypatch, unsafe):
    custody = tmp_path / "private"
    custody.mkdir(mode=0o700)
    for key, value in {
        "OTM_APPLICATION_CONFIG": str(CONFIG),
        "OTM_MFA_SECRET_DIRECTORY": str(custody),
        "OTM_FRONTEND_DIST": str(tmp_path / "public"),
        "OTM_DATABASE_URL": "synthetic",
    }.items():
        monkeypatch.setenv(key, value)
    connection = Mock()
    connection.scalar.return_value = unsafe
    engine = Mock(connect=Mock(return_value=nullcontext(connection)))
    with (
        patch.object(local_server, "maintenance_engine", return_value=engine),
        pytest.raises(ValueError, match="RESTRICTED_RUNTIME_ROLE_REQUIRED"),
    ):
        local_server.create_local_application()
    engine.dispose.assert_called_once()
