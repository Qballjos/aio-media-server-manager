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
    if (Path(install_dir) / "shelfmark").is_dir() or (Path(install_dir) / "venv").is_dir():
        write_shelfmark_runner(install_dir, port=port)
