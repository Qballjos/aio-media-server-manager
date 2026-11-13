from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from applications.plex import PlexApp, plex_linux_build


def test_plex_deb_hierarchy_home_dir_and_env(tmp_path: Path):
    base_install = tmp_path / "apps"
    base_config = tmp_path / "config"
    pms_dir = base_install / "plex" / "usr" / "lib" / "plexmediaserver"
    resources_dir = pms_dir / "Resources"
    lib_dir = pms_dir / "lib"
    resources_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)

    exe = pms_dir / "Plex Media Server"
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)

    cacert = resources_dir / "cacert.pem"
    cacert.write_text("CERTIFICATE DATA\n", encoding="utf-8")

    dummy_lib = lib_dir / "libavcodec.so.60"
    dummy_lib.write_text("ELF", encoding="utf-8")

    app = PlexApp(base_config_dir=base_config, base_install_dir=base_install)

    assert app.home_dir == pms_dir
    assert app.working_directory() == pms_dir
    assert app.start_command() == [str(exe)]

    env = app.extra_env()
    assert env["PLEX_MEDIA_SERVER_HOME"] == str(pms_dir)
    assert (Path(env["PLEX_MEDIA_SERVER_HOME"]) / "Resources" / "cacert.pem").is_file()
    assert env["PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR"] == str(app.config_dir)
    assert app.config_dir.is_dir()
    assert env["PLEX_MEDIA_SERVER_MAX_PLUGIN_PROCS"] == "6"
    assert env["PLEX_MEDIA_SERVER_INFO_VENDOR"] == "aio-media-server-manager"
    assert env["PLEX_MEDIA_SERVER_INFO_DEVICE"] == "aio-media-server-manager"

    # Fallback symlinks created in install_dir
    assert (app.install_dir / "Resources" / "cacert.pem").is_file()
    assert (app.install_dir / "Plex Media Server").is_file()
    assert (app.install_dir / "lib" / "libavcodec.so.60").is_file()

    # LD_LIBRARY_PATH and PATH include home and home/lib
    ld_path = env["LD_LIBRARY_PATH"]
    assert str(pms_dir) in ld_path
    assert str(lib_dir) in ld_path
    assert str(pms_dir) in env["PATH"]


def test_plex_flat_hierarchy_home_dir(tmp_path: Path):
    base_install = tmp_path / "apps"
    base_config = tmp_path / "config"
    plex_install = base_install / "plex"
    resources_dir = plex_install / "Resources"
    resources_dir.mkdir(parents=True)

    exe = plex_install / "Plex Media Server"
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)

    cacert = resources_dir / "cacert.pem"
    cacert.write_text("CERTIFICATE DATA\n", encoding="utf-8")

    app = PlexApp(base_config_dir=base_config, base_install_dir=base_install)

    assert app.home_dir == plex_install
    assert app.working_directory() == plex_install
    env = app.extra_env()
    assert env["PLEX_MEDIA_SERVER_HOME"] == str(plex_install)
    assert (Path(env["PLEX_MEDIA_SERVER_HOME"]) / "Resources" / "cacert.pem").is_file()


