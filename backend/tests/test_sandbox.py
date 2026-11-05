"""Simulator policy, admission, dispatch and HTTP boundaries with isolated IO."""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_admission_service import NOW, admission
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.operations.contracts import Acceptance
from otm.operations.execution_contracts import CommittedInspection
from otm.operations.sandbox import (
    InspectionSubmission,
    SandboxAdmission,
    SandboxAuthority,
    SandboxProvider,
    SandboxUnavailable,
    load_sandbox,
    sample_sandbox,
)
from otm.providers.inspection_contracts import ExecutionContext, InspectTenancy
from otm.storage.admission import RequestConflict
from otm.storage.enqueue import workspace_queue

__all__ = ["admission", "session_case"]


# Create only operator configuration and closed synthetic references, never a fake accepted
# operation.
@pytest.fixture
def sandbox(tmp_path, admission):
    config = sample_sandbox(admission.request.workspace_id, uuid4())
    path = tmp_path / "simulation.json"
    path.write_text(config.model_dump_json())
    intent = admission.intent.model_copy(
        update={
            "policy_revision": config.policy.policy_revision,
            "access_binding_id": config.policy.access_binding_id,
            "target": admission.intent.target.model_copy(
                update={
                    "organization_id": config.policy.organization_id,
                    "parent_tenancy_ocid": config.policy.parent_tenancy_ocid,
                    "tenancy_ocid": config.targets[0].tenancy_ocid,
                }
            ),
        }
    )
    committed = CommittedInspection(
        operation_id=uuid4(),
        operation_revision=1,
        intent_event_id=uuid4(),
        intent_revision=1,
        actor=admission.actor,
        intent=intent,
    )
    return SimpleNamespace(
        config=config, path=path, workspace=config.policy.workspace_id, committed=committed
    )


# Reject duplicate/parent identities, bool versions, unknown data and missing/unsafe fixture files.
@pytest.mark.parametrize(
    "damage",
    ["duplicate", "parent", "version", "extra", "missing", "oversized", "link", "fifo", "scope"],
)
def test_sandbox_configuration_guards(sandbox, damage):
    c = sandbox
    values = c.config.model_dump(mode="json")
    if damage == "duplicate":
        values["targets"].append(values["targets"][0])
    elif damage == "parent":
        values["targets"][0]["tenancy_ocid"] = values["policy"]["parent_tenancy_ocid"]
    elif damage == "version":
        values["schema_version"] = True
    elif damage == "extra":
        values["password"] = "synthetic-marker"
    elif damage == "scope":
        values["policy"]["workspace_id"] = "other"
    c.path.write_text(json.dumps(values))
    if damage == "missing":
        c.path.unlink()
    elif damage == "oversized":
        c.path.write_bytes(b"x" * 65537)
    elif damage == "link":
        c.path.unlink()
        c.path.symlink_to(c.path.parent / "missing")
    elif damage == "fifo":
        c.path.unlink()
        os.mkfifo(c.path)
    with pytest.raises(SandboxUnavailable, match="^INSPECTION_SANDBOX_UNAVAILABLE$"):
        load_sandbox(c.path, c.workspace)


# Current administrator checks precede even catalog reads and compatible committed replays.
def test_sandbox_admission_policy_replay_and_rejections(sandbox, admission):
    c = sandbox
    sessions = Mock(require_admin=Mock(return_value=admission.actor))
    service = SandboxAdmission(Mock(), sessions, c.path, c.workspace, lambda: NOW)
    service.store = Mock(find=Mock(return_value=None), insert=Mock(return_value=admission.accepted))
    assert len(service.catalog(object()).targets) == 5
    command = InspectionSubmission(
        client_request_key=uuid4(), tenancy_ocid=c.config.targets[0].tenancy_ocid
    )
    assert service.submit(object(), command) == admission.accepted
    assert service.store.insert.call_args.args[2].policy_revision == c.config.policy.policy_revision
    with pytest.raises(ValueError, match="INVALID_SANDBOX_TARGET"):
        service.submit(
            object(),
            command.model_copy(update={"tenancy_ocid": "ocid1.tenancy.oc1..notregistered"}),
        )
    c.path.write_text(c.config.model_copy(update={"execution_paused": True}).model_dump_json())
    with pytest.raises(SandboxUnavailable):
        service.submit(object(), command)
    service.store.find.return_value = admission.accepted
    c.path.unlink()
    assert service.submit(object(), command) == admission.accepted
    sessions.require_admin.side_effect = PermissionError()
    with pytest.raises(PermissionError):
        service.submit(object(), command)
    assert workspace_queue("one") != workspace_queue("two")
    assert len(("procrastinate_queue_v1#" + workspace_queue("one")).encode()) <= 63


