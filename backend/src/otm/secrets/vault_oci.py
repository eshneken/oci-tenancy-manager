"""Read-only OCI Vault custody using explicit platform identity; no fallback or cloud writes."""

import base64
import os

import oci
from pydantic import SecretStr, TypeAdapter

from otm.platform_auth import platform_identity
from otm.secrets.contracts import SecretOcid, VaultReadScope, VaultSecretValue, VaultUnavailable
from otm.settings import ApplicationSettings

MAX_SECRET_BYTES = 25000
SERVICE_ACCOUNT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SECRET_ID = TypeAdapter(SecretOcid)


# Metadata scope is checked before secret bytes are requested, even if IAM grants are too broad.
class OciVaultReader:
    # Clients are supplied only by trusted server composition or synthetic test fixtures.
    def __init__(self, scope, metadata_client, bundle_client):
        self.scope = VaultReadScope.model_validate(scope)
        self.metadata_client = metadata_client
        self.bundle_client = bundle_client

    # CURRENT is resolved for every read, so rotations never depend on a cached version pointer.
    def current(self, secret_ocid):
        return self._read(secret_ocid, None)

    # Immutable consumers such as MFA may request only an explicit positive numeric version.
    def version(self, secret_ocid, version_number):
        if type(version_number) is not int or version_number < 1:
            raise VaultUnavailable("VAULT_SECRET_UNAVAILABLE")
        return self._read(secret_ocid, version_number)

    # Reject wrong scope/state/identity/version and malformed or oversized content without logging.
    def _read(self, secret_ocid, version_number):
        try:
            secret_ocid = SECRET_ID.validate_python(secret_ocid, strict=True)
            metadata = self.metadata_client.get_secret(
                secret_ocid, retry_strategy=oci.retry.NoneRetryStrategy()
            ).data
            if (
                metadata.id != secret_ocid
                or metadata.vault_id != self.scope.vault_ocid
                or metadata.compartment_id != self.scope.compartment_ocid
                or metadata.lifecycle_state != "ACTIVE"
            ):
                raise ValueError("VAULT_SCOPE_MISMATCH")
            selection = (
                {"stage": "CURRENT"}
                if version_number is None
                else {"version_number": version_number}
            )
            bundle = self.bundle_client.get_secret_bundle(
                secret_ocid, retry_strategy=oci.retry.NoneRetryStrategy(), **selection
            ).data
            if (
                bundle.secret_id != secret_ocid
                or type(bundle.version_number) is not int
                or bundle.version_number < 1
                or (version_number is not None and bundle.version_number != version_number)
                or (version_number is None and "CURRENT" not in (bundle.stages or []))
            ):
                raise ValueError("VAULT_VERSION_MISMATCH")
            content = bundle.secret_bundle_content
            if (
                content.content_type != "BASE64"
                or not isinstance(content.content, str)
                or not 0 < len(content.content) <= 4 * ((MAX_SECRET_BYTES + 2) // 3)
            ):
                raise ValueError("VAULT_CONTENT_INVALID")
            raw = base64.b64decode(content.content, validate=True)
            if not 0 < len(raw) <= MAX_SECRET_BYTES or b"\0" in raw:
                raise ValueError("VAULT_CONTENT_INVALID")
            value = raw.decode("utf-8")
            return VaultSecretValue(secret_ocid, bundle.version_number, SecretStr(value))
        except Exception:
            raise VaultUnavailable("VAULT_SECRET_UNAVAILABLE") from None


# One signer is reused by both clients; credentials never come from ~/.oci or instance principals.
# Construction intentionally contacts OKE only when explicitly invoked by hosted composition.
def oke_vault_reader(scope):
    try:
        scope = VaultReadScope.model_validate(scope)
        if (
            scope.region not in oci.regions.REGIONS
            or os.environ.get("OCI_RESOURCE_PRINCIPAL_REGION") != scope.region
        ):
            raise ValueError("OKE_REGION_REQUIRED")
        signer = oci.auth.signers.get_oke_workload_identity_resource_principal_signer(
            service_account_token_path=SERVICE_ACCOUNT_PATH,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            log_requests=False,
        )
        options = {
            "signer": signer,
            "timeout": (5, 10),
            "retry_strategy": oci.retry.NoneRetryStrategy(),
            "circuit_breaker_strategy": oci.circuit_breaker.NoCircuitBreakerStrategy(),
        }
        metadata = oci.vault.VaultsClient({"region": scope.region}, **options)
        bundles = oci.secrets.SecretsClient({"region": scope.region}, **options)
        return OciVaultReader(scope, metadata, bundles)
    except Exception:
        raise VaultUnavailable("OKE_VAULT_STARTUP_FAILED") from None


# A configured laptop/hosted identity uses the same reader and guards, never another custody path.
def configured_vault_reader(settings, scope):
    try:
        settings = ApplicationSettings.model_validate(settings)
        scope = VaultReadScope.model_validate(scope)
        if settings.oci is None or settings.oci.region != scope.region:
            raise ValueError("VAULT_IDENTITY_REGION_MISMATCH")
        identity = platform_identity(settings)
        options = {
            "signer": identity.signer,
            "timeout": (5, 10),
            "retry_strategy": oci.retry.NoneRetryStrategy(),
            "circuit_breaker_strategy": oci.circuit_breaker.NoCircuitBreakerStrategy(),
        }
        return OciVaultReader(
            scope,
            oci.vault.VaultsClient(dict(identity.client_config), **options),
            oci.secrets.SecretsClient(dict(identity.client_config), **options),
        )
    except Exception:
        raise VaultUnavailable("CONFIGURED_VAULT_STARTUP_FAILED") from None
