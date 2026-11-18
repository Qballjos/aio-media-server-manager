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


@pytest.mark.parametrize("path", ["/api/catalog", "/api/applications", "/api/homepage", "/api/logs"])
def test_member_session_cannot_read_admin_endpoints(client: TestClient, path: str):
    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42")

    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 403


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


@pytest.mark.parametrize(
    ("provider", "kind", "server_key", "account_key", "user_type", "import_key"),
    [
        ("jellyfin", 2, "serverId", "jellyfinUserId", 3, "jellyfinUserIds"),
        ("plex", 1, "machineId", "plexId", 1, "plexIds"),
    ],
)
def test_media_user_import_and_revocation(
    client, monkeypatch, provider, kind, server_key, account_key, user_type, import_key,
):
    from api.routers import media_users
    from core.integrations.seerr import SeerrClient

    imported = False
    import_calls = []

    def seerr_api(_client, path, payload=None):
        nonlocal imported
        if path == "/settings/main":
            return {"mediaServerType": kind}
        if path == f"/settings/{provider}":
            return {server_key: "server-a"}
        if path == f"/settings/{provider}/users":
            return [{"id": "42", "username": "viewer", "token": "secret"}] if not imported else []
        if path == "/user?take=50&skip=0":
            rows = [{
                "id": 8, account_key: "42", "userType": user_type,
                "displayName": "viewer", "plexToken": "secret",
            }] if imported else []
            return {"results": rows, "pageInfo": {"results": len(rows)}}
        assert path == f"/user/import-from-{provider}"
        assert payload == {import_key: ["42"]}
        import_calls.append(path)
        imported = True

    monkeypatch.setattr(SeerrClient, "_media_users_api", seerr_api)
    monkeypatch.setattr(media_users, "_client", SeerrClient)
    auth_manager.create_admin("admin", "StrongPassword123!")
    headers = {"Authorization": f"Bearer {auth_manager.issue_token('admin')}"}
    path = "/api/settings/media-users"

    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers).json() == {
        "provider": provider,
        "users": [{"id": "42", "name": "viewer", "imported": False, "enabled": False}],
    }
    for _ in range(2):
        assert client.post(path, headers=headers, json={"account_ids": ["42"]}).json() == {"enabled": ["42"]}
    assert len(import_calls) == 1
    assert client.get(path, headers=headers).json()["users"] == [
        {"id": "42", "name": "viewer", "imported": True, "enabled": True},
    ]

    member_token = auth_manager.issue_member_token(provider, "server-a", "42")
    assert client.get(path, headers={"Authorization": f"Bearer {member_token}"}).status_code == 403
    assert client.delete(f"{path}/42", headers=headers).status_code == 204
    with pytest.raises(media_users.HTTPException) as revoked:
        auth_manager.decode_token(member_token, member=True)
    assert revoked.value.status_code == 401


def test_jellyfin_member_sign_in_requires_browser_and_grant(client, monkeypatch):
    from api.routers import media_login
    from core.integrations.jellyfin import JellyfinClient

    monkeypatch.setattr(media_login, "_media_server_id", lambda provider: "server-a")
    monkeypatch.setattr(JellyfinClient, "begin_member_sign_in", lambda self, device: ("123456", "private-secret"))
    results = iter([None, ("server-a", "42", "fixture-jellyfin-token")])
    monkeypatch.setattr(JellyfinClient, "finish_member_sign_in", lambda self, device, secret: next(results))
    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("jellyfin", "server-a", "42")
    path = "/api/media-login/jellyfin"
    started = client.post(path)
    assert started.status_code == 200
    assert started.json()["code"] == "123456"
    assert "private-secret" not in started.text
    headers = {"X-AIO-Media-Attempt": started.json()["attempt"]}
    with TestClient(client.app) as other:
        assert other.post(f"{path}/complete", headers=headers).status_code == 404
    assert client.post(f"{path}/complete", headers=headers).status_code == 202
    assert client.post(f"{path}/complete", headers=headers).status_code == 200
    assert client.post(f"{path}/complete", headers=headers).status_code == 404
    assert client.get("/api/catalog").status_code == 403
    assert client.get("/api/media-login/session").json()["account_id"] == "42"
    auth_manager.media_users.revoke("jellyfin", "server-a", "42")
    assert client.get("/api/media-login/session").status_code == 401


