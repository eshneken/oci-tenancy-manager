"""Disclosure guards, original deadlines and metadata reads without a live credential service."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_recovery_password_custody import custody
from test_recovery_password_units import NOW, password_case

from otm.operations.contracts import canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.recovery_password import (
    RecoveryPasswordAccess,
    current_head,
    disclosure_ready,
    preview_digest,
)
from otm.tenancies.recovery_password_contracts import RecoveryPasswordRequest

__all__ = ["custody", "password_case"]
MODULE = "otm.tenancies.recovery_password."


# Keep real password material private while replacing only database/authority transport details.
@pytest.fixture
def access_case(password_case):
    c = password_case
    c.principal = SimpleNamespace(actor=c.actor)
    c.store = Mock(engine=c.worker.engine, clock=lambda: NOW)
    c.store._principal.return_value = c.intent.workspace_id
    c.store._write.side_effect = lambda principal: nullcontext(
        (
            c.connection,
            c.intent.workspace_id,
            NOW,
        )
    )
    c.presence = Mock(store=c.store)
    c.access = RecoveryPasswordAccess(c.presence, c.vault, Mock(), notifier=Mock())
    c.head.update(
        first_disclosure_at=None,
        rotation_due_at=None,
        active_window_grant_id=None,
        exposure_generation=0,
    )
    c.reference = c.vault.current(c.location).reference
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.child
    return c


# Metadata views never resolve secrets; state/eligibility follows recorded lifecycle and checks.
@pytest.mark.parametrize(
    "state",
    [
        "pending",
        "pending_unknown",
        "terminated",
        "none",
        "staging",
        "rotating",
        "unknown",
        "usable",
        "unavailable",
        "exposed",
        "overdue",
    ],
)
def test_access_safe_projection(access_case, state):
    c = access_case
    head = c.head
    if state in {"pending", "pending_unknown"}:
        c.child["status"] = "pending"
        head["state"] = "unknown" if state == "pending_unknown" else "staging"
    elif state == "terminated":
        c.child["status"] = "terminated"
    elif state == "none":
        head = None
    elif state in {"exposed", "overdue"}:
        head.update(
            first_disclosure_at=NOW - timedelta(hours=3),
            rotation_due_at=NOW + timedelta(hours=1) if state == "exposed" else NOW,
        )
    elif state in {"staging", "rotating", "unknown"}:
        head["state"] = state
    c.access.vault = Mock()
    with (
        patch(MODULE + "current_head", return_value=head),
        patch(
            MODULE + "disclosure_ready",
            return_value=state != "unavailable",
        ),
    ):
        result = c.access.project(c.connection, c.intent.workspace_id, c.child["id"], NOW)
    expected = {
        "pending": "preparing",
        "pending_unknown": "attention",
        "terminated": "inactive",
        "none": "not_prepared",
        "staging": "preparing",
        "unknown": "attention",
        "usable": "ready",
    }.get(state, state)
    assert result.state == expected
    assert result.available == (state in {"usable", "exposed"})
    assert result.preview_hash is not None if result.available else result.preview_hash is None
    c.access.vault.current.assert_not_called()


# Missing children fail without allocating credentials and the authenticated view uses a snapshot.
def test_missing_child_and_snapshot(access_case):
    c = access_case
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    with pytest.raises(OrganizationConflict, match="TENANCY_NOT_FOUND"):
        c.access.project(c.connection, c.intent.workspace_id, c.child["id"], NOW)
    with (
        patch(MODULE + "read_snapshot", return_value=nullcontext(c.connection)),
        patch.object(
            c.access,
            "project",
            return_value="safe-view",
        ) as project,
    ):
        assert c.access.view(c.principal, c.child["id"]) == "safe-view"
    assert project.call_args.args[1:] == (c.intent.workspace_id, c.child["id"], NOW)
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.head
    assert current_head(c.connection, c.intent.workspace_id, c.child["id"], lock=True) == c.head
    assert current_head(c.connection, c.intent.workspace_id, c.child["id"]) == c.head


# Window, generation, child revision and readiness changes invalidate earlier consent previews.
def test_preview_binds_current_window(access_case):
    c = access_case
    original = preview_digest(c.head, c.child, True)
    assert original != preview_digest(c.head, c.child, False)
    assert original != preview_digest(c.head, dict(c.child, revision=2), True)
    head = dict(c.head, first_disclosure_at=NOW, rotation_due_at=NOW + timedelta(hours=4))
    assert original != preview_digest(head, c.child, True)


# Each independent prerequisite is necessary; no one green observation substitutes for another.
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "snapshot",
        "subject",
        "latest",
        "incomplete",
        "missing",
        "stale_presence",
        "group",
        "role",
        "stale_assignments",
        "policy",
        "mfa",
        "network",
    ],
)
def test_disclosure_readiness_is_conjunctive(access_case, fault):
    c = access_case
    subject = (
        c.location.target
        if fault != "subject"
        else c.location.target.model_copy(
            update={"scim_resource_id": "foreign"},
        )
    )
    c.presence.snapshot.return_value = (
        None
        if fault == "snapshot"
        else SimpleNamespace(
            subjects=(subject, subject),
        )
    )
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        None
        if fault == "latest"
        else dict(
            state="running" if fault == "incomplete" else "complete",
            operation_id=uuid4(),
            evidence_event_id=uuid4(),
        )
    )
    subjects = {
        purpose: SimpleNamespace(state="present", stale=False)
        for purpose in ("automation", "recovery")
    }
    if fault == "missing":
        subjects["automation"].state = "missing"
    if fault == "stale_presence":
        subjects["recovery"].stale = True
    access = SimpleNamespace(
        group="missing" if fault == "group" else "verified",
        domain_role="missing" if fault == "role" else "verified",
        stale=fault == "stale_assignments",
    )
    policy = SimpleNamespace(
        state="drift" if fault == "policy" else "verified",
        mfa_exemption="drift" if fault == "mfa" else "verified",
        network_boundary="drift" if fault == "network" else "verified",
    )
    with (
        patch(MODULE + "presence_views", return_value=subjects),
        patch(
            MODULE + "administrator_view",
            return_value=access,
        ),
        patch(MODULE + "console_view", return_value=policy),
    ):
        assert disclosure_ready(
            c.presence, c.connection, c.intent.workspace_id, c.child, c.head, NOW
        ) == (fault == "none")


# Consent is checked even on direct requests before any transaction or secret acquisition.
def test_direct_request_requires_consent(access_case):
    c = access_case
    c.access.vault = Mock()
    command = RecoveryPasswordRequest(
        client_request_key=uuid4(), preview_hash="a" * 64, acknowledged=False
    )
    with pytest.raises(OrganizationConflict, match="CONFIRMATION_REQUIRED"):
        c.access.disclose(c.principal, c.child["id"], command)
    c.store._write.assert_not_called()
    c.access.vault.current.assert_not_called()


# Durable root admission, audit and notices precede reads; response loss cannot extend a window.
@pytest.mark.parametrize("joined", [False, True])
def test_root_and_joined_admission(access_case, joined):
    c = access_case
    original_root, original_operation = uuid4(), uuid4()
    if joined:
        c.head.update(
            first_disclosure_at=NOW - timedelta(hours=1),
            rotation_due_at=NOW + timedelta(hours=3),
            active_window_grant_id=original_root,
            rotation_operation_id=original_operation,
            exposure_generation=1,
        )
    queue = Mock()
    c.access.enqueuer = queue
    command = RecoveryPasswordRequest(
        client_request_key=uuid4(), preview_hash="a" * 64, acknowledged=True
    )
    with (
        patch(MODULE + "version_of", return_value=c.reference),
        patch(
            MODULE + "admit_operation",
            return_value=original_operation,
        ) as admit,
        patch(MODULE + "record_event") as audit,
    ):
        result = c.access.accept(
            c.connection,
            c.intent.workspace_id,
            c.child,
            c.head,
            c.principal,
            command,
            "b" * 64,
            NOW,
        )
    assert result["due_at"] - result["first_disclosure_attempt_at"] == timedelta(hours=4)
    assert result["accepted_operation_id"] == original_operation
    if joined:
        assert result["window_root_grant_id"] == original_root
        admit.assert_not_called()
    else:
        assert result["window_root_grant_id"] == result["id"]
        assert admit.call_args.args[1].due_at == NOW + timedelta(hours=4)
    assert audit.call_args.args[3] == "recovery_password_disclosed"
    c.access.notifier.stage_recovery_disclosure.assert_called_once()


# Replay, preflight and post-read guards prevent secret release while preserving original requests.
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "missing_child",
        "conflict",
        "unavailable",
        "preview",
        "closed",
        "expired",
        "read_error",
        "wrong_current",
        "final_changed",
        "revoked",
    ],
)
def test_disclose_order_and_denials(access_case, fault):
    c = access_case
    command = RecoveryPasswordRequest(
        client_request_key=uuid4(), preview_hash="a" * 64, acknowledged=True
    )
    digest = canonical_hash({"tenancy_id": str(c.child["id"]), **command.model_dump(mode="json")})
    request = dict(
        id=uuid4(),
        credential_id=c.head["id"],
        disclosed_version_id=c.head["current_version_id"],
        exposure_generation=1,
        payload_digest=digest,
    )
    c.head.update(
        first_disclosure_at=NOW, rotation_due_at=NOW + timedelta(hours=4), exposure_generation=1
    )
    if fault == "closed":
        request["disclosed_version_id"] = uuid4()
    if fault == "expired":
        c.head["rotation_due_at"] = NOW
    if fault == "conflict":
        request["payload_digest"] = "c" * 64
    # Child lookup then request replay are separate reads in the first admission transaction.
    child_result, prior_result = Mock(), Mock()
    child_result.mappings.return_value.one_or_none.return_value = (
        None if fault == "missing_child" else c.child
    )
    prior_result.mappings.return_value.one_or_none.return_value = (
        None if fault in {"unavailable", "preview"} else request
    )
    c.connection.execute.side_effect = [child_result, prior_result]
    views = SimpleNamespace(available=fault != "unavailable", preview_hash="b" * 64)
    c.access.project = Mock(return_value=views)
    c.access.hold = Mock()
    c.access.vault = Mock(wraps=c.vault)
    if fault == "read_error":
        c.access.vault.current.side_effect = OSError("private-failure")
    if fault == "wrong_current":
        c.access.vault.current.return_value = c.vault.candidate(c.vault.stage(c.location, uuid4()))
    if fault == "final_changed":
        views.available = False
    if fault == "revoked":
        c.store._write.side_effect = [
            nullcontext((c.connection, c.intent.workspace_id, NOW)),
            nullcontext((c.connection, c.intent.workspace_id, NOW)),
        ]
        c.access.project.side_effect = OrganizationConflict("AUTHORIZATION_CHANGED")
    with (
        patch(MODULE + "current_head", return_value=c.head),
        patch(
            MODULE + "disclosure_ready",
            return_value=True,
        ),
        patch(MODULE + "version_of", return_value=c.reference),
    ):
        if fault == "none":
            result = c.access.disclose(c.principal, c.child["id"], command)
            assert result["password"] == c.vault.current(c.location).password.get_secret_value()
            assert result["rotation_due_at"] == c.head["rotation_due_at"].isoformat()
        else:
            with pytest.raises((OrganizationConflict, RequestConflict)):
                c.access.disclose(c.principal, c.child["id"], command)
    if fault in {"missing_child", "conflict", "unavailable", "preview", "closed", "expired"}:
        c.access.vault.current.assert_not_called()
    assert c.access.hold.call_count == (1 if fault == "wrong_current" else 0)


# An unknown CURRENT holds one generation and notifies without changing its original deadline.
@pytest.mark.parametrize("changed", [False, True])
def test_hold_is_generation_fenced(access_case, changed):
    c = access_case
    row = dict(c.row, state="waiting")
    c.head["generation"] = 2 if changed else 1
    first, second = Mock(), Mock()
    first.mappings.return_value.one.return_value = c.head
    second.mappings.return_value.one.return_value = row
    c.connection.execute.side_effect = [Mock(), first, second, Mock(), Mock()]
    with patch(MODULE + "record_event"):
        c.access.hold(c.intent.workspace_id, c.head["id"], 1)
    assert c.access.notifier.stage_recovery_failure.call_count == (0 if changed else 1)
