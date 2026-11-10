"""Worker authority, durable phase ownership and pause behavior without provider or database I/O."""

from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_signing_key_rotation import rotation_case
from test_user_presence_check_units import result

from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.signing_key_rotation import ManagedSigningKey
from otm.tenancies.onboarding_contracts import OnboardingEvidence
from otm.tenancies.signing_key_contracts import SigningKeyEvidence, SigningKeyIntent
from otm.tenancies.signing_key_engine import SigningRotationBlocked, SigningRotationState
from otm.tenancies.signing_key_records import current_key
from otm.tenancies.signing_key_worker import SigningKeyWorker


# Boundary fixtures preserve real typed provenance while SQL results and external capabilities vary.
def worker_case():
    c = rotation_case()
    c.identifier = c.command.context.operation_id
    c.source_id, c.source_event = uuid4(), uuid4()
    c.intent = SigningKeyIntent(
        phase="rotation",
        workspace_id=c.a.workspace_id,
        credential_id=c.version.credential_id,
        subject=c.a,
        connection_id=c.command.context.connection_id,
        connection_revision=1,
        policy_hash=canonical_hash(c.policy.model_dump(mode="json")),
        expected_generation=1,
        source_operation_id=c.source_id,
        source_evidence_event_id=c.source_event,
        target=ConfigurationOperationTarget(
            tenancy_ocid=c.a.tenancy_ocid, display_name="Synthetic child"
        ),
        old=c.old,
        due_at=c.old.retire_at - timedelta(days=1),
    )
    c.frozen = IntentEventData(intent=c.intent, actor=c.actor)
    c.row = dict(
        id=c.identifier,
        workspace_id=c.a.workspace_id,
        kind="signing_key",
        state="queued",
        wait_reason=None,
        current_intent_event_id=uuid4(),
        current_intent_revision=1,
        initiating_actor_subject=c.actor.key,
        revision=1,
    )
    payload = c.old.model_dump(mode="json")
    target = c.a.model_dump(mode="json")
    c.head = dict(
        id=c.version.credential_id,
        workspace_id=c.a.workspace_id,
        tenancy_id=c.a.tenancy_id,
        principal_binding_id=c.a.subject_binding_id,
        connection_id=c.command.context.connection_id,
        source_operation_id=c.source_id,
        source_evidence_event_id=c.source_event,
        current_key=payload,
        current_hash=canonical_hash(payload),
        target=target,
        target_hash=canonical_hash(target),
        generation=1,
        state="usable",
        retire_at=c.old.retire_at,
        rotation_operation_id=c.identifier,
    )
    c.connection = MagicMock()
    c.engine = MagicMock()
    c.engine.begin.return_value = nullcontext(c.connection)
    c.engine.connect.return_value = nullcontext(c.connection)
    c.worker = SigningKeyWorker(
        c.engine, c.a.workspace_id, c.clock, c.loader, Mock(), Mock(), Mock()
    )
    c.values = (c.row, c.frozen, c.child, c.head)
    c.step = dict(
        attempt_number=1,
        current_attempt_id=c.command.context.attempt_id,
        last_outcome=None,
        evidence_event_id=uuid4(),
    )
    return c


# Exact current metadata is necessary; changed head clocks/hashes cannot renew credential age.
@pytest.mark.parametrize(
    "damage", [None, "hash", "target", "generation", "later_deadline", "earlier_usable"]
)
def test_current_key_authentication(damage):
    c = worker_case()
    if damage == "hash":
        c.head["current_hash"] = "a" * 64
    if damage == "target":
        c.head["target_hash"] = "a" * 64
    if damage == "generation":
        c.head["generation"] = 2
    if damage == "later_deadline":
        c.head["retire_at"] += timedelta(seconds=1)
    if damage == "earlier_usable":
        c.head["retire_at"] -= timedelta(seconds=1)
    if damage:
        with pytest.raises(ValueError):
            current_key(c.head)
    else:
        assert current_key(c.head) == c.old
        c.head["current_key"] = None
        assert current_key(c.head) is None


