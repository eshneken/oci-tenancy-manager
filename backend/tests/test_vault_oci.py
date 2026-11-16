"""Synthetic SDK-shaped custody checks; no OCI endpoints or operator secret files are contacted."""

import base64
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

import oci
import pytest
from pydantic import ValidationError

from otm.secrets import vault_oci as adapter
from otm.secrets.contracts import VaultReadScope, VaultUnavailable

TARGET_OCID = "ocid1.vaultsecret.oc1.iad.synthetic"
SCOPE = VaultReadScope(
    region="us-ashburn-1",
    vault_ocid="ocid1.vault.oc1.iad.synthetic",
    compartment_ocid="ocid1.compartment.oc1..synthetic",
)


# Real SDK response models catch attribute/type assumptions without requiring remote HTTP calls.
@pytest.fixture
def custody():
    metadata = oci.vault.models.Secret(
        id=TARGET_OCID,
        vault_id=SCOPE.vault_ocid,
        compartment_id=SCOPE.compartment_ocid,
        lifecycle_state="ACTIVE",
    )
    bundle = oci.secrets.models.SecretBundle(
        secret_id=TARGET_OCID,
        version_number=7,
        stages=["CURRENT"],
        secret_bundle_content=oci.secrets.models.Base64SecretBundleContentDetails(
            content=base64.b64encode(b"synthetic disposable value").decode("ascii")
        ),
    )
    metadata_client, bundle_client = Mock(), Mock()
    metadata_client.get_secret.return_value = SimpleNamespace(data=metadata)
    bundle_client.get_secret_bundle.return_value = SimpleNamespace(data=bundle)
    reader = adapter.OciVaultReader(SCOPE, metadata_client, bundle_client)
    return SimpleNamespace(
        metadata=metadata,
        bundle=bundle,
        reader=reader,
        metadata_client=metadata_client,
        bundle_client=bundle_client,
    )


# A fresh CURRENT selector observes a later version, while routine representations stay redacted.
def test_current_reads_are_not_cached(custody):
    first = custody.reader.current(TARGET_OCID)
    custody.bundle.version_number = 8
    second = custody.reader.current(TARGET_OCID)
    assert (first.version_number, second.version_number) == (7, 8)
    assert first.value.get_secret_value() == "synthetic disposable value"
    assert "synthetic disposable value" not in repr(first)
    assert "synthetic disposable value" not in str(first.value)
    assert "synthetic disposable value" not in repr(asdict(first))
    assert custody.bundle_client.get_secret_bundle.call_count == 2
    kwargs = custody.bundle_client.get_secret_bundle.call_args.kwargs
    assert kwargs["stage"] == "CURRENT"
    assert isinstance(kwargs["retry_strategy"], oci.retry.NoneRetryStrategy)


# Immutable consumers select only the requested numeric version, independently of CURRENT.
def test_exact_version_read(custody):
    custody.bundle.stages = ["PREVIOUS"]
    result = custody.reader.version(TARGET_OCID, 7)
    assert result.version_number == 7
    assert custody.bundle_client.get_secret_bundle.call_args.kwargs["version_number"] == 7
    assert "stage" not in custody.bundle_client.get_secret_bundle.call_args.kwargs


# A malformed or unrelated identifier never reaches either OCI client.
@pytest.mark.parametrize(
    "value", [None, 42, "", "https://example.test/secret", "x\n", SCOPE.vault_ocid]
)
def test_bad_secret_ids_rejected_before_sdk(custody, value):
    with pytest.raises(VaultUnavailable, match="^VAULT_SECRET_UNAVAILABLE$"):
        custody.reader.current(value)
    custody.metadata_client.get_secret.assert_not_called()
    custody.bundle_client.get_secret_bundle.assert_not_called()


# Booleans and coerced strings cannot silently become immutable numeric versions.
@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.5, "7"])
def test_bad_versions_rejected_before_sdk(custody, value):
    with pytest.raises(VaultUnavailable):
        custody.reader.version(TARGET_OCID, value)
    custody.metadata_client.get_secret.assert_not_called()


