"""Return only encrypted workflow inputs to the Terraform external provider."""

import base64
import hashlib
import json
import os
import re
import stat
import subprocess  # nosec B404
import sys
from pathlib import Path

from nacl.public import PublicKey, SealedBox

ENVIRONMENTS = {"development", "staging", "production"}
AUTH = {
    "APIKey": "api_key",
    "SecurityToken": "security_token",
    "InstancePrincipal": "instance_principal",
    "ResourcePrincipal": "resource_principal",
}
PRIVATE_DIR = Path(__file__).resolve().parents[3] / ".local-dev"


# Local operator tools receive fixed arguments. Their diagnostics may contain credentials.
def invoke(args, *, body=None):
    # OCI receives only its own signer context and transport process settings. In particular the
    # operator GitHub credential and TF_VAR_* inputs must never cross this subprocess boundary.
    allowed = {
        "HOME",
        "PATH",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "OCI_CLI_CONFIG_FILE",
        "OCI_CLI_KEY_FILE",
        "OCI_CLI_PASSPHRASE",
        "OCI_CLI_SECURITY_TOKEN_FILE",
        "OCI_CLI_TENANCY",
        "OCI_CLI_USER",
        "OCI_CLI_FINGERPRINT",
        "OCI_CLI_REGION",
        "OCI_REGION",
        "OCI_CLI_CERT_BUNDLE",
    }
    child = {
        key: value
        for key, value in os.environ.items()
        if key in allowed
        or key.startswith(("OCI_RESOURCE_PRINCIPAL_", "OCI_INSTANCE_PRINCIPAL_"))
    }
    result = subprocess.run(  # nosec B603
        args, input=body, capture_output=True, env=child, timeout=45, check=False
    )
    if result.returncode or not 0 < len(result.stdout) < 256_000:
        raise ValueError("BOOTSTRAP_SEAL_TOOL_FAILED")
    return result.stdout


