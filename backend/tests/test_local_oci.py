"""Exercise the isolated provider development boundary without live credentials."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from otm import local_oci
from otm.settings import load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config/development-oci.application.toml"


# Refuse demo origins, organization reset, SMTP, routable overrides and simulator configuration.
@pytest.mark.parametrize(
    ("section", "update"),
    [
        ("local_server", {"public_origin": "https://localhost:8445"}),
        ("local_server", {"public_origin": "https://127.0.0.1:8443"}),
        ("local_server", {"public_origin": "https://127.0.0.1:8444"}),
        ("local_server", {"organization_reset_enabled": True}),
        ("notifications", {"enabled": True}),
        ("testing", {"email_override": "developer@example.com"}),
        ("testing", {"email_override": None}),
        (None, {"provider_mode": "simulated", "oci": None}),
    ],
)
def test_oci_development_requires_isolation(section, update):
    settings = load_settings(CONFIG)
    if section:
        update = {section: getattr(settings, section).model_copy(update=update)}
    with pytest.raises(ValueError, match="ISOLATED_LOCAL_OCI_CONFIGURATION_REQUIRED"):
        local_oci.validate_local_oci(settings.model_copy(update=update))


# Readiness uses the existing signer, checks the DB and verifies the exact returned OCI tenancy.
@pytest.mark.parametrize("matches", [True, False])
def test_readiness_checks_database_and_signed_tenancy(tmp_path, monkeypatch, matches):
    settings = load_settings(CONFIG)
    expected = settings.oci.tenancy_ocid
    signer = object()
    connection = Mock()
    engine = Mock(connect=Mock(return_value=nullcontext(connection)))
    tenancy = SimpleNamespace(id=expected if matches else "unrelated")
    client = Mock(get_tenancy=Mock(return_value=SimpleNamespace(data=tenancy)))
    client_factory = Mock(return_value=client)
    client_config = {"region": settings.oci.region, "key_file": str(tmp_path / "key")}
    identity = SimpleNamespace(signer=signer, client_config=client_config)
    monkeypatch.setattr(local_oci, "platform_identity", Mock(return_value=identity))
    monkeypatch.setattr(local_oci.oci.identity, "IdentityClient", client_factory)

    ready = local_oci.oci_readiness(settings, engine, tmp_path / "public")
    assert ready() is matches
    assert ready() is matches
    assert connection.execute.call_count == 2
    client.get_tenancy.assert_called_once_with(expected)
    assert client_factory.call_args.args == (client_config,)
    assert client_factory.call_args.kwargs["signer"] is signer
    assert client_factory.call_args.kwargs["log_requests"] is False


# Owner-only OCI credentials must also stay outside publicly served paths.
def test_oci_readiness_refuses_public_key(tmp_path, monkeypatch):
    settings = load_settings(CONFIG)
    key = tmp_path / "public/assets/key"
    identity = SimpleNamespace(client_config={"key_file": str(key)})
    monkeypatch.setattr(local_oci, "platform_identity", Mock(return_value=identity))
    with pytest.raises(ValueError, match="OCI_CREDENTIALS_CANNOT_BE_PUBLIC"):
        local_oci.oci_readiness(settings, Mock(), tmp_path / "public")


# A verified enrollment boot check replaces the broader tenancy readiness call.
def test_scoped_readiness_reuses_startup_enrollment_verification(tmp_path, monkeypatch):
    probe = Mock()
    monkeypatch.setattr(local_oci, "probe_tenancy", probe)
    engine = MagicMock()
    assert local_oci.oci_readiness(Mock(), engine, tmp_path, verified_enrollment=True)() is True
    engine.connect.assert_called_once()
    probe.assert_not_called()


# A missing signer marks readiness unavailable while local recovery can still start.
def test_missing_oci_signer_does_not_stop_laptop_start(tmp_path, monkeypatch):
    missing = Mock(side_effect=local_oci.OciAuthenticationUnavailable())
    monkeypatch.setattr(local_oci, "platform_identity", missing)
    ready = local_oci.oci_readiness(Mock(), MagicMock(), tmp_path)
    assert ready() is False
