"""Override and plan endpoints retain same-origin administrator authority."""

from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_baseline_authoring import NOW
from test_configuration_updates import update_case
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.configuration.override_contracts import OverrideEditor, OverrideValues
from otm.configuration.rollout_contracts import ConfigurationPlanView, ConfigurationPreview
from otm.configuration.rollout_http import rollout_router
from otm.tenancies.contracts import ActionReceipt

__all__ = ["update_case", "session_case"]


# Real middleware protects reads/POSTs before injected application boundaries are reached.
def test_override_and_plan_http_boundaries(session_case, update_case):
    c = update_case
    service = Mock()
    plans = Mock()
    view = ConfigurationPreview(
        baseline=c.baseline,
        tenancy_id=c.target.tenancy_id,
        ready_count=1,
        pending_count=0,
        blockers=(),
        preview_hash="a" * 64,
    )
    editor = OverrideEditor(
        tenancy_id=c.target.tenancy_id,
        tenancy_name=c.target.name,
        tenancy_revision=1,
        baseline=c.baseline,
        configuration=None,
        values=OverrideValues(),
        can_edit=True,
    )
    plan = ConfigurationPlanView(id=uuid4(), revision=1, state="draft", preview=view)
    service.override_editor.return_value = editor
    service.preview_override.return_value = view
    service.start.return_value = ActionReceipt(
        operation_id=c.operation["id"], state="queued", provider_mode="simulated", accepted_at=NOW
    )
    plans.create.return_value = plans.read.return_value = plans.review.return_value = plan
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    with patch("otm.configuration.rollout_http.ConfigurationPlans", return_value=plans):
        app.include_router(rollout_router(service))
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    context = {
        "baseline_version_id": str(c.baseline.id),
        "tenancy_revision": 1,
        "configuration_id": None,
    }
    body = {
        "tenancy_id": str(c.target.tenancy_id),
        "values": {"monthly_budget_override_amount": "500"},
        "context": context,
    }
    command = {
        "client_request_key": str(uuid4()),
        "tenancy_id": str(c.target.tenancy_id),
        "preview_hash": "a" * 64,
        "override_mode": True,
        "override_context": context,
        "overrides": body["values"],
    }
    with TestClient(app, base_url=ORIGIN) as client:
        assert (
            client.get("/api/configuration/overrides/" + str(c.target.tenancy_id)).status_code
            == 401
        )
        assert (
            client.post(
                "/api/configuration/plans",
                json={},
                headers={**headers, "origin": "https://foreign.test"},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/configuration/overrides/" + str(c.target.tenancy_id), headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/configuration/overrides/preview", json=body, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/configuration/overrides/preview",
                json={**body, "actor": "forged"},
                headers=headers,
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/configuration/overrides/preview", content="bad", headers=headers
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/api/configuration/overrides/preview",
                content="x" * 2097153,
                headers={**headers, "content-type": "application/json"},
            ).status_code
            == 413
        )
        assert (
            client.post("/api/configuration/overrides", json=command, headers=headers).status_code
            == 202
        )
        assert (
            client.post("/api/configuration/updates", json=command, headers=headers).status_code
            == 400
        )
        assert (
            client.post(
                "/api/configuration/overrides",
                json={
                    key: value
                    for key, value in command.items()
                    if key not in {"override_mode", "override_context", "overrides"}
                },
                headers=headers,
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/configuration/plans",
                json={"client_request_key": str(uuid4()), "tenancy_id": str(c.target.tenancy_id)},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.get("/api/configuration/plans/" + str(plan.id), headers=headers).status_code
            == 200
        )
        assert (
            client.post(
                "/api/configuration/plans/" + str(plan.id) + "/reviews",
                json={
                    "expected_revision": 1,
                    "tenancy_id": str(c.target.tenancy_id),
                    "policy_choice": "keep_override",
                },
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/configuration/plans/" + str(plan.id) + "/reviews",
                json={
                    "expected_revision": 1,
                    "tenancy_id": str(c.target.tenancy_id),
                    "policy_choice": "merge",
                },
                headers=headers,
            ).status_code
            == 400
        )
        assert client.post("/api/configuration/plans", json={}, headers=headers).status_code == 400
        service.start.return_value = service.start.return_value.model_copy(
            update={"state": "succeeded"}
        )
        assert (
            client.post("/api/configuration/overrides", json=command, headers=headers).status_code
            == 200
        )