# Reading locks never authorize work with a missing anchor, foreign kind or altered intent.
@pytest.mark.parametrize("damage", [None, "anchor", "terminal", "kind", "hash", "actor"])
def test_locked_scope_and_sealed_intent(damage):
    c = worker_case()
    c.connection.scalar.return_value = None if damage == "anchor" else uuid4()
    if damage == "terminal":
        c.row["state"] = "succeeded"
    if damage == "kind":
        c.row["kind"] = "inspect_import"
    if damage == "actor":
        c.row["initiating_actor_subject"] = "other"
    data = c.frozen.model_dump(mode="json")
    event = dict(data=data, data_hash="f" * 64 if damage == "hash" else canonical_hash(data))
    c.connection.execute.side_effect = [
        result(None),
        result(c.row),
        result(event),
        result(c.child),
        result(c.head),
    ]
    if damage in {"hash", "actor"}:
        with pytest.raises(ValueError):
            c.worker.locked(c.connection, c.identifier)
    else:
        got = c.worker.locked(c.connection, c.identifier)
        assert (got is None) == (damage is not None)


# Current source, parent, identity and immutable connection are requalified before every phase.
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "policy",
        "source",
        "retired",
        "owner",
        "target",
        "child",
        "deadline",
        "capture",
        "user",
        "domain",
        "connection",
    ],
)
def test_current_dispatch_context(damage):
    c = worker_case()
    evidence = OnboardingEvidence(
        step="capture_required_users",
        outcome="verified",
        safe_code="ONBOARDING_VERIFIED",
        required_users=c.source,
    )
    data = evidence.model_dump(mode="json")
    source = dict(data=data, data_hash=canonical_hash(data))
    user = dict(
        generation=c.a.binding_generation,
        provider_ocid=c.a.provider_ocid,
        scim_resource_id=c.a.scim_resource_id,
        user_name=c.a.user_name,
        identity_domain_binding_id=c.a.identity_domain_binding_id,
    )
    domain = dict(provider_ocid=c.a.domain_ocid)
    binding = dict(revision=1, automation_binding_id=c.a.subject_binding_id)
    if damage == "policy":
        c.config.execution_paused = True
    if damage == "source":
        c.head["source_operation_id"] = uuid4()
    if damage == "retired":
        c.head["state"] = "retired"
    if damage == "owner":
        c.head["rotation_operation_id"] = uuid4()
    if damage == "target":
        c.head["target_hash"] = "a" * 64
    if damage == "child":
        c.child["parent_tenancy_ocid"] = "ocid1.tenancy.oc1..other"
    if damage == "deadline":
        c.head["retire_at"] += timedelta(seconds=1)
    if damage == "capture":
        source["data_hash"] = "a" * 64
    if damage == "user":
        user["user_name"] = "different"
    if damage == "domain":
        domain = None
    if damage == "connection":
        binding["revision"] = 2
    c.connection.execute.side_effect = [
        result(source),
        result(user),
        result(domain),
        result(binding),
    ]
    assert c.worker.current(c.connection, c.values) == (damage is None)


# Admission refuses held/in-flight/foreign waits before touching a provider or replacing an attempt.
@pytest.mark.parametrize(
    "state,reason",
    [
        ("running", None),
        ("needs_attention", None),
        ("waiting", "onboarding_activation"),
        ("waiting", "signing_rotation_due"),
    ],
)
def test_begin_holds_duplicates_and_future_due(state, reason):
    c = worker_case()
    c.row.update(state=state, wait_reason=reason)
    c.worker.locked = Mock(return_value=c.values)
    assert c.worker.begin(c.identifier) is None
    c.connection.execute.assert_not_called()


# Logical pause precedes draining; no SQL transaction sleeps and active recovery windows keep
# priority.
@pytest.mark.parametrize("draining", [True, False])
def test_begin_pause_and_phase_admission(draining):
    c = worker_case()
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    c.worker.draining = Mock(return_value=draining)
    c.connection.execute.return_value = result(None)
    ticket = c.worker.begin(c.identifier)
    if draining:
        assert ticket is None
        c.worker.enqueuer.enqueue.assert_called_once_with(
            c.connection, c.identifier, delay_seconds=15
        )
    else:
        assert ticket[2].connection_id == c.intent.connection_id
        assert ticket[2].execution_generation == 1
        assert ticket[3] is None
        c.worker.enqueuer.enqueue.assert_not_called()


