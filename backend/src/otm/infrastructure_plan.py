"""Prepare private, non-applying Terraform plans using explicit GitHub-to-OCI federation."""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import ssl
import subprocess  # nosec B404
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
import oci

from otm.hosting_release import render_hosting_input
from otm.network_release import render_network_inputs
from otm.platform_version_release import render_platform_versions
from otm.worker_bootstrap_release import render_worker_inputs

ROOT = Path(__file__).resolve().parents[3]
# Standard exchange protocol identifiers are metadata, never token or credential values.
RPST_TYPE_URN = "urn:oci:token-type:oci-rpst"
JWT_TYPE = "jwt"
ENVIRONMENT_COMPONENTS = {
    "development": {"custody"},
    "staging": {"security", "platform"},
    "production": {"security", "platform"},
}
COMPONENT_FIELDS = {
    "custody": {"target"},
    "security": {"target", "database_provisioner_group_ocid"},
    "platform": {
        "target",
        "vcn_cidr",
        "oke",
        "database_administrator",
        "database",
        "application_vault_ocid",
        "qualified_node_image",
        "smtp_egress",
        "caddy_ingress_enabled",
    },
}


# OAuth and GitHub bearer credentials may never be forwarded to a redirected endpoint.
class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Reject all redirects, including same-host changes; only the configured endpoint is valid.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Duplicate keys cannot conceal a second target or alter the meaning of an approved input.
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_INPUT")
        result[key] = value
    return result


# Read bounded JSON only; no response or configuration text is included in public errors.
def decode_json(content, limit=131072):
    if not isinstance(content, (str, bytes)) or not 0 < len(content) <= limit:
        raise ValueError("BOUNDED_JSON_REQUIRED")
    return json.loads(content, object_pairs_hook=unique_object)


# Write new owner-only regular files; no output path can silently replace another candidate.
def private_write(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


# Canonical bytes bind the exact private inputs without publishing their values.
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


# Require the fixed workflow/environment and explicit enablement before generating or fetching
# secrets.
def context(environment, component, values):
    if component not in ENVIRONMENT_COMPONENTS.get(environment, ()):
        raise ValueError("FIXED_INFRASTRUCTURE_TARGET_REQUIRED")
    repository = values.get("GITHUB_REPOSITORY", "")
    source = values.get("GITHUB_SHA", "")
    if (
        values.get("OTM_INFRASTRUCTURE_ENABLED") != "true"
        or values.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or values.get("GITHUB_REF") != "refs/heads/master"
        or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None
        or values.get("GITHUB_WORKFLOW_REF")
        != f"{repository}/.github/workflows/infra-{environment}.yml@refs/heads/master"
        or re.fullmatch(r"[0-9a-f]{40}", source) is None
        or re.fullmatch(r"[1-9][0-9]{0,19}", values.get("GITHUB_RUN_ID", "")) is None
        or re.fullmatch(r"[1-9][0-9]{0,5}", values.get("GITHUB_RUN_ATTEMPT", "")) is None
    ):
        raise ValueError("PROTECTED_INFRASTRUCTURE_CONTEXT_REQUIRED")
    inputs = decode_json(values.get("OTM_INFRASTRUCTURE_INPUTS_JSON"))
    if not isinstance(inputs, dict) or not inputs or inputs.keys() - COMPONENT_FIELDS[component]:
        raise ValueError("INFRASTRUCTURE_INPUT_FIELDS_REJECTED")
    target = inputs.get("target")
    if (
        not isinstance(target, dict)
        or target.keys() != {"environment", "tenancy_ocid", "object_storage_namespace", "region"}
        or target["environment"] != environment
        or target["region"] != "us-ashburn-1"
        or not isinstance(target["tenancy_ocid"], str)
        or re.fullmatch(r"ocid1[.]tenancy[.]oc1[.][.][a-z0-9]{1,200}", target["tenancy_ocid"])
        is None
        or not isinstance(target["object_storage_namespace"], str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,254}", target["object_storage_namespace"]) is None
    ):
        raise ValueError("INFRASTRUCTURE_TARGET_REJECTED")
    return inputs


# Fixed-host, verified-TLS requests are bounded and never redirect credentials or log response
# bodies.
def request_json(url, headers, body=None):
    context = ssl.create_default_context(cafile=certifi.where())
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), NoRedirect())
    request = urllib.request.Request(url, headers=headers, data=body)
    with opener.open(request, timeout=25) as response:
        return decode_json(response.read(131073))


