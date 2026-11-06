"""Pure planning/readback and update orchestration; real SQL is qualified separately."""

import json
from contextlib import nullcontext
from itertools import chain, repeat
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_baseline_authoring import NOW, result, row
from test_baseline_publication import published_row
from test_tenancy_workflow_units import principal

from otm.configuration.rollout import (
    ConfigurationRollouts,
    operation_row,
    plan_rows,
    save_target_result,
    update_intent,
)
from otm.configuration.rollout_contracts import (
    ConfigurationIntent,
    ConfigurationOperationTarget,
    ConfigurationOutcome,
    ConfigurationPreview,
    ConfigurationUpdate,
    ManagedConfigurationObject,
)
from otm.configuration.rollout_worker import (
    ConfigurationUpdateWorker,
    dispatch_code,
    target_is_current,
)
from otm.configuration.service import draft_view
from otm.operations.contracts import InspectionPolicy, IntentEventData, canonical_hash
from otm.providers.configuration import configure_target, desired_objects
from otm.providers.configuration_simulator import SimulatedConfigurationFacade
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict


# Keep policy, immutable recipe, registry row and actor independently editable for failure tests.
@pytest.fixture
def update_case():
    actor = principal()
    baseline = draft_view(published_row(row(), actor))
    policy = InspectionPolicy(
        workspace_id="updates-unit",
        policy_revision=uuid4(),
        organization_id="synthetic-org",
        parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        access_binding_id=uuid4(),
    )
    identifier = uuid4()
    tenant = dict(
        id=uuid4(),
        workspace_id=policy.workspace_id,
        name="Synthetic child",
        tenancy_ocid="ocid1.tenancy.oc1..otmsimchild",
        parent_tenancy_ocid=policy.parent_tenancy_ocid,
        organization_id=policy.organization_id,
        status="active",
        provider_mode="simulated",
        revision=1,
        baseline_version_id=None,
        verified_baseline_version_id=None,
        operation_id=None,
        configuration_observation=None,
    )
    targets, _, _ = plan_rows([tenant], baseline, policy, None)
    grant = dict(
        id=uuid4(),
        status="active",
        authorization_revision=uuid4(),
        issuer=actor.actor.issuer,
        subject=actor.actor.subject,
    )
    intent = ConfigurationIntent(
        workspace_id=policy.workspace_id,
        policy_revision=policy.policy_revision,
        organization_id=policy.organization_id,
        parent_tenancy_ocid=policy.parent_tenancy_ocid,
        administrator_id=grant["id"],
        authorization_revision=grant["authorization_revision"],
        baseline=baseline,
        targets=targets,
        target=ConfigurationOperationTarget(
            tenancy_ocid=tenant["tenancy_ocid"], display_name=tenant["name"]
        ),
    )
    payload = IntentEventData(intent=intent, actor=actor.actor).model_dump(mode="json")
    operation = dict(
        id=identifier,
        workspace_id=policy.workspace_id,
        intent_data=payload,
        intent_hash=canonical_hash(payload),
        initiating_actor_subject=actor.actor.key,
        responsible_actor_subject=actor.actor.key,
        current_intent_event_id=uuid4(),
        state="queued",
        accepted_at=NOW,
    )
    connection = Mock()
    connection.execute.return_value = Mock(rowcount=1)
    store = Mock()
    store._principal.return_value = policy.workspace_id
    store._write.side_effect = lambda user: nullcontext((connection, policy.workspace_id, NOW))
    enqueuer = Mock()
    loader = Mock(return_value=SimpleNamespace(policy=policy, execution_paused=False))
    service = ConfigurationRollouts(store, policy=policy, policy_loader=loader, enqueuer=enqueuer)
    return SimpleNamespace(
        actor=actor,
        baseline=baseline,
        policy=policy,
        row=tenant,
        target=targets[0],
        intent=intent,
        operation=operation,
        grant=grant,
        connection=connection,
        store=store,
        queue=enqueuer,
        loader=loader,
        service=service,
        facade=SimulatedConfigurationFacade(policy),
    )


