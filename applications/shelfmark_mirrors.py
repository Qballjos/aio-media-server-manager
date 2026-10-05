"""Keep Shelfmark bootable when mirror settings contain unparseable URLs.

Shelfmark's startup migrates ``AA_MIRROR_URLS`` through ``urllib.parse.urlparse``.
A value with a stray ``[`` (often a JSON-array paste or a host-level bracket) raises
``ValueError: Invalid IPv6 URL`` and crash-loops gunicorn. AIO sanitizes persisted
settings before launch and wraps the WSGI entrypoint so normalize failures become
empty strings instead of hard crashes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from applications.install_helpers import venv_bin, write_runner

logger = logging.getLogger(__name__)

_MIRROR_LIST_KEYS = (
    "AA_MIRROR_URLS",
    "AA_ADDITIONAL_URLS",
    "LIBGEN_MIRROR_URLS",
    "LIBGEN_ADDITIONAL_URLS",
    "ZLIB_MIRROR_URLS",
    "ZLIB_ADDITIONAL_URLS",
    "WELIB_MIRROR_URLS",
    "WELIB_ADDITIONAL_URLS",
)

_MIRROR_SCALAR_KEYS = (
    "ZLIB_PRIMARY_URL",
    "WELIB_PRIMARY_URL",
)

_PRELOAD_NAME = "aio_shelfmark_app.py"

_PRELOAD_SOURCE = '''\
"""AIO Shelfmark entrypoint: tolerate bad mirror URLs during normalize."""

from __future__ import annotations


def _patch_normalize_http_url() -> None:
    from shelfmark.core import utils

    original = utils.normalize_http_url

    def normalize_http_url(url, *, default_scheme="http", strip_trailing_slash=True, allow_special=()):
        try:
            return original(
                url,
                default_scheme=default_scheme,
                strip_trailing_slash=strip_trailing_slash,
                allow_special=allow_special,
            )
        except ValueError:
            return ""

    utils.normalize_http_url = normalize_http_url  # type: ignore[assignment]


_patch_normalize_http_url()

from shelfmark.main import app  # noqa: E402
'''


def mirror_url_is_safe(url: str, *, allow_special: tuple[str, ...] = ()) -> bool:
    """Return True when *url* survives the same parse path Shelfmark uses."""
    if not isinstance(url, str):
        return False
    normalized = url.strip()
    if not normalized:
        return False

    if (normalized.startswith('"') and normalized.endswith('"')) or (
        normalized.startswith("'") and normalized.endswith("'")
    ):
        normalized = normalized[1:-1].strip()
        if not normalized:
            return False

    if allow_special:
        special = {value.lower() for value in allow_special if isinstance(value, str)}
        if normalized.lower() in special:
            return True

    if normalized.startswith(("/", "./", "../")):
        return True

    candidate = normalized
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False

    if not parsed.scheme or not parsed.netloc:
        return False
    # Reject host fragments that look like failed IPv6 / bracket pastes.
    host = parsed.hostname or ""
    if "[" in parsed.netloc or "]" in parsed.netloc:
        if not (host and ":" in host):
            return False
    return True


def coerce_url_list(value: Any) -> list[str]:
    """Normalize list / CSV / JSON-array mirror values into string items."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        text = str(value).strip()
        return [text] if text else []

    text = value.strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, list):
            return [str(item).strip() for item in loaded if str(item).strip()]

    return [part.strip() for part in text.split(",") if part.strip()]


