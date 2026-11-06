"""Simulated connections retain scope without assigning permissions or secrets."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from test_organization_fixtures import NOW

from otm.storage.user_presence_connections import capture_connection, retire_connection


# Keep intent provenance independent from database readbacks, including intentionally bad fixtures.
def scenario():
    op, event, domain, signer, child = (uuid4() for _ in range(5))
    intent = SimpleNamespace(
        workspace_id="connection-test",
        pending_tenancy_id=child,
        action="create_tenancy",
        onboarding_version=3,
        presence_connection_contract="simulated-user-presence-1",
    )
    rows = [
        dict(
            id=domain,
            logical_key="identity/domain",
            created_operation_id=op,
            source_evidence_event_id=event,
        ),
        dict(
            id=signer,
            logical_key="identity/user/automation",
            identity_domain_binding_id=domain,
            created_operation_id=op,
            source_evidence_event_id=event,
        ),
    ]
    connection = MagicMock()
    first, second = MagicMock(), MagicMock()
    first.mappings.return_value = rows
    second.mappings.return_value.all.return_value = []
    connection.execute.side_effect = [first, second, MagicMock()]
    return SimpleNamespace(**locals())


# The connection records canonical references only, and identical evidence replays the same ID.
def test_connection_insert_and_exact_replay():
    c = scenario()
    with patch("otm.storage.user_presence_connections.require_transaction"):
        identifier = capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW)
    facts = c.connection.execute.call_args.args[0].compile().params
    assert facts["id"] == identifier and facts["automation_binding_id"] == c.signer
    assert facts["domain_binding_id"] == c.domain and facts["revision"] == 1
    assert facts["provider_mode"] == "simulated" and len(facts) == 14
    assert not ({"password", "user_name", "provider_ocid", "credential_id"} & set(facts))
    c.second.mappings.return_value.all.return_value = [facts]
    c.connection.execute.side_effect = [c.first, c.second]
    with patch("otm.storage.user_presence_connections.require_transaction"):
        assert capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW) == identifier


# Legacy capture is a no-op; the marker cannot enable connections for another action or graph.
@pytest.mark.parametrize("kind", ["legacy", "version", "action"])
def test_marker_and_graph_guards(kind):
    c = scenario()
    if kind == "legacy":
        c.intent.presence_connection_contract = None
    elif kind == "version":
        c.intent.onboarding_version = 2
    else:
        c.intent.action = "delete_tenancy"
    with patch("otm.storage.user_presence_connections.require_transaction"):
        if kind == "legacy":
            assert capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW) is None
        else:
            with pytest.raises(ValueError, match="SOURCE_UNVERIFIED"):
                capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW)
    c.connection.execute.assert_not_called()


# Both exact references must originate from this capture, never a recovery or unrelated user.
@pytest.mark.parametrize("damage", ["missing", "domain", "operation", "event", "duplicate"])
def test_reference_guards(damage):
    c = scenario()
    if damage == "missing":
        c.rows.pop()
    elif damage == "domain":
        c.rows[1]["identity_domain_binding_id"] = uuid4()
    elif damage == "operation":
        c.rows[0]["created_operation_id"] = uuid4()
    elif damage == "event":
        c.rows[1]["source_evidence_event_id"] = uuid4()
    else:
        c.rows.append(c.rows[0])
    with patch("otm.storage.user_presence_connections.require_transaction"):
        with pytest.raises(ValueError, match="SOURCE_UNVERIFIED"):
            capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW)


# Conflicting or retired records are never replaced by redelivery or another capture.
@pytest.mark.parametrize("damage", ["state", "source", "multiple"])
def test_replay_conflict(damage):
    c = scenario()
    with patch("otm.storage.user_presence_connections.require_transaction"):
        capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW)
    facts = c.connection.execute.call_args.args[0].compile().params
    if damage == "state":
        facts["state"] = "retired"
    elif damage == "source":
        facts["source_evidence_event_id"] = uuid4()
    c.second.mappings.return_value.all.return_value = [facts] * (2 if damage == "multiple" else 1)
    c.connection.execute.side_effect = [c.first, c.second]
    with patch("otm.storage.user_presence_connections.require_transaction"):
        with pytest.raises(ValueError, match="CONFLICT"):
            capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW)


# Database details cannot leak through normalized connection-capture errors.
def test_database_failure_is_closed():
    c = scenario()
    c.connection.execute.side_effect = [
        c.first,
        c.second,
        IntegrityError("private", {}, Exception()),
    ]
    with patch("otm.storage.user_presence_connections.require_transaction"):
        with pytest.raises(ValueError, match="^PRESENCE_CONNECTION_CONFLICT$") as caught:
            capture_connection(c.connection, {"id": c.op}, c.intent, c.event, NOW)
    assert caught.value.__suppress_context__


# Retirement changes only lifecycle state and references, under the caller's existing transaction.
def test_retirement_is_scoped():
    c = scenario()
    c.connection.execute.side_effect = None
    with patch("otm.storage.user_presence_connections.require_transaction") as guard:
        retire_connection(c.connection, c.intent.workspace_id, c.child, c.op, NOW)
    guard.assert_called_once_with(c.connection)
    statement = c.connection.execute.call_args.args[0]
    values = statement.compile().params
    assert values["state"] == "retired" and values["retired_operation_id"] == c.op
    assert c.child in values.values() and c.intent.workspace_id in values.values()


# Obsolete assignment/credential bookkeeping is not required or accepted by the revised boundary.
def test_revised_contract_version_is_explicit():
    from pydantic import ValidationError
    from test_required_user_presence import case

    from otm.providers.required_user_contracts import InspectRequiredUser

    command = case().command.model_dump()
    assert command["contract_version"] == "required-user-presence-2"
    command["contract_version"] = "required-user-presence-1"
    with pytest.raises(ValidationError):
        InspectRequiredUser.model_validate(command)
