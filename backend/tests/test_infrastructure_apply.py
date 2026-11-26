"""Exercise reviewed-plan trust, one-attempt custody and staging parity without cloud access."""

import copy
import hashlib
import io
import json
import os
import runpy
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_infrastructure_plan import SHA, environment_values

from otm import infrastructure_apply as module
from otm import infrastructure_plan as planning

BINARY = b"synthetic saved Terraform plan"


# The synthetic receipt mirrors the producer's exact public schema and private archive fields.
def report(environment="staging", component="infrastructure"):
    prefix = "custody" if environment == "development" else component
    return {
        "status": "planned",
        "environment": environment,
        "component": component,
        "source_sha": SHA,
        "run_id": "123",
        "attempt": "1",
        "inputs_sha256": "b" * 64,
        "plan_sha256": hashlib.sha256(BINARY).hexdigest(),
        "changes": {"create": 0, "update": 0, "delete": 0, "replace": 0},
        "object_key": f"infrastructure-plans/{environment}/{prefix}/123/1/plan.tar",
        "applied": False,
    }


# Fixed image-selection metadata can differ by environment only before staging qualification.
def selection():
    return {
        "image_ocid": "ocid1.image.oc1.iad.synthetic",
        "kubernetes_version": "v1.37.1",
        "architecture": "AARCH64",
        "os_major": "9",
    }


# A successful staging apply has no production acceptance fields or private resource outputs.
def applied_report(component="infrastructure"):
    return {
        "status": "applied",
        "environment": "staging",
        "component": component,
        "source_sha": SHA,
        "run_id": "456",
        "attempt": "1",
        "plan_run_id": "123",
        "plan_attempt": "1",
        "plan_sha256": "a" * 64,
        "inputs_sha256": "b" * 64,
        "parity_sha256": module.parity(native_plan(), "staging"),
        "node_image_sha256": module.image_digest(selection()),
        "staging_apply_run_id": None,
        "staging_tests_confirmed": False,
        "applied": True,
    }


# Effective native variables include shared sizing and the explicit production image handoff.
def native_plan():
    values = {
        "oke": {"availability_domains": ["tenant:AD1"], "ocpus": 2},
        "database": {"ocpus": 2, "backup_start_utc": "02:00"},
        "oke_kubernetes_version": "v1.37.1",
        "postgresql_version": "16",
        "caddy_ingress_enabled": True,
        "qualified_node_image": selection(),
    }
    return {
        "variables": {key: {"value": value} for key, value in values.items()},
        "resource_changes": [],
    }


# Build in-memory tar members without extracting anything or introducing stored credentials.
def bundle(receipt, *, entries=None):
    content = io.BytesIO()
    private = {key: value for key, value in receipt.items() if key not in {"object_key", "applied"}}
    with tarfile.open(fileobj=content, mode="w") as archive:
        for name, value in entries or [
            ("plan.tfplan", BINARY),
            ("receipt.json", json.dumps(private).encode()),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))
    return content.getvalue()


# Metadata must come from the precise manual master workflow, not a fork or successful unrelated
# job.
def run_metadata(environment="staging", run_id=123):
    return {
        "id": run_id,
        "run_attempt": 1,
        "repository": {"full_name": "example/tenancy-manager"},
        "head_repository": {"full_name": "example/tenancy-manager"},
        "path": f".github/workflows/infra-{environment}.yml",
        "event": "workflow_dispatch",
        "head_branch": "master",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
    }


# Every metadata trust dimension is independently mandatory before accepting a public receipt.
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 999),
        ("id", True),
        ("run_attempt", 0),
        ("run_attempt", True),
        ("repository", {"full_name": "fork/other"}),
        ("head_repository", {}),
        ("path", ".github/workflows/other.yml"),
        ("event", "pull_request"),
        ("head_branch", "feature"),
        ("head_sha", "c" * 40),
        ("status", "in_progress"),
        ("conclusion", "failure"),
    ],
)
def test_run_rejects_other_producers(field, value):
    metadata = run_metadata()
    metadata[field] = value
    with pytest.raises(ValueError):
        module.validate_run(metadata, "example/tenancy-manager", "staging", SHA, "123")


