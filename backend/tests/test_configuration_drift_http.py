"""Read checks preserve the application's real session and same-origin admission boundary."""

from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_configuration_drift import NOW, drift_case, update_case
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.configuration.drift_contracts import ConfigurationDriftQuery
from otm.configuration.drift_http import drift_router
from otm.configuration.drift_views import check_summary, drift_directory
from otm.tenancies.contracts import ActionReceipt

__all__ = ["session_case", "drift_case", "update_case"]


# Missing auth, foreign Origin, extra privilege fields, oversized bodies and malformed scope
# fail closed.
def test_http_boundaries(session_case, drift_case):
    c = drift_case
    service = Mock()
    view = check_summary(c.row, (), {}, c.policy, c.baseline, NOW)
    service.directory.return_value = drift_directory((view,), ConfigurationDriftQuery(tab="checks"))
    service.detail.return_value = view
    service.start.return_value = ActionReceipt(
        operation_id=uuid4(), state="queued", provider_mode="simulated", accepted_at=NOW
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(drift_router(service))
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/configuration/drift").status_code == 401
        assert (
            client.get(
                "/api/configuration/drift?tab=checks&page=1&page_size=10&sort=name&direction=asc&state=all",
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/configuration/drift/" + str(c.target.tenancy_id), headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/configuration/drift/not-a-uuid", headers=headers).status_code == 422
        body = {"client_request_key": str(uuid4())}
        path = "/api/configuration/checks"
        assert (
            client.post(
                path, json=body, headers={**headers, "origin": "https://foreign.test"}
            ).status_code
            == 403
        )
        assert (
            client.post(path, json={**body, "workspace_id": "foreign"}, headers=headers).status_code
            == 400
        )
        assert (
            client.post(
                path, content="x" * 4097, headers={**headers, "content-type": "application/json"}
            ).status_code
            == 413
        )
        assert client.post(path, json=body, headers=headers).status_code == 202
        service.start.return_value = service.start.return_value.model_copy(
            update={"state": "succeeded"}
        )
        assert client.post(path, json=body, headers=headers).status_code == 200