@pytest.mark.parametrize(
    ("server_id", "account_id", "expired", "expected"),
    [
        ("server-a", "99", False, 403),
        ("server-b", "42", False, 403),
        ("server-a", "42", True, 404),
    ],
)
def test_jellyfin_member_sign_in_rejects_invalid_identity(
    client, monkeypatch, server_id, account_id, expired, expected,
):
    from api.routers import media_login
    from core.integrations.jellyfin import JellyfinClient

    monkeypatch.setattr(media_login, "_media_server_id", lambda provider: "server-a")
    monkeypatch.setattr(JellyfinClient, "begin_member_sign_in", lambda self, device: ("123456", "private-secret"))
    monkeypatch.setattr(
        JellyfinClient, "finish_member_sign_in", lambda self, device, secret: (server_id, account_id, "fixture-jellyfin-token"),
    )
    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("jellyfin", "server-a", "42")

    path = "/api/media-login/jellyfin"
    started = client.post(path)
    key = started.json()["attempt"]
    if expired:
        from dataclasses import replace

        monkeypatch.setitem(media_login._pending, key, replace(media_login._pending[key], expires=0))

    response = client.post(f"{path}/complete", headers={"X-AIO-Media-Attempt": key})
    assert response.status_code == expected
    assert client.get("/api/media-login/session").status_code == 401


