"""TRaSH Guides Recyclarr v8 config and one-shot sync."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from applications.catalog import ApplicationCatalog
from core.integrations.credentials import get_application_api_key
from core.settings import settings

logger = logging.getLogger(__name__)

PREFS_NAME = "amm-prefs.json"
YAML_NAME = "recyclarr.yml"
MANAGED_MARK = "AMM Recyclarr managed"

# Official Recyclarr config-templates / TRaSH guide-backed profile IDs.
_SONARR_WEB_1080P = "72dae194fc92bf828f32cde7744e51a1"
_SONARR_WEB_2160P = "d1498e7d189fbe6c7110ceaabb7473e6"
_SONARR_ANIME_REMUX_1080P = "20e0fc959f1f1704bed501f23bdae76f"
_RADARR_HD_BLURAY_WEB = "d1d67249d3890e49bc12e275d989a7e9"
_RADARR_UHD_BLURAY_WEB = "64fb5f9858489bdac2af690e27c8f42f"

PROFILE_OPTIONS = (
    {
        "id": "sonarr_web_1080p",
        "label": "Sonarr WEB-1080p",
        "guide": "https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/#web-1080p",
        "default": True,
    },
    {
        "id": "sonarr_web_2160p",
        "label": "Sonarr WEB-2160p",
        "guide": "https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/#web-2160p",
        "default": False,
    },
    {
        "id": "sonarr_anime",
        "label": "Sonarr Anime Remux-1080p",
        "guide": "https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles-anime/",
        "default": True,
    },
    {
        "id": "radarr_hd",
        "label": "Radarr HD Bluray + WEB",
        "guide": "https://trash-guides.info/Radarr/radarr-setup-quality-profiles/#hd-bluray-web",
        "default": True,
    },
    {
        "id": "radarr_uhd",
        "label": "Radarr UHD Bluray + WEB",
        "guide": "https://trash-guides.info/Radarr/radarr-setup-quality-profiles/#uhd-bluray-web",
        "default": False,
    },
)

_SONARR_HD_CF = """    custom_format_groups:
      add:
        - trash_id: 158188097a58d7687dee647e04af0da3  # [Optional] Golden Rule HD
        - trash_id: 74aff4168620ed49dcc67e92b2c2a5b4  # [Optional] Language Profiles
        - trash_id: 85fae4a2294965b75710ef2989c850eb  # [Streaming Services] HD/UHD boost
        - trash_id: 59c3af66780d08332fdc64e68297098f  # [Unwanted] Unwanted Formats
"""

_SONARR_UHD_CF = """    custom_format_groups:
      add:
        - trash_id: e3f37512790f00d0e89e54fe5e790d1c  # [Optional] Golden Rule UHD
        - trash_id: 74aff4168620ed49dcc67e92b2c2a5b4  # [Optional] Language Profiles
        - trash_id: 85fae4a2294965b75710ef2989c850eb  # [Streaming Services] HD/UHD boost
        - trash_id: 59c3af66780d08332fdc64e68297098f  # [Unwanted] Unwanted Formats
"""

_RADARR_HD_CF = """    custom_format_groups:
      add:
        - trash_id: f8bf8eab4617f12dfdbd16303d8da245  # [Optional] Golden Rule HD
        - trash_id: a3ac6af01d78e4f21fcb75f601ac96df  # [Unwanted] Unwanted Formats
"""

_RADARR_UHD_CF = """    custom_format_groups:
      add:
        - trash_id: ff204bbcecdd487d1cefcefdbf0c278d  # [Optional] Golden Rule UHD
        - trash_id: a3ac6af01d78e4f21fcb75f601ac96df  # [Unwanted] Unwanted Formats
