"""Consume one reviewed environment plan once; never rebuild or automatically retry an apply."""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess  # nosec B404
import tarfile
import tempfile
import time
from pathlib import Path

from otm import infrastructure_plan as planning

# Bounded private plan custody and retained GitHub log reads; neither is an extraction quota.
MAX_BUNDLE = 64 * 1024 * 1024
MAX_LOG = 16 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}")
NUMBER = re.compile(r"[1-9][0-9]{0,19}")
ATLAS_APP_ADDRESS = "module.atlas_sso.oci_identity_domains_app.atlas_sso"
ATLAS_GRANT_ADDRESS = "module.atlas_sso.oci_identity_domains_grant.atlas_assignment"
ATLAS_GROUP_ADDRESS = "module.atlas_sso.oci_identity_group.users"
ATLAS_GROUP_READ = "module.atlas_sso.data.oci_identity_domains_groups.atlas_users"
SCIM_GUID = re.compile(r"[0-9a-f]{32}")
ATLAS_APP_ATTRIBUTES = (
    "id,ocid,name,displayName,description,schemas,basedOnTemplate,active,allowAccessControl,"
    "isLoginTarget,loginMechanism,isOAuthClient,isOAuthResource,allowedGrants,clientType,"
    "redirectUris,trustScope,signonPolicy,idpPolicy"
)
PLAN_FIELDS = {
    "status",
    "environment",
    "component",
    "source_sha",
    "run_id",
    "attempt",
    "inputs_sha256",
    "plan_sha256",
    "changes",
    "object_key",
    "applied",
}
APPLY_FIELDS = {
    "status",
    "environment",
    "component",
    "source_sha",
    "run_id",
    "attempt",
    "plan_run_id",
    "plan_attempt",
    "plan_sha256",
    "inputs_sha256",
    "parity_sha256",
    "node_image_sha256",
    "staging_apply_run_id",
    "staging_tests_confirmed",
    "applied",
}


# State-save failure is distinct from rollback; report only whether native recovery bytes were kept.
class ApplyStopped(RuntimeError):
    # This boolean is safe public metadata, never provider diagnostics or state contents.
    def __init__(self, recovery_state_retained):
        super().__init__("INFRASTRUCTURE_APPLY_STOPPED")
        self.recovery_state_retained = recovery_state_retained


# Only an explicit job token reaches the fixed GitHub host; local login/config fallback is disabled.
def github(path, values):
    token = values.get("GH_TOKEN")
    executable = shutil.which("gh")
    if (
        not isinstance(token, str)
        or not 0 < len(token) <= 8192
        or "\r" in token
        or "\n" in token
        or not executable
        or not os.path.isabs(executable)
    ):
        raise ValueError("INFRASTRUCTURE_GITHUB_TOKEN_REQUIRED")
    with (
        tempfile.TemporaryDirectory(prefix="otm-gh-plan-") as config,
        tempfile.TemporaryFile() as output,
        tempfile.TemporaryFile() as errors,
    ):
        child_env = {
            "GH_TOKEN": token,
            "GH_HOST": "github.com",
            "GH_CONFIG_DIR": config,
            "GH_PROMPT_DISABLED": "1",
            "PATH": values.get("PATH", "/usr/bin:/bin"),
        }
        version = subprocess.run(  # nosec B603
            [executable, "--version"],
            capture_output=True,
            check=True,
            shell=False,
            timeout=10,
            env=child_env,
        ).stdout
        match = re.match(rb"gh version ([0-9]+)[.]([0-9]+)[.]([0-9]+)\b", version)
        if not match or tuple(map(int, match.groups())) < (2, 104, 0):
            raise ValueError("REVIEWED_GITHUB_CLI_REQUIRED")
        # Path components are constructed from validated repository/numeric IDs, never a caller URL.
        result = subprocess.run(  # nosec B603
            [executable, "api", "--hostname", "github.com", "--allow-escape-sequences", path],
            stdout=output,
            stderr=errors,
            check=False,
            shell=False,
            timeout=120,
            env=child_env,
        )
        if result.returncode:
            raise ValueError("INFRASTRUCTURE_GITHUB_EVIDENCE_UNAVAILABLE")
        output.seek(0)
        content = output.read(MAX_LOG + 1)
    if len(content) > MAX_LOG:
        raise ValueError("INFRASTRUCTURE_GITHUB_EVIDENCE_TOO_LARGE")
    return content