@pytest.mark.parametrize(("has_server_access", "granted"), [(True, True), (False, True), (True, False)])
def test_plex_member_sign_in(client, monkeypatch, has_server_access, granted):
    from urllib.parse import parse_qs, urlsplit

    import requests

    from api.routers import media_login

    monkeypatch.setattr(media_login, "_media_server_id", lambda provider: "server-a")
    auth_manager.create_admin("admin", "StrongPassword123!")
    if granted:
        auth_manager.media_users.grant("plex", "server-a", "42")
    approved = False
    identifiers = set()

    def plex_api(method, url, *, headers, **kwargs):
        from unittest.mock import Mock

        assert kwargs["allow_redirects"] is False
        identifiers.add(headers["X-Plex-Client-Identifier"])
        path = urlsplit(url).path
        if method == "POST":
            assert path == "/api/v2/pins"
            assert kwargs["params"] == {"strong": "true"}
            body = {"id": 123, "code": "abc#pin"}
        elif path == "/api/v2/pins/123":
            body = {"authToken": "private-plex-token" if approved else None}
        elif path == "/api/v2/user":
            assert headers["X-Plex-Token"] == "private-plex-token"
            body = {"id": 42}
        else:
            assert path == "/api/v2/resources"
            assert headers["X-Plex-Token"] == "private-plex-token"
            body = [{
                "clientIdentifier": "server-a" if has_server_access else "other",
                "provides": "server", "accessToken": "private-server-token",
            }]
        return Mock(status_code=201 if method == "POST" else 200, **{"json.return_value": body})

    monkeypatch.setattr(requests, "request", plex_api)
    path = "/api/media-login/plex"
    started = client.post(path)
    assert started.status_code == 200
    assert "private" not in started.text
    url = urlsplit(started.json()["authorize_url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "app.plex.tv", "/auth")
    assert parse_qs(url.fragment[1:])["code"] == ["abc#pin"]
    headers = {"X-AIO-Media-Attempt": started.json()["attempt"]}
    with TestClient(client.app) as other:
        assert other.post(f"{path}/complete", headers=headers).status_code == 404
    assert client.post("/api/media-login/jellyfin/complete", headers=headers).status_code == 404
    assert client.post(f"{path}/complete", headers=headers).status_code == 202
    approved = True
    result = client.post(f"{path}/complete", headers=headers)
    signed_in = has_server_access and granted
    assert result.status_code == (200 if signed_in else 403)
    assert "private" not in result.text
    assert client.get("/api/media-login/session").status_code == (200 if signed_in else 401)
    assert client.post(f"{path}/complete", headers=headers).status_code == 404
    assert len(identifiers) == 1
    if signed_in:
        assert client.post("/api/media-login/logout").status_code == 403
        csrf = result.json()["csrf_token"]
        assert client.post("/api/media-login/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
        assert client.get("/api/media-login/session").status_code == 401


def test_support_reports_are_private_and_reach_admin(client):
    auth_manager.create_admin("admin", "StrongPassword123!")
    admin = {"Authorization": f"Bearer {auth_manager.issue_token('admin')}"}

    def member(provider, server, account):
        auth_manager.media_users.grant(provider, server, account)
        return {"Authorization": f"Bearer {auth_manager.issue_member_token(provider, server, account)}"}

    owner = member("plex", "server-a", "42")
    other = member("plex", "server-b", "42")
    path = "/api/support"
    response = client.post(path, headers=owner, json={"subject": "Playback", "message": "Audio stops."})
    assert response.status_code == 201
    report = response.json()
    detail = f"{path}/{report['id']}"
    assert client.get(path, headers=other).json()["reports"] == []
    assert client.get(detail, headers=other).status_code == 404
    assert client.post(f"{detail}/replies", headers=other, json={"message": "Hello"}).status_code == 404
    assert client.patch(detail, headers=owner, json={"status": "resolved"}).status_code == 403
    assert client.get(path, headers=admin).json()["new_count"] == 1
    assert client.post(f"{detail}/replies", headers=admin, json={"message": "Please retry."}).status_code == 201
    assert client.patch(detail, headers=admin, json={"status": "resolved"}).status_code == 200
    assert client.get(path, headers=admin).json()["new_count"] == 0
    thread = client.get(detail, headers=owner).json()
    assert thread["status"] == "resolved"
    assert thread["replies"][0]["author"] == "admin"
    assert thread["replies"][0]["message"] == "Please retry."


def test_member_discovery_uses_shared_filter_and_hides_library_status(client, monkeypatch):
    from api.routers import media_discovery

    from core.integrations.seerr import SeerrClient

    monkeypatch.setattr(media_discovery, "_seerr_client", SeerrClient)
    monkeypatch.setattr(SeerrClient, "trending_request_coverage", lambda *_: {})
    auth_manager.create_admin("admin", "StrongPassword123!")
    admin = {"Authorization": f"Bearer {auth_manager.issue_token('admin')}"}
    auth_manager.media_users.grant("plex", "server-a", "42")
    member = {"Authorization": f"Bearer {auth_manager.issue_member_token('plex', 'server-a', '42')}"}
    rows = [
        {"mediaType": "movie", "mediaId": 4, "title": "Film", "status": "available", "url": "private"},
        {"mediaType": "tv", "mediaId": 5, "title": "Series", "can_request": False},
    ]
    monkeypatch.setattr(media_discovery, "homepage_trending", lambda host, page: {"items": rows})
    monkeypatch.setattr(media_discovery, "_seerr_search", lambda catalog, term: (rows, None))
    root = "/api/media-discovery"
    assert client.put(f"{root}/trending-filter", headers=member, json={"filter": "movie"}).status_code == 403
    assert client.put(f"{root}/trending-filter", headers=admin, json={"filter": "movie"}).status_code == 200
    assert client.get(f"{root}/trending", headers=member).json()["items"] == [
        {"mediaType": "movie", "mediaId": 4, "title": "Film"},
    ]
    result = client.get(f"{root}/search?q=film", headers=member).json()
    assert len(result["items"]) == 2
    assert all("status" not in row and "url" not in row and "can_request" not in row for row in result["items"])


def test_member_requests_use_session_identity_and_ignore_global_availability(client, monkeypatch):
    from api.routers import media_discovery
    from core.integrations.seerr import SeerrClient

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42")
    monkeypatch.setattr(media_discovery, "_seerr_client", SeerrClient)

    def seerr_api(_client, path, payload=None):
        if path == "/settings/main":
            return {"mediaServerType": 1}
        if path == "/settings/plex":
            return {"machineId": "server-a"}
        if path == "/user?take=50&skip=0":
            return {
                "results": [{"id": 8, "userType": 1, "plexId": 42}],
                "pageInfo": {"results": 1},
            }
        assert path == "/user/8/requests?take=20&skip=0"
        return {
            "results": [
                {"id": 1, "type": "movie", "status": 2, "requestedBy": {"id": 8},
                 "media": {"tmdbId": 4, "status": 5, "rootFolder": "private"}},
                {"id": 2, "type": "movie", "status": 1, "requestedBy": {"id": 9},
                 "media": {"tmdbId": 5}},
            ],
            "pageInfo": {"results": 2},
        }

    monkeypatch.setattr(SeerrClient, "_media_users_api", seerr_api)
    monkeypatch.setattr(media_discovery, "seerr_catalog_details", lambda *args: {"title": "Film", "poster": ""})
    response = client.get("/api/media-discovery/requests?user_id=9", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "items": [{
            "id": 1, "title": "Film", "status": "approved", "poster": "",
            "mediaType": "movie", "createdAt": None, "seasons": [],
        }],
        "has_more": False,
    }


def test_member_quota_uses_only_the_signed_in_account(client, monkeypatch):
    from api.routers import media_discovery
    from core.integrations.seerr import SeerrClient

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("jellyfin", "server-a", "42")
    token = auth_manager.issue_member_token("jellyfin", "server-a", "42")
    monkeypatch.setattr(media_discovery, "_seerr_client", SeerrClient)

    def user_id(_self, *account):
        assert account == ("jellyfin", "server-a", "42")
        return 8

    def seerr_api(_self, path):
        assert path == "/user/8/quota"
        return {
            "movie": {"limit": 5, "remaining": 0, "days": 7, "restricted": True, "extra": "private"},
            "tv": {"limit": 0, "days": 7},
        }

    monkeypatch.setattr(SeerrClient, "member_user_id", user_id)
    monkeypatch.setattr(SeerrClient, "_media_users_api", seerr_api)
    path = "/api/media-discovery/quota?user_id=9"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).json() == {
        "movie": {"limit": 5, "remaining": 0, "days": 7},
        "tv": None,
    }


def test_member_submission_uses_seerr_user_and_hides_upstream_errors(client, monkeypatch):
    from unittest.mock import Mock

    import requests

    from api.routers import media_discovery
    from core.integrations.seerr import SeerrClient

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42")
    monkeypatch.setattr(media_discovery, "_seerr_client", lambda: SeerrClient(api_key="fixture-key"))
    monkeypatch.setattr(SeerrClient, "member_user_id", lambda self, *account: 8)
    status = 201
    actor_id = 8

    def send(_self, method, url, **kwargs):
        assert kwargs["headers"]["X-API-User"] == "8"
        if method == "GET":
            assert url.endswith("/auth/me")
            return Mock(status_code=200, **{"json.return_value": {"id": actor_id}})
        assert method == "POST" and url.endswith("/request")
        assert actor_id == 8
        assert kwargs["json"] == {"mediaType": "tv", "mediaId": 44, "seasons": [1, 2]}
        return Mock(status_code=status, **{"json.return_value": {"id": 11, "requestedBy": {"id": 8}}})

    monkeypatch.setattr(requests.Session, "request", send)
    path = "/api/media-discovery/requests"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"mediaType": "tv", "mediaId": 44, "seasons": [2, 1, 1]}
    assert client.post(path, headers=headers, json={**payload, "userId": 1}).status_code == 422
    assert client.post(path, headers=headers, json=payload).json() == {"id": 11}
    status = 409
    failed = client.post(path, headers=headers, json=payload)
    assert failed.status_code == 409
    assert failed.json() == {"detail": "This title could not be requested."}
    actor_id = 1
    assert client.post(path, headers=headers, json=payload).status_code == 502


@pytest.mark.parametrize("action", ["approve", "decline"])
def test_only_admin_can_review_media_requests(client, monkeypatch, action):
    from api.routers import homepage
    from core.integrations.seerr import SeerrClient

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    member = auth_manager.issue_member_token("plex", "server-a", "42")
    admin = auth_manager.issue_token("admin")
    monkeypatch.setattr(homepage, "_seerr_client", SeerrClient)
    calls = []

    def seerr_api(_self, path, payload):
        calls.append(path)
        assert payload == {}
        return {"id": 4, "status": 2 if action == "approve" else 3}

    monkeypatch.setattr(SeerrClient, "_media_users_api", seerr_api)
    path = f"/api/homepage/requests/4/{action}"
    assert client.post(path, headers={"Authorization": f"Bearer {member}"}).status_code == 403
    assert calls == []
    assert client.post(path, headers={"Authorization": f"Bearer {admin}"}).status_code == 200
    assert calls == [f"/request/4/{action}"]


def test_recent_media_uses_member_token_and_authorized_plex_sections(client, monkeypatch):
    from unittest.mock import Mock

    import requests

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42", library_token="fixture-viewer-token")
    seen = []

    def plex_get(url, *, headers, **kwargs):
        assert headers["X-Plex-Token"] == "fixture-viewer-token"
        assert kwargs["allow_redirects"] is False
        path = url.split(":32400")[-1]
        seen.append(path)
        if path == "/identity":
            return Mock(status_code=200, text='<MediaContainer machineIdentifier="server-a" />')
        if path == "/library/sections":
            body = {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}}
        else:
            assert path == "/library/sections/1/recentlyAdded"
            body = {"MediaContainer": {"Metadata": [{"ratingKey": "3", "type": "movie", "title": "Shared", "addedAt": 1}]}}
        return Mock(status_code=200, **{"json.return_value": body})

    monkeypatch.setattr(requests, "get", plex_get)
    response = client.get("/api/media-discovery/recent", headers={"Authorization": f"Bearer {token}"})
    [item] = response.json()["items"]
    assert item == {
        "id": "3", "title": "Shared", "mediaType": "movie", "playProvider": "plex",
        "playUrl": "http://testserver:32400/web/index.html#!/server/server-a/details?key=%2Flibrary%2Fmetadata%2F3",
    }
    assert seen == ["/identity", "/library/sections", "/library/sections/1/recentlyAdded"]