# Preview includes every active candidate and blocks the complete batch for any busy/foreign target.
def test_complete_candidate_plan(update_case):
    c = update_case
    busy = {**c.row, "id": uuid4(), "operation_id": uuid4()}
    foreign = {**c.row, "id": uuid4(), "parent_tenancy_ocid": "ocid1.tenancy.oc1..otmsimwrong"}
    current = {
        **c.row,
        "id": uuid4(),
        "baseline_version_id": c.baseline.id,
        "verified_baseline_version_id": c.baseline.id,
    }
    pending = {**c.row, "id": uuid4(), "status": "pending"}
    targets, blockers, count = plan_rows(
        [c.row, busy, foreign, current, pending], c.baseline, c.policy, None
    )
    assert (
        len(targets) == 3
        and {b.code for b in blockers} == {"TENANCY_BUSY", "REGISTERED_CHILD_REQUIRED"}
        and count == 1
    )
    assert plan_rows([c.row], None, c.policy, None) == ((), (), 0)
    assert plan_rows([c.row], c.baseline, None, None)[1][0].code == "PROVIDER_UNAVAILABLE"
    with pytest.raises(ValueError):
        c.intent.model_copy(update={"targets": (c.target, c.target)}).__class__.model_validate_json(
            c.intent.model_copy(update={"targets": (c.target, c.target)}).model_dump_json()
        )
    with pytest.raises(ValueError):
        ConfigurationIntent(**{**c.intent.model_dump(), "organization_id": "other"})


# Each category's exact applied payload is read from persisted simulator state, not desired input.
def test_apply_readback_and_verified_prefix(update_case):
    c = update_case
    objects, failed = configure_target(c.target, c.baseline, c.facade, None)
    assert failed is None and set(objects) == {"policy", "quota", "budget", "tags"}
    spy = Mock(wraps=c.facade)
    assert configure_target(c.target, c.baseline, spy, objects) == (objects, None)
    spy.apply.assert_not_called()
    assert spy.read.call_count == 4
    for key, value in objects.items():
        assert c.facade.read(c.target, key, value) == desired_objects(c.target, c.baseline)[key]
    broken = {**objects["policy"], "payload_hash": "0" * 64}
    with pytest.raises(ValueError):
        ManagedConfigurationObject.model_validate_json(json.dumps(broken))
    with pytest.raises(ValueError):
        c.facade.read(c.target, "budget", objects["policy"])
    with pytest.raises(ValueError):
        c.facade.apply(
            c.target,
            desired_objects(c.target, c.baseline)["policy"],
            desired_objects(c.target, c.baseline)["budget"],
        )
    with pytest.raises(ValueError):
        c.facade.require_target(
            c.target.model_copy(update={"parent_tenancy_ocid": "ocid1.tenancy.oc1..otmsimother"})
        )


# A failed readback retains partial state but cannot produce a full verified assignment.
@pytest.mark.parametrize("category", ["policy", "quota", "budget", "tags"])
def test_partial_readback_failure(update_case, category):
    c = update_case
    facade = Mock(wraps=c.facade)

    # Return a valid but different observed object to exercise mismatch without raw provider errors.
    def read(target, key, stored):
        if key == category:
            return desired_objects(c.target, c.baseline)["tags" if key != "tags" else "policy"]
        return c.facade.read(target, key, stored)

    facade.read.side_effect = read
    objects, failed = configure_target(c.target, c.baseline, facade, None)
    assert failed == category and category in objects


# Scoped preview binds latest and registry state; pause/misconfigured workspace cannot show
# readiness.
def test_scoped_preview_and_errors(update_case):
    c = update_case
    c.connection.execute.side_effect = [result({"registry_revision": 1}), result([c.row])]
    with (
        patch("otm.configuration.rollout.current_baseline", return_value=c.baseline),
        patch("otm.configuration.rollout.read_snapshot", return_value=nullcontext(c.connection)),
    ):
        preview = c.service.preview(c.actor, c.row["id"])
    assert preview.ready_count == 1 and not preview.blockers
    for rows, header in [([], {"registry_revision": 1}), ([c.row], None)]:
        c.connection.execute.side_effect = [result(header), result(rows)]
        with pytest.raises(OrganizationConflict):
            c.service._preview(c.connection, c.policy.workspace_id, c.row["id"])
    c.loader.return_value.execution_paused = True
    assert c.service.available_policy() is None
    assert ConfigurationRollouts(c.store).available_policy() is None


