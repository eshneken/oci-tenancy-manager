"""Authenticated same-origin configuration commands reject malformed and privileged input."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_baseline_authoring import NOW
from test_configuration_updates import update_case
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.auth.service import SessionFailure
from otm.configuration.rollout_contracts import ConfigurationPreview
from otm.configuration.rollout_http import guarded, rollout_router
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import ActionReceipt

__all__ = ["session_case", "update_case"]


# Service failures return only closed diagnostics, never raw SQL/provider/employee input.
@pytest.mark.parametrize(
    "failure,status",
    [
        (OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND"), 404),
        (OrganizationConflict("private"), 409),
        (RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT"), 409),
        (ValueError("private"), 400),
        (RuntimeError("private"), 503),
    ],
)
def test_closed_error_mapping(failure, status):
    result = guarded(Mock(side_effect=failure))
    assert result.status_code == status and b"private" not in result.body
    with pytest.raises(SessionFailure):
        guarded(Mock(side_effect=SessionFailure(403, "ADMINISTRATOR_REQUIRED")))


# The real session/Origin/header middleware runs before the bounded closed DTO reaches the service.
def test_protected_configuration_commands(session_case, update_case):
    c = update_case
    service = Mock()
    service.preview.return_value = ConfigurationPreview(
        baseline=c.baseline,
        tenancy_id=None,
        ready_count=1,
        pending_count=0,
        blockers=(),
        preview_hash="a" * 64,
    )
    service.start.return_value = service.retry.return_value = ActionReceipt(
        operation_id=c.operation["id"], state="queued", provider_mode="simulated", accepted_at=NOW
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(rollout_router(service))
    path = "/api/configuration/updates"
    command = {
        "client_request_key": str(uuid4()),
        "tenancy_id": str(c.target.tenancy_id),
        "preview_hash": "a" * 64,
    }
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(path + "/preview").status_code == 401
        assert (
            client.post(
                path, json=command, headers={**headers, "origin": "https://foreign.test"}
            ).status_code
            == 403
        )
        assert client.get(path + "/preview", headers=headers).status_code == 200
        assert (
            client.post(path, json={**command, "actor": "privileged"}, headers=headers).status_code
            == 400
        )
        assert client.post(path, content="bad", headers=headers).status_code == 415
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
        assert client.post(path, json=command, headers=headers).status_code == 202
        retry = path + "/" + str(c.operation["id"]) + "/retry"
        assert (
            client.post(retry, json={"baseline_id": str(uuid4())}, headers=headers).status_code
            == 400
        )
        assert client.post(retry, headers=headers).status_code == 202
        service.start.return_value = service.start.return_value.model_copy(
            update={"state": "succeeded"}
        )
        assert client.post(path, json=command, headers=headers).status_code == 200
        service.start.assert_called()
