"""
Unit tests for core/installer package.
"""

import hashlib
import io
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.installer.arch import (
    PlatformArch,
    PlatformOS,
    detect_system_arch,
    detect_system_os,
    filename_has_cpu_arch,
    is_arch_neutral_asset,
    linux_gnu_triple,
    matches_arch_pattern,
    score_asset_match,
)
from core.installer.extractor import ArchiveExtractor, ExtractionSecurityError
from core.installer.installer import AppInstaller, _find_venv_executable
from core.settings import Settings


def test_detect_system_arch():
    arch = detect_system_arch()
    assert arch in (PlatformArch.X86_64, PlatformArch.ARM64, PlatformArch.ARMV7, PlatformArch.UNKNOWN)
    assert isinstance(arch.value, str)


def test_detect_system_os():
    os_name = detect_system_os()
    assert os_name in (PlatformOS.LINUX, PlatformOS.DARWIN, PlatformOS.WINDOWS, PlatformOS.UNKNOWN)


def test_matches_arch_pattern():
    # x86_64 / amd64 samples
    assert matches_arch_pattern("Sonarr.main.4.0.14.2939.linux-x64.tar.gz", PlatformArch.X86_64)
    assert not matches_arch_pattern("Sonarr.main.4.0.14.2939.linux-x64.tar.gz", PlatformArch.ARM64)

    # arm64 samples
    assert matches_arch_pattern("Sonarr.main.4.0.14.2939.linux-arm64.tar.gz", PlatformArch.ARM64)
    assert not matches_arch_pattern("Sonarr.main.4.0.14.2939.linux-arm64.tar.gz", PlatformArch.X86_64)

    # Core netcore style
    assert matches_arch_pattern("prowlarr.master.1.31.2.4975.linux-core-x64.tar.gz", PlatformArch.X86_64)
    assert matches_arch_pattern("prowlarr.master.1.31.2.4975.linux-core-arm64.tar.gz", PlatformArch.ARM64)

    # Debian packages
    assert matches_arch_pattern("jellyfin-server_10.10.6-1_amd64.deb", PlatformArch.X86_64)
    assert matches_arch_pattern("jellyfin-server_10.10.6-1_arm64.deb", PlatformArch.ARM64)
    assert not matches_arch_pattern("jellyfin-server_10.10.6-1_amd64.deb", PlatformArch.ARM64)


def test_score_asset_match():
    # Valid linux x64 tarball gets positive score
    score_linux = score_asset_match("app-v1.0.0-linux-x64.tar.gz", PlatformArch.X86_64, PlatformOS.LINUX)
    assert score_linux > 0

    # Windows build should be rejected for Linux target
    score_win = score_asset_match("app-v1.0.0-windows-x64.zip", PlatformArch.X86_64, PlatformOS.LINUX)
    assert score_win < 0

    # Checksum files should be rejected
    score_sum = score_asset_match("app-v1.0.0-linux-x64.tar.gz.sha256", PlatformArch.X86_64, PlatformOS.LINUX)
    assert score_sum < 0

    # Wrong architecture should be rejected
    score_wrong_arch = score_asset_match("app-v1.0.0-linux-arm64.tar.gz", PlatformArch.X86_64, PlatformOS.LINUX)
    assert score_wrong_arch < 0


def test_score_prefers_glibc_linux_core_over_musl():
    musl = score_asset_match(
        "Sonarr.main.4.0.14.2939.linux-musl-x64.tar.gz",
        PlatformArch.X86_64,
        PlatformOS.LINUX,
    )
    core = score_asset_match(
        "Sonarr.main.4.0.14.2939.linux-core-x64.tar.gz",
        PlatformArch.X86_64,
        PlatformOS.LINUX,
    )
    generic = score_asset_match(
        "Sonarr.main.4.0.14.2939.linux-x64.tar.gz",
        PlatformArch.X86_64,
        PlatformOS.LINUX,
    )
    assert core > musl
    assert generic > musl
    assert musl > 0


def test_select_asset_allows_preferred_jar():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "openapi.json", "browser_download_url": "http://example/openapi.json"},
            {"name": "grimmory.jar", "browser_download_url": "http://example/grimmory.jar"},
        ],
    }
    asset = client.select_asset(
        release,
        PlatformArch.ARM64,
        PlatformOS.LINUX,
        preferred_patterns=(r"grimmory\.jar$",),
    )
    assert asset["name"] == "grimmory.jar"