# Acceptance freezes exact targets and queues only a reference in the same administrator
# transaction.
def test_atomic_admission_and_original_replay(update_case):
    c = update_case
    preview = ConfigurationPreview(
        baseline=c.baseline,
        tenancy_id=None,
        ready_count=1,
        pending_count=0,
        blockers=(),
        preview_hash="a" * 64,
    )
    request = ConfigurationUpdate(client_request_key=uuid4(), preview_hash=preview.preview_hash)
    c.connection.execute.side_effect = chain(
        [result(None), result(c.grant)], repeat(Mock(rowcount=1))
    )
    with patch.object(c.service, "_preview", return_value=(preview, (c.target,))):
        receipt = c.service.start(c.actor, request)
    c.queue.enqueue.assert_called_once_with(c.connection, receipt.operation_id)
    statements = [call.args[0] for call in c.connection.execute.call_args_list]
    audit = next(
        stmt.compile().params
        for stmt in statements
        if getattr(stmt, "is_insert", False) and stmt.table.name == "audit_event"
    )
    assert audit["data"]["intent"]["baseline"]["id"] == str(c.baseline.id)
    assert audit["data"]["intent"]["targets"][0]["tenancy_id"] == str(c.row["id"])
    prior = {
        **c.operation,
        "request_digest": canonical_hash(
            request.model_dump(
                mode="json", include={"client_request_key", "tenancy_id", "preview_hash"}
            )
        ),
        "kind": "configuration_update",
    }
    c.connection.execute.side_effect = [result(prior)]
    assert c.service.start(c.actor, request).operation_id == c.operation["id"]
    c.connection.execute.side_effect = [result({**prior, "request_digest": "0" * 64})]
    with pytest.raises(RequestConflict):
        c.service.start(c.actor, request)


# Stale, blocked or empty scopes fail before any operation, desired assignment or native job write.
@pytest.mark.parametrize("variant", ["stale", "blocked", "empty", "write_race"])
def test_rejected_admission(update_case, variant):
    c = update_case
    preview = ConfigurationPreview(
        baseline=c.baseline,
        tenancy_id=None,
        ready_count=0 if variant == "empty" else 1,
        pending_count=0,
        blockers=(),
        preview_hash="a" * 64,
    )
    if variant == "blocked":
        c.loader.return_value.execution_paused = True
    request = ConfigurationUpdate(
        client_request_key=uuid4(),
        preview_hash="b" * 64 if variant == "stale" else preview.preview_hash,
    )
    c.connection.execute.side_effect = chain(
        [result(None), result(c.grant)], repeat(Mock(rowcount=0 if variant == "write_race" else 1))
    )
    with patch.object(
        c.service, "_preview", return_value=(preview, () if variant == "empty" else (c.target,))
    ):
        with pytest.raises(OrganizationConflict):
            c.service.start(c.actor, request)
    c.queue.enqueue.assert_not_called()


# Evidence is closed, scoped and integrity-checked; target outcomes remain reusable with audited
# attempts.
def test_evidence_and_target_steps(update_case):
    c = update_case
    assert update_intent(c.operation).intent == c.intent
    with pytest.raises(ValueError):
        update_intent({**c.operation, "intent_hash": "0" * 64})
    with pytest.raises(ValueError):
        update_intent({**c.operation, "workspace_id": "other"})
    operation_row(c.connection, c.policy.workspace_id, c.operation["id"])
    assert c.policy.workspace_id in c.connection.execute.call_args.args[0].compile().params.values()
    save_target_result(
        c.connection, c.operation, c.target, c.baseline, NOW, code="CONFIGURATION_VERIFIED"
    )
    statement = c.connection.execute.call_args_list[-2].args[0].compile().params
    assert statement["kind"] == "configuration_outcome" and statement["data"]["verified_at"]


# Progress and retries expose original fixed targets; duplicate retry does not create another job.
def test_progress_and_retry(update_case):
    c = update_case
    outcome = ConfigurationOutcome(
        tenancy_id=c.target.tenancy_id,
        baseline_id=c.baseline.id,
        safe_code="CONFIGURATION_UNVERIFIED",
        category="quota",
    )
    step = dict(
        step_key="configuration:" + str(c.target.tenancy_id),
        state="needs_attention",
        last_outcome=outcome.model_dump(mode="json"),
    )
    c.operation["state"] = "needs_attention"
    c.connection.execute.side_effect = None
    c.connection.execute.return_value = result([step])
    with (
        patch("otm.configuration.rollout.operation_row", return_value=c.operation),
        patch("otm.configuration.rollout.read_snapshot", return_value=nullcontext(c.connection)),
        patch.object(c.service, "_retryable", return_value=True),
    ):
        progress = c.service.progress(c.actor, c.operation["id"])
        assert progress.can_retry and progress.targets[0].safe_code == "CONFIGURATION_UNVERIFIED"
        receipt = c.service.retry(c.actor, c.operation["id"])
        assert receipt.state == "queued"
        c.operation["state"] = "succeeded"
        c.queue.reset_mock()
        assert c.service.retry(c.actor, c.operation["id"]).state == "succeeded"
        c.queue.enqueue.assert_not_called()
    with patch("otm.configuration.rollout.operation_row", return_value=None):
        with pytest.raises(OrganizationConflict):
            c.service.retry(c.actor, uuid4())