def sanitize_mirror_list(value: Any, *, allow_special: tuple[str, ...] = ()) -> list[str]:
    """Drop mirror entries that would crash ``urlparse`` / Shelfmark migrate."""
    cleaned: list[str] = []
    for item in coerce_url_list(value):
        if item.lower() == "auto" and "auto" not in {s.lower() for s in allow_special}:
            continue
        if not mirror_url_is_safe(item, allow_special=allow_special):
            logger.warning("Dropping unparseable Shelfmark mirror URL: %r", item)
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def sanitize_shelfmark_settings(config_dir: Path) -> bool:
    """Remove bad mirror URLs from Shelfmark ``settings.json``. Returns True if changed."""
    path = Path(config_dir) / "settings.json"
    if not path.is_file():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Could not read Shelfmark settings at %s", path)
        return False

    if not isinstance(data, dict):
        return False

    changed = False

    for key in _MIRROR_LIST_KEYS:
        if key not in data:
            continue
        cleaned = sanitize_mirror_list(data.get(key))
        if data.get(key) != cleaned:
            data[key] = cleaned
            changed = True

    for key in _MIRROR_SCALAR_KEYS:
        if key not in data:
            continue
        raw = data.get(key)
        if raw in (None, ""):
            continue
        text = str(raw).strip()
        if mirror_url_is_safe(text):
            if data.get(key) != text:
                data[key] = text
                changed = True
            continue
        logger.warning("Clearing unparseable Shelfmark %s value: %r", key, raw)
        data[key] = ""
        changed = True

    if "AA_BASE_URL" in data:
        raw = data.get("AA_BASE_URL")
        text = "" if raw is None else str(raw).strip()
        if text and not mirror_url_is_safe(text, allow_special=("auto",)):
            logger.warning("Resetting unparseable Shelfmark AA_BASE_URL: %r", raw)
            data["AA_BASE_URL"] = "auto"
            changed = True

    if not changed:
        return False

    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Sanitized Shelfmark mirror settings in %s", path)
    return True


def _managed_audiobook_library_candidates(*, port: int = 6060) -> set[str]:
    """URLs AIO treats as auto-managed Grimmory audiobook-library links."""
    from core.app_web_url import catalog_app_browser_url, grimmory_browser_url
    from core.public_hostnames import load_hostnames
    from core.settings import settings

    candidates = {
        f"http://127.0.0.1:{int(port)}",
        f"http://localhost:{int(port)}",
        grimmory_browser_url(port=port),
    }
    base = (settings.public_app_base_domain or "").strip().strip(".").lower()
    entry = load_hostnames().get("grimmory") or {}
    sub = str(entry.get("subdomain") or "grimmory").strip().lower()
    if base and sub:
        candidates.add(f"https://{sub}.{base}")
    last = str(entry.get("last_published") or "").strip().lower()
    if last:
        host = last.split("://", 1)[-1].split("/", 1)[0].strip().strip(".")
        if host:
            candidates.add(f"https://{host}")
    # Always include the non-public form even when a subdomain exists.
    candidates.add(catalog_app_browser_url("grimmory", port=port, base_domain=""))
    return {c.rstrip("/") for c in candidates if c}


def sync_shelfmark_audiobook_library_url(config_dir: Path, *, port: int | None = None) -> bool:
    """Keep AUDIOBOOK_LIBRARY_URL pointed at Grimmory (public when exposed).

    Only rewrites empty values or URLs AIO previously managed (localhost Grimmory
    or the current/previous Grimmory public hostname). Custom targets such as
    Audiobookshelf are left alone.
    """
    from core.app_web_url import grimmory_browser_url

    grimmory_port = int(port) if port else 6060
    if port is None:
        try:
            from applications.catalog import ApplicationCatalog

            cat = ApplicationCatalog()
            if cat.has("grimmory"):
                grimmory_port = int(cat.get("grimmory").port or 6060)
        except Exception:
            grimmory_port = 6060

    desired = grimmory_browser_url(port=grimmory_port).rstrip("/")
    path = Path(config_dir) / "settings.json"
    data: dict[str, Any]
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            logger.warning("Could not read Shelfmark settings at %s", path)
            return False
        if not isinstance(loaded, dict):
            return False
        data = loaded
    else:
        data = {}

    current = "" if data.get("AUDIOBOOK_LIBRARY_URL") is None else str(data.get("AUDIOBOOK_LIBRARY_URL")).strip()
    managed = _managed_audiobook_library_candidates(port=grimmory_port)
    if current and current.rstrip("/") not in managed:
        return False
    if current.rstrip("/") == desired:
        return False

    data["AUDIOBOOK_LIBRARY_URL"] = desired
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Set Shelfmark AUDIOBOOK_LIBRARY_URL to %s", desired)
    return True


