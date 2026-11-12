"""Scoped fleet read admission, independent failures and compact authorized progress."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.auth.service import SessionFailure
from otm.financial.service import CostConflict
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.http import workflow_router
from otm.tenancies.refresh import refresh_fleet, refresh_status
from otm.tenancies.refresh_contracts import FleetRefreshRequest, FleetRefreshStatusRequest

__all__ = ["session_case"]


# Build minimal registered rows and explicit transaction-result mocks, never provider fixtures.
def setup_case(rows=None):
    child = uuid4()
    policy = SimpleNamespace(
        organization_id="test-org", parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent"
    )
    row = dict(
        id=child,
        provider_mode="simulated",
        organization_id="test-org",
        parent_tenancy_ocid=policy.parent_tenancy_ocid,
        tenancy_ocid="ocid1.tenancy.oc1..otmsimchild",
    )
    connection = Mock()
    connection.execute.return_value.mappings.return_value.all.return_value = (
        [row] if rows is None else rows
    )
    store = Mock()
    store._principal.return_value = "test-workspace"
    flow = SimpleNamespace(
        store=store,
        policy=policy,
        cost_collections=Mock(),
        presence_checks=Mock(),
        configuration_checks=Mock(),
    )
    cost_id, user_id, config_id = uuid4(), uuid4(), uuid4()
    flow.cost_collections.start.return_value = SimpleNamespace(
        operation_ids=(cost_id,), skipped_count=0
    )
    flow.presence_checks.start.return_value = SimpleNamespace(operation_id=user_id)
    flow.configuration_checks.start.return_value = SimpleNamespace(operation_id=config_id)
    return flow, connection, row


# Batch keys are category/child namespaced, current workspace scoped, and reusable on retries.
def test_fleet_read_categories_and_repeat_keys():
    flow, connection, row = setup_case()
    command = FleetRefreshRequest(client_request_key=uuid4())
    with patch("otm.tenancies.refresh.read_snapshot", return_value=nullcontext(connection)):
        first = refresh_fleet(flow, Mock(), command)
        again = refresh_fleet(flow, Mock(), command)
    assert first == again and first.tenancy_count == 1
    keys = [
        service.start.call_args.args[-1].client_request_key
        for service in (flow.cost_collections, flow.presence_checks, flow.configuration_checks)
    ]
    assert len(set(keys)) == 3
    assert flow.presence_checks.start.call_args.kwargs == {"join_pending": True}
    assert flow.configuration_checks.start.call_args.kwargs == {"join_pending": True}
    assert flow.presence_checks.start.call_args.args[1] == row["id"]
    for service in (flow.cost_collections, flow.presence_checks, flow.configuration_checks):
        assert service.start.call_args_list[0].args[-1] == service.start.call_args_list[1].args[-1]
    compiled = str(connection.execute.call_args.args[0])
    assert "workspace_id" in compiled and "status" in compiled


# Busy/unconfigured checks and failed admission stay separate and never reflect exception text.
@pytest.mark.parametrize("failure", [OrganizationConflict, CostConflict, RuntimeError])
def test_partial_failures_are_independent_and_redacted(failure):
    flow, connection, _ = setup_case()
    flow.cost_collections.start.side_effect = failure("SENSITIVE_INTERNAL_CONTENT")
    flow.presence_checks = None
    with patch("otm.tenancies.refresh.read_snapshot", return_value=nullcontext(connection)):
        result = refresh_fleet(flow, Mock(), FleetRefreshRequest(client_request_key=uuid4()))
    assert result.categories[0].failed_count == (failure is RuntimeError)
    assert result.categories[0].skipped_count == (failure is not RuntimeError)
    assert result.categories[1].skipped_count == 1
    assert len(result.categories[2].operation_ids) == 1
    assert "SENSITIVE_INTERNAL_CONTENT" not in result.model_dump_json()


# Lost authorization and conflicting command identities stop the request, preserving prior jobs.
@pytest.mark.parametrize(
    "failure", [SessionFailure(401, "AUTHENTICATION_REQUIRED"), RequestConflict("collision")]
)
def test_authorization_and_identity_failure_propagate(failure):
    flow, connection, _ = setup_case()
    flow.cost_collections.start.side_effect = failure
    with (
        patch("otm.tenancies.refresh.read_snapshot", return_value=nullcontext(connection)),
        pytest.raises(type(failure)),
    ):
        refresh_fleet(flow, Mock(), FleetRefreshRequest(client_request_key=uuid4()))
    flow.presence_checks.start.assert_not_called()


# Parents and mismatched registry context are excluded before any category admission.
@pytest.mark.parametrize(
    "damage", ["parent", "organization", "mode", "parent_scope", "empty", "limit"]
)
def test_fleet_scope_and_empty_limits(damage):
    flow, connection, row = setup_case()
    if damage == "parent":
        row["tenancy_ocid"] = flow.policy.parent_tenancy_ocid
    elif damage == "organization":
        row["organization_id"] = "foreign"
    elif damage == "mode":
        row["provider_mode"] = "unavailable"
    elif damage == "parent_scope":
        row["parent_tenancy_ocid"] = "foreign"
    rows = [] if damage == "empty" else [row] * (1001 if damage == "limit" else 1)
    connection.execute.return_value.mappings.return_value.all.return_value = rows
    with patch("otm.tenancies.refresh.read_snapshot", return_value=nullcontext(connection)):
        if damage == "limit":
            with pytest.raises(OrganizationConflict, match="FLEET_REFRESH_TOO_LARGE"):
                refresh_fleet(flow, Mock(), FleetRefreshRequest(client_request_key=uuid4()))
        else:
            assert (
                refresh_fleet(
                    flow, Mock(), FleetRefreshRequest(client_request_key=uuid4())
                ).tenancy_count
                == 0
            )
    flow.cost_collections.start.assert_not_called()


# Compact polling reports only known scoped read kinds and never invents success for missing IDs.
def test_progress_projection_deduplicates_and_fails_closed():
    flow, connection, _ = setup_case()
    ids = [uuid4() for _ in range(7)]
    connection.execute.return_value.mappings.return_value.all.return_value = [
        dict(id=key, state=state)
        for key, state in zip(
            ids,
            ["queued", "running", "waiting", "succeeded", "needs_attention", "cancelled"],
            strict=False,
        )
    ]
    with patch("otm.tenancies.refresh.read_snapshot", return_value=nullcontext(connection)):
        result = refresh_status(
            flow, Mock(), FleetRefreshStatusRequest(operation_ids=(*ids, ids[0]))
        )
    assert [job.state for job in result.jobs] == [
        "pending",
        "pending",
        "pending",
        "finished",
        "failed",
        "failed",
        "unavailable",
    ]
    query = connection.execute.call_args.args[0].compile().params
    assert "test-workspace" in query.values()
    assert ["cost_collection", "required_user_check", "configuration_check"] in query.values()


# Both read-command routes retain real session/CSRF protection and closed bounded JSON shapes.
def test_fleet_http_security_and_validation(session_case):
    flow, connection, _ = setup_case([])
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(workflow_router(flow))
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    body = {"client_request_key": str(uuid4())}
    with TestClient(app, base_url=ORIGIN) as client:
        path = "/api/tenancies/refresh"
        assert client.post(path, json=body).status_code == 403
        assert (
            client.post(
                path, json=body, headers={"origin": ORIGIN, "x-otm-request": "1"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                path, json=body, headers={**headers, "origin": "https://foreign.test"}
            ).status_code
            == 403
        )
        for extra in [
            {"workspace_id": "foreign"},
            {"tenancy_ids": []},
            {"client_request_key": "bad"},
            {"endpoint": "https://foreign.test"},
        ]:
            assert client.post(path, json={**body, **extra}, headers=headers).status_code == 400
        assert (
            client.post(
                path, content="x" * 4097, headers={**headers, "content-type": "application/json"}
            ).status_code
            == 413
        )
        with patch("otm.tenancies.refresh.read_snapshot", return_value=nullcontext(connection)):
            assert client.post(path, json=body, headers=headers).status_code == 202
            status = client.post(
                path + "/status", json={"operation_ids": [str(uuid4())]}, headers=headers
            )
            assert status.status_code == 200 and status.json()["jobs"][0]["state"] == "unavailable"
        assert (
            client.post(path + "/status", json={"operation_ids": []}, headers=headers).status_code
            == 400
        )
        assert (
            client.post(
                path + "/status",
                content="x" * 131073,
                headers={**headers, "content-type": "application/json"},
            ).status_code
            == 413
        )
