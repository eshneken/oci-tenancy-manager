"""Exact machine provenance, one-time allocation and durable completion boundaries."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_recovery_password_custody import custody
from test_recovery_password_units import NOW, password_case

from otm.operations.contracts import canonical_hash
from otm.storage.organization import OrganizationConflict
from otm.tenancies.recovery_password_lifecycle import (
    require_termination_ready,
    retire_terminated_credentials,
)
from otm.tenancies.recovery_password_setup import RecoveryPasswordSetup
from otm.tenancies.recovery_password_worker import RecoveryPasswordWorker

__all__ = ["custody", "password_case"]


# Result adapters retain the real SQL expressions while supplying synthetic normalized rows.
def mapped(value, *, many=False):
    result = Mock()
    result.mappings.return_value.one.return_value = value
    result.mappings.return_value.one_or_none.return_value = value
    result.mappings.return_value.all.return_value = value if many else [value]
    return result


# Locked admission authenticates immutable intent hashes and actor/workspace before custody work.
@pytest.mark.parametrize(
    "fault", ["none", "anchor", "missing", "kind", "hash", "actor", "workspace"]
)
def test_locked_intent_authentication(password_case, fault):
    c = password_case
    c.connection.scalar.return_value = None if fault == "anchor" else uuid4()
    row = (
        None
        if fault == "missing"
        else dict(c.row, kind="inspect_import" if fault == "kind" else "recovery_password")
    )
    data = c.frozen.model_dump(mode="json")
    event = dict(data=data, data_hash=canonical_hash(data))
    if fault == "hash":
        event["data_hash"] = "a" * 64
    if fault == "actor":
        row["initiating_actor_subject"] = "foreign"
    if fault == "workspace":
        c.worker.workspace = "foreign"
    c.connection.execute.side_effect = [
        Mock(),
        mapped(row),
        mapped(event),
        mapped(c.child),
        mapped(c.head),
    ]
    if fault in {"hash", "actor", "workspace"}:
        with pytest.raises(ValueError, match="INTENT_INVALID"):
            c.worker.locked(c.connection, c.identifier)
    else:
        result = c.worker.locked(c.connection, c.identifier)
        assert (result is not None) == (fault == "none")


# Dispatch must bind all three identities to the canonical active connection and same evidence.
@pytest.mark.parametrize(
    "fault", ["none", "count", "domain", "automation", "recovery", "evidence", "generation"]
)
def test_dispatch_context_exact_binding(password_case, fault):
    c = password_case
    t = c.location.target
    domain = dict(
        id=t.identity_domain_binding_id, logical_key="identity/domain", provider_ocid=t.domain_ocid
    )
    automation = dict(
        id=uuid4(), logical_key="identity/user/automation", identity_domain_binding_id=domain["id"]
    )
    recovery = dict(
        id=t.subject_binding_id,
        logical_key="identity/user/recovery",
        generation=t.binding_generation,
        scim_resource_id=t.scim_resource_id,
    )
    evidence = uuid4()
    for item in (domain, automation, recovery):
        item.update(
            created_operation_id=c.intent.onboarding_operation_id, source_evidence_event_id=evidence
        )
    machine = dict(
        id=uuid4(),
        revision=3,
        domain_binding_id=domain["id"],
        automation_binding_id=automation["id"],
        source_evidence_event_id=evidence,
    )
    if fault == "domain":
        domain["provider_ocid"] = "foreign"
    if fault == "automation":
        automation["identity_domain_binding_id"] = uuid4()
    if fault == "recovery":
        recovery["scim_resource_id"] = "foreign"
    if fault == "evidence":
        recovery["source_evidence_event_id"] = uuid4()
    if fault == "generation":
        recovery["generation"] += 1
    rows = [domain, automation, recovery][: 2 if fault == "count" else 3]
    c.connection.execute.side_effect = [mapped(machine), mapped(rows, many=True)]
    if fault == "none":
        result = RecoveryPasswordWorker.context(
            c.worker, c.connection, c.intent, c.identifier, uuid4()
        )
        assert result.connection_id == machine["id"] and result.connection_revision == 3
    else:
        with pytest.raises(ValueError, match="CONTEXT_INVALID"):
            RecoveryPasswordWorker.context(c.worker, c.connection, c.intent, c.identifier, uuid4())


# Context drift invalidates the recorded attempt independently of frozen request metadata.
def test_same_context_and_between_call_recheck(password_case):
    c = password_case
    step = dict(inputs={"machine_context": c.context.model_dump(mode="json")})
    c.connection.execute.return_value = mapped(step)
    assert RecoveryPasswordWorker.same_context(c.worker, c.connection, c.row, c.intent, uuid4())
    c.worker.context.return_value = c.context.model_copy(update={"connection_revision": 2})
    assert not RecoveryPasswordWorker.same_context(c.worker, c.connection, c.row, c.intent, uuid4())
    c.worker.locked = Mock(return_value=(dict(c.row, state="running"), c.frozen, c.child, c.head))
    c.worker.current = Mock(return_value=True)
    c.worker.same_context.return_value = False
    assert not RecoveryPasswordWorker.still_current(c.worker, c.identifier, uuid4())
    c.worker.same_context.return_value = True
    assert RecoveryPasswordWorker.still_current(c.worker, c.identifier, uuid4())


# Candidate references are immutable and persisted before marking any external write as possible.
@pytest.mark.parametrize("fault", ["none", "missing", "state", "scope", "context"])
def test_candidate_stage_and_dispatch_fence(password_case, fault):
    c = password_case
    values = (
        dict(c.row, state="failed" if fault == "state" else "running"),
        c.frozen,
        c.child,
        c.head,
    )
    c.worker.locked = Mock(return_value=None if fault == "missing" else values)
    c.worker.current = Mock(return_value=True)
    c.worker.same_context.return_value = fault != "context"
    candidate = c.vault.stage(c.location, uuid4() if fault == "scope" else c.identifier)
    assert c.worker.stage(c.identifier, c.intent, uuid4(), candidate) == (fault == "none")
    assert c.worker.before_write(c.identifier, uuid4()) == (fault in {"none", "scope"})


# Success publishes only a staged candidate; failure preserves the original deadline and notifies.
@pytest.mark.parametrize("state", ["verified", "blocked", "unknown", "superseded"])
def test_rotation_finish_is_coupled_and_replay_safe(password_case, state):
    c = password_case
    candidate = (
        c.vault.stage(c.location, c.identifier) if state in {"verified", "superseded"} else None
    )
    c.worker.current = Mock(return_value=True)
    with patch("otm.tenancies.recovery_password_worker.record_event", return_value=uuid4()):
        c.worker.finish(c.connection, (c.row, c.frozen, c.child, c.head), state, candidate, NOW)
    updates = [call.args[0].compile().params for call in c.connection.execute.call_args_list]
    credential = next(
        v for v in updates if "current_version_id" in v or v.get("state") == "unknown"
    )
    assert credential["state"] == ("usable" if state == "verified" else "unknown")
    if state == "verified":
        assert credential["rotation_due_at"] is None
    else:
        assert "rotation_due_at" not in credential
    assert c.worker.notifier.stage_recovery_failure.call_count == (state != "verified")


# Provider substitution or unexpected CURRENT must stop before even a single child password call.
@pytest.mark.parametrize("fault", ["candidate", "current"])
def test_worker_rejects_foreign_material_before_write(password_case, fault):
    c = password_case
    worker = c.worker
    worker.begin = Mock(return_value=(c.intent, uuid4(), c.context))
    worker.stage = Mock(return_value=True)
    worker.before_write = Mock(return_value=True)
    worker.finish = Mock()
    worker.locked = Mock(return_value=(dict(c.row, state="running"), c.frozen, c.child, c.head))
    vault = Mock(wraps=c.vault)
    other = c.vault.candidate(c.vault.stage(c.location, uuid4()))
    getattr(vault, fault).return_value = other
    worker.vault = vault
    worker.target = Mock()
    worker.run(c.identifier)
    worker.target.change.assert_not_called()
    assert worker.finish.call_args.args[2] == "blocked"


# Head admission only runs for current onboarding and never allocates on legacy/page reads.
def test_setup_version_and_replay(password_case):
    c = password_case
    setup = RecoveryPasswordSetup(Mock())
    with pytest.raises(ValueError, match="CURRENT_ONBOARDING"):
        setup.admit(c.connection, c.row, Mock(onboarding_version=3), NOW)
    identifier = uuid4()
    c.connection.scalar.return_value = identifier
    assert setup.admit(c.connection, c.row, Mock(onboarding_version=4), NOW) == identifier
    setup.enqueuer.enqueue.assert_not_called()


# Every direct or person-plan deletion checks outstanding exposure or uncertain mutation state.
@pytest.mark.parametrize(
    "state,exposed",
    [
        ("usable", False),
        ("usable", True),
        ("staging", False),
        ("rotating", False),
        ("unknown", False),
    ],
)
def test_termination_credential_guard(password_case, state, exposed):
    c = password_case
    # These established password-only fixtures have no managed signing head.
    c.connection.execute.return_value.scalars.return_value.all.return_value = []
    c.connection.execute.return_value.mappings.return_value.all.return_value = [
        dict(state=state, first_disclosure_at=NOW if exposed else None)
    ]
    if state == "usable" and not exposed:
        require_termination_ready(c.connection, c.intent.workspace_id, [c.child["id"]])
    else:
        with pytest.raises(OrganizationConflict, match="ROTATION_REQUIRED"):
            require_termination_ready(c.connection, c.intent.workspace_id, [c.child["id"]])
    require_termination_ready(c.connection, c.intent.workspace_id, [])
    retire_terminated_credentials(c.connection, c.intent.workspace_id, [], NOW)
    retire_terminated_credentials(c.connection, c.intent.workspace_id, [c.child["id"]], NOW)
