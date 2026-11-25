"""Explicit local composition and lifecycle without real credentials or a database."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_corporate_oidc import binding

from otm import local_server
from otm.auth.corporate_enrollment import EnrollmentTarget
from otm.local_development import LocalState, database_url, write_state
from otm.settings import load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"

__all__ = ["binding"]


# Enrollment must match an independent approved active app assignment, not just SSO config.
@pytest.mark.parametrize("fault", [None, "missing", "app", "group", "client_id", "callback"])
def test_laptop_writer_requires_matching_operator_assignment(tmp_path, fault):
    origin = "https://127.0.0.1:8445"
    evidence = local_server.LaptopAssignmentEvidence(
        app="a" * 32,
        client_id="synthetic-client",
        group="b" * 32,
        grant="c" * 32,
        callback=origin + "/api/auth/sso/callback",
    )
    corporate = SimpleNamespace(
        target=SimpleNamespace(app=evidence.app, group=evidence.group),
        oidc=SimpleNamespace(client_id=evidence.client_id, installation_origin=origin),
    )
    if fault != "missing":
        if fault:
            evidence = evidence.model_copy(update={fault: "d" * 32})
        path = tmp_path / "corporate-assignment.json"
        path.write_text(evidence.model_dump_json())
        path.chmod(0o600)
    assert local_server.laptop_assignment_verified(tmp_path, corporate) is (fault is None)


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


# Use synthetic identity-domain details while exercising the real pilot provider pin.
@pytest.fixture
def laptop_oidc_binding(binding):
    return binding.model_copy(
        update={
            "domain_claim": "idcs-example",
            "provider_origin": "https://idcs-example.identity.oraclecloud.com",
            "wire_issuer": "https://identity.oraclecloud.com/",
        }
    )


# The OCI server mounts guarded organization routes and refuses simulator fixtures and dispatch.
@pytest.mark.parametrize("corporate", [False, True])
def test_isolated_oci_factory(tmp_path, monkeypatch, laptop_oidc_binding, corporate):
    binding = laptop_oidc_binding
    config = CONFIG.parent / "development-oci.application.toml"
    root = tmp_path / "oci"
    root.mkdir(mode=0o700)
    state = LocalState(
        instance_id=uuid4(),
        owner_password="synthetic-owner",
        api_password="synthetic-api",
        database_port=18000,
        provider_mode="oci",
    )
    write_state(root, state)
    private_config = root / "application.toml"
    private_config.write_text(config.read_text())
    if corporate:
        target = EnrollmentTarget(
            environment="development",
            workspace=load_settings(config).local_auth.workspace_id,
            domain="synthetic-domain",
            issuer="urn:otm:synthetic-domain",
            app="a" * 32,
            group=binding.group,
            oidc_client_id=binding.client_id,
        )
        path = root / "corporate-sign-in.json"
        path.write_text(
            local_server.LaptopCorporateConfiguration(target=target, oidc=binding).model_dump_json()
        )
        path.chmod(0o600)
    custody = root / "mfa"
    custody.mkdir(mode=0o700)
    public = tmp_path / "public"
    public.mkdir()
    (public / "assets").mkdir()
    (public / "branding-assets").mkdir()
    for name in ("atlas-wordmark.png", "atlas-icon.png"):
        (public / "branding-assets" / name).write_bytes(b"synthetic raster fixture")
    (public / "index.html").write_text("<main>OTM</main>")
    for key, value in {
        "OTM_APPLICATION_CONFIG": str(private_config),
        "OTM_MFA_SECRET_DIRECTORY": str(custody),
        "OTM_FRONTEND_DIST": str(public),
        "OTM_DATABASE_URL": "synthetic",
        "OTM_SANDBOX_CONFIG": "untrusted.json",
    }.items():
        monkeypatch.setenv(key, value)
    connection = Mock()
    connection.scalar.return_value = False
    engine = Mock(connect=Mock(return_value=nullcontext(connection)))
    with (
        patch.object(local_server, "maintenance_engine", return_value=engine),
        patch.object(local_server, "oci_readiness", return_value=lambda: True),
        patch.object(local_server, "compose_notifications") as notifications,
    ):
        with pytest.raises(ValueError, match="LOCAL_OCI_FIXTURES_FORBIDDEN"):
            local_server.create_local_oci_application()
        monkeypatch.delenv("OTM_SANDBOX_CONFIG")
        with pytest.raises(ValueError, match="LOCAL_OCI_INSTALLATION_MISMATCH"):
            local_server.create_local_oci_application()
        monkeypatch.setenv("OTM_DATABASE_URL", database_url(state))
        app = local_server.create_local_oci_application()
        with TestClient(app, base_url="https://127.0.0.1:8445") as client:
            assert client.get("/health/ready").json() == {"status": "ready"}
            assert client.get("/api/auth/sso/status").json() == {"enabled": corporate}
            assert client.get("/api/administrators").status_code == 401
            assert client.get("/api/organization/mapping").status_code == 401
        routes = app.openapi()["paths"]
        assert "/api/organization/mapping/apply" in routes
        assert "/api/organization/feeds" in routes
        assert not any(path.startswith(("/api/tenancies", "/api/configuration")) for path in routes)
        notifications.assert_not_called()
        engine.dispose.assert_called_once()


# Bad local bindings never enable the corporate route or displace the independent recovery path.
@pytest.mark.parametrize(
    "damage",
    [
        "origin",
        "workspace",
        "client",
        "group",
        "environment",
        "callback",
        "mode",
        "domain",
        "provider",
        "issuer",
    ],
)
def test_corporate_configuration_rejects_wrong_binding(tmp_path, laptop_oidc_binding, damage):
    binding = laptop_oidc_binding
    target = EnrollmentTarget(
        environment="development",
        workspace="dev",
        domain="synthetic-domain",
        issuer="urn:otm:synthetic-domain",
        app="a" * 32,
        group=binding.group,
        oidc_client_id=binding.client_id,
    )
    origin, workspace = binding.installation_origin, target.workspace
    if damage == "origin":
        origin = "https://127.0.0.1:8443"
    elif damage == "callback":
        binding = binding.model_copy(update={"installation_origin": "https://127.0.0.1:8444"})
    elif damage == "domain":
        binding = binding.model_copy(update={"domain_claim": "unexpected"})
    elif damage == "provider":
        binding = binding.model_copy(update={"provider_origin": "https://example.test"})
    elif damage == "issuer":
        binding = binding.model_copy(update={"wire_issuer": "https://example.test/"})
    changes = dict(
        workspace={"workspace": "stage"},
        client={"oidc_client_id": "staging-client"},
        group={"group": "d" * 32},
        environment={"environment": "staging"},
    )
    target = target.model_copy(update=changes.get(damage, {}))
    config = local_server.LaptopCorporateConfiguration(target=target, oidc=binding)
    path = tmp_path / "corporate-sign-in.json"
    path.write_text(config.model_dump_json())
    path.chmod(0o644 if damage == "mode" else 0o600)
    assert local_server.read_laptop_corporate(tmp_path, origin, workspace) is None