def _app_port(name: str, default: int) -> int:
    try:
        from applications.catalog import ApplicationCatalog

        cat = ApplicationCatalog()
        if cat.has(name):
            return int(cat.get(name).port or default)
    except Exception:
        pass
    return int(default)


def _app_installed(name: str) -> bool:
    try:
        from applications.catalog import ApplicationCatalog

        cat = ApplicationCatalog()
        return cat.has(name) and bool(cat.get(name).is_installed())
    except Exception:
        return False


def shelfmark_download_client_env() -> dict[str, str]:
    """Autofill Shelfmark torrent/usenet client fields from AIO-managed downloaders."""
    from core.library_layout import LibraryLayout
    from core.settings import settings as live_settings

    env: dict[str, str] = {
        "QBITTORRENT_CATEGORY": "books",
    }
    layout = LibraryLayout.from_settings(live_settings)
    books_torrent = str(layout.torrent_path("books"))

    if _app_installed("qbittorrent"):
        qb_port = _app_port("qbittorrent", 8081)
        try:
            from core.integrations.qbittorrent import qbittorrent_credentials

            qb_user, qb_pass = qbittorrent_credentials()
        except Exception:
            qb_user, qb_pass = "admin", "adminadmin"
        env.update(
            {
                "PROWLARR_TORRENT_CLIENT": "qbittorrent",
                "QBITTORRENT_URL": f"http://127.0.0.1:{qb_port}",
                "QBITTORRENT_USERNAME": qb_user or "admin",
                "QBITTORRENT_PASSWORD": qb_pass or "",
                "QBITTORRENT_DOWNLOAD_DIR": books_torrent,
            }
        )

    if _app_installed("sabnzbd"):
        sab_port = _app_port("sabnzbd", 8085)
        sab_key = ""
        try:
            from core.integrations.credentials import get_application_api_key
            from core.integrations.sabnzbd import read_sabnzbd_ini

            sab_cfg = live_settings.config_dir / "sabnzbd"
            sab_key = (
                get_application_api_key("sabnzbd", sab_cfg)
                or read_sabnzbd_ini(sab_cfg).get("api_key")
                or ""
            )
        except Exception:
            sab_key = ""
        if sab_key:
            env.update(
                {
                    "PROWLARR_USENET_CLIENT": "sabnzbd",
                    "SABNZBD_URL": f"http://127.0.0.1:{sab_port}",
                    "SABNZBD_API_KEY": sab_key,
                    "SABNZBD_CATEGORY": "books",
                }
            )
    elif _app_installed("nzbget"):
        nzb_port = _app_port("nzbget", 6789)
        try:
            from core.integrations.nzbget import nzbget_credentials

            nzb_user, nzb_pass = nzbget_credentials()
        except Exception:
            nzb_user, nzb_pass = "nzbget", "tegbzn6789"
        env.update(
            {
                "PROWLARR_USENET_CLIENT": "nzbget",
                "NZBGET_URL": f"http://127.0.0.1:{nzb_port}",
                "NZBGET_USERNAME": nzb_user or "nzbget",
                "NZBGET_PASSWORD": nzb_pass or "",
                "NZBGET_CATEGORY": "Books",
            }
        )

    return env


_DOWNLOAD_CLIENT_SETTING_KEYS = (
    "PROWLARR_TORRENT_CLIENT",
    "QBITTORRENT_URL",
    "QBITTORRENT_USERNAME",
    "QBITTORRENT_PASSWORD",
    "QBITTORRENT_CATEGORY",
    "QBITTORRENT_DOWNLOAD_DIR",
    "PROWLARR_USENET_CLIENT",
    "SABNZBD_URL",
    "SABNZBD_API_KEY",
    "SABNZBD_CATEGORY",
    "NZBGET_URL",
    "NZBGET_USERNAME",
    "NZBGET_PASSWORD",
    "NZBGET_CATEGORY",
)


