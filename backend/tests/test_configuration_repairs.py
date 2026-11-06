"""Repair scope, evidence and exact selected-object behavior without cloud credentials."""

from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_configuration_drift import NOW, drift_case, envelope, record, update_case

from otm.configuration.repair_contracts import ConfigurationRepairRequest
from otm.configuration.repairs import execute_repair, preview_repair, record_repair_check
from otm.configuration.rollout import ConfigurationRollouts
from otm.configuration.rollout_contracts import ConfigurationUpdate
from otm.operations.contracts import canonical_hash
from otm.storage.organization import OrganizationConflict

__all__ = ["drift_case", "update_case"]


# Keep source identity, current observation and the operator's selection independently changeable.
@pytest.fixture
def repair_case(drift_case):
    c = drift_case
    c.row["configuration_observation"] = {**c.objects, "policy": envelope(c, "policy", "missing")}
    stored, context, evidence = record(c, "drifted", "missing")
    stored["id"] = evidence.check_id
    c.history = ((stored, context, evidence),)
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.row
    c.repairs = ConfigurationRollouts(
        c.store, policy=c.policy, policy_loader=c.loader, enqueuer=c.queue, repair_facade=c.facade
    )
    with (
        patch("otm.configuration.repairs.published_baseline", return_value=c.baseline),
        patch("otm.configuration.repairs.capture_target", return_value=c.target),
        patch("otm.configuration.repairs.check_history", return_value=c.history),
        patch("otm.configuration.repairs.expected_objects", return_value=c.desired),
    ):
        c.preview, targets = preview_repair(
            c.repairs, c.connection, c.policy.workspace_id, c.row["id"], ("policy",)
        )
    c.repair_target = targets[0]
    return c


# Reject fleet scope, authored values, duplicate selection and bypassed override review.
@pytest.mark.parametrize(
    "fields",
    [
        dict(categories=[]),
        dict(categories=["policy", "policy"]),
        dict(categories=["users"]),
        dict(categories=["policy"], statements=["x"]),
    ],
)
def test_repair_request_closed(fields):
    with pytest.raises(ValidationError):
        ConfigurationRepairRequest(tenancy_id=uuid4(), **fields)


# Existing update commands remain valid; repair cannot piggyback a batch, plan or override command.
@pytest.mark.parametrize(
    "extra",
    [dict(tenancy_id=None), dict(plan_id=uuid4()), dict(repair_categories=("policy", "policy"))],
)
def test_repair_admission_scope(extra):
    values = dict(
        client_request_key=uuid4(),
        tenancy_id=uuid4(),
        preview_hash="1" * 64,
        repair_categories=("policy",),
    )
    with pytest.raises(ValidationError):
        ConfigurationUpdate(**(values | extra))


# A stale, unavailable, busy, foreign or no-longer-confirmed target has no repair preview.
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "busy",
        "inactive",
        "paused",
        "facade",
        "stale",
        "unavailable",
        "unselected",
        "changed",
    ],
)
def test_repair_preview_guards(repair_case, case):
    c = repair_case
    categories = ("quota",) if case == "unselected" else ("policy",)
    if case == "missing":
        c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    if case == "busy":
        c.row["operation_id"] = uuid4()
    if case == "inactive":
        c.row["status"] = "retired"
    if case == "paused":
        c.loader.return_value.execution_paused = True
    if case == "facade":
        c.repairs.repair_facade = None
    if case == "stale":
        c.store.clock.return_value = NOW + timedelta(days=2)
    if case in {"unavailable", "changed"}:
        c.row["configuration_observation"] = {
            **c.objects,
            "policy": envelope(c, "policy", "unavailable" if case == "unavailable" else "matching"),
        }
    with (
        patch("otm.configuration.repairs.published_baseline", return_value=c.baseline),
        patch("otm.configuration.repairs.capture_target", return_value=c.target),
        patch("otm.configuration.repairs.check_history", return_value=c.history),
        patch("otm.configuration.repairs.expected_objects", return_value=c.desired),
        pytest.raises(OrganizationConflict),
    ):
        preview_repair(c.repairs, c.connection, c.policy.workspace_id, c.row["id"], categories)