# Native job metadata/logs are mocked at the HTTP/CLI boundary; receipt parsing stays real.
def install_evidence(monkeypatch, receipt, *, jobs=None, logs=None, metadata=None, final=None):
    metadata = metadata or run_metadata(receipt["environment"], int(receipt["run_id"]))
    jobs = (
        jobs
        if jobs is not None
        else {
            "total_count": 1,
            "jobs": [{"id": 88, "name": "Infrastructure", "conclusion": "success"}],
        }
    )
    lines = logs if logs is not None else "2026-11-16T12:00:00.000Z " + json.dumps(receipt)
    mock = Mock(
        side_effect=[
            json.dumps(metadata).encode(),
            json.dumps(jobs).encode(),
            lines.encode(),
            json.dumps(final or metadata).encode(),
        ]
    )
    monkeypatch.setattr(module, "github", mock)
    return mock


# The matching native job receipt is accepted only once and its attempt is rechecked afterward.
@pytest.mark.parametrize("status", ["planned", "applied"])
def test_trusted_report(monkeypatch, status):
    receipt = report() if status == "planned" else applied_report()
    evidence = install_evidence(monkeypatch, receipt)
    assert (
        module.trusted_report(receipt["run_id"], "staging", status, environment_values()) == receipt
    )
    assert evidence.call_count == 4
    assert evidence.call_args_list[1].args[0].endswith("/attempts/1/jobs?per_page=100")
    assert evidence.call_args_list[2].args[0].endswith("/jobs/88/logs")


# Additional JSON, stale source, wrong hashes and malformed application evidence cannot authorize
# apply.
@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "production"),
        ("source_sha", "c" * 40),
        ("run_id", "999"),
        ("attempt", "2"),
        ("component", "bootstrap"),
        ("applied", True),
        ("inputs_sha256", "short"),
        ("plan_sha256", None),
        ("extra", "unexpected"),
    ],
)
def test_report_schema_rejected(monkeypatch, field, value):
    receipt = report()
    receipt[field] = value
    install_evidence(monkeypatch, receipt, metadata=run_metadata())
    with pytest.raises(ValueError):
        module.trusted_report("123", "staging", "planned", environment_values())


# Staging acceptance cannot be inferred from malformed or internally inconsistent apply receipts.
@pytest.mark.parametrize(
    "field,value",
    [
        ("parity_sha256", None),
        ("plan_run_id", "x"),
        ("plan_attempt", "0"),
        ("node_image_sha256", None),
        ("staging_apply_run_id", "123"),
        ("staging_tests_confirmed", True),
    ],
)
def test_apply_report_rejected(monkeypatch, field, value):
    receipt = applied_report()
    receipt[field] = value
    install_evidence(monkeypatch, receipt)
    with pytest.raises(ValueError):
        module.trusted_report("456", "staging", "applied", environment_values())


# Ambiguous jobs/logs and producer reruns fail closed rather than selecting convenient evidence.
@pytest.mark.parametrize(
    "fault", ["jobs", "name", "failed", "id", "none", "duplicate", "rerun", "run-id"]
)
def test_evidence_ambiguity(monkeypatch, fault):
    receipt = report()
    kwargs = {}
    if fault in {"jobs", "name", "failed", "id"}:
        job = {"id": 88, "name": "Infrastructure", "conclusion": "success"}
        if fault != "jobs":
            job[{"name": "name", "failed": "conclusion", "id": "id"}[fault]] = "other"
        kwargs["jobs"] = {"total_count": 2 if fault == "jobs" else 1, "jobs": [job]}
    if fault in {"none", "duplicate"}:
        kwargs["logs"] = "not JSON" if fault == "none" else (json.dumps(receipt) + "\n") * 2
    if fault == "rerun":
        kwargs["final"] = {**run_metadata(), "run_attempt": 2}
    install_evidence(monkeypatch, receipt, **kwargs)
    with pytest.raises(ValueError):
        module.trusted_report(
            "../123" if fault == "run-id" else "123", "staging", "planned", environment_values()
        )


