"""Explicit API-key profiles and hosted identity are tested only with generated disposable keys."""

import os
from pathlib import Path
from unittest.mock import patch

import oci
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from otm import platform_auth as auth
from otm.oci_settings import OciSettings
from otm.secrets.contracts import VaultReadScope, VaultUnavailable
from otm.secrets.vault_oci import configured_vault_reader
from otm.settings import ApplicationSettings, load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config"
TENANCY = "ocid1.tenancy.oc1..synthetic"
PRINCIPAL = "ocid1.user.oc1..synthetic"
REGION = "us-ashburn-1"
PROFILE = "ATLAS_DEV"


# Each fixture has owner-only local files and a generated key that is never logged or committed.
@pytest.fixture
def development(tmp_path):
    key = tmp_path / "api.pem"
    key.write_bytes(
        rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key.chmod(0o600)
    config = tmp_path / "config"
    values = {
        "user": PRINCIPAL,
        "tenancy": TENANCY,
        "region": REGION,
        "fingerprint": ":".join(["ab"] * 16),
        "key_file": str(key),
    }
    config.write_text("[ATLAS_DEV]\n" + "\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
    config.chmod(0o600)
    raw = load_settings(CONFIG / "application.toml").model_dump()
    raw.update(
        provider_mode="oci",
        testing={"email_override": "developer@example.test"},
        oci={
            "auth_method": "api_key_profile",
            "region": REGION,
            "tenancy_ocid": TENANCY,
            "config_file": str(config),
            "profile": PROFILE,
        },
    )
    return config, key, values, ApplicationSettings.model_validate(raw)


# A named API-key profile produces a real SDK signer without browser/OKE/file-default fallback.
def test_named_profile_constructs_real_signer(development):
    config, key, _, settings = development
    with patch.object(
        oci.auth.signers, "get_oke_workload_identity_resource_principal_signer"
    ) as oke:
        identity = auth.platform_identity(settings)
    assert isinstance(identity.signer, oci.signer.Signer)
    assert identity.signer.api_key == f"{TENANCY}/{PRINCIPAL}/" + ":".join(["ab"] * 16)
    assert identity.client_config["region"] == REGION
    assert identity.client_config["key_file"] == str(key)
    assert str(key) not in repr(identity) and str(config) not in repr(identity)
    assert "PRIVATE KEY" not in repr(identity.client_config)
    oke.assert_not_called()


# The same Vault reader accepts a real local signer; SDK client initialization performs no calls.
def test_named_profile_composes_real_vault_clients(development):
    _, _, _, settings = development
    scope = VaultReadScope(
        region=REGION,
        vault_ocid="ocid1.vault.oc1.iad.synthetic",
        compartment_ocid="ocid1.compartment.oc1..synthetic",
    )
    with patch.object(
        oci.base_client.BaseClient, "call_api", side_effect=AssertionError("NO_NETWORK")
    ):
        reader = configured_vault_reader(settings, scope)
    assert reader.metadata_client.base_client.signer is reader.bundle_client.base_client.signer
    assert isinstance(reader.metadata_client.base_client.signer, oci.signer.Signer)
    reader.metadata_client.base_client.session.close()
    reader.bundle_client.base_client.session.close()


# Local cloud use requires test routing, while location/auth mismatches never load credentials.
@pytest.mark.parametrize(
    "fault",
    [
        "missing_oci",
        "simulation_oci",
        "no_override",
        "local_oke",
        "hosted_api",
        "hosted_profile_fields",
    ],
)
def test_configuration_combinations(development, fault):
    raw = development[3].model_dump()
    if fault == "missing_oci":
        raw["oci"] = None
    elif fault == "simulation_oci":
        raw["provider_mode"] = "simulated"
    elif fault == "no_override":
        raw["testing"] = None
    elif fault == "local_oke":
        raw["oci"] = {
            "auth_method": "oke_workload_identity",
            "region": REGION,
            "tenancy_ocid": TENANCY,
        }
    elif fault == "hosted_api":
        raw["environment"] = "staging"
        raw["local_server"] = None
    else:
        raw["oci"]["auth_method"] = "oke_workload_identity"
    with pytest.raises(ValidationError):
        ApplicationSettings.model_validate(raw)


# Profile names and locations are explicit; DEFAULT and relative/CWD selection are not allowed.
@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", None),
        ("profile", "DEFAULT"),
        ("profile", "default"),
        ("profile", "bad/name"),
        ("config_file", None),
        ("config_file", "relative/config"),
    ],
)
def test_profile_settings_require_explicit_selection(development, field, value):
    raw = development[3].oci.model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        OciSettings.model_validate(raw)


# Existing simulator settings remain the default and never inspect ~/.oci/config.
def test_simulation_never_reads_credentials():
    settings = load_settings(CONFIG / "application.toml")
    with patch.object(auth, "private_text") as read:
        with pytest.raises(auth.OciAuthenticationUnavailable):
            auth.platform_identity(settings)
    read.assert_not_called()