"""


def default_prefs() -> dict[str, Any]:
    flags = {item["id"]: item["default"] for item in PROFILE_OPTIONS}
    flags["naming"] = "plex"
    flags["user_edited"] = False
    return flags


def prefs_path(config_dir: Path) -> Path:
    return Path(config_dir) / PREFS_NAME


def yaml_path(config_dir: Path) -> Path:
    return Path(config_dir) / YAML_NAME


def load_prefs(config_dir: Path) -> dict[str, Any]:
    path = prefs_path(config_dir)
    data = default_prefs()
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except json.JSONDecodeError:
            pass
    return data


def save_prefs(config_dir: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    merged = default_prefs()
    merged.update(prefs)
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    prefs_path(config_dir).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged


def write_recyclarr_config(
    config_dir: Path,
    *,
    sonarr_url: str,
    sonarr_key: str,
    radarr_url: str,
    radarr_key: str,
    prefs: dict[str, Any] | None = None,
    force: bool = False,
) -> Path:
    root = Path(config_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = yaml_path(root)
    stored = load_prefs(root) if prefs is None else {**default_prefs(), **prefs}
    if path.is_file() and not force and (stored.get("user_edited") or _is_foreign(path)):
        _refresh_endpoints(path, sonarr_url, sonarr_key, radarr_url, radarr_key)
        return path
    naming = str(stored.get("naming") or "plex")
    body = _render_yaml(
        stored,
        sonarr_url=sonarr_url,
        sonarr_key=sonarr_key,
        radarr_url=radarr_url,
        radarr_key=radarr_key,
        naming=naming,
    )
    path.write_text(body, encoding="utf-8")
    save_prefs(root, {**stored, "user_edited": False})
    logger.info("Wrote TRaSH Recyclarr config at %s", path)
    return path


def save_yaml(config_dir: Path, text: str) -> Path:
    path = yaml_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = text.replace("\r\n", "\n")
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")
    save_prefs(config_dir, {**load_prefs(config_dir), "user_edited": True})
    return path


def config_payload() -> dict[str, Any]:
    catalog = ApplicationCatalog()
    plugin = catalog.get("recyclarr") if catalog.has("recyclarr") else None
    config_dir = plugin.config_dir if plugin else settings.config_dir / "recyclarr"
    prefs = load_prefs(config_dir)
    path = yaml_path(config_dir)
    yaml_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {
        "config_dir": str(config_dir),
        "yaml_path": str(path),
        "yaml": yaml_text,
        "prefs": prefs,
        "profiles": PROFILE_OPTIONS,
        "naming_options": [
            {"id": "plex", "label": "Plex (TRaSH default; works with Jellyfin too)"},
            {"id": "jellyfin", "label": "Jellyfin"},
            {"id": "default", "label": "Sonarr/Radarr default"},
        ],
        "user_edited": bool(prefs.get("user_edited")),
        "installed": bool(plugin and plugin.is_installed()),
        "help_url": "https://recyclarr.dev/wiki/guide-configs/",
    }


def apply_prefs_and_render(prefs: dict[str, Any], *, force: bool = True) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    plugin = catalog.get("recyclarr") if catalog.has("recyclarr") else None
    config_dir = plugin.config_dir if plugin else settings.config_dir / "recyclarr"
    sonarr_port = catalog.get("sonarr").port if catalog.has("sonarr") else 8989
    radarr_port = catalog.get("radarr").port if catalog.has("radarr") else 7878
    if prefs.get("naming") not in {"plex", "jellyfin", "default"}:
        prefs = {**prefs, "naming": "plex"}
    merged = save_prefs(config_dir, {**prefs, "user_edited": False})
    write_recyclarr_config(
        config_dir,
        sonarr_url=f"http://127.0.0.1:{sonarr_port}",
        sonarr_key=get_application_api_key("sonarr") or "",
        radarr_url=f"http://127.0.0.1:{radarr_port}",
        radarr_key=get_application_api_key("radarr") or "",
        prefs=merged,
        force=force,
    )
    return config_payload()


def run_sync(timeout: float = 180.0) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    if not catalog.has("recyclarr"):
        return {"ok": False, "detail": "Recyclarr is not in the catalog.", "log": ""}
    plugin = catalog.get("recyclarr")
    if not plugin.is_installed():
        return {"ok": False, "detail": "Install Recyclarr first.", "log": ""}
    write_recyclarr_config(
        plugin.config_dir,
        sonarr_url=f"http://127.0.0.1:{catalog.get('sonarr').port if catalog.has('sonarr') else 8989}",
        sonarr_key=get_application_api_key("sonarr") or "",
        radarr_url=f"http://127.0.0.1:{catalog.get('radarr').port if catalog.has('radarr') else 7878}",
        radarr_key=get_application_api_key("radarr") or "",
        force=False,
    )
    cmd = plugin.start_command()
    env = {**os.environ, **plugin.extra_env()}
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(plugin.working_directory() or plugin.install_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "detail": "Recyclarr binary is missing.", "log": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "Recyclarr sync timed out.", "log": ""}
    log = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    ok = completed.returncode == 0
    return {
        "ok": ok,
        "detail": "Sync finished." if ok else f"Recyclarr exited {completed.returncode}.",
        "log": log[-8000:],
        "returncode": completed.returncode,
    }


def _is_foreign(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MANAGED_MARK in text or "Generated by AIO Media Server Manager" in text:
        return False
    return "trash_id" in text


def _refresh_endpoints(path: Path, sonarr_url: str, sonarr_key: str, radarr_url: str, radarr_key: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(sonarr:[\s\S]*?)base_url:\s*.*", rf"\1base_url: {sonarr_url}", text, count=1)
    if sonarr_key:
        text = re.sub(r"(sonarr:[\s\S]*?)api_key:\s*.*", rf"\1api_key: {sonarr_key}", text, count=1)
    text = re.sub(r"(radarr:[\s\S]*?)base_url:\s*.*", rf"\1base_url: {radarr_url}", text, count=1)
    if radarr_key:
        text = re.sub(r"(radarr:[\s\S]*?)api_key:\s*.*", rf"\1api_key: {radarr_key}", text, count=1)
    path.write_text(text, encoding="utf-8")


def _naming_block(kind: str, style: str) -> str:
    if kind == "sonarr":
        series = {"plex": "plex-tv", "jellyfin": "jellyfin-tv"}.get(style, "default")
        return (
            "    media_naming:\n"
            f"      series: {series}\n"
            "      season: default\n"
            "      episodes:\n"
            "        rename: true\n"
            "        standard: default\n"
            "        daily: default\n"
            "        anime: default\n"
        )
    folder = {"plex": "plex-tmdb", "jellyfin": "jellyfin-tmdb"}.get(style, "default")
    standard = "plex-tmdb" if style == "plex" else "default"
    return (
        "    media_naming:\n"
        f"      folder: {folder}\n"
        "      movie:\n"
        "        rename: true\n"
        f"        standard: {standard}\n"
    )


def _instance(
    *,
    name: str,
    url: str,
    key: str,
    qdef: str,
    trash_id: str,
    comment: str,
    cf_groups: str,
    naming: str,
) -> str:
    return (
        f"  {name}:\n"
        f"    base_url: {url}\n"
        f"    api_key: {key}\n"
        "    delete_old_custom_formats: true\n"
        "    replace_existing_custom_formats: true\n"
        "    quality_definition:\n"
        f"      type: {qdef}\n"
        "    quality_profiles:\n"
        f"      - trash_id: {trash_id}  # {comment}\n"
        "        reset_unmatched_scores:\n"
        "          enabled: true\n"
        f"{cf_groups}"
        f"{naming}"
    )


def _render_yaml(
    prefs: dict[str, Any],
    *,
    sonarr_url: str,
    sonarr_key: str,
    radarr_url: str,
    radarr_key: str,
    naming: str,
) -> str:
    sonarr_blocks: list[str] = []
    if prefs.get("sonarr_web_1080p"):
        sonarr_blocks.append(
            _instance(
                name="web-1080p",
                url=sonarr_url,
                key=sonarr_key,
                qdef="series",
                trash_id=_SONARR_WEB_1080P,
                comment="WEB-1080p",
                cf_groups=_SONARR_HD_CF,
                naming=_naming_block("sonarr", naming),
            )
        )
    if prefs.get("sonarr_web_2160p"):
        sonarr_blocks.append(
            _instance(
                name="web-2160p",
                url=sonarr_url,
                key=sonarr_key,
                qdef="series",
                trash_id=_SONARR_WEB_2160P,
                comment="WEB-2160p",
                cf_groups=_SONARR_UHD_CF,
                naming=_naming_block("sonarr", naming),
            )
        )
    if prefs.get("sonarr_anime"):
        sonarr_blocks.append(
            _instance(
                name="sonarr-anime-remux-1080p",
                url=sonarr_url,
                key=sonarr_key,
                qdef="anime",
                trash_id=_SONARR_ANIME_REMUX_1080P,
                comment="[Anime] Remux-1080p",
                cf_groups="",
                naming=_naming_block("sonarr", naming),
            )
        )
    radarr_blocks: list[str] = []
    if prefs.get("radarr_hd"):
        radarr_blocks.append(
            _instance(
                name="hd-bluray-web",
                url=radarr_url,
                key=radarr_key,
                qdef="movie",
                trash_id=_RADARR_HD_BLURAY_WEB,
                comment="HD Bluray + WEB",
                cf_groups=_RADARR_HD_CF,
                naming=_naming_block("radarr", naming),
            )
        )
    if prefs.get("radarr_uhd"):
        radarr_blocks.append(
            _instance(
                name="uhd-bluray-web",
                url=radarr_url,
                key=radarr_key,
                qdef="movie",
                trash_id=_RADARR_UHD_BLURAY_WEB,
                comment="UHD Bluray + WEB",
                cf_groups=_RADARR_UHD_CF,
                naming=_naming_block("radarr", naming),
            )
        )
    parts = [
        "# yaml-language-server: $schema=https://schemas.recyclarr.dev/v8/config-schema.json",
        f"# {MANAGED_MARK} — official Recyclarr v8 / TRaSH Guides templates.",
        "# HD profiles are on by default. Enable 4K from Catalog → Recyclarr → Settings.",
        "# Edit custom_format_groups here, or reset from Settings to restore TRaSH defaults.",
        "# https://recyclarr.dev/wiki/guide-configs/",
        "",
    ]
    if sonarr_blocks:
        parts.append("sonarr:")
        parts.extend(sonarr_blocks)
    if radarr_blocks:
        parts.append("radarr:")
        parts.extend(radarr_blocks)
    if not sonarr_blocks and not radarr_blocks:
        parts.append("# No TRaSH profiles selected.")
    return "\n".join(parts).rstrip() + "\n"
