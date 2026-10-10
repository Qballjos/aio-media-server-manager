import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.crypto import SecretStore
from core.integrations.local_auth import (
    patch_bazarr_auth_yaml,
    set_neutarr_login,
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
    assert "Session\\LSDEnabled=false" in conf
    assert "Session\\GlobalMaxRatio=-1" in conf
    assert "Session\\MaxConnections=800" in conf


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
    from core.integrations.local_auth import bazarr_password_hash

    config = tmp_path / "config.yaml"
    assert patch_bazarr_auth_yaml(config, "amm", "SharedPass123!") is True
    text = config.read_text(encoding="utf-8")
    assert "type: form" in text
    assert "amm" in text
    assert bazarr_password_hash("SharedPass123!") in text
    assert sha256_hex("SharedPass123!") not in text
    assert patch_bazarr_auth_yaml(config, "amm", "SharedPass123!") is False


def test_patch_bazarr_auth_yaml_only_updates_auth_section(tmp_path: Path):
    from core.integrations.local_auth import bazarr_password_hash

    config = tmp_path / "config.yaml"
    config.write_text(
        "---\n"
        "addic7ed:\n"
        "  password: ''\n"
        "  username: ''\n"
        "auth:\n"
        "  apikey: keep-me\n"
        "  password: ''\n"
        "  type: None\n"
        "  username: ''\n"
        "sonarr:\n"
        "  username: ''\n",
        encoding="utf-8",
    )
    assert patch_bazarr_auth_yaml(config, "amm", "SharedPass123!") is True
    text = config.read_text(encoding="utf-8")
    assert "apikey: keep-me" in text
    assert "addic7ed:\n  password: ''\n  username: ''" in text
    assert re.search(r"(?m)^auth:\n(?:  .*\n)*  username: \"amm\"", text)
    assert bazarr_password_hash("SharedPass123!") in text
    assert text.count(bazarr_password_hash("SharedPass123!")) == 1


def test_set_neutarr_login_enables_lan_bypass(tmp_path: Path):
    assert set_neutarr_login(tmp_path, "amm", "SharedPass123!") is True
    data = json.loads((tmp_path / "general.json").read_text(encoding="utf-8"))
    assert data["local_access_bypass"] is True
    assert "192.168.0.0/16" in data["local_bypass_cidrs"]


@patch("requests.put")
@patch("requests.get")
def test_set_servarr_forms_auth_restarts_app_when_auth_method_changes(mock_get, mock_put, monkeypatch):
    from core.integrations import local_auth

    restarted = []
    monkeypatch.setattr(local_auth, "restart_app_if_running", lambda name: restarted.append(name))
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"authenticationMethod": "none", "port": 9696})
    mock_put.return_value = MagicMock(status_code=202)
    # Servarr only reads the authentication method at startup, so a change needs a restart.
    assert set_servarr_forms_auth("http://127.0.0.1:9696/api/v1", "key", "amm", "SharedPass123!", name="prowlarr") is True
    assert restarted == ["prowlarr"]


@patch("requests.put")
@patch("requests.get")
def test_set_servarr_forms_auth_leaves_app_running_when_already_forms(mock_get, mock_put, monkeypatch):
    from core.integrations import local_auth

    restarted = []
    monkeypatch.setattr(local_auth, "restart_app_if_running", lambda name: restarted.append(name))
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"authenticationMethod": "forms", "port": 8989})
    mock_put.return_value = MagicMock(status_code=202)
    assert set_servarr_forms_auth("http://127.0.0.1:8989/api/v3", "key", "amm", "SharedPass123!", name="sonarr") is True
    assert restarted == []


def test_shared_logins_run_before_slow_media_setup(tmp_path, monkeypatch):
    from core.integrations import engine
    from core.settings import Settings

    events = []
    manager = engine.IntegrationEngine(Settings(config_dir=tmp_path / "config"))
    monkeypatch.setattr(engine, "apply_shared_local_logins", lambda **kwargs: events.append("shared logins") or [])
    storage = MagicMock()

    def stop_at_storage():
        events.append("media folders")
        raise RuntimeError("stop before media setup")

    storage.create_standard_layout.side_effect = stop_at_storage
    monkeypatch.setattr(engine, "StorageManager", lambda *args: storage)
    with pytest.raises(RuntimeError, match="stop before media setup"):
        manager.run_full_wiring()
    assert events == ["shared logins", "media folders"]