def test_recent_media_queries_jellyfin_as_the_signed_in_viewer(client, monkeypatch):
    from unittest.mock import Mock

    import requests

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("jellyfin", "server-a", "42")
    token = auth_manager.issue_member_token("jellyfin", "server-a", "42", library_token="fixture-viewer-token")

    def jellyfin_get(url, *, headers, params, **kwargs):
        assert 'Token="fixture-viewer-token"' in headers["Authorization"]
        assert kwargs["allow_redirects"] is False
        if url.endswith("/System/Info/Public"):
            body = {"Id": "server-a"}
        else:
            assert url.endswith("/Items")
            assert params["UserId"] == "42"
            body = {"Items": [{"Id": "3", "Name": "Shared", "Type": "Series", "Path": "private-field"}]}
        return Mock(status_code=200, **{"json.return_value": body})

    monkeypatch.setattr(requests, "get", jellyfin_get)
    response = client.get("/api/media-discovery/recent?user_id=9", headers={"Authorization": f"Bearer {token}"})
    [item] = response.json()["items"]
    assert item == {
        "id": "3", "title": "Shared", "mediaType": "tv", "playProvider": "jellyfin",
        "playUrl": "http://testserver:8096/web/#/details?id=3",
    }


def test_member_poster_checks_jellyfin_item_access_before_fetching_image(client, monkeypatch):
    from unittest.mock import Mock

    import requests

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("jellyfin", "server-a", "42")
    token = auth_manager.issue_member_token("jellyfin", "server-a", "42", library_token="fixture-token")
    shared = "a" * 32
    private = "b" * 32
    paths = []

    def jellyfin_get(url, *, headers, params, **kwargs):
        assert 'Token="fixture-token"' in headers["Authorization"]
        assert kwargs["allow_redirects"] is False
        paths.append(url)
        if url.endswith("/System/Info/Public"):
            return Mock(status_code=200, **{"json.return_value": {"Id": "server-a"}})
        if url.endswith("/Items"):
            assert params["UserId"] == "42"
            rows = [{"Id": shared}] if params["Ids"] == shared else []
            return Mock(status_code=200, **{"json.return_value": {"Items": rows}})
        assert url.endswith(f"/Items/{shared}/Images/Primary")
        image = Mock(status_code=200, headers={"Content-Type": "image/png"})
        image.iter_content.return_value = [b"fixture-image"]
        return image

    monkeypatch.setattr(requests, "get", jellyfin_get)
    headers = {"Authorization": f"Bearer {token}"}
    root = "/api/media-discovery/recent/art"
    assert client.get(f"{root}/{shared}").status_code == 401
    result = client.get(f"{root}/{shared}", headers=headers)
    assert result.content == b"fixture-image"
    assert result.headers["cache-control"] == "private, no-store"
    assert client.get(f"{root}/{private}", headers=headers).status_code == 404
    assert all(private not in url for url in paths)