# A direct owner-only regular file supplies the environment's configuration; refuse aliases.
def read_settings(filename):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,126}[.]json", filename):
        raise ValueError("PRIVATE_CONFIGURATION_REQUIRED")
    directory = os.open(PRIVATE_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(
            filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
    finally:
        os.close(directory)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_nlink != 1
            or not 0 < info.st_size <= 256_000
        ):
            raise ValueError("PRIVATE_CONFIGURATION_REQUIRED")
        return json.loads(stream.read(256_001))


# Supply only a fixed, caller-selected projection to the exact regional GetApp.
def read_exchange(query, attributes):
    origin, app_id = query["domain_url"], query["app_id"]
    if not re.fullmatch(r"https://idcs-[a-z0-9]+\.identity\.oraclecloud\.com", origin):
        raise ValueError("DOMAIN_ORIGIN_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{32}", app_id):
        raise ValueError("EXACT_EXCHANGE_APP_REQUIRED")
    return json.loads(
        invoke(
            [
                "oci",
                "--endpoint",
                origin,
                "--auth",
                AUTH[query["oci_auth"]],
                "--profile",
                query["oci_profile"],
                "--cli-rc-file",
                os.devnull,
                "--output",
                "json",
                "identity-domains",
                "app",
                "get",
                "--app-id",
                app_id,
                "--attributes",
                attributes,
            ]
        )
    )["data"]


# Accept one restricted corporate workflow client at the exact immutable GUID.
def verified_exchange(query, extra_attributes):
    projection = (
        "id,name,displayName,allowedGrants,clientType,isOAuthClient,isOAuthResource,"
        "isLoginTarget,trustScope,allowedScopes,grantedAppRoles," + extra_attributes
    )
    app = read_exchange(query, projection)
    if (
        app["id"] != query["app_id"]
        or app["display-name"] != "otm-github-" + query["environment"]
        or app["allowed-grants"] != ["client_credentials"]
        or app["client-type"] != "confidential"
        or app["is-o-auth-client"] is not True
        or app["is-o-auth-resource"] is not False
        or app["is-login-target"] is not False
        or app["trust-scope"] != "Explicit"
        or app.get("allowed-scopes")
        or app.get("granted-app-roles")
        or not isinstance(app["name"], str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", app["name"])
    ):
        raise ValueError("EXACT_EXCHANGE_APP_REQUIRED")
    return app


# The development lookup requests metadata and exports only the verified client ID and name.
def development_exchange_metadata(query):
    if query["environment"] != "development" or query["oci_auth"] != "APIKey":
        raise ValueError("EXACT_EXCHANGE_APP_REQUIRED")
    app = verified_exchange(query, "active")
    if app["active"] is not True:
        raise ValueError("ACTIVE_EXCHANGE_APP_REQUIRED")
    return {"id": app["id"], "name": app["name"]}


# Export only the optional native group OCID from the protected development settings.
def development_group_adoption_pin(query):
    settings = read_settings(query["settings_file"])
    if (
        not isinstance(settings, dict)
        or settings.keys() != {"inputs"}
        or not isinstance(settings["inputs"], dict)
        or not isinstance(settings["inputs"].get("atlas_sso"), dict)
    ):
        raise ValueError("PRIVATE_CONFIGURATION_REQUIRED")
    atlas_sso = settings["inputs"]["atlas_sso"]
    if "adopt_group_ocid" not in atlas_sso:
        return {"ocid": ""}
    group_ocid = atlas_sso["adopt_group_ocid"]
    if not isinstance(group_ocid, str) or not re.fullmatch(
        r"ocid1\.group\.oc1\.\.[a-z0-9]{1,220}", group_ocid
    ):
        raise ValueError("EXACT_ADOPTION_GROUP_REQUIRED")
    return {"ocid": group_ocid}


# Only the sealing path requests a credential and checks the expected OAuth client identifier.
def exchange_secret(query):
    app = verified_exchange(query, "clientSecret")
    if (
        app["name"] != query["client_id"]
        or not isinstance(app["client-secret"], str)
        or not 16 <= len(app["client-secret"]) <= 8192
        or set(app["client-secret"]) == {"*"}
        or "\n" in app["client-secret"]
        or "\r" in app["client-secret"]
    ):
        raise ValueError("EXACT_EXCHANGE_APP_REQUIRED")
    return app["client-secret"]


# Seal exact bytes with the protected environment’s GitHub public key before returning to Terraform.
def seal(query):
    environment = query["environment"]
    if environment not in ENVIRONMENTS or not re.fullmatch(
        r"[a-zA-Z0-9-]{1,39}/[a-zA-Z0-9_.-]{1,100}", query["repository"]
    ):
        raise ValueError("GITHUB_ENVIRONMENT_REQUIRED")
    target = json.loads(query["target"])
    settings = read_settings(query["settings_file"])
    hosted = environment != "development"
    expected = (
        {"inputs", "allowed_source_cidrs", "worker_cloud_init"}
        if hosted
        else {"inputs"}
    )
    if (
        target["environment"] != environment
        or set(settings) != expected
        or "target" in settings["inputs"]
    ):
        raise ValueError("PRIVATE_CONFIGURATION_REQUIRED")
    settings_inputs = json.dumps(
        {**settings["inputs"], "target": target}, sort_keys=True
    )
    values = {
        "OTM_INFRASTRUCTURE_INPUTS_JSON": settings_inputs,
        "OTM_INFRA_IDENTITY_DOMAIN_URL": query["domain_url"],
        "OTM_INFRA_CLIENT_ID": query["client_id"],
        "OTM_HOSTING_COMPARTMENT_OCID": query["compartment_ocid"],
    }
    if hosted:
        values["OTM_ALLOWED_SOURCE_CIDRS"] = settings["allowed_source_cidrs"]
        values["OTM_WORKER_CLOUD_INIT"] = settings["worker_cloud_init"]
    box = SealedBox(PublicKey(base64.b64decode(query["public_key"], validate=True)))
    # The exchange password never enters the input fingerprint or any Terraform state or output.
    digest = hashlib.sha256(
        json.dumps([query, values], sort_keys=True).encode()
    ).hexdigest()
    values["OTM_INFRA_CLIENT_SECRET"] = exchange_secret(query)
    sealed = {}
    for name, value in values.items():
        if not isinstance(value, str) or not 0 < len(value.encode()) <= 48 * 1024:
            raise ValueError("WORKFLOW_INPUT_SIZE_REJECTED")
        sealed[name] = base64.b64encode(box.encrypt(value.encode())).decode("ascii")
    return {**sealed, "input_digest": digest}


# External provider output and errors must never echo CLI diagnostics or the private input file.
def main():
    try:
        query = json.loads(sys.stdin.buffer.read(131_073))
        if sys.argv[1:] == ["--development-exchange-metadata"]:
            result = development_exchange_metadata(query)
        elif sys.argv[1:] == ["--development-group-adoption-pin"]:
            result = development_group_adoption_pin(query)
        elif not sys.argv[1:]:
            result = seal(query)
        else:
            raise ValueError("UNKNOWN_MODE")
        print(json.dumps(result))
    except Exception:  # noqa: BLE001 -- preserve the secret boundary for all tool and decode failures.
        print("GITHUB_ENVIRONMENT_SEAL_FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
