"""Admin profile assets (avatar, visual preferences)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core import branding as branding_mod
from core.settings import settings

logger = logging.getLogger(__name__)

META_NAME = "profile.json"
AVATAR_BASENAME = "avatar"
WALLPAPER_BASENAME = "wallpaper"
MAX_BYTES = branding_mod.MAX_BYTES
MAX_WALLPAPER_BYTES = 4 * 1024 * 1024
THEMES = frozenset({"dark", "light", "system"})
WALLPAPERS = frozenset({"default", "jellyfin", "plex", "personal"})
_DEFAULT_META: dict[str, Any] = {
    "avatar": None,
    "theme": "dark",
    "wallpaper": "default",
    "wallpaper_image": None,
    "homepage_widget_debug": False,
}


def profile_dir(*, create: bool = True) -> Path:
    path = Path(settings.config_dir) / "profile"
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug("Could not create profile dir %s: %s", path, exc)
    return path


def _meta_path() -> Path:
    return profile_dir(create=False) / META_NAME


def _normalize_theme(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in THEMES else "dark"


def _normalize_wallpaper(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in WALLPAPERS else "default"


def _load_meta() -> dict[str, Any]:
    path = _meta_path()
    meta = dict(_DEFAULT_META)
    if not path.is_file():
        return meta
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read profile meta: %s", exc)
        return meta
    if not isinstance(data, dict):
        return meta
    if data.get("avatar"):
        meta["avatar"] = str(data["avatar"])
    meta["theme"] = _normalize_theme(data.get("theme", meta["theme"]))
    meta["wallpaper"] = _normalize_wallpaper(data.get("wallpaper", meta["wallpaper"]))
    if data.get("wallpaper_image"):
        meta["wallpaper_image"] = str(data["wallpaper_image"])
    meta["homepage_widget_debug"] = bool(data.get("homepage_widget_debug", False))
    return meta


def _save_meta(meta: dict[str, Any]) -> None:
    profile_dir(create=True)
    payload = {
        "avatar": meta.get("avatar") or None,
        "theme": _normalize_theme(meta.get("theme")),
        "wallpaper": _normalize_wallpaper(meta.get("wallpaper")),
        "wallpaper_image": meta.get("wallpaper_image") or None,
        "homepage_widget_debug": bool(meta.get("homepage_widget_debug", False)),
    }
    _meta_path().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _resolve_named(meta_key: str, meta: dict[str, Any] | None = None) -> Path | None:
    meta = meta or _load_meta()
    name = meta.get(meta_key)
    if not name:
        return None
    path = profile_dir(create=False) / Path(str(name)).name
    return path if path.is_file() else None


def _resolve_avatar(meta: dict[str, Any] | None = None) -> Path | None:
    return _resolve_named("avatar", meta)


def _resolve_wallpaper(meta: dict[str, Any] | None = None) -> Path | None:
    return _resolve_named("wallpaper_image", meta)


def avatar_url() -> str | None:
    path = _resolve_avatar()
    if path is None:
        return None
    mtime = int(path.stat().st_mtime)
    return f"/api/auth/avatar?v={mtime}"


def wallpaper_url() -> str | None:
    path = _resolve_wallpaper()
    if path is None:
        return None
    mtime = int(path.stat().st_mtime)
    return f"/api/auth/wallpaper?v={mtime}"


def visual_preferences() -> dict[str, Any]:
    meta = _load_meta()
    url = wallpaper_url()
    return {
        "theme": _normalize_theme(meta.get("theme")),
        "wallpaper": _normalize_wallpaper(meta.get("wallpaper")),
        "wallpaper_url": url,
        "has_wallpaper_image": url is not None,
        "homepage_widget_debug": bool(meta.get("homepage_widget_debug", False)),
    }


def public_profile() -> dict[str, Any]:
    url = avatar_url()
    return {
        "avatar_url": url,
        "has_avatar": url is not None,
        "recommended": "512 × 512 px (square)",
        "help": (
            "Shown in the top bar instead of your username initial. "
            "Use a square PNG, JPEG, or WebP. Recommended size: 512 × 512 px "
            "(minimum 128 × 128). Displayed at about 20 × 20."
        ),
        **visual_preferences(),
    }


def save_visual_preferences(
    *,
    theme: str | None = None,
    wallpaper: str | None = None,
    homepage_widget_debug: bool | None = None,
) -> dict[str, Any]:
    meta = _load_meta()
    if theme is not None:
        meta["theme"] = _normalize_theme(theme)
    if wallpaper is not None:
        pref = _normalize_wallpaper(wallpaper)
        meta["wallpaper"] = pref
        if pref != "personal":
            # Keep the file on disk so switching back to Personal still works,
            # but do not require it for gradient presets.
            pass
    if homepage_widget_debug is not None:
        meta["homepage_widget_debug"] = bool(homepage_widget_debug)
    _save_meta(meta)
    return visual_preferences()


def save_avatar(data: bytes) -> dict[str, Any]:
    if not data:
        raise ValueError("Empty image upload.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"Image must be at most {MAX_BYTES // (1024 * 1024)} MB.")
    detected = branding_mod._detect_image(data)
    if not detected:
        raise ValueError("Unsupported image type. Use PNG, JPEG, WebP, or GIF.")
    ext, _mime = detected
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise ValueError("Use PNG, JPEG, WebP, or GIF for the profile image.")
    size = branding_mod._png_size(data)
    if size and (size[0] > 2048 or size[1] > 2048):
        raise ValueError("Image is too large (maximum 2048 × 2048 px).")

    meta = _load_meta()
    basename = AVATAR_BASENAME + ext
    dest = profile_dir(create=True) / basename
    old = _resolve_avatar(meta)
    dest.write_bytes(data)
    if old is not None and old.resolve() != dest.resolve() and old.is_file():
        try:
            old.unlink()
        except OSError:
            pass
    meta["avatar"] = basename
    _save_meta(meta)
    return public_profile()


def clear_avatar() -> dict[str, Any]:
    meta = _load_meta()
    path = _resolve_avatar(meta)
    meta["avatar"] = None
    _save_meta(meta)
    if path is not None and path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Could not remove profile avatar %s: %s", path, exc)
    return public_profile()


def avatar_file() -> tuple[Path, str] | None:
    path = _resolve_avatar()
    if path is None:
        return None
    mime = branding_mod._MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return path, mime


def save_wallpaper_image(data: bytes) -> dict[str, Any]:
    if not data:
        raise ValueError("Empty image upload.")
    if len(data) > MAX_WALLPAPER_BYTES:
        raise ValueError(f"Image must be at most {MAX_WALLPAPER_BYTES // (1024 * 1024)} MB.")
    detected = branding_mod._detect_image(data)
    if not detected:
        raise ValueError("Unsupported image type. Use JPEG, PNG, or WebP.")
    ext, _mime = detected
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Use JPEG, PNG, or WebP for the background image.")

    meta = _load_meta()
    basename = WALLPAPER_BASENAME + (".jpg" if ext == ".jpeg" else ext)
    dest = profile_dir(create=True) / basename
    old = _resolve_wallpaper(meta)
    dest.write_bytes(data)
    if old is not None and old.resolve() != dest.resolve() and old.is_file():
        try:
            old.unlink()
        except OSError:
            pass
    meta["wallpaper_image"] = basename
    meta["wallpaper"] = "personal"
    _save_meta(meta)
    return visual_preferences()


def clear_wallpaper_image() -> dict[str, Any]:
    meta = _load_meta()
    path = _resolve_wallpaper(meta)
    meta["wallpaper_image"] = None
    if meta.get("wallpaper") == "personal":
        meta["wallpaper"] = "default"
    _save_meta(meta)
    if path is not None and path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Could not remove profile wallpaper %s: %s", path, exc)
    return visual_preferences()


def wallpaper_file() -> tuple[Path, str] | None:
    path = _resolve_wallpaper()
    if path is None:
        return None
    mime = branding_mod._MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return path, mime
