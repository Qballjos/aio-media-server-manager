"""
tests/test_integrations.py — Tests for the automatic integration engine and client adapters.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.crypto import secret_store
from core.integrations.credentials import get_application_api_key, set_application_api_key
from core.integrations.engine import IntegrationEngine
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.qbittorrent import QBittorrentClient
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient


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
    assert client.create_category("sonarr", "/data/downloads/torrents/tv") is True


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
