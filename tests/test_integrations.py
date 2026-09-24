"""
tests/test_integrations.py — Tests for the automatic integration engine and client adapters.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.app import create_app
from core.crypto import secret_store
from core.integrations.credentials import get_application_api_key, set_application_api_key
from core.integrations.bazarr import BazarrClient
from core.integrations.hooks import (
    write_neutarr_config,
    write_profilarr_config,
    write_recyclarr_config,
)
from core.integrations.nzbget import NZBGetClient
from core.integrations.prowlarr import ProwlarrClient
from applications.qbittorrent.webui import ensure_webui_localhost_access, qbittorrent_pbkdf2
from core.integrations.qbittorrent import QBittorrentClient
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient, write_bootstrap_ini
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient
from core.integrations.engine import WIRE_AFTER_INSTALL, _register_download_clients


def test_credentials_discovery(tmp_path: Path):
    app_cfg_dir = tmp_path / "sonarr"
    app_cfg_dir.mkdir(parents=True)
    xml_file = app_cfg_dir / "config.xml"
    xml_file.write_text("<Config><ApiKey>0123456789abcdef0123456789abcdef</ApiKey></Config>", encoding="utf-8")

    key = get_application_api_key("sonarr", app_config_dir=app_cfg_dir)
    assert key == "0123456789abcdef0123456789abcdef"

    # Verify persisted in SecretStore
    assert secret_store.get_secret("sonarr_api_key") == "0123456789abcdef0123456789abcdef"

    # Test explicit set
    set_application_api_key("radarr", "fedcba9876543210fedcba9876543210")
    assert get_application_api_key("radarr") == "fedcba9876543210fedcba9876543210"


@patch("requests.get")
def test_sabnzbd_client(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"categories": ["default"]}'
    mock_resp.json.return_value = {"categories": ["default"], "status": True}
    mock_get.return_value = mock_resp

    client = SABnzbdClient(api_key="sab_key_123")
    cats = client.get_categories()
    assert "default" in cats

    mock_resp.json.return_value = {"status": True}
    ok = client.add_category("sonarr", "tv")
    assert ok is True
    assert client.add_news_server(host="news.example.com", username="nzb-user", password="secret") is True


def test_sabnzbd_bootstrap_ini_includes_usenet(tmp_path: Path):
    path = tmp_path / "sabnzbd.ini"
    written = write_bootstrap_ini(
        path,
        port=8085,
        complete_dir="/data/downloads/complete",
        incomplete_dir="/data/downloads/incomplete",
        username="admin",
        password="space pass",
        usenet={
            "host": "news.example.com",
            "port": 563,
            "ssl": True,
            "username": "nzb-user",
            "password": "p#secret",
            "connections": 20,
        },
        api_key="aabbccddeeff00112233445566778899",
    )
    text = written.read_text(encoding="utf-8")
    assert "port = 8085" in text
    assert "api_key = aabbccddeeff00112233445566778899" in text
    assert "[[news.example.com]]" in text
    assert "connections = 20" in text
    assert "ssl = 1" in text
    assert "helpful_warnings = 0" in text
    write_bootstrap_ini(path, port=1, complete_dir="x", incomplete_dir="y")
    assert "port = 8085" in path.read_text(encoding="utf-8")


def test_sabnzbd_post_install_seeds_ini_and_api_key(tmp_path: Path, monkeypatch):
    from applications.sabnzbd import SabnzbdApp
    from core.integrations.credentials import get_application_api_key

    monkeypatch.setattr(
        "core.integrations.usenet.load_usenet_server",
        lambda: {
            "host": "news.example.com",
            "port": 563,
            "ssl": True,
            "username": "nzb-user",
            "password": "nzb-secret",
            "connections": 12,
        },
    )
    monkeypatch.setattr("core.shared_credentials.shared_admin_credentials", lambda: ("admin", "shared-pass"))
    app = SabnzbdApp(base_config_dir=tmp_path / "config", base_install_dir=tmp_path / "apps")
    app.post_install()
    ini = app.config_dir / "sabnzbd.ini"
    text = ini.read_text(encoding="utf-8")
    assert "news.example.com" in text
    assert "connections = 12" in text
    assert "username = admin" in text
    key = get_application_api_key("sabnzbd", app_config_dir=app.config_dir)
    assert key
    assert len(key) >= 32
    mode = ini.stat().st_mode & 0o777
    assert mode == 0o664


@patch("requests.Session.post")
@patch("requests.Session.get")
def test_qbittorrent_client(mock_get, mock_post):
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.text = "Ok."
    mock_post_resp.headers = {}
    mock_post.return_value = mock_post_resp

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {}
    mock_get.return_value = mock_get_resp

    client = QBittorrentClient()
    assert client.login() is True
    assert client.create_category("sonarr", "/downloads/torrents/tv") is True


@patch("requests.get")
@patch("requests.post")
def test_sonarr_client(mock_post, mock_get):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = []
    mock_get.return_value = mock_get_resp

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post.return_value = mock_post_resp

    client = SonarrClient(api_key="sonarr_key_123")
    assert client.add_root_folder("/data/media/tv") is True
    assert client.add_sabnzbd_client(api_key="sab_key") is True
    assert client.add_qbittorrent_client() is True
    assert client.add_nzbget_client() is True


@patch("requests.get")
@patch("requests.put")
def test_sonarr_naming_uses_servarr_tokens(mock_put, mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"id": 1}
    mock_put.return_value.status_code = 202

    assert SonarrClient(api_key="k").configure_naming_defaults() is True
    payload = mock_put.call_args.kwargs["json"]
    assert "{season:00}" in payload["standardEpisodeFormat"]
    assert "{episode:00}" in payload["standardEpisodeFormat"]
    assert "{season:02d}" not in payload["standardEpisodeFormat"]


def test_register_download_clients_skips_clients_that_are_not_ready():
    called: list[str] = []
    assert (
        _register_download_clients(
            ["qbittorrent"],
            add_sab=lambda: called.append("sab") or True,
            add_nzb=lambda: called.append("nzb") or True,
            add_qb=lambda: called.append("qb") or True,
        )
        is True
    )
    assert called == ["qb"]
    assert _register_download_clients([], add_sab=lambda: False, add_nzb=lambda: False, add_qb=lambda: False) is True


def test_qbittorrent_profile_bypasses_localhost_auth(tmp_path: Path):
    conf = ensure_webui_localhost_access(tmp_path)
    text = conf.read_text(encoding="utf-8")
    assert "WebUI\\LocalHostAuth=false" in text
    assert "127.0.0.0/8" in text


def test_qbittorrent_profile_seeds_shared_webui_password(tmp_path: Path):
    conf = ensure_webui_localhost_access(tmp_path, username="amm", password="SharedPass123!")
    text = conf.read_text(encoding="utf-8")
    assert "WebUI\\Username=amm" in text
    assert "WebUI\\Password_PBKDF2=" in text
    hashed = qbittorrent_pbkdf2("SharedPass123!", salt=b"0123456789abcdef")
    assert hashed.startswith('"@ByteArray(')
    first = next(line for line in text.splitlines() if line.startswith("WebUI\\Password_PBKDF2="))
    ensure_webui_localhost_access(tmp_path, username="amm", password="OtherPass123!")
    second = next(
        line
        for line in conf.read_text(encoding="utf-8").splitlines()
        if line.startswith("WebUI\\Password_PBKDF2=")
    )
    assert first != second


@patch("requests.get")
@patch("requests.post")
def test_radarr_client(mock_post, mock_get):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = []
    mock_get.return_value = mock_get_resp

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post.return_value = mock_post_resp

    client = RadarrClient(api_key="radarr_key_123")
    assert client.add_root_folder("/data/media/movies") is True
    assert client.add_sabnzbd_client(api_key="sab_key") is True
    assert client.add_qbittorrent_client() is True
    assert client.add_nzbget_client() is True


@patch("requests.get")
@patch("requests.post")
def test_prowlarr_client(mock_post, mock_get):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = []
    mock_get.return_value = mock_get_resp

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post.return_value = mock_post_resp

    client = ProwlarrClient(api_key="prowlarr_key_123")
    assert client.sync_sonarr(sonarr_api_key="sonarr_key") is True
    assert client.sync_radarr(radarr_api_key="radarr_key") is True
    assert client.sync_lidarr(lidarr_api_key="lidarr_key") is True
    assert client.add_flaresolverr() is True


@patch("requests.get")
@patch("requests.post")
def test_seerr_client(mock_post, mock_get):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = []
    mock_get.return_value = mock_get_resp

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post.return_value = mock_post_resp

    client = SeerrClient(api_key="seerr_key_123")
    assert client.connect_sonarr(api_key="sonarr_key") is True
    assert client.connect_radarr(api_key="radarr_key") is True
    assert client.connect_jellyfin(api_key="jelly_key") is True
    assert client.connect_plex(port=32400) is True
    assert client.setup_local_admin("admin@example.com", "admin", "SharedPass123!") is True


def test_integration_endpoints():
    app = create_app()
    client = TestClient(app)

    # Status
    res_status = client.get("/api/integrations/status")
    assert res_status.status_code == 200
    assert "integrations" in res_status.json()

    # Run wiring
    res_run = client.post("/api/integrations/run")
    assert res_run.status_code == 200
    data = res_run.json()
    assert data["status"] == "completed"
    assert len(data["steps"]) >= 4
    targets = {step["target"] for step in data["steps"]}
    assert {"storage", "seerr", "bazarr", "recyclarr", "nzbget", "jellyfin", "lidarr"}.issubset(targets)
    skipped = {step["target"] for step in data["steps"] if step["status"] == "skipped"}
    assert "lidarr" in skipped
    assert "whisparr" not in targets
    assert "readarr" not in targets
    assert "libraries" in data["layout"]
    assert "tv" in data["layout"]["libraries"]
    assert "books" in data["layout"]["libraries"]
    assert "incomplete" in data["layout"]


def test_arr_install_triggers_wiring_set():
    assert {"sonarr", "radarr", "lidarr", "prowlarr", "seerr", "sabnzbd"}.issubset(WIRE_AFTER_INSTALL)
    assert "whisparr" not in WIRE_AFTER_INSTALL
    assert "readarr" not in WIRE_AFTER_INSTALL


@patch("requests.post")
def test_nzbget_client(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": []}
    mock_post.return_value = mock_resp
    client = NZBGetClient()
    assert client.add_category("sonarr", "tv") is True
    assert client.add_news_server(host="news.example.com", username="nzb-user", password="secret") is True


@patch("requests.post")
def test_bazarr_client(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_post.return_value = mock_resp
    client = BazarrClient(api_key="baz")
    assert client.pair_sonarr("http://127.0.0.1:8989", "sonarr") is True
    assert client.pair_radarr("http://127.0.0.1:7878", "radarr") is True


@patch("requests.post")
def test_bazarr_set_ui_auth_sends_plaintext_and_hashes_yaml(mock_post, tmp_path: Path):
    from core.integrations.local_auth import sha256_hex

    mock_post.return_value = MagicMock(status_code=201)
    client = BazarrClient(api_key="baz")
    assert client.set_ui_auth("amm", "SharedPass123!", tmp_path) is True
    payload = mock_post.call_args.kwargs["json"]
    assert payload["auth"]["username"] == "amm"
    assert payload["auth"]["password"] == "SharedPass123!"
    yaml_text = (tmp_path / "config" / "config.yaml").read_text(encoding="utf-8")
    assert "type: form" in yaml_text
    assert sha256_hex("SharedPass123!") in yaml_text


def test_optimization_hooks(tmp_path: Path):
    rec = write_recyclarr_config(
        tmp_path / "recyclarr",
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="s",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="r",
    )
    assert rec.is_file()
    rec_text = rec.read_text(encoding="utf-8")
    assert "base_url: http://127.0.0.1:8989" in rec_text
    assert "trash_id: 72dae194fc92bf828f32cde7744e51a1" in rec_text
    assert "trash_id: d1d67249d3890e49bc12e275d989a7e9" in rec_text
    assert "plex-tv" in rec_text
    pro = write_profilarr_config(
        tmp_path / "profilarr",
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="s",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="r",
        lidarr_url="http://127.0.0.1:8686",
        lidarr_key="l",
    )
    assert pro.is_file()
    pro_text = pro.read_text(encoding="utf-8")
    assert "base_url: \"http://127.0.0.1:8989\"" in pro_text
    assert "Lidarr (AMM)" in pro_text
    assert "backup_before_sync: true" in pro_text
    neu = write_neutarr_config(
        tmp_path / "neutarr",
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="s",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="r",
        lidarr_url="http://127.0.0.1:8686",
        lidarr_key="l",
    )
    assert neu.is_file()
    sonarr_hunt = (tmp_path / "neutarr" / "sonarr.json").read_text(encoding="utf-8")
    assert "hourly_cap" in sonarr_hunt
    assert "http://127.0.0.1:8989" in sonarr_hunt
    assert (tmp_path / "neutarr" / "lidarr.json").is_file()
