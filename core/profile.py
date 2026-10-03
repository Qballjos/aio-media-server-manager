"""Admin profile assets (avatar image)."""

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
MAX_BYTES = branding_mod.MAX_BYTES


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


def _load_meta() -> dict[str, Any]:
    path = _meta_path()
    if not path.is_file():
        return {"avatar": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read profile meta: %s", exc)
        return {"avatar": None}
    if not isinstance(data, dict):
        return {"avatar": None}
    name = data.get("avatar")
    return {"avatar": str(name) if name else None}


def _save_meta(meta: dict[str, Any]) -> None:
    profile_dir(create=True)
    _meta_path().write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _resolve_avatar(meta: dict[str, Any] | None = None) -> Path | None:
    meta = meta or _load_meta()
    name = meta.get("avatar")
    if not name:
        return None
    path = profile_dir(create=False) / Path(str(name)).name
    return path if path.is_file() else None


def avatar_url() -> str | None:
    path = _resolve_avatar()
    if path is None:
        return None
    mtime = int(path.stat().st_mtime)
    return f"/api/auth/avatar?v={mtime}"


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
    }


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