# Even excessive IAM cannot cause secret bytes to be requested from the wrong scope or state.
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", TARGET_OCID + "different"),
        ("vault_id", SCOPE.vault_ocid + "different"),
        ("compartment_id", SCOPE.compartment_ocid + "different"),
        ("lifecycle_state", "PENDING_DELETION"),
        ("lifecycle_state", "DELETED"),
    ],
)
def test_scope_checked_before_secret_bytes(custody, field, value):
    setattr(custody.metadata, field, value)
    with pytest.raises(VaultUnavailable):
        custody.reader.current(TARGET_OCID)
    custody.bundle_client.get_secret_bundle.assert_not_called()


# Returned identity, version and stage must match the requested credential exactly.
@pytest.mark.parametrize(
    "field,value",
    [
        ("secret_id", TARGET_OCID + "different"),
        ("version_number", 0),
        ("version_number", True),
        ("version_number", None),
        ("stages", []),
        ("stages", None),
    ],
)
def test_mismatched_bundle_rejected(custody, field, value):
    setattr(custody.bundle, field, value)
    with pytest.raises(VaultUnavailable):
        custody.reader.current(TARGET_OCID)


# A response naming another version cannot satisfy an immutable-version lookup.
def test_exact_version_mismatch(custody):
    with pytest.raises(VaultUnavailable):
        custody.reader.version(TARGET_OCID, 6)


# Strict base64, text encoding and byte limits reject unusable or unexpectedly large responses.
@pytest.mark.parametrize(
    "content",
    [
        None,
        "",
        "%%%%",
        "YQ==\n",
        "YQ",
        5,
        base64.b64encode(b"a\0b").decode(),
        base64.b64encode(b"\xff").decode(),
        base64.b64encode(b"a" * (adapter.MAX_SECRET_BYTES + 1)).decode(),
        base64.b64encode(b"").decode(),
    ],
)
def test_invalid_content_rejected(custody, content):
    custody.bundle.secret_bundle_content.content = content
    with pytest.raises(VaultUnavailable):
        custody.reader.current(TARGET_OCID)


# Invalid response model variants cannot bypass the content-type boundary.
@pytest.mark.parametrize("content", [None, SimpleNamespace(content_type="OTHER", content="YQ==")])
def test_content_type_rejected(custody, content):
    custody.bundle.secret_bundle_content = content
    with pytest.raises(VaultUnavailable):
        custody.reader.current(TARGET_OCID)


# The documented byte maximum is inclusive and counts UTF-8 bytes rather than characters.
def test_maximum_content_accepted(custody):
    custody.bundle.secret_bundle_content.content = base64.b64encode(
        b"a" * adapter.MAX_SECRET_BYTES
    ).decode()
    result = custody.reader.current(TARGET_OCID)
    assert len(result.value.get_secret_value()) == adapter.MAX_SECRET_BYTES


# Provider errors are normalized and never printed, chained for display or replaced with local data.
@pytest.mark.parametrize("which", ["metadata", "bundle"])
def test_raw_provider_errors_do_not_escape(custody, capsys, which):
    client = custody.metadata_client if which == "metadata" else custody.bundle_client
    method = client.get_secret if which == "metadata" else client.get_secret_bundle
    method.side_effect = RuntimeError("synthetic provider body containing confidential content")
    with pytest.raises(VaultUnavailable) as caught:
        custody.reader.current(TARGET_OCID)
    assert str(caught.value) == "VAULT_SECRET_UNAVAILABLE"
    assert caught.value.__suppress_context__
    assert caught.value.__cause__ is None
    assert capsys.readouterr() == ("", "")


# Scope contracts reject undeclared fields and path/URL injection without accepting SDK kwargs.
@pytest.mark.parametrize(
    "field,value",
    [
        ("region", "https://example.test"),
        ("vault_ocid", "not-a-vault"),
        ("compartment_ocid", "ocid1.tenancy.oc1..synthetic"),
        ("endpoint", "https://example.test"),
    ],
)
def test_scope_contract(field, value):
    with pytest.raises(ValidationError):
        VaultReadScope.model_validate({**SCOPE.model_dump(), field: value})


