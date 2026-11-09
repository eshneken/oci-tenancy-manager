"""The manual check command uses existing session, same-origin, size and closed-body guards."""

from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import ActionReceipt
from otm.tenancies.http import workflow_router
from otm.tenancies.presence_contracts import PresenceCheckRequest

__all__ = ["session_case"]


# An authenticated browser may select only the registered target URL and one request UUID.
def test_protected_manual_check_route(session_case):
    boundary = Mock()
    key, child, identifier = uuid4(), uuid4(), uuid4()
    boundary.presence_checks.start.return_value = ActionReceipt(
        operation_id=identifier,
        state="queued",
        provider_mode="simulated",
        accepted_at=session_case.clock(),
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(workflow_router(boundary))
    path = f"/api/tenancies/{child}/required-users/check"
    headers = {**cookie(session_case), "Origin": ORIGIN, "X-OTM-Request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert (
            client.post(
                path,
                headers={"Origin": ORIGIN, "X-OTM-Request": "1"},
                json={"client_request_key": str(key)},
            ).status_code
            == 401
        )
        assert (
            client.post(
                path, headers=cookie(session_case), json={"client_request_key": str(key)}
            ).status_code
            == 403
        )
        response = client.post(path, headers=headers, json={"client_request_key": str(key)})
        assert response.status_code == 202 and response.headers["cache-control"] == "no-store"
        args = boundary.presence_checks.start.call_args.args
        assert args[1] == child and args[2] == PresenceCheckRequest(client_request_key=key)
        for field in ("workspace_id", "connection_id", "results", "endpoint", "actor"):
            assert (
                client.post(
                    path, headers=headers, json={"client_request_key": str(key), field: "private"}
                ).status_code
                == 400
            )
        assert client.post(
            path,
            headers=headers,
            content='{"bad":"' + "x" * 5000 + '"}',
        ).status_code in {400, 413, 415}
        boundary.presence_checks.start.side_effect = OrganizationConflict("TENANCY_NOT_FOUND")
        assert (
            client.post(path, headers=headers, json={"client_request_key": str(key)}).status_code
            == 404
        )
        boundary.presence_checks.start.side_effect = RuntimeError("private credentials")
        response = client.post(path, headers=headers, json={"client_request_key": str(key)})
        assert response.status_code == 503 and "private" not in response.text
        boundary.presence_checks = None
        assert (
            client.post(path, headers=headers, json={"client_request_key": str(key)}).status_code
            == 409
        )