def test_select_asset_rejects_preferred_wrong_arch():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    release = {
        "tag_name": "v3.5.2",
        "assets": [
            {"name": "flaresolverr_linux_x64.tar.gz", "browser_download_url": "http://example/x64"},
            {"name": "flaresolverr_windows_x64.zip", "browser_download_url": "http://example/win"},
        ],
    }
    with pytest.raises(ValueError, match="No compatible binary asset"):
        client.select_asset(
            release,
            PlatformArch.ARM64,
            PlatformOS.LINUX,
            preferred_patterns=(r"flaresolverr_linux",),
        )


def test_select_asset_prefers_matching_linux_arch():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    release = {
        "tag_name": "v3.5.2",
        "assets": [
            {"name": "flaresolverr_linux_x64.tar.gz", "browser_download_url": "http://example/x64"},
            {"name": "flaresolverr_linux_aarch64.tar.gz", "browser_download_url": "http://example/arm"},
        ],
    }
    asset = client.select_asset(
        release,
        PlatformArch.ARM64,
        PlatformOS.LINUX,
        preferred_patterns=(r"flaresolverr_linux",),
    )
    assert asset["name"] == "flaresolverr_linux_aarch64.tar.gz"


def test_filename_has_cpu_arch():
    assert filename_has_cpu_arch("flaresolverr_linux_x64.tar.gz")
    assert filename_has_cpu_arch("flaresolverr_linux_aarch64.tar.gz")
    assert not filename_has_cpu_arch("grimmory.jar")
    assert not filename_has_cpu_arch("linux-generic.tar.gz")


def test_is_arch_neutral_asset():
    assert is_arch_neutral_asset("grimmory.jar")
    assert is_arch_neutral_asset("bazarr.zip")
    assert is_arch_neutral_asset("SABnzbd-4.5.3-src.tar.gz")
    assert not is_arch_neutral_asset("flaresolverr_linux_x64.tar.gz")
    assert not is_arch_neutral_asset("linux-generic.tar.gz")
    assert not is_arch_neutral_asset("nzbget-26.3-amd64.deb")


def test_linux_gnu_triple_never_defaults():
    assert linux_gnu_triple(PlatformArch.X86_64) == "x86_64-unknown-linux-gnu"
    assert linux_gnu_triple(PlatformArch.ARM64) == "aarch64-unknown-linux-gnu"
    with pytest.raises(RuntimeError, match="linux-gnu"):
        linux_gnu_triple(PlatformArch.ARMV7)
    with pytest.raises(RuntimeError, match="linux-gnu"):
        linux_gnu_triple(PlatformArch.UNKNOWN)


def test_select_asset_rejects_unknown_host_arch():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "App.linux-core-x64.tar.gz", "browser_download_url": "http://example/x64"},
        ],
    }
    with pytest.raises(ValueError, match="unrecognized"):
        client.select_asset(release, PlatformArch.UNKNOWN, PlatformOS.LINUX, preferred_patterns=("linux",))


def test_select_asset_rejects_linux_tarball_without_arch():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "recyclarr-linux.tar.gz", "browser_download_url": "http://example/generic"},
        ],
    }
    with pytest.raises(ValueError, match="No compatible binary asset"):
        client.select_asset(
            release,
            PlatformArch.ARM64,
            PlatformOS.LINUX,
            preferred_patterns=("linux",),
        )


def test_select_asset_arr_linux_core_matches_host():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    release = {
        "tag_name": "v4.0.14.2939",
        "assets": [
            {"name": "Sonarr.main.4.0.14.2939.linux-core-x64.tar.gz", "browser_download_url": "u-x64"},
            {"name": "Sonarr.main.4.0.14.2939.linux-core-arm64.tar.gz", "browser_download_url": "u-arm"},
            {"name": "Sonarr.main.4.0.14.2939.osx-core-arm64.tar.gz", "browser_download_url": "u-osx"},
        ],
    }
    arm = client.select_asset(release, PlatformArch.ARM64, PlatformOS.LINUX, preferred_patterns=("linux-core", "linux"))
    x64 = client.select_asset(release, PlatformArch.X86_64, PlatformOS.LINUX, preferred_patterns=("linux-core", "linux"))
    assert arm["name"] == "Sonarr.main.4.0.14.2939.linux-core-arm64.tar.gz"
    assert x64["name"] == "Sonarr.main.4.0.14.2939.linux-core-x64.tar.gz"


