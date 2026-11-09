"""Automatic latest defaults, guarded admissions and frozen recipe evidence without OCI calls."""

import json
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_baseline_authoring import NOW, result, row, setup
from test_baseline_publication import published_row
from test_tenancy_workflow_units import command, database, person, principal, registry, service

from otm.configuration.service import (
    current_baseline,
    draft_view,
    published_baseline,
)
from otm.operations.contracts import IntentEventData
from otm.storage.organization import OrganizationConflict

__all__ = ["registry"]


# The loader uses explicit workspace+ID predicates and rejects incomplete or corrupt publications.
@pytest.mark.parametrize("variant", ["valid", "none", "draft", "corrupt"])
def test_published_lookup_and_latest_default(variant):
    c = setup()
    value = row() if variant == "draft" else published_row(row(), c.principal)
    if variant == "corrupt":
        value["content_hash"] = "0" * 64
    c.connection.execute.side_effect = [result(None if variant == "none" else value)]
    if variant == "none":
        assert current_baseline(c.connection, "synthetic") is None
        c.connection.execute.side_effect = [result(None)]
        with pytest.raises(OrganizationConflict):
            published_baseline(c.connection, "synthetic", value["id"])
    elif variant in {"draft", "corrupt"}:
        with pytest.raises((ValueError, RuntimeError)):
            current_baseline(c.connection, "synthetic")
    else:
        assert current_baseline(c.connection, "synthetic") == draft_view(value)
        c.connection.execute.side_effect = [result(value)]
        assert published_baseline(c.connection, "synthetic", value["id"]) == draft_view(value)
        assert set(c.connection.execute.call_args.args[0].compile().params.values()) >= {
            "synthetic",
            value["id"],
        }


# No default blocks only new create/import admissions before registry/audit/queue mutations.
@pytest.mark.parametrize("action", ["create_tenancy", "import_tenancy"])
def test_missing_baseline_blocks_new_admission(registry, action):
    app, connection = service(registry), database()
    employee = person(registry)
    fields = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimnew"}
        if action == "import_tenancy"
        else {"name": "newchild"}
    )
    with patch("otm.tenancies.workflows.current_baseline", return_value=None):
        with pytest.raises(OrganizationConflict, match="PUBLISHED_BASELINE_REQUIRED"):
            app._admit(
                connection,
                registry,
                command(registry, employee, action, **fields),
                employee,
                None,
                principal(),
                NOW,
            )
    connection.execute.assert_not_called()
    app.enqueuer.enqueue.assert_not_called()


# New admissions snapshot the server recipe; old intent JSON stays hash-readable with absent fields.
def test_admission_pin_and_legacy_intent(registry):
    app, connection, employee = service(registry), database(), person(registry)
    account = principal()
    baseline = draft_view(published_row(row(), account))
    connection.execute.return_value.scalar_one.return_value = employee.id
    connection.execute.return_value.mappings.return_value.one.return_value = dict(
        id=uuid4(), authorization_revision=uuid4(), identity_kind="local_recovery", email=None
    )
    with patch("otm.tenancies.workflows.current_baseline", return_value=baseline):
        app._admit(
            connection,
            registry,
            command(registry, employee, "create_tenancy", name="pinnedchild"),
            employee,
            None,
            account,
            NOW,
        )
    event = next(
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False) and call.args[0].table.name == "audit_event"
    )
    frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
    assert frozen.intent.baseline == baseline
    legacy = dict(event["data"])
    legacy["intent"] = {key: value for key, value in legacy["intent"].items() if key != "baseline"}
    legacy["intent"].pop("presence_connection_contract", None)
    legacy["intent"]["onboarding_version"] = 1
    assert IntentEventData.model_validate_json(json.dumps(legacy)).intent.baseline is None


# Pending registry bindings must match the frozen pin, including the explicit old unpinned format.
def test_worker_registry_pin_guard(registry):
    from test_tenancy_workflow_units import attach, intent

    from otm.providers.lifecycle import LifecycleBlocked
    from otm.tenancies.worker import OrganizationLifecycleWorker

    app, employee = service(registry), person(registry)
    key = uuid4()
    tenant, membership = attach(registry, employee, status="pending", operation_id=key)
    membership.update(status="pending", operation_id=key)
    registry.controls[employee.id]["pending_operation_id"] = key
    baseline = draft_view(published_row(row(), principal()))
    frozen = intent(
        registry,
        app,
        employee,
        pending_tenancy_id=tenant["id"],
        pending_association_id=membership["id"],
        baseline=baseline,
    )
    tenant["tenancy_ocid"] = frozen.target.tenancy_ocid
    worker = OrganizationLifecycleWorker(Mock(), registry.workspace, Mock(), Mock(), app.facade)
    with pytest.raises(LifecycleBlocked):
        worker._validate(registry, frozen, key)
    tenant["baseline_version_id"] = baseline.id
    worker._validate(registry, frozen, key)
    with pytest.raises(LifecycleBlocked):
        worker._validate(registry, frozen.model_copy(update={"baseline": None}), key)