# Authenticated metadata must identify the exact successful manual master workflow and source.
def validate_run(run, repository, environment, source, run_id):
    if not isinstance(run, dict) or (
        type(run.get("id")) is not int
        or str(run["id"]) != run_id
        or type(run.get("run_attempt")) is not int
        or run["run_attempt"] < 1
        or run.get("repository", {}).get("full_name") != repository
        or run.get("head_repository", {}).get("full_name") != repository
        or run.get("path") != f".github/workflows/infra-{environment}.yml"
        or run.get("event") != "workflow_dispatch"
        or run.get("head_branch") != "master"
        or run.get("head_sha") != source
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        raise ValueError("INFRASTRUCTURE_RUN_UNTRUSTED")
    return run["run_attempt"]


# Native job logs provide the producer's hash; a matching receipt in a mutable bucket is
# insufficient.
def trusted_report(run_id, environment, status, values):
    if not isinstance(run_id, str) or NUMBER.fullmatch(run_id) is None:
        raise ValueError("INFRASTRUCTURE_RUN_ID_REQUIRED")
    repository, source = values["GITHUB_REPOSITORY"], values["GITHUB_SHA"]
    prefix = f"repos/{repository}/actions/runs/{run_id}"
    run = planning.decode_json(github(prefix, values))
    attempt = validate_run(run, repository, environment, source, run_id)
    jobs = planning.decode_json(github(f"{prefix}/attempts/{attempt}/jobs?per_page=100", values))
    if not isinstance(jobs, dict) or jobs.get("total_count") != 1 or len(jobs.get("jobs", [])) != 1:
        raise ValueError("INFRASTRUCTURE_JOB_REQUIRED")
    job = jobs["jobs"][0]
    if (
        job.get("name") != "Infrastructure"
        or job.get("conclusion") != "success"
        or type(job.get("id")) is not int
        or job["id"] < 1
    ):
        raise ValueError("INFRASTRUCTURE_JOB_UNTRUSTED")
    logs = github(f"repos/{repository}/actions/jobs/{job['id']}/logs", values).decode("utf-8")
    reports = []
    for line in logs.splitlines():
        # GitHub prepends ISO UTC timestamps; the producer's single JSON print is uncolored.
        payload = (
            line.split(" ", 1)[1]
            if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[^ ]+Z ", line)
            else line
        )
        try:
            candidate = planning.decode_json(payload)
        except (ValueError, TypeError):
            continue
        if isinstance(candidate, dict) and candidate.get("status") == status:
            reports.append(candidate)
    if len(reports) != 1:
        raise ValueError("INFRASTRUCTURE_PRODUCER_REPORT_REQUIRED")
    report = reports[0]
    fields = PLAN_FIELDS if status == "planned" else APPLY_FIELDS
    if (
        set(report) != fields
        or report.get("environment") != environment
        or report.get("source_sha") != source
        or report.get("run_id") != run_id
        or report.get("attempt") != str(attempt)
        or report.get("component") != planning.COMPONENT
        or report.get("applied") is not (status == "applied")
        or any(
            not isinstance(report.get(key), str) or HASH.fullmatch(report[key]) is None
            for key in ("inputs_sha256", "plan_sha256")
        )
    ):
        raise ValueError("INFRASTRUCTURE_PRODUCER_REPORT_UNTRUSTED")
    if status == "applied" and (
        not isinstance(report.get("parity_sha256"), str)
        or HASH.fullmatch(report["parity_sha256"]) is None
        or not isinstance(report.get("plan_run_id"), str)
        or NUMBER.fullmatch(report["plan_run_id"]) is None
        or not isinstance(report.get("plan_attempt"), str)
        or NUMBER.fullmatch(report["plan_attempt"]) is None
        or (
            environment != "development"
            and (
                not isinstance(report.get("node_image_sha256"), str)
                or HASH.fullmatch(report["node_image_sha256"]) is None
            )
        )
        or (environment == "development" and report.get("node_image_sha256") is not None)
        or (
            environment != "production"
            and (
                report.get("staging_apply_run_id") is not None
                or report.get("staging_tests_confirmed") is not False
            )
        )
        or (
            environment == "production"
            and (
                report.get("staging_tests_confirmed") is not True
                or not isinstance(report.get("staging_apply_run_id"), str)
                or NUMBER.fullmatch(report["staging_apply_run_id"]) is None
            )
        )
    ):
        raise ValueError("STAGING_APPLY_REPORT_REJECTED")
    # A rerun racing the log selection must not substitute another producer attempt.
    latest = planning.decode_json(github(prefix, values))
    if validate_run(latest, repository, environment, source, run_id) != attempt:
        raise ValueError("INFRASTRUCTURE_RUN_CHANGED")
    return report


# Read exactly two bounded regular members without extracting paths, links or executable contents.
def unpack_plan(content, directory, report):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BUNDLE:
        raise ValueError("BOUNDED_PRIVATE_PLAN_REQUIRED")
    members = {}
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
        for member in archive:
            limit = 131072 if member.name == "receipt.json" else MAX_BUNDLE - 131072
            if (
                member.name not in {"plan.tfplan", "receipt.json"}
                or member.name in members
                or not member.isfile()
                or not 0 < member.size <= limit
                or set(member.pax_headers) - {"mtime", "atime", "ctime"}
            ):
                raise ValueError("PRIVATE_PLAN_ARCHIVE_REJECTED")
            data = archive.extractfile(member).read(limit + 1)
            if len(data) != member.size:
                raise ValueError("PRIVATE_PLAN_ARCHIVE_TRUNCATED")
            members[member.name] = data
    if set(members) != {"plan.tfplan", "receipt.json"}:
        raise ValueError("PRIVATE_PLAN_ARCHIVE_INCOMPLETE")
    receipt = planning.decode_json(members["receipt.json"])
    expected = {key: value for key, value in report.items() if key not in {"object_key", "applied"}}
    if (
        receipt != expected
        or hashlib.sha256(members["plan.tfplan"]).hexdigest() != report["plan_sha256"]
    ):
        raise ValueError("PRIVATE_PLAN_IDENTITY_MISMATCH")
    planning.private_write(directory / "plan.tfplan", members["plan.tfplan"])


# Hash effective shared sizing/version behavior; tenancy references remain environment-specific.
def parity(plan, environment):
    if environment == "development":
        common = {"environment": environment}
    else:
        variables = plan["variables"]
        common = {
            key: variables[key]["value"]
            for key in (
                "oke",
                "database",
                "oke_kubernetes_version",
                "postgresql_version",
                "caddy_ingress_enabled",
            )
        }
        common["oke"] = dict(common["oke"])
        domains = common["oke"]["availability_domains"]
        if (
            not isinstance(domains, list)
            or not domains
            or not all(isinstance(value, str) for value in domains)
        ):
            raise ValueError("INFRASTRUCTURE_PLACEMENT_REQUIRED")
        # OCI AD prefixes identify the tenancy; the logical placement/number of domains must agree.
        common["oke"]["availability_domains"] = sorted(
            value.rsplit(":", 1)[-1] for value in domains
        )
    return hashlib.sha256(planning.canonical(common)).hexdigest()


# Only the four noncredential image-selection fields participate; no private OCID is printed.
def image_digest(selection):
    if (
        not isinstance(selection, dict)
        or set(selection) != {"image_ocid", "kubernetes_version", "architecture", "os_major"}
        or selection.get("architecture") != "AARCH64"
        or selection.get("os_major") not in {"8", "9"}
        or not isinstance(selection.get("image_ocid"), str)
        or re.fullmatch(r"ocid1[.]image[.]oc1[.]iad[.][a-z0-9]{1,200}", selection["image_ocid"])
        is None
        or not isinstance(selection.get("kubernetes_version"), str)
        or re.fullmatch(
            r"v[1-9][0-9]*[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)", selection["kubernetes_version"]
        )
        is None
    ):
        raise ValueError("QUALIFIED_NODE_IMAGE_REQUIRED")
    return hashlib.sha256(planning.canonical(selection)).hexdigest()


# Validate the reviewed hash, fixed component and exact private object key before obtaining OCI
# access.
def reviewed_plan(report, component, reviewed_hash):
    expected_key = planning.plan_object_key(
        report["environment"], component, report["run_id"], report["attempt"]
    )
    changes = report.get("changes")
    if (
        not isinstance(reviewed_hash, str)
        or HASH.fullmatch(reviewed_hash) is None
        or report.get("component") != component
        or report.get("plan_sha256") != reviewed_hash
        or report.get("object_key") != expected_key
        or not isinstance(changes, dict)
        or (changes.keys() - {"import"}) != {"create", "update", "delete", "replace"}
        or (
            "import" in changes
            and (report["environment"] != "development" or changes["import"] != 1)
        )
        or any(type(value) is not int or value < 0 for value in changes.values())
    ):
        raise ValueError("EXACT_REVIEWED_PLAN_REQUIRED")


# One conditional marker fences repeat/uncertain execution; never delete it or retry its creation.
def claim_attempt(client, namespace, bucket, key, report, values):
    body = planning.canonical(
        {
            "plan_sha256": report["plan_sha256"],
            "apply_run_id": values["GITHUB_RUN_ID"],
            "apply_attempt": values["GITHUB_RUN_ATTEMPT"],
        }
    )
    client.put_object(
        namespace,
        bucket,
        key,
        body,
        if_none_match="*",
        content_type="application/json",
        content_length=len(body),
    )


# Preserve Terraform's own failed-backend recovery state privately; never edit/push it
# automatically.
def preserve_recovery_state(client, namespace, bucket, prefix, root):
    try:
        descriptor = os.open(root / "errored.tfstate", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BUNDLE:
                return False
            content = stream.read(MAX_BUNDLE + 1)
        if not 0 < len(content) <= MAX_BUNDLE:
            return False
        client.put_object(
            namespace,
            bucket,
            prefix + "errored.tfstate",
            content,
            if_none_match="*",
            content_type="application/json",
            content_length=len(content),
        )
        return True
    except Exception:
        # Retention failure must not hide the failed apply or cause another provider operation.
        return False


# Terraform includes known-only lists and objects in after_unknown for collection properties.
# Reject actual unknown values anywhere in an activation update.
def _all_known(mask):
    if isinstance(mask, dict):
        return all(_all_known(item) for item in mask.values())
    if isinstance(mask, list):
        return all(_all_known(item) for item in mask)
    return mask is False


# Permit the pending assignment only when the saved plan binds the existing App to the one
# metadata-only SCIM row for the unchanged native development group pinned in plan inputs.
def _reviewed_activation_grant(plan, grant, app, configuration):
    change = grant["change"]
    if (
        grant.get("address") != ATLAS_GRANT_ADDRESS
        or grant.get("type") != "oci_identity_domains_grant"
        or grant.get("provider_name") != "registry.terraform.io/oracle/oci"
        or change["actions"] != ["create"]
        or change.get("before") is not None
    ):
        return False
    try:
        (resource,) = [
            item
            for item in configuration
            if item["address"] == "oci_identity_domains_grant.atlas_assignment"
        ]
        (atlas_state,) = [
            item
            for item in plan["prior_state"]["values"]["root_module"]["child_modules"]
            if item["address"] == "module.atlas_sso"
        ]
        (lookup,) = [
            item["values"]
            for item in atlas_state["resources"]
            if item["address"] == ATLAS_GROUP_READ and item["mode"] == "data"
        ]
        (native_group,) = [
            item["change"]["after"]
            for item in plan["resource_changes"]
            if item.get("address") == ATLAS_GROUP_ADDRESS and item["mode"] == "managed"
        ]
        (group,) = lookup["groups"]
        group_ocid = native_group["id"]
        group_guid = group["id"]
        adoption_pin = plan["variables"]["atlas_sso"]["value"]["adopt_group_ocid"]
        after = change["after"]
        unknown = change["after_unknown"]
        (app_unknown,) = unknown.get("app", [{}])
        (grantee_unknown,) = unknown.get("grantee", [{}])
    except (KeyError, TypeError, ValueError):
        return False
    scope = {
        "app": [{"value": app["id"]}],
        "grant_mechanism": "ADMINISTRATOR_TO_GROUP",
        "grantee": [{"type": "Group", "value": group_guid}],
        "idcs_endpoint": app["idcs_endpoint"],
        "schemas": ["urn:ietf:params:scim:schemas:oracle:idcs:Grant"],
    }
    # Require known dependencies and no additional inputs. Terraform may compute display/ref
    # metadata, but never the planned App GUID, group GUID or grant mechanism.
    return (
        resource["expressions"].keys() == scope.keys()
        and resource["expressions"]["app"]
        == [
            {
                "value": {
                    "references": [
                        "oci_identity_domains_app.atlas_sso.id",
                        "oci_identity_domains_app.atlas_sso",
                    ]
                }
            }
        ]
        and resource["expressions"]["grantee"]
        == [
            {
                "type": {"constant_value": "Group"},
                "value": {
                    "references": [
                        "data.oci_identity_domains_groups.atlas_users.groups",
                        "data.oci_identity_domains_groups.atlas_users",
                    ]
                },
            }
        ]
        and isinstance(group_ocid, str)
        and planning.GROUP_OCID.fullmatch(group_ocid) is not None
        and group_ocid == adoption_pin
        and isinstance(group_guid, str)
        and SCIM_GUID.fullmatch(group_guid) is not None
        and native_group.get("name") == group.get("display_name") == "otm-development-users"
        and lookup.get("total_results") == 1
        and lookup.get("attributes") == "id,ocid,displayName"
        and lookup.get("idcs_endpoint") == app["idcs_endpoint"]
        and lookup.get("group_filter") == f'ocid eq "{group_ocid}"'
        and group.get("ocid") == group_ocid
        and group.get("members") in (None, [])
        and {key: value for key, value in after.items() if value is not None} == scope
        and isinstance(app_unknown, dict)
        and app_unknown.get("value", False) is False
        and isinstance(grantee_unknown, dict)
        and all(grantee_unknown.get(key, False) is False for key in ("type", "value"))
        and all(
            _all_known(unknown.get(key, False))
            for key in ("grant_mechanism", "idcs_endpoint", "schemas")
        )
    )


# The activation run may also finish the specific pending group grant. Leave other state
# writes and out-of-band drift for separate review and handling.
def _activation_changes_are_scoped(plan, app, after, configuration):
    if plan.get("resource_drift"):
        return False
    other_writes = [
        item
        for item in plan["resource_changes"]
        if item is not app
        and item.get("mode") == "managed"
        and (
            item["change"]["actions"] != ["no-op"]
            or "importing" in item["change"]
            or "previous_address" in item
            or "deposed" in item
        )
    ]
    return not other_writes or (
        len(other_writes) == 1
        and not ({"previous_address", "deposed"} & other_writes[0].keys())
        and "importing" not in other_writes[0]["change"]
        and _reviewed_activation_grant(plan, other_writes[0], after, configuration)
    )


# Match the qualified App controls against known values in the exact saved plan and reject
# any unreviewed App configuration, including optional provider fields that can carry secrets.
def _reviewed_development_app(plan, app, identity_domain_url):
    change = app["change"]
    actions = change["actions"]
    activation = actions == ["update"]
    if (
        app.get("address") != ATLAS_APP_ADDRESS
        or app.get("mode") != "managed"
        or app.get("provider_name") != "registry.terraform.io/oracle/oci"
        or actions not in (["create"], ["update"])
        or "importing" in change
        or "deposed" in app
        or "previous_address" in app
    ):
        return False
    expected = {
        "active": activation,
        "allow_access_control": True,
        "allowed_grants": ["authorization_code"],
        "attributes": ATLAS_APP_ATTRIBUTES,
        "client_type": "confidential",
        "description": "Corporate single sign-on for OCI Tenancy Manager.",
        "display_name": "otm-sso-development",
        "idcs_endpoint": identity_domain_url,
        "is_login_target": True,
        "is_oauth_client": True,
        "is_oauth_resource": False,
        "login_mechanism": "OIDC",
        "redirect_uris": ["https://127.0.0.1:8445/api/auth/sso/callback"],
        "schemas": ["urn:ietf:params:scim:schemas:oracle:idcs:App"],
        "trust_scope": "Explicit",
    }
    # Credentials and extra attribute projections must be absent from configuration. Terraform
    # marks provider-computed credentials unknown before the projected create response.
    try:
        module = plan["configuration"]["root_module"]["module_calls"]["atlas_sso"]["module"]
        configuration = module["resources"]
        (resource,) = [
            resource
            for resource in configuration
            if resource.get("address") == "oci_identity_domains_app.atlas_sso"
        ]
        after = change["after"]
        unknown = change["after_unknown"]
        expressions = resource["expressions"]
        if not all(isinstance(mapping, dict) for mapping in (after, unknown, expressions)):
            return False
        (template,) = after["based_on_template"]
        (template_unknown,) = unknown.get("based_on_template", [{}])
    except (KeyError, TypeError, ValueError):
        return False
    before = change.get("before")
    if activation:
        # The complete state comparison fences policy, callback, credential and other App mutations.
        # Check the immutable GUID before admitting an update to the existing App.
        if (
            not isinstance(before, dict)
            or before.get("active") is not False
            or not isinstance(before.get("id"), str)
            or SCIM_GUID.fullmatch(before["id"]) is None
            or planning.canonical({**before, "active": True}) != planning.canonical(after)
            or not _all_known(unknown)
            or not _activation_changes_are_scoped(plan, app, after, configuration)
        ):
            return False
    elif before is not None:
        return False
    # Policy IDs may still be unknown when those policies are created by the same reviewed plan.
    # Their exact configured references prevent substituting unrelated IDs or private literals.
    return (
        expressions.keys() == expected.keys() | {"based_on_template", "signon_policy", "idp_policy"}
        and expressions["based_on_template"]
        == [{"value": {"constant_value": "CustomWebAppTemplateId"}}]
        and all(
            expressions[key]
            == [
                {
                    "value": {
                        "references": [f"module.atlas_policies.{key}_id", "module.atlas_policies"]
                    }
                }
            ]
            for key in ("signon_policy", "idp_policy")
        )
        and all(
            type(after.get(key)) is type(value)
            and after[key] == value
            and (
                unknown.get(key, False) is False
                or (
                    isinstance(value, list)
                    and isinstance(unknown[key], list)
                    and len(unknown[key]) == 1
                    and unknown[key][0] is False
                )
            )
            for key, value in expected.items()
        )
        and isinstance(template, dict)
        and template.get("value") == "CustomWebAppTemplateId"
        and isinstance(template_unknown, dict)
        and template_unknown.get("value", False) is False
        and all(
            after.get(key) is None
            for key in ("authorization", "client_secret", "hashed_client_secret")
        )
        and after.get("attribute_sets") in (None, [])
        and unknown.get("attribute_sets", False) is False
        and unknown.get("authorization", False) is False
    )


# Admit a single inactive development App creation or an existing App activation with its
# exact pending assignment. Hosted App writes and fresh active creates remain held.
def validate_identity_app_writes(plan, environment, identity_domain_url):
    writes = [
        item
        for item in plan.get("resource_changes", [])
        if item.get("type") == "oci_identity_domains_app"
        and item["change"]["actions"] not in (["read"], ["no-op"])
    ]
    if writes and (
        environment != "development"
        or len(writes) != 1
        or not _reviewed_development_app(plan, writes[0], identity_domain_url)
    ):
        raise ValueError("OCI_APP_WORKFLOW_WRITE_UNQUALIFIED")


# Apply one reviewed saved plan. Failures after claiming the attempt retain its marker for review.
def apply_plan(
    environment,
    component,
    plan_run_id,
    reviewed_hash,
    values,
    *,
    staging_run_id="",
    staging_tests_confirmed=False,
):
    inputs = planning.context(environment, component, values)
    command = planning.checked_source(values)
    if values.get("OTM_INFRASTRUCTURE_APPLY_ENABLED") != "true":
        raise ValueError("INFRASTRUCTURE_APPLY_HELD")
    report = trusted_report(plan_run_id, environment, "planned", values)
    reviewed_plan(report, component, reviewed_hash)
    # Development is limited to additive/in-place custody changes. Stop before signing or claiming.
    if environment == "development" and (
        report["changes"]["delete"] or report["changes"]["replace"]
    ):
        raise ValueError("DESTRUCTIVE_DEVELOPMENT_PLAN_REJECTED")
    staging = None
    if environment == "production":
        if staging_tests_confirmed is not True:
            raise ValueError("STAGING_TEST_CONFIRMATION_REQUIRED")
        staging = trusted_report(staging_run_id, "staging", "applied", values)
        if staging["component"] != component:
            raise ValueError("STAGING_COMPONENT_MISMATCH")
    previous_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix="otm-infrastructure-apply-") as temporary:
            directory = Path(temporary)
            _, digest = planning.render_inputs(directory, inputs, values)
            if digest != report["inputs_sha256"]:
                raise ValueError("PLAN_INPUTS_CHANGED")
            credentials = planning.federate(
                directory, inputs["target"], environment, values, lifetime_minutes=120
            )
            client, namespace, bucket = planning.plan_storage(
                credentials, inputs["target"], environment, values["OTM_HOSTING_COMPARTMENT_OCID"]
            )
            response = client.get_object(namespace, bucket, report["object_key"])
            try:
                bundle = response.data.raw.read(MAX_BUNDLE + 1)
            finally:
                response.data.close()
            unpack_plan(bundle, directory, report)
            root = planning.ROOT / "infra/environments" / environment / component
            deadline = time.monotonic() + 4500
            child_env = planning.initialize_terraform(
                directory, root, command, inputs, environment, credentials, values, deadline
            )
            plan = planning.decode_json(
                planning.terraform(
                    command,
                    ["show", "-json", str(directory / "plan.tfplan")],
                    root,
                    child_env,
                    directory,
                    deadline,
                ),
                limit=MAX_LOG,
            )
            if (
                planning.change_counts(
                    plan, adopt_group_ocid=inputs["atlas_sso"].get("adopt_group_ocid")
                )
                != report["changes"]
            ):
                raise ValueError("PLAN_CHANGE_SUMMARY_MISMATCH")
            validate_identity_app_writes(plan, environment, values["OTM_INFRA_IDENTITY_DOMAIN_URL"])
            common = parity(plan, environment)
            if staging is not None and (
                staging["parity_sha256"] != common
                or (
                    staging["node_image_sha256"]
                    != image_digest(plan["variables"]["qualified_node_image"]["value"])
                )
            ):
                raise ValueError("STAGING_PARITY_OR_IMAGE_MISMATCH")
            # Recheck producer metadata/logs immediately before the irreversible single-use claim.
            if trusted_report(plan_run_id, environment, "planned", values) != report:
                raise ValueError("PLAN_PRODUCER_CHANGED")
            if (
                staging is not None
                and trusted_report(staging_run_id, "staging", "applied", values) != staging
            ):
                raise ValueError("STAGING_PRODUCER_CHANGED")
            prefix = report["object_key"].removesuffix("plan.tar")
            claim_attempt(client, namespace, bucket, prefix + "apply-attempt.json", report, values)
            # No new plan, variable override, auto-approve or retry is permitted for this binary.
            try:
                planning.terraform(
                    command,
                    [
                        "apply",
                        "-input=false",
                        "-no-color",
                        "-lock-timeout=60s",
                        str(directory / "plan.tfplan"),
                    ],
                    root,
                    child_env,
                    directory,
                    deadline,
                )
                node_image = None
                if environment != "development":
                    outputs = planning.decode_json(
                        planning.terraform(
                            command,
                            ["output", "-json", "cluster"],
                            root,
                            child_env,
                            directory,
                            deadline,
                        )
                    )
                    if outputs.get("environment") != environment:
                        raise ValueError("APPLIED_CLUSTER_ENVIRONMENT_MISMATCH")
                    node_image = image_digest(outputs.get("image_selection"))
                    if staging is not None and node_image != staging["node_image_sha256"]:
                        raise ValueError("APPLIED_NODE_IMAGE_MISMATCH")
            except Exception:
                retained = preserve_recovery_state(client, namespace, bucket, prefix, root)
                raise ApplyStopped(retained) from None
            return {
                "status": "applied",
                "environment": environment,
                "component": component,
                "source_sha": values["GITHUB_SHA"],
                "run_id": values["GITHUB_RUN_ID"],
                "attempt": values["GITHUB_RUN_ATTEMPT"],
                "plan_run_id": plan_run_id,
                "plan_attempt": report["attempt"],
                "plan_sha256": reviewed_hash,
                "inputs_sha256": digest,
                "parity_sha256": common,
                "node_image_sha256": node_image,
                "staging_apply_run_id": staging_run_id if staging is not None else None,
                "staging_tests_confirmed": staging_tests_confirmed
                if staging is not None
                else False,
                "applied": True,
            }
    finally:
        os.umask(previous_umask)


# An apply error may follow real mutations; never claim rollback or encourage replay in public
# output.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=planning.ENVIRONMENTS, required=True)
    parser.add_argument("--component", choices=(planning.COMPONENT,), required=True)
    parser.add_argument("--plan-run-id", required=True)
    parser.add_argument("--reviewed-plan-sha256", required=True)
    parser.add_argument("--staging-run-id", default="")
    parser.add_argument("--staging-tests-confirmed", choices=("true", "false"), default="false")
    options = parser.parse_args(argv)
    try:
        result = apply_plan(
            options.environment,
            options.component,
            options.plan_run_id,
            options.reviewed_plan_sha256,
            dict(os.environ),
            staging_run_id=options.staging_run_id,
            staging_tests_confirmed=options.staging_tests_confirmed == "true",
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "code": "INFRASTRUCTURE_APPLY_STOPPED",
                    "recovery_state_retained": isinstance(error, ApplyStopped)
                    and error.recovery_state_retained,
                    "guidance": (
                        "No automatic retry. Infrastructure may have changed. Investigate the "
                        "selected run/state before generating and reviewing a fresh plan."
                    ),
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
