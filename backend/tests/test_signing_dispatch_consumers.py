"""Consumer regressions ensure denied managed signing authority never reaches provider effects."""

from contextlib import nullcontext
from itertools import chain, repeat
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_baseline_authoring import NOW, result
from test_configuration_drift import drift_case
from test_configuration_updates import update_case
from test_financial_units import cost_case
from test_financial_values import NOW as COST_NOW
from test_tenancy_workflow_units import (
    attach,
    command,
    database,
    intent,
    person,
    principal,
    registry,
    service,
)

from otm.configuration.rollout_worker import ConfigurationUpdateWorker
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.tenancies.worker import OrganizationLifecycleWorker

__all__ = ["update_case", "drift_case", "cost_case", "registry"]


# Both configuration workers must consult the composed signer guard before any provider access.
@pytest.mark.parametrize("kind", ["check", "update"])
def test_configuration_dispatch_denial_never_calls_provider(request, kind):
    c = request.getfixturevalue("drift_case" if kind == "check" else "update_case")
    denied = Mock(return_value=False)
    c.facade.observe = Mock(wraps=c.facade.observe)
    c.facade.read = Mock(wraps=c.facade.read)
    c.facade.apply = Mock(wraps=c.facade.apply)
    if kind == "check":
        worker = c.worker
        worker.signing_dispatch = denied
        connection = Mock()
        connection.scalar.return_value = None
        connection.execute.return_value.mappings.return_value.one.return_value = c.row
        connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.grant
        worker.engine.begin.return_value = nullcontext(connection)
        with (
            patch.object(worker, "_locked", return_value=c.operation),
            patch("otm.configuration.drift_worker.expected_objects", return_value=c.desired),
            patch("otm.configuration.drift_worker.save_check") as save,
        ):
            worker._target(c.operation["id"], c.target.tenancy_id)
        assert save.call_args.args[4] == "unavailable"
        assert all(not item.complete for item in save.call_args.args[3])
        assert all(item.safe_code == "PROVIDER_UNAVAILABLE" for item in save.call_args.args[3])
    else:
        connection = c.connection
        registered = {
            **c.row,
            "revision": c.target.revision + 1,
            "operation_id": c.operation["id"],
            "baseline_version_id": c.baseline.id,
        }
        connection.execute.side_effect = chain(
            [result(None), result(c.grant), result(registered)], repeat(Mock(rowcount=1))
        )
        worker = ConfigurationUpdateWorker(
            Mock(begin=Mock(return_value=nullcontext(connection))),
            c.policy.workspace_id,
            Mock(return_value=NOW),
            c.loader,
            c.facade,
            signing_dispatch=denied,
        )
        with (
            patch.object(worker, "_locked", return_value=c.operation),
            patch("otm.configuration.rollout_worker.published_baseline", return_value=c.baseline),
            patch("otm.configuration.rollout_worker.save_target_result") as save,
        ):
            worker._target(c.operation["id"], c.target.tenancy_id)
        assert save.call_args.kwargs["code"] == "PROVIDER_UNAVAILABLE"
    denied.assert_called_once_with(connection, c.policy.workspace_id, c.target.tenancy_id, NOW)
    c.facade.observe.assert_not_called()
    c.facade.read.assert_not_called()
    c.facade.apply.assert_not_called()


# Exercise real financial prepare/problem dispatch wiring, not a fabricated denied prepare result.
def test_cost_dispatch_denial_never_reads_budget(cost_case):
    c = cost_case
    denied = Mock(return_value=False)
    c.worker.signing_dispatch = denied
    c.facade.read_managed_budget = Mock(wraps=c.facade.read_managed_budget)
    c.connection.scalars.return_value = [c.collection["id"]]
    c.connection.execute.return_value.mappings.return_value.one.return_value = c.collection
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        c.row,
        c.grant,
    ]
    with (
        patch.object(c.worker, "_locked", return_value=c.operation),
        patch.object(c.worker, "_finish") as finish,
        patch.object(c.worker, "_progress"),
    ):
        c.worker.run(c.operation["id"])
    denied.assert_called_once_with(c.connection, c.policy.workspace_id, c.row["id"], COST_NOW)
    c.facade.read_managed_budget.assert_not_called()
    assert finish.call_args.args[-2:] == (None, "COST_CONTEXT_UNAVAILABLE")


# An otherwise valid existing-child deletion is held when managed signing authority is denied.
def test_lifecycle_dispatch_denial_retains_registered_child(registry):
    state, employee = registry, person(registry)
    app, connection, identifier = service(state), database(), uuid4()
    child, _ = attach(state, employee)
    plan = app._plan(
        state,
        command(state, employee, "delete_tenancy", tenancy_id=child["id"]),
        employee,
    )
    frozen = intent(state, app, employee, action="delete_tenancy", associations=plan)
    actor = principal().actor
    payload = IntentEventData(intent=frozen, actor=actor).model_dump(mode="json")
    row = dict(
        id=identifier,
        workspace_id=state.workspace,
        responsible_actor_subject=actor.key,
        kind="organization_action",
        state="queued",
        current_intent_event_id=uuid4(),
        current_intent_revision=1,
        initiating_actor_subject=actor.key,
        revision=1,
    )
    header, operation_row, event_row, grant_row = [database() for _ in range(4)]
    header.one_or_none.return_value = {"id": state.workspace}
    operation_row.one_or_none.return_value = row
    event_row.one.return_value = {"data": payload, "data_hash": canonical_hash(payload)}
    grant_row.one_or_none.return_value = dict(
        status="active",
        authorization_revision=frozen.authorization_revision,
        issuer=actor.issuer,
        subject=actor.subject,
    )
    connection.execute.return_value.scalar_one_or_none.return_value = uuid4()
    connection.execute.return_value.mappings.side_effect = [
        header,
        operation_row,
        event_row,
        grant_row,
    ]
    state.controls[employee.id]["pending_operation_id"] = identifier
    child["operation_id"] = identifier
    denied = Mock(return_value=False)
    app.facade.apply = Mock(wraps=app.facade.apply)
    worker = OrganizationLifecycleWorker(
        Mock(begin=Mock(return_value=nullcontext(connection))),
        state.workspace,
        Mock(return_value=NOW),
        Mock(return_value=SimpleNamespace(execution_paused=False, policy=app.policy)),
        app.facade,
        signing_dispatch=denied,
    )
    with (
        patch("otm.tenancies.worker.require_transaction"),
        patch("otm.tenancies.worker.registry_state", return_value=state),
        patch.object(worker, "_publish") as publish,
    ):
        worker._run(identifier)
    denied.assert_called_once_with(connection, state.workspace, child["id"], NOW)
    app.facade.apply.assert_not_called()
    publish.assert_not_called()
    outcomes = [
        call.args[0].compile().params["data"]
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False) and call.args[0].table.name == "audit_event"
    ]
    assert len(outcomes) == 1 and outcomes[0]["safe_code"] == "LIFECYCLE_UNAVAILABLE"
    assert child["status"] == "active" and state.associations(person=employee.id)
