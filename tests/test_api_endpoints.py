"""
tests/test_api_endpoints.py — End-to-end integration tests for FastAPI routers.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.auth import auth_manager
from core.settings import Settings, settings


@pytest.fixture(autouse=True)
def clean_auth_for_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Ensure tests run with an isolated auth store and clean rate limits."""
    test_settings = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    test_settings.initialise()
    monkeypatch.setattr(auth_manager, "_settings", test_settings)
    auth_manager._rate._hits.clear()
    yield
    auth_manager._rate._hits.clear()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client: TestClient):
    """GET /health returns 200 ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_frontend_root_served(client: TestClient):
    """GET / serves the dashboard HTML when frontend/dist is built."""
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if not dist.is_dir():
        pytest.skip("frontend/dist is not built in this environment")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "AIO Media Server Manager" in resp.text



def test_auth_status_setup_and_login_flow(client: TestClient):
    """Complete auth lifecycle: status -> setup -> me -> logout."""
    # 1. Initially requires setup
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is True
    assert resp.json()["authenticated"] is False

    # 2. Complete setup
    setup_payload = {
        "username": "admin",
        "password": "StrongPassword123!",
    }
    resp = client.post("/api/auth/setup", json=setup_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert "access_token" in data
    assert "csrf_token" in data

    token = data["access_token"]

    # 3. Status now indicates setup not required and returns the CSRF cookie
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is False
    assert resp.json()["authenticated"] is True
    assert resp.json().get("csrf_token")

    # 4. /api/auth/me with Bearer token
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"

    # 5. Login with invalid password
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword"})
    assert resp.status_code == 401

    # 6. Login with correct password
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword123!"})
    assert resp.status_code == 200
    new_token = resp.json()["access_token"]
    assert new_token is not None


def test_catalog_endpoints(client: TestClient):
    """Catalog endpoints list applications and port assignments."""
    # 1. List catalog
    resp = client.get("/api/catalog")
    assert resp.status_code == 200
    apps = resp.json()["applications"]
    assert len(apps) >= 7
    names = [a["name"] for a in apps]
    assert "prowlarr" in names
    assert "sonarr" in names

    # 2. Get single app details
    resp = client.get("/api/catalog/prowlarr")
    assert resp.status_code == 200
    app_data = resp.json()
    assert app_data["name"] == "prowlarr"
    assert app_data["default_port"] == 9696

    # 3. Port allocations
    resp = client.get("/api/catalog/ports")
    assert resp.status_code == 200
    allocations = resp.json()["allocations"]
    alloc_map = {a["app_name"]: a["port"] for a in allocations}
    assert alloc_map.get("prowlarr") == 9696


def test_applications_endpoints(client: TestClient):
    """Application management endpoints return process statuses and logs."""
    # 1. List application statuses
    resp = client.get("/api/applications")
    assert resp.status_code == 200
    apps = resp.json()["applications"]
    assert len(apps) >= 7

    # 2. Get application logs
    resp = client.get("/api/applications/prowlarr/logs")
    assert resp.status_code == 200
    assert resp.json()["name"] == "prowlarr"
    assert isinstance(resp.json()["lines"], list)


def test_system_info_endpoint(client: TestClient):
    """GET /api/system/info returns paths and supervisor status."""
    resp = client.get("/api/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "storage" in data
    assert "settings" in data
    assert "puid" in data["settings"]
    assert "pgid" in data["settings"]
