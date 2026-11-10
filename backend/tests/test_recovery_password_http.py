"""Password disclosure is an authenticated, same-origin, no-store exceptional response."""

from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.storage.organization import OrganizationConflict
from otm.tenancies.http import workflow_router
from otm.tenancies.recovery_password_contracts import RecoveryPasswordView

__all__ = ["session_case"]


# Neither direct API bodies nor caches can bypass the existing session and consent boundary.
def test_password_routes_are_private_and_closed(session_case):
    boundary = Mock()
    child = uuid4()
    boundary.recovery_passwords.view.return_value = RecoveryPasswordView(
        tenancy_id=child,
        tenancy_name="Example tenancy",
        state="ready",
        available=True,
        preview_hash="a" * 64,
    )
    boundary.recovery_passwords.disclose.return_value = {"password": "synthetic-response-only"}
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(workflow_router(boundary))
    path = f"/api/tenancies/{child}/administrator-access"
    command = dict(client_request_key=str(uuid4()), preview_hash="a" * 64, acknowledged=True)
    headers = {**cookie(session_case), "Origin": ORIGIN, "X-OTM-Request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(path).status_code == 401
        response = client.get(path, headers=cookie(session_case))
        assert response.status_code == 200 and "password" not in response.json()
        for actual in (headers, cookie(session_case), {"Origin": ORIGIN, "X-OTM-Request": "1"}):
            response = client.post(path + "/password", headers=actual, json=command)
            assert response.status_code == (
                200
                if actual is headers
                else 403
                if any(key.lower() == "cookie" for key in actual)
                else 401
            )
        response = client.post(path + "/password", headers=headers, json=command)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"
        for field in ("secret_reference", "version", "actor", "workspace_id", "target"):
            response = client.post(
                path + "/password", headers=headers, json={**command, field: "foreign"}
            )
            assert response.status_code == 400
            assert response.headers["cache-control"] == "no-store"
        for code, status in (
            ("RECOVERY_PASSWORD_UNAVAILABLE", 409),
            ("RECOVERY_PASSWORD_READ_UNAVAILABLE", 503),
        ):
            boundary.recovery_passwords.disclose.side_effect = OrganizationConflict(code)
            response = client.post(path + "/password", headers=headers, json=command)
            assert response.status_code == status
            assert response.headers["cache-control"] == "no-store"
        boundary.recovery_passwords = None
        assert client.get(path, headers=cookie(session_case)).status_code == 409
