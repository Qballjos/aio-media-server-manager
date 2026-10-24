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
LOCALES = frozenset({"en", "nl", "de", "fr"})
WALLPAPERS = frozenset({
    "default", "aurora", "candy", "mono", "jellyfin", "plex",
    "forest", "northern", "city", "ocean", "alpine", "dunes", "lavender", "starry", "sunset", "nebula",
    "tide", "retrowave", "personal",
})
# Liquid-glass tuning: panel opacity, backdrop blur (px), parallax depth and how blurred a photo wallpaper is (px).
GLASS_DEFAULTS = {"glass_alpha": 0.5, "glass_blur": 28, "glass_depth": 1.0, "wallpaper_blur": 12}
GLASS_RANGES = {"glass_alpha": (0.15, 0.9), "glass_blur": (0, 60), "glass_depth": (0.0, 2.0), "wallpaper_blur": (0, 40)}
_DEFAULT_META: dict[str, Any] = {
    "avatar": None,
    "theme": "dark",
    "locale": "",
    "wallpaper": "default",
    "wallpaper_image": None,
    "homepage_widget_debug": False,
    "homepage_layout": [],
    "homepage_hidden": [],
    "homepage_sizes": {},
    "homepage_grid": {},
    **GLASS_DEFAULTS,
}


def _normalize_glass(key: str, value: Any) -> float | int:
    low, high = GLASS_RANGES[key]
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(GLASS_DEFAULTS[key])
    number = min(high, max(low, number))
    return int(round(number)) if key.endswith("_blur") else round(number, 2)


SPANS = frozenset({4, 6, 12})


def _normalize_sizes(value: Any) -> dict[str, int]:
    """Home card widths in grid columns (4 = a third, 6 = half, 12 = full); cards not listed share a row."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key, span in list(value.items())[:20]:
        name = str(key).strip()[:32]
        try:
            columns = int(span)
        except (TypeError, ValueError):
            continue
        if name and columns in SPANS:
            out[name] = columns
    return out


GRID_COLUMNS = {"phone": 4, "tablet": 8, "desktop": 12}


def _normalize_grid(value: Any) -> dict[str, list[dict[str, int | str]]]:
    """Home widgets per screen size: id plus place (x, y) and size (w, h) in grid cells; overlaps are the dashboard's job."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[dict[str, int | str]]] = {}
    for size, columns in GRID_COLUMNS.items():
        if size not in value:
            continue
        items = value[size] if isinstance(value[size], list) else []
        kept: list[dict[str, int | str]] = []
        seen: set[str] = set()
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id") or "").strip()[:32]
            try:
                x, y, w, h = (int(item.get(key)) for key in ("x", "y", "w", "h"))
            except (TypeError, ValueError):
                continue
            if not name or name in seen:
                continue
            if x < 0 or w < 1 or x + w > columns or not 0 <= y <= 199 or not 1 <= h <= 12:
                continue
            seen.add(name)
            kept.append({"id": name, "x": x, "y": y, "w": w, "h": h})
        out[size] = kept
    return out


def _normalize_layout(value: Any) -> list[str]:
    """Home block ids in the order the user arranged them; the frontend fills in the rest."""
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        name = str(item).strip()[:32]
        if name and name not in seen:
            seen.append(name)
    return seen[:20]


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


def _normalize_locale(value: Any) -> str:
    code = str(value or "").strip().lower()
    return code if code in LOCALES else ""


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
    meta["locale"] = _normalize_locale(data.get("locale", meta.get("locale")))
    meta["wallpaper"] = _normalize_wallpaper(data.get("wallpaper", meta["wallpaper"]))
    if data.get("wallpaper_image"):
        meta["wallpaper_image"] = str(data["wallpaper_image"])
    meta["homepage_widget_debug"] = bool(data.get("homepage_widget_debug", False))
    meta["homepage_layout"] = _normalize_layout(data.get("homepage_layout"))
    meta["homepage_hidden"] = _normalize_layout(data.get("homepage_hidden"))
    meta["homepage_sizes"] = _normalize_sizes(data.get("homepage_sizes"))
    meta["homepage_grid"] = _normalize_grid(data.get("homepage_grid"))
    for key in GLASS_DEFAULTS:
        meta[key] = _normalize_glass(key, data.get(key, GLASS_DEFAULTS[key]))
    return meta


