from pathlib import Path
import json
from unittest.mock import MagicMock, patch

from core.crypto import SecretStore
from core.integrations.local_auth import (
    patch_bazarr_auth_yaml,
    set_neutarr_login,
    set_profilarr_login,
    set_servarr_forms_auth,
    sha256_hex,
)
from core.shared_credentials import save_shared_admin_credentials, shared_admin_credentials
from core.integrations.qbittorrent import apply_qbittorrent_webui_login, target_webui_credentials


def test_save_and_read_shared_admin_credentials(tmp_path: Path, monkeypatch):
    store = SecretStore(key_path=tmp_path / "secret.key", storage_path=tmp_path / "secrets.enc")
    monkeypatch.setattr("core.shared_credentials.secret_store", store)
    assert shared_admin_credentials() is None
    save_shared_admin_credentials("amm", "SharedPass123!")
    assert shared_admin_credentials() == ("amm", "SharedPass123!")


def test_qbittorrent_credentials_follow_manager_login(tmp_path: Path, monkeypatch):
    store = SecretStore(key_path=tmp_path / "secret.key", storage_path=tmp_path / "secrets.enc")
    monkeypatch.setattr("core.shared_credentials.secret_store", store)
    monkeypatch.setattr("core.integrations.qbittorrent.secret_store", store)
    save_shared_admin_credentials("qballjos", "ManagerPass123!")
    assert target_webui_credentials() == ("qballjos", "ManagerPass123!")
    store.save_secret("qbittorrent_username", "admin")
    store.save_secret("qbittorrent_password", "")
    assert target_webui_credentials() == ("qballjos", "ManagerPass123!")


def test_apply_qbittorrent_webui_login_sets_preferences(tmp_path: Path, monkeypatch):
    store = SecretStore(key_path=tmp_path / "secret.key", storage_path=tmp_path / "secrets.enc")
    monkeypatch.setattr("core.shared_credentials.secret_store", store)
    monkeypatch.setattr("core.integrations.qbittorrent.secret_store", store)
    save_shared_admin_credentials("qballjos", "ManagerPass123!")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.username = kwargs.get("username")
            self.password = kwargs.get("password")

        def login(self):
            return True

        def app_accessible(self):
            return True

        def set_webui_login(self, username, password):
            assert username == "qballjos"
            assert password == "ManagerPass123!"
            return True

    monkeypatch.setattr("core.integrations.qbittorrent.QBittorrentClient", FakeClient)
    assert apply_qbittorrent_webui_login(tmp_path, 8081, restart_if_needed=False) is True
    conf = (tmp_path / "qBittorrent" / "qBittorrent.conf").read_text(encoding="utf-8")
    assert "WebUI\\Username=qballjos" in conf
    assert "WebUI\\Password_PBKDF2=" in conf


@patch("core.integrations.local_auth.requests.put")
@patch("core.integrations.local_auth.requests.get")
def test_set_servarr_forms_auth(mock_get, mock_put):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"port": 8989, "bindAddress": "*"})
    mock_put.return_value = MagicMock(status_code=202)
    assert set_servarr_forms_auth("http://127.0.0.1:8989/api/v3", "key", "amm", "SharedPass123!") is True
    payload = mock_put.call_args.kwargs["json"]
    assert payload["authenticationMethod"] == "forms"
    assert payload["username"] == "amm"
    assert payload["password"] == "SharedPass123!"
    assert payload["passwordConfirmation"] == "SharedPass123!"


def test_patch_bazarr_auth_yaml(tmp_path: Path):
    config = tmp_path / "config.yaml"
    assert patch_bazarr_auth_yaml(config, "amm", "SharedPass123!") is True
    text = config.read_text(encoding="utf-8")
    assert "type: form" in text
    assert "amm" in text
    assert sha256_hex("SharedPass123!") in text


@patch("core.integrations.local_auth.requests.post")
def test_set_profilarr_login_accepts_register(mock_post):
    mock_post.return_value = MagicMock(status_code=201)
    assert set_profilarr_login(6868, "amm", "SharedPass123!") is True
    assert mock_post.call_args.kwargs["json"]["password"] == "SharedPass123!"


def test_set_neutarr_login_enables_lan_bypass(tmp_path: Path):
    assert set_neutarr_login(tmp_path, "amm", "SharedPass123!") is True
    data = json.loads((tmp_path / "general.json").read_text(encoding="utf-8"))
    assert data["local_access_bypass"] is True
    assert "192.168.0.0/16" in data["local_bypass_cidrs"]
