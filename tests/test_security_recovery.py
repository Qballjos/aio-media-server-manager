"""Regression tests for backup boundaries, session revocation and double-failure recovery."""

import asyncio
import io
import tarfile
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient

from core.auth import AuthManager
from core.backup_manager import BackupManager
from core.installer.installer import AppInstaller
from core.settings import Settings
from core.update_schedule import UpdateScheduler
from tests.test_updater import _setup


def request(token="", method="GET", path="/api/backups", headers=()):
    return Request({"type": "http", "method": method, "path": path,
                    "headers": [(b"authorization", f"Bearer {token}".encode()), *headers],
                    "scheme": "http", "server": ("test", 80), "query_string": b""})


@pytest.mark.parametrize("auth_content", [None, "{invalid", "[]"])
def test_backup_routes_fail_closed_before_setup(tmp_path, monkeypatch, auth_content):
    from api.routers import backups
    manager = AuthManager(Settings(config_dir=tmp_path))
    if auth_content is not None:
        manager._auth_path.write_text(auth_content)
    monkeypatch.setattr(backups, "auth_manager", manager)
    monkeypatch.delenv("AMM_BACKUP_RECOVERY_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(backups.router)
    client = TestClient(app)
    for method, path in [("GET", ""), ("GET", "/job"), ("GET", "/amm-test.tar.gz/download"),
                         ("POST", "/upload"), ("POST", "/amm-test.tar.gz/restore"),
                         ("DELETE", "/amm-test.tar.gz")]:
        assert client.request(method, "/api/backups" + path).status_code == 401


def test_recovery_token_is_explicit_and_limited(tmp_path, monkeypatch):
    from api.routers import backups
    monkeypatch.setattr(backups, "auth_manager", AuthManager(Settings(config_dir=tmp_path)))
    monkeypatch.setenv("AMM_BACKUP_RECOVERY_TOKEN", "a" * 32)
    headers = [(b"x-aio-recovery-token", b"a" * 32)]
    backups._ensure_authenticated(request(method="POST", path="/api/backups/amm-x.tar.gz/restore", headers=headers))
    for method, path in [("DELETE", "/api/backups/amm-x.tar.gz"), ("GET", "/api/backups/amm-x.tar.gz/download")]:
        with pytest.raises(HTTPException):
            backups._ensure_authenticated(request(method=method, path=path, headers=headers))
    with pytest.raises(HTTPException):
        backups._ensure_authenticated(request())
    backups.auth_manager.create_admin("admin", "Password123!")
    with pytest.raises(HTTPException):
        backups._ensure_authenticated(request(headers=headers))


@pytest.mark.parametrize("kind", ["traversal", "absolute", "symlink"])
def test_restore_rejects_unsafe_paths_before_sidecar_deletion(tmp_path, kind):
    cfg = Settings(config_dir=tmp_path / "config", backup_dir=tmp_path / "backups")
    cfg.config_dir.mkdir()
    cfg.backup_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "db.sqlite-wal"
    victim.write_text("preserve")
    names = {"traversal": "../outside/db.sqlite", "absolute": str(outside / "db.sqlite"), "symlink": "link/db.sqlite"}
    if kind == "symlink":
        (cfg.config_dir / "link").symlink_to(outside, target_is_directory=True)
    archive = cfg.backup_dir / "amm-unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo(names[kind])
        member.size = 3
        tar.addfile(member, io.BytesIO(b"bad"))
    with pytest.raises(tarfile.ExtractError):
        BackupManager(cfg).restore_backup(archive.name)
    assert victim.read_text() == "preserve"
    assert not (outside / "db.sqlite").exists()


def test_logout_revokes_only_current_session_and_survives_restart(tmp_path):
    cfg = Settings(config_dir=tmp_path)
    auth = AuthManager(cfg)
    auth.create_admin("admin", "Password123!")
    first, second = auth.issue_token("admin"), auth.issue_token("admin")
    auth.revoke_request_session(request(first, "POST"))
    auth = AuthManager(cfg)
    with pytest.raises(HTTPException):
        auth.decode_token(first)
    assert auth.decode_token(second)["sub"] == "admin"
    auth.update_account("admin", current_password="Password123!", new_password="Different123!")
    with pytest.raises(HTTPException):
        auth.decode_token(second)
    assert auth.decode_token(auth.issue_token("admin"))["sub"] == "admin"


@pytest.mark.parametrize("secure", [False, True])
def test_cookie_security_is_explicit_not_forwarded_header_dependent(tmp_path, secure):
    auth = AuthManager(Settings(config_dir=tmp_path, secure_cookies=secure))
    response = Response()
    auth.set_session_cookies(response, auth.issue_token("admin"))
    assert all(("; Secure" in cookie) == secure for cookie in response.headers.getlist("set-cookie"))
    response = Response()
    auth.clear_session_cookies(response)
    assert all(("; Secure" in cookie) == secure for cookie in response.headers.getlist("set-cookie"))


async def test_failed_snapshot_restore_is_not_reported_as_success(tmp_path, monkeypatch):
    def install():
        raise RuntimeError("install failed")
    updater, plugin = _setup(tmp_path, install)
    def restore(_archive):
        raise OSError("snapshot failed")
    monkeypatch.setattr(updater.backups, "restore_application_snapshot", restore)
    result = await updater.update(plugin)
    assert result["status"] == "rollback_failed"
    assert result["recovery"] == {"binary": True, "configuration": False, "process": True}
    assert result["recovery_errors"]["configuration"] == "snapshot failed"


async def test_failed_binary_rollback_keeps_recovery_copy(tmp_path, monkeypatch):
    def install():
        raise RuntimeError("install failed")
    updater, plugin = _setup(tmp_path, install)
    def move(*_args):
        raise OSError("move failed")
    monkeypatch.setattr("core.updater.shutil.move", move)
    result = await updater.update(plugin)
    assert result["status"] == "rollback_failed"
    assert (plugin.install_dir.parent / ".demo.pre-update" / "old.txt").read_text() == "old"
    assert result["recovery_install"]


@pytest.mark.parametrize("failure", ["start", "health"])
async def test_daemon_rollback_requires_healthy_restart(tmp_path, monkeypatch, failure):
    def install():
        return SimpleNamespace(version="2")
    updater, plugin = _setup(tmp_path, install)
    plugin.manifest.daemon = True
    plugin.start_command = lambda: ["demo"]
    plugin.working_directory = lambda: plugin.install_dir
    plugin.extra_env = lambda: {}
    supervisor = SimpleNamespace(status=lambda _name: SimpleNamespace(value="running"),
                                 stop=AsyncMock(), start=AsyncMock())
    monkeypatch.setattr("core.updater.ProcessSupervisor.get", lambda: supervisor)
    monkeypatch.setattr(updater, "_wait_healthy", lambda _plugin: False)
    if failure == "start":
        supervisor.start.side_effect = [None, OSError("restart failed")]
    result = await updater.update(plugin)
    assert result["status"] == "rollback_failed"
    assert result["recovery"]["binary"] is True
    assert result["recovery"]["configuration"] is True
    assert result["recovery"]["process"] is False
    assert supervisor.start.await_count == 2


def test_installer_retains_previous_copy_on_double_swap_failure(tmp_path, monkeypatch):
    cfg = Settings(config_dir=tmp_path / "config", install_dir=tmp_path / "apps")
    installer = AppInstaller(app_settings=cfg)
    target = cfg.install_dir / "demo"
    target.mkdir(parents=True)
    (target / "demo").write_text("old")
    archive = tmp_path / "demo.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("demo")
        member.size = 3
        tar.addfile(member, io.BytesIO(b"new"))
    import os
    replace = os.replace
    def fail_activation(src, dest):
        if dest == target:
            raise OSError("activation and recovery failed")
        return replace(src, dest)
    monkeypatch.setattr("core.installer.installer.os.replace", fail_activation)
    with pytest.raises(OSError):
        installer.activate_archive(archive, target, "demo", "demo")
    copies = list(target.parent.glob(".demo.previous-*"))
    assert len(copies) == 1
    assert (copies[0] / "demo").read_text() == "old"


async def test_slow_update_check_keeps_event_loop_responsive(tmp_path, monkeypatch):
    scheduler = UpdateScheduler(Settings(config_dir=tmp_path))
    monkeypatch.setattr("core.update_schedule.pause_reason", lambda: None)
    started, release = threading.Event(), threading.Event()
    def check():
        started.set()
        assert release.wait(3)
        return {"available": []}
    monkeypatch.setattr(scheduler, "check_installed", check)
    task = asyncio.create_task(scheduler.tick(force_check=True))
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        assert not task.done()
    finally:
        release.set()
        await task


@pytest.mark.parametrize("state", ["corrupt", "missing"])
def test_existing_account_cannot_be_replaced_through_public_setup(tmp_path, state):
    auth = AuthManager(Settings(config_dir=tmp_path))
    auth.create_admin("admin", "Password123!")
    auth.issue_token("admin")
    if state == "missing":
        auth._auth_path.unlink()
    else:
        auth._auth_path.write_text("broken")
    assert auth.setup_required()
    with pytest.raises(HTTPException) as exc:
        auth.create_admin("attacker", "Password123!")
    assert exc.value.status_code == 409


async def test_daemon_rollback_success_requires_second_health_check(tmp_path, monkeypatch):
    updater, plugin = _setup(tmp_path, lambda: SimpleNamespace(version="2"))
    plugin.manifest.daemon = True
    plugin.start_command = lambda: ["demo"]
    plugin.working_directory = lambda: plugin.install_dir
    plugin.extra_env = lambda: {}
    supervisor = SimpleNamespace(status=lambda _name: SimpleNamespace(value="running"),
                                 stop=AsyncMock(), start=AsyncMock())
    monkeypatch.setattr("core.updater.ProcessSupervisor.get", lambda: supervisor)
    checks = iter([False, True])
    monkeypatch.setattr(updater, "_wait_healthy", lambda _plugin: next(checks))
    result = await updater.update(plugin)
    assert result["status"] == "rolled_back"
    assert all(result["recovery"].values())
    assert (plugin.install_dir / "old.txt").read_text() == "old"
    assert supervisor.start.await_count == 2


def test_https_mode_can_be_enabled_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("AMM_SECURE_COOKIES", "true")
    assert Settings(config_dir=tmp_path).secure_cookies is True


def test_session_records_are_not_backed_up(tmp_path):
    cfg = Settings(config_dir=tmp_path / "config", backup_dir=tmp_path / "backups")
    auth = AuthManager(cfg)
    auth.create_admin("admin", "Password123!")
    auth.issue_token("admin")
    manager = BackupManager(cfg)
    result = manager.create_backup("sessions")
    with tarfile.open(manager.resolve_archive(result["name"]), "r:gz") as tar:
        assert not any(".sessions" in member.name for member in tar)


async def test_retry_preserves_existing_recovery_copy_and_snapshot(tmp_path, monkeypatch):
    updater, plugin = _setup(tmp_path, lambda: SimpleNamespace(version="2"))
    previous = plugin.install_dir.parent / ".demo.pre-update"
    previous.mkdir()
    (previous / "old.txt").write_text("recovery")
    def snapshot(_name):
        pytest.fail("Retry must not create or prune snapshots while recovery is unresolved")
    monkeypatch.setattr(updater.backups, "snapshot_application", snapshot)
    with pytest.raises(RuntimeError, match="retained recovery copy"):
        await updater.update(plugin)
    assert (previous / "old.txt").read_text() == "recovery"