# Active child operations, password windows and running acquisition rows independently delay
# rotation.
@pytest.mark.parametrize(
    "active", ["child", "password", "cost", "presence", "configuration", "none"]
)
def test_drain_sources(active):
    c = worker_case()
    if active == "child":
        c.child["operation_id"] = uuid4()
    values = {
        "password": [uuid4()],
        "cost": [None, uuid4()],
        "presence": [None, None, uuid4()],
        "configuration": [None, None, None, uuid4()],
        "none": [None] * 4,
    }
    c.connection.scalar.side_effect = values.get(active, [])
    assert c.worker.draining(c.connection, c.child) == (active != "none")


# A stale callback cannot publish a candidate or release another attempt's provider pause.
@pytest.mark.parametrize("valid", [True, False])
def test_callback_fence(valid):
    c = worker_case()
    c.row["state"] = "running"
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    c.connection.scalar.return_value = c.command.context.attempt_id if valid else uuid4()
    checkpoint = SigningRotationState(old=c.old)
    assert c.worker.callback(c.identifier, c.command.context, checkpoint) == valid
    if valid:
        inserted = c.connection.execute.call_args_list[-2].args[0].compile().params
        assert inserted["kind"] == "signing_key_outcome"
        assert (
            inserted["data"]["checkpoint"]["old"]["version"]["fingerprint"] == c.version.fingerprint
        )


# Activation changes the exact current head but retains the OLD unresolved retirement deadline.
def test_activation_and_completion_are_distinct():
    c = worker_case()
    c.row["state"] = "running"
    c.child["operation_id"] = c.identifier
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    c.connection.scalar.return_value = c.command.context.attempt_id
    uploaded = ManagedSigningKey(
        version=c.candidate, provider_key_id="candidate-id", uploaded_at=c.clock()
    )
    state = SigningRotationState(
        old=c.old, phase="retire", candidate=c.candidate, uploaded=uploaded
    )
    assert c.worker.callback(c.identifier, c.command.context, state, activate=True)
    payload = c.connection.execute.call_args_list[0].args[0].compile().params
    assert payload["generation"] == 2 and "retire_at" not in payload
    c.head.update(
        current_key=uploaded.model_dump(mode="json"),
        current_hash=canonical_hash(uploaded.model_dump(mode="json")),
        generation=2,
        state="rotating",
    )
    c.connection.execute.reset_mock()
    with patch("otm.tenancies.signing_key_worker.admit", return_value=uuid4()) as next_rotation:
        c.worker.finish(
            c.identifier,
            c.command.context,
            uploaded,
            state.model_copy(update={"phase": "complete"}),
        )
    assert next_rotation.call_args.args[1].due_at == uploaded.retire_at - timedelta(days=1)
    assert next_rotation.call_args.args[1].expected_generation == 2
    assert any(
        call.args[0].compile().params.get("state") == "succeeded"
        for call in c.connection.execute.call_args_list
    )


# A failure keeps the exact staged candidate and reservation; duplicate held delivery does not
# resume.
def test_attention_retains_checkpoint_and_original_job():
    c = worker_case()
    c.row["state"] = "running"
    checkpoint = SigningRotationState(
        old=c.old, phase="upload", candidate=c.candidate, upload_dispatched=True
    )
    c.step["last_outcome"] = SigningKeyEvidence(
        operation_id=c.identifier,
        credential_id=c.head["id"],
        tenancy_id=c.a.tenancy_id,
        phase="rotation",
        state="progress",
        safe_code="SIGNING_KEY_PROGRESS",
        checkpoint=checkpoint,
        checked_at=c.clock(),
    ).model_dump(mode="json")
    c.worker.locked = Mock(return_value=c.values)
    c.connection.execute.return_value = result(c.step)
    c.worker.fail(c.identifier, c.command.context, "SIGNING_KEY_UNAVAILABLE")
    proof = c.connection.execute.call_args_list[1].args[0].compile().params["data"]
    assert proof["checkpoint"] == c.step["last_outcome"]["checkpoint"]
    assert proof["state"] == "attention"
    c.worker.enqueuer.enqueue.assert_not_called()


# The worker yields a single checkpointed transition and queues its continuation atomically.
def test_one_phase_yields_to_native_queue():
    c = worker_case()
    c.row["state"] = "running"
    c.worker.begin = Mock(return_value=(c.frozen, c.head, c.command.context, None))
    c.worker.machine.step = Mock(
        return_value=SigningRotationState(old=c.old, phase="upload", candidate=c.candidate)
    )
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    c.connection.scalar.return_value = c.command.context.attempt_id
    c.worker.run(c.identifier)
    c.worker.enqueuer.enqueue.assert_called_once_with(c.connection, c.identifier)
    assert c.connection.execute.call_args.args[0].compile().params["state"] == "queued"