# Both real SDK clients reuse exactly one workload signer and explicit regional TLS defaults.
def test_oke_factory_uses_only_workload_identity(monkeypatch):
    monkeypatch.setenv("OCI_RESOURCE_PRINCIPAL_REGION", SCOPE.region)
    with (
        patch.object(
            oci.auth.signers, "get_oke_workload_identity_resource_principal_signer"
        ) as signer,
        patch.object(oci.vault, "VaultsClient") as metadata,
        patch.object(oci.secrets, "SecretsClient") as bundles,
    ):
        reader = adapter.oke_vault_reader(SCOPE)
    assert reader.scope == SCOPE
    signer.assert_called_once()
    assert signer.call_args.kwargs["service_account_token_path"] == adapter.SERVICE_ACCOUNT_PATH
    assert signer.call_args.kwargs["log_requests"] is False
    assert isinstance(signer.call_args.kwargs["retry_strategy"], oci.retry.NoneRetryStrategy)
    for client in (metadata, bundles):
        assert client.call_args.args == ({"region": SCOPE.region},)
        assert client.call_args.kwargs["signer"] is signer.return_value
        assert client.call_args.kwargs["timeout"] == (5, 10)
        assert isinstance(client.call_args.kwargs["retry_strategy"], oci.retry.NoneRetryStrategy)
        assert isinstance(
            client.call_args.kwargs["circuit_breaker_strategy"],
            oci.circuit_breaker.NoCircuitBreakerStrategy,
        )
        assert "service_endpoint" not in client.call_args.kwargs


# Region mismatch/absence and unknown regions fail before any token exchange is attempted.
@pytest.mark.parametrize("region", [None, "us-phoenix-1", "unknown-region-1"])
def test_factory_region_guard(monkeypatch, region):
    monkeypatch.delenv("OCI_RESOURCE_PRINCIPAL_REGION", raising=False)
    scope = SCOPE
    if region is not None:
        monkeypatch.setenv("OCI_RESOURCE_PRINCIPAL_REGION", region)
    if region == "unknown-region-1":
        scope = SCOPE.model_copy(update={"region": region})
    with patch.object(
        oci.auth.signers, "get_oke_workload_identity_resource_principal_signer"
    ) as signer:
        with pytest.raises(VaultUnavailable, match="^OKE_VAULT_STARTUP_FAILED$"):
            adapter.oke_vault_reader(scope)
    signer.assert_not_called()


# Failure in identity exchange or either client constructor never falls back to another identity.
@pytest.mark.parametrize("failure", ["signer", "metadata", "bundle"])
def test_factory_failure_is_normalized(monkeypatch, failure):
    monkeypatch.setenv("OCI_RESOURCE_PRINCIPAL_REGION", SCOPE.region)
    with (
        patch.object(
            oci.auth.signers, "get_oke_workload_identity_resource_principal_signer"
        ) as signer,
        patch.object(oci.vault, "VaultsClient") as metadata,
        patch.object(oci.secrets, "SecretsClient") as bundles,
    ):
        {"signer": signer, "metadata": metadata, "bundle": bundles}[
            failure
        ].side_effect = RuntimeError("synthetic confidential SDK body")
        with pytest.raises(VaultUnavailable, match="^OKE_VAULT_STARTUP_FAILED$") as caught:
            adapter.oke_vault_reader(SCOPE)
    assert caught.value.__suppress_context__


# Exercise SDK argument/model wiring with real clients and intercept the HTTP boundary entirely.
def test_real_sdk_read_dispatch(monkeypatch, custody):
    monkeypatch.setenv("OCI_RESOURCE_PRINCIPAL_REGION", SCOPE.region)
    signer = Mock(spec=oci.auth.signers.SecurityTokenSigner)
    with patch.object(
        oci.auth.signers, "get_oke_workload_identity_resource_principal_signer", return_value=signer
    ):
        reader = adapter.oke_vault_reader(SCOPE)
    with (
        patch.object(
            reader.metadata_client.base_client,
            "call_api",
            return_value=SimpleNamespace(data=custody.metadata),
        ) as metadata,
        patch.object(
            reader.bundle_client.base_client,
            "call_api",
            return_value=SimpleNamespace(data=custody.bundle),
        ) as bundle,
    ):
        assert reader.current(TARGET_OCID).version_number == 7
    assert metadata.call_args.kwargs["path_params"] == {"secretId": TARGET_OCID}
    assert bundle.call_args.kwargs["path_params"] == {"secretId": TARGET_OCID}
    assert bundle.call_args.kwargs["query_params"]["stage"] == "CURRENT"
    assert metadata.call_args.kwargs["method"] == bundle.call_args.kwargs["method"] == "GET"
    reader.metadata_client.base_client.session.close()
    reader.bundle_client.base_client.session.close()