# The native CLI receives only the job token and fixed host, with no operator login fallback.
@pytest.mark.parametrize(
    "fault", [None, "old", "bad-version", "failed", "large", "missing-token", "relative"]
)
def test_github_cli(monkeypatch, fault):
    monkeypatch.setattr(
        module.shutil, "which", lambda _: "gh" if fault == "relative" else "/bin/gh"
    )
    calls = []

    # Capture native calls without invoking GitHub or allowing another host or ambient credentials.
    def execute(arguments, **kwargs):
        calls.append((arguments, kwargs))
        assert kwargs["env"]["GH_HOST"] == "github.com"
        assert "HOME" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]
        if arguments[1] == "--version":
            return SimpleNamespace(
                stdout=b"bad"
                if fault == "bad-version"
                else b"gh version 2.103.0"
                if fault == "old"
                else b"gh version 2.104.0"
            )
        assert arguments[1:4] == ["api", "--hostname", "github.com"]
        kwargs["stdout"].write(b"x" * (17 if fault == "large" else 2))
        return SimpleNamespace(returncode=1 if fault == "failed" else 0)

    monkeypatch.setattr(module.subprocess, "run", execute)
    monkeypatch.setattr(module, "MAX_LOG", 16)
    values = {"GH_TOKEN": "synthetic-job-token", "HOME": "/untrusted", "GITHUB_TOKEN": "untrusted"}
    if fault == "missing-token":
        values.pop("GH_TOKEN")
    if fault:
        with pytest.raises(ValueError):
            module.github("repos/example/repo/actions/runs/123", values)
    else:
        assert module.github("repos/example/repo/actions/runs/123", values) == b"xx"
        assert len(calls) == 2
        assert not Path(calls[-1][1]["env"]["GH_CONFIG_DIR"]).exists()


# Valid archive bytes are written privately only after both the receipt and binary hash agree.
def test_unpack(tmp_path):
    receipt = report()
    module.unpack_plan(bundle(receipt), tmp_path, receipt)
    assert (tmp_path / "plan.tfplan").read_bytes() == BINARY
    assert (tmp_path / "plan.tfplan").stat().st_mode & 0o777 == 0o600


# Reject traversal, duplicates, missing entries, changed binary bytes and untrusted receipt data.
@pytest.mark.parametrize(
    "fault", ["traversal", "duplicate", "missing", "hash", "receipt", "empty", "oversize", "link"]
)
def test_unpack_rejected(tmp_path, monkeypatch, fault):
    receipt = report()
    entries = [("plan.tfplan", BINARY), ("receipt.json", b"{}")]
    if fault == "traversal":
        entries[0] = ("../plan.tfplan", BINARY)
    elif fault == "duplicate":
        entries.append(entries[0])
    elif fault == "missing":
        entries.pop()
    content = bundle(receipt) if fault in {"hash", "oversize"} else bundle(receipt, entries=entries)
    if fault == "hash":
        private = {
            key: value for key, value in receipt.items() if key not in {"object_key", "applied"}
        }
        content = bundle(
            receipt,
            entries=[
                ("plan.tfplan", BINARY + b"tampered"),
                ("receipt.json", json.dumps(private).encode()),
            ],
        )
    if fault == "empty":
        content = b""
    if fault == "oversize":
        monkeypatch.setattr(module, "MAX_BUNDLE", 8)
    if fault == "link":
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            member = tarfile.TarInfo("plan.tfplan")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
        content = stream.getvalue()
    with pytest.raises(ValueError):
        module.unpack_plan(content, tmp_path, receipt)
    assert not list(tmp_path.iterdir())


# Shared parity ignores tenancy AD prefixes while protecting sizing, versions and scheduled windows.
def test_parity_and_image():
    plan = native_plan()
    original = module.parity(plan, "staging")
    plan["variables"]["oke"]["value"]["availability_domains"] = ["other:AD1"]
    assert module.parity(plan, "staging") == original
    plan["variables"]["database"]["value"]["ocpus"] = 4
    assert module.parity(plan, "staging") != original
    assert (
        module.image_digest(selection())
        == hashlib.sha256(planning.canonical(selection())).hexdigest()
    )
    plan["variables"]["oke"]["value"]["availability_domains"] = []
    with pytest.raises(ValueError):
        module.parity(plan, "staging")


# Image handoff fields are exact and regional, not a free-form image or architecture selector.
@pytest.mark.parametrize(
    "field,value",
    [
        ("image_ocid", "ocid1.image.oc1.phx.synthetic"),
        ("os_major", "7"),
        ("architecture", "X86_64"),
        ("kubernetes_version", "latest"),
        ("extra", "x"),
    ],
)
def test_image_rejected(field, value):
    image = selection()
    image[field] = value
    with pytest.raises(ValueError):
        module.image_digest(image)