def test_member_poster_checks_plex_section_before_fetching_image(client, monkeypatch):
    from unittest.mock import Mock

    import requests

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42", library_token="fixture-token")
    section = "2"

    def plex_get(url, *, headers, **kwargs):
        assert headers["X-Plex-Token"] == "fixture-token"
        if url.endswith("/identity"):
            return Mock(status_code=200, text='<MediaContainer machineIdentifier="server-a" />')
        if url.endswith("/library/sections"):
            payload = {"Directory": [{"key": "1", "type": "movie"}]}
        elif url.endswith("/library/metadata/3"):
            payload = {"librarySectionID": section, "Metadata": [{"ratingKey": "3"}]}
        else:
            assert section == "1" and url.endswith("/library/metadata/3/thumb")
            image = Mock(status_code=200, headers={"Content-Type": "image/jpeg"})
            image.iter_content.return_value = [b"fixture-image"]
            return image
        return Mock(status_code=200, **{"json.return_value": {"MediaContainer": payload}})

    monkeypatch.setattr(requests, "get", plex_get)
    headers = {"Authorization": f"Bearer {token}"}
    path = "/api/media-discovery/recent/art/3"
    assert client.get(path, headers=headers).status_code == 404
    section = "1"
    assert client.get(path, headers=headers).content == b"fixture-image"


