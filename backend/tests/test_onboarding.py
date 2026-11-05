"""Guided setup preserves exact identity, safe pauses, replay and ordered cleanup without OCI."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import intent, person, principal, registry, service

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies import onboarding as flow
from otm.tenancies.onboarding_contracts import OnboardingCommand, OnboardingEvidence

__all__ = ["registry"]


# Build a frozen pending target independently of the database to exercise deterministic
# capabilities.
def case(state, origin="create_tenancy"):
    app, p = service(state), person(state)
    frozen = intent(
        state,
        app,
        p,
        action=origin,
        pending_tenancy_id=uuid4(),
        pending_association_id=uuid4(),
        onboarding_version=1,
    )
    actor = principal().actor
    row = dict(
        id=uuid4(),
        workspace_id=state.workspace,
        current_intent_revision=1,
        current_intent_event_id=uuid4(),
        initiating_actor_subject=actor.key,
        responsible_actor_subject=actor.key,
        revision=1,
        state="waiting",
        wait_reason="onboarding_handoff",
    )
    data = IntentEventData(intent=frozen, actor=actor)
    return app, frozen, row, data


# Contracts reject credentials, wrong account shape and unsafe action/confirmation combinations.
@pytest.mark.parametrize(
    "fields",
    [
        {"action": "verify_handoff"},
        {"action": "start_setup"},
        {"action": "start_setup", "confirm_cleanup": True, "private_key": "forbidden"},
        {
            "action": "verify_handoff",
            "handoff": {
                "tenancy_ocid": "ocid1.tenancy.oc1..otmsimchild",
                "bootstrap_user_ocid": "real-user",
            },
        },
    ],
)
def test_closed_commands(fields):
    with pytest.raises(ValueError):
        OnboardingCommand(client_request_key=uuid4(), revision=1, **fields)


# Names cannot select another user; exact supplied IDs, protected distinction and import rules
# apply.
@pytest.mark.parametrize("origin", ["create_tenancy", "import_tenancy"])
def test_facade_exact_binding_and_typed_discovery(registry, origin):
    app, frozen, _, _ = case(registry, origin)
    handoff = app.facade.onboarding_handoff(frozen)
    discovery = app.facade.inspect_onboarding(frozen, handoff)
    assert discovery.bootstrap_user_ocid != discovery.activation_user_ocid
    assert (discovery.activation_user_ocid is None) == (origin == "import_tenancy")
    assert discovery == app.facade.inspect_onboarding(frozen, handoff)
    for key, _ in flow.STEPS[1:]:
        app.facade.onboarding_step(frozen, key, discovery.model_dump(mode="json"))
    with pytest.raises(ValueError):
        app.facade.inspect_onboarding(
            frozen,
            handoff.model_copy(update={"bootstrap_user_ocid": "ocid1.user.oc1..otmsimwrong"}),
        )
    with pytest.raises(ValueError):
        app.facade.onboarding_step(frozen, "arbitrary", discovery.model_dump(mode="json"))
    with pytest.raises(ValueError):
        app.facade.onboarding_step(frozen, "retire_temporary", {"tenancy_ocid": "wrong"})


# Immutable source hashes and actor/workspace identity fence historical/foreign operation
# substitution.
def test_intent_loading_and_step_evidence(registry):
    _, frozen, row, data = case(registry)
    connection = MagicMock()
    payload = data.model_dump(mode="json")
    record = dict(data=payload, data_hash=canonical_hash(payload))
    connection.execute.return_value.mappings.return_value.one.return_value = record
    assert flow.load_intent(connection, row).intent == frozen
    record["data_hash"] = "0" * 64
    with pytest.raises(ValueError, match="INVALID_ONBOARDING_INTENT"):
        flow.load_intent(connection, row)
    historical = data.model_copy(
        update={"intent": frozen.model_copy(update={"onboarding_version": None})}
    ).model_dump(mode="json")
    record.update(data=historical, data_hash=canonical_hash(historical))
    with pytest.raises(OrganizationConflict, match="NOT_AVAILABLE"):
        flow.load_intent(connection, row)
    connection.execute.return_value.mappings.return_value = [{"step_key": "handoff"}]
    assert flow.step_rows(connection, row)["handoff"]["step_key"] == "handoff"
    event = OnboardingEvidence(step="handoff", outcome="accepted", safe_code="ONBOARDING_ACCEPTED")
    flow.save_step(
        connection, row, "handoff", NOW, inputs={}, payload=event, actor=principal().actor
    )
    flow.save_step(
        connection, row, "handoff", NOW, inputs={}, payload=event, state="needs_attention"
    )
    flow.transition(connection, row, NOW, "waiting", "Manual handoff", "onboarding_handoff")
    statements = [
        c.args[0].compile().params
        for c in connection.execute.call_args_list
        if getattr(c.args[0], "is_insert", False)
    ]
    assert any(p.get("kind") == "onboarding_action" for p in statements)
    assert any(p.get("kind") == "onboarding_outcome" for p in statements)


# Persisted waits and terminal states determine one current action; no GET runs the facade mutator.
@pytest.mark.parametrize(
    "status,wait,inspection,phase,actions",
    [
        ("queued", None, False, "preparing", ()),
        ("waiting", "onboarding_handoff", False, "handoff", ("verify_handoff",)),
        ("waiting", "onboarding_review", True, "review", ("start_setup",)),
        ("needs_attention", None, False, "blocked", ("verify_handoff",)),
        ("needs_attention", None, True, "blocked", ("start_setup",)),
        ("succeeded", None, True, "complete", ()),
        ("cancelled", None, False, "cancelled", ()),
    ],
)
def test_progress_comes_from_persisted_state(registry, status, wait, inspection, phase, actions):
    app, frozen, row, data = case(registry)
    row.update(state=status, wait_reason=wait)
    steps = {}
    if inspection:
        handoff = app.facade.onboarding_handoff(frozen)
        discovery = app.facade.inspect_onboarding(frozen, handoff)
        steps = {
            "handoff": {
                "state": "verified",
                "inputs": {"handoff": handoff.model_dump(mode="json")},
            },
            "inspect_bootstrap": {
                "state": "verified",
                "verified_at": NOW,
                "inputs": {"discovery": discovery.model_dump(mode="json")},
            },
        }
    with (
        patch.object(flow, "load_intent", return_value=data),
        patch.object(flow, "step_rows", return_value=steps),
    ):
        view = flow.progress(Mock(), row, app.facade)
    assert view.phase == phase and view.available_actions == actions and view.public_key is None


# Repeated native deliveries pause without occupying a worker or advancing past manual approval.
def test_wait_verify_preview_and_ordered_setup(registry):
    app, frozen, row, _ = case(registry)
    handoff = app.facade.onboarding_handoff(frozen)
    connection = MagicMock()
    with patch.object(flow, "step_rows", return_value={}), patch.object(flow, "transition") as move:
        assert not flow.advance(connection, row, frozen, app.facade, NOW)
        assert move.call_args.args[-1] == "onboarding_handoff"
    steps = {"handoff": {"inputs": {"handoff": handoff.model_dump(mode="json")}}}
    with (
        patch.object(flow, "step_rows", return_value=steps),
        patch.object(flow, "save_step") as saved,
        patch.object(flow, "transition") as move,
    ):
        assert not flow.advance(connection, row, frozen, app.facade, NOW)
        assert saved.call_args.args[2] == "inspect_bootstrap"
        assert move.call_args.args[-1] == "onboarding_review"
    steps["inspect_bootstrap"] = {
        "state": "verified",
        "inputs": {
            "discovery": app.facade.inspect_onboarding(frozen, handoff).model_dump(mode="json")
        },
    }
    steps["handoff"]["inputs"]["cleanup_confirmed"] = True
    with (
        patch.object(flow, "step_rows", return_value=steps),
        patch.object(flow, "save_step"),
        patch.object(app.facade, "onboarding_step", wraps=app.facade.onboarding_step) as dispatch,
    ):
        assert flow.advance(connection, row, frozen, app.facade, NOW)
        assert [c.args[1] for c in dispatch.call_args_list] == [k for k, _ in flow.STEPS[1:]]


# Failed bootstrap/replacement/recovery checks never retire temporary access or publish active
# state.
@pytest.mark.parametrize("failed", [k for k, _ in flow.STEPS])
def test_failure_and_resume_skip_verified_steps(registry, failed):
    app, frozen, row, _ = case(registry)
    handoff = app.facade.onboarding_handoff(frozen)
    discovery = app.facade.inspect_onboarding(frozen, handoff)
    steps = {
        "handoff": {
            "inputs": {"handoff": handoff.model_dump(mode="json"), "cleanup_confirmed": True}
        }
    }
    if failed != "inspect_bootstrap":
        steps["inspect_bootstrap"] = {
            "state": "verified",
            "inputs": {"discovery": discovery.model_dump(mode="json")},
        }
        for key, _ in flow.STEPS[1:]:
            if key == failed:
                break
            steps[key] = {"state": "verified"}
    with (
        patch.object(flow, "step_rows", return_value=steps),
        patch.object(flow, "save_step") as save,
        patch.object(flow, "transition") as move,
        patch.object(app.facade, "inspect_onboarding", side_effect=ValueError("private"))
        if failed == "inspect_bootstrap"
        else patch.object(app.facade, "onboarding_step", side_effect=ValueError("private")),
    ):
        assert not flow.advance(MagicMock(), row, frozen, app.facade, NOW)
        assert save.call_args.args[2] == failed
        assert save.call_args.kwargs["state"] == "needs_attention"
        assert move.call_args.args[3] == "needs_attention"
    # The same verified target resumes only the incomplete suffix of the dependency graph.
    if failed != "inspect_bootstrap":
        with (
            patch.object(flow, "step_rows", return_value=steps),
            patch.object(flow, "save_step"),
            patch.object(
                app.facade, "onboarding_step", wraps=app.facade.onboarding_step
            ) as dispatch,
        ):
            assert flow.advance(MagicMock(), row, frozen, app.facade, NOW)
            assert dispatch.call_args_list[0].args[1] == failed


# Current revision, scope, command body and responsible actor prevent silent replay/retargeting.
@pytest.mark.parametrize("origin", ["create_tenancy", "import_tenancy"])
def test_command_admission_and_replay(registry, origin):
    app, frozen, row, data = case(registry, origin)
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    handoff = app.facade.onboarding_handoff(frozen)
    command = OnboardingCommand(
        client_request_key=uuid4(), revision=1, action="verify_handoff", handoff=handoff
    )
    view = SimpleNamespace(
        available_actions=("verify_handoff",),
        suggested_handoff=handoff,
        origin="create" if origin == "create_tenancy" else "import",
    )
    with (
        patch.object(flow, "load_intent", return_value=data),
        patch.object(flow, "progress", return_value=view),
        patch.object(flow, "save_step"),
        patch.object(app, "_require_onboarding_context"),
    ):
        assert (
            flow.submit(app, connection, registry, row, principal(), command, NOW).state == "queued"
        )
        app.enqueuer.enqueue.assert_called_once()
        for altered, code in [
            (command.model_copy(update={"revision": 5}), "PREVIEW_CHANGED"),
            (
                command.model_copy(
                    update={
                        "handoff": handoff.model_copy(
                            update={"tenancy_ocid": "ocid1.tenancy.oc1..otmsimwrong"}
                        )
                    }
                ),
                "TARGET_CHANGED",
            ),
        ]:
            with pytest.raises(OrganizationConflict, match=code):
                flow.submit(app, connection, registry, row, principal(), altered, NOW)
        with pytest.raises(OrganizationConflict, match="RESPONSIBLE"):
            flow.submit(
                app,
                connection,
                registry,
                {**row, "responsible_actor_subject": "foreign"},
                principal(),
                command,
                NOW,
            )
        accepted = dict(request_hash=canonical_hash(command.model_dump(mode="json")))
        previous = dict(data=accepted, data_hash=canonical_hash(accepted))
        connection.execute.return_value.mappings.return_value.one_or_none.return_value = previous
        assert (
            flow.submit(app, connection, registry, row, principal(), command, NOW).operation_id
            == row["id"]
        )
        previous["data_hash"] = "invalid"
        with pytest.raises(RequestConflict):
            flow.submit(app, connection, registry, row, principal(), command, NOW)
    setup = OnboardingCommand(
        client_request_key=uuid4(), revision=1, action="start_setup", confirm_cleanup=True
    )
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    with (
        patch.object(flow, "load_intent", return_value=data),
        patch.object(
            flow, "progress", return_value=SimpleNamespace(available_actions=("start_setup",))
        ),
        patch.object(
            flow,
            "step_rows",
            return_value={"handoff": {"inputs": {"handoff": handoff.model_dump(mode="json")}}},
        ),
        patch.object(flow, "save_step") as save,
        patch.object(app, "_require_onboarding_context"),
    ):
        flow.submit(app, connection, registry, row, principal(), setup, NOW)
        assert save.call_args.kwargs["inputs"]["cleanup_confirmed"]


# Fresh organization/grant/scope checks happen again when an administrator resumes a long wait.
def test_service_context_and_scoped_adapters(registry):
    app, frozen, row, data = case(registry)
    app._require_onboarding_context(registry, frozen)
    registry.supplied.remove(person(registry).email)
    with pytest.raises(OrganizationConflict, match="CONTEXT_CHANGED"):
        app._require_onboarding_context(registry, frozen)
    app.mode = "unavailable"
    with pytest.raises(OrganizationConflict, match="PROVIDER_UNAVAILABLE"):
        app._require_onboarding_context(registry, frozen)
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    app.store._principal.return_value = registry.workspace
    app.store._write.return_value = nullcontext((connection, registry.workspace, NOW))
    with (
        patch("otm.tenancies.workflows.read_snapshot", return_value=nullcontext(connection)),
        patch.object(flow, "progress", return_value=SimpleNamespace(phase="projection")),
        patch.object(flow, "submit", return_value="receipt"),
        patch("otm.tenancies.workflows.registry_state", return_value=registry),
    ):
        assert app.onboarding(principal(), row["id"]).phase == "projection"
        assert app.onboarding_action(principal(), row["id"], Mock()) == "receipt"
        connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
        with pytest.raises(OrganizationConflict, match="NOT_AVAILABLE"):
            app.onboarding(principal(), uuid4())
        with pytest.raises(OrganizationConflict, match="NOT_AVAILABLE"):
            app.onboarding_action(principal(), uuid4(), Mock())


# A faulty provider cannot turn the wrong child or account into a verified cleanup preview.
@pytest.mark.parametrize(
    "field,value",
    [
        ("tenancy_ocid", "ocid1.tenancy.oc1..otmsimother"),
        ("parent_tenancy_ocid", "ocid1.tenancy.oc1..otmsimother"),
        ("bootstrap_user_ocid", "ocid1.user.oc1..otmsimother"),
        ("activation_user_ocid", "ocid1.user.oc1..otmsimother"),
        ("activation_scim_id", None),
    ],
)
def test_wrong_provider_discovery_never_becomes_verified(registry, field, value):
    app, frozen, row, _ = case(registry)
    handoff = app.facade.onboarding_handoff(frozen)
    discovery = app.facade.inspect_onboarding(frozen, handoff).model_copy(update={field: value})
    steps = {"handoff": {"inputs": {"handoff": handoff.model_dump(mode="json")}}}
    with (
        patch.object(flow, "step_rows", return_value=steps),
        patch.object(app.facade, "inspect_onboarding", return_value=discovery),
        patch.object(flow, "save_step") as save,
        patch.object(flow, "transition"),
    ):
        assert not flow.advance(MagicMock(), row, frozen, app.facade, NOW)
        assert save.call_args.kwargs["state"] == "needs_attention"
        assert save.call_args.kwargs["payload"].safe_code == "BOOTSTRAP_UNVERIFIED"


# Route parsing rejects malformed/oversized/credential-bearing bodies before the service is called.
def test_onboarding_http_bounded_commands_and_scoped_reads(registry):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from otm.tenancies.contracts import ActionReceipt
    from otm.tenancies.http import workflow_router

    app, frozen, row, data = case(registry)
    with (
        patch.object(flow, "load_intent", return_value=data),
        patch.object(flow, "step_rows", return_value={}),
    ):
        projection = flow.progress(Mock(), row, app.facade)
    boundary = Mock()
    boundary.onboarding.return_value = projection
    boundary.onboarding_action.return_value = ActionReceipt(
        operation_id=row["id"], state="queued", provider_mode="simulated", accepted_at=NOW
    )
    application = FastAPI()

    # Authentication itself is separately qualified; this test observes route/body translation only.
    @application.middleware("http")
    async def test_user(request, call_next):
        request.scope["user"] = object()
        return await call_next(request)

    application.include_router(workflow_router(boundary))
    command = OnboardingCommand(
        client_request_key=uuid4(),
        revision=1,
        action="verify_handoff",
        handoff=app.facade.onboarding_handoff(frozen),
    ).model_dump(mode="json")
    with TestClient(application) as client:
        path = "/api/tenancy-onboarding/" + str(row["id"])
        assert client.get(path).json()["phase"] == "handoff"
        assert client.post(path, json=command).status_code == 202
        assert client.post(path, content=b"{}").status_code == 400
        assert (
            client.post(
                path, content=b"x" * 4097, headers={"Content-Type": "application/json"}
            ).status_code
            == 400
        )
        assert client.post(path, json={**command, "password": "forbidden"}).status_code == 400
        assert boundary.onboarding_action.call_count == 1
        boundary.onboarding_action.return_value = ActionReceipt(
            operation_id=row["id"], state="succeeded", provider_mode="simulated", accepted_at=NOW
        )
        assert client.post(path, json=command).status_code == 200