# Use a fresh standard RSA key pair; no persistent OCI user/signing key is created.
def signing_pair():
    executable = shutil.which("openssl")
    if not executable or not os.path.isabs(executable):
        raise ValueError("OPENSSL_REQUIRED")
    private = subprocess.run(  # nosec B603
        [executable, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
        check=True,
        capture_output=True,
        timeout=20,
        shell=False,
        env={"OPENSSL_CONF": os.devnull},
    ).stdout
    public = subprocess.run(  # nosec B603
        [executable, "pkey", "-pubout"],
        input=private,
        check=True,
        capture_output=True,
        timeout=20,
        shell=False,
        env={"OPENSSL_CONF": os.devnull},
    ).stdout
    if not private.startswith(b"-----BEGIN PRIVATE KEY-----") or not public.startswith(
        b"-----BEGIN PUBLIC KEY-----"
    ):
        raise ValueError("SIGNING_KEY_REQUIRED")
    return private, public


# OCI validates the signed GitHub claims; local checks do not substitute for the configured
# trust/IAM.
def federate(directory, target, environment, values, *, lifetime_minutes=60):
    if type(lifetime_minutes) is not int or lifetime_minutes not in (60, 120):
        raise ValueError("BOUNDED_FEDERATION_LIFETIME_REQUIRED")
    domain = values.get("OTM_INFRA_IDENTITY_DOMAIN_URL", "")
    endpoint = urllib.parse.urlsplit(values.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""))
    client_id, client_secret = (
        values.get("OTM_INFRA_CLIENT_ID"),
        values.get("OTM_INFRA_CLIENT_SECRET"),
    )
    bearer = values.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if (
        re.fullmatch(r"https://[a-z0-9-]+[.]identity[.]oraclecloud[.]com", domain) is None
        or endpoint.scheme != "https"
        or not endpoint.hostname
        or not endpoint.hostname.endswith(".actions.githubusercontent.com")
        or endpoint.username
        or endpoint.password
        or endpoint.port
        or endpoint.fragment
        or not all(
            isinstance(value, str)
            and 0 < len(value) <= 8192
            and "\n" not in value
            and "\r" not in value
            for value in (client_id, client_secret, bearer)
        )
    ):
        raise ValueError("FEDERATION_CONFIGURATION_REQUIRED")
    audience = "otm-infrastructure-" + environment
    query = urllib.parse.parse_qsl(endpoint.query, keep_blank_values=True)
    if any(key == "audience" for key, _ in query):
        raise ValueError("OIDC_AUDIENCE_ALREADY_SET")
    jwt_url = urllib.parse.urlunsplit(
        endpoint._replace(query=urllib.parse.urlencode(query + [("audience", audience)]))
    )
    issued = request_json(jwt_url, {"Authorization": "Bearer " + bearer})
    token = issued.get("value") if isinstance(issued, dict) else None
    if not isinstance(token, str) or not 0 < len(token) <= 65536:
        raise ValueError("GITHUB_ID_TOKEN_REQUIRED")
    private, public = signing_pair()
    basic = base64.b64encode((client_id + ":" + client_secret).encode()).decode()
    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "requested_token_type": RPST_TYPE_URN,
            "subject_token_type": JWT_TYPE,
            "subject_token": token,
            "public_key": public.decode("ascii"),
            "res_type": "githubactions",
            "rpst_exp": str(lifetime_minutes),
        }
    ).encode()
    exchanged = request_json(
        domain + "/oauth2/v1/token",
        {
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
    )
    rpst = exchanged.get("token") if isinstance(exchanged, dict) else None
    if not isinstance(rpst, str) or len(rpst) > 65536 or len(rpst.split(".")) != 3:
        raise ValueError("OCI_SESSION_TOKEN_REQUIRED")
    claims = decode_json(
        base64.urlsafe_b64decode(rpst.split(".")[1] + "=" * (-len(rpst.split(".")[1]) % 4))
    )
    # The response came from verified OCI TLS; inspecting its claims only fences target/lifetime
    # errors.
    if (
        not isinstance(claims, dict)
        or claims.get("res_tenant") != target["tenancy_ocid"]
        or type(claims.get("exp")) is not int
        or not time.time() + (lifetime_minutes - 25) * 60
        < claims["exp"]
        <= time.time() + (lifetime_minutes + 10) * 60
    ):
        raise ValueError("OCI_SESSION_TARGET_OR_LIFETIME_REJECTED")
    private_write(directory / "private.pem", private)
    private_write(directory / "rpst", rpst.encode())
    return {
        "OCI_RESOURCE_PRINCIPAL_VERSION": "2.2",
        "OCI_RESOURCE_PRINCIPAL_RPST": str(directory / "rpst"),
        "OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM": str(directory / "private.pem"),
        "OCI_RESOURCE_PRINCIPAL_REGION": target["region"],
    }


# Reuse existing private renderers; caller JSON cannot override auth, versions, compartment or
# cloud-init.
def render_inputs(directory, inputs, component, values):
    candidate = {**inputs, "oci_auth": "ResourcePrincipal"}
    private_write(directory / "inputs.tfvars.json", canonical(candidate))
    render_hosting_input(
        directory / "hosting.tfvars.json", values.get("OTM_HOSTING_COMPARTMENT_OCID")
    )
    if component == "platform":
        render_network_inputs(
            directory / "network.tfvars.json", values.get("OTM_ALLOWED_SOURCE_CIDRS")
        )
        render_platform_versions(
            directory / "versions.tfvars.json",
            values.get("OTM_OKE_KUBERNETES_VERSION"),
            values.get("OTM_POSTGRESQL_VERSION"),
        )
        render_worker_inputs(directory / "worker.tfvars.json", values.get("OTM_WORKER_CLOUD_INIT"))
    files = sorted(directory.glob("*.tfvars.json"))
    digest = hashlib.sha256(
        canonical({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
    ).hexdigest()
    return files, digest


# Strip ambient Terraform/OCI overrides and secrets; only the newly minted file-backed signer
# survives.
def terraform_environment(directory, credentials, values):
    result = {
        key: value
        for key, value in values.items()
        if not key.startswith(("OCI_", "TF_", "OTM_", "GH_", "GITHUB_", "ACTIONS_"))
    }
    private_write(directory / "terraform.rc", b"")
    result.update(credentials)
    result.update(
        {
            "TF_DATA_DIR": str(directory / "terraform-data"),
            "TF_CLI_CONFIG_FILE": str(directory / "terraform.rc"),
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
            "TF_WORKSPACE": "default",
        }
    )
    return result


# Never stream plans/provider errors to public CI logs; each command shares one bounded plan budget.
def terraform(command, arguments, root, environment, directory, deadline):
    remaining = int(deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError("INFRASTRUCTURE_PLAN_BUDGET_EXHAUSTED")
    result = subprocess.run(  # nosec B603
        [command, *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        timeout=remaining,
        shell=False,
    )
    with (directory / "terraform.log").open("ab") as stream:
        # Machine-readable plans/outputs can contain sensitive values and never belong in logs.
        machine_output = len(arguments) > 1 and arguments[1] == "-json"
        stream.write((b"" if machine_output else result.stdout) + result.stderr)
    if result.returncode:
        raise ValueError("TERRAFORM_PLAN_COMMAND_FAILED")
    return result.stdout


# Emit only action counts; all resource names, IDs, attributes and provider diagnostics stay
# private.
def change_counts(plan):
    if (
        not isinstance(plan, dict)
        or plan.get("errored") is True
        or not isinstance(plan.get("resource_changes", []), list)
    ):
        raise ValueError("TERRAFORM_PLAN_JSON_REQUIRED")
    result = {"create": 0, "update": 0, "delete": 0, "replace": 0}
    for resource in plan.get("resource_changes", []):
        actions = resource["change"]["actions"]
        if actions in (["create", "delete"], ["delete", "create"]):
            result["replace"] += 1
        elif actions in (["create"], ["update"], ["delete"]):
            result[actions[0]] += 1
        elif actions not in (["no-op"], ["read"]):
            raise ValueError("UNKNOWN_TERRAFORM_PLAN_ACTION")
    return result


# The shared private bucket boundary is used for plan upload and later exact-plan consumption.
def plan_storage(credentials, target, environment, hosting_compartment):
    signer = oci.auth.signers.EphemeralResourcePrincipalSigner(
        session_token=credentials["OCI_RESOURCE_PRINCIPAL_RPST"],
        private_key=credentials["OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM"],
        region=target["region"],
    )
    client = oci.object_storage.ObjectStorageClient(
        {"region": target["region"]},
        signer=signer,
        timeout=(10, 60),
        retry_strategy=oci.retry.NoneRetryStrategy(),
        log_requests=False,
    )
    namespace, bucket = target["object_storage_namespace"], "otm-" + environment + "-tfstate"
    metadata = client.get_bucket(namespace, bucket).data
    if (
        metadata.compartment_id != hosting_compartment
        or metadata.public_access_type != "NoPublicAccess"
        or metadata.versioning != "Enabled"
    ):
        raise ValueError("PRIVATE_ENVIRONMENT_PLAN_BUCKET_REQUIRED")
    return client, namespace, bucket


# Store secret-bearing plans only in the environment's verified private versioned state bucket.
def upload_plan(directory, credentials, target, environment, hosting_compartment, key):
    client, namespace, bucket = plan_storage(credentials, target, environment, hosting_compartment)
    with (directory / "plan.tar").open("rb") as stream:
        client.put_object(
            namespace,
            bucket,
            key,
            stream,
            if_none_match="*",
            content_type="application/x-tar",
            content_length=(directory / "plan.tar").stat().st_size,
        )


# Both plan and apply must use the exact checked-out workflow source and installed toolchain.
def checked_source(values):
    command = shutil.which("terraform")
    if not command or not os.path.isabs(command):
        raise ValueError("TERRAFORM_REQUIRED")
    git = shutil.which("git")
    if not git or not os.path.isabs(git):
        raise ValueError("GIT_REQUIRED")
    if (
        subprocess.check_output(  # nosec B603
            [git, "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10, shell=False
        ).strip()
        != values["GITHUB_SHA"]
    ):
        raise ValueError("EXACT_WORKFLOW_SOURCE_REQUIRED")
    return command


# Initialize only this environment's fixed backend with the minted signer and readonly provider
# lock.
def initialize_terraform(
    directory, root, command, inputs, environment, credentials, values, deadline
):
    child_env = terraform_environment(directory, credentials, values)
    backend = {
        "bucket": "otm-" + environment + "-tfstate",
        "namespace": inputs["target"]["object_storage_namespace"],
        "region": inputs["target"]["region"],
        "auth": "ResourcePrincipal",
    }
    private_write(directory / "backend.json", canonical(backend))
    version = decode_json(
        terraform(command, ["version", "-json"], root, child_env, directory, deadline)
    )
    if version.get("terraform_version") != "1.15.5":
        raise ValueError("EXACT_TERRAFORM_VERSION_REQUIRED")
    terraform(
        command,
        [
            "init",
            "-input=false",
            "-lockfile=readonly",
            "-no-color",
            "-backend-config=" + str(directory / "backend.json"),
        ],
        root,
        child_env,
        directory,
        deadline,
    )
    terraform(command, ["validate", "-no-color"], root, child_env, directory, deadline)
    return child_env


# Generate a plan without applying; shared setup does not introduce a mutable command selector.
def prepare_plan(environment, component, values):
    inputs = context(environment, component, values)
    command = checked_source(values)
    root = ROOT / "infra/environments" / environment / component
    previous_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix="otm-infrastructure-") as temporary:
            directory = Path(temporary)
            files, digest = render_inputs(directory, inputs, component, values)
            credentials = federate(directory, inputs["target"], environment, values)
            # Check development bucket placement and privacy before Terraform can create a lock.
            if environment == "development":
                plan_storage(
                    credentials,
                    inputs["target"],
                    environment,
                    values["OTM_HOSTING_COMPARTMENT_OCID"],
                )
            deadline = time.monotonic() + 1200
            child_env = initialize_terraform(
                directory, root, command, inputs, environment, credentials, values, deadline
            )
            terraform(
                command,
                [
                    "plan",
                    "-input=false",
                    "-no-color",
                    "-lock-timeout=60s",
                    "-out=" + str(directory / "plan.tfplan"),
                    *["-var-file=" + str(path) for path in files],
                ],
                root,
                child_env,
                directory,
                deadline,
            )
            plan = decode_json(
                terraform(
                    command,
                    ["show", "-json", str(directory / "plan.tfplan")],
                    root,
                    child_env,
                    directory,
                    deadline,
                ),
                limit=16777216,
            )
            receipt = {
                "status": "planned",
                "environment": environment,
                "component": component,
                "source_sha": values["GITHUB_SHA"],
                "run_id": values["GITHUB_RUN_ID"],
                "attempt": values["GITHUB_RUN_ATTEMPT"],
                "inputs_sha256": digest,
                "plan_sha256": hashlib.sha256((directory / "plan.tfplan").read_bytes()).hexdigest(),
                "changes": change_counts(plan),
            }
            key = (
                f"infrastructure-plans/{environment}/{component}/"
                f"{values['GITHUB_RUN_ID']}/{values['GITHUB_RUN_ATTEMPT']}/plan.tar"
            )
            with tarfile.open(directory / "plan.tar", "w") as archive:
                archive.add(directory / "plan.tfplan", arcname="plan.tfplan", recursive=False)
                member = tarfile.TarInfo("receipt.json")
                body = canonical(receipt)
                member.size, member.mode = len(body), 0o600
                archive.addfile(member, io.BytesIO(body))
            upload_plan(
                directory,
                credentials,
                inputs["target"],
                environment,
                values["OTM_HOSTING_COMPARTMENT_OCID"],
                key,
            )
            return {**receipt, "object_key": key, "applied": False}
    finally:
        os.umask(previous_umask)


# Public diagnostics never include private values, command output, credentials or raw provider
# errors.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=tuple(ENVIRONMENT_COMPONENTS), required=True)
    parser.add_argument("--component", choices=tuple(COMPONENT_FIELDS), required=True)
    options = parser.parse_args(argv)
    try:
        result = prepare_plan(options.environment, options.component, dict(os.environ))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "code": "INFRASTRUCTURE_PLAN_FAILED",
                    "guidance": (
                        "Check protected inputs, federation trust/IAM and private state access; "
                        "no infrastructure was applied by this command."
                    ),
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