# Replay markers are fixed to the producer plan, use conditional creation and contain no secrets.
def test_claim_once():
    objects = {}

    # Mimic Object Storage's atomic precondition across different consumer attempts.
    def put(namespace, bucket, key, body, **kwargs):
        assert kwargs["if_none_match"] == "*"
        if key in objects:
            raise ValueError("precondition failed")
        objects[key] = body

    client = SimpleNamespace(put_object=put)
    args = (
        client,
        "namespace",
        "bucket",
        "producer/apply-attempt.json",
        report(),
        environment_values(),
    )
    module.claim_attempt(*args)
    with pytest.raises(ValueError):
        module.claim_attempt(*args)
    assert len(objects) == 1


# External effects are replaced; real input rendering, saved-plan checks, parity and orchestration
# run.
@pytest.fixture
def harness(tmp_path, monkeypatch, request):
    environment, component = getattr(request, "param", ("staging", "infrastructure"))
    state = SimpleNamespace(
        values=environment_values(environment),
        receipt=report(environment, component),
        plan=native_plan(),
        stage=applied_report(component),
        calls=[],
        objects={},
    )
    state.values["OTM_INFRASTRUCTURE_APPLY_ENABLED"] = "true"
    root = tmp_path / "source"
    state.root = root / "infra/environments" / environment / component
    state.root.mkdir(parents=True)
    monkeypatch.setattr(planning, "ROOT", root)
    monkeypatch.setattr(planning, "checked_source", Mock(return_value="/bin/terraform"))
    monkeypatch.setattr(planning, "federate", Mock(return_value={}))
    monkeypatch.setattr(planning, "initialize_terraform", Mock(return_value={}))
    inputs = planning.context(environment, component, state.values)
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    state.receipt["inputs_sha256"] = planning.render_inputs(rendered, inputs, state.values)[1]

    # Return a newly serialized archive so intentional tampering is tested against the actual
    # reader.
    def get(*args):
        return SimpleNamespace(
            data=SimpleNamespace(raw=io.BytesIO(bundle(state.receipt)), close=Mock())
        )

    # Atomic marker creation must survive a second consumer invocation and all apply failures.
    def put(namespace, bucket, key, body, **kwargs):
        assert kwargs["if_none_match"] == "*"
        if key in state.objects:
            raise ValueError("already consumed")
        state.objects[key] = body

    state.client = SimpleNamespace(get_object=get, put_object=put)
    monkeypatch.setattr(
        planning, "plan_storage", Mock(return_value=(state.client, "namespace", "bucket"))
    )

    # Successful native outputs describe this fixed environment; no cloud process is executed.
    def terraform(command, arguments, root, child_env, directory, deadline):
        state.calls.append(arguments)
        assert command == "/bin/terraform" and deadline > module.time.monotonic()
        assert "plan" not in arguments and "-auto-approve" not in arguments
        if arguments[0] == "show":
            return json.dumps(state.plan).encode()
        if arguments[0] == "apply":
            assert Path(arguments[-1]).read_bytes() == BINARY
            if getattr(state, "fail", False):
                (root / "errored.tfstate").write_bytes(b"synthetic-native-recovery-state")
                raise subprocess.TimeoutExpired("terraform", 1)
            return b"applied"
        return json.dumps({"environment": environment, "image_selection": selection()}).encode()

    monkeypatch.setattr(planning, "terraform", terraform)
    monkeypatch.setattr(
        module,
        "trusted_report",
        lambda run, env, status, values: copy.deepcopy(
            state.receipt if status == "planned" else state.stage
        ),
    )
    return state


