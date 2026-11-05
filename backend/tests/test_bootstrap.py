"""Production bootstrap contracts, without network listeners, credentials or external services."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import otm
from otm.app import create_app


# The production environment must resolve its own package rather than the local lab.
def test_package_import_is_isolated_from_the_prototype():
    source = Path(__file__).resolve().parents[1] / "src/otm"
    assert Path(otm.__file__).resolve().parent == source


# Health reports a small public contract without claiming external dependency readiness.
def test_liveness_is_process_only_and_contains_no_environment_details():
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Local destructive shortcuts and interactive documentation cannot leak into this app.
@pytest.mark.parametrize("path", ["/api/local/clean", "/api/local/feeds", "/docs", "/openapi.json"])
def test_prototype_and_documentation_endpoints_are_not_exposed(path):
    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 404
        assert client.post(path, json={}).status_code == 404


# App construction cannot inherit mutable routes or accidentally mount prototype handlers.
def test_only_explicit_health_route_is_mounted_and_factories_are_independent():
    first, second = create_app(), create_app()
    assert first is not second and first.router is not second.router
    assert {route.path for route in first.routes} == {"/health/live"}
