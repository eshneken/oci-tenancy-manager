"""Explicit platform SDK signing: private named laptop API-key profile or hosted OKE identity."""

import configparser
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

import oci

from otm.settings import ApplicationSettings

SERVICE_ACCOUNT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


# Keep SDK construction data internal; neither a local key nor its path appears in representations.
@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    client_config: dict = field(repr=False)
    signer: object = field(repr=False)


# Authentication failures contain no config contents, filenames, private keys or raw SDK errors.
class OciAuthenticationUnavailable(RuntimeError):
    pass


# Read bounded private regular files; no relative paths, symlink leaves, FIFOs or shared custody.
def private_text(filename):
    path = Path(filename).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("PRIVATE_OCI_FILE_REQUIRED")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_nlink != 1
            or not 0 < info.st_size <= 65536
        ):
            raise ValueError("PRIVATE_OCI_FILE_REQUIRED")
        content = stream.read(65537)
    if not 0 < len(content) <= 65536:
        raise ValueError("PRIVATE_OCI_FILE_REQUIRED")
    return content.decode("utf-8")


# Require a complete named API-key section; DEFAULT inheritance cannot choose another identity.
def api_key_signer(policy):
    parser = configparser.ConfigParser(interpolation=None, default_section="OTM_NO_INHERITANCE")
    parser.read_string(private_text(policy.config_file))
    if parser.defaults() or not parser.has_section(policy.profile):
        raise ValueError("EXPLICIT_OCI_PROFILE_REQUIRED")
    values = dict(parser[policy.profile])
    required = {"user", "tenancy", "fingerprint", "key_file", "region"}
    if not required <= values.keys() or values.keys() - required - {"pass_phrase"}:
        raise ValueError("COMPLETE_OCI_API_KEY_PROFILE_REQUIRED")
    if (
        values["tenancy"] != policy.tenancy_ocid
        or values["region"] != policy.region
        or re.fullmatch(r"ocid1\.user\.oc[0-9]+\.[a-z0-9.-]{1,220}", values["user"]) is None
        or re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){15}", values["fingerprint"]) is None
    ):
        raise ValueError("OCI_PROFILE_TARGET_MISMATCH")
    # Pass only explicit signer fields, not profile-controlled endpoints, logging or auth overrides.
    signer = oci.signer.Signer(
        tenancy=values["tenancy"],
        user=values["user"],
        fingerprint=values["fingerprint"].lower(),
        private_key_file_location=None,
        private_key_content=private_text(values["key_file"]),
        pass_phrase=values.get("pass_phrase"),
    )

    return PlatformIdentity(
        {key: values[key] for key in required} | {"fingerprint": values["fingerprint"].lower()},
        signer,
    )


# Keep one workload signer per composition; never select config files or node instance identity.
def oke_signer(region):
    if (
        region not in oci.regions.REGIONS
        or os.environ.get("OCI_RESOURCE_PRINCIPAL_REGION") != region
    ):
        raise ValueError("OKE_REGION_REQUIRED")
    return oci.auth.signers.get_oke_workload_identity_resource_principal_signer(
        service_account_token_path=SERVICE_ACCOUNT_PATH,
        retry_strategy=oci.retry.NoneRetryStrategy(),
        log_requests=False,
    )


# Revalidate the full trusted profile before loading any private file or exchanging an OKE token.
def platform_identity(settings):
    try:
        settings = ApplicationSettings.model_validate(settings)
        if settings.provider_mode != "oci" or settings.oci.region not in oci.regions.REGIONS:
            raise ValueError("EXPLICIT_OCI_CONFIGURATION_REQUIRED")
        if settings.oci.auth_method == "api_key_profile":
            return api_key_signer(settings.oci)
        return PlatformIdentity({"region": settings.oci.region}, oke_signer(settings.oci.region))
    except Exception:
        raise OciAuthenticationUnavailable("OCI_AUTHENTICATION_UNAVAILABLE") from None
