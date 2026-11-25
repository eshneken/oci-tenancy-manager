"""Qualify local-only organization mapping and CSV upload with the installed runtime DB role."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_sandbox_runtime_postgres import runtime

from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.local import LocalLogin, LocalSignIn
from otm.local_server import development_organization
from otm.organization.web import organization_router
from otm.secrets.directory import DirectorySecrets
from otm.storage.local_auth import SqlLocalAuth
from otm.storage.organization import SqlOrganizationStore

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Exercise UI-equivalent requests and verify organization changes never stage jobs or mail.
def test_oci_development_mapping_and_csv_import(runtime):
    c = runtime
    now = datetime.now(UTC)
    store = SqlOrganizationStore(c.api, c.sessions, lambda: now)
    workspace = c.settings.local_auth.workspace_id
    organization = development_organization(store, lambda: now, workspace, "developer@example.test")
    origin = "https://127.0.0.1:8445"
    app = create_app(c.sessions, BrowserSettings(public_origin=origin))
    app.include_router(organization_router(organization))

    login = LocalLogin(
        c.settings, SqlLocalAuth(c.api, c.settings, lambda: now), DirectorySecrets(c.root / "mfa")
    )
    issued = login.sign_in(
        LocalSignIn(
            username="recovery-admin",
            password=c.password.get_secret_value(),
            totp_code=pyotp.TOTP(c.seed.get_secret_value()).at(now.timestamp()),
        )
    )
    csrf = {"origin": origin, "x-otm-request": "1"}
    csv_headers = {
        **csrf,
        "content-type": "text/csv",
        "x-otm-as-of": (now - timedelta(minutes=1)).isoformat(),
        "x-otm-complete": "true",
        "x-otm-delivery": str(uuid4()),
    }
    csv = (
        "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n"
        "Director,director@example.test,,\n"
        "Engineering Lead,lead@example.test,director@example.test,director@example.test\n"
        "Engineer,engineer@example.test,lead@example.test,lead@example.test\n"
    )

    with TestClient(app, base_url=origin) as client:
        assert client.get("/api/organization/mapping").status_code == 401
        client.cookies.set(COOKIE_NAME, issued.handle.get_secret_value())
        mapping = "/api/organization/mapping"
        assert client.get("/api/tenancies").status_code == 404
        settings = client.get(mapping).json()
        assert settings["available"] and not settings["configured"]
        assert (
            client.post("/api/organization/feeds", content=csv, headers=csv_headers).status_code
            == 409
        )
        body = {
            "context": settings["context"],
            "candidate": {
                "root_email": "director@example.test",
                "segments": [{"label": "Engineering", "leader_email": "lead@example.test"}],
            },
        }
        rejected = client.post(
            mapping + "/preview", json=body, headers={**csrf, "origin": "https://localhost:8443"}
        )
        assert rejected.status_code == 403
        preview = client.post(mapping + "/preview", json=body, headers=csrf)
        assert preview.status_code == 200
        applied = client.post(
            mapping + "/apply",
            json={**body, "preview_token": preview.json()["preview_token"]},
            headers=csrf,
        )
        assert applied.status_code == 200 and applied.json()["configured"]
        uploaded = client.post("/api/organization/feeds", content=csv, headers=csv_headers)
        assert uploaded.status_code == 200 and uploaded.json()["state"] == "published"
        directory = client.get("/api/organization").json()
        people = {row["email"]: row for row in directory["items"]}
        assert people["engineer@example.test"]["lob_name"] == "Engineering"
        assert not directory["absence_eligible"] and not directory["workflows_enabled"]

        settings = client.get(mapping).json()
        assert settings["has_feed"]
        body = {"context": settings["context"], "candidate": settings["candidate"]}
        body["candidate"]["segments"][0]["label"] = "Product Engineering"
        preview = client.post(mapping + "/preview", json=body, headers=csrf)
        assert preview.status_code == 200
        applied = client.post(
            mapping + "/apply",
            json={**body, "preview_token": preview.json()["preview_token"]},
            headers=csrf,
        )
        assert applied.status_code == 200
        assert "Product Engineering" in {
            row["lob_name"] for row in client.get("/api/organization").json()["items"]
        }
    with c.owner.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.procrastinate_jobs")) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.otm_notification_outbox")) == 0