# A valid apply consumes the exact saved binary and the second invocation cannot execute it again.
def test_apply_and_no_replay(harness):
    state = harness
    before = os.umask(0o077)
    os.umask(before)
    result = module.apply_plan(
        "staging", "infrastructure", "123", state.receipt["plan_sha256"], state.values
    )
    assert result["status"] == "applied" and set(result) == module.APPLY_FIELDS
    assert result["node_image_sha256"] == module.image_digest(selection())
    assert planning.federate.call_args.kwargs == {"lifetime_minutes": 120}
    assert state.calls[1][0] == "apply" and state.calls[2] == ["output", "-json", "cluster"]
    assert len(state.objects) == 1
    with pytest.raises(ValueError, match="already consumed"):
        module.apply_plan(
            "staging",
            "infrastructure",
            "123",
            state.receipt["plan_sha256"],
            {**state.values, "GITHUB_RUN_ID": "999"},
        )
    assert sum(call[0] == "apply" for call in state.calls) == 1
    restored = os.umask(before)
    assert restored == before
    assert not Path(state.calls[1][-1]).exists()


# Every pre-claim fault fails before Terraform apply or a consumption marker is written.
@pytest.mark.parametrize(
    "fault",
    [
        "held",
        "inputs",
        "hash",
        "key",
        "counts",
        "producer",
        "stage-confirm",
        "stage-component",
        "parity",
        "image",
        "stage-race",
    ],
)
def test_apply_preclaim_guards(harness, monkeypatch, fault):
    state = harness
    environment = "staging"
    keywords = {}
    if fault in {"stage-confirm", "stage-component", "parity", "image", "stage-race"}:
        environment = "production"
        state.values.update(environment_values(environment))
        state.receipt.update(report(environment, "infrastructure"))
        directory = state.root.parent.parent.parent / "render-prod"
        directory.mkdir()
        state.receipt["inputs_sha256"] = planning.render_inputs(
            directory,
            planning.context(environment, "infrastructure", state.values),
            state.values,
        )[1]
        keywords = {"staging_run_id": "456", "staging_tests_confirmed": fault != "stage-confirm"}
    if fault == "held":
        state.values["OTM_INFRASTRUCTURE_APPLY_ENABLED"] = "false"
    elif fault == "inputs":
        state.receipt["inputs_sha256"] = "c" * 64
    elif fault == "hash":
        state.receipt["plan_sha256"] = "short"
    elif fault == "key":
        state.receipt["object_key"] = "other/plan.tar"
    elif fault == "counts":
        state.receipt["changes"]["create"] = 1
    elif fault == "stage-component":
        state.stage["component"] = "security"
    elif fault == "parity":
        state.stage["parity_sha256"] = "c" * 64
    elif fault == "image":
        state.plan["variables"]["qualified_node_image"]["value"]["image_ocid"] = (
            "ocid1.image.oc1.iad.other"
        )
    if fault in {"producer", "stage-race"}:
        original = copy.deepcopy(state.receipt)
        calls = {"planned": 0, "applied": 0}

        # A changed producer between verification and claim cannot authorize a mutation.
        def racing(run, env, status, values):
            calls[status] += 1
            result = copy.deepcopy(original if status == "planned" else state.stage)
            if calls[status] > 1 and status == ("planned" if fault == "producer" else "applied"):
                result["attempt"] = "2"
            return result

        monkeypatch.setattr(module, "trusted_report", racing)
    with pytest.raises(ValueError):
        module.apply_plan(
            environment,
            "infrastructure",
            "123",
            state.receipt["plan_sha256"],
            state.values,
            **keywords,
        )
    assert not state.objects and not any(call[0] == "apply" for call in state.calls)


# Failure after the claim keeps the marker and native recovery state; a fresh plan is mandatory.
def test_apply_failure_retains_state(harness):
    state = harness
    state.fail = True
    with pytest.raises(module.ApplyStopped) as error:
        module.apply_plan(
            "staging", "infrastructure", "123", state.receipt["plan_sha256"], state.values
        )
    assert error.value.recovery_state_retained is True
    assert len(state.objects) == 2
    assert any(key.endswith("errored.tfstate") for key in state.objects)
    with pytest.raises(ValueError, match="already consumed"):
        module.apply_plan(
            "staging", "infrastructure", "123", state.receipt["plan_sha256"], state.values
        )
    assert sum(call[0] == "apply" for call in state.calls) == 1