def test_select_asset_qbittorrent_and_nzbget_match_host():
    from core.installer.github import GitHubReleaseClient

    client = GitHubReleaseClient()
    qbit = {
        "tag_name": "release-5.0.0",
        "assets": [
            {"name": "x86_64-qbittorrent-nox", "browser_download_url": "u-x64"},
            {"name": "aarch64-qbittorrent-nox", "browser_download_url": "u-arm"},
        ],
    }
    nzb = {
        "tag_name": "v26.3",
        "assets": [
            {"name": "nzbget-26.3-amd64.deb", "browser_download_url": "u-deb-x64"},
            {"name": "nzbget-26.3-arm64.deb", "browser_download_url": "u-deb-arm"},
            {"name": "nzbget-26.3-bin-linux.run", "browser_download_url": "u-run"},
        ],
    }
    assert (
        client.select_asset(qbit, PlatformArch.ARM64, PlatformOS.LINUX, preferred_patterns=("qbittorrent-nox",))["name"]
        == "aarch64-qbittorrent-nox"
    )
    assert (
        client.select_asset(qbit, PlatformArch.X86_64, PlatformOS.LINUX, preferred_patterns=("qbittorrent-nox",))["name"]
        == "x86_64-qbittorrent-nox"
    )
    assert (
        client.select_asset(nzb, PlatformArch.ARM64, PlatformOS.LINUX, preferred_patterns=(r"\.deb$",))["name"]
        == "nzbget-26.3-arm64.deb"
    )
    assert (
        client.select_asset(nzb, PlatformArch.X86_64, PlatformOS.LINUX, preferred_patterns=(r"\.deb$",))["name"]
        == "nzbget-26.3-amd64.deb"
    )


def test_catalog_github_apps_never_select_wrong_cpu(tmp_path):
    from applications.catalog import ApplicationCatalog
    from applications.manifest import InstallMethod
    from core.installer.arch import filename_has_cpu_arch, is_arch_neutral_asset, matches_arch_pattern
    from core.installer.github import GitHubReleaseClient
    from core.settings import Settings

    test_settings = Settings(
        AMM_CONFIG_DIR=tmp_path / "config",
        AMM_DOWNLOAD_DIR=tmp_path / "downloads",
        AMM_MEDIA_DIR=tmp_path / "media",
        AMM_CACHE_DIR=tmp_path / "cache",
        AMM_INSTALL_DIR=tmp_path / "apps",
        PUID=1000,
        PGID=1000,
    )
    catalog = ApplicationCatalog(app_settings=test_settings)
    client = GitHubReleaseClient()
    names = [
        "App.linux-core-x64.tar.gz",
        "App.linux-core-arm64.tar.gz",
        "recyclarr-linux-x64.tar.gz",
        "recyclarr-linux-arm64.tar.gz",
        "x86_64-qbittorrent-nox",
        "aarch64-qbittorrent-nox",
        "nzbget-26.3-amd64.deb",
        "nzbget-26.3-arm64.deb",
        "flaresolverr_linux_x64.tar.gz",
        "flaresolverr_linux_aarch64.tar.gz",
        "linux-generic.tar.gz",
        "bazarr.zip",
        "grimmory.jar",
        "SABnzbd-4.5.3-src.tar.gz",
    ]
    release = {
        "tag_name": "v1.0.0",
        "assets": [{"name": name, "browser_download_url": f"http://example/{name}"} for name in names],
    }
    github_apps = [
        plugin
        for plugin in catalog.all_plugins()
        if plugin.manifest.install_method == InstallMethod.GITHUB_RELEASE
    ]
    assert github_apps, "expected GitHub-release catalog apps"
    for plugin in github_apps:
        for host in (PlatformArch.X86_64, PlatformArch.ARM64):
            try:
                asset = client.select_asset(
                    release,
                    host,
                    PlatformOS.LINUX,
                    preferred_patterns=plugin.preferred_patterns(),
                )
            except ValueError:
                continue
            selected = asset["name"]
            if filename_has_cpu_arch(selected):
                assert matches_arch_pattern(selected, host), (
                    f"{plugin.name} selected {selected} for {host.value}"
                )
            else:
                assert is_arch_neutral_asset(selected), (
                    f"{plugin.name} selected non-neutral {selected} for {host.value}"
                )