# Retryability reflects current grant, policy and actual repair paths rather than needs-attention
# alone.
def test_retryability_guards(update_case):
    c = update_case
    c.connection.execute.side_effect = None
    c.connection.execute.return_value = result(c.grant)
    assert c.service._retryable(c.connection, c.operation, c.intent, c.actor, {})
    c.connection.execute.side_effect = [result(c.grant), result([])]
    assert c.service._retryable(c.connection, c.operation, c.intent, c.actor)
    c.connection.execute.side_effect = None
    c.connection.execute.return_value = result({**c.grant, "status": "revoked"})
    assert not c.service._retryable(c.connection, c.operation, c.intent, c.actor, {})
    c.connection.execute.return_value = result(c.grant)
    assert not c.service._retryable(
        c.connection, {**c.operation, "responsible_actor_subject": "other"}, c.intent, c.actor, {}
    )
    outcome = ConfigurationOutcome(
        tenancy_id=c.target.tenancy_id, baseline_id=c.baseline.id, safe_code="TARGET_CHANGED"
    )
    assert not c.service._retryable(
        c.connection,
        c.operation,
        c.intent,
        c.actor,
        {"one": {"last_outcome": outcome.model_dump(mode="json")}},
    )


# Guard every frozen binding and re-check initiating authority independently of the current default.
def test_dispatch_guards(update_case):
    c = update_case
    registered = {
        **c.row,
        "revision": c.target.revision + 1,
        "operation_id": c.operation["id"],
        "baseline_version_id": c.baseline.id,
    }
    assert target_is_current(registered, c.target, c.intent, c.operation["id"])
    assert not target_is_current(
        {**registered, "revision": 999}, c.target, c.intent, c.operation["id"]
    )
    assert dispatch_code(c.intent, c.actor.actor, c.grant, c.loader()) is None
    assert dispatch_code(c.intent, c.actor.actor, None, c.loader()) == "AUTHORIZATION_CHANGED"
    c.loader.return_value.execution_paused = True
    assert dispatch_code(c.intent, c.actor.actor, c.grant, c.loader()) == "LIFECYCLE_UNAVAILABLE"
    c.loader.return_value.execution_paused = False
    c.loader.return_value.policy = c.policy.model_copy(update={"policy_revision": uuid4()})
    assert dispatch_code(c.intent, c.actor.actor, c.grant, c.loader()) == "TARGET_CHANGED"


# Worker records simulation readback separately from desired pin and clears only its exact
# reservation.
@pytest.mark.parametrize("failure", [False, True])
def test_worker_target_and_completion(update_case, failure):
    c = update_case
    registered = {
        **c.row,
        "revision": c.target.revision + 1,
        "operation_id": c.operation["id"],
        "baseline_version_id": c.baseline.id,
    }
    c.connection.execute.side_effect = chain(
        [result(None), result(c.grant), result(registered)], repeat(Mock(rowcount=1))
    )
    engine = Mock()
    engine.begin.side_effect = lambda: nullcontext(c.connection)
    worker = ConfigurationUpdateWorker(
        engine, c.policy.workspace_id, Mock(return_value=NOW), c.loader, c.facade
    )
    with (
        patch.object(worker, "_locked", return_value=c.operation),
        patch("otm.configuration.rollout_worker.published_baseline", return_value=c.baseline),
        patch("otm.configuration.rollout_worker.save_target_result") as save,
    ):
        if failure:
            c.facade.read = Mock(side_effect=ValueError("synthetic"))
        worker._target(c.operation["id"], c.target.tenancy_id)
        assert save.call_args.kwargs["code"] == (
            "CONFIGURATION_UNVERIFIED" if failure else "CONFIGURATION_VERIFIED"
        )
        values = [
            call.args[0].compile().params
            for call in c.connection.execute.call_args_list
            if getattr(call.args[0], "is_update", False)
            and call.args[0].table.name == "otm_tenancy"
        ]
        assert values[0].get("verified_baseline_version_id") == (None if failure else c.baseline.id)
        c.connection.execute.side_effect = None
        c.connection.execute.return_value = Mock(
            scalars=Mock(
                return_value=Mock(
                    all=Mock(
                        return_value=[]
                        if failure
                        else ["configuration:" + str(c.target.tenancy_id)]
                    )
                )
            )
        )
        worker._finish(c.operation["id"])
        assert c.connection.execute.call_args.args[0].compile().params["state"] == (
            "needs_attention" if failure else "succeeded"
        )


