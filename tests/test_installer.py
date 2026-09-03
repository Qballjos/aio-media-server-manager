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

import pytest

from core.installer.arch import (
    PlatformArch,
    PlatformOS,
    detect_system_arch,
    detect_system_os,
    matches_arch_pattern,
    score_asset_match,
)
from core.installer.extractor import ArchiveExtractor, ExtractionSecurityError
from core.installer.installer import AppInstaller
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


def test_download_checksum_verification(tmp_path, monkeypatch):
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
            self.headers = {"content-length": str(len(content))}

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
    computed_sha = installer.download_file("http://fake.url/pkg.tar.gz", dest, expected_sha256=expected_hash)
    assert computed_sha == expected_hash
    assert dest.read_bytes() == payload

    # Corrupted / mismatched SHA raises ValueError and removes temp file
    with pytest.raises(ValueError, match="Checksum verification failed"):
        installer.download_file("http://fake.url/pkg.tar.gz", dest, expected_sha256="wronghash00000000000000000000000000000000000000000000000000000000")