async def test_ready_servarr_gets_aio_login_before_waiting_for_shared_wiring(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from core.integrations import lifecycle

    events = []
    plugin = SimpleNamespace(
        name="prowlarr", port=9696, config_dir=tmp_path,
        manifest=SimpleNamespace(daemon=True), start_command=lambda: ["Prowlarr"],
        working_directory=lambda: tmp_path, extra_env=lambda: {},
    )
    supervisor = SimpleNamespace(start=AsyncMock())
    monkeypatch.setattr(lifecycle.ProcessSupervisor, "get", lambda: supervisor)
    monkeypatch.setattr(lifecycle.vpn_manager, "assert_can_start_tunneled_app", lambda name: None)
    healthy = AsyncMock(return_value=True)
    monkeypatch.setattr(lifecycle, "_wait_healthy", healthy)
    monkeypatch.setattr(lifecycle, "wait_for_application_api_key", AsyncMock(return_value="test-api-key"))
    monkeypatch.setattr(lifecycle, "set_job", lambda *args, **kwargs: None)

    def configure_login(**kwargs):
        assert kwargs["installed"]("prowlarr") is True
        assert kwargs["installed"]("sonarr") is False
        assert kwargs["port_for"]("prowlarr", 0) == 9696
        assert kwargs["api_key_for"]("prowlarr") == "test-api-key"
        assert kwargs["config_dir_for"]("prowlarr") == tmp_path
        events.append("shared login")
        return [{"status": "success"}]

    async def wiring():
        assert healthy.await_count == 2
        events.append("shared wiring")
        return {"status": "completed"}

    monkeypatch.setattr(lifecycle, "apply_shared_local_logins", configure_login)
    monkeypatch.setattr(lifecycle, "schedule_full_wiring", wiring)
    report = await lifecycle.finalize_application_install(plugin)
    assert events == ["shared login", "shared wiring"]
    assert report["shared_login"] is True
    assert report["healthy"] is True


def test_concurrent_servarr_login_setup_changes_auth_and_restarts_once(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from core.integrations import local_auth

    first_get = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_get = threading.Event()
    methods = []
    current = {"method": "none"}
    restarted = []

    def get(*args, **kwargs):
        method = current["method"]
        methods.append(method)
        if len(methods) == 1:
            first_get.set()
            assert release_first.wait(2)
        else:
            second_get.set()
        return MagicMock(status_code=200, json=lambda: {"authenticationMethod": method})

    def put(*args, **kwargs):
        current["method"] = kwargs["json"]["authenticationMethod"]
        return MagicMock(status_code=202)

    def configure(second=False):
        if second:
            second_started.set()
        return set_servarr_forms_auth("http://127.0.0.1:9696/api/v1", "key", "amm", "SharedPass123!", name="prowlarr")

    monkeypatch.setattr(local_auth.requests, "get", get)
    monkeypatch.setattr(local_auth.requests, "put", put)
    monkeypatch.setattr(local_auth, "restart_app_if_running", restarted.append)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(configure)
        try:
            assert first_get.wait(1)
            second = workers.submit(configure, True)
            assert second_started.wait(1)
            assert not second_get.wait(0.1)
        finally:
            release_first.set()
        assert first.result(timeout=2) is True
        assert second.result(timeout=2) is True
    assert methods == ["none", "forms"]
    assert restarted == ["prowlarr"]


def test_shared_login_pass_reports_progress_per_app(monkeypatch):
    from core.integrations import local_auth
    from core.integrations.bazarr import BazarrClient

    messages: list[str] = []
    monkeypatch.setattr(local_auth, "set_wiring_progress", messages.append)
    monkeypatch.setattr(local_auth, "shared_admin_credentials", lambda: ("amm", "pw"))
    monkeypatch.setattr(local_auth, "set_servarr_forms_auth", lambda *args, **kwargs: True)
    monkeypatch.setattr(BazarrClient, "set_ui_auth", lambda self, username, password, config_dir: True)
    local_auth.apply_shared_local_logins(
        installed=lambda name: name in {"sonarr", "bazarr"},
        port_for=lambda name, fallback: fallback,
        api_key_for=lambda name: "k",
        config_dir_for=lambda name: Path("/tmp/aio-test"),
    )
    assert messages == ["Setting the AIO login in Sonarr", "Setting the AIO login in Bazarr"]
