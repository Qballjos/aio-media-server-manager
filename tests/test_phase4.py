"""Tests for Phase 4 catalog plugins, backups, and uninstall safeguards."""

from __future__ import annotations

from pathlib import Path

import pytest

from applications.catalog import ApplicationCatalog
from core.backup_manager import BackupManager
from core.settings import Settings
from core.uninstall import UninstallError, uninstall_application
from core.updater import _is_newer


@pytest.fixture
def catalog(tmp_path: Path) -> ApplicationCatalog:
    test_settings = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        backup_dir=tmp_path / "backups",
    )
    return ApplicationCatalog(app_settings=test_settings)


def test_phase4_catalog_plugins(catalog: ApplicationCatalog):
    names = set(catalog.names())
    expected = {
        "plex",
        "nzbget",
        "bazarr",
        "recyclarr",
        "neutarr",
        "lidarr",
        "flaresolverr",
        "grimmory",
        "shelfmark",
    }
    assert expected.issubset(names)
    assert catalog.get("recyclarr").manifest.daemon is False
    assert catalog.get("plex").manifest.default_port == 32400
    names = set(catalog.names())
    assert "mylar3" not in names
    assert "unpackerr" not in names
    assert "tautulli" not in names
    assert "cleanuparr" not in names
    assert "maintainerr" not in names
    assert "autobrr" not in names
    assert "kometa" not in names
    assert "readarr" not in names
    assert "whisparr" not in names
    assert "huntarr" not in names


def test_nzbget_start_uses_configfile_not_option(tmp_path: Path):
    install_root = tmp_path / "apps"
    bindir = install_root / "nzbget" / "usr" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / "nzbget"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    webui = install_root / "nzbget" / "usr" / "share" / "nzbget" / "webui"
    webui.mkdir(parents=True)

    catalog = ApplicationCatalog(
        app_settings=Settings(
            config_dir=tmp_path / "config",
            install_dir=install_root,
            download_dir=tmp_path / "downloads",
        )
    )
    app = catalog.get("nzbget")
    cmd = app.start_command()

    assert cmd[0] == str(exe)
    assert "--configfile" in cmd
    assert str(app.config_dir / "nzbget.conf") in cmd
    assert "--server" in cmd
    assert "OutputMode=log" in cmd
    assert f"ControlPort={app.port}" in cmd
    assert "ConfigFile=" not in " ".join(cmd)
    assert app.config_file().is_file()
    assert app.working_directory() == bindir
    assert f"WebDir={webui}" in cmd
    assert f"DestDir={tmp_path / 'downloads' / 'complete'}" in cmd


def test_backup_create_list_and_restore(tmp_path: Path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "amm_config.json").write_text("{}", encoding="utf-8")
    (cfg / "sonarr").mkdir()
    (cfg / "sonarr" / "config.xml").write_text("<config/>", encoding="utf-8")
    (cfg / "cache").mkdir()
    (cfg / "cache" / "big.bin").write_text("skip", encoding="utf-8")
    media = tmp_path / "media"
    media.mkdir()
    (media / "movie.mkv").write_text("nope", encoding="utf-8")

    settings = Settings(
        config_dir=cfg,
        download_dir=tmp_path / "downloads",
        media_dir=media,
        backup_dir=tmp_path / "backups",
        backup_retention=2,
        install_dir=tmp_path / "apps",
    )
    manager = BackupManager(settings)
    first = manager.create_backup(label="one")
    assert Path(first["path"]).is_file()
    manager.create_backup(label="two")
    manager.create_backup(label="three")
    backups = manager.list_backups()
    assert len(backups) == 2

    restore_dir = tmp_path / "restore"
    restore_settings = Settings(
        config_dir=restore_dir,
        download_dir=tmp_path / "downloads",
        media_dir=media,
        backup_dir=tmp_path / "backups",
        install_dir=tmp_path / "apps",
    )
    restored = BackupManager(restore_settings).restore_backup(backups[0]["name"])
    assert restored["status"] == "restored"
    assert (restore_dir / "amm_config.json").is_file()
    assert not (restore_dir / "cache" / "big.bin").exists()


@pytest.mark.asyncio
async def test_uninstall_refuses_media_paths(tmp_path: Path, catalog: ApplicationCatalog):
    plugin = catalog.get("sonarr")
    plugin.config_dir = tmp_path / "media" / "sonarr"
    plugin.config_dir.mkdir(parents=True)
    with pytest.raises(UninstallError):
        await uninstall_application(plugin, app_settings=catalog._settings)


@pytest.mark.asyncio
async def test_uninstall_continues_when_stop_fails(tmp_path: Path, catalog: ApplicationCatalog, monkeypatch):
    plugin = catalog.get("sonarr")
    plugin.install_dir = tmp_path / "apps" / "sonarr"
    plugin.install_dir.mkdir(parents=True)
    (plugin.install_dir / "Sonarr").write_text("x", encoding="utf-8")
    plugin.config_dir = tmp_path / "config" / "sonarr"
    plugin.config_dir.mkdir(parents=True)
    forgotten: list[str] = []

    class FakeSupervisor:
        async def stop(self, name: str, timeout: float = 10.0) -> None:
            raise RuntimeError("Task got Future attached to a different loop")

        def forget(self, name: str) -> None:
            forgotten.append(name)

    monkeypatch.setattr("core.uninstall.ProcessSupervisor.get", lambda: FakeSupervisor())
    result = await uninstall_application(plugin, app_settings=catalog._settings)
    assert result["status"] == "uninstalled"
    assert forgotten == ["sonarr"]
    assert not plugin.install_dir.exists()


def test_version_compare():
    assert _is_newer("1.2.0", "1.1.0")
    assert not _is_newer("1.1.0", "1.2.0")
    assert _is_newer("v2.0.0", "1.9.9")


def test_grimmory_runner_starts_mariadb_as_root(catalog: ApplicationCatalog):
    app = catalog.get("grimmory")
    app.install_dir.mkdir(parents=True, exist_ok=True)
    app.data_dir.mkdir(parents=True, exist_ok=True)
    (app.install_dir / "grimmory.jar").write_bytes(b"jar")
    app.post_install()
    script = (app.install_dir / "run-grimmory").read_text(encoding="utf-8")
    assert "--user=root" in script
    assert "command -v java" in script
    assert "--enable-preview" in script
    assert "if ! _mariadb_up" in script


def test_grimmory_bookdrop_matches_shelfmark_ingest(tmp_path: Path, monkeypatch):
    from applications.community import GrimmoryApp, ShelfmarkApp
    from core.library_layout import LibraryLayout
    from core import settings as settings_mod

    cfg = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(settings_mod, "settings", cfg)
    monkeypatch.setattr("applications.community.default_settings", cfg)

    grimmory = GrimmoryApp(base_config_dir=cfg.config_dir, base_install_dir=cfg.install_dir)
    shelfmark = ShelfmarkApp(base_config_dir=cfg.config_dir, base_install_dir=cfg.install_dir)
    layout = LibraryLayout.from_settings(cfg)
    bookdrop = str(layout.bookdrop)
    g_env = grimmory.extra_env()
    s_env = shelfmark.extra_env()
    assert g_env["APP_BOOKDROP_FOLDER"] == bookdrop
    assert s_env["INGEST_DIR"] == bookdrop
    assert s_env["DESTINATION"] == bookdrop
    assert "DESTINATION_AUDIOBOOK" not in s_env
    assert "QBITTORRENT_CATEGORY_AUDIOBOOK" not in s_env

