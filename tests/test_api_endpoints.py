"""
tests/test_api_endpoints.py — End-to-end integration tests for FastAPI routers.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core import two_factor
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
    auth_manager._factor_rate._hits.clear()
    yield
    auth_manager._rate._hits.clear()
    auth_manager._factor_rate._hits.clear()


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
        "email": "admin@example.com",
        "password": "StrongPassword123!",
    }
    resp = client.post("/api/auth/setup", json=setup_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["email"] == "admin@example.com"
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
    assert resp.json()["email"] == "admin@example.com"

    # 5. Login with invalid password
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword"})
    assert resp.status_code == 401

    # 6. Login with correct password
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword123!"})
    assert resp.status_code == 200
    new_token = resp.json()["access_token"]
    assert new_token is not None


def test_setup_requires_email(client: TestClient):
    resp = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "StrongPassword123!"},
    )
    assert resp.status_code in (400, 422)


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
    sonarr = next(a for a in apps if a["name"] == "sonarr")
    shelfmark = next(a for a in apps if a["name"] == "shelfmark")
    assert sonarr["popularity"] > shelfmark["popularity"]
    assert "category" in sonarr

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
    """Unauthenticated LAN clients cannot read the host dump."""
    resp = client.get("/api/system/info")
    assert resp.status_code == 401

    local = TestClient(create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    resp = local.get("/api/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["debug"] is True
    assert "storage" in data
    assert "settings" in data
    assert "puid" in data["settings"]
    assert "pgid" in data["settings"]
    media = data["storage"].get("media_dir") or next(iter(data["storage"].values()), {})
    assert "fs_type" in media
    assert "disk_total" in media


def test_two_factor_enrollment_and_recovery(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    credentials = {"username": "admin", "password": "StrongPassword123!"}
    monkeypatch.setattr("api.routers.auth.save_shared_admin_credentials", lambda *args, **kwargs: None)
    setup = client.post("/api/auth/setup", json={**credentials, "email": "admin@example.com"})
    initial = {"Authorization": f"Bearer {setup.json()['access_token']}"}
    path = "/api/auth/two-factor"
    assert client.get(path, headers=initial).json() == {"enabled": False}
    assert client.post(f"{path}/setup", json={"password": credentials["password"]}).status_code == 403

    enrollment = client.post(f"{path}/setup", headers=initial, json={"password": credentials["password"]})
    assert enrollment.status_code == 200
    assert enrollment.headers["cache-control"] == "no-store"
    pending = enrollment.json()
    assert client.get(path, headers=initial).json() == {"enabled": False}

    counter = 60_000_000
    monkeypatch.setattr(two_factor, "current_counter", lambda: counter)
    code = two_factor.totp_code(pending["secret"], counter)
    confirmation = {"enrollment": pending["enrollment"], "code": code}
    enabled = client.post(f"{path}/enable", headers=initial, json=confirmation)
    assert enabled.status_code == 200
    data = enabled.json()
    assert len(set(data["recovery_codes"])) == 10
    recovery_code = data["recovery_codes"][0]
    assert recovery_code not in auth_manager._auth_path.read_text()
    assert pending["secret"] not in auth_manager._auth_path.read_text()

    assert client.get(path, headers=initial).status_code == 401
    client.cookies.clear()
    challenge = client.post("/api/auth/login", json=credentials)
    assert challenge.json() == {"status": "two_factor_required"}
    assert "set-cookie" not in challenge.headers
    assert client.get("/api/auth/status").json()["authenticated"] is False
    assert client.post("/api/auth/login", json={**credentials, "code": code}).status_code == 401

    next_code = two_factor.totp_code(pending["secret"], counter + 1)
    success = client.post("/api/auth/login", json={**credentials, "code": next_code})
    assert success.status_code == 200
    assert client.post("/api/auth/login", json={**credentials, "code": next_code}).status_code == 401

    success = client.post("/api/auth/login", json={**credentials, "code": recovery_code})
    assert success.status_code == 200
    assert client.post("/api/auth/login", json={**credentials, "code": recovery_code}).status_code == 401

    headers = {"Authorization": f"Bearer {success.json()['access_token']}"}
    disabled = client.post(f"{path}/disable", headers=headers, json={
        "password": credentials["password"], "code": data["recovery_codes"][1],
    })
    assert disabled.status_code == 200
    assert client.get(path, headers=headers).status_code == 401
    replacement = {"Authorization": f"Bearer {disabled.json()['access_token']}"}
    assert client.get(path, headers=replacement).json() == {"enabled": False}
    assert "access_token" in client.post("/api/auth/login", json=credentials).json()


def test_auth_does_not_echo_invalid_verification_data(client: TestClient):
    code = "private-input" * 20
    response = client.post("/api/auth/login", json={"username": "admin", "password": "unused", "code": code})
    assert response.status_code == 422
    assert code not in response.text


def test_passkey_options_require_local_session_and_secure_origin(client, monkeypatch):
    monkeypatch.setattr("api.routers.auth.save_shared_admin_credentials", lambda *args, **kwargs: None)
    password = "FixturePasskeyPassword123!"
    setup = client.post("/api/auth/setup", json={
        "username": "admin", "password": password, "email": "admin@example.test",
    })
    auth = {"Authorization": f"Bearer {setup.json()['access_token']}"}
    endpoint = "/api/auth/passkeys/register/options"
    assert client.post(endpoint, headers={**auth, "Origin": "https://elsewhere.example"},
                       json={"password": password}).status_code == 400
    assert client.post(endpoint, headers={**auth, "Origin": "http://testserver"},
                       json={"password": password}).status_code == 400
    origin = {"Origin": "https://testserver"}
    assert client.post(endpoint, headers=origin, json={"password": password}).status_code == 403
    response = client.post(endpoint, headers={**auth, **origin}, json={"password": password})
    assert response.status_code == 200
    options = response.json()
    assert options["rp"]["id"] == "testserver"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert response.headers["cache-control"] == "no-store"
    other = {"Authorization": f"Bearer {auth_manager.issue_token('admin')}"}
    pending = {"challenge": options["challenge"], "credential": "{}"}
    verify_url = "/api/auth/passkeys/register"
    wrong_session = client.post(verify_url, headers={**other, **origin}, json=pending)
    assert wrong_session.json()["detail"] == "Passkey request expired. Try again."
    same_session = client.post(verify_url, headers={**auth, **origin}, json=pending)
    assert same_session.json()["detail"] == "Could not verify the passkey."


def test_passkey_registration_requires_second_factor_when_enabled(client, monkeypatch):
    monkeypatch.setattr("api.routers.auth.save_shared_admin_credentials", lambda *args, **kwargs: None)
    password = "FixturePasskeyPassword123!"
    auth_manager.create_admin("admin", password, email="admin@example.test")
    counter = 60_000_000
    monkeypatch.setattr(two_factor, "current_counter", lambda: counter)
    secret, enrollment = auth_manager.begin_two_factor()
    recovery = auth_manager.enable_two_factor(enrollment, two_factor.totp_code(secret, counter))
    token = auth_manager.issue_token("admin")
    headers = {"Authorization": f"Bearer {token}", "Origin": "https://testserver"}
    endpoint = "/api/auth/passkeys/register/options"

    assert client.post(endpoint, headers=headers, json={"password": password}).status_code == 400
    next_code = two_factor.totp_code(secret, counter + 1)
    assert client.post(endpoint, headers=headers, json={"password": password, "code": next_code}).status_code == 200
    assert client.post(endpoint, headers=headers, json={"password": password, "code": next_code}).status_code == 400

    auth_manager.save_passkey({"origin": "https://testserver"})
    assert client.post(endpoint, headers=headers, json={"password": password, "code": recovery[0]}).status_code == 409
    removed = client.post("/api/auth/passkeys/remove", headers={"Authorization": f"Bearer {token}"},
                          json={"password": password, "code": recovery[0]})
    assert removed.json() == {"origin": None}
    assert auth_manager.passkey() is None
