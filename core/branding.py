"""Appliance branding: display title and custom header/logo/favicon images."""

from __future__ import annotations

import json
import logging
import re
import struct
from pathlib import Path
from typing import Any

from core.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "AIO Media Server Manager"
DEFAULT_ACCENT = "#f97316"
MAX_TITLE_LEN = 64
MAX_BYTES = 2 * 1024 * 1024
META_NAME = "branding.json"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Slot → UI guidance + on-disk basename (extension added from upload).
SLOTS: dict[str, dict[str, str]] = {
    "header": {
        "label": "Header icon",
        "help": (
            "Shown in the top navigation bar. "
            "Use a square PNG or WebP. Recommended size: 512 × 512 px "
            "(minimum 128 × 128). Displayed at 44 × 44."
        ),
        "recommended": "512 × 512 px (square)",
        "basename": "header",
    },
    "logo": {
        "label": "Logo",
        "help": (
            "Shown on the login and first-run setup screens. "
            "Use a square PNG or WebP. Recommended size: 512 × 512 px "
            "(minimum 128 × 128). Displayed at about 72 × 72."
        ),
        "recommended": "512 × 512 px (square)",
        "basename": "logo",
    },
    "favicon": {
        "label": "Favicon",
        "help": (
            "Browser tab icon (and home-screen shortcut when installed). "
            "Use a square PNG or ICO. Recommended: 32 × 32 or 64 × 64 px; "
            "180 × 180 px also works well for Apple touch icons."
        ),
        "recommended": "32 × 32 or 64 × 64 px (square)",
        "basename": "favicon",
    },
}

_DEFAULT_STATIC = {
    "header": "/logo-aio-media-manager.png",
    "logo": "/logo-aio-media-manager.png",
    "favicon": "/logo-aio-media-manager.png",
}

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".gif": "image/gif",
}


def branding_dir() -> Path:
    path = Path(settings.config_dir) / "branding"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path() -> Path:
    return branding_dir() / META_NAME


def normalize_accent(value: str | None, *, allow_default_token: bool = False) -> str:
    text = str(value or "").strip()
    if allow_default_token and text.lower() in {"", "default", "reset"}:
        return DEFAULT_ACCENT
    if not text:
        return DEFAULT_ACCENT
    if not text.startswith("#"):
        text = f"#{text}"
    if not _HEX_RE.match(text):
        raise ValueError("Accent must be a hex color like #f97316.")
    return text.lower()


