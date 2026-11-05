"""Public shell and protected directory boundaries without a database or browser factor bypass."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.administrators import AdministratorDirectory, AdministratorFailure
from otm.auth.http import BrowserSettings

__all__ = ["session_case"]


# Build synthetic immutable assets, never serve a checkout or real private local directory.
@pytest.fixture
def ui(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<main id="root"></main>')
    (tmp_path / "assets/app.js").write_text('document.title="OTM";')
    return tmp_path


# Public HTML and scripts must load before sign-in while all near-prefix/API paths remain guarded.
def test_public_ui_only_exposes_explicit_shell_and_assets(session_case, ui):
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), ui_dist=ui)
    with TestClient(app, base_url=ORIGIN) as client:
        for path in (
            "/",
            "/login",
            "/administrators",
            "/tenancies",
            "/tenancies/" + str(uuid4()),
            "/organization",
            "/organization/drift",
            "/organization-mapping",
            "/configuration",
            "/configuration/drift",
            "/configuration/drift/" + str(uuid4()),
            "/operations",
            "/audit-history",
            "/operations/" + str(uuid4()),
            "/assets/app.js",
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert "script-src 'self'" in response.headers["content-security-policy"]
            assert response.headers["cache-control"] == "no-store"
        for path in (
            "/api/administrators",
            "/api/configuration/baselines",
            "/configuration/extra",
            "/configuration/drift/not-an-id",
            "/configuration/drift/" + str(uuid4()) + "/extra",
            "/api/configuration/drift",
            "/configuration-other",
            "/api/organization/mapping",
            "/organization-mapping/anything",
            "/organization-mapping-other",
            "/login/anything",
            "/assets-other",
            "/operations/not-an-id",
            "/operations/" + str(uuid4()) + "/extra",
            "/.local-dev/state.json",
        ):
            assert client.get(path).status_code == 401
        assert (
            client.post("/login", headers={"origin": ORIGIN, "x-otm-request": "1"}).status_code
            == 401
        )
        assert client.get("/login", headers={"host": "attacker.test"}).status_code == 400
        assert client.get("/assets/no-file.js").status_code == 404
    session_case.repository.find.assert_not_called()


# Neither a linked asset directory nor linked shell can publish private files through static roots.
@pytest.mark.parametrize("target", ["assets", "index.html", "missing"])
def test_invalid_asset_roots_refused(session_case, ui, tmp_path, target):
    if target == "assets":
        (ui / "assets/app.js").unlink()
        (ui / "assets").rmdir()
        (ui / "assets").symlink_to(tmp_path.parent, target_is_directory=True)
    elif target == "index.html":
        (ui / target).unlink()
        (ui / target).symlink_to(tmp_path / "outside")
    else:
        (ui / "index.html").unlink()
    with pytest.raises(ValueError, match="BUILT_FRONTEND_REQUIRED"):
        create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), ui_dist=ui)


# Optional routes cannot silently enable an unauthenticated application factory.
def test_optional_ui_requires_session_authority(ui):
    with pytest.raises(ValueError, match="ADMINISTRATION_UI_REQUIRES_SESSION_BOUNDARY"):
        create_app(ui_dist=ui)
    with pytest.raises(ValueError, match="ADMINISTRATION_UI_REQUIRES_SESSION_BOUNDARY"):
        create_app(administrators=Mock())


# Fresh scope, allowlisted queries and fixed storage errors protect directory reads and mutations.
def test_directory_and_revocation_boundaries(session_case):
    store = Mock()
    store.directory.return_value = AdministratorDirectory(
        items=[],
        total=0,
        page=1,
        page_size=10,
        pages=1,
        statistics={"total": 0, "active": 0, "protected_recovery": 0},
    )
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), administrators=store
    )
    with TestClient(app, base_url=ORIGIN) as client:
        headers = cookie(session_case)
        response = client.get("/api/administrators?query=a%25&page=2", headers=headers)
        assert response.status_code == 200 and response.json()["items"] == []
        args = store.directory.call_args.args
        assert args[0] == session_case.session.workspace_id and args[1].query == "a%"
        assert (
            response.headers["content-security-policy"]
            == "default-src 'none'; frame-ancestors 'none'"
        )
        for query in (
            "sort=drop",
            "page=0",
            "page_size=7",
            "direction=sideways",
            "query=" + "x" * 129,
        ):
            assert client.get("/api/administrators?" + query, headers=headers).status_code == 400
        store.directory.side_effect = RuntimeError("private SQL")
        response = client.get("/api/administrators", headers=headers)
        assert response.status_code == 503 and "private" not in response.text
        identifier, revision = uuid4(), uuid4()
        store.revoke.side_effect = AdministratorFailure(403, "RECOVERY_ADMINISTRATOR_PROTECTED")
        headers.update(origin=ORIGIN, **{"x-otm-request": "1"})
        response = client.post(
            f"/api/administrators/{identifier}/revoke",
            headers=headers,
            json={"expected_revision": str(revision)},
        )
        assert response.status_code == 403
        assert store.revoke.call_args.args[1:] == (identifier, revision)