# Recovery preservation rejects absent, oversized, linked or unwritable state instead of hiding
# failure.
@pytest.mark.parametrize("fault", ["absent", "empty", "oversize", "symlink", "upload"])
def test_recovery_state_guard(tmp_path, monkeypatch, fault):
    path = tmp_path / "errored.tfstate"
    if fault != "absent":
        path.write_bytes(b"" if fault == "empty" else b"synthetic-state")
    if fault == "oversize":
        monkeypatch.setattr(module, "MAX_BUNDLE", 1)
    if fault == "symlink":
        path.unlink()
        path.symlink_to(tmp_path / "other")
    client = Mock()
    if fault == "upload":
        client.put_object.side_effect = ValueError("private diagnostics")
    assert (
        module.preserve_recovery_state(client, "namespace", "bucket", "producer/", tmp_path)
        is False
    )


# CLI errors disclose only a stable stop code and recovery boolean, never Terraform/provider
# messages.
def test_cli(monkeypatch, capsys):
    apply = Mock(return_value={"status": "applied"})
    monkeypatch.setattr(module, "apply_plan", apply)
    args = [
        "--environment",
        "staging",
        "--component",
        "infrastructure",
        "--plan-run-id",
        "123",
        "--reviewed-plan-sha256",
        "a" * 64,
    ]
    assert module.main(args) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "applied"}
    apply.side_effect = module.ApplyStopped(True)
    assert module.main(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["recovery_state_retained"] is True and "No automatic retry" in result["guidance"]
    monkeypatch.setattr("sys.argv", ["otm.infrastructure_apply", *args])
    monkeypatch.setenv("OTM_INFRASTRUCTURE_ENABLED", "false")
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(module.__file__)), run_name="__main__")
    assert result.value.code == 1


# Production consumes its own plan and credentials after matching staging metadata and manual tests.
def test_production_success(harness, monkeypatch, tmp_path):
    state = harness
    state.values.update(environment_values("production"))
    state.receipt.update(report("production", "infrastructure"))
    directory = tmp_path / "production-render"
    directory.mkdir()
    state.receipt["inputs_sha256"] = planning.render_inputs(
        directory,
        planning.context("production", "infrastructure", state.values),
        state.values,
    )[1]
    old = planning.terraform

    # The exact production apply returns production's selected cluster, never staging's state.
    def execute(command, arguments, root, child_env, private, deadline):
        if arguments[0] == "output":
            return json.dumps(
                {"environment": "production", "image_selection": selection()}
            ).encode()
        return old(command, arguments, root, child_env, private, deadline)

    monkeypatch.setattr(planning, "terraform", execute)
    result = module.apply_plan(
        "production",
        "infrastructure",
        "123",
        state.receipt["plan_sha256"],
        state.values,
        staging_run_id="456",
        staging_tests_confirmed=True,
    )
    assert result["staging_apply_run_id"] == "456" and result["staging_tests_confirmed"] is True
    assert list(state.objects) == [
        "infrastructure-plans/production/infrastructure/123/1/apply-attempt.json"
    ]
    assert planning.federate.call_args.args[2] == "production"


# A mismatched cluster output fails closed even after the provider reports apply success.
def test_hosted_apply_rejects_wrong_cluster_output(harness, monkeypatch):
    state = harness
    old = planning.terraform

    # Model a provider reporting the wrong post-apply environment without touching real resources.
    def execute(command, arguments, root, child_env, private, deadline):
        if arguments[0] == "output":
            return b'{"environment":"other"}'
        return old(command, arguments, root, child_env, private, deadline)

    monkeypatch.setattr(planning, "terraform", execute)
    with pytest.raises(module.ApplyStopped) as error:
        module.apply_plan(
            "staging", "infrastructure", "123", state.receipt["plan_sha256"], state.values
        )
    assert error.value.recovery_state_retained is False
    assert len(state.objects) == 1


# A reviewer cannot approve another hash, mutable path or malformed change summary.
@pytest.mark.parametrize(
    "changes",
    [
        None,
        {"create": True, "update": 0, "delete": 0, "replace": 0},
        {"create": -1, "update": 0, "delete": 0, "replace": 0},
        {},
    ],
)
def test_reviewed_changes_rejected(changes):
    receipt = report()
    receipt["changes"] = changes
    with pytest.raises(ValueError):
        module.reviewed_plan(receipt, "infrastructure", receipt["plan_sha256"])


