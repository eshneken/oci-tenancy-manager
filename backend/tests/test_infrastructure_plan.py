"""Prove held plan-only delivery, private custody and explicit federation without OCI access."""

import base64
import io
import json
import os
import runpy
import stat
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from cryptography.hazmat.primitives import serialization

from otm import infrastructure_plan as module

SHA = "a" * 40
TENANCY = "ocid1.tenancy.oc1..synthetic"
COMPARTMENT = "ocid1.compartment.oc1..synthetic"


# Synthetic protected settings exercise both fixed roots; no actual employee or cloud identity
# exists.
def environment_values(environment="staging", component="security"):
    target = {
        "environment": environment,
        "tenancy_ocid": TENANCY,
        "region": "us-ashburn-1",
        "object_storage_namespace": "synthetic",
    }
    inputs = {"target": target, "database_provisioner_group_ocid": "ocid1.group.oc1..synthetic"}
    if component == "platform":
        inputs = {
            "target": target,
            "vcn_cidr": "10.80.0.0/16",
            "oke": {"availability_domains": ["synthetic:AD1"]},
            "database_administrator": {
                "username": "provisioner",
                "secret_ocid": ".".join(("ocid1", "vaultsecret", "oc1", "iad", "synthetic")),
                "secret_version": "1",
            },
            "database": {"backup_start_utc": "02:00", "maintenance_start_utc": "SUN 03:00"},
            "application_vault_ocid": "ocid1.vault.oc1.iad.synthetic",
        }
    return {
        "OTM_INFRASTRUCTURE_ENABLED": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/master",
        "GITHUB_SHA": SHA,
        "GITHUB_REPOSITORY": "example/tenancy-manager",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": (
            f"example/tenancy-manager/.github/workflows/infra-{environment}.yml@refs/heads/master"
        ),
        "OTM_INFRASTRUCTURE_INPUTS_JSON": json.dumps(inputs),
        "OTM_INFRA_IDENTITY_DOMAIN_URL": "https://idcs-synthetic.identity.oraclecloud.com",
        "OTM_INFRA_CLIENT_ID": "synthetic-client",
        "OTM_INFRA_CLIENT_SECRET": "synthetic" + "-client-credential",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://vstoken.actions.githubusercontent.com/job?api-version=2.0",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic" + "-job-credential",
        "ACTIONS_RUNTIME_TOKEN": "synthetic" + "-artifact-credential",
        "OTM_HOSTING_COMPARTMENT_OCID": COMPARTMENT,
        "OTM_ALLOWED_SOURCE_CIDRS": "192.0.2.1/32",
        "OTM_OKE_KUBERNETES_VERSION": "v1.37.1",
        "OTM_POSTGRESQL_VERSION": "16",
        "OTM_WORKER_CLOUD_INIT": "#!/bin/bash\ntrue\n",
        "PATH": "/usr/bin:/bin",
        "HOME": "/synthetic",
        "TF_CLI_ARGS": "unapproved",
        "OCI_PRIVATE_KEY": "unapproved",
    }


# Opaque signatures are never treated as locally verified; the exchange response is a TLS fixture.
def rpst(**overrides):
    claims = {"res_tenant": TENANCY, "exp": int(time.time()) + 3600, **overrides}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "eyJhbGciOiJSUzI1NiJ9." + payload + ".c3ludGhldGlj"


# Standard bounded JSON and duplicate rejection apply recursively to protected inputs and responses.
@pytest.mark.parametrize(
    "content",
    [None, "", b"", "x" * 131073, '{"target":1,"target":2}', '{"a":{"b":1,"b":2}}', "not-json"],
)
def test_invalid_json(content):
    with pytest.raises((ValueError, TypeError)):
        module.decode_json(content)