@pytest.mark.parametrize("provider", ["jellyfin", "plex"])
def test_movie_availability_matches_only_accessible_tmdb_ids(client, monkeypatch, provider):
    from unittest.mock import Mock

    import requests

    from api.routers import media_discovery

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant(provider, "server-a", "42")
    token = auth_manager.issue_member_token(provider, "server-a", "42", library_token="viewer-token")
    movies = [
        {"mediaType": "movie", "mediaId": 5, "title": "Shared", "status": "available"},
        {"mediaType": "movie", "mediaId": 9, "title": "Same name", "status": "available"},
    ]
    monkeypatch.setattr(media_discovery, "_seerr_search", lambda *_args: (movies, None))

    def server_get(url, *, headers, params, **kwargs):
        if provider == "jellyfin":
            assert 'Token="viewer-token"' in headers["Authorization"]
            if url.endswith("/System/Info/Public"):
                data = {"Id": "server-a"}
            else:
                assert params["UserId"] == "42"
                data = {"Items": [{"Type": "Movie", "ProviderIds": {"Tmdb": "5"}}]}
        else:
            assert headers["X-Plex-Token"] == "viewer-token"
            if url.endswith("/identity"):
                return Mock(status_code=200, text='<MediaContainer machineIdentifier="server-a" />')
            if url.endswith("/library/sections"):
                data = {"Directory": [{"key": "1", "type": "movie"}]}
            else:
                assert url.endswith("/library/sections/1/all")
                data = {"Metadata": [{"type": "movie", "Guid": [{"id": "tmdb://5"}]}]}
            data = {"MediaContainer": data}
        return Mock(status_code=200, **{"json.return_value": data})

    monkeypatch.setattr(requests, "get", server_get)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/media-discovery/search?q=film", headers=headers)
    assert response.json() == {"items": [
        {"mediaType": "movie", "mediaId": 5, "title": "Shared", "available": True},
        {"mediaType": "movie", "mediaId": 9, "title": "Same name"},
    ]}


