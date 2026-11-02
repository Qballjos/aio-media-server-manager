"""Boot does not block the dashboard and does not rewrite permissions that are already right."""

import asyncio
import os
from pathlib import Path

from fastapi.testclient import TestClient

from core.settings import Settings
from core.vpn import VpnManager


def _manager(tmp_path: Path) -> VpnManager:
    return VpnManager(
        Settings(
            config_dir=tmp_path / "config",
            download_dir=tmp_path / "dl",
            media_dir=tmp_path / "media",
            vpn_enabled=True,
        )
    )


def test_chown_tree_skips_entries_that_are_already_right(tmp_path, monkeypatch):
    tree = tmp_path / "dl"
    (tree / "show").mkdir(parents=True)
    (tree / "show" / "episode.mkv").write_text("x")
    mgr = _manager(tmp_path)
    uid, gid = os.getuid(), os.getgid()
    # 0o775, not 0o2775: macOS drops setgid on directories, Linux keeps it.
    assert mgr._chown_tree(tree, uid=uid, gid=gid, mode=0o775) is True

    writes = []
    monkeypatch.setattr(os, "chown", lambda *a, **k: writes.append(("chown", a[0])))
    real_chmod = os.chmod
    monkeypatch.setattr(os, "chmod", lambda p, m, **k: (writes.append(("chmod", p)), real_chmod(p, m)))
    mgr._chown_tree(tree, uid=uid, gid=gid, mode=0o775)
    # Only the top-level directory is touched; nothing below it changed.
    assert [str(path) for _, path in writes] == [str(tree), str(tree)]


def test_prepare_tunneled_app_reuses_a_fresh_result(tmp_path, monkeypatch):
    mgr = _manager(tmp_path)
    monkeypatch.setattr(mgr, "uses_uid_isolation", lambda: True)
    monkeypatch.setattr(mgr, "_ensure_vpn_app_user", lambda: None)
    monkeypatch.setattr(mgr, "_vpn_app_gid", lambda: os.getgid())
    monkeypatch.setattr(mgr, "_vpn_uid_can_write", lambda path, gid: True)
    monkeypatch.setattr(mgr, "_strip_posix_acls", lambda path: None)
    walks = []
    monkeypatch.setattr(mgr, "_chown_tree", lambda path, **kw: walks.append(Path(path)) or True)

    mgr.prepare_tunneled_app("qbittorrent")
    mgr.prepare_tunneled_app("qbittorrent")
    mgr.prepare_tunneled_app("prowlarr")
    downloads = [path for path in walks if path == tmp_path / "dl"]
    assert len(downloads) == 1
    assert len(walks) == 3  # two app config dirs, one downloads tree

    config_dir = next(path for path in walks if "qbittorrent" in str(path))
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "new-file").write_text("installed")
    mgr.prepare_tunneled_app("qbittorrent")
    assert len(walks) == 4  # the config dir changed, so it is prepared again


def test_dashboard_answers_while_apps_are_still_booting(monkeypatch):
    from api import app as app_module
    from core.settings import settings

    release = asyncio.Event()
    entered = []

    async def slow_boot(self=None):
        entered.append(True)
        await release.wait()

    monkeypatch.setattr(settings, "vpn_enabled", False)
    monkeypatch.setattr(settings, "cloudflare_tunnel_enabled", False)
    monkeypatch.setattr("applications.catalog.ApplicationCatalog.all_plugins", lambda self: [])
    monkeypatch.setattr("core.integrations.lifecycle.vpn_isolation_loop", slow_boot)
    monkeypatch.setattr("core.update_schedule.scheduler_loop", slow_boot)
    monkeypatch.setattr("core.downloads_pause.resume_when_due_loop", slow_boot)
    monkeypatch.setattr("core.notifications.notifications_loop", slow_boot)
    with TestClient(app_module.create_app()) as client:
        assert client.get("/api/health").status_code < 500