# Only exact selected bindings are written, with all-four independent reads and no desired revision.
def test_repair_selected_objects_and_result(repair_case):
    c = repair_case
    with (
        patch("otm.configuration.repairs.capture_target", return_value=c.target),
        patch.object(c.facade, "apply", wraps=c.facade.apply) as apply,
    ):
        objects, failed, results = execute_repair(
            c.connection, c.policy.workspace_id, c.row, c.repair_target, c.baseline, c.facade
        )
    assert failed is None and all(item.state == "matching" for item in results)
    assert apply.call_count == 1 and apply.call_args.args[1].category == "policy"
    assert objects["policy"] == c.objects["policy"]
    assert c.row["configuration_observation"]["policy"]["state"] == "missing"


# Context or bound-identity drift after admission cannot reach the apply capability.
@pytest.mark.parametrize("change", ["binding", "observation", "context"])
def test_repair_dispatch_fences(repair_case, change):
    c = repair_case
    target = c.repair_target.model_copy(
        update={
            {
                "binding": "repair_bindings",
                "observation": "repair_observation_hash",
                "context": "repair_context_hash",
            }[change]: {} if change == "binding" else "0" * 64
        }
    )
    with (
        patch("otm.configuration.repairs.capture_target", return_value=c.target),
        patch.object(c.facade, "apply", wraps=c.facade.apply) as apply,
        pytest.raises(ValueError, match="REPAIR_BINDINGS_CHANGED"),
    ):
        execute_repair(c.connection, c.policy.workspace_id, c.row, target, c.baseline, c.facade)
    apply.assert_not_called()


# Failed or incomplete reads cannot clear prior evidence, even if a selected write returned success.
@pytest.mark.parametrize("failure", ["before", "apply", "readback", "after"])
def test_repair_partial_and_unknown(repair_case, failure):
    c = repair_case
    facade = Mock(wraps=c.facade)
    if failure == "before":
        facade.observe.side_effect = ValueError("private provider error")
    if failure == "apply":
        facade.apply.side_effect = ValueError("private provider error")
    if failure == "readback":
        facade.read.side_effect = ValueError("private provider error")
    if failure == "after":
        calls = [
            c.facade.observe(c.target, key, c.row["configuration_observation"][key])
            for key in ("policy", "quota", "budget", "tags")
        ]
        facade.observe.side_effect = calls + [ValueError("private provider error")] * 4
    facade.policy = c.policy
    with patch("otm.configuration.repairs.capture_target", return_value=c.target):
        _, failed, _ = execute_repair(
            c.connection, c.policy.workspace_id, c.row, c.repair_target, c.baseline, facade
        )
    assert failed is not None


# Completion seals observed evidence against the actual post-release registry generation.
def test_repair_seals_current_context(repair_case):
    c = repair_case
    c.connection.execute.return_value.mappings.return_value.one.return_value = c.row
    with (
        patch("otm.configuration.repairs.capture_target", return_value=c.target),
        patch("otm.configuration.repairs.save_check") as save,
    ):
        results = c.history[0][2].results
        record_repair_check(c.connection, c.operation, c.row, c.policy, results, NOW)
    assert save.call_args.args[4] == "drifted"
    assert save.call_args.args[2] == c.target
    assert canonical_hash(c.target.model_dump(mode="json")) == c.repair_target.repair_context_hash