def test_plex_linux_build_never_defaults():
    from applications.plex import plex_linux_build

    assert plex_linux_build("x86_64") == "linux-x86_64"
    assert plex_linux_build("arm64") == "linux-aarch64"
    with pytest.raises(RuntimeError, match="not published"):
        plex_linux_build("armv7")
    with pytest.raises(RuntimeError, match="not published"):
        plex_linux_build("unknown")


def test_score_rejects_nzbget_run_installer():
    run = score_asset_match(
        "nzbget-26.3-bin-linux.run",
        PlatformArch.X86_64,
        PlatformOS.LINUX,
    )
    deb = score_asset_match(
        "nzbget-26.3-amd64.deb",
        PlatformArch.X86_64,
        PlatformOS.LINUX,
    )
    assert run < 0
    assert deb > 0


def test_extractor_tar_gz(tmp_path):
    # Create a dummy tar.gz
    archive_path = tmp_path / "test.tar.gz"
    dest_dir = tmp_path / "extracted"

    with tarfile.open(archive_path, "w:gz") as tar:
        file_data = b"echo 'hello world'"
        info = tarfile.TarInfo(name="mybinary")
        info.size = len(file_data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(file_data))

    ArchiveExtractor.extract(archive_path, dest_dir)
    extracted_binary = dest_dir / "mybinary"
    assert extracted_binary.is_file()
    assert extracted_binary.read_bytes() == b"echo 'hello world'"


def test_extractor_zip(tmp_path):
    archive_path = tmp_path / "test.zip"
    dest_dir = tmp_path / "extracted_zip"

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("app/config.json", '{"name": "test"}')

    ArchiveExtractor.extract(archive_path, dest_dir, strip_single_wrapper=False)
    assert (dest_dir / "app" / "config.json").is_file()


def test_extractor_wrapper_stripping(tmp_path):
    archive_path = tmp_path / "wrapped.tar.gz"
    dest_dir = tmp_path / "unwrapped"

    with tarfile.open(archive_path, "w:gz") as tar:
        data = b"binary content"
        info = tarfile.TarInfo(name="TopFolder/subbinary")
        info.size = len(data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(data))

    ArchiveExtractor.extract(archive_path, dest_dir, strip_single_wrapper=True)
    # The TopFolder should be stripped, placing subbinary directly at the root
    assert (dest_dir / "subbinary").is_file()
    assert not (dest_dir / "TopFolder").exists()


def test_extractor_zip_slip_rejection(tmp_path):
    evil_archive = tmp_path / "evil.tar.gz"
    dest_dir = tmp_path / "safe_dir"

    with tarfile.open(evil_archive, "w:gz") as tar:
        data = b"malicious payload"
        info = tarfile.TarInfo(name="../../evil.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    with pytest.raises(ExtractionSecurityError):
        ArchiveExtractor.extract(evil_archive, dest_dir)


def test_transactional_activation(tmp_path):
    test_settings = Settings(
        AMM_CONFIG_DIR=tmp_path / "config",
        AMM_DOWNLOAD_DIR=tmp_path / "downloads",
        AMM_MEDIA_DIR=tmp_path / "media",
        AMM_CACHE_DIR=tmp_path / "cache",
        AMM_INSTALL_DIR=tmp_path / "apps",
        PUID=1000,
        PGID=1000,
    )
    installer = AppInstaller(app_settings=test_settings)

    # 1. Create a mock app archive
    archive_path = tmp_path / "cache" / "sonarr-v1.tar.gz"
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "w:gz") as tar:
        bin_data = b"#!/bin/sh\necho 'Sonarr v1'"
        info = tarfile.TarInfo(name="Sonarr/Sonarr")
        info.size = len(bin_data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(bin_data))

    # Activate archive
    install_target = test_settings.install_dir / "sonarr"
    exe_path = installer.activate_archive(
        archive_path=archive_path,
        target_install_dir=install_target,
        executable_name="Sonarr",
        app_name="sonarr",
    )

    assert exe_path.is_file()
    assert exe_path.name == "Sonarr"
    assert (install_target / "Sonarr").is_file()

    # 2. Upgrade to v2 atomically
    archive_v2 = tmp_path / "cache" / "sonarr-v2.tar.gz"
    with tarfile.open(archive_v2, "w:gz") as tar:
        bin_data = b"#!/bin/sh\necho 'Sonarr v2'"
        info = tarfile.TarInfo(name="Sonarr/Sonarr")
        info.size = len(bin_data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(bin_data))

    exe_path_v2 = installer.activate_archive(
        archive_path=archive_v2,
        target_install_dir=install_target,
        executable_name="Sonarr",
        app_name="sonarr",
    )
    assert exe_path_v2.is_file()
    assert (install_target / "Sonarr").read_bytes() == b"#!/bin/sh\necho 'Sonarr v2'"


