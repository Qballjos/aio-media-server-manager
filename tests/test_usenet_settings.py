"""Usenet provider and NZB indexer settings after the first run."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import usenet as usenet_router
from core.integrations import usenet
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
    assert "indexers" not in overview  # NZB indexers are added by hand in Prowlarr


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


def test_settings_take_over_the_server_sabnzbd_already_has(monkeypatch, tmp_path):
    (tmp_path / "sabnzbd.ini").write_text(
        "[misc]\nusername = admin\npassword = adminpw\n"
        "[servers]\n[[host]]\nhost = \"\"\n"
        "[[Eweka]]\nenable = 1\nhost = news.eweka.nl\nport = 563\nusername = me\n"
        "password = 'p#ss\"word'\nconnections = 16\nssl = 1\n"
        "[categories]\n[[tv]]\nname = tv\n",
        encoding="utf-8",
    )
    secrets = _Secrets()
    monkeypatch.setattr(usenet, "secret_store", secrets)
    plugin = SimpleNamespace(config_dir=tmp_path, is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: name == "sabnzbd", get=lambda name: plugin)
    with patch("applications.catalog.ApplicationCatalog", return_value=catalog):
        assert usenet.import_usenet_server() == "sabnzbd"
        assert usenet.import_usenet_server() == ""  # once AIO has a server it stays in charge
    assert usenet.load_usenet_server() == {
        "host": "news.eweka.nl", "port": 563, "ssl": True, "username": "me",
        "password": 'p#ss"word', "connections": 16,
    }


def test_nzbget_template_placeholder_is_not_taken_over(tmp_path):
    from core.integrations.nzbget import read_nzbget_conf_server

    conf = tmp_path / "nzbget.conf"
    conf.write_text("Server1.Active=yes\nServer1.Host=my.newsserver.com\nServer1.Password=pass\n", encoding="utf-8")
    assert read_nzbget_conf_server(conf) is None
    conf.write_text("Server1.Active=yes\nServer1.Host=news.eweka.nl\nServer1.Port=563\nServer1.Username=me\n"
                    "Server1.Password=pw\nServer1.Encryption=yes\nServer1.Connections=16\n", encoding="utf-8")
    assert read_nzbget_conf_server(conf) == {
        "host": "news.eweka.nl", "port": 563, "ssl": True, "username": "me", "password": "pw", "connections": 16,
    }