def _save_meta(meta: dict[str, Any]) -> None:
    profile_dir(create=True)
    payload = {
        "avatar": meta.get("avatar") or None,
        "theme": _normalize_theme(meta.get("theme")),
        "locale": _normalize_locale(meta.get("locale")),
        "wallpaper": _normalize_wallpaper(meta.get("wallpaper")),
        "wallpaper_image": meta.get("wallpaper_image") or None,
        "homepage_widget_debug": bool(meta.get("homepage_widget_debug", False)),
        "homepage_layout": _normalize_layout(meta.get("homepage_layout")),
        "homepage_hidden": _normalize_layout(meta.get("homepage_hidden")),
        "homepage_sizes": _normalize_sizes(meta.get("homepage_sizes")),
        "homepage_grid": _normalize_grid(meta.get("homepage_grid")),
        **{key: _normalize_glass(key, meta.get(key)) for key in GLASS_DEFAULTS},
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
        "locale": _normalize_locale(meta.get("locale")),
        "wallpaper": _normalize_wallpaper(meta.get("wallpaper")),
        "wallpaper_url": url,
        "has_wallpaper_image": url is not None,
        "homepage_widget_debug": bool(meta.get("homepage_widget_debug", False)),
        "homepage_layout": _normalize_layout(meta.get("homepage_layout")),
        "homepage_hidden": _normalize_layout(meta.get("homepage_hidden")),
        "homepage_sizes": _normalize_sizes(meta.get("homepage_sizes")),
        "homepage_grid": _normalize_grid(meta.get("homepage_grid")),
        **{key: _normalize_glass(key, meta.get(key)) for key in GLASS_DEFAULTS},
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
    locale: str | None = None,
    wallpaper: str | None = None,
    homepage_widget_debug: bool | None = None,
    homepage_layout: list[str] | None = None,
    homepage_hidden: list[str] | None = None,
    homepage_sizes: dict[str, int] | None = None,
    homepage_grid: dict[str, Any] | None = None,
    glass_alpha: float | None = None,
    glass_blur: float | None = None,
    glass_depth: float | None = None,
    wallpaper_blur: float | None = None,
) -> dict[str, Any]:
    meta = _load_meta()
    if theme is not None:
        meta["theme"] = _normalize_theme(theme)
    if locale is not None:
        meta["locale"] = _normalize_locale(locale)
    if wallpaper is not None:
        pref = _normalize_wallpaper(wallpaper)
        meta["wallpaper"] = pref
        if pref != "personal":
            # Keep the file on disk so switching back to Personal still works,
            # but do not require it for gradient presets.
            pass
    if homepage_widget_debug is not None:
        meta["homepage_widget_debug"] = bool(homepage_widget_debug)
    if homepage_layout is not None:
        meta["homepage_layout"] = _normalize_layout(homepage_layout)
    if homepage_hidden is not None:
        meta["homepage_hidden"] = _normalize_layout(homepage_hidden)
    if homepage_sizes is not None:
        meta["homepage_sizes"] = _normalize_sizes(homepage_sizes)
    if homepage_grid is not None:
        meta["homepage_grid"] = _normalize_grid(homepage_grid)
    for key, value in (
        ("glass_alpha", glass_alpha),
        ("glass_blur", glass_blur),
        ("glass_depth", glass_depth),
        ("wallpaper_blur", wallpaper_blur),
    ):
        if value is not None:
            meta[key] = _normalize_glass(key, value)
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
