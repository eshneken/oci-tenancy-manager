"""Self-claim commands retain real session/CSRF enforcement and bounded closed input."""

from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from test_admission_service import NOW
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.tenancies.contracts import ActionReceipt
from otm.tenancies.http import workflow_router

__all__ = ["session_case"]


# Neither an assignee/actor claim nor a foreign-origin request can bypass explicit current self-
# claim.
def test_takeover_http_guards(session_case):
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    service = Mock()
    app.include_router(workflow_router(service))
    identifier = uuid4()
    path = f"/api/operations/{identifier}/responsibility"
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    body = {"client_request_key": str(uuid4()), "expected_revision": 1}
    receipt = ActionReceipt(
        operation_id=identifier, state="waiting", provider_mode="simulated", accepted_at=NOW
    )
    with (
        patch("otm.operations.responsibility.take_responsibility", return_value=receipt) as take,
        TestClient(app, base_url=ORIGIN) as client,
    ):
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
        assert (
            client.post(
                path, json={**body, "administrator_id": str(uuid4())}, headers=headers
            ).status_code
            == 400
        )
        assert (
            client.post(path, json={**body, "expected_revision": 0}, headers=headers).status_code
            == 400
        )
        assert (
            client.post(path, json={**body, "expected_revision": "1"}, headers=headers).status_code
            == 400
        )
        assert (
            client.post(
                path, content="bad", headers={**headers, "content-type": "application/json"}
            ).status_code
            == 400
        )
        assert (
            client.post(
                path, content="x" * 4097, headers={**headers, "content-type": "application/json"}
            ).status_code
            == 413
        )
        take.assert_not_called()
        assert client.post(path, json=body, headers=headers).status_code == 200
        assert take.call_args.args[2] == identifier
        assert (
            take.call_args.args[1].actor.key
            == session_case.service.authenticate(session_case.handle).actor.key
        )
