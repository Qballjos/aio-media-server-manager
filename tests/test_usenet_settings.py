"""Usenet provider and NZB indexer settings after the first run."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import usenet as usenet_router
from core.integrations import usenet
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.sabnzbd import SABnzbdClient


class _Secrets(dict):
    def save_secret(self, name, value):
        self[name] = value

    def get_secret(self, name, default=None):
        return self.get(name, default)


def _resp(status, payload=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    resp.text = text
    return resp


def test_api_hides_the_password_and_keeps_it_when_left_blank(monkeypatch):
    secrets = _Secrets()
    monkeypatch.setattr(usenet, "secret_store", secrets)
    pushed = []
    monkeypatch.setattr(usenet_router, "push_usenet_server", lambda previous_host="": pushed.append(previous_host) or {"sabnzbd": True})
    monkeypatch.setattr(usenet_router, "_usenet_clients", lambda: ["sabnzbd"])
    monkeypatch.setattr(usenet_router, "_prowlarr_usenet_indexers", lambda: None)
    client = TestClient(create_app())

    first = client.put("/api/usenet/server", json={"host": "news.example.net", "port": 563, "ssl": True,
                                                    "username": "me", "password": "s3cret", "connections": 20})
    assert first.status_code == 200
    assert first.json()["applied"] == {"sabnzbd": True}
    assert "password" not in first.json()["server"]
    assert first.json()["server"]["has_password"] is True

    second = client.put("/api/usenet/server", json={"host": "eu.example.net", "port": 563, "ssl": True,
                                                     "username": "me", "connections": 20})
    assert second.status_code == 200
    assert usenet.load_usenet_server()["password"] == "s3cret"
    assert usenet.load_usenet_server()["host"] == "eu.example.net"
    assert pushed == ["", "news.example.net"]  # the old host is handed over so it can be replaced

    overview = client.get("/api/usenet").json()
    assert overview["server"]["host"] == "eu.example.net"
    assert "password" not in overview["server"]
    assert overview["clients"] == ["sabnzbd"]


def test_push_replaces_the_previous_server_in_sabnzbd(monkeypatch):
    secrets = _Secrets()
    monkeypatch.setattr(usenet, "secret_store", secrets)
    usenet.save_usenet_server(host="eu.example.net", port=563, ssl=True, username="me", password="pw", connections=10)
    calls = []

    class FakeSab:
        def __init__(self, port, api_key):
            calls.append(("init", port, api_key))

        def remove_news_server(self, host):
            calls.append(("remove", host))
            return True

        def add_news_server(self, **kwargs):
            calls.append(("add", kwargs["host"], kwargs.get("update")))
            return True

    plugin = SimpleNamespace(port=8085, config_dir="/config/sabnzbd", is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: name == "sabnzbd", get=lambda name: plugin)
    supervisor = SimpleNamespace(status=lambda name: SimpleNamespace(value="running"))
    with (
        patch("applications.catalog.ApplicationCatalog", return_value=catalog),
        patch("core.supervisor.ProcessSupervisor.get", return_value=supervisor),
        patch("core.integrations.sabnzbd.SABnzbdClient", FakeSab),
        patch("core.integrations.credentials.get_application_api_key", return_value="sabkey"),
    ):
        applied = usenet.push_usenet_server(previous_host="news.example.net")
    assert applied == {"sabnzbd": True}
    assert calls == [("init", 8085, "sabkey"), ("remove", "news.example.net"), ("add", "eu.example.net", True)]


def test_sabnzbd_update_rewrites_an_existing_server():
    client = SABnzbdClient(api_key="k")
    sent = []

    def fake_request(mode, extra=None):
        sent.append((mode, dict(extra or {})))
        if mode == "get_config":
            return {"config": {"servers": [{"name": "news.example.net", "host": "news.example.net"}]}}
        return {"status": True}

    client._request = fake_request
    assert client.add_news_server(host="news.example.net", password="new", update=True) is True
    writes = [extra for mode, extra in sent if mode == "set_config"]
    assert writes and writes[-1]["password"] == "new"
    # Without update an existing server is left as it is.
    sent.clear()
    assert client.add_news_server(host="news.example.net", password="new") is True
    assert not [mode for mode, _ in sent if mode == "set_config"]


@patch("requests.post")
@patch("requests.get")
def test_add_newznab_indexer_uses_the_generic_definition(mock_get, mock_post):
    template = {
        "name": "Generic Newznab", "implementation": "Newznab", "configContract": "NewznabSettings",
        "protocol": "usenet", "privacy": "private", "enable": True, "appProfileId": 0, "priority": 25,
        "tags": [], "indexerUrls": [""], "presets": [{"name": "x"}],
        "fields": [{"name": "baseUrl", "value": ""}, {"name": "apiPath", "value": "/api"},
                   {"name": "apiKey", "value": None}, {"name": "vipExpiration", "value": ""}],
    }

    def get(url, **kwargs):
        if url.endswith("/indexer/schema"):
            return _resp(200, [template])
        if url.endswith("/indexer"):
            return _resp(200, [])
        return _resp(404, [])

    mock_get.side_effect = get
    mock_post.return_value = _resp(201, {"id": 7})
    ok, detail = ProwlarrClient(api_key="k").add_newznab_indexer(
        name="", url="https://www.usenet-crawler.com/api/", api_key="abc123"
    )
    assert ok is True
    body = mock_post.call_args.kwargs["json"]
    fields = {field["name"]: field["value"] for field in body["fields"]}
    assert body["name"] == "usenet-crawler.com"
    assert body["enable"] is True and body["appProfileId"] == 1
    assert "presets" not in body
    assert fields["baseUrl"] == "https://www.usenet-crawler.com"
    assert fields["apiPath"] == "/api"
    assert fields["apiKey"] == "abc123"


@patch("requests.post")
@patch("requests.get")
def test_add_newznab_indexer_reports_prowlarrs_reason(mock_get, mock_post):
    template = {"name": "Generic Newznab", "protocol": "usenet", "fields": [{"name": "baseUrl"}, {"name": "apiPath", "value": "/api"}, {"name": "apiKey"}]}
    mock_get.side_effect = lambda url, **kw: _resp(200, [template] if url.endswith("/schema") else [])
    mock_post.return_value = _resp(400, text='[{"propertyName":"ApiKey","errorMessage":"Invalid API key"}]')
    ok, detail = ProwlarrClient(api_key="k").add_newznab_indexer(name="Crawler", url="https://x.example", api_key="bad")
    assert ok is False
    assert detail == "Invalid API key"
