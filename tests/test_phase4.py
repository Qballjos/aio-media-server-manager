"""Tests for Phase 4 catalog plugins, backups, and uninstall safeguards."""

from __future__ import annotations

import json
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
        "cleanuparr",
    }
    assert expected.issubset(names)
    assert catalog.get("recyclarr").manifest.daemon is False
    assert catalog.get("plex").manifest.default_port == 32400
    names = set(catalog.names())
    assert "mylar3" not in names
    assert "unpackerr" not in names
    assert "tautulli" not in names
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


def test_grimmory_runner_uses_supervised_identity(catalog: ApplicationCatalog):
    app = catalog.get("grimmory")
    app.install_dir.mkdir(parents=True, exist_ok=True)
    app.data_dir.mkdir(parents=True, exist_ok=True)
    (app.install_dir / "grimmory.jar").write_bytes(b"jar")
    app.post_install()
    script = (app.install_dir / "run-grimmory").read_text(encoding="utf-8")
    assert "command -v java" in script
    assert "--enable-preview" in script
    assert "--enable-native-access=ALL-UNNAMED" in script
    assert "--expire-logs-days=0 --binlog-expire-logs-seconds=0" in script
    assert "if ! _mariadb_up" in script


def test_grimmory_bootstrap_uses_sql_root_without_running_daemon_as_root(catalog, tmp_path, monkeypatch):
    import os
    import subprocess

    app = catalog.get("grimmory")
    app.install_dir.mkdir(parents=True)
    (app.data_dir / "mysql" / "mysql").mkdir(parents=True)
    (app.install_dir / "grimmory.jar").write_bytes(b"jar")
    app.post_install()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    started = tmp_path / "db-started"
    bootstrapped = tmp_path / "db-bootstrapped"
    commands = {
        "mariadbd": f'case " $* " in *" --user=root "*) exit 1;; esac\ntouch "{started}"',
        "mariadb-admin": f'[ "$1" = "--user=root" ] && test -f "{started}"',
        "mysqladmin": "exit 1",
        "mariadb": f'[ "$1" = "--user=root" ] && touch "{bootstrapped}"',
        "java": f'test -f "{started}" && test -f "{bootstrapped}"',
    }
    for name, content in commands.items():
        target = bin_dir / name
        target.write_text("#!/bin/sh\n" + content + "\n")
        target.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    result = subprocess.run([str(app.install_dir / "run-grimmory")], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert bootstrapped.is_file()


def test_neutarr_retains_legacy_state_in_its_owned_directory(catalog):
    app = catalog.get("neutarr")
    legacy = app.config_dir.parent / "stateful" / "sonarr"
    legacy.mkdir(parents=True)
    (legacy / "processed.json").write_text('{"id": 42}')
    env = app.extra_env()
    stateful = Path(env["STATEFUL_DIR"])
    assert stateful == app.config_dir / "stateful"
    copied = stateful / "sonarr" / "processed.json"
    assert copied.read_text() == '{"id": 42}'
    copied.write_text('{"id": 43}')
    app.extra_env()
    assert copied.read_text() == '{"id": 43}'
    assert (legacy / "processed.json").read_text() == '{"id": 42}'


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
    assert "BOOKLORE_HOST" not in s_env
    assert "AUDIOBOOK_LIBRARY_URL" not in s_env
    assert s_env["QBITTORRENT_CATEGORY"] == "books"
    assert "DESTINATION_AUDIOBOOK" not in s_env
    assert "QBITTORRENT_CATEGORY_AUDIOBOOK" not in s_env
    # qBittorrent not installed in this fixture → client URL not autofilled yet
    assert "QBITTORRENT_URL" not in s_env


def test_shelfmark_download_client_env_autofills_qbittorrent(tmp_path: Path, monkeypatch):
    from applications.shelfmark_mirrors import (
        shelfmark_download_client_env,
        sync_shelfmark_download_clients,
    )
    from core import settings as settings_mod
    from core.library_layout import LibraryLayout

    cfg = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(settings_mod, "settings", cfg)
    monkeypatch.setattr(
        "applications.shelfmark_mirrors._app_installed",
        lambda name: name == "qbittorrent",
    )
    monkeypatch.setattr("applications.shelfmark_mirrors._app_port", lambda name, default: 8081)
    monkeypatch.setattr(
        "core.integrations.qbittorrent.qbittorrent_credentials",
        lambda: ("aioadmin", "secret"),
    )

    env = shelfmark_download_client_env()
    assert env["PROWLARR_TORRENT_CLIENT"] == "qbittorrent"
    assert env["QBITTORRENT_URL"] == "http://127.0.0.1:8081"
    assert env["QBITTORRENT_USERNAME"] == "aioadmin"
    assert env["QBITTORRENT_PASSWORD"] == "secret"
    assert env["QBITTORRENT_CATEGORY"] == "books"
    assert env["QBITTORRENT_DOWNLOAD_DIR"] == str(LibraryLayout.from_settings(cfg).torrent_path("books"))

    shelf_cfg = tmp_path / "config" / "shelfmark"
    shelf_cfg.mkdir(parents=True)
    assert sync_shelfmark_download_clients(shelf_cfg) is True
    import json

    data = json.loads((shelf_cfg / "settings.json").read_text(encoding="utf-8"))
    assert data["QBITTORRENT_URL"] == "http://127.0.0.1:8081"
    assert data["PROWLARR_TORRENT_CLIENT"] == "qbittorrent"


def test_shelfmark_launcher_uses_vpn_wrapper(catalog, monkeypatch):
    shelfmark = catalog.get("shelfmark")
    runner = shelfmark.install_dir / "run-shelfmark"
    monkeypatch.setattr("core.vpn.vpn_manager.wrap_isolated_command", lambda cmd: ["vpn-wrapper", *cmd])

    assert shelfmark.build_start_command(runner) == ["vpn-wrapper", str(runner)]


def test_shelfmark_updates_managed_usenet_url_when_openvpn_changes(tmp_path, monkeypatch):
    import json

    from applications.shelfmark_mirrors import sync_shelfmark_download_clients

    monkeypatch.setattr("applications.shelfmark_mirrors._app_installed", lambda name: name == "sabnzbd")
    monkeypatch.setattr("applications.shelfmark_mirrors._app_port", lambda name, default: default)
    monkeypatch.setattr("core.integrations.credentials.get_application_api_key", lambda *args: "test-key")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"SABNZBD_URL": "http://127.0.0.1:8085"}))

    for netns, host in [(True, "10.200.200.1"), (False, "127.0.0.1")]:
        monkeypatch.setattr("core.vpn.vpn_manager.uses_netns_isolation", lambda: netns)
        assert sync_shelfmark_download_clients(tmp_path)
        assert json.loads(path.read_text())["SABNZBD_URL"] == f"http://{host}:8085"