# Verify live grants and pause/config changes before any adapter dispatch, with stable runtime
# fences.
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "paused",
        "revision",
        "binding",
        "parent",
        "organization",
        "workspace",
        "target",
        "grant",
    ],
)
def test_sandbox_authority(sandbox, damage):
    c = sandbox
    grants = Mock()
    authority = SandboxAuthority(grants, c.path, c.workspace)
    original = authority.require_inspection(c.committed)
    assert (
        original.runtime_policy_revision
        == authority.require_inspection(c.committed).runtime_policy_revision
    )
    values = c.config.model_dump(mode="json")
    if damage == "paused":
        values["execution_paused"] = True
    elif damage in {"revision", "binding"}:
        values["policy"][
            {"revision": "policy_revision", "binding": "access_binding_id"}[damage]
        ] = str(uuid4())
    elif damage == "parent":
        values["policy"]["parent_tenancy_ocid"] = "ocid1.tenancy.oc1..differentparent"
    elif damage == "organization":
        values["policy"]["organization_id"] = "other"
    elif damage == "workspace":
        values["policy"]["workspace_id"] = "other"
    elif damage == "target":
        values["targets"] = values["targets"][1:]
    elif damage == "grant":
        grants.require_admin.side_effect = PermissionError()
    c.path.write_text(json.dumps(values))
    if damage:
        with pytest.raises((PermissionError, SandboxUnavailable)):
            authority.require_inspection(c.committed)
    else:
        assert authority.require_inspection(c.committed) == original


# Execute each real simulator result path behind the facade, never a network/OCI client.
@pytest.mark.parametrize(
    "index,code",
    [
        (0, "TENANCY_INSPECTED"),
        (1, "ACCESS_DENIED"),
        (2, "READ_TIMEOUT"),
        (3, "UNSUPPORTED_CAPABILITY"),
        (4, "TENANCY_UNOBSERVABLE"),
    ],
)
def test_sandbox_provider_scenarios(sandbox, index, code):
    c = sandbox
    context = ExecutionContext(
        workspace_id=c.workspace,
        operation_id=c.committed.operation_id,
        step_key="inspect_target",
        attempt_id=uuid4(),
        intent_revision=1,
        execution_generation=1,
        access_binding_id=c.config.policy.access_binding_id,
        credential_generation=1,
    )
    target = c.committed.intent.target.model_copy(
        update={"tenancy_ocid": c.config.targets[index].tenancy_ocid}
    )
    command = InspectTenancy(
        contract_version="execution-1-draft",
        kind="inspect_tenancy",
        context=context,
        payload=target,
    )
    assert (
        SandboxProvider(c.path, c.workspace, lambda: NOW).inspect_tenancy(command).safe_code == code
    )


# HTTP accepts only bounded child/key input after the existing session/Origin/custom-header
# boundary.
def test_submission_http_contract(session_case, sandbox):
    service = Mock()
    service.catalog.return_value = {
        "provider_mode": "simulated",
        "execution_paused": False,
        "targets": [],
    }
    receipt = Acceptance(operation_id=uuid4(), state="queued", accepted_at=NOW)
    service.submit.return_value = receipt
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), sandbox=service)
    command = {
        "client_request_key": str(uuid4()),
        "tenancy_ocid": sandbox.config.targets[0].tenancy_ocid,
    }
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/inspection-sandbox").status_code == 401
        assert client.post("/api/operations/inspect", json=command).status_code == 403
        assert (
            client.get("/api/inspection-sandbox", headers=cookie(session_case)).status_code == 200
        )
        assert (
            client.post("/api/operations/inspect", headers=headers, json=command).status_code == 202
        )
        for bad in (
            {**command, "workspace_id": "forged"},
            {"tenancy_ocid": command["tenancy_ocid"]},
            None,
        ):
            assert (
                client.post("/api/operations/inspect", headers=headers, json=bad).status_code == 400
            )
        assert (
            client.post("/api/operations/inspect", headers=headers, content=b"x" * 4097).status_code
            == 400
        )
        for failure, status in [
            (RequestConflict(), 409),
            (SandboxUnavailable(), 503),
            (ValueError(), 400),
            (RuntimeError("private"), 503),
        ]:
            service.submit.side_effect = failure
            response = client.post("/api/operations/inspect", headers=headers, json=command)
            assert response.status_code == status and "private" not in response.text
        service.catalog.side_effect = RuntimeError("private")
        assert client.get("/api/inspection-sandbox", headers=headers).status_code == 503
    with pytest.raises(ValueError):
        create_app(sandbox=service)
