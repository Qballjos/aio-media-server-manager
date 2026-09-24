"""Install VueTorrent and point qBittorrent's alternative WebUI at it."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from core.app_prefs import app_option
from core.installer.extractor import ArchiveExtractor
from core.installer.github import GitHubReleaseClient
from core.settings import settings

logger = logging.getLogger(__name__)

VUETORRENT_REPO = "VueTorrent/VueTorrent"
VUETORRENT_HELP = "https://github.com/VueTorrent/VueTorrent"
_UI_DIR = "vuetorrent"
_META_NAME = ".amm_vuetorrent.json"
_ASSET_PATTERNS = (r"^vuetorrent\.zip$", r"vuetorrent.*\.zip$")


def vuetorrent_dir(config_dir: Path) -> Path:
    return Path(config_dir) / _UI_DIR


def vuetorrent_enabled(*, app_settings=None) -> bool:
    return app_option("qbittorrent", "vuetorrent", default=False, app_settings=app_settings)


def ui_ready(config_dir: Path) -> bool:
    return (vuetorrent_dir(config_dir) / "index.html").is_file()


def installed_meta(config_dir: Path) -> dict[str, Any]:
    path = vuetorrent_dir(config_dir) / _META_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def alternative_ui_root(config_dir: Path, *, app_settings=None) -> Path | None:
    if vuetorrent_enabled(app_settings=app_settings) and ui_ready(config_dir):
        root = vuetorrent_dir(config_dir)
        _make_webui_readable(root)
        try:
            return root.resolve()
        except OSError:
            return root.absolute()
    return None


def install_vuetorrent(config_dir: Path, *, app_settings=None) -> dict[str, Any]:
    """Download the latest VueTorrent zip into the qBittorrent config dir."""
    cfg = app_settings or settings
    client = GitHubReleaseClient(token=cfg.github_token)
    release = client.get_latest_release(VUETORRENT_REPO)
    version = str(release.get("tag_name") or "unknown")
    asset = _pick_zip(release)
    url = asset["browser_download_url"]
    name = str(asset.get("name") or "vuetorrent.zip")

    cache_dir = Path(cfg.cache_dir) / "downloads"
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / name
    _download(url, archive_path, token=cfg.github_token)

    target = vuetorrent_dir(config_dir)
    staging = Path(tempfile.mkdtemp(prefix="amm-vuetorrent-"))
    try:
        ArchiveExtractor.extract(archive_path, staging, strip_single_wrapper=True)
        root = _find_index_root(staging)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(root, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not (target / "index.html").is_file():
        raise RuntimeError("VueTorrent zip did not contain index.html.")
    _make_webui_readable(target)
    meta = {"repo": VUETORRENT_REPO, "version": version, "asset": name}
    (target / _META_NAME).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    logger.info("Installed VueTorrent %s at %s", version, target)
    return meta


def _pick_zip(release: dict[str, Any]) -> dict[str, Any]:
    import re

    assets = release.get("assets") or []
    for pattern in _ASSET_PATTERNS:
        for asset in assets:
            if isinstance(asset, dict) and re.search(pattern, str(asset.get("name") or ""), re.I):
                return asset
    names = [str(item.get("name") or "") for item in assets if isinstance(item, dict)]
    raise RuntimeError(f"No vuetorrent.zip in VueTorrent release {release.get('tag_name')}. Assets: {names}")


def _download(url: str, destination: Path, *, token: str | None) -> None:
    import requests

    headers = {"User-Agent": "AIO-Media-Server-Manager/0.1.0", "Accept": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with requests.get(url, headers=headers, stream=True, timeout=(15, 120)) as resp:
        resp.raise_for_status()
        with destination.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    fh.write(chunk)


def _make_webui_readable(root: Path) -> None:
    """qBittorrent runs as PUID/PGID and needs to read every VueTorrent asset."""
    for path in [root, *root.rglob("*")]:
        try:
            mode = path.stat().st_mode
            path.chmod(mode | (0o755 if path.is_dir() else 0o644))
        except OSError:
            continue
    try:
        uid = int(settings.puid)
        gid = int(settings.pgid)
        for path in [root, *root.rglob("*")]:
            os.chown(path, uid, gid)
    except Exception:
        logger.debug("Could not chown VueTorrent files to PUID/PGID", exc_info=True)


def _find_index_root(extracted: Path) -> Path:
    direct = extracted / "index.html"
    if direct.is_file():
        return extracted
    matches = list(extracted.rglob("index.html"))
    if not matches:
        raise RuntimeError("VueTorrent archive has no index.html.")
    return matches[0].parent
