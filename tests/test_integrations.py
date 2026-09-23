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
    write_unpackerr_config,
)
from core.integrations.nzbget import NZBGetClient
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.qbittorrent import QBittorrentClient
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient
from core.integrations.engine import WIRE_AFTER_INSTALL


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
    assert WIRE_AFTER_INSTALL == frozenset({"sonarr", "radarr", "lidarr", "prowlarr", "flaresolverr"})
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


@patch("requests.post")
def test_bazarr_client(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_post.return_value = mock_resp
    client = BazarrClient(api_key="baz")
    assert client.pair_sonarr("http://127.0.0.1:8989", "sonarr") is True
    assert client.pair_radarr("http://127.0.0.1:7878", "radarr") is True


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
    unpack = write_unpackerr_config(
        tmp_path / "unpackerr",
        complete_paths=["/downloads/complete/tv", "/downloads/complete/movies"],
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="s",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="r",
    )
    assert unpack.is_file()
    text = unpack.read_text(encoding="utf-8")
    assert "/downloads/complete/tv" in text
    assert "[[sonarr]]" in text
