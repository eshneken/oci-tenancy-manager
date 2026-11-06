"""Read-only identity records stay scoped and cannot imply current OCI access health."""

from contextlib import nullcontext
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_organization_fixtures import NOW
from test_sessions import session_case
from test_tenancy_workflow_units import principal, registry, service

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.storage.organization import OrganizationConflict
from otm.tenancies.http import workflow_router
from otm.tenancies.required_users import (
    RequiredUserRecord,
    RequiredUsersDirectory,
    required_user_records,
)

__all__ = ["session_case", "registry"]


# Build independently editable canonical records, without creating a provider or credential head.
def records(state="active"):
    child = dict(id=uuid4(), status=state, provider_mode="simulated")
    event = uuid4()
    domain = dict(
        id=uuid4(),
        logical_key="identity/domain",
        kind="identity_domain",
        ownership_mode="observed_reference",
        state="active",
        provider_ocid="ocid1.domain.oc1..otmsimdomain",
        source_evidence_event_id=event,
        generation=1,
    )
    users = [
        dict(
            id=uuid4(),
            logical_key="identity/user/" + purpose,
            kind="managed_user",
            ownership_mode="managed",
            state="active",
            identity_domain_binding_id=domain["id"],
            provider_ocid="ocid1.user.oc1..otmsim" + purpose,
            scim_resource_id=purpose + "-scim",
            user_name="otm-" + purpose,
            source_evidence_event_id=event,
            generation=1,
            created_at=NOW,
            updated_at=NOW,
            created_operation_id=uuid4(),
        )
        for purpose in ("automation", "recovery")
    ]
    return child, domain, users


# Record the exact SQL scope of this closed projection; no write query may be issued.
def project(child, rows):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = rows
    result = required_user_records(connection, "example-workspace", child)
    assert connection.execute.call_count == 1
    query = connection.execute.call_args.args[0]
    assert "example-workspace" in query.compile().params.values()
    assert child["id"] in query.compile().params.values()
    assert query.is_select
    return result


# Registration is independent per role and never produces a presence/permission/readiness success.
@pytest.mark.parametrize("count", [0, 1, 2])
def test_independent_recorded_and_historical_unbound_accounts(count):
    child, domain, users = records()
    result = project(child, [domain, *users[:count]])
    assert [r.purpose for r in result.users] == ["automation", "recovery"]
    assert [r.identity_state for r in result.users] == ["recorded"] * count + ["not_recorded"] * (
        2 - count
    )
    for record in result.users:
        assert set(record.model_dump()) == {"purpose", "identity_state", "identity", "presence"}
        if record.identity is not None:
            assert record.identity.domain_ocid == domain["provider_ocid"]
            assert record.identity.retired_at is None
            assert record.identity.scim_resource_id.endswith("-scim")


# Logical retirement retains exact identity/history, while pending registration never means ready.
@pytest.mark.parametrize(
    "status", ["pending", "active", "terminating", "terminated", "failed", "cancelled"]
)
def test_lifecycle_context_and_retained_identity(status):
    child, domain, users = records(status)
    if status == "terminated":
        for item in [domain, *users]:
            item["state"] = "retired"
    result = project(child, [domain, *users])
    assert result.tenancy_status == status
    assert all(
        r.identity_state == ("retired" if status == "terminated" else "recorded")
        for r in result.users
    )
    assert all(
        (r.identity.retired_at is not None) == (status == "terminated") for r in result.users
    )