@pytest.mark.parametrize("netns, host", [(False, "127.0.0.1"), (True, "10.200.200.1")])
def test_shelfmark_grimmory_urls(tmp_path: Path, monkeypatch, netns, host):
    from applications.community import ShelfmarkApp
    from applications.shelfmark_mirrors import sync_shelfmark_audiobook_library_url
    from core import settings as settings_mod
    from core.public_hostnames import save_hostnames

    cfg = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        cache_dir=tmp_path / "cache",
        public_app_base_domain="example.com",
    )
    monkeypatch.setattr(settings_mod, "settings", cfg)
    monkeypatch.setattr("applications.community.default_settings", cfg)
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    save_hostnames(
        {"grimmory": {"subdomain": "grimmory", "enabled": True}},
        app_settings=cfg,
    )
    monkeypatch.setattr("core.vpn.vpn_manager.uses_netns_isolation", lambda: netns)
    shelfmark = ShelfmarkApp(base_config_dir=cfg.config_dir, base_install_dir=cfg.install_dir)
    monkeypatch.setattr("applications.shelfmark_mirrors._app_installed", lambda name: name == "grimmory")
    env = shelfmark.extra_env()
    assert env["BOOKLORE_HOST"] == f"http://{host}:6060"
    assert sync_shelfmark_audiobook_library_url(shelfmark.config_dir)
    saved = json.loads((shelfmark.config_dir / "settings.json").read_text())
    assert saved["AUDIOBOOK_LIBRARY_URL"] == "https://grimmory.example.com"