def _load_meta() -> dict[str, Any]:
    path = _meta_path()
    if not path.is_file():
        return {"title": DEFAULT_TITLE, "accent_color": DEFAULT_ACCENT, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read branding meta: %s", exc)
        return {"title": DEFAULT_TITLE, "accent_color": DEFAULT_ACCENT, "files": {}}
    if not isinstance(data, dict):
        return {"title": DEFAULT_TITLE, "accent_color": DEFAULT_ACCENT, "files": {}}
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    title = str(data.get("title") or DEFAULT_TITLE).strip() or DEFAULT_TITLE
    try:
        accent = normalize_accent(data.get("accent_color"))
    except ValueError:
        accent = DEFAULT_ACCENT
    return {
        "title": title[:MAX_TITLE_LEN],
        "accent_color": accent,
        "files": files,
    }


def _save_meta(meta: dict[str, Any]) -> None:
    path = _meta_path()
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def normalize_title(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return DEFAULT_TITLE
    return text[:MAX_TITLE_LEN]


def set_title(value: str | None) -> str:
    meta = _load_meta()
    meta["title"] = normalize_title(value)
    _save_meta(meta)
    return meta["title"]


def set_accent(value: str | None) -> str:
    meta = _load_meta()
    meta["accent_color"] = normalize_accent(value, allow_default_token=True)
    _save_meta(meta)
    return meta["accent_color"]


def _detect_image(data: bytes) -> tuple[str, str] | None:
    """Return (extension, mime) or None if unsupported."""
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if len(data) >= 4 and data[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"):
        return ".ico", "image/x-icon"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif", "image/gif"
    return None


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        width, height = struct.unpack(">II", data[16:24])
    except struct.error:
        return None
    return int(width), int(height)


def _resolve_file(slot: str, meta: dict[str, Any] | None = None) -> Path | None:
    if slot not in SLOTS:
        return None
    meta = meta or _load_meta()
    name = (meta.get("files") or {}).get(slot)
    if not name:
        return None
    path = branding_dir() / Path(str(name)).name
    return path if path.is_file() else None


def asset_url(slot: str, meta: dict[str, Any] | None = None) -> str:
    path = _resolve_file(slot, meta)
    if path is None:
        return _DEFAULT_STATIC[slot]
    mtime = int(path.stat().st_mtime)
    return f"/api/branding/file/{slot}?v={mtime}"


def public_branding() -> dict[str, Any]:
    meta = _load_meta()
    title = normalize_title(meta.get("title"))
    slots_out: dict[str, Any] = {}
    for slot, info in SLOTS.items():
        custom = _resolve_file(slot, meta) is not None
        slots_out[slot] = {
            "label": info["label"],
            "help": info["help"],
            "recommended": info["recommended"],
            "custom": custom,
            "url": asset_url(slot, meta),
        }
    accent = normalize_accent(meta.get("accent_color"))
    return {
        "title": title,
        "default_title": DEFAULT_TITLE,
        "accent_color": accent,
        "default_accent": DEFAULT_ACCENT,
        "accent_custom": accent != DEFAULT_ACCENT,
        "header_url": slots_out["header"]["url"],
        "logo_url": slots_out["logo"]["url"],
        "favicon_url": slots_out["favicon"]["url"],
        "slots": slots_out,
    }


def save_slot(slot: str, data: bytes) -> dict[str, Any]:
    if slot not in SLOTS:
        raise ValueError(f"Unknown branding slot: {slot}")
    if not data:
        raise ValueError("Empty image upload.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"Image must be at most {MAX_BYTES // (1024 * 1024)} MB.")
    detected = _detect_image(data)
    if not detected:
        raise ValueError("Unsupported image type. Use PNG, JPEG, WebP, GIF, or ICO.")
    ext, _mime = detected
    if slot == "favicon" and ext not in {".png", ".ico", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Favicon must be PNG, ICO, JPEG, or WebP.")
    if slot in {"header", "logo"} and ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise ValueError("Use PNG, JPEG, WebP, or GIF for this image.")
    size = _png_size(data)
    if size and (size[0] > 2048 or size[1] > 2048):
        raise ValueError("Image is too large (maximum 2048 × 2048 px).")

    meta = _load_meta()
    basename = SLOTS[slot]["basename"] + ext
    dest = branding_dir() / basename
    # Remove previous file for this slot if extension changed.
    old = _resolve_file(slot, meta)
    dest.write_bytes(data)
    if old is not None and old.resolve() != dest.resolve() and old.is_file():
        try:
            old.unlink()
        except OSError:
            pass
    files = dict(meta.get("files") or {})
    files[slot] = basename
    meta["files"] = files
    _save_meta(meta)
    return public_branding()


def clear_slot(slot: str) -> dict[str, Any]:
    if slot not in SLOTS:
        raise ValueError(f"Unknown branding slot: {slot}")
    meta = _load_meta()
    path = _resolve_file(slot, meta)
    files = dict(meta.get("files") or {})
    files.pop(slot, None)
    meta["files"] = files
    _save_meta(meta)
    if path is not None and path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Could not remove branding file %s: %s", path, exc)
    return public_branding()


def file_for_slot(slot: str) -> tuple[Path, str] | None:
    path = _resolve_file(slot)
    if path is None:
        return None
    mime = _MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return path, mime