# A complete named section must stand alone even when DEFAULT contains usable credentials.
@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "inherit",
        "session_token",
        "endpoint",
        "debug",
        "wrong_tenancy",
        "wrong_region",
        "wrong_user",
        "fingerprint",
        "invalid_toml_like_ini",
    ],
)
def test_bad_profiles_fail_closed(development, fault, capsys):
    config, _, values, settings = development
    values = dict(values)
    if fault == "missing":
        content = "[OTHER]\nregion=us-ashburn-1\n"
    elif fault == "inherit":
        content = (
            "[DEFAULT]\n" + "\n".join(f"{k}={v}" for k, v in values.items()) + "\n[ATLAS_DEV]\n"
        )
    elif fault == "invalid_toml_like_ini":
        content = "not a profile\n"
    else:
        updates = {
            "session_token": ("security_token_file", "/unused"),
            "endpoint": ("service_endpoint", "https://example.test"),
            "debug": ("log_requests", "true"),
            "wrong_tenancy": ("tenancy", TENANCY + "other"),
            "wrong_region": ("region", "us-phoenix-1"),
            "wrong_user": ("user", "bad"),
            "fingerprint": ("fingerprint", "bad"),
        }
        name, value = updates[fault]
        values[name] = value
        content = "[ATLAS_DEV]\n" + "\n".join(f"{k}={v}" for k, v in values.items())
    config.write_text(content)
    with patch.object(
        oci.auth.signers, "get_oke_workload_identity_resource_principal_signer"
    ) as oke:
        with pytest.raises(
            auth.OciAuthenticationUnavailable, match="^OCI_AUTHENTICATION_UNAVAILABLE$"
        ) as caught:
            auth.platform_identity(settings)
    assert caught.value.__suppress_context__
    assert capsys.readouterr() == ("", "")
    oke.assert_not_called()


# Private files cannot be shared, linked, special, oversized, absent or relative.
@pytest.mark.parametrize(
    "fault",
    [
        "permission",
        "symlink",
        "hardlink",
        "directory",
        "fifo",
        "oversized",
        "empty",
        "missing",
        "relative",
        "traversal",
    ],
)
def test_private_file_guards(tmp_path, fault):
    original = tmp_path / "original"
    original.write_text("synthetic test value")
    original.chmod(0o600)
    target = original
    if fault == "permission":
        original.chmod(0o644)
    elif fault == "symlink":
        target = tmp_path / "link"
        target.symlink_to(original)
    elif fault == "hardlink":
        os.link(original, tmp_path / "other")
    elif fault == "directory":
        target = tmp_path
    elif fault == "fifo":
        target = tmp_path / "fifo"
        os.mkfifo(target, 0o600)
    elif fault == "oversized":
        original.write_text("x" * 65537)
    elif fault == "empty":
        original.write_text("")
    elif fault == "missing":
        target = tmp_path / "absent"
    elif fault == "relative":
        target = Path("relative")
    elif fault == "traversal":
        target = tmp_path / ".." / tmp_path.name / "original"
    with pytest.raises((ValueError, OSError)):
        auth.private_text(str(target))


# OKE identity is selected only by hosted settings and still never reads a laptop config file.
def test_hosted_uses_oke_only(monkeypatch):
    raw = load_settings(CONFIG / "staging.application.toml").model_dump()
    raw.update(
        provider_mode="oci",
        oci={"auth_method": "oke_workload_identity", "region": REGION, "tenancy_ocid": TENANCY},
    )
    settings = ApplicationSettings.model_validate(raw)
    monkeypatch.setenv("OCI_RESOURCE_PRINCIPAL_REGION", REGION)
    with (
        patch.object(auth, "private_text") as read,
        patch.object(
            oci.auth.signers, "get_oke_workload_identity_resource_principal_signer"
        ) as signer,
    ):
        identity = auth.platform_identity(settings)
    assert identity.signer is signer.return_value
    assert identity.client_config == {"region": REGION}
    read.assert_not_called()


# Unknown SDK regions and hosted token-exchange failures normalize without another identity attempt.
@pytest.mark.parametrize("fault", ["region", "oke_failure", "oke_region"])
def test_hosted_auth_failure(monkeypatch, fault):
    raw = load_settings(CONFIG / "staging.application.toml").model_dump()
    raw.update(
        provider_mode="oci",
        oci={"auth_method": "oke_workload_identity", "region": REGION, "tenancy_ocid": TENANCY},
    )
    if fault == "region":
        raw["oci"]["region"] = "unknown-region-1"
    monkeypatch.setenv(
        "OCI_RESOURCE_PRINCIPAL_REGION", "us-phoenix-1" if fault == "oke_region" else REGION
    )
    with patch.object(
        oci.auth.signers,
        "get_oke_workload_identity_resource_principal_signer",
        side_effect=RuntimeError("private SDK body"),
    ):
        with pytest.raises(auth.OciAuthenticationUnavailable):
            auth.platform_identity(raw)


# Wrong-region Vault scope fails before private files are read or service clients are built.
def test_vault_scope_region_guard(development):
    scope = VaultReadScope(
        region="us-phoenix-1",
        vault_ocid="ocid1.vault.oc1.phx.synthetic",
        compartment_ocid="ocid1.compartment.oc1..synthetic",
    )
    with patch.object(auth, "private_text") as read:
        with pytest.raises(VaultUnavailable):
            configured_vault_reader(development[3], scope)
    read.assert_not_called()


# Existing simulator launchers fail before DB/cloud work when explicitly given a live OCI profile.
@pytest.mark.parametrize(
    "module_name,entry",
    [("otm.local_server", "create_local_application"), ("otm.local_worker", "run_worker")],
)
def test_simulator_launchers_do_not_accept_live_mode(development, monkeypatch, module_name, entry):
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.setenv("OTM_APPLICATION_CONFIG", str(development[0]))
    with (
        patch.object(module, "load_settings", return_value=development[3]),
        patch.object(module, "maintenance_engine") as database,
    ):
        with pytest.raises(ValueError, match="LOCAL_OCI_SERVICE_COMPOSITION_PENDING"):
            getattr(module, entry)()
    database.assert_not_called()