# Admission keeps the accepted revision and prior finding context unchanged while reserving work.
def test_repair_atomic_admission_and_preview_wrapper(repair_case):
    from contextlib import nullcontext
    from itertools import chain, repeat

    from test_configuration_updates import result

    c = repair_case
    request = ConfigurationUpdate(
        client_request_key=uuid4(),
        tenancy_id=c.row["id"],
        preview_hash=c.preview.preview_hash,
        repair_categories=("policy",),
    )
    c.connection.execute.side_effect = chain(
        [result(None), result(c.grant)], repeat(Mock(rowcount=1))
    )
    with (
        patch.object(c.repairs, "_preview", return_value=(c.preview, (c.repair_target,))),
        patch("otm.configuration.rollout.load_configuration", return_value=None),
        patch("otm.configuration.rollout.accept_configuration") as revision,
    ):
        receipt = c.repairs.start(c.actor, request)
    revision.assert_not_called()
    c.queue.enqueue.assert_called_once_with(c.connection, receipt.operation_id)
    statements = [call.args[0] for call in c.connection.execute.call_args_list]
    changes = next(
        stmt.compile().params
        for stmt in statements
        if getattr(stmt, "is_update", False) and stmt.table.name == "otm_tenancy"
    )
    assert changes["revision"] == c.row["revision"]
    assert changes["desired_configuration_id"] is None
    with (
        patch("otm.configuration.rollout.read_snapshot", return_value=nullcontext(c.connection)),
        patch(
            "otm.configuration.repairs.preview_repair", return_value=(c.preview, (c.repair_target,))
        ),
    ):
        assert (
            c.repairs.preview_repair(
                c.actor, ConfigurationRepairRequest(tenancy_id=c.row["id"], categories=("policy",))
            )
            == c.preview
        )


# The actual worker repair branch seals only complete success and classifies changed scope safely.
@pytest.mark.parametrize("failed", [False, True])
def test_worker_repair_branch(repair_case, failed):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from otm.configuration.rollout_contracts import (
        ConfigurationIntent,
        ConfigurationOperationTarget,
    )
    from otm.configuration.rollout_worker import ConfigurationUpdateWorker

    c = repair_case
    intent = ConfigurationIntent(
        change_kind="repair",
        workspace_id=c.policy.workspace_id,
        policy_revision=c.policy.policy_revision,
        organization_id=c.policy.organization_id,
        parent_tenancy_ocid=c.policy.parent_tenancy_ocid,
        administrator_id=c.grant["id"],
        authorization_revision=c.grant["authorization_revision"],
        baseline=c.baseline,
        targets=(c.repair_target,),
        target=ConfigurationOperationTarget(
            tenancy_ocid=c.target.tenancy_ocid, display_name=c.row["name"]
        ),
    )
    engine = Mock()
    engine.begin.side_effect = lambda: nullcontext(c.connection)
    worker = ConfigurationUpdateWorker(
        engine, c.policy.workspace_id, c.store.clock, c.loader, c.facade
    )
    c.operation["workspace_id"] = c.policy.workspace_id
    c.operation["effect_knowledge"] = "none"
    c.connection.execute.side_effect = None
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        None,
        c.grant,
        c.row,
    ]
    with (
        patch.object(worker, "_locked", return_value=c.operation),
        patch(
            "otm.configuration.rollout_worker.update_intent",
            return_value=SimpleNamespace(intent=intent, actor=c.actor.actor),
        ),
        patch("otm.configuration.rollout_worker.target_is_current", return_value=True),
        patch("otm.configuration.rollout_worker.published_baseline", return_value=c.baseline),
        patch(
            "otm.configuration.repairs.execute_repair",
            return_value=(c.objects, None, c.history[0][2].results),
            side_effect=ValueError("changed") if failed else None,
        ),
        patch("otm.configuration.repairs.record_repair_check") as seal,
    ):
        worker._target(c.operation["id"], c.row["id"])
    assert seal.call_count == (0 if failed else 1)


