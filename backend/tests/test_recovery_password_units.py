"""Pure contract, private-reference and worker scheduling/uncertainty regression coverage."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_recovery_password_custody import change, context_for, custody

from otm.operations.contracts import ActorIdentity, IntentEventData, canonical_hash
from otm.providers.recovery_password import PasswordChange
from otm.tenancies.recovery_password_contracts import (
    RecoveryDisclosureEvidence,
    RecoveryPasswordEvidence,
    RecoveryPasswordIntent,
)
from otm.tenancies.recovery_password_records import admit_operation, location_of, version_of
from otm.tenancies.recovery_password_worker import RecoveryPasswordWorker

__all__ = ["custody"]
NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


# Each case has a true redacted private candidate plus independent nonsecret operation context.
@pytest.fixture
def password_case(custody):
    vault, location, _ = custody
    identifier = uuid4()
    prior = vault.stage(location, uuid4())
    change(vault, vault.candidate(prior))
    vault.promote(prior, None)
    intent = RecoveryPasswordIntent(
        workspace_id=location.target.workspace_id,
        phase="rotation",
        credential_id=location.credential_id,
        generation=1,
        location=location,
        target={"tenancy_ocid": location.target.tenancy_ocid, "display_name": "Test tenancy"},
        onboarding_operation_id=uuid4(),
        expected_current=prior.version,
        exposure_generation=1,
        due_at=NOW,
    )
    actor = ActorIdentity(issuer="urn:password-test", subject="admin", display_name="Test admin")
    row = dict(
        id=identifier,
        workspace_id=intent.workspace_id,
        kind="recovery_password",
        state="queued",
        revision=1,
        current_intent_revision=1,
        current_intent_event_id=uuid4(),
        initiating_actor_subject=actor.key,
    )
    head = dict(
        id=location.credential_id,
        workspace_id=intent.workspace_id,
        tenancy_id=location.target.tenancy_id,
        principal_binding_id=location.target.subject_binding_id,
        source_operation_id=intent.onboarding_operation_id,
        location=location.model_dump(mode="json"),
        location_hash=canonical_hash(location.model_dump(mode="json")),
        generation=1,
        exposure_generation=1,
        rotation_operation_id=identifier,
        state="usable",
        rotation_due_at=NOW,
        first_disclosure_at=NOW - timedelta(hours=4),
        active_window_grant_id=uuid4(),
        current_version_id=uuid4(),
        staged_version_id=uuid4(),
    )
    child = dict(
        id=location.target.tenancy_id,
        name="Test tenancy",
        status="active",
        operation_id=None,
        provider_mode="simulated",
        revision=1,
        tenancy_ocid=location.target.tenancy_ocid,
        parent_tenancy_ocid=location.target.parent_tenancy_ocid,
    )
    frozen = IntentEventData(intent=intent, actor=actor)
    policy = SimpleNamespace(
        execution_paused=False,
        policy=SimpleNamespace(
            workspace_id=intent.workspace_id,
            parent_tenancy_ocid=location.target.parent_tenancy_ocid,
            organization_id=location.target.organization_id,
        ),
    )
    connection = Mock()
    connection.scalar.return_value = 0
    connection.execute.return_value.rowcount = 1
    engine = Mock()
    engine.begin.side_effect = lambda: nullcontext(connection)
    worker = RecoveryPasswordWorker(
        engine,
        intent.workspace_id,
        lambda: NOW,
        Mock(return_value=policy),
        vault,
        vault,
        Mock(),
        Mock(),
        notifier=Mock(),
    )
    context = context_for(vault.candidate(vault.stage(location, identifier)))
    worker.context = Mock(return_value=context)
    worker.same_context = Mock(return_value=True)
    worker.still_current = Mock(return_value=True)
    return SimpleNamespace(
        context=context,
        vault=vault,
        location=location,
        intent=intent,
        actor=actor,
        row=row,
        head=head,
        child=child,
        frozen=frozen,
        policy=policy,
        connection=connection,
        worker=worker,
        identifier=identifier,
    )


# Operation intent and references cannot cross children, purposes or original-window phases.
@pytest.mark.parametrize(
    "fault", ["credential", "workspace", "child", "setup_due", "generation", "due", "current"]
)
def test_password_intent_scope_rejects_substitution(password_case, fault):
    c = password_case
    change = {
        "credential": {"credential_id": uuid4()},
        "workspace": {"workspace_id": "foreign"},
        "child": {
            "target": {"tenancy_ocid": "ocid1.tenancy.oc1..otmsimforeign", "display_name": "Other"}
        },
        "setup_due": {"phase": "setup"},
        "generation": {"exposure_generation": 0},
        "due": {"due_at": None},
        "current": {"expected_current": None},
    }[fault]
    with pytest.raises(ValueError):
        RecoveryPasswordIntent.model_validate(c.intent.model_copy(update=change))


# Safe outcome variants retain known superseded effects without certifying current readiness.
@pytest.mark.parametrize(
    "state,effect,code",
    [
        ("verified", "known", "RECOVERY_PASSWORD_VERIFIED"),
        ("blocked", "none", "RECOVERY_PASSWORD_BLOCKED"),
        ("unknown", "unknown", "RECOVERY_PASSWORD_UNKNOWN"),
        ("superseded", "known", "RECOVERY_PASSWORD_SUPERSEDED"),
    ],
)
def test_password_outcome_coherence(password_case, state, effect, code):
    c = password_case
    ref = c.vault.stage(c.location, c.identifier) if effect == "known" else None
    proof = RecoveryPasswordEvidence(
        credential_id=c.head["id"],
        tenancy_id=c.child["id"],
        operation_id=c.identifier,
        phase="rotation",
        state=state,
        effect=effect,
        safe_code=code,
        checked_at=NOW,
        version=ref,
    )
    with pytest.raises(ValueError):
        RecoveryPasswordEvidence.model_validate(
            proof.model_copy(update={"effect": "known" if effect != "known" else "none"})
        )
    if ref is not None:
        with pytest.raises(ValueError):
            RecoveryPasswordEvidence.model_validate(
                proof.model_copy(update={"tenancy_id": uuid4()})
            )


# The private reference decoder rejects mutated hashes and wrong heads before touching custody.
def test_reference_authentication(password_case):
    c = password_case
    assert location_of(c.head) == c.location
    with pytest.raises(ValueError):
        location_of(dict(c.head, location_hash="0" * 64))
    with pytest.raises(ValueError):
        location_of(dict(c.head, principal_binding_id=uuid4()))
    ref = c.vault.stage(c.location, c.identifier)
    row = dict(
        reference=ref.model_dump(mode="json"),
        reference_hash=canonical_hash(ref.model_dump(mode="json")),
        created_operation_id=c.identifier,
    )
    c.connection.execute.return_value.mappings.return_value.one.return_value = row
    assert version_of(c.connection, c.head, uuid4()) == ref
    row["reference_hash"] = "0" * 64
    with pytest.raises(ValueError):
        version_of(c.connection, c.head, uuid4())


# Native admission schedules one exact reference while no candidate/password enters queue payloads.
@pytest.mark.parametrize("phase", ["setup", "rotation"])
def test_admission_original_schedule(password_case, phase):
    c = password_case
    intent = (
        c.intent.model_copy(
            update={
                "phase": "setup",
                "location": c.location.model_copy(update={"secret_reference": None}),
                "due_at": None,
                "expected_current": None,
                "exposure_generation": 0,
            }
        )
        if phase == "setup"
        else c.intent.model_copy(update={"due_at": NOW + timedelta(hours=4)})
    )
    queue = Mock()
    key = admit_operation(c.connection, intent, c.actor, NOW, queue)
    assert queue.enqueue.call_count == 1
    assert queue.enqueue.call_args.args[:2] == (c.connection, key)
    assert queue.enqueue.call_args.kwargs["delay_seconds"] == (14401 if phase == "rotation" else 0)


# Early jobs, completed records and uncertain interrupted attempts never send another password.
@pytest.mark.parametrize("state", ["queued", "waiting", "running", "succeeded", "failed"])
def test_begin_replay_and_original_due(password_case, state):
    c = password_case
    c.row["state"] = state
    c.worker.locked = Mock(return_value=(c.row, c.frozen, c.child, c.head))
    c.worker.current = Mock(return_value=True)
    c.worker.finish = Mock()
    c.worker.target = Mock()
    result = c.worker.begin(c.identifier)
    if state in {"queued", "waiting"}:
        assert result[0] == c.intent
        step = next(
            call.args[0].compile().params
            for call in c.connection.execute.call_args_list
            if call.args[0].compile().params.get("command_kind") == "recovery_password"
        )
        assert step["effect_knowledge"] == "none"
    else:
        assert result is None
        assert c.worker.finish.call_count == (1 if state == "running" else 0)
    c.worker.target.change.assert_not_called()


# A future deadline or occupied child is rescheduled without moving its original exposure window.
@pytest.mark.parametrize("reason", ["future", "busy", "invalid", "missing"])
def test_begin_wait_and_context_guards(password_case, reason):
    c = password_case
    if reason == "future":
        c.worker.clock = lambda: NOW - timedelta(hours=1)
    if reason == "busy":
        c.child["operation_id"] = uuid4()
    c.worker.locked = Mock(
        return_value=None if reason == "missing" else (c.row, c.frozen, c.child, c.head)
    )
    c.worker.current = Mock(return_value=reason != "invalid")
    c.worker.finish = Mock()
    assert c.worker.begin(c.identifier) is None
    assert c.worker.enqueuer.enqueue.call_count == (1 if reason in {"future", "busy"} else 0)
    assert c.head["rotation_due_at"] == NOW


# Actual target calls are one-shot; partial stage/change/readback/promotion failures are
# distinguished.
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "stage",
        "context",
        "candidate",
        "before_write",
        "write",
        "no_effect",
        "unknown",
        "readback",
        "promote",
        "current",
    ],
)
def test_worker_one_shot_effect_knowledge(password_case, fault):
    c = password_case
    worker = c.worker
    vault = Mock(wraps=c.vault)
    target = Mock(wraps=c.vault)
    worker.vault, worker.target = vault, target
    worker.begin = Mock(return_value=(c.intent, uuid4(), c.context))
    worker.stage = Mock(return_value=fault != "context")
    worker.before_write = Mock(return_value=fault != "before_write")
    worker.locked = Mock(return_value=(dict(c.row, state="running"), c.frozen, c.child, c.head))
    worker.finish = Mock()
    if fault in {"stage", "candidate", "promote"}:
        getattr(vault, fault).side_effect = ValueError("fixed-provider-failure")
    if fault == "current":
        vault.current.side_effect = [c.vault.current(c.location), ValueError("fixed")]
    if fault == "write":
        target.change.side_effect = ValueError("fixed-provider-failure")
    if fault in {"no_effect", "unknown"}:
        target.change.return_value = PasswordChange(
            effect="none" if fault == "no_effect" else "unknown"
        )
    if fault == "readback":
        target.verify.return_value = False
    worker.run(c.identifier)
    expected = (
        "verified"
        if fault == "none"
        else "blocked"
        if fault
        in {
            "stage",
            "context",
            "candidate",
            "before_write",
            "no_effect",
        }
        else "unknown"
    )
    assert worker.finish.call_args.args[2] == expected
    assert target.change.call_count <= 1
    if fault in {"stage", "context", "candidate", "before_write"}:
        target.change.assert_not_called()


# Current machine binding guards are independent from the initiating administrator's later grant.
@pytest.mark.parametrize(
    "fault", ["none", "pause", "generation", "state", "child", "parent", "binding", "machine"]
)
def test_rotation_machine_scope(password_case, fault):
    c = password_case
    if fault == "pause":
        c.policy.execution_paused = True
    if fault == "generation":
        c.head["generation"] = 2
    if fault == "state":
        c.head["state"] = "unknown"
    if fault == "child":
        c.child["status"] = "terminated"
    if fault == "parent":
        c.child["parent_tenancy_ocid"] = "ocid1.tenancy.oc1..otmsimforeign"
    first, second = Mock(), Mock()
    first.scalar_one_or_none.return_value = None if fault == "binding" else uuid4()
    second.scalar_one_or_none.return_value = None if fault == "machine" else uuid4()
    c.connection.execute.side_effect = [first, second]
    assert c.worker.current(c.connection, c.row, c.intent, c.child, c.head) == (fault == "none")


# API/audit evidence cannot claim another duration while preserving the same nominal policy.
def test_disclosure_original_deadline_contract(password_case):
    c = password_case
    proof = RecoveryDisclosureEvidence(
        grant_id=uuid4(),
        credential_id=c.head["id"],
        tenancy_id=c.child["id"],
        disclosed_version_id=uuid4(),
        window_root_grant_id=uuid4(),
        exposure_generation=1,
        first_disclosure_at=NOW,
        rotation_due_at=NOW + timedelta(hours=4),
    )
    with pytest.raises(ValueError):
        RecoveryDisclosureEvidence.model_validate(
            proof.model_copy(
                update={
                    "rotation_due_at": NOW + timedelta(hours=4, seconds=1),
                }
            )
        )