# Raw provider failures never become audit text; safe normalized failure publication retains
# context.
def test_worker_normalizes_provider_failure():
    c = worker_case()
    c.worker.begin = Mock(side_effect=OSError("private provider failure"))
    c.worker.fail = Mock()
    c.worker.run(c.identifier)
    c.worker.fail.assert_called_once_with(c.identifier, None, "SIGNING_KEY_UNAVAILABLE")
    c.worker.begin.side_effect = SigningRotationBlocked("SIGNING_KEY_PROBE_FAILED")
    c.worker.fail.side_effect = RuntimeError("private database failure")
    with pytest.raises(RuntimeError, match="^SIGNING_KEY_OUTCOME_UNAVAILABLE$") as error:
        c.worker.run(c.identifier)
    assert error.value.__cause__ is None


# A restart must recover the exact sealed checkpoint; altered cached outcomes cannot resume writes.
@pytest.mark.parametrize("tampered", [False, True])
def test_begin_recovers_sealed_checkpoint(tampered):
    c = worker_case()
    c.child["operation_id"] = c.identifier
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    checkpoint = SigningRotationState(
        old=c.old, phase="upload", candidate=c.candidate, upload_dispatched=True
    )
    data = SigningKeyEvidence(
        operation_id=c.identifier,
        credential_id=c.head["id"],
        tenancy_id=c.a.tenancy_id,
        phase="rotation",
        state="attention",
        safe_code="SIGNING_KEY_UNAVAILABLE",
        checkpoint=checkpoint,
        checked_at=c.clock(),
    ).model_dump(mode="json")
    c.step["last_outcome"] = data
    evidence = dict(data=data, data_hash="f" * 64 if tampered else canonical_hash(data))
    c.connection.execute.side_effect = [
        result(c.step),
        result(evidence),
        result(None),
        result(None),
    ]
    if tampered:
        with pytest.raises(ValueError, match="CONTEXT_CHANGED"):
            c.worker.begin(c.identifier)
    else:
        ticket = c.worker.begin(c.identifier)
        assert ticket[3] == checkpoint and ticket[2].execution_generation == 2


# A terminated child cancels future maintenance without resurrecting identities or credentials.
def test_inactive_child_cancels_scheduled_job():
    c = worker_case()
    c.child["status"] = "terminated"
    c.worker.locked = Mock(return_value=c.values)
    assert c.worker.begin(c.identifier) is None
    assert c.connection.execute.call_args.args[0].compile().params["state"] == "cancelled"


# Failed setup preserves temporary administrators and routes completion/failure through the parent.
@pytest.mark.parametrize("success", [False, True])
def test_setup_returns_to_parent_without_last_admin_cleanup(success):
    c = worker_case()
    intent = SigningKeyIntent.model_validate(
        {
            **c.intent.model_dump(),
            "phase": "setup",
            "old": None,
            "due_at": None,
            "expected_generation": 0,
        }
    )
    frozen = IntentEventData(intent=intent, actor=c.actor)
    c.row["state"] = "running"
    c.head.update(
        generation=0, state="staging", current_key=None, current_hash=None, retire_at=None
    )
    c.values = (c.row, frozen, c.child, c.head)
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    c.connection.scalar.return_value = c.command.context.attempt_id
    parent = dict(c.row, id=c.source_id)
    c.worker.record = Mock()
    c.connection.execute.return_value = result(parent)
    version = c.version.model_copy(update={"created_operation_id": c.identifier})
    key = ManagedSigningKey(version=version, provider_key_id="initial-key", uploaded_at=c.clock())
    with (
        patch("otm.tenancies.onboarding.save_step") as saved,
        patch("otm.tenancies.onboarding.transition") as moved,
        patch("otm.tenancies.signing_key_worker.admit", return_value=uuid4()),
    ):
        if success:
            c.worker.finish(c.identifier, c.command.context, key, None)
            c.worker.organization_enqueuer.enqueue.assert_called_once_with(
                c.connection, c.source_id
            )
            assert saved.call_args.kwargs["payload"].outcome == "verified"
        else:
            c.connection.execute.side_effect = [
                result(c.step),
                result(parent),
                result(None),
                result(None),
            ]
            c.worker.fail(c.identifier, c.command.context, "SIGNING_KEY_UNAVAILABLE")
            c.worker.organization_enqueuer.enqueue.assert_not_called()
            assert moved.call_args.args[3] == "needs_attention"
        assert saved.call_args.args[2] == "prepare_automation_signer"