# Broken persisted identity relations become an unavailable read, never an empty/healthy result.
@pytest.mark.parametrize(
    "fault",
    [
        "domain",
        "domain_kind",
        "domain_mode",
        "user_kind",
        "user_mode",
        "domain_id",
        "state",
        "state_mismatch",
        "event",
    ],
)
def test_inconsistent_records_fail_closed(fault):
    child, domain, users = records()
    rows = [domain, *users]
    if fault == "domain":
        rows.pop(0)
    elif fault.startswith("domain_"):
        if fault == "domain_id":
            users[0]["identity_domain_binding_id"] = uuid4()
        else:
            domain["kind" if fault == "domain_kind" else "ownership_mode"] = "wrong"
    elif fault.startswith("user_"):
        users[0]["kind" if fault == "user_kind" else "ownership_mode"] = "wrong"
    elif fault == "event":
        users[0]["source_evidence_event_id"] = uuid4()
    else:
        users[0]["state"] = "unknown" if fault == "state" else "retired"
    with pytest.raises(RuntimeError, match="REQUIRED_USER_RECORDS_UNAVAILABLE"):
        project(child, rows)


# Highest generation wins without combining an old identity with the newer subject's domain.
def test_latest_generation_is_preserved():
    child, domain, users = records()
    older = {**users[0], "user_name": "older-user", "generation": 0}
    result = project(child, [domain, *users, older])
    assert result.users[0].identity.user_name == users[0]["user_name"]


# The public record cannot omit a role, fabricate a missing identity or mislabel retirement.
def test_closed_record_contracts():
    child, domain, users = records()
    result = project(child, [domain, *users])
    with pytest.raises(ValueError, match="PURPOSES_REQUIRED"):
        RequiredUsersDirectory(**{**result.model_dump(), "users": tuple(reversed(result.users))})
    with pytest.raises(ValueError, match="RECORD_MISMATCH"):
        RequiredUserRecord(
            purpose="automation", identity_state="not_recorded", identity=result.users[0].identity
        )
    with pytest.raises(ValueError, match="RETIREMENT_MISMATCH"):
        RequiredUserRecord(
            purpose="automation", identity_state="retired", identity=result.users[0].identity
        )


# Resolve current principal scope before SQL; foreign and unknown children share one response.
def test_service_authority_and_unavailable_storage(registry):
    app = service(registry)
    app.store._principal.return_value = registry.workspace
    child, domain, users = records()
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    with patch("otm.tenancies.workflows.read_snapshot", return_value=nullcontext(connection)):
        with pytest.raises(OrganizationConflict, match="TENANCY_NOT_FOUND"):
            app.required_users(principal(), child["id"])
        connection.execute.return_value.mappings.return_value.one_or_none.return_value = child
        with patch(
            "otm.tenancies.required_users.required_user_records", return_value="scoped"
        ) as read:
            assert app.required_users(principal(), child["id"]) == "scoped"
            read.assert_called_once_with(connection, registry.workspace, child)
        with patch(
            "otm.tenancies.required_users.required_user_records", side_effect=ValueError("private")
        ):
            with pytest.raises(RuntimeError, match="^REQUIRED_USER_RECORDS_UNAVAILABLE$") as caught:
                app.required_users(principal(), child["id"])
            assert caught.value.__suppress_context__


# Real auth middleware protects reads; malformed targets and server failures remain safe.
def test_http_session_scope_and_no_mutation(session_case):
    boundary = Mock()
    child, _, _ = records()
    boundary.required_users.return_value = project(child, [])
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(workflow_router(boundary))
    path = "/api/tenancies/" + str(child["id"]) + "/required-users"
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(path).status_code == 401
        boundary.required_users.assert_not_called()
        response = client.get(path + "?workspace_id=foreign", headers=cookie(session_case))
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert boundary.required_users.call_args.args[1] == child["id"]
        assert (
            client.get(
                "/api/tenancies/not-a-uuid/required-users", headers=cookie(session_case)
            ).status_code
            == 422
        )
        boundary.required_users.side_effect = OrganizationConflict("TENANCY_NOT_FOUND")
        assert client.get(path, headers=cookie(session_case)).status_code == 404
        boundary.required_users.side_effect = RuntimeError("private credential details")
        response = client.get(path, headers=cookie(session_case))
        assert response.status_code == 503 and "private" not in response.text
        assert client.post(path, headers=cookie(session_case)).status_code in {403, 405}
