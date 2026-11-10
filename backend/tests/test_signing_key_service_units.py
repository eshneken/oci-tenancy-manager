"""Preview authority, request replay, bounded rescue and explicit enrollment registration."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_signing_key_worker_units import worker_case
from test_user_presence_check_units import result

from otm.operations.contracts import canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.signing_key_contracts import SigningKeyRequest, SigningKeyRequestEvidence
from otm.tenancies.signing_key_records import SigningKeySetup, admit
from otm.tenancies.signing_keys import (
    SigningKeys,
    require_signing_admission,
    signing_dispatch_allowed,
)


# No source read or head without explicit managed setup invents a credential from public inventory.
@pytest.mark.parametrize("state", [None, "usable", "rotating", "attention", "retired", "expired"])
def test_admission_and_dispatch_limits(state):
    c = worker_case()
    head = None if state is None else dict(c.head, state="usable" if state == "expired" else state)
    c.connection.execute.return_value = result(head)
    at = c.old.retire_at if state == "expired" else c.clock()
    allowed = state in {None, "usable"}
    if allowed:
        require_signing_admission(c.connection, c.a.workspace_id, c.a.tenancy_id, at)
    else:
        with pytest.raises(OrganizationConflict, match="MAINTENANCE_REQUIRED"):
            require_signing_admission(c.connection, c.a.workspace_id, c.a.tenancy_id, at)
    assert signing_dispatch_allowed(c.connection, c.a.workspace_id, c.a.tenancy_id, at) == (
        state in {None, "usable", "rotating"}
    )


# Public metadata reveals only progress, never secret locator/version or private material.
@pytest.mark.parametrize(
    "state",
    ["usable", "staging", "rotating", "attention", "retired", "inactive", "absent", "expired"],
)
def test_public_state_projection(state):
    c = worker_case()
    service = SigningKeys(c.store, c.loader, Mock())
    if state == "inactive":
        c.child["status"] = "terminated"
    elif state == "expired":
        c.clock.return_value = c.old.retire_at
    elif state != "absent":
        c.head["state"] = state
    c.connection.execute.return_value = result(c.row)
    view = service.project(
        c.connection, c.principal, c.child, None if state == "absent" else c.head
    )
    assert view.state == {
        "usable": "scheduled",
        "staging": "preparing",
        "retired": "unavailable",
        "absent": "not_prepared",
        "expired": "overdue",
    }.get(state, state)
    assert (
        "secret_reference" not in view.model_dump_json()
        and "secret_version" not in view.model_dump_json()
    )
    assert view.available == (state in {"usable", "attention", "expired"})


# Source-owned row selection cannot cross a workspace or silently create a missing child.
def test_rows_and_readonly_snapshot():
    c = worker_case()
    service = SigningKeys(c.store, c.loader, Mock())
    c.connection.execute.side_effect = [result(c.child), result(c.head)]
    assert service.rows(c.connection, c.a.workspace_id, c.a.tenancy_id, lock=True) == (
        c.child,
        c.head,
    )
    c.connection.execute.side_effect = [result(None)]
    with pytest.raises(OrganizationConflict, match="TENANCY_NOT_FOUND"):
        service.rows(c.connection, c.a.workspace_id, c.a.tenancy_id)
    service.rows = Mock(return_value=(c.child, c.head))
    service.project = Mock(return_value="view")
    c.store._principal.return_value = c.a.workspace_id
    with patch("otm.tenancies.signing_keys.read_snapshot", return_value=nullcontext(c.connection)):
        assert service.view(c.principal, c.a.tenancy_id) == "view"


# Request state is frozen in immutable audit; a replay after completion returns the original job.
@pytest.mark.parametrize(
    "mode",
    ["new", "resume", "replay", "reused", "unconfirmed", "stale", "unavailable", "wrong_action"],
)
def test_explicit_request_guards(mode):
    c = worker_case()
    queue = Mock()
    service = SigningKeys(c.store, c.loader, queue)
    c.store._write.return_value = nullcontext((c.connection, c.a.workspace_id, c.clock()))
    c.row.update(
        accepted_at=c.clock(), updated_at=c.clock(), effect_knowledge="none", completed_at=None
    )
    c.connection.execute.return_value = result(c.row)
    preview = service.project(c.connection, c.principal, c.child, c.head)
    if mode == "resume":
        preview = preview.model_copy(update={"state": "attention"})
    if mode == "unavailable":
        preview = preview.model_copy(update={"available": False})
    service.rows = Mock(return_value=(c.child, c.head))
    service.project = Mock(return_value=preview)
    command = SigningKeyRequest(
        client_request_key=uuid4(),
        preview_hash="b" * 64 if mode == "stale" else preview.preview_hash,
        acknowledged=mode != "unconfirmed",
        action="resume" if mode in {"resume", "wrong_action"} else "rotate",
    )
    digest = canonical_hash({"tenancy_id": str(c.a.tenancy_id), **command.model_dump(mode="json")})
    previous = None
    if mode in {"replay", "reused"}:
        proof = SigningKeyRequestEvidence(
            operation_id=c.identifier,
            tenancy_id=c.a.tenancy_id,
            client_request_key=command.client_request_key,
            request_digest="f" * 64 if mode == "reused" else digest,
            action="rotate",
        )
        data = proof.model_dump(mode="json")
        previous = dict(data=data, data_hash=canonical_hash(data))
    c.connection.execute.side_effect = [
        result(previous),
        result(c.row),
        result(None),
        result(None),
        result(None),
    ]
    if mode in {"reused", "unconfirmed", "stale", "unavailable", "wrong_action"}:
        with pytest.raises((OrganizationConflict, RequestConflict)):
            service.request(c.principal, c.a.tenancy_id, command)
        queue.enqueue.assert_not_called()
    else:
        accepted = service.request(c.principal, c.a.tenancy_id, command)
        assert accepted.operation_id == c.identifier
        assert queue.enqueue.call_count == (0 if mode == "replay" else 1)


# Native ETA and business intent are inserted on the same transaction; future is not an active
# pause.
def test_due_admission_and_bounded_rescue():
    c = worker_case()
    queue = Mock()
    identifier = admit(c.connection, c.intent, c.actor, c.clock(), queue)
    assert identifier
    assert queue.enqueue.call_args.kwargs["delay_seconds"] > 0
    service = SigningKeys(c.store, c.loader, queue)
    with pytest.raises(ValueError, match="SCAN_LIMIT_INVALID"):
        service.enqueue_due(c.connection, c.a.workspace_id, c.clock(), 101)
    rows = Mock()
    rows.mappings.return_value = [c.head]
    c.connection.execute.side_effect = [result(None), result(None), rows, result(None)]
    with patch("otm.storage.transaction.require_transaction"):
        assert service.enqueue_due(c.connection, c.a.workspace_id, c.clock()) == 1
    assert queue.enqueue.call_args.args == (c.connection, c.identifier)


# Initial allocation binds committed identity rows, original evidence and stable parent operation
# IDs.
def test_explicit_setup_registration_and_replay():
    c = worker_case()
    queue = Mock()
    setup = SigningKeySetup(queue, c.loader)
    intent = SimpleNamespace(
        signing_key_rotation_contract=None,
        workspace_id=c.a.workspace_id,
        pending_tenancy_id=c.a.tenancy_id,
    )
    with pytest.raises(ValueError, match="SETUP_NOT_SELECTED"):
        setup.admit(c.connection, c.row, intent, c.clock())
    intent.signing_key_rotation_contract = "1"
    c.connection.execute.return_value = result(c.head)
    assert setup.admit(c.connection, c.row, intent, c.clock()) == c.head["id"]
    c.head["state"] = "attention"
    c.connection.execute.side_effect = [result(c.head), result(None), result(None)]
    assert setup.admit(c.connection, c.row, intent, c.clock()) == c.head["id"]
    queue.enqueue.assert_called_once()
    c.child.update(status="pending", operation_id=c.identifier)
    binding = dict(
        id=c.command.context.connection_id,
        revision=1,
        created_operation_id=c.identifier,
        source_evidence_event_id=c.source_event,
        domain_binding_id=c.a.identity_domain_binding_id,
        automation_binding_id=c.a.subject_binding_id,
    )
    user = dict(
        id=c.a.subject_binding_id,
        logical_key="identity/user/automation",
        source_evidence_event_id=c.source_event,
        generation=1,
        provider_ocid=c.a.provider_ocid,
        scim_resource_id=c.a.scim_resource_id,
        user_name=c.a.user_name,
    )
    domain = dict(
        id=c.a.identity_domain_binding_id,
        logical_key="identity/domain",
        provider_ocid=c.a.domain_ocid,
    )
    rows = Mock()
    rows.mappings.return_value = [user, domain]
    data = c.frozen.model_dump(mode="json")
    c.connection.execute.side_effect = [
        result(None),
        result(c.child),
        result(binding),
        rows,
        result(dict(data=data, data_hash=canonical_hash(data))),
        result(None),
        result(None),
        result(None),
    ]
    assert setup.admit(c.connection, c.row, intent, c.clock())


# Rescue uses a restricted connection and scopes the workspace without provider I/O.
def test_rescue_command_uses_existing_runtime_transaction(capsys, tmp_path):
    from otm.maintenance import main

    c = worker_case()
    settings = SimpleNamespace(local_auth=SimpleNamespace(workspace_id=c.a.workspace_id))
    with (
        patch("otm.maintenance.load_settings", return_value=settings),
        patch("otm.maintenance.maintenance_engine", return_value=c.engine),
        patch("otm.maintenance.require_runtime_role") as restricted,
        patch("otm.tenancies.signing_keys.SigningKeys") as service,
    ):
        service.return_value.enqueue_due.return_value = 2
        assert (
            main(["queue-signing-rotations", "--config", str(tmp_path / "application.toml")]) == 0
        )
    restricted.assert_called_once_with(c.engine)
    service.return_value.enqueue_due.assert_called_once_with(
        c.connection, c.a.workspace_id, service.return_value.enqueue_due.call_args.args[2]
    )
    assert '"queued_due_operations": 2' in capsys.readouterr().out
    c.engine.dispose.assert_called_once()


# A non-signing task cannot request rotation priority to evade normal queue ordering.
def test_scheduled_priority_is_signing_only():
    from otm.storage.enqueue import InspectionEnqueuer

    with pytest.raises(ValueError, match="SIGNING_ROTATION_SCHEDULE_REQUIRED"):
        InspectionEnqueuer().enqueue(Mock(), uuid4(), scheduled_rotation=True)


# Only the original future wait exposes an execution date; expedite/drain/terminal states do not.
@pytest.mark.parametrize(
    "state,reason,scheduled",
    [
        ("waiting", "signing_rotation_due", True),
        ("queued", None, False),
        ("running", None, False),
        ("waiting", "signing_drain", False),
        ("succeeded", None, False),
    ],
)
def test_operation_schedule_separate_from_acceptance(state, reason, scheduled):
    from otm.storage.operation_directory import SqlOperationDirectory

    c = worker_case()
    data = c.frozen.model_dump(mode="json")
    row = {
        **c.row,
        "state": state,
        "wait_reason": reason,
        "stage": "Rotate automation signing key",
        "accepted_at": c.clock(),
        "updated_at": c.clock(),
        "completed_at": None,
        "intent_data": data,
        "intent_hash": canonical_hash(data),
    }
    summary = SqlOperationDirectory(c.engine).summary(row)
    assert summary.scheduled_for == (c.intent.due_at if scheduled else None)
    assert ("scheduled_for" in summary.model_dump()) == scheduled
    assert summary.accepted_at == c.clock()