@pytest.mark.parametrize("known_length", [True, False])
def test_download_checksum_verification(tmp_path, monkeypatch, known_length):
    test_settings = Settings(
        AMM_CONFIG_DIR=tmp_path / "config",
        AMM_DOWNLOAD_DIR=tmp_path / "downloads",
        AMM_MEDIA_DIR=tmp_path / "media",
        PUID=1000,
        PGID=1000,
    )
    installer = AppInstaller(app_settings=test_settings)

    payload = b"mock payload content"
    expected_hash = hashlib.sha256(payload).hexdigest()

    # Mock requests.get
    class MockResponse:
        def __init__(self, content):
            self.content = content
            self.headers = {"content-length": str(len(content))} if known_length else {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=64):
            yield self.content

    import requests

    monkeypatch.setattr(requests, "get", lambda url, stream=True, timeout=None: MockResponse(payload))

    dest = tmp_path / "downloaded_file.tar.gz"

    # Successful download with matching SHA
    progress = []
    computed_sha = installer.download_file(
        "http://fake.url/pkg.tar.gz", dest, expected_sha256=expected_hash,
        progress_callback=lambda downloaded, total: progress.append((downloaded, total)),
    )
    assert computed_sha == expected_hash
    assert dest.read_bytes() == payload
    assert progress == [(len(payload), len(payload) if known_length else 0)]

    # Corrupted / mismatched SHA raises ValueError and removes temp file
    with pytest.raises(ValueError, match="Checksum verification failed"):
        installer.download_file("http://fake.url/pkg.tar.gz", dest, expected_sha256="wronghash00000000000000000000000000000000000000000000000000000000")


@pytest.mark.parametrize("workflow", ["github", "url", "github_source"])
@pytest.mark.parametrize("custom_callback", [False, True])
def test_install_workflows_report_progress_and_preserve_callback(
    tmp_path, monkeypatch, workflow, custom_callback
):
    from core.install_jobs import clear_jobs, get_job, set_job, update_job

    cfg = Settings(config_dir=tmp_path / "config", install_dir=tmp_path / "apps")
    github = MagicMock()
    github.get_latest_release.return_value = {
        "tag_name": "v1", "zipball_url": "https://example.org/source.zip"
    }
    github.select_asset.return_value = {
        "name": "app.zip", "browser_download_url": "https://example.org/app.zip"
    }
    github.find_checksum.return_value = None
    installer = AppInstaller(app_settings=cfg, github_client=github)
    messages = []
    callback = MagicMock() if custom_callback else None

    def record(name, message):
        update_job(name, message)
        messages.append(get_job(name)["message"])

    def download(*, destination, progress_callback, **kwargs):
        assert get_job("app")["message"] == "Downloading package…"
        if custom_callback:
            assert progress_callback is callback
        progress_callback(1_250_000, 2_000_000)
        progress_callback(1_500_000, 0)
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("app", "executable content")
        return "sha256"

    def permissions(*args, **kwargs):
        assert get_job("app")["message"] == "Setting file permissions…"

    monkeypatch.setattr("core.installer.installer.update_job", record)
    monkeypatch.setattr(installer, "download_file", download)
    monkeypatch.setattr(installer.storage_manager, "apply_permissions", permissions)
    set_job("app", "installing")
    try:
        method = getattr(installer, f"install_from_{workflow}")
        source = "https://example.org/app.zip" if workflow == "url" else "owner/repo"
        result = method(source, "app", "app", progress_callback=callback)
        assert result.executable_path.read_text() == "executable content"
        assert get_job("app")["status"] == "installing"
        assert "Extracting archive…" in messages
        if workflow != "url":
            assert messages[0] == "Finding release…"
        if custom_callback:
            assert callback.call_count == 2
            assert not any(message.startswith("Downloading:") for message in messages)
        else:
            assert "Downloading: 1.2 MB of 2.0 MB" in messages
            assert "Downloading: 1.5 MB" in messages
    finally:
        clear_jobs()