# A disabled, wrong-branch, wrong-workflow or malformed context cannot start federation or write
# files.
@pytest.mark.parametrize(
    "key,value",
    [
        ("OTM_INFRASTRUCTURE_ENABLED", "false"),
        ("OTM_INFRASTRUCTURE_ENABLED", "TRUE"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_REPOSITORY", "../untrusted"),
        ("GITHUB_SHA", "short"),
        ("GITHUB_RUN_ID", "123;false"),
        ("GITHUB_RUN_ATTEMPT", "0"),
        (
            "GITHUB_WORKFLOW_REF",
            "example/tenancy-manager/.github/workflows/build-application.yml@refs/heads/master",
        ),
    ],
)
def test_context_rejects_unapproved_job(key, value):
    values = environment_values()
    values[key] = value
    with pytest.raises(ValueError, match="PROTECTED_INFRASTRUCTURE_CONTEXT_REQUIRED"):
        module.context("staging", "security", values)


# No user-selectable root, environment or auth field can escape the fixed source and signer
# contract.
@pytest.mark.parametrize(
    "environment,component",
    [("development", "security"), ("staging", "../platform"), ("production", "bootstrap")],
)
def test_context_fixed_roots(environment, component):
    with pytest.raises(ValueError, match="FIXED_INFRASTRUCTURE_TARGET_REQUIRED"):
        module.context(environment, component, environment_values())


# Root JSON cannot smuggle another backend/auth selector or a different environment target.
@pytest.mark.parametrize(
    "fault",
    [
        "list",
        "empty",
        "extra",
        "target-missing",
        "target-extra",
        "wrong-environment",
        "wrong-region",
        "wrong-tenancy",
        "wrong-namespace",
        "tenancy-type",
        "namespace-type",
    ],
)
def test_context_private_input_guard(fault):
    values = environment_values()
    inputs = json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])
    if fault == "list":
        inputs = []
    elif fault == "empty":
        inputs = {}
    elif fault == "extra":
        inputs["oci_auth"] = "APIKey"
    elif fault == "target-missing":
        del inputs["target"]
    elif fault == "target-extra":
        inputs["target"]["endpoint"] = "http://example.test"
    else:
        field, value = {
            "wrong-environment": ("environment", "production"),
            "wrong-region": ("region", "other-region"),
            "wrong-tenancy": ("tenancy_ocid", "not-an-ocid"),
            "wrong-namespace": ("object_storage_namespace", "../namespace"),
            "tenancy-type": ("tenancy_ocid", 1),
            "namespace-type": ("object_storage_namespace", None),
        }[fault]
        inputs["target"][field] = value
    values["OTM_INFRASTRUCTURE_INPUTS_JSON"] = json.dumps(inputs)
    with pytest.raises(ValueError):
        module.context("staging", "security", values)


# All renderers preserve separate protected values and create only owner-readable candidate files.
@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("component", ["security", "platform"])
def test_render_inputs(tmp_path, environment, component):
    values = environment_values(environment, component)
    inputs = module.context(environment, component, values)
    files, digest = module.render_inputs(tmp_path, inputs, component, values)
    assert len(files) == (2 if component == "security" else 5)
    assert len(digest) == 64
    assert (
        json.loads((tmp_path / "inputs.tfvars.json").read_text())["oci_auth"] == "ResourcePrincipal"
    )
    for file in files:
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert json.loads((tmp_path / "hosting.tfvars.json").read_text()) == {
        "hosting_compartment_ocid": COMPARTMENT
    }
    with pytest.raises(FileExistsError):
        module.render_inputs(tmp_path, inputs, component, values)


# Existing files and symlink leaves are never replaced when staging private material.
def test_private_write_preserves_targets(tmp_path):
    file = tmp_path / "preserve"
    file.write_bytes(b"unchanged")
    alias = tmp_path / "alias"
    alias.symlink_to(file)
    for path in (file, alias):
        with pytest.raises(FileExistsError):
            module.private_write(path, b"replacement")
    assert file.read_bytes() == b"unchanged"


