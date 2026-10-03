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
    # Default on: stock WebUI remains available by turning the setting off.
    return app_option("qbittorrent", "vuetorrent", default=True, app_settings=app_settings)


def ui_ready(config_dir: Path) -> bool:
    # qBittorrent serves alt UI from <RootFolder>/public/… — index.html must live there.
    return (vuetorrent_dir(config_dir) / "public" / "index.html").is_file()


def ensure_vuetorrent(config_dir: Path, *, app_settings=None) -> bool:
    """Install VueTorrent when the option is on and files are missing.

    Returns True when the alternative UI root is ready to use.
    """
    if not vuetorrent_enabled(app_settings=app_settings):
        return False
    if ui_ready(config_dir):
        return True
    install_vuetorrent(config_dir, app_settings=app_settings)
    return ui_ready(config_dir)


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
        root = _find_ui_root(staging)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(root, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not (target / "public" / "index.html").is_file():
        raise RuntimeError(
            "VueTorrent zip layout is invalid (expected public/index.html under the UI root)."
        )
    _make_webui_readable(target)
    # Prefer VPN uid when WireGuard isolation is on; otherwise PUID/PGID.
    _chown_for_qbittorrent(target)
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
    """Ensure every VueTorrent asset is world-readable (qBittorrent may run as VPN uid)."""
    for path in [root, *root.rglob("*")]:
        try:
            mode = path.stat().st_mode
            path.chmod(mode | (0o755 if path.is_dir() else 0o644))
        except OSError:
            continue


def _chown_for_qbittorrent(root: Path) -> None:
    try:
        from core.vpn import VPN_APP_UID, vpn_manager

        if vpn_manager.settings.vpn_enabled and vpn_manager.uses_uid_isolation():
            uid = VPN_APP_UID
            try:
                gid = int(settings.pgid)
            except (TypeError, ValueError):
                gid = uid
        else:
            uid = int(settings.puid)
            gid = int(settings.pgid)
    except Exception:
        try:
            uid = int(settings.puid)
            gid = int(settings.pgid)
        except Exception:
            return
    try:
        for path in [root, *root.rglob("*")]:
            os.chown(path, uid, gid)
    except Exception:
        logger.debug("Could not chown VueTorrent files to %s:%s", uid, gid, exc_info=True)


def _find_ui_root(extracted: Path) -> Path:
    """Return the folder that contains ``public/index.html`` (qBittorrent RootFolder).

    Pointing RootFolder at ``public/`` itself causes:
    "Unacceptable file type, only regular file is allowed."
    """
    direct = extracted / "public" / "index.html"
    if direct.is_file():
        return extracted
    for child in sorted(extracted.iterdir()) if extracted.is_dir() else []:
        if child.is_dir() and (child / "public" / "index.html").is_file():
            return child
    matches = list(extracted.rglob("public/index.html"))
    if matches:
        # …/<ui-root>/public/index.html → <ui-root>
        return matches[0].parent.parent
    raise RuntimeError(
        "VueTorrent archive must contain public/index.html "
        "(configure RootFolder as the parent of the public/ directory)."
    )