# Keep failed reservations distinct from active progress while retaining findings.
@pytest.mark.parametrize(
    "state,expected",
    [("queued", "checking"), ("running", "checking"), ("needs_attention", "drifted")],
)
def test_repair_reservation_status(repair_case, state, expected):
    from otm.configuration.drift_views import check_summary

    c = repair_case
    row = {**c.row, "operation_id": uuid4(), "reserved_operation_state": state}
    summary = check_summary(row, c.history, {}, c.policy, c.baseline, NOW)
    assert summary.state == expected and summary.confirmed_issue_count == 1
    assert not summary.can_check


# Restore exact authored values for each category, drift state and override profile.
@pytest.mark.parametrize("category", ["policy", "quota", "budget", "tags"])
@pytest.mark.parametrize("state", ["missing", "different"])
@pytest.mark.parametrize("overridden", [False, True], ids=["inherited", "overrides"])
def test_repair_write_matrix(repair_case, category, state, overridden):
    import json

    from repair_examples import BASELINE_PAYLOADS, CHANGED_PAYLOADS, OVERRIDE_PAYLOADS, OVERRIDES

    from otm.configuration.observation_contracts import ManagedObservation
    from otm.configuration.override_contracts import (
        OverrideValues,
        TenancyConfiguration,
        configuration_hash,
        effective_content,
    )
    from otm.providers.configuration import desired_objects

    c = repair_case
    values = OVERRIDES if overridden else OverrideValues()
    configuration = (
        TenancyConfiguration(
            **values.model_dump(),
            id=uuid4(),
            tenancy_id=c.row["id"],
            baseline_version_id=c.baseline.id,
            revision_number=1,
            previous_id=None,
            operation_id=uuid4(),
            created_by="unit-operator",
            created_at=NOW,
            effective_hash=configuration_hash(c.baseline, values),
        )
        if overridden
        else None
    )
    context = c.target.model_copy(
        update={
            "overrides": values,
            "configuration_id": configuration.id if configuration else None,
            "effective_hash": configuration_hash(c.baseline, values),
        }
    )
    authored = c.baseline.model_copy(update={"content": effective_content(c.baseline, values)})
    desired = desired_objects(context, authored)
    original = {key: item.model_dump(mode="json") for key, item in desired.items()}
    observed = (
        None
        if state == "missing"
        else desired[category].model_copy(
            update={
                "payload": json.dumps(CHANGED_PAYLOADS[category]),
                "payload_hash": canonical_hash(CHANGED_PAYLOADS[category]),
            }
        )
    )
    cloud = {
        **original,
        category: ManagedObservation(
            binding=desired[category],
            state="missing" if state == "missing" else "present",
            observed=observed,
            complete=True,
        ).model_dump(mode="json"),
    }
    before = json.dumps(cloud, sort_keys=True)
    row = {**c.row, "configuration_observation": cloud}
    target = c.repair_target.model_copy(
        update={
            "configuration": configuration,
            "source_configuration_id": context.configuration_id,
            "overrides": values,
            "repair_categories": (category,),
            "repair_bindings": context.bindings,
            "repair_context_hash": canonical_hash(context.model_dump(mode="json")),
            "repair_observation_hash": canonical_hash(cloud),
        }
    )
    with (
        patch("otm.configuration.repairs.capture_target", return_value=context),
        patch.object(c.facade, "apply", wraps=c.facade.apply) as apply,
    ):
        objects, failed, results = execute_repair(
            c.connection, c.policy.workspace_id, row, target, c.baseline, c.facade
        )
    assert failed is None and all(item.state == "matching" and item.complete for item in results)
    assert apply.call_count == 1 and apply.call_args.args[1].category == category
    expected = (OVERRIDE_PAYLOADS if overridden else BASELINE_PAYLOADS)[category]
    assert json.loads(objects[category]["payload"]) == expected
    assert {key: value for key, value in objects.items() if key != category} == {
        key: value for key, value in original.items() if key != category
    }
    assert json.dumps(cloud, sort_keys=True) == before