@pytest.mark.parametrize("provider", ["jellyfin", "plex"])
def test_series_availability_requires_every_requested_season(client, monkeypatch, provider):
    from unittest.mock import Mock

    import requests

    from api.routers import media_discovery
    from core.integrations.seerr import SeerrClient

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant(provider, "server-a", "42")
    token = auth_manager.issue_member_token(provider, "server-a", "42", library_token="viewer-token")
    headers = {"Authorization": f"Bearer {token}"}
    show = {"mediaType": "tv", "mediaId": 5, "title": "Series"}
    monkeypatch.setattr(media_discovery, "_seerr_search", lambda *_: ([show], None))
    monkeypatch.setattr(media_discovery, "_seerr_client", SeerrClient)
    monkeypatch.setattr(media_discovery, "seerr_catalog_details", lambda *_: {"title": "Series"})
    monkeypatch.setattr(SeerrClient, "member_user_id", lambda *_: 8)
    rows = [{
        "id": number, "type": "tv", "requestedBy": {"id": 8}, "status": 2,
        "media": {"tmdbId": 5, "status": 5},
        "seasons": [{"seasonNumber": season} for season in seasons],
    } for number, seasons in enumerate(([1, 2], [1]), start=1)]
    monkeypatch.setattr(SeerrClient, "user_requests", lambda *_: {"results": rows, "pageInfo": {"results": 2}})
    jellyfin_id = "a" * 32

    def get(url, *, headers, params, **kwargs):
        if provider == "jellyfin":
            assert 'Token="viewer-token"' in headers["Authorization"]
            if url.endswith("/System/Info/Public"):
                data = {"Id": "server-a"}
            elif params["IncludeItemTypes"] == "Series":
                assert params["UserId"] == "42"
                data = {"Items": [{"Id": jellyfin_id, "Type": "Series", "ProviderIds": {"Tmdb": "5"}}]}
            else:
                assert params["ParentId"] == jellyfin_id and params["UserId"] == "42"
                data = {"Items": [
                    {"Type": "Episode", "ParentIndexNumber": 1},
                    {"Type": "Episode", "ParentIndexNumber": 2, "LocationType": "Virtual"},
                ]}
        else:
            assert headers["X-Plex-Token"] == "viewer-token"
            if url.endswith("/identity"):
                return Mock(status_code=200, text='<MediaContainer machineIdentifier="server-a" />')
            if url.endswith("/library/sections"):
                payload = {"Directory": [{"key": "1", "type": "show"}]}
            elif url.endswith("/library/sections/1/all"):
                payload = {"Metadata": [{"type": "show", "ratingKey": "3", "Guid": [{"id": "tmdb://5"}]}]}
            else:
                assert url.endswith("/library/metadata/3/allLeaves")
                payload = {"Metadata": [
                    {"type": "episode", "parentIndex": 1, "grandparentRatingKey": "3"},
                    {"type": "episode", "parentIndex": 2, "grandparentRatingKey": "9"},
                ]}
            data = {"MediaContainer": payload}
        return Mock(status_code=200, **{"json.return_value": data})

    monkeypatch.setattr(requests, "get", get)
    search = client.get("/api/media-discovery/search?q=series", headers=headers).json()["items"]
    assert search == [{**show, "availableSeasons": [1]}]
    own = client.get("/api/media-discovery/requests", headers=headers).json()["items"]
    assert own[0]["availableSeasons"] == [1] and "available" not in own[0]
    assert own[1]["availableSeasons"] == [1] and own[1]["available"] is True