# A plan that forgets the retired key remains plan-only even with a matching digest.
def test_development_state_removal_receipt_rejected_for_apply():
    receipt = report()
    receipt.update(
        environment="development",
        component="infrastructure",
        object_key="infrastructure-plans/development/custody/123/1/plan.tar",
    )
    receipt["changes"]["forget"] = 1
    with pytest.raises(ValueError, match="EXACT_REVIEWED_PLAN_REQUIRED"):
        module.reviewed_plan(receipt, "infrastructure", receipt["plan_sha256"])


# A remotely committed marker with a lost response forbids both apply and any later consumer replay.
def test_uncertain_marker_response(harness, monkeypatch):
    state = harness
    original = state.client.put_object

    # Emulate successful remote creation followed by a network error; do not erase remote evidence.
    def uncertain(namespace, bucket, key, body, **kwargs):
        original(namespace, bucket, key, body, **kwargs)
        raise ConnectionError("synthetic lost response")

    monkeypatch.setattr(state.client, "put_object", uncertain)
    with pytest.raises(ConnectionError):
        module.apply_plan(
            "staging", "infrastructure", "123", state.receipt["plan_sha256"], state.values
        )
    assert len(state.objects) == 1
    with pytest.raises(ValueError, match="already consumed"):
        module.apply_plan(
            "staging",
            "infrastructure",
            "123",
            state.receipt["plan_sha256"],
            {**state.values, "GITHUB_RUN_ID": "999"},
        )
    assert not any(call[0] == "apply" for call in state.calls)


# Development refuses delete/replacement receipts before accessing OCI, even with a reviewed hash.
@pytest.mark.parametrize("destructive", ["delete", "replace"])
def test_development_refuses_destructive_plan(monkeypatch, destructive):
    values = environment_values("development")
    values["OTM_INFRASTRUCTURE_APPLY_ENABLED"] = "true"
    receipt = report("development", "infrastructure")
    receipt["changes"][destructive] = 1
    monkeypatch.setattr(planning, "checked_source", Mock(return_value="/bin/terraform"))
    monkeypatch.setattr(module, "trusted_report", Mock(return_value=receipt))
    federation = Mock()
    monkeypatch.setattr(planning, "federate", federation)
    with pytest.raises(ValueError, match="DESTRUCTIVE_DEVELOPMENT_PLAN_REJECTED"):
        module.apply_plan(
            "development", "infrastructure", receipt["run_id"], receipt["plan_sha256"], values
        )
    federation.assert_not_called()


# Development applies exactly its reviewed custody plan with no cluster or staging dependency.
@pytest.mark.parametrize("harness", [("development", "infrastructure")], indirect=True)
def test_development_applies_reviewed_infrastructure(harness):
    state = harness
    result = module.apply_plan(
        "development", "infrastructure", "123", state.receipt["plan_sha256"], state.values
    )
    assert result["status"] == "applied" and result["node_image_sha256"] is None
    assert result["staging_apply_run_id"] is None
    assert [call[0] for call in state.calls] == ["show", "apply"]
    assert len(state.objects) == 1


# Preserve the scope and cardinality of the development-only state adoption in the consumer.
@pytest.mark.parametrize(
    "environment,imports,valid",
    [
        ("development", 1, True),
        ("production", 1, False),
        ("staging", 1, False),
        ("development", 2, False),
        ("development", True, False),
    ],
)
def test_reviewed_group_import(environment, imports, valid):
    receipt = report(environment)
    receipt["changes"]["import"] = imports
    if valid:
        module.reviewed_plan(receipt, "infrastructure", receipt["plan_sha256"])
    else:
        with pytest.raises(ValueError, match="EXACT_REVIEWED_PLAN_REQUIRED"):
            module.reviewed_plan(receipt, "infrastructure", receipt["plan_sha256"])


# An approved generic apply cannot run an unqualified confidential App write or consume its plan.
def test_identity_app_write_stops_before_claim(harness):
    harness.plan["resource_changes"] = [
        {"type": "oci_identity_domains_app", "change": {"actions": ["create"]}}
    ]
    harness.receipt["changes"]["create"] = 1
    with pytest.raises(ValueError, match="OCI_APP_WORKFLOW_WRITE_UNQUALIFIED"):
        module.apply_plan(
            "staging", "infrastructure", "123", harness.receipt["plan_sha256"], harness.values
        )
    assert not harness.objects
    assert [call[0] for call in harness.calls] == ["show"]