# Terraform subprocesses inherit no ambient signer, CLI override, OAuth secret or GitHub token.
def test_terraform_environment(tmp_path):
    values = environment_values()
    credentials = {"OCI_RESOURCE_PRINCIPAL_VERSION": "2.2"}
    result = module.terraform_environment(tmp_path, credentials, values)
    assert result["HOME"] == "/synthetic" and result["PATH"] == "/usr/bin:/bin"
    assert result["TF_WORKSPACE"] == "default" and result["TF_INPUT"] == "0"
    assert result["OCI_RESOURCE_PRINCIPAL_VERSION"] == "2.2"
    assert "OCI_PRIVATE_KEY" not in result and "TF_CLI_ARGS" not in result
    assert not any(key.startswith(("GH_", "GITHUB_", "OTM_", "ACTIONS_")) for key in result)
    assert stat.S_IMODE((tmp_path / "terraform.rc").stat().st_mode) == 0o600


# Authenticated network I/O uses a fixed timeout, bounded JSON, verified TLS and no redirect
# handler.
def test_request_json(monkeypatch):
    response = io.BytesIO(b'{"token":"synthetic"}')
    opener = Mock()
    opener.open.return_value = response
    builder = Mock(return_value=opener)
    monkeypatch.setattr(module.urllib.request, "build_opener", builder)
    assert module.request_json(
        "https://example.test", {"Authorization": "synthetic"}, b"payload"
    ) == {"token": "synthetic"}
    https, redirects = builder.call_args.args
    assert (
        https._context.check_hostname is True
        and https._context.verify_mode == module.ssl.CERT_REQUIRED
    )
    assert redirects.redirect_request(None, None, 302, "redirect", {}, "https://other.test") is None
    request = opener.open.call_args.args[0]
    assert request.data == b"payload" and request.get_header("Authorization") == "synthetic"
    assert opener.open.call_args.kwargs == {"timeout": 25}
    assert response.closed


# A real standard OpenSSL pair is generated locally without a network, persistent OCI key or shell.
def test_real_signing_pair():
    private, public = module.signing_pair()
    key = serialization.load_pem_private_key(private, password=None)
    counterpart = serialization.load_pem_public_key(public)
    assert key.key_size == counterpart.key_size == 2048
    assert key.public_key().public_numbers() == counterpart.public_numbers()


# Missing/invalid executables and malformed key output fail closed rather than minting a credential.
@pytest.mark.parametrize("fault", ["missing", "relative", "private", "public"])
def test_signing_pair_guards(monkeypatch, fault):
    private, public = module.signing_pair()
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: (
            None if fault == "missing" else "openssl" if fault == "relative" else "/usr/bin/openssl"
        ),
    )
    execute = Mock(
        side_effect=[
            SimpleNamespace(stdout=b"bad" if fault == "private" else private),
            SimpleNamespace(stdout=b"bad" if fault == "public" else public),
        ]
    )
    monkeypatch.setattr(module.subprocess, "run", execute)
    with pytest.raises(ValueError):
        module.signing_pair()
    if fault in {"missing", "relative"}:
        execute.assert_not_called()


