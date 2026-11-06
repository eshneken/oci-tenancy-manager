"""Inventory summaries preserve exact evidence and a fixed, scoped four-query read budget."""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from test_required_user_presence import NOW
from test_user_presence_check_units import case

from otm.tenancies.presence_contracts import RequiredUsersSummary, UserPresenceView
from otm.tenancies.presence_summary import summaries, summarize


# Mixed outcomes retain each subject; only fresh complete positives can produce a green summary.
@pytest.mark.parametrize(
    "a,b,stale,expected",
    [
        ("present", "present", False, "present"),
        ("present", "missing", False, "missing"),
        ("missing", "unknown", False, "missing"),
        ("present", "unknown", False, "unavailable"),
        ("present", "present", True, "stale"),
        ("missing", "missing", True, "missing"),
        ("not_checked", "present", False, "not_checked"),
        ("unknown", "not_checked", False, "unavailable"),
    ],
)
def test_mixed_summary_precedence(a, b, stale, expected):
    views = {
        "automation": UserPresenceView(state=a, stale=stale, checked_at=NOW, operation_id=uuid4()),
        "recovery": UserPresenceView(state=b, checked_at=NOW, operation_id=uuid4()),
    }
    view = summarize(views, True)
    assert view.state == expected and view.checking
    assert view.automation == views["automation"] and view.recovery == views["recovery"]
    assert summarize({}).state == "not_checked"


# Real SQL statement construction is retained while independent rows isolate evidence failures.
def rows(value):
    result = MagicMock()
    result.mappings.return_value.__iter__.return_value = iter(value)
    result.mappings.return_value.all.return_value = value
    return result


# The same latest-evidence decoder handles list and detail; corrupt proof never falls back green.
@pytest.mark.parametrize(
    "mode",
    [
        "present",
        "pending",
        "stale",
        "changed",
        "corrupt",
        "missing_event",
        "bad_pending",
        "duplicate_connection",
        "unbound",
        "empty",
        "inactive",
        "provider",
    ],
)
def test_scoped_batch_projection(mode):
    c = case()
    latest = {**c.check, "data": c.payload, "data_hash": c.evidence.model_dump_json()}
    from otm.operations.contracts import canonical_hash

    latest["data_hash"] = canonical_hash(c.payload)
    snapshot = c.snapshot
    child = {**c.child, "workspace_id": c.row["workspace_id"]}
    pending = []
    if mode == "pending":
        pending = [{**c.row, "presence_tenancy_id": child["id"]}]
    if mode == "bad_pending":
        pending = [{**c.row, "presence_tenancy_id": child["id"], "intent_hash": "0" * 64}]
    if mode == "stale":
        c.clock.return_value += timedelta(hours=24)
    if mode == "changed":
        snapshot = snapshot.model_copy(update={"tenancy_revision": 9})
    if mode == "unbound":
        snapshot = None
    if mode == "provider":
        c.service.policy = None
        snapshot = None
    if mode == "inactive":
        child["status"] = "terminated"
    if mode == "corrupt":
        latest["data_hash"] = "0" * 64
    if mode == "missing_event":
        latest["data"] = None
    current = [{"tenancy_id": child["id"]}]
    if mode == "duplicate_connection":
        current *= 2
    c.connection.execute.side_effect = [
        rows(current),
        rows([]),
        rows([] if mode == "empty" else [latest]),
        rows(pending),
    ]
    with patch("otm.tenancies.presence_summary.bound_snapshot", return_value=snapshot):
        result = summaries(c.service, c.connection, c.row["workspace_id"], (child,))
    if mode == "inactive":
        assert result == {} and not c.connection.execute.called
        return
    view = result[child["id"]]
    expected = (
        "unavailable"
        if mode in {"corrupt", "missing_event", "bad_pending", "duplicate_connection"}
        else "stale"
        if mode == "stale"
        else "not_checked"
        if mode in {"changed", "unbound", "provider", "empty"}
        else "present"
    )
    assert view.state == expected and view.checking == (mode == "pending")
    assert c.connection.execute.call_count == 4
    for call in c.connection.execute.call_args_list:
        parameters = call.args[0].compile().params
        assert c.row["workspace_id"] in parameters.values()
        assert any(
            child["id"] in value
            for value in parameters.values()
            if isinstance(value, (list, tuple))
        )


