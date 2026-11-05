"""Readable scoped audit targets come from verified immutable intents and registered resources."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_configuration_updates import update_case

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.audit_directory import resource_context
from otm.tenancies.contracts import LifecycleTarget, OrganizationIntent

__all__ = ["update_case"]


# Represent one independent SQL mapping result per batched read, retaining the actual expressions.
def mappings(rows):
    return Mock(mappings=Mock(return_value=rows))


# Parent and per-child evidence produce friendly targets without raw payload leakage.
@pytest.mark.parametrize(
    "kind", ["operation_intent", "configuration_outcome", "organization_action"]
)
def test_scoped_resource_targets(update_case, kind):
    c = update_case
    intent = c.intent
    if kind == "organization_action":
        intent = OrganizationIntent(
            workspace_id=c.policy.workspace_id,
            policy_revision=c.policy.policy_revision,
            organization_id=c.policy.organization_id,
            parent_tenancy_ocid=c.policy.parent_tenancy_ocid,
            administrator_id=c.grant["id"],
            authorization_revision=c.grant["authorization_revision"],
            action="create_tenancy",
            target=LifecycleTarget(person_id=uuid4(), display_name="Example employee"),
            person_was_absent=False,
            person_was_manager=False,
            pending_tenancy_id=c.target.tenancy_id,
        )
    payload = IntentEventData(intent=intent, actor=c.actor.actor).model_dump(mode="json")
    operation = c.operation["id"]
    evidence = {
        "id": uuid4(),
        "operation_id": operation,
        "kind": kind,
        "data": {
            "contract_version": "configuration-update-1",
            "tenancy_id": str(c.target.tenancy_id),
            "baseline_id": str(c.baseline.id),
            "safe_code": "CONFIGURATION_VERIFIED",
        },
    }
    connection = Mock()
    connection.execute.side_effect = [
        mappings(
            [{"operation_id": operation, "data": payload, "data_hash": canonical_hash(payload)}]
        ),
        mappings(
            [
                {
                    "id": c.target.tenancy_id,
                    "name": "Example child",
                    "tenancy_ocid": c.target.tenancy_ocid,
                }
            ]
        ),
    ]
    resources = resource_context(connection, c.policy.workspace_id, [evidence])[evidence["id"]]
    assert resources[-1].name == "Example child" and resources[-1].kind == "tenancy"
    if kind == "organization_action":
        assert resources[0].name == "Example employee" and resources[0].kind == "person"
    for call in connection.execute.call_args_list:
        assert c.policy.workspace_id in call.args[0].compile().params.values()


# Missing context remains empty; corrupt hashes or cross-workspace evidence fail closed.
def test_missing_and_corrupt_resource_evidence(update_case):
    c = update_case
    connection = Mock()
    assert resource_context(connection, c.policy.workspace_id, [{"operation_id": None}]) == {}
    row = {"id": uuid4(), "operation_id": c.operation["id"], "kind": "operation_intent"}
    connection.execute.side_effect = [mappings([]), mappings([])]
    assert resource_context(connection, c.policy.workspace_id, [row]) == {}
    payload = c.operation["intent_data"]
    connection.execute.side_effect = [
        mappings([{"operation_id": row["operation_id"], "data": payload, "data_hash": "0" * 64}])
    ]
    with pytest.raises(ValueError, match="INVALID_AUDIT_EVIDENCE"):
        resource_context(connection, c.policy.workspace_id, [row])
    connection.execute.side_effect = [
        mappings(
            [
                {
                    "operation_id": row["operation_id"],
                    "data": payload,
                    "data_hash": canonical_hash(payload),
                }
            ]
        )
    ]
    with pytest.raises(ValueError, match="INVALID_AUDIT_SCOPE"):
        resource_context(connection, "different-workspace", [row])