def _managed_download_client_values(desired: dict[str, str]) -> dict[str, set[str]]:
    """Values AIO may safely overwrite per setting key."""
    managed: dict[str, set[str]] = {key: {""} for key in _DOWNLOAD_CLIENT_SETTING_KEYS}
    for key, value in desired.items():
        managed.setdefault(key, {""}).add(str(value).strip())

    qb_port = _app_port("qbittorrent", 8081)
    sab_port = _app_port("sabnzbd", 8085)
    nzb_port = _app_port("nzbget", 6789)
    managed["PROWLARR_TORRENT_CLIENT"].update({"qbittorrent"})
    managed["QBITTORRENT_URL"].update(
        {
            f"http://127.0.0.1:{qb_port}",
            f"http://localhost:{qb_port}",
        }
    )
    managed["QBITTORRENT_USERNAME"].update({"admin"})
    managed["QBITTORRENT_CATEGORY"].update({"books"})
    managed["PROWLARR_USENET_CLIENT"].update({"sabnzbd", "nzbget"})
    managed["SABNZBD_URL"].update(
        {
            f"http://127.0.0.1:{sab_port}",
            f"http://localhost:{sab_port}",
        }
    )
    managed["SABNZBD_CATEGORY"].update({"books"})
    managed["NZBGET_URL"].update(
        {
            f"http://127.0.0.1:{nzb_port}",
            f"http://localhost:{nzb_port}",
        }
    )
    managed["NZBGET_USERNAME"].update({"nzbget", "admin"})
    managed["NZBGET_CATEGORY"].update({"Books", "books"})
    return managed


def sync_shelfmark_download_clients(config_dir: Path) -> bool:
    """Write AIO download-client defaults into Shelfmark settings when still unmanaged."""
    desired = shelfmark_download_client_env()
    if not desired:
        return False

    path = Path(config_dir) / "settings.json"
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            logger.warning("Could not read Shelfmark settings at %s", path)
            return False
        if not isinstance(loaded, dict):
            return False
        data = loaded
    else:
        data = {}

    managed = _managed_download_client_values(desired)
    changed = False
    for key, value in desired.items():
        if key not in _DOWNLOAD_CLIENT_SETTING_KEYS:
            continue
        current = "" if data.get(key) is None else str(data.get(key)).strip()
        allowed = managed.get(key, {""})
        if current and current not in allowed:
            continue
        if current == str(value).strip():
            continue
        data[key] = value
        changed = True

    if not changed:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Synced Shelfmark download client settings from AIO")
    return True


def write_shelfmark_preload(install_dir: Path) -> Path:
    """Write the hardened WSGI module next to the Shelfmark install."""
    target = Path(install_dir) / _PRELOAD_NAME
    target.write_text(_PRELOAD_SOURCE, encoding="utf-8")
    return target


def write_shelfmark_runner(install_dir: Path, *, port: int) -> Path:
    """Rewrite ``run-shelfmark`` to boot through the hardened entrypoint."""
    install_dir = Path(install_dir)
    write_shelfmark_preload(install_dir)
    gunicorn = venv_bin(install_dir / "venv", "gunicorn")
    return write_runner(
        install_dir / "run-shelfmark",
        [
            "#!/bin/sh",
            f'cd "{install_dir}"',
            f'export PYTHONPATH="{install_dir}"',
            f'exec "{gunicorn}" --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker '
            f"--workers 1 -t 300 -b 0.0.0.0:{port} aio_shelfmark_app:app",
        ],
    )


def prepare_shelfmark_runtime(config_dir: Path, install_dir: Path, *, port: int) -> None:
    """Sanitize settings and ensure the hardened launcher exists (install + each start)."""
    sanitize_shelfmark_settings(config_dir)
    sync_shelfmark_audiobook_library_url(config_dir)
    sync_shelfmark_download_clients(config_dir)
    if (Path(install_dir) / "shelfmark").is_dir() or (Path(install_dir) / "venv").is_dir():
        write_shelfmark_runner(install_dir, port=port)
