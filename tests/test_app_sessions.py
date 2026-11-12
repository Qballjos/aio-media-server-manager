"""Sign the shared admin in to catalog apps and hand the browser their session cookies."""

from unittest.mock import MagicMock

import requests
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import applications as applications_router
from core.integrations import sessions
from core.settings import settings


def _http(cookie_name: str | None):
    http = MagicMock()
    http.cookies = requests.cookies.RequestsCookieJar()

    def post(url, **kwargs):
        if cookie_name:
            http.cookies.set(cookie_name, "value", path="/")
        resp = MagicMock()
        resp.status_code = 302
        return resp

    http.post.side_effect = post
    return http


def test_servarr_login_posts_the_form_and_returns_the_auth_cookie(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: ("admin", "pw"))
    http = _http("SonarrAuth")
    jar = sessions.app_session_cookies("sonarr", 8989, http=http)
    assert [cookie.name for cookie in jar] == ["SonarrAuth"]
    url, kwargs = http.post.call_args.args[0], http.post.call_args.kwargs
    assert url == "http://127.0.0.1:8989/login"
    assert kwargs["data"] == {"username": "admin", "password": "pw", "rememberMe": "on"}
    assert kwargs["allow_redirects"] is False


def test_qbittorrent_login_uses_the_webapi(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: ("admin", "pw"))
    http = _http("SID")
    jar = sessions.app_session_cookies("qbittorrent", 8081, http=http)
    assert [cookie.name for cookie in jar] == ["SID"]
    url, kwargs = http.post.call_args.args[0], http.post.call_args.kwargs
    assert url == "http://127.0.0.1:8081/api/v2/auth/login"
    assert kwargs["data"] == {"username": "admin", "password": "pw"}


def test_bazarr_login_uses_the_account_action(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: ("admin", "pw"))
    http = _http("session")
    jar = sessions.app_session_cookies("bazarr", 6767, http=http)
    assert [cookie.name for cookie in jar] == ["session"]
    url, kwargs = http.post.call_args.args[0], http.post.call_args.kwargs
    assert url == "http://127.0.0.1:6767/api/system/account"
    assert kwargs["params"] == {"action": "login"}
    assert kwargs["data"] == {"username": "admin", "password": "pw"}


def test_sabnzbd_login_remembers_the_session(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: ("admin", "pw"))
    http = _http("sabnzbd_user")
    jar = sessions.app_session_cookies("sabnzbd", 8085, http=http)
    assert [cookie.name for cookie in jar] == ["sabnzbd_user"]
    url, kwargs = http.post.call_args.args[0], http.post.call_args.kwargs
    assert url == "http://127.0.0.1:8085/sabnzbd/login"
    assert kwargs["data"] == {"username": "admin", "password": "pw", "remember_me": "1"}


def test_failed_login_hands_back_nothing(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: ("admin", "pw"))
    assert sessions.app_session_cookies("radarr", 7878, http=_http(None)) is None


def test_apps_without_a_cookie_login_are_skipped(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: ("admin", "pw"))
    for name in ("jellyfin", "plex", "nzbget", "recyclarr"):
        http = _http("whatever")
        assert sessions.app_session_cookies(name, 1234, http=http) is None
        http.post.assert_not_called()


def test_missing_shared_credentials_skip_the_login(monkeypatch):
    monkeypatch.setattr(sessions, "shared_admin_credentials", lambda: None)
    http = _http("SonarrAuth")
    assert sessions.app_session_cookies("sonarr", 8989, http=http) is None
    http.post.assert_not_called()


def test_session_endpoint_sets_the_app_cookie_and_returns_its_url(monkeypatch):
    jar = requests.cookies.RequestsCookieJar()
    jar.set("SonarrAuth", "abc", path="/")
    monkeypatch.setattr(applications_router, "app_session_cookies", lambda *a, **k: jar)
    monkeypatch.setattr(settings, "public_app_base_domain", "")
    client = TestClient(create_app())
    res = client.post("/api/applications/sonarr/session")
    assert res.status_code == 200
    assert res.json() == {"url": "http://testserver:8989", "signed_in": True}
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("SonarrAuth=abc")
    assert "HttpOnly" in cookie and "Path=/" in cookie


def test_session_endpoint_rejects_unknown_apps():
    client = TestClient(create_app())
    assert client.post("/api/applications/nope/session").status_code == 404


def test_cleanuparr_session_requires_auth_and_never_returns_api_keys(monkeypatch):
    from core.integrations.cleanuparr import CleanuparrClient
    from core.shared_credentials import save_shared_admin_credentials
    from fastapi import HTTPException

    client = TestClient(create_app())
    monkeypatch.setattr(applications_router.auth_manager, "authenticate_request",
                        lambda request: (_ for _ in ()).throw(HTTPException(status_code=401)))
    assert client.post("/api/applications/cleanuparr/session").status_code == 401
    monkeypatch.setattr(applications_router.auth_manager, "authenticate_request", lambda request: "admin")
    plugin = applications_router.catalog.get("cleanuparr")
    monkeypatch.setattr(plugin, "prepare_browser_login", lambda: True)
    save_shared_admin_credentials("admin", "Password123!")
    monkeypatch.setattr(CleanuparrClient, "login", lambda self, *args: {"accessToken": "session", "refreshToken": "refresh"})
    result = client.post("/api/applications/cleanuparr/session")
    assert result.status_code == 200
    assert result.json()["handoff"] == "cleanuparr-session"
    assert result.json()["url"] == "http://testserver:11011/aio-login.html"
    assert result.headers["cache-control"] == "no-store"
    assert "Password123" not in result.text and "api_key" not in result.text


def test_cleanuparr_public_url_keeps_its_own_login(monkeypatch):
    from core.integrations.cleanuparr import CleanuparrClient
    monkeypatch.setattr(applications_router.auth_manager, "authenticate_request", lambda request: "admin")
    monkeypatch.setattr(applications_router, "app_web_ui_url_for_request", lambda *args, **kwargs: "https://cleanuparr.example.com")
    monkeypatch.setattr(CleanuparrClient, "login", lambda *args: pytest.fail("Public URL must not receive a shared session"))
    result = TestClient(create_app()).post("/api/applications/cleanuparr/session")
    assert result.json() == {"url": "https://cleanuparr.example.com", "signed_in": False}


def test_cleanuparr_two_factor_login_keeps_the_manual_login(monkeypatch):
    from core.integrations.cleanuparr import CleanuparrClient, CleanuparrError
    from core.shared_credentials import save_shared_admin_credentials
    monkeypatch.setattr(applications_router.auth_manager, "authenticate_request", lambda request: "admin")
    monkeypatch.setattr(applications_router.catalog.get("cleanuparr"), "prepare_browser_login", lambda: True)
    save_shared_admin_credentials("admin", "Password123!")
    def requires_two_factor(*args):
        raise CleanuparrError("Two-factor sign-in required")
    monkeypatch.setattr(CleanuparrClient, "login", requires_two_factor)
    result = TestClient(create_app()).post("/api/applications/cleanuparr/session")
    assert result.status_code == 200
    assert result.json()["signed_in"] is False
    assert "tokens" not in result.json()
    assert result.json()["url"] == "http://testserver:11011"
