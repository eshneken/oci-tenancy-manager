"""Signing maintenance requests retain authenticated same-origin, closed-body and consent guards."""

from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from test_admission_service import NOW
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import ActionReceipt
from otm.tenancies.http import workflow_router
from otm.tenancies.signing_key_contracts import SigningKeyView

__all__ = ["session_case"]


# Server target selection, CSRF and schema checks cannot be bypassed through a direct API request.
def test_private_bounded_signing_routes(session_case):
    boundary = Mock()
    child = uuid4()
    operation = uuid4()
    boundary.signing_key_rotations.view.return_value = SigningKeyView(
        tenancy_id=child,
        tenancy_name="Synthetic child",
        state="scheduled",
        available=True,
        preview_hash="a" * 64,
    )
    boundary.signing_key_rotations.request.return_value = ActionReceipt(
        operation_id=operation, state="queued", provider_mode="simulated", accepted_at=NOW
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(workflow_router(boundary))
    path = f"/api/tenancies/{child}/signing-key-rotation"
    command = dict(client_request_key=str(uuid4()), preview_hash="a" * 64, acknowledged=True)
    headers = {**cookie(session_case), "Origin": ORIGIN, "X-OTM-Request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(path).status_code == 401
        response = client.get(path, headers=cookie(session_case))
        assert response.status_code == 200
        assert "secret_reference" not in response.text
        assert client.post(path, headers=cookie(session_case), json=command).status_code == 403
        client.cookies.clear()
        assert (
            client.post(
                path, headers={"Origin": ORIGIN, "X-OTM-Request": "1"}, json=command
            ).status_code
            == 401
        )
        response = client.post(path, headers=headers, json=command)
        assert response.status_code == 202 and response.json()["operation_id"] == str(operation)
        for key in ["target", "actor", "workspace_id", "secret_version", "fingerprint"]:
            assert (
                client.post(path, headers=headers, json={**command, key: "foreign"}).status_code
                == 400
            )
        assert (
            client.post(
                path,
                headers={**headers, "Content-Type": "application/json"},
                content='{"extra":"' + "x" * 4096 + '"}',
            ).status_code
            == 413
        )
        boundary.signing_key_rotations.request.side_effect = OrganizationConflict(
            "SIGNING_KEY_CONFIRMATION_REQUIRED"
        )
        assert (
            client.post(path, headers=headers, json={**command, "acknowledged": False}).status_code
            == 409
        )
        boundary.signing_key_rotations = None
        assert client.get(path, headers=cookie(session_case)).status_code == 409
        assert client.post(path, headers=headers, json=command).status_code == 409