def test_find_venv_executable_names(tmp_path):
    venv = tmp_path / "venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "sabnzbdplus").write_text("#!/bin/sh\n", encoding="utf-8")
    found = _find_venv_executable(tmp_path / "venv", "sabnzbd")
    assert found is not None
    assert found.name == "sabnzbdplus"


def test_write_runner_avoids_package_directory(tmp_path):
    from applications.install_helpers import write_runner

    pkg = tmp_path / "bazarr"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    written = write_runner(pkg, ["#!/bin/sh", "echo ok"])
    assert written == tmp_path / "run-bazarr"
    assert written.is_file()
    assert pkg.is_dir()
    direct = tmp_path / "sabnzbd-bin"
    written2 = write_runner(direct, ["#!/bin/sh", "echo ok"])
    assert written2 == direct
    assert written2.is_file()


def test_launch_argv_prefixes_python_scripts(tmp_path: Path):
    from applications.install_helpers import launch_argv, python_bin

    script = tmp_path / "bazarr.py"
    script.write_text("print(1)\n", encoding="utf-8")
    argv = launch_argv(script, ["--port", "6767"])
    assert argv[0] == python_bin()
    assert argv[1] == str(script)
    assert argv[2:] == ["--port", "6767"]

    binary = tmp_path / "Radarr"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    assert launch_argv(binary, ["-nobrowser"]) == [str(binary), "-nobrowser"]


def test_bazarr_start_uses_python_not_raw_script(tmp_path: Path):
    from applications.extended import BazarrApp

    install_root = tmp_path / "apps"
    (install_root / "bazarr").mkdir(parents=True)
    script = install_root / "bazarr" / "bazarr.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    venv_python = install_root / "bazarr" / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    venv_python.chmod(0o755)
    main = install_root / "bazarr" / "bazarr" / "main.py"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("print('bazarr')\n", encoding="utf-8")

    app = BazarrApp(base_config_dir=tmp_path / "config", base_install_dir=install_root)
    cmd = app.start_command()
    runner = install_root / "bazarr" / "run-bazarr"
    assert runner.is_file()
    runner_text = runner.read_text(encoding="utf-8")
    assert str(venv_python) in runner_text
    assert str(main) in runner_text
    assert "bazarr.py" not in runner_text
    assert cmd[0] == str(runner)
    assert "--no-update" in cmd
    assert str(app.port) in cmd


def test_sabnzbd_start_uses_venv_runner(tmp_path: Path, monkeypatch):
    from applications.sabnzbd import SabnzbdApp

    install_root = tmp_path / "apps"
    app_dir = install_root / "sabnzbd"
    app_dir.mkdir(parents=True)
    (app_dir / "SABnzbd.py").write_text("print('ok')\n", encoding="utf-8")
    venv_python = app_dir / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    venv_python.chmod(0o755)

    app = SabnzbdApp(base_config_dir=tmp_path / "config", base_install_dir=install_root)
    monkeypatch.setattr(app, "_ensure_runtime", lambda: venv_python)
    cmd = app.start_command()
    runner = app_dir / "run-sabnzbd"
    assert runner.is_file()
    assert str(venv_python) in runner.read_text(encoding="utf-8")
    assert cmd[0] == str(runner)
    assert f"0.0.0.0:{app.port}" in cmd
    assert str(app.config_dir / "sabnzbd.ini") in cmd


def test_child_python_prefers_env_override(tmp_path: Path, monkeypatch):
    from applications.install_helpers import child_python

    fake = tmp_path / "python3.13"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("AMM_CHILD_PYTHON", str(fake))
    assert child_python() == str(fake)