# Page size changes row data, never the number of queries or the authorized ID predicate.
@pytest.mark.parametrize("count", [1, 10, 50])
def test_fixed_query_budget(count):
    c = case()
    children = tuple(
        {**c.child, "id": uuid4(), "workspace_id": c.row["workspace_id"]} for _ in range(count)
    )
    c.connection.execute.side_effect = [rows([]) for _ in range(4)]
    result = summaries(c.service, c.connection, c.row["workspace_id"], children)
    assert len(result) == count and c.connection.execute.call_count == 4
    assert all(v.state == "not_checked" for v in result.values())


# Undated positive labels are unavailable; foreign pages fail before any database read.
def test_undated_positive_and_foreign_page():
    assert summarize({"automation": UserPresenceView(state="present")}).state == "unavailable"
    c = case()
    with pytest.raises(ValueError, match="PRESENCE_SCOPE_INVALID"):
        summaries(
            c.service,
            c.connection,
            c.row["workspace_id"],
            ({**c.child, "workspace_id": "foreign"},),
        )
    c.connection.execute.assert_not_called()


# The public response model rejects unsupported positive labels independently from SQL acquisition.
@pytest.mark.parametrize("state", ["present", "missing"])
def test_summary_contract_requires_dated_positive_facts(state):
    with pytest.raises(ValueError, match="PRESENCE_SUMMARY_INVALID"):
        RequiredUsersSummary(state=state)


# Broken configured bindings are unavailable; only a genuinely absent connection is unchecked.
@pytest.mark.parametrize("damage", [None, "missing_user", "domain", "source", "legacy"])
def test_actual_bound_records_in_summary(damage):
    c = case()
    event, operation = uuid4(), uuid4()
    a, b = c.snapshot.subjects
    domain = dict(
        id=a.identity_domain_binding_id,
        logical_key="identity/domain",
        kind="identity_domain",
        ownership_mode="observed_reference",
        provider_ocid=a.domain_ocid,
        source_evidence_event_id=event,
        created_operation_id=operation,
    )
    identities = [
        domain,
        *(
            dict(
                id=t.subject_binding_id,
                logical_key="identity/user/" + t.purpose,
                kind="managed_user",
                ownership_mode="managed",
                identity_domain_binding_id=domain["id"],
                provider_ocid=t.provider_ocid,
                scim_resource_id=t.scim_resource_id,
                user_name=t.user_name,
                generation=t.binding_generation,
                source_evidence_event_id=event,
                created_operation_id=operation,
            )
            for t in (a, b)
        ),
    ]
    for identity in identities:
        identity["tenancy_id"] = c.child["id"]
    current = dict(
        id=c.snapshot.connection_id,
        tenancy_id=c.child["id"],
        domain_binding_id=domain["id"],
        automation_binding_id=a.subject_binding_id,
        revision=1,
        source_evidence_event_id=event,
        created_operation_id=operation,
    )
    if damage == "missing_user":
        identities.pop()
    if damage == "domain":
        identities[1]["identity_domain_binding_id"] = uuid4()
    if damage == "source":
        identities[2]["source_evidence_event_id"] = uuid4()
    latest = {**c.check, "data": c.payload, "data_hash": c.row["intent_hash"]}
    from otm.operations.contracts import canonical_hash

    latest["data_hash"] = canonical_hash(c.payload)
    c.connection.execute.side_effect = [
        rows([] if damage == "legacy" else [current]),
        rows(identities),
        rows([latest]),
        rows([]),
    ]
    child = {**c.child, "workspace_id": c.row["workspace_id"]}
    result = summaries(c.service, c.connection, c.row["workspace_id"], (child,))[child["id"]]
    assert result.state == (
        "present" if damage is None else "not_checked" if damage == "legacy" else "unavailable"
    )
