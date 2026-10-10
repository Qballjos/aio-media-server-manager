from unittest.mock import MagicMock

import requests
from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import applications as router
from applications.jellyfin import JellyfinApp
from core.auth import AuthManager
from core.integrations.jellyfin import JellyfinClient
from core.settings import Settings


def test_helper_is_copied_for_existing_install_and_refreshed_idempotently(tmp_path):
    app = JellyfinApp(base_config_dir=tmp_path / "config", base_install_dir=tmp_path / "apps")
    assert app.prepare_browser_login() is False
    web = app.install_dir / "jellyfin-web"
    web.mkdir(parents=True)
    assert app.prepare_browser_login() is True
    html = web / "aio-login.html"
    assert 'src="aio-login.js"' in html.read_text()
    before = html.stat().st_mtime_ns
    app.prepare_browser_login()
    assert html.stat().st_mtime_ns == before
    (web / "aio-login.js").write_text("old helper")
    app.prepare_browser_login()
    assert "AuthenticateWithQuickConnect" in (web / "aio-login.js").read_text()


def test_jellyfin_session_prepares_helper_without_returning_credentials(monkeypatch):
    plugin = MagicMock(name="plugin")
    plugin.name, plugin.port = "jellyfin", 8096
    plugin.prepare_browser_login.return_value = True
    monkeypatch.setattr(router.catalog, "get", lambda name: plugin)
    monkeypatch.setattr(router, "_ensure_authenticated", lambda request: None)
    monkeypatch.setattr(router, "app_web_ui_url_for_request", lambda *a, **k: "https://jellyfin.example.com")
    client = TestClient(create_app())
    response = client.post("/api/applications/jellyfin/session")
    assert response.json() == {
        "url": "https://jellyfin.example.com/web/aio-login.html",
        "signed_in": False,
        "handoff": "jellyfin-quick-connect",
    }
    assert "set-cookie" not in response.headers
    plugin.prepare_browser_login.assert_called_once()
    plugin.prepare_browser_login.side_effect = OSError("read-only installation")
    response = client.post("/api/applications/jellyfin/session")
    assert response.json()["url"] == "https://jellyfin.example.com"
    assert "handoff" not in response.json()


def test_quick_connect_requires_auth_and_csrf_and_only_accepts_code(tmp_path, monkeypatch):
    auth = AuthManager(Settings(config_dir=tmp_path))
    monkeypatch.setattr(router, "auth_manager", auth)
    monkeypatch.setattr(router, "shared_admin_credentials", lambda: ("admin", "password"))
    jellyfin = MagicMock()
    jellyfin.authenticate.return_value = "server-only-token"
    jellyfin.authorize_quick_connect.return_value = True
    monkeypatch.setattr(router, "JellyfinClient", lambda **kwargs: jellyfin)
    client = TestClient(create_app())
    endpoint = "/api/applications/jellyfin/quick-connect"
    assert client.post(endpoint, json={"code": "123456"}).status_code == 401
    client.cookies.set("amm_access", auth.issue_token("admin"))
    assert client.post(endpoint, json={"code": "123456"}).status_code == 403
    jellyfin.authenticate.assert_not_called()
    client.cookies.set("amm_csrf", "csrf")
    headers = {"X-CSRF-Token": "csrf"}
    response = client.post(endpoint, json={"code": "123456"}, headers=headers)
    assert response.json() == {"authorized": True}
    jellyfin.authenticate.assert_called_once_with("admin", "password")
    jellyfin.authorize_quick_connect.assert_called_once_with("123456")
    assert client.post(endpoint, json={"code": "123456\n"}, headers=headers).status_code == 422
    assert client.post(endpoint, json={"code": "wrong-code"}, headers=headers).status_code == 422
    jellyfin.authorize_quick_connect.return_value = False
    response = client.post(endpoint, json={"code": "123456"}, headers=headers)
    assert response.status_code == 502
    assert "server-only-token" not in response.text


def test_quick_connect_authorization_uses_header_token_and_handles_disabled(monkeypatch):
    post = MagicMock()
    monkeypatch.setattr("core.integrations.jellyfin.requests.post", post)
    client = JellyfinClient(port=9999, api_key="secret")
    post.return_value.status_code = 200
    post.return_value.json.return_value = True
    assert client.authorize_quick_connect("123456") is True
    assert post.call_args.args[0] == "http://127.0.0.1:9999/QuickConnect/Authorize"
    assert post.call_args.kwargs["params"] == {"Code": "123456"}
    assert 'Token="secret"' in post.call_args.kwargs["headers"]["Authorization"]
    post.return_value.status_code = 401
    assert client.authorize_quick_connect("123456") is False
    post.side_effect = requests.ConnectionError("offline")
    assert client.authorize_quick_connect("123456") is False
    post.reset_mock()
    assert client.authorize_quick_connect("bad") is False
    post.assert_not_called()