# The separate setup delivery consumes committed canonical evidence and performs no later lifecycle
# I/O.
def test_run_setup_uses_committed_capture():
    c = worker_case()
    intent = SigningKeyIntent.model_validate(
        {
            **c.intent.model_dump(),
            "phase": "setup",
            "old": None,
            "due_at": None,
            "expected_generation": 0,
        }
    )
    frozen = IntentEventData(intent=intent, actor=c.actor)
    c.worker.begin = Mock(return_value=(frozen, c.head, c.command.context, None))
    c.worker.finish = Mock()
    data = OnboardingEvidence(
        step="capture_required_users",
        outcome="verified",
        safe_code="ONBOARDING_VERIFIED",
        required_users=c.source,
    ).model_dump(mode="json")
    c.connection.execute.return_value = result(dict(data=data, data_hash=canonical_hash(data)))
    c.worker.run(c.identifier)
    c.worker.provider.enroll.assert_called_once()
    c.worker.finish.assert_called_once()


# Missing context never steals an in-flight attempt; failures before dispatch still become visible.
@pytest.mark.parametrize("state", ["queued", "running"])
def test_failure_before_attempt_does_not_steal_running_work(state):
    c = worker_case()
    c.row["state"] = state
    c.worker.locked = Mock(return_value=c.values)
    c.connection.execute.return_value = result(None)
    c.worker.record = Mock()
    c.worker.fail(c.identifier, None, "SIGNING_KEY_CONTEXT_CHANGED")
    assert c.worker.record.call_count == (state == "queued")


# Terminal machine progress delegates to finish; a stale continuation cannot admit another phase.
@pytest.mark.parametrize("mode", ["complete", "stale", "empty"])
def test_run_terminal_and_stale_continuation(mode):
    c = worker_case()
    c.row["state"] = "running"
    state = SigningRotationState(
        old=c.old,
        phase="complete" if mode == "complete" else "upload",
        candidate=c.candidate,
        uploaded=ManagedSigningKey(
            version=c.candidate, provider_key_id="candidate", uploaded_at=c.clock()
        )
        if mode == "complete"
        else None,
    )
    c.worker.begin = Mock(
        return_value=None if mode == "empty" else (c.frozen, c.head, c.command.context, None)
    )
    c.worker.machine.step = Mock(return_value=state)
    c.worker.finish = Mock()
    c.worker.locked = Mock(return_value=c.values)
    c.worker.current = Mock(return_value=True)
    c.connection.scalar.return_value = uuid4()
    c.worker.run(c.identifier)
    assert c.worker.finish.call_count == (mode == "complete")
    c.worker.enqueuer.enqueue.assert_not_called()


# Reversible termination waits retain the signer; only a confirmed terminated child retires it.
def test_terminating_child_defers_without_retiring_custody():
    c = worker_case()
    c.child["status"] = "terminating"
    c.worker.locked = Mock(return_value=c.values)
    assert c.worker.begin(c.identifier) is None
    assert len(c.connection.execute.call_args_list) == 1
    payload = c.connection.execute.call_args.args[0].compile().params
    assert payload["state"] == "waiting" and payload["wait_reason"] == "signing_drain"
    assert "retired" not in payload.values()


# Deadline-crossing drain queues a deduplicated incident while preserving the original signer/head.
def test_overdue_password_drain_alerts_without_stealing_closure():
    c = worker_case()
    c.clock.return_value = c.old.retire_at
    c.worker.locked = Mock(return_value=c.values)
    c.worker.draining = Mock(return_value=True)
    c.worker.notifier = Mock()
    with patch("otm.tenancies.signing_key_notices.stage_failure") as notice:
        assert c.worker.begin(c.identifier) is None
    notice.assert_called_once_with(c.worker.notifier, c.connection, c.row, c.head, c.clock())
    assert not any(
        call.args[0].compile().params.get("operation_id") == c.identifier
        for call in c.connection.execute.call_args_list
    )
