"""Identity mappings require fresh closed evidence, stable replay and no ambiguous adoption."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from test_onboarding import case, registry
from test_organization_fixtures import NOW

from otm.operations.contracts import canonical_hash
from otm.storage.managed_bindings import capture_bindings, retire_bindings
from otm.tenancies.onboarding_contracts import OnboardingEvidence

__all__ = ["registry"]


# Build provider facts and editable SQL read results; real transaction guards have PostgreSQL tests.
def scenario(state):
    app, intent, row, _ = case(state)
    intent = intent.model_copy(update={"onboarding_version": 3})
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    users = app.facade.capture_onboarding_users(intent, discovery.model_dump(mode="json"))
    event_id = uuid4()
    data = OnboardingEvidence(
        step="capture_required_users",
        outcome="verified",
        safe_code="ONBOARDING_VERIFIED",
        required_users=users,
    ).model_dump(mode="json")
    event = dict(data=data, data_hash=canonical_hash(data), at=NOW)
    child = dict(
        id=intent.pending_tenancy_id,
        tenancy_ocid=users.tenancy_ocid,
        parent_tenancy_ocid=users.parent_tenancy_ocid,
        organization_id=users.organization_id,
        status="pending",
        operation_id=row["id"],
    )
    return SimpleNamespace(
        app=app, intent=intent, row=row, users=users, event_id=event_id, event=event, child=child
    )


# Configure four independent SQL reads without implying that IDs alone establish authority.
def connection_for(c, existing=()):
    results = [MagicMock() for _ in range(4)]
    results[0].mappings.return_value.one_or_none.return_value = c.event
    results[1].scalar_one_or_none.return_value = c.event_id
    results[2].mappings.return_value.one_or_none.return_value = c.child
    results[3].mappings.return_value = existing
    connection = MagicMock()
    connection.execute.side_effect = results + [MagicMock() for _ in range(3)]
    return connection


# New capture stores one observed domain and two distinct managed users in one nested transaction.
def test_three_bindings_and_exact_idempotent_replay(registry):
    c = scenario(registry)
    connection = connection_for(c)
    with patch("otm.storage.managed_bindings.require_transaction"):
        identifiers = capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW)
    rows = [call.args[0].compile().params for call in connection.execute.call_args_list[4:]]
    assert len(set(identifiers)) == len(rows) == 3
    assert rows[0]["ownership_mode"] == "observed_reference"
    assert rows[0]["scim_resource_id"] is None
    assert all(row["identity_domain_binding_id"] == identifiers[0] for row in rows[1:])
    assert all(row["generation"] == 1 and row["state"] == "active" for row in rows)
    connection = connection_for(c, rows)
    with patch("otm.storage.managed_bindings.require_transaction"):
        assert (
            capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW) == identifiers
        )
    assert connection.execute.call_count == 4


# Hash, accepted scope, verified step, lifecycle and historical version independently gate writes.
@pytest.mark.parametrize(
    "fault",
    [
        "event",
        "step",
        "child",
        "hash",
        "workspace",
        "tenancy",
        "parent",
        "organization",
        "intent_workspace",
        "intent_tenancy",
        "intent_parent",
        "intent_organization",
        "time",
        "status",
        "operation",
        "version",
        "action",
        "evidence",
    ],
)
def test_invalid_source_never_inserts(registry, fault):
    c = scenario(registry)
    if fault in {"event", "child"}:
        setattr(c, fault, None)
    elif fault == "hash":
        c.event["data_hash"] = "0" * 64
    elif fault == "workspace":
        c.row["workspace_id"] = "foreign-workspace"
    elif fault in {"tenancy", "parent", "organization", "status", "operation"}:
        field = {
            "tenancy": "tenancy_ocid",
            "parent": "parent_tenancy_ocid",
            "organization": "organization_id",
            "status": "status",
            "operation": "operation_id",
        }[fault]
        c.child[field] = "foreign"
    elif fault.startswith("intent_"):
        field = fault.removeprefix("intent_")
        if field == "tenancy":
            c.intent = c.intent.model_copy(
                update={
                    "target": c.intent.target.model_copy(
                        update={"tenancy_ocid": "ocid1.tenancy.oc1..otmsimforeign"}
                    )
                }
            )
        else:
            c.intent = c.intent.model_copy(
                update={
                    {
                        "workspace": "workspace_id",
                        "parent": "parent_tenancy_ocid",
                        "organization": "organization_id",
                    }[field]: "foreign"
                }
            )
    elif fault == "time":
        c.event["at"] = None
    elif fault == "version":
        c.intent = c.intent.model_copy(update={"onboarding_version": 2})
    elif fault == "action":
        c.intent = c.intent.model_copy(update={"action": "delete_tenancy"})
    elif fault == "evidence":
        c.event["data"]["required_users"]["recovery"]["user_name"] = "different"
        c.event["data_hash"] = canonical_hash(c.event["data"])
    connection = connection_for(c)
    if fault == "step":
        results = list(connection.execute.side_effect)
        results[1].scalar_one_or_none.return_value = None
        connection.execute.side_effect = results
    with patch("otm.storage.managed_bindings.require_transaction"):
        with pytest.raises(ValueError, match="MANAGED_BINDING_SOURCE_UNVERIFIED"):
            capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW)
    assert connection.execute.call_count <= 4


# Existing different or partial mappings are conflicts rather than replaceable defaults.
@pytest.mark.parametrize("fault", ["partial", "name", "state", "domain", "source", "generation"])
def test_conflicting_bindings_are_never_overwritten(registry, fault):
    c = scenario(registry)
    connection = connection_for(c)
    with patch("otm.storage.managed_bindings.require_transaction"):
        capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW)
    rows = [call.args[0].compile().params for call in connection.execute.call_args_list[4:]]
    if fault == "partial":
        rows.pop()
    else:
        field = {
            "name": "user_name",
            "state": "state",
            "domain": "identity_domain_binding_id",
            "source": "source_evidence_event_id",
            "generation": "generation",
        }[fault]
        rows[1][field] = "changed"
    connection = connection_for(c, rows)
    with patch("otm.storage.managed_bindings.require_transaction"):
        with pytest.raises(ValueError, match="MANAGED_BINDING_CONFLICT"):
            capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW)
    assert connection.execute.call_count == 4


# Database faults leave the savepoint and expose only a closed code, never raw SQL/provider data.
def test_insert_fault_normalization_and_retirement_scope(registry):
    c = scenario(registry)
    connection = connection_for(c)
    calls = list(connection.execute.side_effect)
    calls[5] = IntegrityError("private", {}, Exception("private"))
    connection.execute.side_effect = calls
    with patch("otm.storage.managed_bindings.require_transaction"):
        with pytest.raises(ValueError, match="^MANAGED_BINDING_CONFLICT$") as caught:
            capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW)
    assert caught.value.__suppress_context__
    assert connection.begin_nested.return_value.__exit__.called
    connection = MagicMock()
    with (
        patch("otm.storage.managed_bindings.require_transaction"),
        patch("otm.storage.user_presence_connections.require_transaction"),
    ):
        retire_bindings(connection, c.intent.workspace_id, c.child["id"], c.row["id"], NOW)
    statement = connection.execute.call_args.args[0]
    assert statement.compile().params["state"] == "retired"
    assert "workspace_id" in str(statement) and "tenancy_id" in str(statement)


# JSONB list encoding must retain normalized policy tuples without blocking valid setup capture.
def test_policy_capture_jsonb_round_trip(registry):
    from otm.providers.recovery_console_simulator import configured_console_capture
    from otm.recovery_console import parse_release_cidrs

    c = scenario(registry)
    capture = configured_console_capture(
        c.users.domain_ocid,
        c.users.recovery.scim_resource_id,
        "binding-round-trip",
        parse_release_cidrs("198.51.100.0/24,2001:db8::/32"),
    )
    c.users = c.users.model_copy(update={"recovery_console": capture})
    data = OnboardingEvidence(
        step="capture_required_users",
        outcome="verified",
        safe_code="ONBOARDING_VERIFIED",
        required_users=c.users,
    ).model_dump(mode="json")
    c.event.update(data=data, data_hash=canonical_hash(data))
    assert isinstance(data["required_users"]["recovery_console"]["facts"]["rules"], list)
    connection = connection_for(c)
    with patch("otm.storage.managed_bindings.require_transaction"):
        assert len(capture_bindings(connection, c.row, c.intent, c.users, c.event_id, NOW)) == 3