# Native replay is inert after completion, while unexpected local failure retains work for
# explicit retry.
def test_worker_run_replay_and_exception(update_case):
    c = update_case
    engine = Mock()
    engine.connect.side_effect = lambda: nullcontext(c.connection)
    engine.begin.side_effect = lambda: nullcontext(c.connection)
    worker = ConfigurationUpdateWorker(
        engine, c.policy.workspace_id, Mock(return_value=NOW), c.loader, c.facade
    )
    with (
        patch("otm.configuration.rollout_worker.operation_row", return_value=c.operation),
        patch.object(worker, "_target") as target,
        patch.object(worker, "_finish") as finish,
    ):
        worker.run(c.operation["id"])
        target.assert_called_once()
        finish.assert_called_once()
        c.operation["state"] = "succeeded"
        target.reset_mock()
        worker.run(c.operation["id"])
        target.assert_not_called()
        c.operation["state"] = "queued"
        target.side_effect = RuntimeError("synthetic")
        worker.run(c.operation["id"])
        assert c.connection.execute.call_args.args[0].compile().params["state"] == "needs_attention"


# Row locking uses the same live anchor, workspace and operation order as admission/revocation.
def test_worker_locking_and_verified_skip(update_case):
    c = update_case
    engine = Mock()
    engine.begin.side_effect = lambda: nullcontext(c.connection)
    worker = ConfigurationUpdateWorker(
        engine, c.policy.workspace_id, Mock(return_value=NOW), c.loader, c.facade
    )
    c.connection.execute.side_effect = None
    c.connection.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    with patch("otm.configuration.rollout_worker.require_transaction"):
        assert worker._locked(c.connection, c.operation["id"]) is None
        c.connection.execute.return_value.scalar_one_or_none.return_value = c.grant["id"]
        with patch("otm.configuration.rollout_worker.operation_row", return_value=c.operation):
            assert worker._locked(c.connection, c.operation["id"]) == c.operation
    c.connection.execute.return_value = result({"state": "verified"})
    with (
        patch.object(worker, "_locked", return_value=c.operation),
        patch.object(c.facade, "apply") as apply,
    ):
        worker._target(c.operation["id"], c.target.tenancy_id)
        apply.assert_not_called()


# Every allowed statement length remains representable after JSON serialization and readback.
def test_maximum_unicode_and_control_statements(update_case):
    from otm.configuration.contracts import BaselineContent

    c = update_case
    for character in ["😀", "界", "\x01"]:
        content = BaselineContent.model_validate(
            {
                **c.baseline.content.model_dump(),
                "quota_statements": tuple(str(i) + character * 1998 for i in range(50)),
            }
        )
        baseline = c.baseline.model_copy(update={"content": content})
        objects, failure = configure_target(c.target, baseline, c.facade, None)
        assert failure is None and len(objects) == 4


# Navigation counters count only currently authorized retries, never all historical failures.
def test_actionable_count_uses_supported_owned_retries(update_case):
    c = update_case
    c.connection.execute.return_value.scalars.return_value.all.return_value = [
        c.operation["id"],
        uuid4(),
    ]
    with (
        patch("otm.configuration.rollout.read_snapshot", return_value=nullcontext(c.connection)),
        patch("otm.configuration.rollout.operation_row", side_effect=[c.operation, None]),
        patch.object(c.service, "_retryable", return_value=True),
    ):
        assert c.service.actionable_count(c.actor) == 1


# Maximum accepted tag keys/values also fit their worst-case JSON escape envelope.
def test_maximum_tag_escape_envelope(update_case):
    from test_baseline_authoring import content

    c = update_case
    recipe = content(
        tag_defaults=[
            {"key": str(i).ljust(100, "\x01"), "value": "x" + "\x01" * 999} for i in range(100)
        ]
    )
    objects, failure = configure_target(
        c.target, c.baseline.model_copy(update={"content": recipe}), c.facade, None
    )
    assert failure is None and len(objects["tags"]["payload"]) <= 700000