# A synthetic OCI response demonstrates matching PEM custody and both Terraform auth consumers.
def test_federation(tmp_path, monkeypatch):
    values = environment_values()
    target = json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"]
    request = Mock(side_effect=[{"value": "synthetic-jwt"}, {"token": rpst()}])
    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "signing_pair", lambda: (b"private-synthetic", b"public-synthetic"))
    credentials = module.federate(tmp_path, target, "staging", values)
    assert credentials["OCI_RESOURCE_PRINCIPAL_VERSION"] == "2.2"
    assert credentials["OCI_RESOURCE_PRINCIPAL_REGION"] == "us-ashburn-1"
    assert (
        Path(credentials["OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM"]).read_bytes() == b"private-synthetic"
    )
    assert stat.S_IMODE(Path(credentials["OCI_RESOURCE_PRINCIPAL_RPST"]).stat().st_mode) == 0o600
    first, second = request.call_args_list
    assert "audience=otm-infrastructure-staging" in first.args[0]
    assert first.args[1]["Authorization"] == "Bearer " + values["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    assert second.args[0] == values["OTM_INFRA_IDENTITY_DOMAIN_URL"] + "/oauth2/v1/token"
    payload = module.urllib.parse.parse_qs(second.args[2].decode())
    assert payload["public_key"] == ["public-synthetic"] and payload["rpst_exp"] == ["60"]
    assert payload["requested_token_type"] == ["urn:oci:token-type:oci-rpst"]
    assert payload["res_type"] == ["githubactions"]
    assert "private-synthetic" not in str(request.call_args_list)


# The installed SDK accepts our actual ephemeral PEM/token files without making any OCI request.
def test_real_sdk_file_backed_signer(tmp_path, monkeypatch):
    values = environment_values()
    target = json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"]
    monkeypatch.setattr(
        module, "request_json", Mock(side_effect=[{"value": "synthetic-jwt"}, {"token": rpst()}])
    )
    network = Mock(side_effect=AssertionError("no OCI calls in SDK-construction test"))
    monkeypatch.setattr(module.oci.base_client.BaseClient, "call_api", network)
    credentials = module.federate(tmp_path, target, "staging", values)
    signer = module.oci.auth.signers.EphemeralResourcePrincipalSigner(
        session_token=credentials["OCI_RESOURCE_PRINCIPAL_RPST"],
        private_key=credentials["OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM"],
        region=target["region"],
    )
    client = module.oci.object_storage.ObjectStorageClient(
        {"region": target["region"]},
        signer=signer,
        timeout=(10, 60),
        retry_strategy=module.oci.retry.NoneRetryStrategy(),
        log_requests=False,
    )
    assert signer.tenancy_id == TENANCY
    assert client.base_client.signer is signer
    # The SDK retains its dual-stack template until request time; region binding is already fixed.
    assert client.base_client.endpoint.startswith("https://objectstorage.us-ashburn-1.")
    network.assert_not_called()


# URLs and credentials are validated before either authorization header can be sent.
@pytest.mark.parametrize(
    "key,value",
    [
        ("OTM_INFRA_IDENTITY_DOMAIN_URL", "http://idcs-synthetic.identity.oraclecloud.com"),
        ("OTM_INFRA_IDENTITY_DOMAIN_URL", "https://example.test"),
        ("OTM_INFRA_IDENTITY_DOMAIN_URL", "https://idcs-synthetic.identity.oraclecloud.com/path"),
        ("ACTIONS_ID_TOKEN_REQUEST_URL", "http://vstoken.actions.githubusercontent.com/token"),
        ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://example.test/token"),
        (
            "ACTIONS_ID_TOKEN_REQUEST_URL",
            "https://user" + chr(64) + "vstoken.actions.githubusercontent.com/token",
        ),
        ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://vstoken.actions.githubusercontent.com:443/token"),
        (
            "ACTIONS_ID_TOKEN_REQUEST_URL",
            "https://vstoken.actions.githubusercontent.com/token#fragment",
        ),
        (
            "ACTIONS_ID_TOKEN_REQUEST_URL",
            "https://vstoken.actions.githubusercontent.com/token?audience=other",
        ),
        ("OTM_INFRA_CLIENT_ID", None),
        ("OTM_INFRA_CLIENT_SECRET", ""),
        ("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "header\ninjection"),
        ("OTM_INFRA_CLIENT_SECRET", "x" * 8193),
    ],
)
def test_federation_configuration_guards(tmp_path, monkeypatch, key, value):
    values = environment_values()
    values[key] = value
    request = Mock()
    monkeypatch.setattr(module, "request_json", request)
    with pytest.raises(ValueError):
        module.federate(
            tmp_path,
            json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"],
            "staging",
            values,
        )
    request.assert_not_called()
    assert not list(tmp_path.iterdir())


# Empty/malformed responses, mismatched tenancy and insufficient session lifetime produce no files.
@pytest.mark.parametrize(
    "fault",
    [
        "github-list",
        "github-empty",
        "github-long",
        "oci-list",
        "oci-empty",
        "oci-long",
        "oci-format",
        "wrong-tenancy",
        "expired",
        "too-long",
        "expiry-type",
    ],
)
def test_federation_response_guards(tmp_path, monkeypatch, fault):
    github = {"value": "synthetic-jwt"}
    exchanged = {"token": rpst()}
    if fault.startswith("github-"):
        github = (
            []
            if fault == "github-list"
            else {"value": "" if fault == "github-empty" else "x" * 65537}
        )
    elif fault.startswith("oci-"):
        exchanged = (
            []
            if fault == "oci-list"
            else {
                "token": {"oci-empty": None, "oci-long": "x" * 65537, "oci-format": "not-a-jwt"}[
                    fault
                ]
            }
        )
    else:
        claims = {
            "wrong-tenancy": {"res_tenant": "other"},
            "expired": {"exp": int(time.time()) - 1},
            "too-long": {"exp": int(time.time()) + 10000},
            "expiry-type": {"exp": "3600"},
        }[fault]
        exchanged = {"token": rpst(**claims)}
    monkeypatch.setattr(module, "request_json", Mock(side_effect=[github, exchanged]))
    monkeypatch.setattr(module, "signing_pair", lambda: (b"private", b"public"))
    values = environment_values()
    with pytest.raises(ValueError):
        module.federate(
            tmp_path,
            json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"],
            "staging",
            values,
        )
    assert not list(tmp_path.iterdir())


# Subprocess failures remain private and use one deadline without executing shell input.
def test_terraform_command_and_budget(tmp_path, monkeypatch):
    execute = Mock(
        return_value=SimpleNamespace(
            stdout=b"private-output", stderr=b"private-error", returncode=0
        )
    )
    monkeypatch.setattr(module.subprocess, "run", execute)
    deadline = time.monotonic() + 10
    assert (
        module.terraform(
            "/usr/bin/terraform", ["version", "-json"], tmp_path, {}, tmp_path, deadline
        )
        == b"private-output"
    )
    assert execute.call_args.args[0] == ["/usr/bin/terraform", "version", "-json"]
    assert execute.call_args.kwargs["shell"] is False
    assert 0 < execute.call_args.kwargs["timeout"] <= 10
    assert (tmp_path / "terraform.log").read_bytes() == b"private-error"
    execute.return_value.returncode = 1
    with pytest.raises(ValueError, match="TERRAFORM_PLAN_COMMAND_FAILED"):
        module.terraform("/usr/bin/terraform", ["plan"], tmp_path, {}, tmp_path, deadline)
    with pytest.raises(TimeoutError):
        module.terraform(
            "/usr/bin/terraform", ["plan"], tmp_path, {}, tmp_path, time.monotonic() - 1
        )
    assert (tmp_path / "terraform.log").read_bytes().count(b"private-error") == 2


# Only complete known action shapes are summarized; raw resource identities never leave the plan.
def test_change_counts():
    actions = [
        ["create"],
        ["update"],
        ["delete"],
        ["delete", "create"],
        ["create", "delete"],
        ["no-op"],
        ["read"],
    ]
    plan = {
        "resource_changes": [
            {"address": "private-name", "change": {"actions": value}} for value in actions
        ]
    }
    assert module.change_counts(plan) == {"create": 1, "update": 1, "delete": 1, "replace": 2}
    assert module.change_counts({}) == dict.fromkeys(("create", "update", "delete", "replace"), 0)
    for invalid in (
        [],
        {"errored": True},
        {"resource_changes": None},
        {"resource_changes": [{"change": {"actions": ["future"]}}]},
    ):
        with pytest.raises(ValueError):
            module.change_counts(invalid)


# Private bucket checks and conditional object creation prevent public, cross-compartment or
# overwrite custody.
@pytest.mark.parametrize("fault", [None, "compartment", "public", "versioning", "upload"])
def test_private_plan_upload(tmp_path, monkeypatch, fault):
    values = environment_values()
    target = json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"]
    credentials = {
        "OCI_RESOURCE_PRINCIPAL_RPST": "/private/token",
        "OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM": "/private/key",
    }
    signer = Mock(return_value=object())
    constructor = Mock()
    client = constructor.return_value
    client.get_bucket.return_value.data = SimpleNamespace(
        compartment_id="other" if fault == "compartment" else COMPARTMENT,
        public_access_type="ObjectRead" if fault == "public" else "NoPublicAccess",
        versioning="Disabled" if fault == "versioning" else "Enabled",
    )
    if fault == "upload":
        client.put_object.side_effect = RuntimeError("uncertain upload")
    monkeypatch.setattr(module.oci.auth.signers, "EphemeralResourcePrincipalSigner", signer)
    monkeypatch.setattr(module.oci.object_storage, "ObjectStorageClient", constructor)
    (tmp_path / "plan.tar").write_bytes(b"private-plan")
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            module.upload_plan(tmp_path, credentials, target, "staging", COMPARTMENT, "fixed-key")
    else:
        module.upload_plan(tmp_path, credentials, target, "staging", COMPARTMENT, "fixed-key")
        args = client.put_object.call_args
        assert args.args[:3] == ("synthetic", "otm-staging-tfstate", "fixed-key")
        assert args.kwargs == {
            "if_none_match": "*",
            "content_type": "application/x-tar",
            "content_length": 12,
        }
        assert args.args[3].closed
    if fault in {"compartment", "public", "versioning"}:
        client.put_object.assert_not_called()
    assert constructor.call_args.kwargs["timeout"] == (10, 60)
    assert constructor.call_args.kwargs["log_requests"] is False


# Drive actual rendering, federation/file custody, tar creation and cleanup with only remote effects
# mocked.
@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("component", ["security", "platform"])
@pytest.mark.parametrize("fault", [None, "version", "plan", "upload"])
def test_prepare_full_plan(monkeypatch, environment, component, fault):
    values = environment_values(environment, component)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: SHA + "\n")
    monkeypatch.setattr(
        module, "request_json", Mock(side_effect=[{"value": "synthetic-jwt"}, {"token": rpst()}])
    )
    monkeypatch.setattr(module, "signing_pair", lambda: (b"private-synthetic", b"public-synthetic"))
    calls, directories = [], []

    # Assert the real orchestration's command arguments and create only a synthetic binary plan.
    def fake_terraform(executable, arguments, root, child_env, directory, deadline):
        assert (
            executable == "/usr/bin/terraform"
            and root == module.ROOT / "infra/environments" / environment / component
        )
        assert "OTM_INFRA_CLIENT_SECRET" not in child_env and "TF_CLI_ARGS" not in child_env
        assert (
            Path(child_env["OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM"]).read_bytes()
            == b"private-synthetic"
        )
        assert json.loads((directory / "backend.json").read_text())["auth"] == "ResourcePrincipal"
        calls.append(arguments)
        directories.append(directory)
        if arguments[0] == "version":
            return json.dumps(
                {"terraform_version": "1.0.0" if fault == "version" else "1.15.5"}
            ).encode()
        if arguments[0] == "plan":
            if fault == "plan":
                raise RuntimeError("private provider failure")
            (directory / "plan.tfplan").write_bytes(b"synthetic-plan")
        if arguments[0] == "show":
            return b'{"resource_changes":[{"change":{"actions":["create"]}}]}'
        return b""

    # Inspect the exact two-file private archive before it leaves temporary custody.
    def fake_upload(directory, credentials, target, selected_environment, compartment, key):
        assert selected_environment == environment and compartment == COMPARTMENT
        assert key == f"infrastructure-plans/{environment}/{component}/123/1/plan.tar"
        with tarfile.open(directory / "plan.tar") as archive:
            assert archive.getnames() == ["plan.tfplan", "receipt.json"]
            assert archive.extractfile("plan.tfplan").read() == b"synthetic-plan"
            receipt = json.load(archive.extractfile("receipt.json"))
            assert receipt["changes"]["create"] == 1
            assert "private-synthetic" not in json.dumps(receipt) and "tenancy_ocid" not in receipt
        if fault == "upload":
            raise RuntimeError("private storage failure")

    monkeypatch.setattr(module, "terraform", fake_terraform)
    monkeypatch.setattr(module, "upload_plan", fake_upload)
    old_mask = os.umask(0o027)
    try:
        if fault:
            with pytest.raises((ValueError, RuntimeError)):
                module.prepare_plan(environment, component, values)
        else:
            result = module.prepare_plan(environment, component, values)
            assert result["status"] == "planned" and result["applied"] is False
            assert result["source_sha"] == SHA and len(result["plan_sha256"]) == 64
            assert [args[0] for args in calls] == ["version", "init", "validate", "plan", "show"]
            assert "-lockfile=readonly" in calls[1] and "-lock-timeout=60s" in calls[3]
            assert len([arg for arg in calls[3] if arg.startswith("-var-file=")]) == (
                2 if component == "security" else 5
            )
        assert os.umask(0o027) == 0o027
    finally:
        os.umask(old_mask)
    assert directories and not any(path.exists() for path in directories)


# Missing Terraform or a checkout different from the workflow SHA fails before any exchange.
@pytest.mark.parametrize("fault", ["missing", "relative", "git-missing", "git-relative", "source"])
def test_prepare_preflight_guards(monkeypatch, fault):
    # Missing or relative Git fails independently of a valid Terraform executable.
    def resolve(name):
        if name == "git":
            return (
                None
                if fault == "git-missing"
                else "git"
                if fault == "git-relative"
                else "/usr/bin/git"
            )
        return (
            None
            if fault == "missing"
            else "terraform"
            if fault == "relative"
            else "/usr/bin/terraform"
        )

    monkeypatch.setattr(module.shutil, "which", resolve)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: "b" * 40)
    exchange = Mock()
    monkeypatch.setattr(module, "federate", exchange)
    with pytest.raises(ValueError):
        module.prepare_plan("staging", "security", environment_values())
    exchange.assert_not_called()