def test_plex_install_calls_post_install(tmp_path: Path, monkeypatch):
    from core.settings import settings

    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    base_install = tmp_path / "apps"
    base_config = tmp_path / "config"
    app = PlexApp(base_config_dir=base_config, base_install_dir=base_install)

    fake_payload = {
        "computer": {
            "Linux": {
                "version": "1.43.5.11079-b3b13e506",
                "releases": [
                    {
                        "build": "linux-x86_64",
                        "distro": "debian",
                        "url": "https://downloads.plex.tv/deb/plexmediaserver_1.43.5_amd64.deb",
                    },
                    {
                        "build": "linux-aarch64",
                        "distro": "debian",
                        "url": "https://downloads.plex.tv/deb/plexmediaserver_1.43.5_arm64.deb",
                    },
                ],
            }
        }
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_payload
    monkeypatch.setattr("applications.plex.requests.get", lambda *a, **k: mock_resp)

    def fake_download_file(self_inst, url, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("fake deb", encoding="utf-8")
        return "fake-sha256"

    def fake_activate_archive(self_inst, archive_path, target_install_dir, executable_name, app_name):
        pms_dir = target_install_dir / "usr" / "lib" / "plexmediaserver"
        resources = pms_dir / "Resources"
        resources.mkdir(parents=True, exist_ok=True)
        cacert = resources / "cacert.pem"
        cacert.write_text("CA", encoding="utf-8")
        exe = pms_dir / executable_name
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        exe.chmod(0o755)
        return exe

    monkeypatch.setattr("core.installer.installer.AppInstaller.download_file", fake_download_file)
    monkeypatch.setattr("core.installer.installer.AppInstaller.activate_archive", fake_activate_archive)

    result = app.install()
    assert result.app_name == "plex"
    assert result.version == "1.43.5.11079-b3b13e506"
    assert app.is_installed()

    # Symlinks created by post_install
    assert (app.install_dir / "Resources" / "cacert.pem").is_file()
    assert (app.install_dir / "Plex Media Server").is_file()


@pytest.mark.parametrize("process_state", ["missing", "alive", "denied"])
def test_plex_stale_pid_cleanup(tmp_path, monkeypatch, process_state):
    from applications.plex import cleanup_stale_plex_pid

    support = tmp_path / "Plex Media Server"
    support.mkdir()
    pid_file = support / "plexmediaserver.pid"
    pid_file.write_text("424242\n")

    def probe(pid, sig):
        assert (pid, sig) == (424242, 0)
        if process_state == "missing":
            raise ProcessLookupError()
        if process_state == "denied":
            raise PermissionError()

    monkeypatch.setattr(os, "kill", probe)
    cleanup_stale_plex_pid(tmp_path)
    assert pid_file.exists() == (process_state != "missing")


@pytest.mark.parametrize("contents", ["", "broken", "0", "-1"])
def test_plex_invalid_pid_is_preserved(tmp_path, monkeypatch, contents):
    from applications.plex import cleanup_stale_plex_pid

    support = tmp_path / "Plex Media Server"
    support.mkdir()
    pid_file = support / "plexmediaserver.pid"
    pid_file.write_text(contents)
    cleanup_stale_plex_pid(tmp_path)
    assert pid_file.read_text() == contents


@pytest.mark.parametrize("executable, preserved", [
    ("/config/apps/prowlarr/Prowlarr", False),
    ("/config/apps/plex/Plex Media Server", True),
    ("/config/apps/plex/Plex Media Server (deleted)", True),
])
def test_plex_pid_reused_by_another_executable(tmp_path, monkeypatch, executable, preserved):
    from applications.plex import cleanup_stale_plex_pid

    support = tmp_path / "Plex Media Server"
    support.mkdir()
    pid_file = support / "plexmediaserver.pid"
    pid_file.write_text("376")
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(Path, "readlink", lambda self: Path(executable))

    cleanup_stale_plex_pid(tmp_path)

    assert pid_file.exists() == preserved


def test_plex_reused_pid_preserves_replaced_file(tmp_path, monkeypatch):
    from applications.plex import cleanup_stale_plex_pid

    support = tmp_path / "Plex Media Server"
    support.mkdir()
    pid_file = support / "plexmediaserver.pid"
    pid_file.write_text("376")
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    def executable(self):
        pid_file.write_text("999")
        return Path("/config/apps/prowlarr/Prowlarr")

    monkeypatch.setattr(Path, "readlink", executable)
    cleanup_stale_plex_pid(tmp_path)

    assert pid_file.read_text() == "999"


@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError])
def test_plex_live_pid_with_unknown_executable_is_preserved(tmp_path, monkeypatch, error):
    from applications.plex import cleanup_stale_plex_pid

    support = tmp_path / "Plex Media Server"
    support.mkdir()
    pid_file = support / "plexmediaserver.pid"
    pid_file.write_text("376")
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    def unreadable_executable(self):
        raise error()

    monkeypatch.setattr(Path, "readlink", unreadable_executable)
    cleanup_stale_plex_pid(tmp_path)

    assert pid_file.read_text() == "376"


@pytest.mark.asyncio
async def test_plex_supervisor_cleans_pid_on_every_start(tmp_path):
    import sys
    from core.supervisor import ProcessSupervisor, RestartPolicy

    support = tmp_path / "Plex Media Server"
    support.mkdir()
    pid_file = support / "plexmediaserver.pid"
    supervisor = ProcessSupervisor.get()
    try:
        for _ in range(2):
            # A reaped child gives us a PID known to have exited.
            import subprocess
            child = subprocess.Popen([sys.executable, "-c", "pass"])
            child.wait()
            pid_file.write_text(str(child.pid))
            await supervisor.start(
                "plex", [sys.executable, "-c", "import time; time.sleep(30)"],
                env={"PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR": str(tmp_path)},
                restart_policy=RestartPolicy.NEVER,
                log_dir=tmp_path / "logs",
            )
            assert not pid_file.exists()
            await supervisor.stop("plex", timeout=2)
    finally:
        await supervisor.stop("plex", timeout=2)
