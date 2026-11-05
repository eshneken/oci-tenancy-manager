"""Public instance identity never exposes authentication or secret settings."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_administrator_ui import ui
from test_auth_http import ORIGIN
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.settings import ApplicationSettings, BrandingSettings, BrandingView, load_settings

__all__ = ["session_case", "ui"]
CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"


# Existing installations with no branding block retain their internal product's public name.
def test_branding_defaults_and_explicit_instance():
    values = load_settings(CONFIG).model_dump()
    assert values["branding"]["display_name"] == "Atlas"
    del values["branding"]
    fallback = ApplicationSettings.model_validate(values).branding
    assert fallback == BrandingSettings()
    assert BrandingView(**fallback.model_dump()).model_dump() == {
        "display_name": "OCI Tenancy Manager",
        "logo_url": None,
        "icon_url": None,
    }


# Assets cannot be remote, executable, ambiguous URLs, nested paths or filesystem traversal.
@pytest.mark.parametrize(
    "path",
    [
        "https://attacker.test/logo.png",
        "//attacker.test/logo.png",
        "data:image/png;base64,AA==",
        "/branding-assets/../secret.png",
        "/branding-assets/%2e%2e.png",
        "/branding-assets/nested/logo.png",
        "/branding-assets/logo.svg",
        "/branding-assets/logo.png?x=1",
        "/branding-assets/logo.png#fragment",
        "/branding-assets/logo.png\n",
        "/branding-assets/" + "a" * 81 + ".png",
        "/branding-assets/.png",
    ],
)
def test_branding_asset_restrictions(path):
    with pytest.raises(ValidationError):
        BrandingSettings(logo_url=path)
    with pytest.raises(ValidationError):
        BrandingSettings(icon_url=path)


# Names are bounded nonblank text; extra settings cannot enter the public presentation contract.
@pytest.mark.parametrize(
    "values", [{"display_name": " "}, {"display_name": "a" * 81}, {"password": "private"}]
)
def test_branding_rejects_invalid_configuration(values):
    with pytest.raises(ValidationError):
        BrandingSettings.model_validate(values)


# Public identity loads without parsing cookies or invoking any administrator/session database read.
def test_public_branding_has_only_display_fields(session_case, ui):
    assets = ui / "branding-assets"
    assets.mkdir()
    (assets / "instance.png").write_bytes(b"synthetic raster fixture")
    branding = BrandingSettings(
        display_name="Example control plane", logo_url="/branding-assets/instance.png"
    )
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), ui_dist=ui, branding=branding
    )
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.get("/api/branding", headers={"cookie": "malformed"})
        assert response.status_code == 200 and response.json() == {
            "display_name": "Example control plane",
            "logo_url": "/branding-assets/instance.png",
            "icon_url": None,
        }
        assert response.headers["cache-control"] == "no-store"
        image = client.get("/branding-assets/instance.png")
        assert image.status_code == 200 and image.headers["content-type"] == "image/png"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert client.get("/branding-assets/unknown.png").status_code == 404
        assert client.get("/api/branding", headers={"host": "other.test"}).status_code == 400
        assert client.get("/api/branding/private").status_code == 401
        assert client.get("/branding-assets/secret.toml").status_code == 401
        assert client.get("/api/session").status_code == 401
        assert client.post("/api/branding").status_code == 403
    session_case.repository.find.assert_not_called()


# Branding alone cannot expand the default process-only factory into a public application.
def test_branding_requires_explicit_ui():
    assert TestClient(create_app()).get("/api/branding").status_code == 404
    with pytest.raises(ValueError, match="BRANDING_REQUIRES_PUBLIC_UI"):
        create_app(branding=BrandingSettings())


# Configured missing or linked assets fail at startup instead of publishing private file roots.
@pytest.mark.parametrize("damage", ["directory_link", "file_link", "missing"])
def test_branding_asset_custody(session_case, ui, tmp_path, damage):
    assets = ui / "branding-assets"
    if damage == "directory_link":
        assets.symlink_to(tmp_path.parent, target_is_directory=True)
    else:
        assets.mkdir()
        if damage == "file_link":
            (assets / "logo.png").symlink_to(ui / "index.html")
    with pytest.raises(ValueError, match="INVALID_BRANDING_ASSETS"):
        create_app(
            session_case.service,
            BrowserSettings(public_origin=ORIGIN),
            ui_dist=ui,
            branding=BrandingSettings(logo_url="/branding-assets/logo.png"),
        )
