"""Financial refresh session, body limits and same-origin boundaries."""

from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_financial_values import NOW
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.auth.service import SessionFailure
from otm.financial.contracts import CostRefreshReceipt
from otm.financial.http import cost_router, guarded

__all__ = ["session_case"]


# Browser commands cannot select another workspace, inject endpoints or bypass authentication/CSRF.
def test_cost_http_boundaries(session_case):
    service = Mock()
    service.start.return_value = CostRefreshReceipt(
        operation_ids=(uuid4(),), accepted_count=1, joined_count=0, skipped_count=0, accepted_at=NOW
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(cost_router(service))
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        path = "/api/costs/refresh"
        body = {"client_request_key": str(uuid4())}
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
            {"endpoint": "https://foreign.test"},
            {"workspace_id": "other"},
            {"budget_ocid": "wrong"},
            {"tenancy_id": "bad"},
        ]:
            assert client.post(path, json={**body, **extra}, headers=headers).status_code == 400
        assert (
            client.post(
                path, content="x" * 4097, headers={**headers, "content-type": "application/json"}
            ).status_code
            == 413
        )
        assert client.post(path, json=body, headers=headers).status_code == 202
        assert service.start.call_count == 1
    import pytest

    with pytest.raises(SessionFailure):
        guarded(Mock(side_effect=SessionFailure(401, "AUTHENTICATION_REQUIRED")))