# CLI errors expose one fixed diagnostic rather than provider messages or credential values.
def test_cli_and_entrypoint(monkeypatch, capsys):
    prepare = Mock(side_effect=RuntimeError("private credential and provider details"))
    monkeypatch.setattr(module, "prepare_plan", prepare)
    assert module.main(["--environment", "staging", "--component", "security"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "INFRASTRUCTURE_PLAN_FAILED"
    assert "private credential and provider details" not in str(output)
    prepare.side_effect = None
    prepare.return_value = {"status": "planned", "applied": False}
    assert module.main(["--environment", "production", "--component", "platform"]) == 0
    assert json.loads(capsys.readouterr().out) == prepare.return_value
    monkeypatch.setattr(
        "sys.argv",
        ["otm.infrastructure_plan", "--environment", "staging", "--component", "security"],
    )
    monkeypatch.setenv("OTM_INFRASTRUCTURE_ENABLED", "false")
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(module.__file__)), run_name="__main__")
    assert result.value.code == 1


# Both workflows require fixed protected environments, exact source, bounded jobs and no
# unreviewed apply/artifacts.
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_workflow_contract(environment):
    path = module.ROOT / ".github/workflows" / f"infra-{environment}.yml"
    workflow = yaml.safe_load(path.read_text())
    assert list(workflow[True]) == ["workflow_dispatch"]
    assert workflow[True]["workflow_dispatch"]["inputs"]["component"]["options"] == [
        "security",
        "platform",
    ]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "otm-environment-" + environment,
        "cancel-in-progress": False,
    }
    job = workflow["jobs"]["infrastructure"]
    assert job["environment"] == environment and job["if"] == "github.ref == 'refs/heads/master'"
    assert (
        job["permissions"] == {"contents": "read", "actions": "read", "id-token": "write"}
        and job["timeout-minutes"] == "${{ inputs.operation == 'apply' && 90 || 30 }}"
    )
    checkout = job["steps"][0]
    assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": False}
    actions = [step["uses"] for step in job["steps"] if "uses" in step]
    assert all(len(action.rsplit("@", 1)[1]) == 40 for action in actions)
    assert not any("upload-artifact" in action for action in actions)
    final = job["steps"][-1]
    assert 'case "$OTM_OPERATION" in' in final["run"]
    assert f"otm.infrastructure_plan --environment {environment}" in final["run"]
    assert f"otm.infrastructure_apply --environment {environment}" in final["run"]
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["operation"]["options"] == ["plan", "apply"]
    assert inputs["operation"]["default"] == "plan"
    assert inputs["plan_run_id"]["type"] == "string"
    assert inputs["reviewed_plan_sha256"]["type"] == "string"
    assert final["env"]["OTM_INFRASTRUCTURE_APPLY_ENABLED"] == (
        "${{ vars.OTM_INFRASTRUCTURE_APPLY_ENABLED || 'false' }}"
    )
    if environment == "production":
        assert inputs["staging_tests_confirmed"]["default"] is False
        assert inputs["staging_apply_run_id"]["type"] == "string"
        assert '--staging-tests-confirmed "$OTM_STAGING_TESTS_CONFIRMED"' in final["run"]
    assert (
        final["env"]["OTM_INFRASTRUCTURE_ENABLED"]
        == "${{ vars.OTM_INFRASTRUCTURE_ENABLED || 'false' }}"
    )
    assert final["env"]["OTM_INFRA_CLIENT_SECRET"] == "${{ secrets.OTM_INFRA_CLIENT_SECRET }}"
    for field in (
        "OTM_INFRA_IDENTITY_DOMAIN_URL",
        "OTM_INFRA_CLIENT_ID",
        "OTM_HOSTING_COMPARTMENT_OCID",
        "OTM_ALLOWED_SOURCE_CIDRS",
    ):
        assert final["env"][field] == "${{ secrets." + field + " }}"
    assert all("${{" not in step.get("run", "") for step in job["steps"])


# Apply sessions receive two hours; shorter plan tokens cannot be reused for a longer execution.
@pytest.mark.parametrize(
    "minutes,expires,accepted",
    [
        (120, 7200, True),
        (120, 3600, False),
        (60, 7200, False),
        (True, 3600, False),
        (180, 10800, False),
    ],
)
def test_federation_bounded_apply_lifetime(tmp_path, monkeypatch, minutes, expires, accepted):
    values = environment_values()
    target = json.loads(values["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"]
    request = Mock(
        side_effect=[{"value": "synthetic-jwt"}, {"token": rpst(exp=int(time.time()) + expires)}]
    )
    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "signing_pair", lambda: (b"synthetic-private", b"synthetic-public"))
    if not accepted:
        with pytest.raises(ValueError):
            module.federate(tmp_path, target, "staging", values, lifetime_minutes=minutes)
        assert not list(tmp_path.iterdir())
    else:
        module.federate(tmp_path, target, "staging", values, lifetime_minutes=minutes)
        payload = module.urllib.parse.parse_qs(request.call_args.args[2].decode())
        assert payload["rpst_exp"] == ["120"]
