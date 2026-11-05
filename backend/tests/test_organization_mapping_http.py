"""Mapping transport rejects unsafe inputs, cross-scope authority and private errors."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_organization_mapping import mapping_case
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.service import SessionFailure
from otm.organization.mapping_http import guarded
from otm.organization.web import organization_router
from otm.storage.organization import OrganizationConflict

__all__ = ["session_case"]
ORIGIN = "https://otm.example.test"
HEADERS = {"origin": ORIGIN, "x-otm-request": "1"}


# Closed diagnostics cannot reflect parser, database, provider or employee values.
@pytest.mark.parametrize(
    "failure,status,code",
    [
        (ValueError("private"), 400, "INVALID_MAPPING_SETTINGS"),
        (OrganizationConflict("MAPPING_ROOT_FIXED"), 409, "MAPPING_ROOT_FIXED"),
        (OrganizationConflict("private"), 409, "MAPPING_CHANGED"),
        (RuntimeError("private"), 503, "MAPPING_UNAVAILABLE"),
    ],
)
def test_mapping_closed_errors(failure, status, code):
    result = guarded(Mock(side_effect=failure))
    assert (
        result.status_code == status
        and code.encode() in result.body
        and b"private" not in result.body
    )
    with pytest.raises(SessionFailure):
        guarded(Mock(side_effect=SessionFailure(403, "ADMINISTRATOR_REQUIRED")))


# Session/CSRF authorization is shared with the actual application; no bypass-only router is used.
def test_mapping_http_authority_bounds_and_strict_fields(session_case):
    c = mapping_case()
    service = Mock()
    from otm.organization.mapping_contracts import MappingSettings

    service.read.return_value = MappingSettings(
        configured=True,
        available=True,
        context=c.context,
        candidate=c.request.candidate,
        root_editable=False,
        has_feed=True,
        roles=(),
        blockers=(),
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(organization_router(SimpleNamespace(workflows=None, mapping=service)))
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/organization/mapping").status_code == 401
        client.cookies.set(COOKIE_NAME, session_case.handle)
        assert client.get("/api/organization/mapping?workspace_id=foreign").status_code == 200
        assert (
            service.read.call_args.args[0].session.workspace_id == session_case.session.workspace_id
        )
        body = c.request.model_dump(mode="json")
        path = "/api/organization/mapping/preview"
        assert client.post(path, json=body).status_code == 403
        for altered in (
            {**body, "workspace_id": "foreign"},
            {**body, "candidate": {**body["candidate"], "policy": {"authoritative": True}}},
        ):
            assert client.post(path, json=altered, headers=HEADERS).status_code == 400
        assert (
            client.post(
                path, content="x" * 65537, headers={**HEADERS, "content-type": "application/json"}
            ).status_code
            == 413
        )
        assert (
            client.post(
                path, content="{}", headers={**HEADERS, "content-type": "text/plain"}
            ).status_code
            == 415
        )
        assert (
            client.post(
                path, content="{broken", headers={**HEADERS, "content-type": "application/json"}
            ).status_code
            == 400
        )
        # Known valid service outputs keep the response schema closed and verified.
        view, _ = c.service._compute(
            c.connection, "w", c.request, c.config, c.head, c.context, (), c.store.clock(), 1
        )
        service.preview.return_value = view
        assert client.post(path, json=body, headers=HEADERS).status_code == 200
        service.apply.side_effect = OrganizationConflict("MAPPING_PENDING_WORK")
        assert (
            client.post(
                "/api/organization/mapping/apply",
                json={**body, "preview_token": view.preview_token},
                headers=HEADERS,
            ).status_code
            == 409
        )
        service.preview.assert_called_once()
