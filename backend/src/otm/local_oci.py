"""Read-only OCI connection for the isolated laptop development application."""

from pathlib import Path
from urllib.parse import urlsplit

import oci
from sqlalchemy import text

from otm.platform_auth import OciAuthenticationUnavailable, platform_identity


# Require the OCI dev origin on the loopback IP and disable real recipient delivery.
def validate_local_oci(settings):
    server = settings.local_server
    origin = urlsplit(server.public_origin) if server else None
    override = settings.mail_policy().email_override
    if (
        settings.environment != "local"
        or settings.provider_mode != "oci"
        or settings.oci.auth_method != "api_key_profile"
        or origin is None
        or origin.hostname != "127.0.0.1"
        or origin.port in {None, 8443, 8444}
        or server.organization_reset_enabled
        or settings.notifications.enabled
        or not override
        or not override.lower().endswith(".test")
    ):
        raise ValueError("ISOLATED_LOCAL_OCI_CONFIGURATION_REQUIRED")


# Use an already verified enrollment scope or the default one-time OCI probe.
def oci_readiness(settings, engine, frontend, *, verified_enrollment=False):
    verified = verified_enrollment or probe_tenancy(settings, frontend)

    # Report startup OCI verification and check only the current database on every request.
    def ready():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return verified

    return ready


# Check the tenancy with the configured signer for development without enrollment enabled.
def probe_tenancy(settings, frontend):
    try:
        identity = platform_identity(settings)
    except OciAuthenticationUnavailable:
        return False
    policy = settings.oci
    if any(
        Path(filename).expanduser().resolve().is_relative_to(frontend.resolve())
        for filename in (policy.config_file, identity.client_config["key_file"])
    ):
        raise ValueError("OCI_CREDENTIALS_CANNOT_BE_PUBLIC")
    try:
        client = oci.identity.IdentityClient(
            dict(identity.client_config),
            signer=identity.signer,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(3, 5),
            log_requests=False,
        )
        return client.get_tenancy(policy.tenancy_ocid).data.id == policy.tenancy_ocid
    except Exception:
        return False
