"""Seerr first-run automation and the Open UI login handoff."""

from unittest.mock import MagicMock

import requests
from fastapi.testclient import TestClient

from api.app import create_app
from core.integrations import seerr as seerr_mod
from core.integrations.seerr import SeerrClient
from core.settings import settings


def _resp(status: int, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    return resp


def _client() -> SeerrClient:
    http = MagicMock()
    http.cookies = requests.cookies.RequestsCookieJar()
    return SeerrClient(http=http)


def test_login_tries_plain_jellyfin_signin_first():
    client = _client()
    client.http.post.return_value = _resp(200, {"id": 1})
    assert client.login("admin", "pw", email="a@b.c", jellyfin_port=8096) is True
    assert client.logged_in is True
    url, kwargs = client.http.post.call_args.args[0], client.http.post.call_args.kwargs
    assert url.endswith("/auth/jellyfin")
    assert kwargs["json"] == {"username": "admin", "password": "pw"}


def test_login_falls_back_to_first_run_jellyfin_setup():
    client = _client()
    client.http.post.side_effect = [
        _resp(400, {"error": "No hostname provided."}),
        _resp(200, {"id": 1}),
    ]
    assert client.login("admin", "pw", email="a@b.c", jellyfin_port=8096) is True
    body = client.http.post.call_args.kwargs["json"]
    assert body["hostname"] == "127.0.0.1"
    assert body["port"] == 8096
    assert body["serverType"] == 2
    assert body["email"] == "a@b.c"
    assert body["username"] == "admin"


def test_login_uses_plex_token_when_jellyfin_fails():
    client = _client()
    client.http.post.side_effect = [_resp(403), _resp(200, {"id": 1})]
    assert client.login("admin", "pw", plex_token="tok") is True
    url = client.http.post.call_args.args[0]
    assert url.endswith("/auth/plex")
    assert client.http.post.call_args.kwargs["json"] == {"authToken": "tok"}
    assert client.media_server == "plex"


def test_login_failure_leaves_client_signed_out():
    client = _client()
    client.http.post.return_value = _resp(403)
    assert client.login("admin", "pw") is False
    assert client.logged_in is False


def test_enable_all_libraries_puts_each_library():
    client = _client()
    client.http.post.return_value = _resp(
        200, [{"id": "a", "name": "Movies", "enabled": False}, {"id": "b", "name": "TV", "enabled": True}]
    )
    client.http.put.return_value = _resp(200)
    assert client.enable_all_libraries("jellyfin") is True
    sync_url = client.http.post.call_args.args[0]
    assert sync_url.endswith("/settings/jellyfin/library/sync")
    put_urls = [call.args[0] for call in client.http.put.call_args_list]
    assert put_urls == [
        client.base_url + "/settings/jellyfin/library/a",
        client.base_url + "/settings/jellyfin/library/b",
    ]
    assert all(call.kwargs["json"] == {"enabled": True} for call in client.http.put.call_args_list)


def test_initialize_marks_seerr_setup_complete():
    client = _client()
    client.http.post.return_value = _resp(200, {"initialized": True})
    assert client.initialize() is True
    assert client.http.post.call_args.args[0].endswith("/settings/initialize")


def test_connect_sonarr_and_radarr_send_required_fields():
    client = _client()
    client.http.get.return_value = _resp(200, [])
    client.http.post.return_value = _resp(201)
    assert client.connect_sonarr(api_key="k") is True
    assert client.http.post.call_args.kwargs["json"]["enableSeasonFolders"] is True
    assert client.connect_radarr(api_key="k") is True
    assert client.http.post.call_args.kwargs["json"]["minimumAvailability"] == "released"


def test_api_key_header_dropped_once_signed_in():
    client = _client()
    client.api_key = "key"
    assert client._headers()["X-Api-Key"] == "key"
    client.http.post.return_value = _resp(200, {"id": 1})
    client.login("admin", "pw")
    assert "X-Api-Key" not in client._headers()


def _fake_login(self, *args, **kwargs):
    self.http.cookies.set("connect.sid", "s%3Aabc.def", path="/")
    self.logged_in = True
    return True


def test_seerr_session_hands_cookie_to_browser_and_returns_url(monkeypatch):
    monkeypatch.setattr(seerr_mod, "shared_admin_credentials", lambda: ("admin", "pw"))
    monkeypatch.setattr(seerr_mod, "admin_email", lambda: "a@b.c")
    monkeypatch.setattr(SeerrClient, "login", _fake_login)
    monkeypatch.setattr(settings, "public_app_base_domain", "")
    client = TestClient(create_app())
    res = client.post("/api/applications/seerr/session")
    assert res.status_code == 200
    assert res.json() == {"url": "http://testserver:5055", "signed_in": True}
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("connect.sid=s%3Aabc.def")
    assert "Path=/" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_seerr_session_without_cookie_on_public_domain(monkeypatch):
    monkeypatch.setattr(seerr_mod, "shared_admin_credentials", lambda: ("admin", "pw"))
    monkeypatch.setattr(SeerrClient, "login", _fake_login)
    monkeypatch.setattr(settings, "public_app_base_domain", "example.com")
    client = TestClient(create_app())
    res = client.post("/api/applications/seerr/session")
    assert res.status_code == 200
    assert res.json() == {"url": "https://seerr.example.com", "signed_in": False}
    assert "set-cookie" not in res.headers


def test_seerr_session_without_cookie_when_login_fails(monkeypatch):
    monkeypatch.setattr(seerr_mod, "shared_admin_credentials", lambda: None)
    monkeypatch.setattr(settings, "public_app_base_domain", "")
    client = TestClient(create_app())
    res = client.post("/api/applications/seerr/session")
    assert res.status_code == 200
    assert res.json()["signed_in"] is False
    assert "set-cookie" not in res.headers
