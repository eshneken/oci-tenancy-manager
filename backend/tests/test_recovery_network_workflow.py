"""Repair admission, context fencing, replay and immutable source semantics without a database."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_user_presence_check_units import case, result

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.recovery_console import observed_fingerprint
from otm.providers.recovery_console_simulator import configured_console_capture
from otm.providers.recovery_network import RecoveryNetworkOutcome
from otm.providers.recovery_network_simulator import simulated_network_repair
from otm.recovery_console import parse_release_cidrs
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.recovery_network import (
    RecoveryNetworkRepairs,
    latest_network_capture,
    network_command,
)
from otm.tenancies.recovery_network_contracts import (
    RecoveryNetworkEvidence,
    RecoveryNetworkIntent,
    RecoveryNetworkRequest,
)
from otm.tenancies.recovery_network_worker import RecoveryNetworkWorker


# Build independent before/desired policies alongside existing canonical subject and actor fixtures.
def network_workflow():
    c = case()
    before = parse_release_cidrs("198.51.100.0/24")
    desired = parse_release_cidrs("203.0.113.0/24")
    capture = configured_console_capture(c.b.domain_ocid, c.b.scim_resource_id, "network", before)
    source = c.source.model_copy(update={"recovery_console": capture})
    snapshot = c.snapshot.model_copy(update={"recovery_console_fingerprint": desired.fingerprint})
    identifier = uuid4()
    child = dict(
        id=snapshot.tenancy_id,
        name=snapshot.tenancy_name,
        status="active",
        operation_id=identifier,
        tenancy_ocid=c.a.tenancy_ocid,
        parent_tenancy_ocid=c.a.parent_tenancy_ocid,
        organization_id=c.a.organization_id,
        revision=snapshot.tenancy_revision,
    )
    intent = RecoveryNetworkIntent(
        workspace_id=c.a.workspace_id,
        administrator_id=c.grant["id"],
        authorization_revision=c.grant["authorization_revision"],
        snapshot=snapshot,
        source_check_id=uuid4(),
        source_hash=canonical_hash(source.model_dump(mode="json")),
        desired_fingerprint=desired.fingerprint,
        observed_fingerprint=observed_fingerprint(capture.facts),
        preview_hash="b" * 64,
        target=c.intent.target,
        expires_at=c.clock() + timedelta(hours=24),
    )
    frozen = IntentEventData(intent=intent, actor=c.actor)
    row = dict(c.row, id=identifier, kind="recovery_network_repair")
    worker = RecoveryNetworkWorker(
        c.engine,
        c.a.workspace_id,
        c.clock,
        c.loader,
        Mock(return_value=desired),
        simulated_network_repair,
    )
    presence = c.service
    presence.recovery_console_loader = Mock(return_value=desired)
    service = RecoveryNetworkRepairs(presence, Mock(), Mock())
    c.store._principal.return_value = c.a.workspace_id
    last = dict(c.check, operation_id=intent.source_check_id)
    prepared = (
        dict(child, operation_id=None),
        snapshot,
        source,
        desired,
        last,
        intent.observed_fingerprint,
        intent.preview_hash,
    )
    return SimpleNamespace(**locals())


# Closed commands require explicit consent server-side; retries reuse the exact original receipt.
def test_admission_consent_preview_and_replay():
    n = network_workflow()
    c, service = n.c, n.service
    request = RecoveryNetworkRequest(
        client_request_key=uuid4(), preview_hash=n.intent.preview_hash, acknowledged=False
    )
    with pytest.raises(OrganizationConflict, match="CONFIRMATION_REQUIRED"):
        service.start(c.principal, n.child["id"], request)
    request = request.model_copy(update={"acknowledged": True})
    with patch.object(service, "prepare", return_value=n.prepared):
        c.connection.execute.side_effect = [
            result(None),
            result(None),
            result(c.grant),
            result(None),
            result(None),
            result(None),
        ]
        accepted = service.start(c.principal, n.child["id"], request)
    assert accepted.state == "queued"
    service.enqueuer.enqueue.assert_called_once_with(c.connection, accepted.operation_id)
    digest = canonical_hash({"tenancy_id": str(n.child["id"]), **request.model_dump(mode="json")})
    prior = dict(n.row, id=accepted.operation_id, request_digest=digest, accepted_at=c.clock())
    c.connection.execute.side_effect = [result(prior)]
    assert service.start(c.principal, n.child["id"], request).operation_id == accepted.operation_id
    c.connection.execute.side_effect = [result(dict(prior, request_digest="changed"))]
    with pytest.raises(RequestConflict):
        service.start(c.principal, n.child["id"], request)
    c.connection.execute.side_effect = [result(None), result(None)]
    with patch.object(service, "prepare", return_value=(*n.prepared[:-1], "c" * 64)):
        with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
            service.start(c.principal, n.child["id"], request)


# Preview authority is requested only after the read transaction is closed, never while locked.
def test_preview_is_safe_and_network_free_in_transaction():
    n = network_workflow()
    command = network_command(n.snapshot, n.capture, n.desired, n.row["id"], uuid4())
    n.service.factory.return_value.preview.return_value = simulated_network_repair(
        command, n.capture, n.c.clock
    ).preview(command)
    with (
        patch(
            "otm.tenancies.recovery_network.read_snapshot", return_value=nullcontext(n.c.connection)
        ),
        patch.object(n.service, "prepare", return_value=n.prepared),
    ):
        preview = n.service.preview(n.c.principal, n.child["id"])
    assert preview.tenancy_id == n.child["id"]
    assert (
        "198.51" not in preview.model_dump_json() and "203.0.113" not in preview.model_dump_json()
    )
    n.service.factory.return_value.preview.assert_called_once()


# A freshly checked external edit is actual-before state; setup facts remain ownership provenance.
def test_preview_uses_sealed_observed_state_instead_of_setup_facts():
    n = network_workflow()
    command = network_command(n.snapshot, n.capture, n.desired, n.row["id"], uuid4())
    external = n.capture.model_copy(
        update={
            "facts": n.capture.facts.model_copy(
                update={"perimeter": parse_release_cidrs("192.0.2.0/24")}
            )
        }
    )
    authority = simulated_network_repair(command, external, n.c.clock).preview(command)
    n.service.factory.return_value.preview.return_value = authority
    prepared = (*n.prepared[:5], observed_fingerprint(external.facts), n.prepared[-1])
    with (
        patch(
            "otm.tenancies.recovery_network.read_snapshot", return_value=nullcontext(n.c.connection)
        ),
        patch.object(n.service, "prepare", return_value=prepared),
    ):
        preview = n.service.preview(n.c.principal, n.child["id"])
    assert preview.observed_fingerprint == observed_fingerprint(external.facts)
    assert preview.observed_fingerprint != observed_fingerprint(n.capture.facts)


# Source restoration keeps immutable setup history and uses only scoped verified operation evidence.
@pytest.mark.parametrize("fault", [None, "empty", "digest", "scope", "missing", "binding"])
def test_retained_capture_selection(fault):
    n = network_workflow()
    proof = RecoveryNetworkEvidence(
        operation_id=n.row["id"],
        tenancy_id=n.child["id"],
        snapshot=n.snapshot,
        effect="known",
        state="verified",
        safe_code="RECOVERY_NETWORK_VERIFIED",
        checked_at=n.c.clock(),
        capture=n.capture.model_copy(
            update={"facts": n.capture.facts.model_copy(update={"perimeter": n.desired})}
        ),
    )
    if fault == "binding":
        proof = proof.model_copy(
            update={
                "capture": proof.capture.model_copy(
                    update={
                        "binding": proof.capture.binding.model_copy(update={"group_id": "other"})
                    }
                )
            }
        )
    data = proof.model_dump(mode="json")
    row = dict(
        data=data,
        data_hash=canonical_hash(data),
        operation_id=proof.operation_id,
        actor_subject="otm-worker:recovery-network",
        actor_snapshot={"kind": "worker", "subject": "recovery-network"},
    )
    if fault == "digest":
        row["data_hash"] = "bad"
    origin = n.frozen.model_dump(mode="json")
    row.update(intent_data=origin, intent_hash=canonical_hash(origin))
    n.c.connection.execute.side_effect = [
        result(None if fault == "empty" else row),
    ]
    snapshot = (
        n.snapshot.model_copy(update={"connection_id": uuid4()}) if fault == "scope" else n.snapshot
    )
    source = (
        n.source.model_copy(update={"recovery_console": None}) if fault == "missing" else n.source
    )
    if fault in {"digest", "missing", "binding"}:
        with pytest.raises(ValueError):
            latest_network_capture(n.c.connection, n.c.a.workspace_id, snapshot, source)
    else:
        selected = latest_network_capture(n.c.connection, n.c.a.workspace_id, snapshot, source)
        assert (
            selected == source
            if fault in {"empty", "scope"}
            else selected.recovery_console == proof.capture
        )


# A new or stale context cannot dispatch the originally reviewed network update.
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "grant",
        "revision",
        "actor",
        "busy",
        "inactive",
        "paused",
        "desired",
        "expired",
        "snapshot",
        "source",
    ],
)
def test_worker_current_context(fault):
    n = network_workflow()
    grant = dict(n.c.grant)
    child = dict(n.child)
    if fault == "grant":
        grant["status"] = "revoked"
    if fault == "revision":
        grant["authorization_revision"] = uuid4()
    if fault == "actor":
        grant["subject"] = "other"
    if fault == "busy":
        child["operation_id"] = uuid4()
    if fault == "inactive":
        child["status"] = "terminating"
    if fault == "paused":
        n.c.config.execution_paused = True
    if fault == "desired":
        n.worker.console_loader.return_value = n.before
    if fault == "expired":
        n.c.clock.return_value = n.intent.expires_at
    n.c.connection.execute.return_value = result(grant)
    source = (
        n.source
        if fault != "source"
        else n.source.model_copy(update={"organization_id": "changed"})
    )
    with (
        patch(
            "otm.tenancies.recovery_network_worker.capture_snapshot",
            return_value=None if fault == "snapshot" else n.snapshot,
        ),
        patch("otm.tenancies.recovery_network_worker.load_presence_source", return_value=source),
    ):
        selected = n.worker.current(n.c.connection, n.row, n.frozen, child)
    assert (selected is not None) == (fault is None)


# Replayed possibly-sent attempts hold for reconciliation; no blind second write is issued.
@pytest.mark.parametrize("state", ["queued", "running", "succeeded", "absent", "blocked"])
def test_begin_replay_fence(state):
    n = network_workflow()
    row = dict(n.row, state="queued" if state == "blocked" else state)
    with (
        patch.object(
            n.worker, "locked", return_value=None if state == "absent" else (row, n.frozen, n.child)
        ),
        patch.object(
            n.worker, "current", return_value=None if state == "blocked" else (n.source, n.desired)
        ),
        patch.object(n.worker, "complete") as completed,
    ):
        ticket = n.worker.begin(n.row["id"])
    assert (ticket is not None) == (state == "queued")
    if state in {"running", "blocked"}:
        assert completed.call_args.args[-1].effect == ("unknown" if state == "running" else "none")


# A stale actor/target or non-current attempt cannot mark a provider dispatch ready.
@pytest.mark.parametrize("fault", [None, "absent", "terminal", "context", "attempt"])
def test_dispatch_fences(fault):
    n = network_workflow()
    command = network_command(n.snapshot, n.capture, n.desired, n.row["id"], uuid4())
    authority = simulated_network_repair(command, n.capture, n.c.clock).preview(command)
    n.c.connection.execute.return_value.rowcount = 0 if fault == "attempt" else 1
    with (
        patch.object(
            n.worker,
            "locked",
            return_value=None
            if fault == "absent"
            else (
                dict(n.row, state="succeeded" if fault == "terminal" else "running"),
                n.frozen,
                n.child,
            ),
        ),
        patch.object(
            n.worker, "current", return_value=None if fault == "context" else (n.source, n.desired)
        ),
        patch.object(n.worker, "complete") as completed,
    ):
        dispatched = n.worker.dispatch(n.row["id"], authority)
    assert dispatched == (fault is None)
    assert completed.called == (fault == "context")


# Preflight errors are blocked; uncertainty after dispatch never becomes no-effect.
@pytest.mark.parametrize("fault", [None, "begin", "preview", "dispatch", "write", "changed"])
def test_worker_orchestration(fault):
    n = network_workflow()
    command = network_command(n.snapshot, n.capture, n.desired, n.row["id"], uuid4())
    factory = Mock()
    n.worker.factory = factory
    facade = factory.return_value
    facade.preview.return_value = simulated_network_repair(command, n.capture, n.c.clock).preview(
        command
    )
    if fault == "changed":
        facade.preview.return_value = facade.preview.return_value.model_copy(
            update={
                "facts": n.capture.facts.model_copy(
                    update={"perimeter": parse_release_cidrs("192.0.2.0/24")}
                )
            }
        )
    facade.preview.side_effect = RuntimeError() if fault == "preview" else None
    facade.apply.return_value = RecoveryNetworkOutcome(effect="none")
    facade.apply.side_effect = RuntimeError() if fault == "write" else None
    with (
        patch.object(
            n.worker,
            "begin",
            return_value=None
            if fault == "begin"
            else (command, n.capture, n.intent.observed_fingerprint),
        ),
        patch.object(n.worker, "dispatch", return_value=fault != "dispatch"),
        patch.object(n.worker, "finish") as finished,
    ):
        n.worker.run(n.row["id"])
    if fault in {"begin", "dispatch"}:
        finished.assert_not_called()
    else:
        assert finished.call_args.args[-1].effect == ("unknown" if fault == "write" else "none")


# Completion holds unknown effects but frees known/unsent work; observed older state is retained.
@pytest.mark.parametrize(
    "effect,current", [("known", True), ("known", False), ("none", False), ("unknown", True)]
)
def test_completion_history_and_child_fence(effect, current):
    n = network_workflow()
    capture = (
        n.capture.model_copy(
            update={"facts": n.capture.facts.model_copy(update={"perimeter": n.desired})}
        )
        if effect == "known"
        else None
    )
    with patch.object(n.worker, "current", return_value=(n.source, n.desired) if current else None):
        n.worker.complete(
            n.c.connection,
            n.row,
            n.frozen,
            n.child,
            RecoveryNetworkOutcome(effect=effect, capture=capture),
        )
    queries = [str(call.args[0]) for call in n.c.connection.execute.call_args_list]
    assert any("INSERT INTO public.audit_event" in value for value in queries)
    assert any("UPDATE public.otm_tenancy" in value for value in queries) == (effect != "unknown")


# Terminal/late callbacks cannot publish a competing history after another attempt has held the row.
@pytest.mark.parametrize("state", ["running", "needs_attention", "absent"])
def test_finish_terminal_guard(state):
    n = network_workflow()
    with (
        patch.object(
            n.worker,
            "locked",
            return_value=None
            if state == "absent"
            else (dict(n.row, state=state), n.frozen, n.child),
        ),
        patch.object(n.worker, "complete") as complete,
    ):
        n.worker.finish(n.row["id"], RecoveryNetworkOutcome(effect="none"))
    assert complete.called == (state == "running")
