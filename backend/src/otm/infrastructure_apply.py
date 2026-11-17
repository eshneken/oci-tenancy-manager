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
        or report.get("component") not in planning.COMPONENT_FIELDS
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
            report["component"] == "platform"
            and (
                not isinstance(report.get("node_image_sha256"), str)
                or HASH.fullmatch(report["node_image_sha256"]) is None
            )
        )
        or (report["component"] == "security" and report.get("node_image_sha256") is not None)
        or (
            environment == "staging"
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
def parity(plan, component):
    if component == "security":
        common = {"component": component}
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
    expected_key = (
        f"infrastructure-plans/{report['environment']}/{component}/"
        f"{report['run_id']}/{report['attempt']}/plan.tar"
    )
    changes = report.get("changes")
    if (
        not isinstance(reviewed_hash, str)
        or HASH.fullmatch(reviewed_hash) is None
        or report.get("component") != component
        or report.get("plan_sha256") != reviewed_hash
        or report.get("object_key") != expected_key
        or not isinstance(changes, dict)
        or set(changes) != {"create", "update", "delete", "replace"}
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


# Apply exactly one reviewed saved plan; all failures retain the marker and require investigation.
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
            _, digest = planning.render_inputs(directory, inputs, component, values)
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
            if planning.change_counts(plan) != report["changes"]:
                raise ValueError("PLAN_CHANGE_SUMMARY_MISMATCH")
            common = parity(plan, component)
            if staging is not None and (
                staging["parity_sha256"] != common
                or (
                    component == "platform"
                    and staging["node_image_sha256"]
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
                if component == "platform":
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
    parser.add_argument("--environment", choices=("staging", "production"), required=True)
    parser.add_argument("--component", choices=tuple(planning.COMPONENT_FIELDS), required=True)
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
