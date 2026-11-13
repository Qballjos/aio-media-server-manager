"""Operations capabilities: inspect before action, protect edits and verify encrypted recovery."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from core.external_backups import ExternalBackups, encrypt_archive, decrypt_archive
from core.backup_manager import BackupManager
from core.install_jobs import clear_jobs, get_job, set_job, update_job
from core.preflight import inspect_action, require_action, PreflightError
from core.settings import Settings


@pytest.fixture
def cfg(tmp_path):
    value = Settings(config_dir=tmp_path / "config", backup_dir=tmp_path / "backups", media_dir=tmp_path / "media", download_dir=tmp_path / "downloads")
    value.config_dir.mkdir()
    return value


def plugin(name="sonarr", port=8989, **kwargs):
    return SimpleNamespace(name=name, port=port, config_dir=Path("/unused"), manifest=SimpleNamespace(github_repo="owner/repo"), is_installed=lambda: True, **kwargs)


def test_low_space_blocks_action_before_changes(cfg, monkeypatch):
    monkeypatch.setattr("core.preflight.shutil.disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(PreflightError, match="MiB"):
        require_action(plugin(), cfg)
    assert not cfg.install_dir.exists()


def test_preflight_reports_rate_limit_and_does_not_leak_token(cfg, monkeypatch):
    monkeypatch.setattr("core.preflight.requests.get", lambda *a, **kw: SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"resources": {"core": {"remaining": 0, "reset": 9999999999}}}))
    result = inspect_action(plugin(), cfg, network=True)
    assert result["ok"] is False
    assert next(c for c in result["checks"] if c["name"] == "github")["status"] == "blocked"


def test_unreachable_github_is_an_explicit_warning(cfg, monkeypatch):
    def fail(*a, **kw):
        raise requests.Timeout()
    monkeypatch.setattr("core.preflight.requests.get", fail)
    report = inspect_action(plugin(), cfg, network=True)
    assert report["ok"]
    assert any(c["name"] == "github" and c["status"] == "warning" for c in report["checks"])


def test_progress_history_preserves_stages_and_is_bounded():
    clear_jobs()
    set_job("test", "queued", "Waiting")
    set_job("test", "installing", "Downloading")
    update_job("test", "Extracting")
    set_job("test", "configuring", "Connecting")
    assert [r["message"] for r in get_job("test")["history"]] == ["Waiting", "Downloading", "Extracting", "Connecting"]
    for i in range(150):
        set_job("test", "configuring", f"Step {i}")
    assert len(get_job("test")["history"]) == 100
    clear_jobs()


def test_public_indexers_require_explicit_opt_in(cfg):
    from core.integrations.engine import IntegrationEngine
    engine = IntegrationEngine(cfg)
    client = Mock()
    result = engine._starter_indexers_step(client)
    assert "opt-in" in result["detail"]
    client.add_starter_indexers.assert_not_called()
    client.ensure_seed_settings.assert_not_called()


def test_manual_mode_preserves_exact_yaml_even_when_forced(tmp_path):
    from core.recyclarr import save_yaml, write_recyclarr_config
    original = "# my notes\nsonarr:\n  custom:\n    api_key: unchanged\n"
    path = save_yaml(tmp_path, original)
    write_recyclarr_config(tmp_path, sonarr_url="new", sonarr_key="new", radarr_url="new", radarr_key="new", prefs={}, force=True)
    assert path.read_text() == original


@pytest.mark.parametrize("change", ["wrong-password", "bitflip", "truncated"])
def test_encrypted_backup_rejects_tampering_and_removes_plaintext(tmp_path, change):
    source, encrypted, restored = (tmp_path / name for name in ("source", "encrypted", "restored"))
    source.write_bytes(b"private configuration" * 100)
    encrypt_archive(source, encrypted, "very-private-password")
    if change == "bitflip":
        value = bytearray(encrypted.read_bytes()); value[50] ^= 1; encrypted.write_bytes(value)
    elif change == "truncated":
        encrypted.write_bytes(encrypted.read_bytes()[:-10])
    with pytest.raises(ValueError):
        decrypt_archive(encrypted, restored, "wrong" if change == "wrong-password" else "very-private-password")
    assert not restored.exists()


class Response:
    def __init__(self, data=b"", status=200):
        self.data, self.status_code = data, status
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size):
        yield self.data


class WebDAV:
    def __init__(self): self.data = b""; self.status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def put(self, url, *, data, **kwargs):
        assert url.startswith("https://") and kwargs["allow_redirects"] is False
        self.data = data.read()
        return Response(status=201)
    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        return Response(self.data, self.status)


def prepared_external(cfg):
    (cfg.config_dir / "sonarr").mkdir()
    (cfg.config_dir / "sonarr" / "config.xml").write_text("<secret>private-key</secret>")
    backup = BackupManager(cfg).create_backup("external")
    external = ExternalBackups(cfg)
    external.save(enabled=True, url="https://cloud.example/backups", username="user", password="webdav-password", encryption_password="separate-recovery-password")
    return external, backup["name"]


def test_webdav_export_import_and_isolated_restore_drill(cfg, monkeypatch):
    external, name = prepared_external(cfg)
    dav = WebDAV()
    monkeypatch.setattr(external, "_session", lambda: dav)
    result = external.export(name)
    assert result["status"] == "verified"
    assert b"private-key" not in dav.data
    assert b"webdav-password" not in dav.data
    imported = external.import_backup(result["name"])
    active = cfg.config_dir / "sonarr" / "config.xml"
    active.write_text("active configuration remains untouched")
    drill = external.drill(imported["name"])
    assert drill["status"] == "verified" and drill["files"] > 0
    assert active.read_text() == "active configuration remains untouched"
    assert external.public()["last_drill"]["name"] == imported["name"]
    public = json.dumps(external.public())
    assert "webdav-password" not in public and "separate-recovery-password" not in public
    assert "separate-recovery-password" not in external.path.read_text()


def test_webdav_redirect_is_rejected_and_failure_saved(cfg, monkeypatch):
    external, name = prepared_external(cfg)
    dav = WebDAV(); dav.status = 302
    monkeypatch.setattr(external, "_session", lambda: dav)
    with pytest.raises(ValueError, match="HTTP 302"):
        external.export(name)
    assert external.public()["last_transfer"]["status"] == "failed"


@pytest.mark.parametrize("url", ["http://cloud.example/backups", "https://user:password@cloud.example/", "https://cloud.example/?token=secret", "https://cloud.example/#secret"])
def test_external_destination_validation(cfg, url):
    with pytest.raises(ValueError):
        ExternalBackups(cfg).save(url=url)


def test_integration_verification_detects_actual_misconfiguration_without_writes(cfg, monkeypatch):
    from core.integration_verify import verify_integrations
    from core.library_layout import LibraryLayout, arr_root_folders
    apps = [plugin(), plugin("qbittorrent", 8082)]
    catalog = SimpleNamespace(all_plugins=lambda: apps)
    monkeypatch.setattr("core.integration_verify.get_application_api_key", lambda *a: "private-api-key")
    def get(url, **kwargs):
        assert kwargs["headers"]["X-Api-Key"] == "private-api-key"
        rows = [{"path": str(p)} for p in arr_root_folders(LibraryLayout.from_settings(cfg))["sonarr"]] if url.endswith("rootfolder") else [{"enable": True, "implementation": "QBittorrent", "fields": [{"name": "host", "value": "127.0.0.1"}, {"name": "port", "value": 9999}, {"name": "tvCategory", "value": "sonarr"}]}]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: rows)
    monkeypatch.setattr("core.integration_verify.requests.get", get)
    post = Mock(); monkeypatch.setattr("requests.post", post)
    result = verify_integrations(cfg, catalog)
    assert result["ok"] is False
    assert result["checks"][0]["status"] == "pass"
    assert result["checks"][1]["status"] == "failed"
    assert "private-api-key" not in json.dumps(result)
    post.assert_not_called()


def test_custom_thresholds_and_incident_history(cfg, monkeypatch):
    from core import notifications
    from core.crypto import SecretStore
    monkeypatch.setattr(notifications, "settings", cfg)
    monkeypatch.setattr(notifications, "secret_store", SecretStore(cfg=cfg))
    notifications.save_config(discord_enabled=False, webhook_url=None, email={}, smtp_password=None, events={}, disk_alert_percent=80, disk_clear_percent=70)
    watcher = notifications.Watcher()
    messages = watcher.messages({"full_disks": {"media": 82}, "disk_alert_percent": 80, "disk_clear_percent": 70})
    assert len(messages) == 1
    assert watcher.messages({"full_disks": {"media": 75}, "disk_alert_percent": 80, "disk_clear_percent": 70}) == []
    assert watcher.messages({"full_disks": {"media": 65}, "disk_alert_percent": 80, "disk_clear_percent": 70})[0][3] == "ok"
    notifications.notify("backups", "Backup failed", "Open Backups", "problem")
    assert notifications.incident_history()[-1]["event"] == "backups"
    assert notifications.incident_history()[-1]["subject"] == "Backup failed"


def test_operations_endpoints_require_admin_and_never_return_secrets(cfg, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.auth import AuthManager
    from core.backup_jobs import BackupJobs
    from api.routers import backups, integrations
    auth = AuthManager(cfg)
    monkeypatch.setattr(backups, "auth_manager", auth)
    monkeypatch.setattr(backups, "settings", cfg)
    monkeypatch.setattr(backups, "backup_jobs", BackupJobs(cfg))
    monkeypatch.setattr(integrations, "auth_manager", auth)
    app = FastAPI(); app.include_router(backups.router); app.include_router(integrations.router)
    client = TestClient(app)
    for method, url, data in [("GET", "/api/backups/external/config", None), ("PUT", "/api/backups/external/config", {}), ("POST", "/api/backups/external/export", {"name": "amm-test.tar.gz"}), ("POST", "/api/integrations/verify", None)]:
        assert client.request(method, url, json=data).status_code == 401
    auth.create_admin("admin", "StrongPassword123!")
    headers = {"Authorization": f"Bearer {auth.issue_token('admin')}"}
    response = client.put("/api/backups/external/config", headers=headers, json={"enabled": True, "url": "https://cloud.example/backups", "username": "user", "password": "remote-secret", "encryption_password": "private-recovery-key"})
    assert response.status_code == 200
    assert response.json()["password_saved"]
    assert "remote-secret" not in response.text and "private-recovery-key" not in response.text
    assert client.get("/api/backups/external/config", headers=headers).status_code == 200


async def test_scheduled_backup_exports_and_keeps_local_copy_on_remote_failure(cfg, monkeypatch):
    from core.backup_jobs import BackupJobs
    from core import notifications
    monkeypatch.setattr(notifications, "settings", cfg)
    external = ExternalBackups(cfg)
    external.save(enabled=True, url="https://cloud.example/backups", encryption_password="private-recovery-key")
    def fail(*_args):
        raise ValueError("destination unavailable")
    monkeypatch.setattr(ExternalBackups, "export", fail)
    jobs = BackupJobs(cfg)
    jobs.start_backup("scheduled", kind="scheduled")
    result = await jobs.wait()
    assert result["status"] == "error"
    assert jobs.manager.list_backups()
    assert jobs.public_status()["last_error"]
    assert "destination unavailable" not in jobs.public_status()["last_error"]
    assert notifications.incident_history()[-1]["event"] == "backups"


def test_pending_restart_and_maintenance_block_preflight(cfg):
    from core.maintenance import backup_in_progress
    clear_jobs()
    set_job("sonarr", "restart_required", "Restart first")
    try:
        with pytest.raises(PreflightError, match="restart"):
            require_action(plugin(), cfg, operation="update")
        clear_jobs()
        with backup_in_progress():
            with pytest.raises(PreflightError, match="backup"):
                require_action(plugin(), cfg, operation="install")
    finally:
        clear_jobs()


def test_retry_setup_connects_installed_app_without_reinstalling(cfg, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    from core.auth import AuthManager
    from api.routers import catalog
    auth = AuthManager(cfg); auth.create_admin("admin", "StrongPassword123!")
    monkeypatch.setattr(catalog, "auth_manager", auth)
    app_plugin = plugin(install=Mock())
    monkeypatch.setattr(catalog, "catalog", SimpleNamespace(get=lambda _name: app_plugin))
    finalize = AsyncMock(return_value={"wired": True})
    monkeypatch.setattr(catalog, "finalize_application_install", finalize)
    clear_jobs(); set_job("sonarr", "failed", "Automatic setup failed")
    app = FastAPI(); app.include_router(catalog.router)
    response = TestClient(app).post("/api/catalog/sonarr/retry-setup", headers={"Authorization": f"Bearer {auth.issue_token('admin')}"})
    assert response.status_code == 200
    finalize.assert_awaited_once_with(app_plugin)
    app_plugin.install.assert_not_called()
    assert get_job("sonarr")["status"] == "started"
    clear_jobs()
