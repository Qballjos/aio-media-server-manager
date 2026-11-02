"""Run NAS setup scripts with temporary filesystems and fake platform commands."""

import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def compose_mounts(volume):
    text = (volume / "docker/aio-media-manager/docker-compose.yml").read_text()
    return [
        line.strip()[2:]
        for line in text.splitlines()
        if line.strip().startswith("- ") and ":/" in line
    ]


@pytest.fixture
def nas(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = {
        "id": 'case "$1" in -u) echo 0;; -g) echo 0;; *) echo admin;; esac',
        "chown": "exit 0",
        "synopkg": 'exit "${PACKAGE_STATUS:-0}"',
        "docker": 'exit "${DOCKER_STATUS:-0}"',
        "mountpoint": 'exit "${POOL_STATUS:-0}"',
        "curl": f'cat "{ROOT}/deploy/unraid/templates/aio-media-manager.xml"',
    }
    for name, body in scripts.items():
        p = bin_dir / name
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(0o755)
    volume = tmp_path / "volume"
    volume.mkdir()
    (volume / "docker").mkdir()
    data = volume / "media" / "aio"
    data.mkdir(parents=True)
    env = dict(
        os.environ,
        PATH=f'{bin_dir}:{os.environ["PATH"]}',
        VOLUME=str(volume),
        DATA=str(data),
        PUID="99",
        PGID="100",
        CONFIG=str(volume / "config"),
        BACKUPS=str(volume / "backups"),
        TEMPLATE_DIR=str(volume / "templates"),
        SHARE_CONFIG_DIR=str(volume / "shares"),
        CACHE_ROOT=str(volume / "pool"),
    )

    def run(platform, **overrides):
        return subprocess.run(
            ["sh", str(ROOT / f"deploy/{platform}/install.sh")],
            env=dict(env, **overrides),
            text=True,
            capture_output=True,
        )

    return volume, data, run


@pytest.mark.parametrize("failure", ["package", "daemon", "share"])
def test_synology_prerequisites_fail_before_creating_folders(nas, failure):
    volume, data, run = nas
    env = {}
    if failure == "package":
        env["PACKAGE_STATUS"] = "1"
    elif failure == "daemon":
        env["DOCKER_STATUS"] = "1"
    else:
        (volume / "docker").rmdir()
    result = run("synology", **env)
    assert result.returncode != 0
    assert "Container Manager" in result.stderr
    assert not (volume / "docker/aio-media-manager").exists()
    assert not (data / "downloads").exists()


def test_synology_optional_ssd_mounts_keep_library_and_torrents_on_data(nas):
    volume, data, run = nas
    ssd_share = volume / "ssd-downloads"
    ssd_share.mkdir()
    cache = ssd_share / "aio"
    result = run("synology", DOWNLOAD_CACHE=str(cache))
    assert result.returncode == 0, result.stderr
    mounts = compose_mounts(volume)
    assert f"{cache}/incomplete:/data/downloads/incomplete" in mounts
    assert f"{cache}/complete:/data/downloads/complete" in mounts
    assert f"{data}:/data" in mounts
    assert not any(
        ":/data/media" in m or ":/data/downloads/torrents" in m for m in mounts
    )
    assert (cache / "incomplete").is_dir()
    assert (cache / "complete").is_dir()


def test_synology_missing_ssd_share_does_not_get_created(nas):
    volume, _, run = nas
    result = run("synology", DOWNLOAD_CACHE=str(volume / "missing-share/aio"))
    assert result.returncode != 0
    assert not (volume / "missing-share").exists()
    assert not (volume / "docker/aio-media-manager").exists()


def test_synology_does_not_hide_existing_downloads(nas):
    volume, data, run = nas
    (volume / "ssd").mkdir()
    (data / "downloads/incomplete").mkdir(parents=True)
    active = data / "downloads/incomplete/active.part"
    active.write_text("preserve me")
    result = run("synology", DOWNLOAD_CACHE=str(volume / "ssd/aio"))
    assert result.returncode != 0
    assert active.read_text() == "preserve me"
    assert not (volume / "docker/aio-media-manager/docker-compose.yml").exists()


def test_synology_default_install_keeps_single_data_mount(nas):
    volume, data, run = nas
    result = run("synology")
    assert result.returncode == 0, result.stderr
    mounts = compose_mounts(volume)
    assert f"{data}:/data" in mounts
    assert not any(":/data/downloads/" in m for m in mounts)


def test_unraid_requires_mounted_pool_before_writing(nas):
    volume, _, run = nas
    result = run(
        "unraid",
        POOL_STATUS="1",
        CACHE_ROOT=str(volume / "pool"),
        TEMPLATE_DIR=str(volume / "templates"),
    )
    assert result.returncode != 0
    assert "pool" in result.stderr.lower()
    assert not (volume / "templates").exists()
    assert not (volume / "pool").exists()


def test_unraid_templates_stage_on_pool_and_preserve_media_mount():
    for name in ["deploy/unraid.xml", "deploy/unraid/templates/aio-media-manager.xml"]:
        root = ET.parse(ROOT / name).getroot()
        mounts = {
            n.attrib["Target"]: n.text
            for n in root.findall("Config")
            if n.attrib["Type"] == "Path"
        }
        assert mounts["/data"] == "/mnt/user/aio-media-manager"
        assert (
            mounts["/data/downloads/incomplete"]
            == "/mnt/cache/aio-download-cache/incomplete"
        )
        assert (
            mounts["/data/downloads/complete"]
            == "/mnt/cache/aio-download-cache/complete"
        )


def test_unraid_custom_pool_generates_template_and_pool_only_share(nas):
    volume, data, run = nas
    (volume / "pool").mkdir()
    result = run("unraid")
    assert result.returncode == 0, result.stderr
    root = ET.parse(volume / "templates/my-aio-media-manager.xml").getroot()
    mounts = {
        n.attrib["Target"]: n.text
        for n in root.findall("Config")
        if n.attrib["Type"] == "Path"
    }
    assert mounts["/data"] == str(data)
    assert mounts["/data/downloads/incomplete"] == str(
        volume / "pool/aio-download-cache/incomplete"
    )
    assert mounts["/data/downloads/complete"] == str(
        volume / "pool/aio-download-cache/complete"
    )
    config = (volume / "shares/aio-download-cache.cfg").read_text()
    assert 'shareUseCache="only"' in config
    assert 'shareCachePool="pool"' in config
    assert run("unraid").returncode == 0  # safe to prepare again


def test_unraid_refuses_to_hide_populated_downloads(nas):
    volume, data, run = nas
    (volume / "pool").mkdir()
    (data / "downloads/complete").mkdir(parents=True)
    active = data / "downloads/complete/movie.mkv"
    active.write_text("keep")
    result = run("unraid")
    assert result.returncode != 0
    assert active.read_text() == "keep"
    assert not (volume / "templates").exists()


def test_unraid_does_not_reconfigure_existing_cache_share(nas):
    volume, _, run = nas
    (volume / "pool").mkdir()
    (volume / "shares").mkdir()
    config = volume / "shares/aio-download-cache.cfg"
    config.write_text('shareUseCache="yes"\nshareCachePool="other"\n')
    result = run("unraid")
    assert result.returncode != 0
    assert 'shareCachePool="other"' in config.read_text()
    assert not (volume / "templates").exists()


@pytest.mark.parametrize("new_cache", ["", "different"])
def test_synology_rerun_cannot_silently_remove_or_change_ssd_mounts(nas, new_cache):
    volume, _, run = nas
    (volume / "ssd").mkdir()
    cache = volume / "ssd/aio"
    assert run("synology", DOWNLOAD_CACHE=str(cache)).returncode == 0
    compose = volume / "docker/aio-media-manager/docker-compose.yml"
    original = compose.read_text()
    requested = str(volume / "ssd/other") if new_cache else ""
    result = run("synology", DOWNLOAD_CACHE=requested)
    assert result.returncode != 0
    assert compose.read_text() == original


def test_synology_ssd_setup_can_be_prepared_again(nas):
    volume, _, run = nas
    (volume / "ssd").mkdir()
    env = dict(DOWNLOAD_CACHE=str(volume / "ssd/aio"))
    assert run("synology", **env).returncode == 0
    assert run("synology", **env).returncode == 0


def test_synology_missing_package_cannot_move_legacy_downloads(nas):
    volume, _, run = nas
    (volume / "homes/media").mkdir(parents=True)
    legacy = volume / "data/downloads/incomplete"
    legacy.mkdir(parents=True)
    active = legacy / "active.part"
    active.write_text("original")
    result = run("synology", PACKAGE_STATUS="1", DATA="", HOME_USER="media")
    assert result.returncode != 0
    assert active.read_text() == "original"
    assert not (volume / "homes/media/aio-media-manager").exists()


def test_unraid_custom_ownership_is_reflected_in_template(nas):
    volume, _, run = nas
    (volume / "pool").mkdir()
    result = run("unraid", PUID="1234", PGID="5678")
    assert result.returncode == 0, result.stderr
    root = ET.parse(volume / "templates/my-aio-media-manager.xml").getroot()
    values = {n.attrib["Target"]: n for n in root.findall("Config")}
    assert values["PUID"].text == values["PUID"].attrib["Default"] == "1234"
    assert values["PGID"].text == values["PGID"].attrib["Default"] == "5678"


def test_unraid_rerun_cannot_switch_staging_sources(nas):
    volume, _, run = nas
    (volume / "pool").mkdir()
    assert run("unraid").returncode == 0
    template = volume / "templates/my-aio-media-manager.xml"
    original = template.read_text()
    # Even if somebody updates the share configuration, don't hide the old
    # template's staging files by silently generating mounts for a new pool.
    config = volume / "shares/aio-download-cache.cfg"
    config.write_text('shareUseCache="only"\nshareCachePool="fast"\n')
    (volume / "fast").mkdir()
    result = run("unraid", CACHE_ROOT=str(volume / "fast"))
    assert result.returncode != 0
    assert template.read_text() == original