def test_member_calendar_uses_session_account_and_token(client, monkeypatch):
    from datetime import date

    from api.routers import media_discovery

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42", library_token="calendar-token")

    def scoped_calendar(provider, server, account, credential, start, end):
        assert (provider, server, account, credential) == ("plex", "server-a", "42", "calendar-token")
        assert (start, end) == (date(2026, 11, 16), date(2026, 11, 22))
        return []

    monkeypatch.setattr(media_discovery, "member_calendar", scoped_calendar)
    path = "/api/media-discovery/calendar?start=2026-11-16&user_id=99"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.json() == {"items": []}
    assert response.headers["cache-control"] == "private, no-store"


def test_member_title_returns_catalog_metadata_only(client, monkeypatch):
    from api.routers import media_discovery

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42")

    def upstream(_host, _scheme, kind, media_id):
        assert (kind, media_id) == ("tv", 5)
        return {
            "ok": True, "title": "Series", "overview": "Synopsis",
            "trailer": "https://www.youtube.com/watch?v=abcdefghijk",
            "status": "available", "can_request": False, "url": "private-seerr-url", "voteAverage": 8.5,
        }

    monkeypatch.setattr(media_discovery, "homepage_title", upstream)
    path = "/api/media-discovery/titles/tv/5"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.json() == {
        "title": "Series", "overview": "Synopsis",
        "trailer": "https://www.youtube.com/watch?v=abcdefghijk", "voteAverage": 8.5,
    }


def test_trending_omits_complete_movies_and_series_but_keeps_incomplete_seasons(client, monkeypatch):
    from api.routers import media_discovery
    from core.integrations.seerr import SeerrClient

    auth_manager.create_admin("admin", "StrongPassword123!")
    auth_manager.media_users.grant("plex", "server-a", "42")
    token = auth_manager.issue_member_token("plex", "server-a", "42", library_token="fixture-token")
    titles = [
        {"mediaType": kind, "mediaId": media_id, "title": title}
        for kind, media_id, title in [
            ("movie", 1, "Complete film"), ("tv", 2, "Complete show"),
            ("tv", 3, "Partial show"), ("movie", 4, "Private film"),
            ("movie", 5, "Requested film"), ("tv", 6, "Requested show"),
        ]
    ]
    monkeypatch.setattr(media_discovery, "homepage_trending", lambda *args: {"items": titles})
    monkeypatch.setattr(media_discovery, "_seerr_client", SeerrClient)
    monkeypatch.setattr(SeerrClient, "request_season_counts", lambda self, media_id: {1: 2, 2: 1} if media_id == 3 else {1: 2})

    def seerr_requests(_self, path):
        assert path == "/request?take=100&skip=0&filter=all"
        rows = [
            {"type": "movie", "media": {"tmdbId": 5}, "status": 1, "requestedBy": {"id": 99}},
            {"type": "tv", "media": {"tmdbId": 6}, "status": 1, "seasons": [{"seasonNumber": 1}]},
            {"type": "tv", "media": {"tmdbId": 3}, "status": 2, "seasons": [{"seasonNumber": 2}]},
            {"type": "movie", "media": {"tmdbId": 4}, "status": 3},
        ]
        return {"results": rows, "pageInfo": {"results": len(rows)}}

    monkeypatch.setattr(SeerrClient, "_media_users_api", seerr_requests)

    def inventory(provider, server, account, library_token, requested):
        assert (provider, server, account, library_token) == ("plex", "server-a", "42", "fixture-token")
        return {("movie", 1): {}, ("tv", 2): {1: {1, 2}}, ("tv", 3): {1: {1}}}

    monkeypatch.setattr(media_discovery, "member_inventory", inventory)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/media-discovery/trending", headers=headers)
    assert response.json() == {
        "items": [{**titles[2], "availableSeasons": [1], "requestableSeasons": [1]}, titles[3]],
        "has_more": True,
    }
